# Shared-Binder

## Descripción del proyecto

Shared-Binder es una aplicación web que permite tanto gestionar colecciones de cartas, como préstamos entre particulares

> **Advertencia**: El objetivo de Shared Binder no es otro que hacer de testigo, no mediar de forma activa entre jugadores
> ni tiene per se validez jurídica. Es un pacto entre dos personas firmado por ellas, y shared binder es un testigo imparcial.

## Funcionalidad

Esta web permite a jugadores gestionar la collección de cartas de múltiples juegos, por ejemplo:

* Magic the Gathering
* Yu-Gi-Oh!
* Digimon Card Game
* Gundam
* One Piece
* Pokémon

Además permite a los usuarios gestionar préstamos entre ellos, generando un PDF que contiene:
Nombre y apellidos de cada jugador, usuario del jugador (opcional) así como estado de la carta y fotos de la misma.

El criterio con el que se dictamina el estado de una carta se corresponde a la [guía de condiciones de una carta de Cardmarket](https://help.cardmarket.com/en/CardCondition)


### Lista de juegos coleccionables implementados

Las imágenes son más difíciles de conseguir, y además hay un conflicto grave potencialmente con la propiedad
intelectual dependiendo del juego de cartas y la monetización de esta aplicación.

| Juego de cartas coleccionables | ¿Tiene automatizada la carga de datos? | ¿Tiene acceso a las imágenes de forma simple?  |
|:------------------------------:|:--------------------------------------:|:----------------------------------------------:|
|       Magic the Gathering      |                   Sí                   |                       No                       |
|            Yu-Gi-Oh!           |                   Sí                   |                       Si                       |
|        Digimon Card Game       |                   Sí                   |                       No                       |
|             Gundam             |                   Sí                   |                       No                       |
|            One Piece           |                   Sí                   |                       No                       |
|             Pokemon            |                   Sí                   |                       No                       |

## Infraestructura y automatización

### Ingesta de datos

No hay estándar alguno oficial por parte de cada juego de cartas, por lo que se podrían usar dos servicios:

* [**tcgcsv**](https://tcgcsv.com/). Es una web que permite ingestar los datos en formato CSV, y actualiza diariamente  las colecciones de TODOS los TCG's, incluyendo los precios.
* [**Scryfall**](https://scryfall.com/docs/api): Permite obtenener información en JSON y varios formatos además de las imágenes, pero en el ámbito de Magic The Gathering.

En esta tabla comparativa se aprecia mejor:


| Característica | [Scryfall](https://scryfall.com "Scryfall Magic: The Gathering Search") | [TCGCSV](https://tcgcsv.com "TCGCSV") |
| :--- | :--- | :--- |
| **Enfoque principal** | Base de datos, reglas, arte y buscador de cartas de MTG | Catálogo de productos y precios de TCGplayer |
| **Juegos compatibles** | Solo *Magic: The Gathering* | Más de 90 categorías (MTG, Pokémon, Yu-Gi-Oh!, Lorcana, One Piece, accesorios, etc.) |
| **Formatos de datos** | API REST (JSON/CSV) y archivos masivos (*bulk data*) en JSON | Hojas de cálculo CSV estáticas y endpoints JSON |
| **Detalle de precios** | Capturas diarias básicas (USD, EUR, TIX) | Precios detallados de TCGplayer (Bajo, Medio, Alto, Mercado, Directo) + historial |
| **Metadatos del juego** | Texto Oracle, reglas, legalidad por formato, artista, imágenes en alta resolución | Nombres de productos, IDs de colección/grupo y atributos básicos (sin texto de reglas) |
| **Costo y acceso** | Gratis, no requiere clave de API (*API key*) | Gratis, no requiere clave de API (*API key*) |

Se puede obtener el detalle en [Documentación de la ingesta](docs/procesos/ingesta.md)

### PHP y versión de Laravel

* Versión de PHP: 8.5 o superior
* Versión de Laravel: 13

### Versión de Node

* Node 26

### Librerías del frontend

* Svelte

### Base de datos

* Postgres 19 o superior
