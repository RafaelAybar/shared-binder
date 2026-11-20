import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from config import (
    DIRECTORIO_LOGS,
    FORMATO_FECHA,
    FORMATO_LOG,
    NIVEL_LOG,
    PG_DATABASE,
    PG_HOST,
    PG_PASSWORD,
    PG_USER,
)

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
        super().__init__(self._path_for(self.current_date), encoding=encoding, delay=True)

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


def main() -> None:
    setup_logging()
    logger.info("Inicio: conectando a %s@%s/%s", PG_USER, PG_HOST, PG_DATABASE)
    logger.debug("Detalle de depuración")
    logger.warning("Ejemplo de aviso")
    logger.error("Ejemplo de error")
    # ... lógica principal ...
    logger.info("Fin")


if __name__ == "__main__":
    main()