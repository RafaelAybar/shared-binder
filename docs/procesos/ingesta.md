# Proceso de carga de datos en el servidor

## Diagrama simplifado

```mermaid
flowchart TD
inicio(Ejecución del script  de Ingesta)
inicio --> |Descarga y valida datos de | ScryFall[Scryfall]
inicio --> |Descarga y valida datos de | tcgcsv[tcgcsv]
ScryFall --> DatosValidos{¿Los datos son correctos?}
tcgcsv --> DatosValidos
DatosValidos -->si(Sí)
DatosValidos -->no(No)
no --> error(Genera error con logs en el servidor)
si --> |Guarda datos en| db[PostgreSQL]
```

## Requerimientos

### Lenguaje de programación

Python 3.14 o superior.

### Librerías

Pydantic 2.14.3 o superior.
Pytest 9.2.0 o superior.

## Ingesta de Magic: The Gathering (Scryfall)

El código está en `python-scripts/` y se ejecuta desde esa carpeta:

```bash
python main.py                      # modo automático
python main.py --completa           # fuerza la carga completa desde el fichero bulk
python main.py --set fdn --set sld  # carga o refresca expansiones concretas
```

### Modos de ejecución

- **Carga inicial** (automática si `mtg_sets` está vacía, o con `--completa`). Descarga el
  fichero bulk `all_cards` (todas las impresiones en todos los idiomas, ~400 MB en formato
  JSON Lines comprimido), lo procesa línea a línea y lo guarda en una única transacción. Si
  falla, no se guarda nada y la siguiente ejecución lo reintenta reutilizando el fichero ya
  descargado. Si termina bien, el fichero se borra.
