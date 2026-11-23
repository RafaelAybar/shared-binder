"""Tests de la ingesta (etl.py) sin red ni base de datos.

Cada caso parte de las tres cartas de ejemplo de ejemplos.py. ClienteFalso hace de API de
Scryfall y BDFalsa de PostgreSQL (ver falsos.py).
"""

import json
import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

import psycopg
import pytest

import etl
from bd import ResultadoFusion
from ejemplos import (
    ID_DELVER,
    ID_DFT,
    ID_DSK,
    ID_FDN,
    ID_FDN_ANTIGUO,
    ID_LLANOWAR,
    ID_RAYO,
    ID_TDM,
    ID_YDFT,
    imagen,
    set_scryfall,
    tres_cartas,
)
from falsos import BDFalsa, ClienteFalso
from modelos import CartaScryfall
from scryfall import ErrorScryfall


def ids(cartas: list[CartaScryfall]) -> list[str]:
    return [str(c.id) for c in cartas]


def mensajes(caplog: pytest.LogCaptureFixture, nivel: int) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == nivel]


def lineas_bulk(cartas: list[dict[str, Any]]) -> list[str]:
    return [json.dumps(c, ensure_ascii=False) for c in cartas]


# --- Errores de formato ------------------------------------------------------------

Rotura = Callable[[dict[str, Any]], object]

ERRORES_DE_FORMATO = [
    pytest.param(lambda c: c.pop("id"), "id", id="falta el id"),
    pytest.param(lambda c: c.pop("name"), "name", id="falta el nombre"),
    pytest.param(lambda c: c.pop("released_at"), "released_at", id="falta la fecha"),
    pytest.param(
        lambda c: c.update(id="no-es-un-uuid"), "id", id="id que no es un UUID"
    ),
    pytest.param(
        lambda c: c.update(released_at="15/11/2024"),
        "released_at",
        id="fecha con otro formato",
    ),
    pytest.param(
        lambda c: c.update(digital="quizás"), "digital", id="booleano no válido"
    ),
    pytest.param(
        lambda c: c.update(collector_number=None),
        "collector_number",
        id="número de colección nulo",
    ),
    pytest.param(
        lambda c: c["card_faces"][1].update(image_uris={"small": "no es una URL"}),
        "card_faces.1.image_uris.small",
        id="URL de imagen no válida",
    ),
    pytest.param(
        lambda c: c.update(card_faces="Delver"),
        "card_faces",
        id="caras que no son una lista",
    ),
    pytest.param(
        lambda c: c.update(finishes=["nonfoil", "glossy"]),
        "finishes",
        id="acabado desconocido",
    ),
]


@pytest.mark.parametrize(("romper", "campo"), ERRORES_DE_FORMATO)
def test_carta_con_formato_incorrecto_se_descarta_y_se_registra(
    romper: Rotura, campo: str, bd_falsa: BDFalsa, caplog: pytest.LogCaptureFixture
) -> None:
    cartas = tres_cartas()
    romper(cartas[1])  # la de dos caras
    cliente = ClienteFalso([set_scryfall("fdn")], {"fdn": cartas})

    resumen = etl.cargar_sets(bd_falsa, cliente, ["fdn"])

    assert ids(bd_falsa.cartas) == [ID_LLANOWAR, ID_RAYO]  # las otras dos se guardan
    assert resumen.invalidas == 1
    assert not resumen.correcto  # el script terminará con código 1
    [error] = mensajes(caplog, logging.ERROR)
    assert "de fdn no es válido" in error
    assert f"{campo}:" in error  # indica el campo que falla


def test_linea_cortada_del_bulk_se_descarta_con_su_numero(
    bd_falsa: BDFalsa, caplog: pytest.LogCaptureFixture, tmp_path
) -> None:
    lineas = lineas_bulk(tres_cartas())
    lineas[1] = lineas[1][:60]  # JSON incompleto, como si el fichero estuviera dañado
    cliente = ClienteFalso([set_scryfall("fdn")], bulk=lineas, directorio=tmp_path)

    resumen = etl.carga_inicial(bd_falsa, cliente)

    assert ids(bd_falsa.cartas) == [ID_LLANOWAR, ID_RAYO]
    assert resumen.invalidas == 1
    [error] = mensajes(caplog, logging.ERROR)
    assert error.startswith("Línea 2 del fichero bulk no es válido")


