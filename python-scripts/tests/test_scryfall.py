"""Tests del cliente de Scryfall (scryfall.py) sin red.

ScryfallFalso sustituye a urlopen: devuelve respuestas preparadas y apunta cada petición.
time.sleep también se sustituye, así que los tests no esperan de verdad.
"""

import io
import json
import re
import ssl
from collections.abc import Callable
from http.client import HTTPMessage
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

import scryfall
from config import MAX_INTENTOS, PAUSA_PETICIONES
from ejemplos import set_scryfall, tres_cartas
from modelos import SetScryfall
from scryfall import ClienteScryfall, ErrorScryfall

URL_BULK = "https://data.scryfall.io/all-cards/all-cards-20250301090000.jsonl.gz"


class ScryfallFalso:
    def __init__(self, respuestas: tuple[Any, ...]) -> None:
        self.respuestas = list(respuestas)
        self.peticiones: list[Request] = []

    def __call__(self, peticion: Request, timeout: float) -> io.BytesIO:
        self.peticiones.append(peticion)
        respuesta = self.respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        if isinstance(respuesta, bytes):
            return io.BytesIO(respuesta)
        return io.BytesIO(json.dumps(respuesta).encode())

    @property
    def urls(self) -> list[str]:
        return [p.full_url for p in self.peticiones]


Instalar = Callable[..., ScryfallFalso]


@pytest.fixture
def scryfall_falso(monkeypatch: pytest.MonkeyPatch) -> Instalar:
    """Instala un ScryfallFalso con las respuestas dadas, en orden."""

    def instalar(*respuestas: Any) -> ScryfallFalso:
        falso = ScryfallFalso(respuestas)
        monkeypatch.setattr(scryfall, "urlopen", falso)
        return falso

    return instalar


