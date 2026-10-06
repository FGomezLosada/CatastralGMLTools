# Catastral GML Tools

[Español](#español) · [English](#english)

> ⚠ **Herramienta no oficial.** Catastral GML Tools no pertenece ni está avalada por la Dirección General del Catastro. Valide siempre el resultado en la [Sede Electrónica del Catastro](https://www.sedecatastro.gob.es/) antes de usarlo en cualquier trámite.

## Español

Plugin de QGIS para preparar los ficheros GML que pide la Sede Electrónica del Catastro:

- **GML de parcela** (INSPIRE CadastralParcels 4.0) para el informe de validación gráfica: una o varias parcelas, con los identificadores que corresponden a cada alteración (segregación, división, agregación, agrupación, subsanación).
- **GML de edificio** (INSPIRE BuildingExtended2D) para el informe de ubicación de construcciones: edificios y otras construcciones (piscinas).
- **Comprobar** un GML antes de subirlo: estructura, identificadores, orientación de los anillos, superficie, solapes y sistema de referencia.
- **Utilidades**: abrir y revisar GML, convertir del esquema 3.0 al 4.0, unir varios GML, dividir parcelas, descargar una parcela concreta (y sus colindantes y construcciones) por referencia catastral, e informes de superficies y coordenadas.

> Estado: **en desarrollo** (versión 0.1.0, esqueleto). Las funciones se activan versión a versión; ver [CHANGELOG](CHANGELOG.md) y [docs/DESARROLLO.md](docs/DESARROLLO.md).

### Requisitos
QGIS 3.34 o posterior, incluido QGIS 4 (Qt6). Sin dependencias externas.

### Instalación
- Desde el repositorio oficial de QGIS (cuando se publique): *Complementos → Administrar e instalar complementos* → buscar «Catastral GML Tools».
- Desde ZIP: descarga el ZIP de la última [versión](https://github.com/FGomezLosada/CatastralGMLTools/releases) y usa *Complementos → Instalar a partir de ZIP*.

El panel se abre desde el botón de la barra de herramientas o desde *Vectorial → Catastral GML Tools*.

### Ámbito territorial
Territorio gestionado por la Dirección General del Catastro. Navarra y los territorios forales del País Vasco (Álava/Araba, Gipuzkoa y Bizkaia) tienen catastros propios: el plugin los detecta y lo indica.

### Datos
Los datos descargados proceden de los servicios públicos de la **Dirección General del Catastro**, que se cita como fuente junto con la fecha de descarga. El plugin no usa datos protegidos (titulares ni valores catastrales) y no incluye datos del Catastro.

### Licencia
GPL-2.0-or-later. Ver [LICENSE](LICENSE) y [CREDITS.md](CREDITS.md).

---

## English

QGIS plugin to prepare the GML files required by the Spanish Cadastre electronic office (Sede Electrónica del Catastro):

- **Cadastral parcel GML** (INSPIRE CadastralParcels 4.0) for graphic validation reports, with the identifiers required by each kind of change.
- **Building GML** (INSPIRE BuildingExtended2D) for construction location reports: buildings and other constructions (swimming pools).
- **Check** a GML file before uploading it: structure, identifiers, ring orientation, area, overlaps and reference system.
- **Utilities**: open and review GML files, convert schema 3.0 to 4.0, merge GML files, divide parcels, download a single parcel (with its neighbours and buildings) by cadastral reference, and area and coordinate reports.

> Status: **under development** (version 0.1.0, skeleton).

Requires QGIS 3.34 or later, including QGIS 4 (Qt6). Covers the territory managed by the Spanish Directorate General for Cadastre; Navarre and the Basque Country have their own cadastres. **Not an official tool**: always validate the result in the Sede Electrónica del Catastro. Cadastral data: Dirección General del Catastro. User interface in Spanish. Licence: GPL-2.0-or-later.

---

© 2026 Francisco Gómez Losada
