import logging
from enum import StrEnum
from os import getenv
from pathlib import Path
from typing import Final


def _required(name: str) -> str:
    """Lee una variable de entorno obligatoria; si falta, para el script con un error claro."""
    value = getenv(name)
    if not value:
        raise RuntimeError(f"Falta la variable de entorno obligatoria {name}")
    return value


# Conexión a DB
PG_USER: Final = _required("PG_USER")
PG_PASSWORD: Final = _required("PG_PASSWORD")
PG_HOST: Final = _required("PG_HOST")
PG_DATABASE: Final = _required("PG_DATABASE")
PG_PORT: Final = int(getenv("PG_PORT", "5432"))


# Gestión de logs
class LogLevel(StrEnum):
    """Únicos niveles de log permitidos."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

    @classmethod
    def parse(cls, value: str) -> "LogLevel":
        """Convierte 'info', 'INFO', ' Warning '... en un LogLevel; si no es válido, da un error claro."""
        members = cls.__members__
        member = members.get(value.strip().upper())
        if member is None:
            valid = ", ".join(m.value for m in members.values())
            raise ValueError(f"Nivel de log no válido: {value!r}. Usa: {valid}")
        return member

    @property
    def logging_level(self) -> int:
        """Valor necesario para el módulo logging (logging.INFO, etc.)."""
        return getattr(logging, self.name)


# Python no tiene constantes como PHP: Final indica al IDE y al linter que estos
# valores no deben reasignarse (en ejecución no se impide).
NIVEL_LOG: Final = LogLevel.parse(getenv("LOG_LEVEL", "info"))
FORMATO_LOG: Final = "%(asctime)s.%(msecs)03dZ %(levelname)-8s %(name)s: %(message)s"
FORMATO_FECHA: Final = "%Y-%m-%dT%H:%M:%S"

DIRECTORIO_LOGS: Final = Path(getenv("LOG_DIR", Path(__file__).resolve().parent / "logs"))

# Scryfall (https://scryfall.com/docs/api)
VERSION_ETL: Final = "0.1.0"
# Scryfall exige en todas las peticiones un User-Agent que identifique la aplicación
# (nunca el que pone por defecto la librería HTTP) y una cabecera Accept.
USER_AGENT: Final = f"SharedBinder-ETL/{VERSION_ETL}"
ACCEPT: Final = "application/json;q=0.9,*/*;q=0.8"
SCRYFALL_API_URL: Final = "https://api.scryfall.com"
# Segundos mínimos entre dos peticiones. Con 0,5 s la búsqueda de Scryfall llega a
# responder 429 en expansiones grandes; con 1 s no.
PAUSA_PETICIONES: Final = 1.0
TIMEOUT_PETICIONES: Final = 60  # segundos
MAX_INTENTOS: Final = 3  # intentos por petición ante errores temporales (429, 5xx, red)

# all_cards: todas las impresiones de todas las cartas en todos los idiomas.
TIPO_BULK: Final = "all_cards"
DIRECTORIO_DESCARGAS: Final = Path(
    getenv("DOWNLOAD_DIR", Path(__file__).resolve().parent / "descargas")
)
# Las expansiones publicadas en estos últimos días se vuelven a sincronizar en cada
# ejecución, porque Scryfall añade idiomas y promos después de la fecha de salida.
DIAS_RESINCRONIZACION: Final = int(getenv("RESYNC_DAYS", "30"))