def test_lineas_en_blanco_del_bulk_se_ignoran(bd_falsa: BDFalsa, tmp_path) -> None:
    llanowar, delver, rayo = lineas_bulk(tres_cartas())
    cliente = ClienteFalso(
        [set_scryfall("fdn")],
        bulk=[llanowar, "", delver, "   ", rayo],
        directorio=tmp_path,
    )

    resumen = etl.carga_inicial(bd_falsa, cliente)

    assert ids(bd_falsa.cartas) == [ID_LLANOWAR, ID_DELVER, ID_RAYO]
    assert resumen.correcto


# --- Publicaciones oficiales -------------------------------------------------------


def test_solo_se_guardan_cartas_en_papel_ya_publicadas(
    bd_falsa: BDFalsa, tmp_path
) -> None:
    cartas = tres_cartas()
    cartas[0]["digital"] = True  # versión solo para MTG Arena
    cartas[1]["released_at"] = "2025-04-11"  # preview: aún no ha salido
    cliente = ClienteFalso(
        [set_scryfall("fdn")], bulk=lineas_bulk(cartas), directorio=tmp_path
    )

    resumen = etl.carga_inicial(bd_falsa, cliente)

    assert ids(bd_falsa.cartas) == [ID_RAYO]
    assert resumen.descartadas == 2
    assert resumen.correcto  # descartar no es un error


@pytest.mark.parametrize(
    ("romper", "motivo"),
    [
        pytest.param(
            lambda c: c.update(finishes=["holo"]),
            "acabado desconocido holo",
            id="desconocido",
        ),
        pytest.param(
            lambda c: c.update(finishes=[]), "no tiene ningún acabado", id="lista vacía"
        ),
        pytest.param(
            lambda c: c.update(finishes=None), "no tiene ningún acabado", id="nulo"
        ),
        pytest.param(
            lambda c: c.pop("finishes"), "no tiene ningún acabado", id="sin el campo"
        ),
    ],
)
def test_acabados_incorrectos_solo_son_error_en_las_cartas_que_se_guardan(
    romper: Rotura,
    motivo: str,
    bd_falsa: BDFalsa,
    caplog: pytest.LogCaptureFixture,
    tmp_path,
) -> None:
    """Si Scryfall estrena un acabado, o deja de enviarlos, en cartas digitales, estas se
    descartan como siempre, sin contar como error."""
    cartas = tres_cartas()
    cartas[0]["digital"] = True
    romper(cartas[0])
    romper(cartas[1])
    cliente = ClienteFalso(
        [set_scryfall("fdn")], bulk=lineas_bulk(cartas), directorio=tmp_path
    )

    resumen = etl.carga_inicial(bd_falsa, cliente)

    assert ids(bd_falsa.cartas) == [ID_RAYO]
    assert (resumen.descartadas, resumen.invalidas) == (1, 1)
    [error] = mensajes(caplog, logging.ERROR)
    assert error.startswith("Línea 2 del fichero bulk no es válido")
    assert f"finishes: {motivo}" in error


def test_cartas_de_sets_no_oficiales_se_descartan(bd_falsa: BDFalsa, tmp_path) -> None:
    cartas = tres_cartas()
    cartas[1]["set_id"] = ID_YDFT  # set solo digital
    cartas[2]["set_id"] = ID_TDM  # set en preview
    sets = [set_scryfall("fdn"), set_scryfall("ydft"), set_scryfall("tdm")]
    cliente = ClienteFalso(sets, bulk=lineas_bulk(cartas), directorio=tmp_path)

    resumen = etl.carga_inicial(bd_falsa, cliente)

    assert ids(bd_falsa.cartas) == [ID_LLANOWAR]
    assert [s.code for s in bd_falsa.sets] == ["fdn"]
    assert resumen.descartadas == 2


def test_set_sin_cartas_no_se_guarda(bd_falsa: BDFalsa, tmp_path) -> None:
    """Así, un set publicado sin cartas en el bulk se vuelve a intentar más adelante."""
    sets = [set_scryfall("fdn"), set_scryfall("dsk")]
    cliente = ClienteFalso(
        sets, bulk=lineas_bulk(tres_cartas(ID_FDN)), directorio=tmp_path
    )

    resumen = etl.carga_inicial(bd_falsa, cliente)

    assert [s.code for s in bd_falsa.sets] == ["fdn"]
    assert resumen.sets == 1


# --- Cartas duplicadas -------------------------------------------------------------


