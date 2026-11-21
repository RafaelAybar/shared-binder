"""Dobles de prueba: sustituyen a la API de Scryfall y a PostgreSQL en los tests."""

import gzip
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from bd import ResultadoFusion
from modelos import BulkScryfall, CartaScryfall, SetScryfall
from scryfall import NoEncontrado


class ClienteFalso:
    """Sustituye a ClienteScryfall con respuestas preparadas por el test.

    - sets: objetos set de GET /sets.
    - cartas: cartas que devuelve la búsqueda de cada set, por código.
    - bulk: líneas del fichero bulk; descargar() las escribe comprimidas en directorio.
    - fallos: excepción que lanza la búsqueda de un set, por código.
    """

    def __init__(
        self,
        sets: list[dict[str, Any]],
        cartas: dict[str, list[dict[str, Any]]] | None = None,
        *,
        bulk: Iterable[str] = (),
        directorio: Path | None = None,
        fallos: dict[str, Exception] | None = None,
    ) -> None:
        self.sets = sets
        self.cartas = cartas or {}
        self.bulk = list(bulk)
        self.directorio = directorio
        self.fallos = fallos or {}
        self.pedidas: list[str] = []  # códigos de los sets cuyas cartas se han buscado
        self.ruta_bulk: Path | None = None  # fichero bulk "descargado"

    def listar_sets(self) -> Iterator[dict[str, Any]]:
        return iter(self.sets)

    def obtener_set(self, codigo: str) -> SetScryfall:
        for dato in self.sets:
            if dato["code"] == codigo:
                return SetScryfall.model_validate(dato)
        raise NoEncontrado(f"404 en /sets/{codigo}")

    def cartas_de_set(self, set_: SetScryfall) -> Iterator[dict[str, Any]]:
        self.pedidas.append(set_.code)
        if set_.code in self.fallos:
            raise self.fallos[set_.code]
        return iter(self.cartas.get(set_.code, []))

    def obtener_bulk(self, tipo: str) -> BulkScryfall:
        return BulkScryfall.model_validate({
            "type": tipo,
            "updated_at": "2025-03-01T09:00:00+00:00",
            "jsonl_download_uri": f"https://data.scryfall.io/{tipo}/{tipo}-20250301.jsonl.gz",
            "compressed_size": 0,
        })

    def descargar(self, url: str, tamano: int, directorio: Path) -> Path:
        assert self.directorio is not None, "la carga inicial necesita directorio=tmp_path"
        self.ruta_bulk = self.directorio / Path(urlsplit(url).path).name
        with gzip.open(self.ruta_bulk, "wt", encoding="utf-8") as fichero:
            fichero.writelines(f"{linea}\n" for linea in self.bulk)
        return self.ruta_bulk


class BDFalsa:
    """Sustituye a PostgreSQL: hace de conexión y de las funciones de bd.py que usa etl.py
    (el fixture bd_falsa de conftest.py las cambia por estos métodos).

    Guarda en memoria lo que llegaría a la base de datos. Como en una transacción real,
    las cartas de una carga que falla no se guardan.
    """

    def __init__(self) -> None:
        self.guardados: set[tuple[UUID, str]] = set()  # (id, código) de los sets guardados
        self.cartas: list[CartaScryfall] = []  # cartas guardadas, en el orden de llegada
        self.sets: list[SetScryfall] = []  # sets guardados, en el orden de llegada
        self.fallos: dict[UUID, Exception] = {}  # error al copiar una carta de ese set
        self.resultado: ResultadoFusion | None = None  # respuesta fija de fusionar_cartas
        self._lote: list[CartaScryfall] = []

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self._lote = []
        yield

    def sets_guardados(self, conn: "BDFalsa") -> set[tuple[UUID, str]]:
        return set(self.guardados)

    def codigos_ocupados(self, conn: "BDFalsa", sets: Iterable[SetScryfall]) -> dict[UUID, UUID]:
        id_por_codigo = {codigo: id_ for id_, codigo in self.guardados}
        return {
            s.id: id_por_codigo[s.code]
            for s in sets
            if s.code in id_por_codigo and id_por_codigo[s.code] != s.id
        }

    def copiar_a_temporal(self, conn: "BDFalsa", cartas: Iterable[CartaScryfall]) -> None:
        for carta in cartas:
            if carta.set_id in self.fallos:
                raise self.fallos[carta.set_id]
            self._lote.append(carta)

    def upsert_sets(self, conn: "BDFalsa", sets: Iterable[SetScryfall]) -> None:
        for set_ in sets:
            self.sets.append(set_)
            self.guardados = {p for p in self.guardados if p[0] != set_.id} | {(set_.id, set_.code)}

    def fusionar_cartas(self, conn: "BDFalsa") -> ResultadoFusion:
        self.cartas.extend(self._lote)
        return self.resultado or ResultadoFusion(len(self._lote), 0, 0)
