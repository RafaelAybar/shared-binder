"""Datos de ejemplo con la forma de la API de Scryfall.

Cada test parte de las tres cartas de tres_cartas() y cambia lo que necesita para provocar
su caso. Las funciones devuelven diccionarios nuevos en cada llamada, así que un test puede
modificarlos sin afectar a los demás.
"""

from datetime import date
from typing import Any

# Fecha fija para que los tests no dependan del día en que se ejecutan: conftest.py la
# usa como fecha actual del ETL.
HOY = date(2025, 3, 1)

# Ids ficticios, fáciles de reconocer en los mensajes de error.
ID_FDN = "00000000-0000-4000-a000-000000000001"
ID_DSK = "00000000-0000-4000-a000-000000000002"
ID_DFT = "00000000-0000-4000-a000-000000000003"
ID_YDFT = "00000000-0000-4000-a000-000000000004"
ID_TDM = "00000000-0000-4000-a000-000000000005"
ID_FDN_ANTIGUO = "00000000-0000-4000-a000-000000000099"  # mismo código, otro id

ID_LLANOWAR = "00000000-0000-4000-b000-000000000001"
ID_DELVER = "00000000-0000-4000-b000-000000000002"
ID_RAYO = "00000000-0000-4000-b000-000000000003"

# código: (id, nombre, tipo, fecha de salida, solo digital)
_SETS = {
    "fdn": (ID_FDN, "Foundations", "core", "2024-11-15", False),
    "dsk": (ID_DSK, "Duskmourn: House of Horror", "expansion", "2024-09-27", False),
    "dft": (ID_DFT, "Aetherdrift", "expansion", "2025-02-14", False),  # salió hace 15 días
    "ydft": (ID_YDFT, "Alchemy: Aetherdrift", "alchemy", "2025-02-25", True),  # solo MTG Arena
    "tdm": (ID_TDM, "Tarkir: Dragonstorm", "expansion", "2025-04-11", False),  # en preview
}


def set_scryfall(codigo: str = "fdn", **cambios: Any) -> dict[str, Any]:
    """Un set como lo devuelve GET /sets/{código}. cambios sustituye campos."""
    id_, nombre, tipo, salida, digital = _SETS[codigo]
    return {
        "object": "set",
        "id": id_,
        "code": codigo,
        "name": nombre,
        "set_type": tipo,
        "released_at": salida,
        "card_count": 3,
        "digital": digital,
        "icon_svg_uri": f"https://svgs.scryfall.io/sets/{codigo}.svg?1740000000",
        "search_uri": (
            "https://api.scryfall.com/cards/search?include_extras=true"
            f"&include_variations=true&order=set&q=e%3A{codigo}&unique=prints"
        ),
    } | cambios


def imagen(id_carta: str, cara: str = "front", version: int = 1730000000) -> str:
    """URL de la imagen small de una cara, con el formato de Scryfall."""
    return (
        f"https://cards.scryfall.io/small/{cara}/{id_carta[0]}/{id_carta[1]}/{id_carta}.jpg"
        f"?{version}"
    )


def tres_cartas(id_set: str = ID_FDN) -> list[dict[str, Any]]:
    """Una carta normal, una de dos caras y una impresión en español, del set id_set."""
    llanowar = _carta(
        id_set,
        id=ID_LLANOWAR,
        oracle_id="00000000-0000-4000-c000-000000000001",
        name="Llanowar Elves",
        collector_number="227",
        rarity="common",
        layout="normal",
        mana_cost="{G}",
        type_line="Creature — Elf Druid",
        image_uris={"small": imagen(ID_LLANOWAR), "normal": "https://cards.scryfall.io/n.jpg"},
    )
    # Dos caras físicas: no hay image_uris en la raíz, cada cara tiene la suya.
    delver = _carta(
        id_set,
        id=ID_DELVER,
        oracle_id="00000000-0000-4000-c000-000000000002",
        name="Delver of Secrets // Insectile Aberration",
        collector_number="51",
        rarity="common",
        layout="transform",
        type_line="Creature — Human Wizard // Creature — Human Insect",
        card_faces=[
            {
                "object": "card_face",
                "name": "Delver of Secrets",
                "mana_cost": "{U}",
                "image_uris": {"small": imagen(ID_DELVER)},
            },
            {
                "object": "card_face",
                "name": "Insectile Aberration",
                "mana_cost": "",
                "image_uris": {"small": imagen(ID_DELVER, "back")},
            },
        ],
    )
    rayo = _carta(
        id_set,
        id=ID_RAYO,
        oracle_id="00000000-0000-4000-c000-000000000003",
        name="Lightning Bolt",
        printed_name="Rayo",
        lang="es",
        collector_number="187",
        rarity="uncommon",
        layout="normal",
        mana_cost="{R}",
        type_line="Instant",
        printed_type_line="Instantáneo",
        image_uris={"small": imagen(ID_RAYO)},
    )
    return [llanowar, delver, rayo]


def _carta(id_set: str, **campos: Any) -> dict[str, Any]:
    return {
        "object": "card",
        "set_id": id_set,
        "lang": "en",
        "released_at": "2024-11-15",
        "digital": False,
        "image_status": "highres_scan",
        "prices": {"eur": "0.10"},  # campo que el ETL no usa: debe ignorarse
    } | campos
