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