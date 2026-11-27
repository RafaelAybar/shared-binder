-- Catálogo de Magic: The Gathering cargado desde Scryfall.
-- Lo ejecutan el ETL en cada arranque y, cuando exista, la migración de Laravel que crea
-- las tablas de los jugadores. Por eso todas las sentencias son idempotentes, y el fichero
-- se ejecuta siempre dentro de una transacción (ver el bloqueo de abajo).
-- Requiere PostgreSQL 19 o superior compilado con ICU.
--
-- Las columnas usan los nombres de los campos de Scryfall, y created_at/updated_at
-- siguen la convención de Laravel para que un modelo Eloquent funcione sin configurar.
--
-- IF NOT EXISTS no modifica tablas que ya existan. Si falta alguna columna que carga el
-- ETL, se detiene al arrancar y dice cuál. Cómo aplicar el cambio depende de si ya hay
-- tablas de jugadores que apuntan al catálogo: ver «Tablas» en docs/procesos/ingesta.md.
-- Nunca uses DROP TABLE ... CASCADE: borraría en silencio sus claves ajenas.

-- Impide que dos procesos (el ETL y la migración de Laravel) apliquen el fichero a la vez:
-- IF NOT EXISTS y el bloque DO del tipo no evitan que dos CREATE simultáneos choquen. El
-- bloqueo se libera al terminar la transacción. El número es cualquiera, pero fijo.
SELECT pg_advisory_xact_lock(5317420001);

-- Orden natural de los números de colección: 1, 2, 2a, 10, 10a, 100 (con la colación
-- por defecto sería 1, 10, 100, 2). Así el índice por set devuelve las cartas ya en el
-- orden del binder, sin ordenar en cada consulta.
CREATE COLLATION IF NOT EXISTS mtg_numero_coleccion (provider = icu, locale = 'und-u-kn');

-- Búsqueda por trigramas: permite buscar cartas por cualquier trozo del nombre
-- (name ILIKE '%bolt%') y por parecido (tolerante a erratas) usando índice.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Acabados en que existe una impresión, con los valores del campo finishes de Scryfall.
-- Las tablas de Laravel lo usan también para el acabado de cada copia de un jugador.
-- El bloque DO crea el tipo solo si no existe, así que cambiar la lista no afecta a las
-- bases de datos que ya lo tienen. Para añadir un valor, deja la lista como está y añade
-- debajo una línea ALTER TYPE mtg_finish ADD VALUE IF NOT EXISTS '...'; sirve para las
-- bases de datos nuevas y para las existentes. Añádelo también al final de ACABADOS
-- (modelos.py).
DO $$
BEGIN
    CREATE TYPE mtg_finish AS ENUM ('nonfoil', 'foil', 'etched');
EXCEPTION WHEN duplicate_object THEN NULL;
END
$$;

-- Notas de diseño:
-- * Columnas de ancho fijo (uuid, timestamptz, date, integer) primero y texto al final:
--   PostgreSQL alinea cada valor a su tamaño, y este orden evita bytes de relleno.
-- * COLLATE "C" en los códigos (set, idioma, rareza...): son identificadores ASCII, se
--   comparan byte a byte (más rápido) y sus índices no dependen de la versión de glibc
--   del servidor, así que no hay que reindexarlos al actualizar el sistema operativo.
-- * Las tablas guardan cada dato tal como lo da Scryfall y no se normalizan: finishes es una
--   lista, y name, mana_cost y type_line dependen de oracle_id. Solo las escribe el ETL.
--   Ver «Formas normales» en docs/base-de-datos/diagrama-entidad-relacion.md.

CREATE TABLE IF NOT EXISTS mtg_sets (
    id              uuid        PRIMARY KEY,  -- id del set en Scryfall
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    released_at     date        NOT NULL,
    card_count      integer     NOT NULL,
    code            text        COLLATE "C" NOT NULL UNIQUE,
    set_type        text        COLLATE "C" NOT NULL,
    parent_set_code text        COLLATE "C",
    name            text        NOT NULL,
    icon_svg_uri    text
);

CREATE TABLE IF NOT EXISTS mtg_cards (
    id                   uuid        PRIMARY KEY,  -- id de Scryfall: una impresión en un idioma
    oracle_id            uuid,                     -- nulo en las cartas reversibles
    set_id               uuid        NOT NULL REFERENCES mtg_sets (id),
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    released_at          date        NOT NULL,
    cmc                  numeric,                  -- valor de maná; decimal en algunas cartas Un-
    collector_number     text        COLLATE mtg_numero_coleccion NOT NULL,
    lang                 text        COLLATE "C" NOT NULL,
    rarity               text        COLLATE "C" NOT NULL,
    layout               text        COLLATE "C" NOT NULL,
    finishes             mtg_finish[] NOT NULL CHECK (cardinality(finishes) > 0),  -- acabados en que existe
    name                 text        NOT NULL,     -- nombre en inglés (Oracle)
    printed_name         text,                     -- nombre impreso, en cartas no inglesas
    mana_cost            text,
    type_line            text,
    image_small_url      text,                     -- cara frontal (o única)
    image_small_back_url text                      -- cara trasera, solo cartas de dos caras
);

-- Un set en un idioma, en orden de colección: WHERE set_id = ? AND lang = ?
-- ORDER BY collector_number. También sirve para localizar una impresión concreta
-- (set + número + idioma) y, con el skip scan de PostgreSQL 18+, para listar un set en
-- todos los idiomas. Cubre además la clave ajena set_id.
CREATE INDEX IF NOT EXISTS mtg_cards_set_lang_number_idx
    ON mtg_cards (set_id, lang, collector_number);

-- Todas las impresiones de una misma carta (mismo texto Oracle).
CREATE INDEX IF NOT EXISTS mtg_cards_oracle_id_idx ON mtg_cards (oracle_id);

-- Catálogo de la web (/cards): las cartas de un idioma por orden alfabético,
-- WHERE lang = ? ORDER BY name, id LIMIT 50. Sin él, cada página y su COUNT(*) leen la tabla
-- entera. id desempata las cartas con el mismo nombre, para que las páginas no se solapen.
CREATE INDEX IF NOT EXISTS mtg_cards_lang_name_id_idx
    ON mtg_cards (lang, name, id);

-- Búsqueda por nombre en inglés y por nombre impreso (español, japonés...), sin
-- distinguir mayúsculas y por cualquier parte del nombre: ILIKE '%texto%', o similitud
-- con el operador %.
CREATE INDEX IF NOT EXISTS mtg_cards_name_trgm_idx
    ON mtg_cards USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS mtg_cards_printed_name_trgm_idx
    ON mtg_cards USING gin (printed_name gin_trgm_ops)
    WHERE printed_name IS NOT NULL;
