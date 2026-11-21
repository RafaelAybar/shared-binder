"""ETL de cartas de Magic: The Gathering desde Scryfall a PostgreSQL.

Uso (desde python-scripts/):
    python main.py                 # automático: carga inicial si la BD está vacía;
                                   # si no, expansiones nuevas y recientes
    python main.py --completa      # fuerza la carga completa desde el fichero bulk
    python main.py --set fdn --set sld   # carga o refresca expansiones concretas
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import bd
import etl
from config import (
    DIRECTORIO_LOGS,
    FORMATO_FECHA,
    FORMATO_LOG,
    NIVEL_LOG,
    PG_DATABASE,
    PG_HOST,
    PG_USER,
    USER_AGENT,
)
from scryfall import ClienteScryfall

logger = logging.getLogger(__name__)


class DailyUTCFileHandler(logging.FileHandler):
    """Escribe en <dir>/AAAA-MM-DD.log y cambia de fichero al pasar la medianoche UTC."""

    # Atributo heredado de FileHandler (ruta del fichero abierto). Se declara aquí
    # porque esta clase lo reasigna al cambiar de día.
    baseFilename: str

    def __init__(self, log_dir: Path, encoding: str = "utf-8") -> None:
        self.log_dir = Path(log_dir).resolve()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.current_date = self._utc_date()
        super().__init__(
            self._path_for(self.current_date), encoding=encoding, delay=True
        )

    @staticmethod
    def _utc_date() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _path_for(self, date: str) -> str:
        return str(self.log_dir / f"{date}.log")

    def emit(self, record: logging.LogRecord) -> None:
        # emit() se ejecuta con el lock del handler, así que el cambio es seguro entre hilos
        date = datetime.fromtimestamp(record.created, timezone.utc).strftime("%Y-%m-%d")
        if date != self.current_date:
            self.close()
            self.current_date = date
            self.baseFilename = self._path_for(date)
        super().emit(record)


def setup_logging() -> None:
    """Configura el logging con el nivel y el formato definidos en config.py."""
    formatter = logging.Formatter(FORMATO_LOG, datefmt=FORMATO_FECHA)
    formatter.converter = time.gmtime  # marcas de tiempo en UTC

    file_handler = DailyUTCFileHandler(DIRECTORIO_LOGS)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logging.basicConfig(
        level=NIVEL_LOG.logging_level,
        handlers=[file_handler, console_handler],
        force=True,
    )


def parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ETL de cartas de Magic desde Scryfall a PostgreSQL. Sin argumentos, "
        "hace la carga inicial si la base de datos está vacía y, si no, carga las "
        "expansiones nuevas y re-sincroniza las recientes."
    )
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument(
        "--completa",
        action="store_true",
        help="fuerza la carga completa desde el fichero bulk de Scryfall",
    )
    modo.add_argument(
        "--set",
        dest="sets",
        action="append",
        metavar="CÓDIGO",
        help="carga o refresca una expansión concreta (se puede repetir)",
    )
    return parser.parse_args(argv)


def ejecutar(args: argparse.Namespace) -> etl.Resumen:
    cliente = ClienteScryfall()
    with bd.conectar() as conn:
        bd.crear_esquema(conn)
        if args.sets:
            if not bd.hay_sets(conn):
                raise RuntimeError("La base de datos está vacía: ejecuta antes la carga inicial")
            return etl.cargar_sets(conn, cliente, args.sets)
        if args.completa or not bd.hay_sets(conn):
            logger.info("Carga completa desde el fichero bulk")
            return etl.carga_inicial(conn, cliente)
        logger.info("Carga incremental por expansiones")
        return etl.cargar_pendientes(conn, cliente)


def main() -> int:
    args = parsear_argumentos()
    setup_logging()
    logger.info("Inicio (%s): conectando a %s@%s/%s", USER_AGENT, PG_USER, PG_HOST, PG_DATABASE)
    inicio = time.monotonic()
    try:
        resumen = ejecutar(args)
    except Exception:
        logger.exception("La ejecución ha fallado; no se ha guardado la carga en curso")
        return 1
    nivel = logging.INFO if resumen.correcto else logging.ERROR
    logger.log(nivel, "Fin en %.0f s: %s", time.monotonic() - inicio, resumen)
    return 0 if resumen.correcto else 1


if __name__ == "__main__":
    sys.exit(main())
