"""Acceso a PostgreSQL: esquema, consultas y volcado de sets y cartas."""

from collections.abc import Iterable
from pathlib import Path
from typing import Final

import psycopg

from config import PG_DATABASE, PG_HOST, PG_PASSWORD, PG_PORT, PG_USER
from modelos import CartaScryfall, SetScryfall

FICHERO_ESQUEMA: Final = Path(__file__).resolve().parent / "esquema.sql"

COLUMNAS_SETS: Final = (
    "id", "code", "name", "set_type", "released_at", "card_count", "parent_set_code",
    "icon_svg_uri",
)
COLUMNAS_CARTAS: Final = (
    "id", "oracle_id", "set_id", "collector_number", "lang", "name", "printed_name",
    "rarity", "layout", "mana_cost", "type_line", "released_at", "image_small_url",
    "image_small_back_url",
)


def _upsert(tabla: str, columnas: tuple[str, ...]) -> str:
    """Parte común de los upsert: ON CONFLICT (id) que solo toca las filas que cambian,
    para que updated_at refleje cambios reales. Las columnas son constantes del módulo."""
    datos = [c for c in columnas if c != "id"]
    return f"""
        ON CONFLICT (id) DO UPDATE SET
            {", ".join(f"{c} = EXCLUDED.{c}" for c in datos)},
            updated_at = now()
        WHERE ({", ".join(f"{tabla}.{c}" for c in datos)})
            IS DISTINCT FROM ({", ".join(f"EXCLUDED.{c}" for c in datos)})
    """


SQL_UPSERT_SETS: Final = f"""
    INSERT INTO mtg_sets ({", ".join(COLUMNAS_SETS)})
    VALUES ({", ".join(["%s"] * len(COLUMNAS_SETS))})
    {_upsert("mtg_sets", COLUMNAS_SETS)}
"""

# DISTINCT ON evita el error de ON CONFLICT si una carta llegara repetida. xmax = 0
# identifica las filas insertadas (las actualizadas tienen xmax distinto de 0).
SQL_FUSIONAR_CARTAS: Final = f"""
    WITH filas AS (
        INSERT INTO mtg_cards ({", ".join(COLUMNAS_CARTAS)})
        SELECT DISTINCT ON (id) {", ".join(COLUMNAS_CARTAS)} FROM tmp_cards ORDER BY id
        {_upsert("mtg_cards", COLUMNAS_CARTAS)}
        RETURNING (xmax = 0) AS insertada
    )
    SELECT count(*) FILTER (WHERE insertada), count(*) FILTER (WHERE NOT insertada)
    FROM filas
"""


def conectar() -> psycopg.Connection:
    """Conexión en autocommit: cada carga abre su propia transacción explícita."""
    return psycopg.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD,
        application_name="shared-binder-etl",
        autocommit=True,
    )


def crear_esquema(conn: psycopg.Connection) -> None:
    with conn.transaction():
        conn.execute(FICHERO_ESQUEMA.read_text(encoding="utf-8"))


def hay_sets(conn: psycopg.Connection) -> bool:
    fila = conn.execute("SELECT EXISTS (SELECT 1 FROM mtg_sets)").fetchone()
    return bool(fila and fila[0])


def codigos_sets(conn: psycopg.Connection) -> set[str]:
    return {codigo for (codigo,) in conn.execute("SELECT code FROM mtg_sets")}


def upsert_sets(conn: psycopg.Connection, sets: Iterable[SetScryfall]) -> None:
    filas = [
        (s.id, s.code, s.name, s.set_type, s.released_at, s.card_count, s.parent_set_code,
         str(s.icon_svg_uri) if s.icon_svg_uri else None)
        for s in sets
    ]
    if filas:
        with conn.cursor() as cur:
            cur.executemany(SQL_UPSERT_SETS, filas)


def copiar_a_temporal(conn: psycopg.Connection, cartas: Iterable[CartaScryfall]) -> None:
    """Vuelca las cartas con COPY a la tabla temporal tmp_cards.

    Debe llamarse dentro de conn.transaction(): la tabla se borra al terminar la
    transacción. Después hay que llamar a fusionar_cartas.
    """
    with conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE tmp_cards (LIKE mtg_cards INCLUDING DEFAULTS) ON COMMIT DROP")
        with cur.copy(f"COPY tmp_cards ({', '.join(COLUMNAS_CARTAS)}) FROM STDIN") as copia:
            for c in cartas:
                copia.write_row((
                    c.id, c.oracle_id, c.set_id, c.collector_number, c.lang, c.name,
                    c.printed_name, c.rarity, c.layout, c.mana_cost, c.type_line,
                    c.released_at, c.imagen_small, c.imagen_small_trasera,
                ))


def fusionar_cartas(conn: psycopg.Connection) -> tuple[int, int]:
    """Pasa tmp_cards a mtg_cards. Devuelve (insertadas, actualizadas)."""
    fila = conn.execute(SQL_FUSIONAR_CARTAS).fetchone()
    assert fila is not None
    return fila[0], fila[1]
