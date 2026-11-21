"""Acceso a PostgreSQL: esquema, consultas y volcado de sets y cartas."""

from collections.abc import Iterable
from pathlib import Path
from typing import Final, NamedTuple
from uuid import UUID

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

# orden numera las cartas según llegan en el COPY.
SQL_CREAR_TEMPORAL: Final = """
    CREATE TEMP TABLE tmp_cards (
        LIKE mtg_cards INCLUDING DEFAULTS,
        orden bigint GENERATED ALWAYS AS IDENTITY
    ) ON COMMIT DROP
"""

# Si una carta llega repetida (p. ej. porque la paginación de Scryfall se desplaza
# mientras actualizan un set), DISTINCT ON se queda con la última copia recibida: siempre
# la misma, para que dos cargas iguales no alternen entre versiones.
# RETURNING old: old es NULL en las filas insertadas y contiene la fila anterior en las
# actualizadas. Las filas sin cambios no se devuelven.
SQL_FUSIONAR_CARTAS: Final = f"""
    WITH filas AS (
        INSERT INTO mtg_cards ({", ".join(COLUMNAS_CARTAS)})
        SELECT DISTINCT ON (id) {", ".join(COLUMNAS_CARTAS)}
        FROM tmp_cards
        ORDER BY id, orden DESC
        {_upsert("mtg_cards", COLUMNAS_CARTAS)}
        RETURNING old.id IS NULL AS insertada
    )
    SELECT count(*) FILTER (WHERE insertada),
           count(*) FILTER (WHERE NOT insertada),
           (SELECT count(*) - count(DISTINCT id) FROM tmp_cards)
    FROM filas
"""


class ResultadoFusion(NamedTuple):
    insertadas: int
    actualizadas: int
    duplicadas: int  # copias repetidas descartadas


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


def sets_guardados(conn: psycopg.Connection) -> set[tuple[UUID, str]]:
    """Pares (id, código) de los sets guardados."""
    return {(id_, codigo) for id_, codigo in conn.execute("SELECT id, code FROM mtg_sets")}


def codigos_ocupados(conn: psycopg.Connection, sets: Iterable[SetScryfall]) -> dict[UUID, UUID]:
    """Sets cuyo código ya está guardado con otro id: {id en Scryfall: id guardado}.

    Pasa si Scryfall recrea un set con otro id y el mismo código. Como el código es
    único, el upsert fallaría y desharía la transacción entera.
    """
    id_por_codigo = {s.code: s.id for s in sets}
    if not id_por_codigo:
        return {}
    filas = conn.execute(
        "SELECT code, id FROM mtg_sets WHERE code = ANY(%s)", [list(id_por_codigo)]
    )
    return {
        id_por_codigo[codigo]: id_guardado
        for codigo, id_guardado in filas
        if id_guardado != id_por_codigo[codigo]
    }


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
        cur.execute(SQL_CREAR_TEMPORAL)
        with cur.copy(f"COPY tmp_cards ({', '.join(COLUMNAS_CARTAS)}) FROM STDIN") as copia:
            for c in cartas:
                copia.write_row((
                    c.id, c.oracle_id, c.set_id, c.collector_number, c.lang, c.name,
                    c.printed_name, c.rarity, c.layout, c.mana_cost, c.type_line,
                    c.released_at, c.imagen_small, c.imagen_small_trasera,
                ))


def fusionar_cartas(conn: psycopg.Connection) -> ResultadoFusion:
    """Pasa tmp_cards a mtg_cards."""
    fila = conn.execute(SQL_FUSIONAR_CARTAS).fetchone()
    assert fila is not None
    return ResultadoFusion(*fila)