@pytest.fixture(autouse=True)
def esperas(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Segundos que el cliente habría esperado, en orden."""
    registro: list[float] = []
    monkeypatch.setattr(scryfall.time, "sleep", registro.append)
    return registro


def pagina(datos: list[dict[str, Any]], siguiente: str | None = None) -> dict[str, Any]:
    return {
        "object": "list",
        "has_more": siguiente is not None,
        "next_page": siguiente,
        "data": datos,
    }


def error_http(
    codigo: int, detalles: str = "", cabeceras: dict[str, str] | None = None
) -> HTTPError:
    mensaje = HTTPMessage()
    for nombre, valor in (cabeceras or {}).items():
        mensaje[nombre] = valor
    cuerpo = json.dumps(
        {"object": "error", "status": codigo, "details": detalles}
    ).encode()
    return HTTPError(
        "https://api.scryfall.com", codigo, "Error", mensaje, io.BytesIO(cuerpo)
    )


def fdn() -> SetScryfall:
    return SetScryfall.model_validate(set_scryfall("fdn"))


# --- Política de uso de Scryfall ---------------------------------------------------


def test_todas_las_peticiones_llevan_user_agent_y_accept(
    scryfall_falso: Instalar,
) -> None:
    """Scryfall exige un User-Agent propio (nunca el de urllib) y la cabecera Accept."""
    siguiente = "https://api.scryfall.com/sets?page=2"
    falso = scryfall_falso(
        pagina([set_scryfall("fdn"), set_scryfall("dsk")], siguiente),
        pagina([set_scryfall("dft")]),
    )

    sets = list(ClienteScryfall().listar_sets())

    assert [s["code"] for s in sets] == ["fdn", "dsk", "dft"]
    assert len(falso.peticiones) == 2
    for peticion in falso.peticiones:
        assert re.fullmatch(
            r"SharedBinder-ETL/\d+\.\d+\.\d+", peticion.get_header("User-agent", "")
        )
        assert peticion.get_header("Accept") == "application/json;q=0.9,*/*;q=0.8"


def test_pausa_entre_peticiones(scryfall_falso: Instalar, esperas: list[float]) -> None:
    scryfall_falso(set_scryfall("fdn"), set_scryfall("dsk"), set_scryfall("dft"))
    cliente = ClienteScryfall()

    for codigo in ("fdn", "dsk", "dft"):
        cliente.obtener_set(codigo)

    assert (
        esperas == [pytest.approx(PAUSA_PETICIONES, abs=0.1)] * 2
    )  # antes de la 2.ª y la 3.ª


# --- Búsqueda de cartas ------------------------------------------------------------


def test_busqueda_recorre_todas_las_paginas_en_todos_los_idiomas(
    scryfall_falso: Instalar,
) -> None:
    cartas = tres_cartas()
    siguiente = "https://api.scryfall.com/cards/search?page=2&q=e%3Afdn"
    falso = scryfall_falso(pagina(cartas[:2], siguiente), pagina(cartas[2:]))

    recibidas = list(ClienteScryfall().cartas_de_set(fdn()))

    assert [c["id"] for c in recibidas] == [c["id"] for c in cartas]
    assert falso.urls[0].endswith("&include_multilingual=true")
    assert falso.urls[1] == siguiente


def test_busqueda_sin_resultados_no_devuelve_cartas(scryfall_falso: Instalar) -> None:
    """Scryfall responde 404 cuando un set aún no tiene cartas."""
    scryfall_falso(error_http(404, "Your query didn't match any cards."))

    assert list(ClienteScryfall().cartas_de_set(fdn())) == []


# --- Errores y reintentos ----------------------------------------------------------


def test_429_se_reintenta_respetando_retry_after(
    scryfall_falso: Instalar, esperas: list[float]
) -> None:
    falso = scryfall_falso(
        error_http(429, cabeceras={"Retry-After": "7"}), pagina(tres_cartas())
    )

    assert len(list(ClienteScryfall().cartas_de_set(fdn()))) == 3
    assert len(falso.peticiones) == 2
    assert 7 in esperas


def test_error_del_servidor_se_reintenta_hasta_agotar_los_intentos(
    scryfall_falso: Instalar, esperas: list[float]
) -> None:
    falso = scryfall_falso(*(error_http(503) for _ in range(MAX_INTENTOS)))

    with pytest.raises(ErrorScryfall, match="HTTP 503"):
        list(ClienteScryfall().listar_sets())

    assert len(falso.peticiones) == MAX_INTENTOS
    # Espera exponencial entre intentos (las demás esperas son la pausa entre peticiones).
    assert [e for e in esperas if e >= 2] == [2**i for i in range(1, MAX_INTENTOS)]


def test_error_400_no_se_reintenta_y_explica_el_motivo(
    scryfall_falso: Instalar,
) -> None:
    falso = scryfall_falso(error_http(400, "All of your terms were ignored."))
    cartas = ClienteScryfall().cartas_de_set(fdn())  # un generador: aún no pide nada

    with pytest.raises(ErrorScryfall, match="All of your terms were ignored"):
        list(cartas)

    assert len(falso.peticiones) == 1


def test_corte_de_red_se_reintenta(scryfall_falso: Instalar) -> None:
    falso = scryfall_falso(
        URLError(ConnectionResetError(54, "Connection reset by peer")), set_scryfall()
    )

    assert ClienteScryfall().obtener_set("fdn").code == "fdn"
    assert len(falso.peticiones) == 2


def test_certificado_no_valido_no_se_reintenta(scryfall_falso: Instalar) -> None:
    falso = scryfall_falso(
        URLError(ssl.SSLCertVerificationError(1, "certificate verify failed"))
    )

    with pytest.raises(URLError):
        ClienteScryfall().obtener_set("fdn")

    assert len(falso.peticiones) == 1


# --- Descarga del fichero bulk -----------------------------------------------------


def test_descarga_completa(scryfall_falso: Instalar, tmp_path) -> None:
    scryfall_falso(b"x" * 10)

    ruta = ClienteScryfall().descargar(URL_BULK, 10, tmp_path)

    assert ruta == tmp_path / "all-cards-20250301090000.jsonl.gz"
    assert ruta.read_bytes() == b"x" * 10
    assert list(tmp_path.iterdir()) == [ruta]  # no queda el .part


def test_descarga_cortada_falla_sin_dejar_ficheros(
    scryfall_falso: Instalar, tmp_path
) -> None:
    scryfall_falso(b"x" * 6)

    with pytest.raises(ErrorScryfall, match="incompleta"):
        ClienteScryfall().descargar(URL_BULK, 10, tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_se_reutiliza_una_descarga_previa_completa(
    scryfall_falso: Instalar, tmp_path
) -> None:
    previa = tmp_path / "all-cards-20250301090000.jsonl.gz"
    previa.write_bytes(b"x" * 10)
    falso = scryfall_falso()

    assert ClienteScryfall().descargar(URL_BULK, 10, tmp_path) == previa
    assert falso.peticiones == []
