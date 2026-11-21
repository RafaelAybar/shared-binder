"""Orquestación del ETL de Scryfall.

- carga_inicial: carga el fichero bulk completo (solo la primera vez o con --completa).
- cargar_pendientes: carga las expansiones oficiales nuevas y re-sincroniza las recientes.
- cargar_sets: carga o refresca las expansiones indicadas.

Solo se guardan publicaciones oficiales: sets que se venden en papel y ya han salido,
y dentro de ellos las cartas no digitales que ya han salido (nada de previews).
"""

import gzip
import logging
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Final
from uuid import UUID

import psycopg
from pydantic import BaseModel, ValidationError

import bd
from config import DIAS_RESINCRONIZACION, DIRECTORIO_DESCARGAS, TIPO_BULK
from modelos import CartaScryfall, SetScryfall
from scryfall import ClienteScryfall, ErrorScryfall, NoEncontrado

logger = logging.getLogger(__name__)

AVISO_LINEAS: Final = 100_000  # informa del progreso del bulk cada N líneas

# Errores que hacen fallar la carga de una expansión sin parar las demás.
ERRORES_EXPANSION: Final = (ErrorScryfall, OSError, ValidationError, psycopg.Error)


@dataclass
class Resumen:
    sets: int = 0
    insertadas: int = 0
    actualizadas: int = 0
    descartadas: int = 0  # cartas no oficiales: digitales o aún sin publicar
    duplicadas: int = 0  # copias repetidas de una carta; se guarda la última
    invalidas: int = 0  # registros que no superan la validación
    errores: int = 0  # expansiones que no se han podido cargar

    @property
    def correcto(self) -> bool:
        return self.invalidas == 0 and self.errores == 0

    def __str__(self) -> str:
        return (
            f"{self.sets} sets, {self.insertadas} cartas nuevas, "
            f"{self.actualizadas} actualizadas, {self.descartadas} descartadas por no "
            f"oficiales, {self.duplicadas} repetidas, {self.invalidas} registros inválidos, "
            f"{self.errores} errores"
        )


def hoy() -> date:
    return datetime.now(UTC).date()


def es_carta_oficial(carta: CartaScryfall, sets_oficiales: dict[UUID, SetScryfall], dia: date) -> bool:
    return carta.set_id in sets_oficiales and not carta.digital and carta.released_at <= dia


# --- Modos de ejecución ------------------------------------------------------------


def carga_inicial(conn: psycopg.Connection, cliente: ClienteScryfall) -> Resumen:
    """Carga el fichero bulk completo en una única transacción."""
    resumen = Resumen()
    sets = _sets_oficiales(cliente, resumen)
    bulk = cliente.obtener_bulk(TIPO_BULK)
    logger.info("Fichero bulk %s generado el %s", bulk.type, bulk.updated_at.isoformat())
    ruta = cliente.descargar(str(bulk.jsonl_download_uri), bulk.compressed_size, DIRECTORIO_DESCARGAS)

    _guardar(conn, _cartas_del_bulk(ruta, sets, resumen), sets, resumen)

    ruta.unlink()  # solo se borra si todo ha ido bien; si no, se reutiliza al reintentar
    return resumen


def cargar_pendientes(conn: psycopg.Connection, cliente: ClienteScryfall) -> Resumen:
    """Carga las expansiones oficiales que faltan y re-sincroniza las recientes."""
    resumen = Resumen()
    sets = _sets_oficiales(cliente, resumen)
    guardados = bd.sets_guardados(conn)
    limite = hoy() - timedelta(days=DIAS_RESINCRONIZACION)

    # Se compara el par (id, código): también se cargan los sets cuyo código ha cambiado y
    # los que Scryfall ha recreado con otro id. Estos últimos dan error en cada ejecución
    # hasta que se resuelvan, en vez de quedar olvidados.
    nuevas = [s for s in sets.values() if (s.id, s.code) not in guardados and s.card_count > 0]
    recientes = [
        s for s in sets.values() if (s.id, s.code) in guardados and s.released_at >= limite
    ]
    logger.info(
        "%d expansiones nuevas y %d publicadas en los últimos %d días por re-sincronizar",
        len(nuevas), len(recientes), DIAS_RESINCRONIZACION,
    )
    for set_ in sorted(nuevas + recientes, key=lambda s: (s.released_at, s.code)):
        _cargar_expansion_aislada(conn, cliente, set_, resumen)
    return resumen


def cargar_sets(conn: psycopg.Connection, cliente: ClienteScryfall, codigos: Iterable[str]) -> Resumen:
    """Carga o refresca las expansiones indicadas por código (p. ej. fdn, sld)."""
    resumen = Resumen()
    dia = hoy()
    for codigo in codigos:
        try:
            set_ = cliente.obtener_set(codigo)
        except NoEncontrado:
            logger.error("La expansión %r no existe en Scryfall", codigo)
            resumen.errores += 1
            continue
        except ERRORES_EXPANSION:
            logger.exception("No se pudo consultar la expansión %r", codigo)
            resumen.errores += 1
            continue
        if not set_.es_oficial(dia):
            logger.error(
                "La expansión %s no es una publicación oficial (digital=%s, salida=%s); se omite",
                set_.code, set_.digital, set_.released_at,
            )
            resumen.errores += 1
            continue
        _cargar_expansion_aislada(conn, cliente, set_, resumen)
    return resumen


# --- Pasos comunes -----------------------------------------------------------------


