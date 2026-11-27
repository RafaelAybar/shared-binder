"""Modelos Pydantic de los objetos de la API de Scryfall que usa el ETL.

Solo se declaran los campos que se guardan o se usan para filtrar; el resto se ignora.
Referencia: https://scryfall.com/docs/api
"""

from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Final
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    HttpUrl,
)

# Acabados en que puede existir una impresión (campo finishes de Scryfall). Son los valores
# del tipo mtg_finish de esquema.sql, en el mismo orden (test_bd.py lo comprueba). Para
# admitir uno nuevo, ver «Acabados» en docs/procesos/ingesta.md.
ACABADOS: Final = ("nonfoil", "foil", "etched")


def _ordenar_acabados(acabados: list[str]) -> list[str]:
    """Sin repetidos y en el orden del tipo, con los desconocidos al final. Así, si Scryfall
    envía los mismos acabados en otro orden, la carta no cuenta como cambiada."""

    def posicion(acabado: str) -> tuple[int, str]:
        return (
            ACABADOS.index(acabado) if acabado in ACABADOS else len(ACABADOS),
            acabado,
        )

    return sorted(set(acabados), key=posicion)


class ModeloScryfall(BaseModel):
    """Base común: ignora los campos que no usamos y hace los objetos inmutables."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class ImagenesCarta(ModeloScryfall):
    """Objeto image_uris. Solo interesa el tamaño small (146×204 JPG)."""

    small: HttpUrl | None = None


class CaraCarta(ModeloScryfall):
    """Una cara de una carta con varias caras (card_faces)."""

    name: str
    printed_name: str | None = None
    mana_cost: str | None = None
    type_line: str | None = None
    cmc: Decimal | None = None
    image_uris: ImagenesCarta | None = None


class CartaScryfall(ModeloScryfall):
    """Una impresión concreta de una carta en un idioma concreto."""

    id: UUID
    oracle_id: UUID | None = None  # las cartas reversibles no lo tienen en la raíz
    set_id: UUID
    collector_number: str
    lang: str
    name: str
    printed_name: str | None = None  # nombre impreso en el idioma de la carta
    rarity: str
    layout: str
    # Normal, foil o etched: la impresión (y su id) es la misma en todos. Aquí se acepta
    # cualquier lista, o ninguna (se toma como vacía), porque también llegan cartas que el
    # ETL descarta (digitales, en preview...); etl.py comprueba error_acabados() solo en las
    # que va a guardar.
    finishes: Annotated[
        list[str],
        BeforeValidator(lambda valor: [] if valor is None else valor),
        AfterValidator(_ordenar_acabados),
    ] = Field(default_factory=list)
    # printed_name, mana_cost, type_line y cmc faltan en la raíz de algunas cartas con
    # varias caras: el ETL guarda los de las propiedades de abajo, que los toman de las
    # caras. cmc es decimal porque algunas cartas Un- cuestan ½.
    mana_cost: str | None = None
    cmc: Decimal | None = None
    type_line: str | None = None
    released_at: date
    digital: bool
    # missing: Scryfall aún no tiene escaneo y image_uris apunta a una imagen genérica
    # ("soon.webp"). Se guarda NULL y la re-sincronización la rellena cuando exista.
    image_status: str | None = None
    image_uris: ImagenesCarta | None = None
    card_faces: list[CaraCarta] | None = None

    @property
    def nombre_impreso(self) -> str | None:
        """Las cartas no inglesas con varias caras (también split y aventura) solo lo
        tienen en cada cara."""
        if self.printed_name is not None:
            return self.printed_name
        return self._unir_caras(lambda cara: cara.printed_name)

    @property
    def coste_mana(self) -> str | None:
        """Las cartas de dos caras físicas solo lo tienen en cada cara. Las caras sin
        coste no se unen: Delver of Secrets // Insectile Aberration cuesta {U}."""
        if self.mana_cost is not None:
            return self.mana_cost
        return self._unir_caras(lambda cara: cara.mana_cost)

    @property
    def linea_tipo(self) -> str | None:
        """Las cartas reversibles solo la tienen en cada cara."""
        if self.type_line is not None:
            return self.type_line
        return self._unir_caras(lambda cara: cara.type_line)

    @property
    def valor_mana(self) -> Decimal | None:
        """Las cartas reversibles solo lo tienen en cada cara: se toma el de la frontal."""
        if self.cmc is not None or not self.card_faces:
            return self.cmc
        return self.card_faces[0].cmc

    @property
    def imagen_small(self) -> str | None:
        """Imagen small de la carta o, si tiene dos caras físicas, de la cara frontal."""
        if self.image_status == "missing":
            return None
        if self.image_uris and self.image_uris.small:
            return str(self.image_uris.small)
        return self._imagen_de_cara(0)

    @property
    def imagen_small_trasera(self) -> str | None:
        """Imagen small de la cara trasera; solo existe en cartas de dos caras físicas.

        Las cartas con varias caras impresas en el mismo lado (split, aventura, flip...)
        tienen una única imagen en la raíz y no tienen cara trasera.
        """
        if self.image_status == "missing" or self.image_uris is not None:
            return None
        return self._imagen_de_cara(1)

    def error_acabados(self) -> str | None:
        """Por qué no se pueden guardar los acabados, o None si se pueden. Una lista vacía
        también es un error: no se podría registrar ninguna copia de la carta."""
        if not self.finishes:
            return "no tiene ningún acabado"
        if desconocidos := [a for a in self.finishes if a not in ACABADOS]:
            return (
                f"acabado desconocido {', '.join(desconocidos)}; para admitirlo, ver "
                "«Acabados» en docs/procesos/ingesta.md"
            )
        return None

    def _unir_caras(self, campo: Callable[[CaraCarta], str | None]) -> str | None:
        """El campo de cada cara, unidos con « // » como Scryfall une los nombres. None si
        ninguna cara lo tiene."""
        valores = [
            v for cara in self.card_faces or [] if (v := campo(cara)) is not None
        ]
        if not valores:
            return None
        return " // ".join(valor for valor in valores if valor)

    def _imagen_de_cara(self, indice: int) -> str | None:
        if not self.card_faces or len(self.card_faces) <= indice:
            return None
        imagenes = self.card_faces[indice].image_uris
        return str(imagenes.small) if imagenes and imagenes.small else None


class SetScryfall(ModeloScryfall):
    """Una expansión (o cualquier otro producto) de Magic."""

    id: UUID
    code: str
    name: str
    set_type: str
    released_at: date | None = None
    card_count: int
    digital: bool
    parent_set_code: str | None = None
    icon_svg_uri: HttpUrl | None = None
    search_uri: str  # búsqueda de Scryfall con todas las cartas del set

    def es_oficial(self, hoy: date) -> bool:
        """Oficial = se vende en papel (no es solo digital) y ya ha salido a la venta."""
        return (
            not self.digital
            and self.released_at is not None
            and self.released_at <= hoy
        )


class ListaScryfall(ModeloScryfall):
    """Objeto list paginado. Los elementos se validan uno a uno fuera de aquí, para
    poder descartar los incorrectos sin perder el resto de la página."""

    data: list[dict[str, Any]]
    has_more: bool = False
    next_page: str | None = None


class BulkScryfall(ModeloScryfall):
    """Descripción de un fichero bulk (GET /bulk-data/{tipo})."""

    type: str
    updated_at: datetime
    jsonl_download_uri: HttpUrl  # JSON Lines comprimido con gzip: una carta por línea
    compressed_size: int