- **Carga por expansión** (automática en las ejecuciones siguientes). Nunca vuelve a
  descargar el bulk: consulta la lista de sets y carga, con la búsqueda de Scryfall, las
  expansiones oficiales que aún no están en la base de datos. También re-sincroniza las
  publicadas en los últimos `RESYNC_DAYS` días, porque Scryfall añade idiomas y promos
  después de la salida. Cada expansión va en su propia transacción. Las impresiones de las
  demás expansiones no se tocan: si Scryfall corrige el texto Oracle de una carta (`name`,
  `mana_cost`, `cmc`, `type_line`), sus impresiones de otras expansiones lo reciben cuando se
  vuelven a cargar con `--set` o `--completa` (ver
  [El catálogo de Magic no se normaliza](../base-de-datos/diagrama-entidad-relacion.md#el-catálogo-de-magic-no-se-normaliza)).
- **`--set CÓDIGO`**: carga o refresca expansiones concretas, por ejemplo las que reciben
  cartas durante mucho tiempo (Secret Lair, `sld`). Requiere haber hecho la carga inicial.

### Qué se considera publicación oficial

- **Set**: no es solo digital (`digital = false`) y su fecha de salida ya ha pasado. Se
  incluyen todos los tipos en papel: expansiones, Commander, promos, tokens, etc.
- **Carta**: pertenece a un set oficial, no es digital y su fecha de salida ya ha pasado
  (no se guardan cartas en preview).

Las cartas descartadas por no ser oficiales se cuentan en el resumen final del log.

### Validación y errores

Cada registro se valida con Pydantic. Un registro inválido se escribe en el log con nivel
ERROR y se descarta sin detener la carga. Al final se registra un resumen y el script
termina con código 1 si hubo registros inválidos o expansiones que no se pudieron cargar
(0 si todo fue bien).

Otros casos que no detienen la carga:

- **Carta repetida** (mismo `id` dos veces en el mismo lote, por ejemplo si la paginación
  de Scryfall se desplaza durante la descarga): se guarda la última copia recibida y se
  avisa con nivel WARNING. No cuenta como error.
- **Código de set ocupado** (Scryfall recrea un set con otro `id` pero el mismo código, que
  es único en `mtg_sets`): el set y sus cartas se omiten con nivel ERROR y el resto se carga
  con normalidad. El modo automático lo vuelve a intentar en cada ejecución hasta que se
  resuelva a mano: borra el set que sobra (y sus cartas) y vuelve a cargarlo con
  `--set CÓDIGO`.

### Imágenes

Solo se guarda la URL de la imagen en tamaño *small* (146×204) servida por Scryfall:
`image_small_url` (cara frontal o única) e `image_small_back_url` (cara trasera de las
cartas de dos caras). No se descarga ninguna imagen.

### Cartas con varias caras

Scryfall da algunos datos solo en cada cara (`card_faces`) y no en la raíz de la carta. Si
faltan en la raíz, el ETL los toma de las caras:

- `mana_cost`, en las cartas de dos caras físicas (`transform`, `modal_dfc`...). Se guardan
  los costes de las caras unidos con « // », como hace Scryfall en las cartas divididas, sin
  las caras que no tienen coste: Delver of Secrets // Insectile Aberration guarda `{U}`.
- `printed_name`, en las impresiones no inglesas de cualquier carta con varias caras,
  también las divididas y las de aventura. Se unen igual: `Fuego // Hielo`.
- `type_line` y `cmc`, en las cartas reversibles (`reversible_card`). `type_line` se une
  igual, y `cmc` es el de la cara frontal.

### Acabados

`mtg_cards.finishes` guarda el campo `finishes` de Scryfall: los acabados en que existe la
impresión, entre `nonfoil`, `foil` y `etched` (tipo `mtg_finish[]`). Scryfall usa el mismo
`id` para todos los acabados de una impresión, así que la aplicación lo necesita para saber
si una copia puede ser foil.

Se guardan sin repetidos y siempre en el mismo orden, para que la misma lista en otro orden no
cuente como un cambio de la carta.

Una carta que se va a guardar y no tiene acabados, o tiene uno fuera de esa lista, se descarta
con nivel ERROR. En las cartas que se descartan de todas formas (digitales, en preview o de
sets no oficiales) no se comprueban, así que un acabado nuevo que solo tengan esas cartas no
es un error. Para admitir un acabado nuevo:

1. Añádelo al final de `ACABADOS`, en `modelos.py`.
2. Añade en `esquema.sql`, debajo del tipo, la línea
   `ALTER TYPE mtg_finish ADD VALUE IF NOT EXISTS '…';`. Lo añade tanto en las bases de datos
   nuevas como en las que ya existen. Si falta esta línea, el ETL se detiene al arrancar y lo
   indica.
3. Vuelve a cargar las expansiones afectadas con `--set CÓDIGO`, o todas con `--completa`.

### Política de uso de Scryfall

Todas las peticiones envían `User-Agent: SharedBinder-ETL/<versión>` y
`Accept: application/json;q=0.9,*/*;q=0.8`, tal como exige Scryfall. Entre peticiones hay
una pausa de 1 s, y los errores temporales (429, 5xx, red) se reintentan hasta 3 veces
respetando la cabecera `Retry-After`.

> **macOS**: el Python de python.org no usa los certificados del sistema. Si aparece
> `CERTIFICATE_VERIFY_FAILED`, ejecuta `Install Certificates.command` (en la carpeta de
> Python de Aplicaciones) o exporta `SSL_CERT_FILE=/etc/ssl/cert.pem`.

### Tablas

El ETL crea las tablas al arrancar si no existen (`python-scripts/esquema.sql`):

- `mtg_sets`: expansiones oficiales cargadas.
- `mtg_cards`: una fila por impresión e idioma (`id` de Scryfall), con clave ajena a `mtg_sets`.

Crea también el tipo `mtg_finish`, que usan `mtg_cards` y las tablas de los jugadores.

Si una tabla ya existe pero le faltan columnas, porque se creó con una versión anterior de
`esquema.sql`, el ETL se detiene al arrancar con un error que dice cuáles. Cómo actualizarla
depende de si ya hay tablas de los jugadores que apuntan al catálogo (`mtg_cartas_carpeta`,
`mtg_cartas_mazo` o `mtg_cartas_prestamo`):

- **Si no las hay**: borra las tablas (`DROP TABLE mtg_cards, mtg_sets`) y vuelve a ejecutar
  el ETL, que las recreará y hará la carga inicial.
- **Si las hay**: sus claves ajenas impiden borrarlas. Añade cada columna con
  `ALTER TABLE … ADD COLUMN`, sin `NOT NULL`, y rellénala con `python main.py --completa`.
  Después, añade con `ALTER TABLE` el `NOT NULL` y los `CHECK` que tenga en `esquema.sql`.

Nunca uses `DROP TABLE … CASCADE`: borraría en silencio las claves ajenas de las tablas de los
jugadores.

El ETL también se detiene al arrancar si `ACABADOS` tiene un valor que falta en el tipo
`mtg_finish` (ver [Acabados](#acabados)).

### Variables de entorno

| Variable | Obligatoria | Por defecto | Uso |
| --- | --- | --- | --- |
| `PG_USER`, `PG_PASSWORD`, `PG_HOST`, `PG_DATABASE` | Sí | — | Conexión a PostgreSQL |
| `PG_PORT` | No | `5432` | Puerto de PostgreSQL |
| `LOG_LEVEL` | No | `info` | `debug` muestra cada petición HTTP |
| `LOG_DIR` | No | `python-scripts/logs` | Logs diarios en UTC |
| `DOWNLOAD_DIR` | No | `python-scripts/descargas` | Descarga temporal del bulk |
| `RESYNC_DAYS` | No | `30` | Días de re-sincronización de expansiones recientes |

### Tests

Los tests están en `python-scripts/tests/` y usan pytest (`dev-requirements.txt`):

```bash
pip install -r dev-requirements.txt
cd python-scripts && pytest
```

- **Unitarios** (`test_ingesta.py`, `test_modelos.py`, `test_scryfall.py`): no se conectan
  a Scryfall ni a PostgreSQL, y tardan menos de un segundo. Cada caso parte de las tres
  cartas de ejemplo de `tests/ejemplos.py` (una normal, una de dos caras y una en español):
  errores de formato, líneas dañadas del bulk, cartas y sets no oficiales, cartas
  repetidas, códigos de set ocupados, errores aislados por expansión, cabeceras
  obligatorias de Scryfall, reintentos y descarga del bulk.
- **Base de datos** (`test_bd.py`): comprueban lo que resuelve PostgreSQL. Por ejemplo, qué
  copia se guarda de una carta repetida, que las filas sin cambios no se tocan y que un
  error deshace la carga. Se omiten salvo que se defina `TEST_DATABASE_URL`, que debe
  apuntar a un PostgreSQL 19 o superior. Cada test trabaja en un esquema propio que borra
  al terminar, así que no toca las tablas del esquema `public`:

  ```bash
  TEST_DATABASE_URL=postgresql://usuario:clave@127.0.0.1:5432/basedatos pytest
  ```
