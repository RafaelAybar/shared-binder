"""Cliente HTTP mínimo para la API de Scryfall (https://scryfall.com/docs/api).

Todas las peticiones pasan por ClienteScryfall._abrir, que añade siempre las cabeceras
User-Agent y Accept que exige Scryfall, espera entre peticiones y reintenta los errores
temporales.
"""

import json
import logging
import ssl
import time
from collections.abc import Iterator
from http.client import HTTPResponse
from pathlib import Path
from typing import Any, Final
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from config import (
    ACCEPT,
    MAX_INTENTOS,
    PAUSA_PETICIONES,
    SCRYFALL_API_URL,
    TIMEOUT_PETICIONES,
    USER_AGENT,
)
from modelos import BulkScryfall, ListaScryfall, SetScryfall

logger = logging.getLogger(__name__)

CABECERAS: Final = {"User-Agent": USER_AGENT, "Accept": ACCEPT}
TAMANO_BLOQUE: Final = 1024 * 1024  # 1 MB
AVISO_DESCARGA: Final = 50 * TAMANO_BLOQUE  # informa del progreso cada 50 MB


class ErrorScryfall(Exception):
    """Scryfall ha respondido con un error que no se resuelve reintentando."""


class NoEncontrado(ErrorScryfall):
    """Scryfall ha respondido 404 (también cuando una búsqueda no tiene resultados)."""


class ClienteScryfall:
    def __init__(self) -> None:
        self._ultima_peticion = 0.0

    # --- API pública -------------------------------------------------------------

    def listar_sets(self) -> Iterator[dict[str, Any]]:
        """Todos los sets de Scryfall, sin validar."""
        return self._paginas(f"{SCRYFALL_API_URL}/sets")

    def obtener_set(self, codigo: str) -> SetScryfall:
        url = f"{SCRYFALL_API_URL}/sets/{quote(codigo.lower())}"
        return SetScryfall.model_validate_json(self._leer(url))

    def obtener_bulk(self, tipo: str) -> BulkScryfall:
        url = f"{SCRYFALL_API_URL}/bulk-data/{quote(tipo)}"
        return BulkScryfall.model_validate_json(self._leer(url))

    def cartas_de_set(self, set_: SetScryfall) -> Iterator[dict[str, Any]]:
        """Todas las cartas del set en todos los idiomas, sin validar.

        Si el set aún no tiene cartas en Scryfall, no devuelve nada.
        """
        # search_uri ya incluye extras, variaciones y unique=prints; falta pedir todos
        # los idiomas para que coincida con el fichero bulk all_cards.
        return self._paginas(f"{set_.search_uri}&include_multilingual=true", vacia_si_404=True)

    def descargar(self, url: str, tamano: int, directorio: Path) -> Path:
        """Descarga url en directorio y devuelve la ruta del fichero.

        Si ya existe un fichero completo con el mismo nombre (de una ejecución anterior
        que falló después de descargar), se reutiliza.
        """
        destino = directorio / Path(urlsplit(url).path).name
        if destino.exists() and destino.stat().st_size == tamano:
            logger.info("Se reutiliza la descarga previa %s", destino)
            return destino

        directorio.mkdir(parents=True, exist_ok=True)
        parcial = destino.with_name(f"{destino.name}.part")
        logger.info("Descargando %s (%d MB) en %s", url, tamano // TAMANO_BLOQUE, destino)
        inicio = time.monotonic()
        descargado = 0
        siguiente_aviso = AVISO_DESCARGA
        with self._abrir(url) as respuesta, parcial.open("wb") as fichero:
            while bloque := respuesta.read(TAMANO_BLOQUE):
                fichero.write(bloque)
                descargado += len(bloque)
                if descargado >= siguiente_aviso:
                    logger.info(
                        "Descargados %d de %d MB", descargado // TAMANO_BLOQUE, tamano // TAMANO_BLOQUE
                    )
                    siguiente_aviso += AVISO_DESCARGA

        if descargado != tamano:
            parcial.unlink()
            raise ErrorScryfall(
                f"Descarga incompleta de {url}: {descargado} de {tamano} bytes"
            )
        parcial.replace(destino)
        logger.info("Descarga completada en %.0f s", time.monotonic() - inicio)
        return destino

    # --- Internos ----------------------------------------------------------------

    def _paginas(self, url: str, vacia_si_404: bool = False) -> Iterator[dict[str, Any]]:
        """Recorre todas las páginas de un objeto list de Scryfall."""
        siguiente: str | None = url
        primera = True
        while siguiente:
            try:
                pagina = ListaScryfall.model_validate_json(self._leer(siguiente))
            except NoEncontrado:
                # Scryfall responde 404 cuando una búsqueda no tiene resultados
                if primera and vacia_si_404:
                    return
                raise
            primera = False
            yield from pagina.data
            siguiente = pagina.next_page if pagina.has_more else None

    def _leer(self, url: str) -> bytes:
        with self._abrir(url) as respuesta:
            return respuesta.read()

    def _abrir(self, url: str) -> HTTPResponse:
        """Abre url con las cabeceras obligatorias, reintentando los errores temporales."""
        for intento in range(1, MAX_INTENTOS + 1):
            self._esperar_turno()
            logger.debug("GET %s", url)
            try:
                return urlopen(Request(url, headers=CABECERAS), timeout=TIMEOUT_PETICIONES)
            except HTTPError as error:
                if error.code == 404:
                    raise NoEncontrado(f"404 en {url}") from error
                temporal = error.code == 429 or error.code >= 500
                if not temporal or intento == MAX_INTENTOS:
                    raise ErrorScryfall(
                        f"HTTP {error.code} en {url}: {_detalle_error(error)}"
                    ) from error
                espera = _segundos_retry_after(error) or 2**intento
                motivo = f"HTTP {error.code}"
            except OSError as error:  # errores de red y timeouts (HTTPError ya tratado)
                if intento == MAX_INTENTOS or _es_permanente(error):
                    raise
                espera = 2**intento
                motivo = repr(error)
            logger.warning(
                "%s en %s (intento %d de %d); se reintenta en %d s",
                motivo, url, intento, MAX_INTENTOS, espera,
            )
            time.sleep(espera)
        raise AssertionError("inalcanzable")

    def _esperar_turno(self) -> None:
        """Respeta la pausa mínima entre peticiones que pide Scryfall."""
        espera = self._ultima_peticion + PAUSA_PETICIONES - time.monotonic()
        if espera > 0:
            time.sleep(espera)
        self._ultima_peticion = time.monotonic()


def _es_permanente(error: OSError) -> bool:
    """Un certificado TLS no válido no se arregla reintentando."""
    causa = error.reason if isinstance(error, URLError) else error
    return isinstance(causa, ssl.SSLCertVerificationError)


def _segundos_retry_after(error: HTTPError) -> int | None:
    valor = error.headers.get("Retry-After", "")
    return int(valor) if valor.isdigit() else None


def _detalle_error(error: HTTPError) -> str:
    """Mensaje del objeto error de Scryfall o, si no lo hay, el motivo HTTP."""
    try:
        return json.loads(error.read()).get("details") or error.reason
    except (ValueError, AttributeError):
        return str(error.reason)
