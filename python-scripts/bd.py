"""Acceso a PostgreSQL: esquema, consultas y volcado de sets y cartas."""

from collections.abc import Iterable
from pathlib import Path
from typing import Final, NamedTuple
from uuid import UUID

import psycopg

from config import PG_DATABASE, PG_HOST, PG_PASSWORD, PG_PORT, PG_USER
from modelos import ACABADOS, CartaScryfall, SetScryfall

FICHERO_ESQUEMA: Final = Path(__file__).resolve().parent / "esquema.sql"

# Columnas que existen en la tabla (to_regclass sigue el search_path, como las consultas).
SQL_COLUMNAS_TABLA: Final = """
    SELECT attname FROM pg_attribute
    WHERE attrelid = to_regclass(%s) AND attnum > 0 AND NOT attisdropped
"""

# Valores del tipo mtg_finish. Se leen de pg_enum y no con enum_range(): un valor añadido
# con ALTER TYPE en la misma transacción todavía no se puede usar, y enum_range() fallaría.
SQL_VALORES_ACABADO: Final = """
    SELECT enumlabel FROM pg_enum
    WHERE enumtypid = to_regtype('mtg_finish')
    ORDER BY enumsortorder
"""

AYUDA_ESQUEMA: Final = "ver «Tablas» en docs/procesos/ingesta.md"

COLUMNAS_SETS: Final = (
    "id",
    "code",
    "name",
    "set_type",
    "released_at",
    "card_count",
    "parent_set_code",
    "icon_svg_uri",
)
COLUMNAS_CARTAS: Final = (
    "id",
    "oracle_id",
    "set_id",
    "collector_number",
    "lang",
    "name",
    "printed_name",
    "rarity",
    "layout",
    "finishes",
    "mana_cost",
    "cmc",
    "type_line",
    "released_at",
    "image_small_url",
    "image_small_back_url",
)


def _upsert(tabla: str, columnas: tuple[str, ...]) -> str:
    """Parte común de los upsert: ON CONFLICT (id) que solo toca las filas que cambian,
    para que updated_at refleje cambios reales. Las columnas son constantes del módulo.
    """
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


class EsquemaAntiguo(RuntimeError):
    """A la base de datos le falta algo que carga el ETL: columnas de una tabla creada con
    una versión anterior de esquema.sql, o valores del tipo mtg_finish."""


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
    """Aplica esquema.sql y comprueba que la base de datos admite todo lo que carga el ETL.

    CREATE TABLE IF NOT EXISTS no añade columnas a una tabla que ya existe, y un valor de
    ACABADOS que falte en el tipo mtg_finish haría fallar el COPY. Sin estas comprobaciones,
    las cargas fallarían una tras otra con errores menos claros.
    """
    with conn.transaction():  # esquema.sql toma un bloqueo que dura hasta el final
        conn.execute(FICHERO_ESQUEMA.read_text(encoding="utf-8"))
        for tabla, columnas in (
            ("mtg_sets", COLUMNAS_SETS),
            ("mtg_cards", COLUMNAS_CARTAS),
        ):
            existentes = {
                nombre for (nombre,) in conn.execute(SQL_COLUMNAS_TABLA, [tabla])
            }
            if faltan := [c for c in columnas if c not in existentes]:
                raise EsquemaAntiguo(
                    f"A la tabla {tabla} le faltan las columnas {', '.join(faltan)}: se creó con "
                    f"una versión anterior de esquema.sql. Para añadirlas, {AYUDA_ESQUEMA}. No "
                    "uses DROP TABLE ... CASCADE: borraría las claves ajenas de las tablas de "
                    "los jugadores"
                )
        en_el_tipo = {valor for (valor,) in conn.execute(SQL_VALORES_ACABADO)}
        if faltan := [a for a in ACABADOS if a not in en_el_tipo]:
            raise EsquemaAntiguo(
                f"Al tipo mtg_finish le faltan los acabados {', '.join(faltan)}, que ACABADOS "
                "(modelos.py) sí admite. Añade a esquema.sql la línea ALTER TYPE mtg_finish "
                "ADD VALUE IF NOT EXISTS de cada uno: ver «Acabados» en docs/procesos/ingesta.md"
            )


def hay_sets(conn: psycopg.Connection) -> bool:
    fila = conn.execute("SELECT EXISTS (SELECT 1 FROM mtg_sets)").fetchone()
    return bool(fila and fila[0])


def sets_guardados(conn: psycopg.Connection) -> set[tuple[UUID, str]]:
    """Pares (id, código) de los sets guardados."""
    return {
        (id_, codigo) for id_, codigo in conn.execute("SELECT id, code FROM mtg_sets")
    }


def codigos_ocupados(
    conn: psycopg.Connection, sets: Iterable[SetScryfall]
) -> dict[UUID, UUID]:
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
        (
            s.id,
            s.code,
            s.name,
            s.set_type,
            s.released_at,
            s.card_count,
            s.parent_set_code,
            str(s.icon_svg_uri) if s.icon_svg_uri else None,
        )
        for s in sets
    ]
    if filas:
        with conn.cursor() as cur:
            cur.executemany(SQL_UPSERT_SETS, filas)


def copiar_a_temporal(
    conn: psycopg.Connection, cartas: Iterable[CartaScryfall]
) -> None:
    """Vuelca las cartas con COPY a la tabla temporal tmp_cards.

    Debe llamarse dentro de conn.transaction(): la tabla se borra al terminar la
    transacción. Después hay que llamar a fusionar_cartas.
    """
    with conn.cursor() as cur:
        cur.execute(SQL_CREAR_TEMPORAL)
        with cur.copy(
            f"COPY tmp_cards ({', '.join(COLUMNAS_CARTAS)}) FROM STDIN"
        ) as copia:
            for c in cartas:
                copia.write_row(
                    (
                        c.id,
                        c.oracle_id,
                        c.set_id,
                        c.collector_number,
                        c.lang,
                        c.name,
                        c.nombre_impreso,
                        c.rarity,
                        c.layout,
                        c.finishes,
                        c.coste_mana,
                        c.valor_mana,
                        c.linea_tipo,
                        c.released_at,
                        c.imagen_small,
                        c.imagen_small_trasera,
                    )
                )


def fusionar_cartas(conn: psycopg.Connection) -> ResultadoFusion:
    """Pasa tmp_cards a mtg_cards."""
    fila = conn.execute(SQL_FUSIONAR_CARTAS).fetchone()
    assert fila is not None
    return ResultadoFusion(*fila)