def test_carta_repetida_llega_en_orden_a_la_bd_y_se_avisa(
    bd_falsa: BDFalsa, caplog: pytest.LogCaptureFixture
) -> None:
    """Si la paginación de la búsqueda se desplaza, una carta puede llegar dos veces. El ETL
    pasa ambas copias en el orden recibido: PostgreSQL se queda con la última (test_bd.py
    lo comprueba) y el ETL informa de cuántas había."""
    llanowar, delver, _ = tres_cartas()
    repetida = llanowar | {
        "image_uris": {"small": imagen(ID_LLANOWAR, version=1740000000)}
    }
    cliente = ClienteFalso([set_scryfall("fdn")], {"fdn": [llanowar, delver, repetida]})
    bd_falsa.resultado = ResultadoFusion(insertadas=2, actualizadas=0, duplicadas=1)

    resumen = etl.cargar_sets(bd_falsa, cliente, ["fdn"])

    assert ids(bd_falsa.cartas) == [ID_LLANOWAR, ID_DELVER, ID_LLANOWAR]
    assert bd_falsa.cartas[-1].imagen_small == imagen(ID_LLANOWAR, version=1740000000)
    assert (resumen.insertadas, resumen.duplicadas) == (2, 1)
    assert resumen.correcto  # una carta repetida no es un error
    assert any("repetidas" in m for m in mensajes(caplog, logging.WARNING))


# --- Sets con el código ocupado ----------------------------------------------------


def test_set_recreado_con_otro_id_se_omite_sin_bloquear_el_resto(
    bd_falsa: BDFalsa, caplog: pytest.LogCaptureFixture, tmp_path
) -> None:
    bd_falsa.guardados = {(UUID(ID_FDN_ANTIGUO), "fdn")}  # fdn ya guardado con otro id
    cartas = tres_cartas(ID_FDN)
    cartas[2]["set_id"] = ID_DSK
    sets = [set_scryfall("fdn"), set_scryfall("dsk")]
    cliente = ClienteFalso(sets, bulk=lineas_bulk(cartas), directorio=tmp_path)

    resumen = etl.carga_inicial(bd_falsa, cliente)

    assert ids(bd_falsa.cartas) == [ID_RAYO]  # la de dsk sí se guarda
    assert [s.code for s in bd_falsa.sets] == ["dsk"]
    assert resumen.errores == 1
    [error] = mensajes(caplog, logging.ERROR)
    for texto in ("expansión fdn", "sus 2 cartas", ID_FDN, ID_FDN_ANTIGUO, "--set fdn"):
        assert texto in error


def test_set_recreado_da_error_en_cada_ejecucion_hasta_resolverlo(
    bd_falsa: BDFalsa,
) -> None:
    bd_falsa.guardados = {(UUID(ID_FDN_ANTIGUO), "fdn")}
    cliente = ClienteFalso([set_scryfall("fdn")], {"fdn": tres_cartas()})

    primera = etl.cargar_pendientes(bd_falsa, cliente)
    segunda = etl.cargar_pendientes(bd_falsa, cliente)

    assert (primera.errores, segunda.errores) == (1, 1)
    assert cliente.pedidas == ["fdn", "fdn"]
    assert bd_falsa.cartas == []


def test_set_que_cambia_de_codigo_se_actualiza_aunque_sea_antiguo(
    bd_falsa: BDFalsa,
) -> None:
    bd_falsa.guardados = {(UUID(ID_FDN), "fd1")}  # mismo id, código anterior
    cliente = ClienteFalso([set_scryfall("fdn")], {"fdn": tres_cartas()})

    resumen = etl.cargar_pendientes(bd_falsa, cliente)

    assert bd_falsa.guardados == {(UUID(ID_FDN), "fdn")}
    assert len(bd_falsa.cartas) == 3
    assert resumen.correcto


# --- Carga por expansiones ---------------------------------------------------------


def test_cargar_pendientes_pide_las_nuevas_y_las_recientes(bd_falsa: BDFalsa) -> None:
    llanowar, delver, rayo = tres_cartas()
    delver["set_id"], rayo["set_id"] = ID_DFT, ID_DSK
    bd_falsa.guardados = {(UUID(ID_DFT), "dft"), (UUID(ID_DSK), "dsk")}
    cliente = ClienteFalso(
        [set_scryfall("fdn"), set_scryfall("dft"), set_scryfall("dsk")],
        {"fdn": [llanowar], "dft": [delver], "dsk": [rayo]},
    )

    etl.cargar_pendientes(bd_falsa, cliente)

    # fdn es nueva; dft salió hace 15 días y se re-sincroniza; dsk ya está y es antigua.
    assert cliente.pedidas == ["fdn", "dft"]
    assert ids(bd_falsa.cartas) == [ID_LLANOWAR, ID_DELVER]