def _sets_oficiales(cliente: ClienteScryfall, resumen: Resumen) -> dict[UUID, SetScryfall]:
    dia = hoy()
    sets: dict[UUID, SetScryfall] = {}
    total = 0
    for dato in cliente.listar_sets():
        total += 1
        set_ = _validar(SetScryfall, dato, f"Set {dato.get('code')!r}", resumen)
        if set_ is not None and set_.es_oficial(dia):
            sets[set_.id] = set_
    logger.info("%d de %d sets de Scryfall son oficiales y ya han salido", len(sets), total)
    return sets


def _cartas_del_bulk(
    ruta: Path, sets: dict[UUID, SetScryfall], resumen: Resumen
) -> Iterator[CartaScryfall]:
    """Lee el JSON Lines comprimido línea a línea, sin cargarlo entero en memoria."""
    dia = hoy()
    with gzip.open(ruta, "rb") as fichero:
        for numero, linea in enumerate(fichero, start=1):
            if numero % AVISO_LINEAS == 0:
                logger.info("Procesadas %d líneas del fichero bulk", numero)
            if not linea.strip():
                continue
            carta = _validar(CartaScryfall, linea, f"Línea {numero} del fichero bulk", resumen)
            if carta is None:
                continue
            if not es_carta_oficial(carta, sets, dia):
                resumen.descartadas += 1
                continue
            yield carta


def _cargar_expansion_aislada(
    conn: psycopg.Connection, cliente: ClienteScryfall, set_: SetScryfall, resumen: Resumen
) -> None:
    """Carga una expansión en su propia transacción; si falla, sigue con las demás."""
    logger.info("Cargando expansión %s (%s, %s)", set_.code, set_.name, set_.released_at)
    try:
        cartas = _cartas_de_expansion(cliente, set_, resumen)
        if not cartas:
            logger.warning(
                "La expansión %s aún no tiene cartas oficiales en Scryfall; se reintentará en la próxima ejecución",
                set_.code,
            )
            return
        _guardar(conn, cartas, {set_.id: set_}, resumen)
    except ERRORES_EXPANSION:
        logger.exception("Error cargando la expansión %s; no se ha guardado nada de ella", set_.code)
        resumen.errores += 1


def _cartas_de_expansion(
    cliente: ClienteScryfall, set_: SetScryfall, resumen: Resumen
) -> list[CartaScryfall]:
    """Descarga y valida las cartas antes de abrir la transacción, para no tenerla
    abierta mientras se hacen peticiones HTTP."""
    dia = hoy()
    sets = {set_.id: set_}
    cartas = []
    for dato in cliente.cartas_de_set(set_):
        carta = _validar(CartaScryfall, dato, f"Carta {dato.get('id')} de {set_.code}", resumen)
        if carta is None:
            continue
        if not es_carta_oficial(carta, sets, dia):
            resumen.descartadas += 1
            continue
        cartas.append(carta)
    return cartas


def _guardar(
    conn: psycopg.Connection,
    cartas: Iterable[CartaScryfall],
    sets: dict[UUID, SetScryfall],
    resumen: Resumen,
) -> None:
    """Guarda cartas y sus sets en una transacción.

    Solo se guardan los sets que tienen alguna carta, para que un set vacío se vuelva a
    intentar en la próxima ejecución. Los sets cuyo código ya pertenece a otro set de la
    base de datos se omiten con sus cartas, sin impedir que se guarde el resto.
    """
    vistos: set[UUID] = set()
    omitidas: Counter[UUID] = Counter()  # cartas de sets con el código ocupado

    with conn.transaction():
        ocupados = bd.codigos_ocupados(conn, sets.values())

        def filtrar(origen: Iterable[CartaScryfall]) -> Iterator[CartaScryfall]:
            for carta in origen:
                if carta.set_id in ocupados:
                    omitidas[carta.set_id] += 1
                    continue
                vistos.add(carta.set_id)
                yield carta

        bd.copiar_a_temporal(conn, filtrar(cartas))
        bd.upsert_sets(conn, (sets[i] for i in vistos))  # antes que las cartas (clave ajena)
        fusion = bd.fusionar_cartas(conn)

    for id_set, cantidad in omitidas.items():
        set_ = sets[id_set]
        logger.error(
            "No se guarda la expansión %s (%s) ni sus %d cartas: Scryfall le ha dado el id %s, "
            "pero el código ya pertenece al set %s de la base de datos. Revisa a mano cuál "
            "sobra y vuelve a cargarla con --set %s",
            set_.code, set_.name, cantidad, set_.id, ocupados[id_set], set_.code,
        )
    if fusion.duplicadas:
        logger.warning(
            "%d cartas llegaron repetidas; se ha guardado la última copia de cada una",
            fusion.duplicadas,
        )
    resumen.sets += len(vistos)
    resumen.insertadas += fusion.insertadas
    resumen.actualizadas += fusion.actualizadas
    resumen.duplicadas += fusion.duplicadas
    resumen.errores += len(omitidas)
    logger.info(
        "Guardados %d sets: %d cartas nuevas y %d actualizadas",
        len(vistos), fusion.insertadas, fusion.actualizadas,
    )


def _validar[M: BaseModel](modelo: type[M], dato: Any, contexto: str, resumen: Resumen) -> M | None:
    """Valida un registro; si no es correcto lo registra en el log y devuelve None."""
    try:
        if isinstance(dato, (bytes, str)):
            return modelo.model_validate_json(dato)
        return modelo.model_validate(dato)
    except ValidationError as error:
        resumen.invalidas += 1
        detalle = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or '(raíz)'}: {e['msg']}" for e in error.errors()
        )
        logger.error("%s no es válido y se descarta: %s", contexto, detalle)
        return None
