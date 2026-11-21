"""Tests contra PostgreSQL de lo que resuelve la base de datos: cartas repetidas, filas sin
cambios, sets con el código ocupado, transacciones y el esquema.

Necesitan PostgreSQL 19 o superior y se omiten si no se define TEST_DATABASE_URL:

    TEST_DATABASE_URL=postgresql://usuario:clave@127.0.0.1:5432/basedatos pytest

Cada test crea su propio esquema (test_etl_xxxxxxxx) y lo borra al terminar, así que no
toca las tablas del esquema public.
"""

import json
import os
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from psycopg import sql

import bd
import etl
from ejemplos import (
    ID_DELVER,
    ID_DSK,
    ID_FDN,
    ID_FDN_ANTIGUO,
    ID_LLANOWAR,
    ID_RAYO,
    imagen,
    set_scryfall,
    tres_cartas,
)
from falsos import ClienteFalso
from modelos import SetScryfall

URL_BD = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = [
    pytest.mark.bd,
    pytest.mark.skipif(not URL_BD, reason="define TEST_DATABASE_URL para probar con PostgreSQL"),
]


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    esquema = sql.Identifier(f"test_etl_{os.urandom(4).hex()}")
    with psycopg.connect(URL_BD, autocommit=True) as conexion:
        conexion.execute(sql.SQL("CREATE SCHEMA {}").format(esquema))
        try:
            conexion.execute(sql.SQL("SET search_path TO {}, public").format(esquema))
            bd.crear_esquema(conexion)
            yield conexion
        finally:
            conexion.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(esquema))


def cargar(conn: psycopg.Connection, cartas: list[dict[str, Any]]) -> etl.Resumen:
    """Carga las cartas como lo haría python main.py --set fdn."""
    return etl.cargar_sets(conn, ClienteFalso([set_scryfall("fdn")], {"fdn": cartas}), ["fdn"])


def columna(conn: psycopg.Connection, nombre: str) -> dict[str, Any]:
    """{id de carta: valor} de una columna de mtg_cards."""
    consulta = sql.SQL("SELECT id, {} FROM mtg_cards").format(sql.Identifier(nombre))
    return {str(id_): valor for id_, valor in conn.execute(consulta)}


def hay_tabla_temporal(conn: psycopg.Connection) -> bool:
    fila = conn.execute("SELECT to_regclass('pg_temp.tmp_cards')").fetchone()
    return fila is not None and fila[0] is not None


# --- Carga y actualización ---------------------------------------------------------


def test_cada_dato_se_guarda_en_su_columna(conn: psycopg.Connection) -> None:
    resumen = cargar(conn, tres_cartas())

    assert (resumen.insertadas, resumen.actualizadas, resumen.errores) == (3, 0, 0)
    filas = conn.execute(
        "SELECT id, lang, printed_name, mana_cost, image_small_url, image_small_back_url"
        " FROM mtg_cards"
    )
    assert {str(f[0]): f[1:] for f in filas} == {
        ID_LLANOWAR: ("en", None, "{G}", imagen(ID_LLANOWAR), None),
        ID_DELVER: ("en", None, None, imagen(ID_DELVER), imagen(ID_DELVER, "back")),
        ID_RAYO: ("es", "Rayo", "{R}", imagen(ID_RAYO), None),
    }
    assert conn.execute("SELECT code, name FROM mtg_sets").fetchall() == [("fdn", "Foundations")]


def test_repetir_la_carga_no_toca_ninguna_fila(conn: psycopg.Connection) -> None:
    cargar(conn, tres_cartas())
    antes = columna(conn, "updated_at")

    resumen = cargar(conn, tres_cartas())

    assert (resumen.insertadas, resumen.actualizadas) == (0, 0)
    assert columna(conn, "updated_at") == antes


def test_solo_se_actualiza_la_carta_que_cambia(conn: psycopg.Connection) -> None:
    cargar(conn, tres_cartas())
    antes = columna(conn, "updated_at")
    cartas = tres_cartas()
    nueva = imagen(ID_DELVER, "back", version=1740000000)  # Scryfall ha vuelto a escanearla
    cartas[1]["card_faces"][1]["image_uris"]["small"] = nueva

    resumen = cargar(conn, cartas)

    assert (resumen.insertadas, resumen.actualizadas) == (0, 1)
    assert columna(conn, "image_small_back_url")[ID_DELVER] == nueva
    despues = columna(conn, "updated_at")
    assert despues[ID_DELVER] > antes[ID_DELVER]
    assert (despues[ID_LLANOWAR], despues[ID_RAYO]) == (antes[ID_LLANOWAR], antes[ID_RAYO])


# --- Cartas duplicadas -------------------------------------------------------------


