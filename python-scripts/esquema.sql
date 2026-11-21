-- Catálogo de Magic: The Gathering cargado desde Scryfall.
-- Lo ejecuta el ETL en cada arranque: todas las sentencias son idempotentes.
-- Requiere PostgreSQL 18 o superior compilado con ICU (probado en PostgreSQL 19).
--
-- Las columnas usan los nombres de los campos de Scryfall, y created_at/updated_at
-- siguen la convención de Laravel para que un modelo Eloquent funcione sin configurar.
--
-- IF NOT EXISTS no modifica tablas que ya existan: si cambias este fichero, borra las
-- tablas (DROP TABLE mtg_cards, mtg_sets) y deja que el ETL las recree y recargue.

-- Orden natural de los números de colección: 1, 2, 2a, 10, 10a, 100 (con la colación
-- por defecto sería 1, 10, 100, 2). Así el índice por set devuelve las cartas ya en el
-- orden del binder, sin ordenar en cada consulta.
CREATE COLLATION IF NOT EXISTS mtg_numero_coleccion (provider = icu, locale = 'und-u-kn');

-- Búsqueda por trigramas: permite buscar cartas por cualquier trozo del nombre
-- (name ILIKE '%bolt%') y por parecido (tolerante a erratas) usando índice.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Notas de diseño:
-- * Columnas de ancho fijo (uuid, timestamptz, date, integer) primero y texto al final:
--   PostgreSQL alinea cada valor a su tamaño, y este orden evita bytes de relleno.
-- * COLLATE "C" en los códigos (set, idioma, rareza...): son identificadores ASCII, se
--   comparan byte a byte (más rápido) y sus índices no dependen de la versión de glibc
--   del servidor, así que no hay que reindexarlos al actualizar el sistema operativo.

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
    collector_number     text        COLLATE mtg_numero_coleccion NOT NULL,
    lang                 text        COLLATE "C" NOT NULL,
    rarity               text        COLLATE "C" NOT NULL,
    layout               text        COLLATE "C" NOT NULL,
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

-- Búsqueda por nombre en inglés y por nombre impreso (español, japonés...), sin
-- distinguir mayúsculas y por cualquier parte del nombre: ILIKE '%texto%', o similitud
-- con el operador %.
CREATE INDEX IF NOT EXISTS mtg_cards_name_trgm_idx
    ON mtg_cards USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS mtg_cards_printed_name_trgm_idx
    ON mtg_cards USING gin (printed_name gin_trgm_ops)
    WHERE printed_name IS NOT NULL;
