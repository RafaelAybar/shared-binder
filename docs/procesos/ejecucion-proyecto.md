# Manual de arranque y parada

Cómo poner en marcha y detener Shared-Binder en un equipo de desarrollo. Los comandos se
ejecutan desde la raíz del repositorio salvo que se indique otra carpeta. La aplicación web
y el ETL ocupan cada uno su propia terminal.

## Resumen

| Componente | Arranque | Parada |
| --- | --- | --- |
| 1. Base de datos | `docker compose --profile db up -d` | `docker compose --profile db stop` |
| 2. Aplicación web | `cd shared-binder && composer dev` | `q` o `Ctrl+C` en esa terminal |

Se arranca en ese orden y se para en el inverso: primero la aplicación web y después la base
de datos. El ETL se lanza solo cuando hay que cargar datos y termina por sí mismo.

## Componentes

| Componente | Qué es | Cómo se ejecuta | Dirección |
| --- | --- | --- | --- |
| Base de datos | PostgreSQL 19 en Docker (contenedor `databases`) | `docker compose --profile db` | `127.0.0.1:5432` |
| Aplicación web | Laravel 13 + Inertia + Svelte | `composer dev` en `shared-binder/` | `http://localhost:8000` |
| ETL de cartas | Script de Python que carga los datos de Scryfall | `python main.py` en `python-scripts/` | Se ejecuta y termina |

La aplicación web y el ETL necesitan la base de datos en marcha.

> El servicio `web-server` (nginx, perfil `full`) todavía no sirve la aplicación:
> `nginx-config/site.conf` está vacío y no se monta en el contenedor. No forma parte de este
> procedimiento.

## Requisitos

| Herramienta | Versión | Notas |
| --- | --- | --- |
| Docker con Compose | Compose v2 o superior | |
| PHP | 8.5 o superior | Con la extensión `pdo_pgsql`. Con `pcntl`, `composer dev` muestra también los logs en vivo |
| Composer | 2 | |
| Node | 26 | Fijado en `mise.toml`: `mise install` |
| Python | 3.14 o superior | Solo para el ETL, que además necesita acceso a internet |

## Primera puesta en marcha

Solo hace falta la primera vez, o después de vaciar la base de datos.