@pytest.mark.parametrize(
    "fallo",
    [
        pytest.param(
            {"bd": psycopg.OperationalError("se ha perdido la conexión")},
            id="PostgreSQL",
        ),
        pytest.param({"scryfall": ErrorScryfall("HTTP 503")}, id="Scryfall"),
    ],
)
def test_un_error_en_una_expansion_no_detiene_las_demas(
    fallo: dict[str, Exception], bd_falsa: BDFalsa, caplog: pytest.LogCaptureFixture
) -> None:
    llanowar, delver, rayo = tres_cartas()
    delver["set_id"], rayo["set_id"] = ID_DSK, ID_DFT
    if "bd" in fallo:
        bd_falsa.fallos[UUID(ID_DSK)] = fallo["bd"]
    cliente = ClienteFalso(
        [set_scryfall("fdn"), set_scryfall("dsk"), set_scryfall("dft")],
        {"fdn": [llanowar], "dsk": [delver], "dft": [rayo]},
        fallos={"dsk": fallo["scryfall"]} if "scryfall" in fallo else None,
    )

    resumen = etl.cargar_pendientes(bd_falsa, cliente)

    assert ids(bd_falsa.cartas) == [ID_LLANOWAR, ID_RAYO]
    assert {s.code for s in bd_falsa.sets} == {"fdn", "dft"}
    assert resumen.errores == 1
    assert any("expansión dsk" in m for m in mensajes(caplog, logging.ERROR))


def test_expansion_aun_sin_cartas_no_se_guarda_ni_es_error(
    bd_falsa: BDFalsa, caplog: pytest.LogCaptureFixture
) -> None:
    cliente = ClienteFalso(
        [set_scryfall("fdn")], {"fdn": []}
    )  # la búsqueda responde 404

    resumen = etl.cargar_sets(bd_falsa, cliente, ["fdn"])

    assert bd_falsa.sets == []
    assert resumen.correcto
    assert any("se reintentará" in m for m in mensajes(caplog, logging.WARNING))


def test_cargar_sets_rechaza_codigos_inexistentes_y_no_oficiales(
    bd_falsa: BDFalsa,
) -> None:
    sets = [set_scryfall("fdn"), set_scryfall("ydft"), set_scryfall("tdm")]
    cliente = ClienteFalso(sets, {"fdn": tres_cartas()})

    resumen = etl.cargar_sets(bd_falsa, cliente, ["zzz", "ydft", "tdm", "fdn"])

    assert resumen.errores == 3  # no existe, solo digital y en preview
    assert cliente.pedidas == ["fdn"]
    assert len(bd_falsa.cartas) == 3


# --- Fichero bulk y resultado ------------------------------------------------------


def test_carga_inicial_borra_el_fichero_al_terminar(
    bd_falsa: BDFalsa, tmp_path
) -> None:
    cliente = ClienteFalso(
        [set_scryfall("fdn")], bulk=lineas_bulk(tres_cartas()), directorio=tmp_path
    )

    etl.carga_inicial(bd_falsa, cliente)

    assert cliente.ruta_bulk is not None and not cliente.ruta_bulk.exists()


def test_si_la_carga_inicial_falla_se_conserva_el_fichero(
    bd_falsa: BDFalsa, tmp_path
) -> None:
    """La siguiente ejecución lo reutiliza en vez de volver a descargar ~400 MB."""
    bd_falsa.fallos[UUID(ID_FDN)] = psycopg.OperationalError(
        "se ha perdido la conexión"
    )
    cliente = ClienteFalso(
        [set_scryfall("fdn")], bulk=lineas_bulk(tres_cartas()), directorio=tmp_path
    )

    with pytest.raises(psycopg.OperationalError):
        etl.carga_inicial(bd_falsa, cliente)

    assert cliente.ruta_bulk is not None and cliente.ruta_bulk.exists()
    assert bd_falsa.cartas == []


@pytest.mark.parametrize(
    ("resumen", "correcto"),
    [
        pytest.param(etl.Resumen(insertadas=3), True, id="todo bien"),
        pytest.param(
            etl.Resumen(descartadas=2, duplicadas=1), True, id="descartes y repetidas"
        ),
        pytest.param(etl.Resumen(invalidas=1), False, id="registro inválido"),
        pytest.param(etl.Resumen(errores=1), False, id="expansión fallida"),
    ],
)
def test_codigo_de_salida_segun_el_resumen(
    resumen: etl.Resumen, correcto: bool
) -> None:
    assert resumen.correcto is correcto
