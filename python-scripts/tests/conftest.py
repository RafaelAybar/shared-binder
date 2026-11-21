"""Configuración común de los tests del ETL.

Ningún test se conecta a Scryfall. Solo test_bd.py usa PostgreSQL, y únicamente si hay
una base de datos de pruebas configurada; el resto usa los dobles de falsos.py.
"""

import os

# config.py exige estas variables al importarse. Los tests no las usan para conectarse.
for _variable in ("PG_USER", "PG_PASSWORD", "PG_HOST", "PG_DATABASE"):
    os.environ.setdefault(_variable, "tests")

import pytest  # noqa: E402

import bd  # noqa: E402
import etl  # noqa: E402
import scryfall  # noqa: E402
from ejemplos import HOY  # noqa: E402
from falsos import BDFalsa  # noqa: E402


@pytest.fixture(autouse=True)
def dia_fijo(monkeypatch: pytest.MonkeyPatch) -> None:
    """El ETL toma HOY como fecha actual para decidir qué está publicado."""
    monkeypatch.setattr(etl, "hoy", lambda: HOY)


@pytest.fixture(autouse=True)
def sin_conexiones_reales(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si un test intenta llegar a Scryfall o a la base de datos de config.py, falla."""

    def prohibido(*args: object, **kwargs: object) -> None:
        raise AssertionError("Los tests no deben conectarse a Scryfall ni a la base de datos real")

    monkeypatch.setattr(scryfall, "urlopen", prohibido)
    monkeypatch.setattr(bd, "conectar", prohibido)


@pytest.fixture
def bd_falsa(monkeypatch: pytest.MonkeyPatch) -> BDFalsa:
    """BDFalsa en lugar de PostgreSQL: se pasa como conexión y sustituye a bd.py."""
    falsa = BDFalsa()
    for funcion in (
        "sets_guardados",
        "codigos_ocupados",
        "copiar_a_temporal",
        "upsert_sets",
        "fusionar_cartas",
    ):
        monkeypatch.setattr(bd, funcion, getattr(falsa, funcion))
    return falsa