@pytest.mark.parametrize("orden", ["la nueva al final", "la nueva al principio"])
def test_carta_repetida_se_guarda_la_ultima_copia(conn: psycopg.Connection, orden: str) -> None:
    llanowar, delver, _ = tres_cartas()
    otra = llanowar | {"image_uris": {"small": imagen(ID_LLANOWAR, version=1740000000)}}
    lote = [llanowar, delver, otra] if orden == "la nueva al final" else [otra, delver, llanowar]

    resumen = cargar(conn, lote)

    assert (resumen.insertadas, resumen.duplicadas, resumen.errores) == (2, 1, 0)
    assert columna(conn, "image_small_url")[ID_LLANOWAR] == lote[-1]["image_uris"]["small"]


def test_carta_repetida_no_alterna_entre_versiones(conn: psycopg.Connection) -> None:
    """Dos cargas con las mismas copias guardan siempre la misma: sin falsos cambios."""
    llanowar, delver, _ = tres_cartas()
    otra = llanowar | {"image_uris": {"small": imagen(ID_LLANOWAR, version=1740000000)}}
    cargar(conn, [llanowar, delver, otra])

    resumen = cargar(conn, [llanowar, delver, otra])

    assert (resumen.insertadas, resumen.actualizadas, resumen.duplicadas) == (0, 0, 1)


# --- Errores -----------------------------------------------------------------------


def test_set_recreado_con_el_mismo_codigo_no_bloquea_el_resto(
    conn: psycopg.Connection, tmp_path
) -> None:
    bd.upsert_sets(conn, [SetScryfall.model_validate(set_scryfall("fdn", id=ID_FDN_ANTIGUO))])
    cartas = tres_cartas(ID_FDN)
    cartas[2]["set_id"] = ID_DSK
    cliente = ClienteFalso(
        [set_scryfall("fdn"), set_scryfall("dsk")],
        bulk=[json.dumps(c) for c in cartas],
        directorio=tmp_path,
    )

    resumen = etl.carga_inicial(conn, cliente)  # sin UniqueViolation

    assert resumen.errores == 1
    sets = {codigo: str(id_) for codigo, id_ in conn.execute("SELECT code, id FROM mtg_sets")}
    assert sets == {"fdn": ID_FDN_ANTIGUO, "dsk": ID_DSK}
    assert list(columna(conn, "name")) == [ID_RAYO]


def test_si_falla_la_carga_inicial_no_se_guarda_nada(
    conn: psycopg.Connection, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fusion_que_falla(conexion: psycopg.Connection) -> bd.ResultadoFusion:
        raise psycopg.errors.DiskFull("no queda espacio en el disco")

    monkeypatch.setattr(bd, "fusionar_cartas", fusion_que_falla)  # después de guardar el set
    cliente = ClienteFalso(
        [set_scryfall("fdn")], bulk=[json.dumps(c) for c in tres_cartas()], directorio=tmp_path
    )

    with pytest.raises(psycopg.errors.DiskFull):
        etl.carga_inicial(conn, cliente)

    assert conn.execute("SELECT count(*) FROM mtg_sets").fetchone() == (0,)
    assert conn.execute("SELECT count(*) FROM mtg_cards").fetchone() == (0,)
    assert not hay_tabla_temporal(conn)


def test_carta_que_postgresql_rechaza_solo_hace_fallar_su_expansion(
    conn: psycopg.Connection,
) -> None:
    """Pydantic acepta el carácter NUL en un texto, pero PostgreSQL no."""
    cartas = tres_cartas()
    cartas[2] |= {"set_id": ID_DSK, "printed_name": "Ra\x00yo"}
    cliente = ClienteFalso(
        [set_scryfall("fdn"), set_scryfall("dsk")], {"fdn": cartas[:2], "dsk": cartas[2:]}
    )

    resumen = etl.cargar_sets(conn, cliente, ["fdn", "dsk"])

    assert (resumen.insertadas, resumen.errores) == (2, 1)
    assert conn.execute("SELECT code FROM mtg_sets").fetchall() == [("fdn",)]
    assert sorted(columna(conn, "name")) == [ID_LLANOWAR, ID_DELVER]
    assert not hay_tabla_temporal(conn)


# --- Esquema -----------------------------------------------------------------------


def test_numeros_de_coleccion_en_orden_natural(conn: psycopg.Connection) -> None:
    cartas = tres_cartas()
    for carta, numero in zip(cartas, ["10", "2", "1a"], strict=True):
        carta["collector_number"] = numero
    cargar(conn, cartas)

    numeros = conn.execute("SELECT collector_number FROM mtg_cards ORDER BY collector_number")

    assert [n for (n,) in numeros] == ["1a", "2", "10"]  # no "10", "1a", "2"