1. Arranca la base de datos (ver [Arrancar la base de datos](#arrancar-la-base-de-datos)).

2. Crea el `.env` de Laravel:

   ```bash
   cd shared-binder
   cp .env.example .env
   ```

   `DB_DATABASE` y `DB_USERNAME` ya coinciden con `env-files-examples/postgres-backend-example.env`.
   Copia en `DB_PASSWORD` el valor de `POSTGRES_PASSWORD` de ese fichero, entre comillas
   simples si contiene espacios, `#` o `$`.

3. Instala las dependencias, genera la clave, crea las tablas y compila el frontend:

   ```bash
   composer setup
   ```

   Ejecuta `composer install`, `php artisan key:generate`, `php artisan migrate --force`,
   `npm install --ignore-scripts` y `npm run build`. No lo uses para el arranque diario:
   `key:generate` sustituye `APP_KEY` cada vez, lo que invalida las sesiones y los datos
   cifrados.

4. Prepara el entorno de Python del ETL (en la raíz del repositorio):

   ```bash
   python3.14 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

5. Haz la carga inicial de cartas (ver [Lanzar el ETL](#lanzar-el-etl)). Descarga unos
   400 MB y tarda un rato.

## Arranque

### Arrancar la base de datos

```bash
docker compose --profile db up -d
```

Todos los servicios de `docker-compose.yaml` tienen perfil, así que `docker compose up` sin
`--profile` no arranca nada. Hoy los perfiles `db` y `backend` arrancan lo mismo (solo
PostgreSQL); `full` añade nginx en el puerto 80.

Comprueba que acepta conexiones:

```bash
docker exec databases pg_isready
# /var/run/postgresql:5432 - accepting connections
```

En el primer arranque PostgreSQL tarda unos segundos en crear la base de datos. Si responde
`no response`, espera y repite.

### Arrancar la aplicación web

```bash
cd shared-binder
composer dev
```

`composer dev` lanza `php artisan dev`, que abre en la terminal un panel con una pestaña por
proceso:

| Pestaña | Comando | Función |
| --- | --- | --- |
| `server` | `php artisan serve` | Servidor PHP en `http://localhost:8000` |
| `queue` | `php artisan queue:listen --tries=1 --timeout=0` | Procesa la cola de trabajos (`QUEUE_CONNECTION=database`) |
| `logs` | `php artisan pail --timeout=0` | Logs de Laravel en vivo (solo si PHP tiene `pcntl`) |
| `vite` | `npm run dev` | Servidor de Vite con recarga en caliente |

Teclas útiles: `1`–`9` cambian de pestaña, `r` reinicia el proceso seleccionado, `s` muestra
toda la salida en un único flujo y `/` busca en ella. Si un proceso se cae, se reinicia solo.
Para ver la salida como texto normal, sin panel (por ejemplo, para copiarla), usa
`php artisan dev --inline`.

Comprueba que responde:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/up
# 200
```

`/up` solo comprueba que Laravel arranca. Para comprobar la conexión con la base de datos,
ejecuta `php artisan db:show` en `shared-binder/`.

Si el puerto 8000 está ocupado, `php artisan serve` usa el siguiente libre (8001, 8002…).
La URL real aparece en la pestaña `server`.

### Lanzar el ETL

Solo cuando haya que cargar o actualizar cartas. No forma parte del arranque de la
aplicación: se ejecuta, termina y devuelve el código 0 (todo bien) o 1 (hubo errores).

El ETL no lee el `.env` de Laravel; necesita las variables `PG_*` en el entorno:

```bash
source venv/bin/activate
export PG_HOST=127.0.0.1 PG_PORT=5432 PG_DATABASE=app-datahase PG_USER=test-user
export PG_PASSWORD='<valor de POSTGRES_PASSWORD>'
cd python-scripts
python main.py
```

Pon `PG_PASSWORD` entre comillas simples para que la terminal no interprete caracteres como
`!` o `$`.

Los modos de ejecución (`--completa`, `--set`), los logs y el resto de variables están en la
[documentación de la ingesta](ingesta.md).

## Parada

### Parar el ETL

Termina solo. Para abortarlo, pulsa `Ctrl+C` en su terminal: Python muestra un
`KeyboardInterrupt` (es lo esperado) y el log se queda sin el resumen final.

Qué se conserva al abortar:

- **Carga inicial** (`--completa`, o base de datos vacía): nada, porque va en una única
  transacción. Si el fichero bulk se había descargado entero, la siguiente ejecución lo
  reutiliza. Si se cortó durante la descarga, queda un fichero `.part` en
  `python-scripts/descargas/` que se puede borrar; la descarga vuelve a empezar de cero.
- **Carga por expansión** (modo automático o `--set`): las expansiones ya terminadas, porque
  cada una va en su propia transacción. La que estaba en curso se deshace; vuelve a lanzar el
  mismo comando para completarla.

### Parar la aplicación web

En la terminal de `composer dev`, pulsa `q` o `Ctrl+C`. Todos los procesos reciben `SIGTERM`
y tienen dos segundos para cerrarse (Vite borra entonces `public/hot`); pasado ese tiempo se
matan. Un segundo `Ctrl+C` los mata sin esperar. Cerrar la ventana de la terminal también los
detiene.

Comprueba que no queda nada escuchando:

```bash
lsof -nP -iTCP:8000 -iTCP:5173 -sTCP:LISTEN
```

Si aparece algún proceso, termínalo con `kill <PID>`.

### Parar la base de datos

Para el día a día, para el contenedor sin eliminarlo:

```bash
docker compose --profile db stop
```

Se vuelve a arrancar con el mismo `docker compose --profile db up -d`. Usa siempre el mismo
`--profile` que al arrancar: sin él, Compose no ve el servicio.

| Comando | Contenedor | Datos |
| --- | --- | --- |
| `docker compose --profile db stop` | Se para y se conserva | Se conservan |
| `docker compose --profile db down` | Se elimina | Se conservan en el volumen `postgres_data` |
| `docker compose --profile db down -v` | Se elimina | Se borra el volumen: la base de datos queda vacía |

Los datos están en el volumen `postgres_data`, montado en `/var/lib/postgresql`. La imagen
guarda cada versión mayor en su propia carpeta (`19/docker`, que es `PGDATA`), así que al pasar a
`postgres:20` las dos versiones estarán en el mismo volumen, que es lo que necesita
`pg_upgrade`.

Si se cierra Docker o se reinicia el equipo, el contenedor se para pero no se elimina, y los
datos se conservan. El servicio no tiene política de reinicio: hay que volver a arrancarlo a
mano.

## Problemas frecuentes

| Síntoma | Causa | Solución |
| --- | --- | --- |
| `docker compose up -d` no arranca ningún contenedor | Falta `--profile` | `docker compose --profile db up -d` |
| `port is already allocated` en el puerto 5432 | Hay otro PostgreSQL local (Homebrew, Postgres.app…) | Páralo, o cambia el puerto publicado en `docker-compose.yaml` y `DB_PORT` en el `.env` |
| `Connection refused` al migrar o al abrir la web | PostgreSQL parado o todavía iniciándose | Arráncalo y espera a que `pg_isready` responda `accepting connections` |
| `password authentication failed for user "test-user"` | `DB_PASSWORD` no coincide con `POSTGRES_PASSWORD` | Copia el valor. Cambiar `POSTGRES_PASSWORD` después del primer arranque no cambia la contraseña: solo se aplica al crear la base de datos |
| Página en blanco y errores al cargar recursos de `localhost:5173` | Quedó `public/hot` de un Vite cerrado a la fuerza | `rm shared-binder/public/hot`, o arranca `composer dev` |
| `Vite manifest not found` | Ni Vite está en marcha ni el frontend está compilado | `composer dev`, o `npm run build` en `shared-binder/` |
| La base de datos está vacía al arrancar | Se paró con `down -v`, o el contenedor se creó con el montaje antiguo (`/var/lib/postgresql/19/data`), que dejaba los datos en un volumen anónimo | `docker compose --profile db down` y `up -d` para usar el montaje actual, y después `php artisan migrate` y la carga inicial del ETL |
| ETL: `Falta la variable de entorno obligatoria PG_…` | Las variables no están exportadas en esa terminal | Exporta las variables `PG_*` |
| ETL: `CERTIFICATE_VERIFY_FAILED` | Python de python.org en macOS | Ver la nota de macOS en la [documentación de la ingesta](ingesta.md) |
