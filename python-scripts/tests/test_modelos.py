"""Tests de los modelos de Scryfall (modelos.py): imágenes small, datos que solo tienen
las caras y sets oficiales."""

from decimal import Decimal
from typing import Any

import pytest

from ejemplos import (
    HOY,
    ID_DELVER,
    ID_LLANOWAR,
    ID_RAYO,
    imagen,
    set_scryfall,
    tres_cartas,
)
from modelos import CartaScryfall, SetScryfall

PENDIENTE = (
    "https://cards.scryfall.io/small/front/soon.webp"  # imagen genérica de Scryfall
)


def validar(datos: list[dict[str, Any]]) -> list[CartaScryfall]:
    return [CartaScryfall.model_validate(d) for d in datos]


def test_imagen_small_de_las_tres_cartas() -> None:
    llanowar, delver, rayo = validar(tres_cartas())

    assert (llanowar.imagen_small, llanowar.imagen_small_trasera) == (
        imagen(ID_LLANOWAR),
        None,
    )
    assert (delver.imagen_small, delver.imagen_small_trasera) == (
        imagen(ID_DELVER),
        imagen(ID_DELVER, "back"),
    )
    assert (rayo.imagen_small, rayo.imagen_small_trasera) == (imagen(ID_RAYO), None)


def test_cartas_con_dos_caras_en_el_mismo_lado_no_tienen_imagen_trasera() -> None:
    """Split, aventura y flip tienen varias caras pero una sola imagen, en la raíz."""
    formatos = [
        ("split", "Fire", "Ice"),
        ("adventure", "Bonecrusher Giant", "Stomp"),
        ("flip", "Akki Lavarunner", "Tok-Tok, Volcano Born"),
    ]
    cartas = [
        carta
        | {
            "layout": layout,
            "name": f"{cara} // {otra}",
            "card_faces": [{"name": cara}, {"name": otra}],
        }
        for carta, (layout, cara, otra) in zip(tres_cartas(), formatos, strict=True)
    ]
    cartas[1]["image_uris"] = {
        "small": imagen(ID_DELVER)
    }  # la de dos caras no la tenía

    for carta in validar(cartas):
        assert carta.imagen_small == imagen(str(carta.id))
        assert carta.imagen_small_trasera is None


def test_imagen_aun_no_escaneada_se_guarda_vacia() -> None:
    """Con image_status missing, Scryfall sirve una imagen genérica que no se guarda."""
    cartas = tres_cartas()
    for carta in cartas:
        carta["image_status"] = "missing"
        if "image_uris" in carta:
            carta["image_uris"] = {"small": PENDIENTE}
    for cara in cartas[1]["card_faces"]:
        cara["image_uris"] = {"small": PENDIENTE}

    for carta in validar(cartas):
        assert (carta.imagen_small, carta.imagen_small_trasera) == (None, None)


def test_coste_de_las_cartas_de_dos_caras() -> None:
    """Se unen los costes de las caras, sin las que no tienen."""
    valki = tres_cartas()[1] | {
        "layout": "modal_dfc",
        "name": "Valki, God of Lies // Tibalt, Cosmic Impostor",
        "card_faces": [
            {"name": "Valki, God of Lies", "mana_cost": "{1}{B}"},
            {"name": "Tibalt, Cosmic Impostor", "mana_cost": "{5}{B}{R}"},
        ],
    }

    assert validar(tres_cartas())[1].coste_mana == "{U}"
    assert CartaScryfall.model_validate(valki).coste_mana == "{1}{B} // {5}{B}{R}"


def test_nombre_impreso_de_las_cartas_con_varias_caras() -> None:
    fuego_hielo = tres_cartas()[2]  # la impresión en español
    del fuego_hielo["printed_name"]
    fuego_hielo |= {
        "layout": "split",
        "name": "Fire // Ice",
        "card_faces": [
            {"name": "Fire", "printed_name": "Fuego"},
            {"name": "Ice", "printed_name": "Hielo"},
        ],
    }

    assert CartaScryfall.model_validate(fuego_hielo).nombre_impreso == "Fuego // Hielo"
    assert validar(tres_cartas())[1].nombre_impreso is None  # Delver, en inglés


def test_cartas_reversibles() -> None:
    """Las dos caras son la misma carta con otra ilustración."""
    cara = {
        "name": "Llanowar Elves",
        "mana_cost": "{G}",
        "type_line": "Creature — Elf Druid",
        "cmc": 1.0,
    }
    reversible = tres_cartas()[0]
    for campo in ("mana_cost", "cmc", "type_line"):
        del reversible[campo]
    reversible |= {
        "layout": "reversible_card",
        "name": "Llanowar Elves // Llanowar Elves",
        "card_faces": [cara, cara],
    }
    carta = CartaScryfall.model_validate(reversible)

    assert (carta.coste_mana, carta.linea_tipo, carta.valor_mana) == (
        "{G} // {G}",
        "Creature — Elf Druid // Creature — Elf Druid",
        Decimal("1"),
    )


def test_acabados_sin_repetir_y_siempre_en_el_mismo_orden() -> None:
    """Así, los mismos acabados en otro orden no cuentan como un cambio de la carta."""
    conocidos = tres_cartas()[0] | {"finishes": ["etched", "nonfoil", "etched"]}
    con_uno_nuevo = tres_cartas()[0] | {"finishes": ["holo", "foil"]}

    assert CartaScryfall.model_validate(conocidos).finishes == ["nonfoil", "etched"]
    assert CartaScryfall.model_validate(con_uno_nuevo).finishes == ["foil", "holo"]


def test_campos_nuevos_de_scryfall_se_ignoran() -> None:
    cartas = [c | {"campo_nuevo": {"anadido": "2025-03-01"}} for c in tres_cartas()]

    assert len(validar(cartas)) == 3


@pytest.mark.parametrize(
    ("dato", "oficial"),
    [
        pytest.param(set_scryfall("fdn"), True, id="en papel y publicado"),
        pytest.param(set_scryfall("ydft"), False, id="solo digital"),
        pytest.param(set_scryfall("tdm"), False, id="en preview"),
        pytest.param(
            set_scryfall("fdn", released_at=None), False, id="sin fecha de salida"
        ),
    ],
)
def test_set_oficial(dato: dict[str, Any], oficial: bool) -> None:
    assert SetScryfall.model_validate(dato).es_oficial(HOY) is oficial
