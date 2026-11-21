"""Modelos Pydantic de los objetos de la API de Scryfall que usa el ETL.

Solo se declaran los campos que se guardan o se usan para filtrar; el resto se ignora.
Referencia: https://scryfall.com/docs/api
"""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, HttpUrl


class ModeloScryfall(BaseModel):
    """Base común: ignora los campos que no usamos y hace los objetos inmutables."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class ImagenesCarta(ModeloScryfall):
    """Objeto image_uris. Solo interesa el tamaño small (146×204 JPG)."""

    small: HttpUrl | None = None


class CaraCarta(ModeloScryfall):
    """Una cara de una carta con varias caras (card_faces)."""

    name: str
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
    mana_cost: str | None = None
    type_line: str | None = None
    released_at: date
    digital: bool
    # missing: Scryfall aún no tiene escaneo y image_uris apunta a una imagen genérica
    # ("soon.webp"). Se guarda NULL y la re-sincronización la rellena cuando exista.
    image_status: str | None = None
    image_uris: ImagenesCarta | None = None
    card_faces: list[CaraCarta] | None = None

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
        return not self.digital and self.released_at is not None and self.released_at <= hoy


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
