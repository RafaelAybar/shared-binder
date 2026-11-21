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

Pydantic 2.14.3 o superior

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
  después de la salida. Cada expansión va en su propia transacción.
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

### Imágenes

Solo se guarda la URL de la imagen en tamaño *small* (146×204) servida por Scryfall:
`image_small_url` (cara frontal o única) e `image_small_back_url` (cara trasera de las
cartas de dos caras). No se descarga ninguna imagen.

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

### Variables de entorno

| Variable | Obligatoria | Por defecto | Uso |
| --- | --- | --- | --- |
| `PG_USER`, `PG_PASSWORD`, `PG_HOST`, `PG_DATABASE` | Sí | — | Conexión a PostgreSQL |
| `PG_PORT` | No | `5432` | Puerto de PostgreSQL |
| `LOG_LEVEL` | No | `info` | `debug` muestra cada petición HTTP |
| `LOG_DIR` | No | `python-scripts/logs` | Logs diarios en UTC |
| `DOWNLOAD_DIR` | No | `python-scripts/descargas` | Descarga temporal del bulk |
| `RESYNC_DAYS` | No | `30` | Días de re-sincronización de expansiones recientes |
