# Fase 0 · Investigación

> Documento de trabajo. Recoge los datos exactos obtenidos de fuentes oficiales y el análisis de plugins y webs de referencia. Fecha: 2026-10-06.
> Plugin: **Catastral GML Tools** (repositorio `FGomezLosada/CatastralGMLTools`, carpeta de QGIS `catastral_gml_tools`).

---

## 1. GML de parcela catastral (IVGA, coordinación Catastro-Registro)

**Norma de base:** INSPIRE Data Specification on Cadastral Parcels (TG 3.1), esquema **CP 4.0**. La Sede Electrónica del Catastro (SEC) **solo acepta el esquema 4.0**; el 3.0 está obsoleto y se rechaza para nuevos IVGA (aviso de la DGC, enero de 2025).

### 1.1 Estructura (esquema 4.0)

| Elemento | Valor / regla |
|---|---|
| Cabecera | `<?xml version="1.0" encoding="utf-8"?>` |
| Raíz | `FeatureCollection` en el espacio por defecto `http://www.opengis.net/wfs/2.0`, con `timeStamp`, `numberMatched`, `numberReturned` |
| Espacios de nombres | `gml=http://www.opengis.net/gml/3.2` · `cp=http://inspire.ec.europa.eu/schemas/cp/4.0` · `xsi=http://www.w3.org/2001/XMLSchema-instance` · (`gmd=http://www.isotc211.org/2005/gmd`) · base 3.3 declarado en línea en `Identifier` |
| schemaLocation | `http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://inspire.ec.europa.eu/schemas/cp/4.0 http://inspire.ec.europa.eu/schemas/cp/4.0/CadastralParcels.xsd` |
| Contenedor | Un `<member>` por parcela. **Varias parcelas en un fichero: sí** (multiparcela) |
| Recintos | **Un solo recinto por parcela**: la SEC no valida parcelas con más de un `gml:surfaceMember` (no admite parcelas multiparte) |
| Orden de hijos de `cp:CadastralParcel` | `areaValue` → `beginLifespanVersion` → `endLifespanVersion` → `geometry` → `inspireId` → `label` → `nationalCadastralReference` → `referencePoint` |
| `gml:id` de la parcela | `ES.<SDGC|LOCAL>.CP.<localId>` |
| `cp:areaValue uom="m2"` | Superficie cartesiana de la geometría, **redondeada al m²** (entero) |
| `cp:beginLifespanVersion` | `AAAA-MM-DDTHH:MM:SS` |
| `cp:endLifespanVersion` | `xsi:nil="true" nilReason="http://inspire.ec.europa.eu/codelist/VoidReasonValue/Unpopulated"` |
| Geometría | `gml:MultiSurface` → `gml:surfaceMember` → `gml:Surface` → `gml:patches` → `gml:PolygonPatch` → `gml:exterior`/`gml:interior` → `gml:LinearRing` → `gml:posList srsDimension="2" count="N"` |
| `gml:id` de geometría | `MultiSurface_ES.<ns>.CP.<id>`, `Surface_ES.<ns>.CP.<id>.1`, `ReferencePoint_ES.<ns>.CP.<id>` |
| `srsName` (v4) | `http://www.opengis.net/def/crs/EPSG/0/<código>` en todos los elementos geométricos, coherente |
| `count` | Nº de vértices **incluido** el último repetido |
| Coordenadas | Metros, **2 decimales**, separador decimal punto, X Y separadas por espacio |
| Anillos | Cerrados (último = primero), mínimo 4 vértices; **exterior en sentido horario, interiores antihorario** |
| `inspireId` | `<Identifier xmlns="http://inspire.ec.europa.eu/schemas/base/3.3"><localId>…</localId><namespace>ES.SDGC.CP | ES.LOCAL.CP</namespace></Identifier>` |
| `cp:label` | Número de parcela visible en la cartografía (2 dígitos urbana, hasta 5 rústica) |
| `cp:nationalCadastralReference` | Referencia catastral (o el localId) |
| `cp:referencePoint` | `gml:Point` con `gml:pos`: punto **interior** del recinto (no basta el centroide si cae fuera) |

**SRC admitidos por la SEC:** EPSG:25829, 25830, 25831 (ETRS89 UTM 29/30/31) y EPSG:32628 (WGS84 UTM 28, Canarias). Pendiente de confirmar si la SEC acepta también 4083 (REGCAN95 UTM 28) → **E-03** en la lista de errores conocidos.

### 1.2 Identificadores según la alteración

| Alteración | Parcela(s) aportada(s) | localId / namespace |
|---|---|---|
| Segregación | Resto de la matriz | RC original / `ES.SDGC.CP` |
| | Segregadas | p. ej. `Seg_1` / `ES.LOCAL.CP` |
| División | Todas | p. ej. `Div_1_1` / `ES.LOCAL.CP` |
| Agregación | Resultante | RC de la parcela principal / `ES.SDGC.CP` |
| Agrupación | Resultante | p. ej. `Agrupa_1_2_3` / `ES.LOCAL.CP` |
| Subsanación | Todas | RC original / `ES.SDGC.CP` (excepciones: dominio público) |

Tabla de decisión de la SEC (NPO = parcelas de origen, NPP = parcelas aportadas):

| NPO | NPP | Namespace | Alteraciones posibles |
|---|---|---|---|
| 1 | >1 | 1 SDGC | Segregación · Subsanación |
| 1 | >1 | 0 SDGC | División |
| 1 | >1 | ≥2 SDGC | No permitido |
| >1 | 1 | 1 SDGC | Agregación · Subsanación |
| >1 | 1 | 1 LOCAL | Agrupación |
| = NPP | | Todos SDGC | Subsanación |
| = NPP | | Alguno LOCAL | Subsanación o reparcelación |
| ≠ NPP (y ni 1 ni 2) | | | Subsanación o reparcelación |

### 1.3 Comprobaciones conocidas de la SEC (IVGA)
- Estructura del GML válida; esquema 4.0.
- Sin solapes entre parcelas aportadas.
- Error si una parcela aportada es **idéntica** a su parcela catastral de origen (no hay cambio).
- El **contorno conjunto** de las aportadas debe coincidir con el de las parcelas de origen (si no, positivo solo condicionado por afección a dominio público).
- Limitaciones de tramitación automática: parcelas sin expedientes abiertos; relación ancho/alto ≤ 15; mismo municipio, polígono/manzana y naturaleza (urbana/rústica); máx. 30 parcelas resultantes de una o 30 a unir.
- Tolerancias (Resolución conjunta DGSJFP-DGC, BOE-A-2020-12111, anexo II): ±0,50 m en urbana, ±2,00 m en rústica, y diferencia de superficie ≤ 5 %.

### 1.3 bis Reglas del documento de preguntas frecuentes de coordinación Catastro-Registro (DGC, material del curso, Tema 8)
- **Tolerancia del contorno:** el conjunto de parcelas resultantes debe coincidir con el de las parcelas catastrales de origen con una tolerancia en sus vértices de **±1 cm**.
- **Topología:** recintos sin autointersecciones, con huecos permitidos; los objetos adyacentes no pueden superponerse ni dejar huecos. **Fincas discontinuas:** una representación por cada porción (no parcelas multiparte).
- **Curvas:** se sustituyen por vértices con flecha < 2 cm. Distancia recomendada entre puntos según el radio: 1 m → 0,3 m · 2 m → 0,5 m · 3 m → 0,7 m · 4 m → 0,8 m · 5–15 m → 1,0 m · 16–24 m → 1,5 m · 25–60 m → 2,0 m · > 60 m → 3,0 m.
- **Sistema:** ETRS89 (REGCAN95 en Canarias) en proyección UTM. La conformidad con el esquema XSD es imprescindible: un GML mal formado ni siquiera lo lee el validador de la Sede.
- **SRC por provincia** (para proponer el huso por defecto y avisar si no encaja):

| EPSG | Provincias |
|---|---|
| 25829 | Coruña, Huelva, Lugo, Ourense, Pontevedra |
| 25829 o 25830 | Badajoz, Cáceres, Cádiz, León, Oviedo (Asturias), Salamanca, Sevilla, Zamora |
| 25830 | Albacete, Almería, Ávila, Burgos, Cantabria, Ceuta, Ciudad Real, Córdoba, Cuenca, Granada, Guadalajara, Jaén, La Rioja, Madrid, **Málaga**, Murcia, Palencia, Segovia, Soria, Toledo, Valencia, Valladolid |
| 25830 o 25831 | Alicante, Castellón, Huesca, Teruel, Zaragoza |
| 25831 | Baleares, Barcelona, Lleida, Tarragona |
| 32628 | S.C. de Tenerife (Las Palmas no aparece en la tabla del documento por un salto de página: se supone 32628; Melilla, 25830; se confirmará) |

Navarra no aparece en el material del curso: su investigación sigue pendiente (mejora 30).

### 1.4 Diferencias 3.0 → 4.0 (para el conversor)
| | 3.0 | 4.0 |
|---|---|---|
| Raíz | `gml:FeatureCollection gml:id="ES.SDGC.CP"` | `FeatureCollection` (wfs 2.0) |
| `cp` | `urn:x-inspire:specification:gmlas:CadastralParcels:3.0` | `http://inspire.ec.europa.eu/schemas/cp/4.0` |
| Contenedor | `gml:featureMember` | `member` |
| `gml:boundedBy` | Sí | Se elimina |
| Identifier | `base:Identifier` (`urn:x-inspire:specification:gmlas:BaseTypes:3.2`) | `Identifier` (`http://inspire.ec.europa.eu/schemas/base/3.3`) |
| srsName | `urn:ogc:def:crs:EPSG::25830` | `http://www.opengis.net/def/crs/EPSG/0/25830` |
| Elementos | `cp:validFrom`, `cp:validTo`, `cp:zoning` | Desaparecen |
| nilReason | `other:unpopulated` | `http://inspire.ec.europa.eu/codelist/VoidReasonValue/Unpopulated` |

---

## 2. GML de edificio (ICUC)

**Norma de base:** INSPIRE Buildings, esquema **BuildingExtended2D 2.0** con modificaciones locales de la DGC (copia en `https://www.catastro.hacienda.gob.es/ws/esquemas/GML/inspire.ec.europa.eu/draft-schemas/bu-ext2d/2.0/BuildingExtended2D.xsd`).

| Elemento | Valor / regla |
|---|---|
| Cabecera | `<?xml version="1.0" encoding="ISO-8859-1"?>` |
| Raíz | `gml:FeatureCollection gml:id="ES.LOCAL.BU"` con `gml:featureMember` |
| Espacios de nombres clave | `gml/3.2` · `bu-ext2d=http://inspire.jrc.ec.europa.eu/schemas/bu-ext2d/2.0` · `bu-core2d=http://inspire.jrc.ec.europa.eu/schemas/bu-core2d/2.0` · `base=urn:x-inspire:specification:gmlas:BaseTypes:3.2` |
| schemaLocation | `http://inspire.jrc.ec.europa.eu/schemas/bu-ext2d/2.0 http://inspire.ec.europa.eu/draft-schemas/bu-ext2d/2.0/BuildingExtended2D.xsd` |
| Edificio | `bu-ext2d:Building`: `beginLifespanVersion` → `conditionOfConstruction` (declined, demolished, functional, projected, ruin, underConstruction) → `inspireId` → `geometry` (`bu-core2d:BuildingGeometry` con `gml:Surface` y uno o varios `gml:PolygonPatch`, `horizontalGeometryEstimatedAccuracy uom="m"`, `horizontalGeometryReference`=`footPrint`, `referenceGeometry`=`true`) → `numberOfFloorsAboveGround` |
| Otras construcciones | `bu-ext2d:OtherConstruction` con `conditionOfConstruction xsi:nil="true" nilReason="other:unpopulated"`, `constructionNature`=`openAirPool` (piscinas) y geometría `gml:Polygon` |
| localId | RC de la parcela; si hay varias construcciones, sufijos (p. ej. `_PI.1` para piscinas) |
| namespace | `ES.SDGC.BU` o `ES.LOCAL.BU` |
| srsName | `urn:ogc:def:crs:EPSG::<código>` |
| SRC | 25829, 25830, 25831, 32628 |
| Coordenadas | 2 decimales; anillos cerrados; exterior horario, interiores antihorario; sin autointersecciones |
| Huella | Contorno a nivel del suelo, sin vuelos, terrazas ni balcones |

**Comprobaciones conocidas del ICUC:** máx. **60 ficheros** por solicitud, sin nombres repetidos; identificadores no vacíos ni repetidos; huso obligatorio e igual en todas las geometrías; geometrías no vacías, cerradas, con ≥4 puntos de 2 coordenadas; sin superposición entre construcciones; distancia máxima a la parcela **100 m**; parcelas BICE excluidas. El ICUC no admite aportar geometría de parcela: se trabaja con la parcela catastral vigente (por RC).

---

## 3. Servicios del Catastro

| Servicio | URL | Uso en el plugin |
|---|---|---|
| WFS INSPIRE Parcelas (2.0, GML 3.2.1) | `http://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx` | `GetParcel` (REFCAT), `GetNeighbourParcel` (REFCAT), `GetZoning` / `GetParcelsByZoning` (COD_ZONA); BBOX ≤ 1 km² y 5.000 elementos |
| WFS INSPIRE Edificios | `http://ovc.catastro.meh.es/INSPIRE/wfsBU.aspx` | `GetBuildingByParcel`, `GetBuildingPartByParcel`, `GetOtherBuildingByParcel` (REFCAT); BBOX ≤ 4 km² y 5.000 elementos |
| ATOM (descarga por municipio) | `…/INSPIRE/CadastralParcels/ES.SDGC.CP.atom.xml` (y BU, AD) | **No** se usará (ya lo cubre Spanish Inspire Catastral Downloader) |
| Servicios web libres (WCF, SOAP/REST, v2.6 de 01/12/2025) | `http://ovc.catastro.meh.es/OVCServWeb/OVCWcfCallejero/COVCCoordenadas.svc` y `COVCCallejero.svc` | `Consulta_RCCOOR` (RC por coordenadas, para clic en el mapa), `Consulta_CPMRC` (coordenadas por RC), `Consulta_DNPRC` (datos no protegidos: uso, superficie… nunca titular ni valor) |

SRC de los WFS: 4326, 4258, 25829, 25830, 25831, 3785, 3857. **No incluyen 32628** → para Canarias se pedirá en 4258 y se transformará en QGIS (E-02).

### 3.1 Territorios con catastro propio

El plugin es solo para España, pero no todo el territorio lo gestiona la DGC:

| Territorio | Organismo | Qué sabemos | Qué falta |
|---|---|---|---|
| **Navarra** (provincia 31) | Servicio de Riqueza Territorial y Tributos Patrimoniales (Registro de la Riqueza Territorial, Ley Foral 12/2006) | Cartografía catastral pública en IDENA (descarga en Shapefile y GeoPackage, EPSG:25830). La coordinación con el Registro se hace con **cédulas parcelarias**, no con el IVGA de la Sede de la DGC | Formato GML que admite el RRTN (si lo hay) y su servicio WFS de parcelas; condiciones de uso de IDENA. Se investigará en la fase 6 (mejora 30), también en la carpeta del curso de gestión catastral |
| **Álava/Araba** (01), **Gipuzkoa** (20), **Bizkaia** (48) | Diputaciones forales | Catastros propios, con sus servicios | Solo se detectan y se avisa (mejora 31) |

Consecuencia: los GML para la Sede de la DGC **no sirven** en estos territorios; el plugin lo detectará (por municipio o por posición) y avisará antes de generar nada.

---

## 4. Condiciones de uso de los datos

- **Licencia INSPIRE de la DGC (v1.0, julio 2016)** y **Licencia de descarga de productos catastrales**: se permite el uso, incluido el comercial, de la información **transformada**; no se permite difundir la información original sin transformar; los productos derivados **no pueden presentarse como "cartografía catastral" o "información catastral"** ni suplantar los servicios de la DGC; la DGC no responde de los productos del usuario.
- Cita obligatoria de la fuente: «Dirección General del Catastro» y fecha de acceso.
- Datos protegidos (titularidad, valor catastral): fuera del plugin. Los servicios libres ya los excluyen.

**Consecuencias para el plugin:**
1. Descarga **puntual** a petición del usuario (por RC o clic), nunca masiva ni en caché redistribuible.
2. Las capas descargadas llevan en sus metadatos/atribución «Fuente: Dirección General del Catastro · fecha».
3. El plugin no incluye datos del Catastro en su ZIP; los datos de prueba de `tests/data` son **inventados** (coordenadas sintéticas) o generados por nosotros.
4. Nombre, icono y textos sin «Catastro» como marca, sin escudos ni logotipos, y aviso visible: «Herramienta no oficial. Valide siempre el resultado en la Sede Electrónica del Catastro».

---

## 5. Plugins y webs de referencia: licencias

Nota: Check4SEC no venía en tu lista de enlaces, pero sí en los adjuntos; lo incluyo.


| Nombre | Autor | Licencia | Qué hace | Qué se puede reutilizar | Qué no |
|---|---|---|---|---|---|
| **Check4SEC** (RAR adjunto) | Laura García de Marina (Unidad de Cartografía Catastral, DGC) | **GPL-3.0** (LICENSE). Declara código derivado de ParCatGML (GPL-3) | Simula las validaciones de la SEC (IVGA e ICUC), genera GML CP 4.0 y BU | Ideas y el flujo de comprobaciones (son reglas públicas de la SEC). Código: solo si aceptamos pasar a GPL-3 | Iconos/PNG, escudos y textos del manual; el código si mantenemos GPL-2.0-or-later |
| **ParCatGML** | Pep Vallory, David Erill, Carlos López Quintanilla (PSIG) | **GPL-3.0** | Genera GML de parcela desde QGIS | Idea | Código (misma razón), iconos |
| **Parcel-o-rama** | Daniel Ibarra Marinas | **GPL-2.0-or-later** | 7 herramientas de corte: split, equal, percent, strip, perpendicular, pivot, boundary | **Código reutilizable** conservando copyright, cabecera y CREDITS.md (aunque preferimos reescribir) | Iconos y textos (salvo que tengan la misma licencia y se citen) |
| **Cadastral_Divisions (Frazionamenti)** | Korto19 | **CC-BY-4.0** | División por partes iguales, fracción o superficie objetivo (bisección) | Solo la idea (el método de bisección es matemática general) | Código: CC-BY-4.0 no es compatible con GPL-2 |
| **RFCL-PolygonDivider** | Jonathan Huck | **GPL-3.0** | Divide polígonos en piezas "cuadradas" de superficie dada (método de Brent) | Idea y algoritmo general | Código (GPL-3) |
| **SEC4QGIS** | Andrés V. O. | **GPL-3.0-or-later** (cabecera); última versión para QGIS 2.x | Importa FXCC/DXF/GML, edita y exporta GML INSPIRE para IVGA | Idea (importar FXCC/DXF) | Código (GPL-3, y además API de QGIS 2) |
| **gmlweb.com** | Javier Sarralde Fernández (© gmlweb.com) | **Propietaria** (web comercial, sin licencia de reutilización) | GML Parcela, GML Edificio, Multiparcelas, Unión, GMLv3v4, Visor, informe de coordenadas | **Solo la idea de funcionalidad**, implementada desde la documentación oficial | Todo: código, textos, nombres de herramientas, diseño, iconos. No se hace scraping |
| **Spanish Inspire Catastral Downloader** | Patricio Soriano | GPL (por confirmar) | Descarga masiva ATOM/WFS | — | No duplicamos su función |

**Aviso importante sobre GPL-3:** el código GPL-3 (Check4SEC, ParCatGML, PolygonDivider, SEC4QGIS) **no se puede incorporar** a un plugin GPL-2.0-or-later sin que el conjunto pase a ser GPL-3. Decisión propuesta: **no copiar código de ninguno de ellos**; escribir todo desde la documentación oficial. Lo único reutilizable sin cambiar la licencia es Parcel-o-rama (GPL-2.0-or-later), y aun así lo reescribiremos.

Pendiente: revisar las cabeceras de cada repositorio cuando los clone (la licencia de Parcel-o-rama y la del Downloader se confirmarán leyendo los ficheros, no solo el resumen de GitHub).

---

## 6. Fuentes
- Formato GML de parcela catastral (DGC): https://www.catastro.hacienda.gob.es/documentos/formatos_intercambio/Formato%20GML%20parcela%20catastral.pdf
- Fichero GML coordinación Catastro-Registro (DGC): https://www.catastro.hacienda.gob.es/asistente_catreg/img/GML.pdf
- IVGA (DGC): https://www.catastro.hacienda.gob.es/asistente_catreg/img/IVGA.pdf
- Formato GML de edificio (DGC): https://www.catastro.hacienda.gob.es/documentos/formatos_intercambio/Formato%20GML%20edificio.pdf
- Ayuda ICUC: https://www.catastro.hacienda.gob.es/ayuda/vga/ayuda_ICUC.htm
- Diferencias esquemas 3.0 y 4.0: https://www.idee.es/resources/documentos/blog/Diferencias_GML_parcela_3_4.pdf
- Limitación al esquema 4.0 (blog IDEE): https://blog-idee.blogspot.com/2025/01/limitacion-de-archivos-gml-de-parcela.html
- WFS CP: https://www.catastro.hacienda.gob.es/webinspire/documentos/inspire-cp-WFS.pdf · WFS BU: https://www.catastro.hacienda.gob.es/webinspire/documentos/inspire-bu-wfs.pdf
- Servicios web libres v2.6: https://www.catastro.hacienda.gob.es/ws/Webservices_Libres.pdf
- Licencia INSPIRE DGC: https://www.catastro.hacienda.gob.es/webinspire/documentos/Licencia.pdf · Licencia de descarga: https://www.catastro.hacienda.gob.es/pdf/ovc/licdescargaES.pdf
- Resolución conjunta DGSJFP-DGC (BOE-A-2020-12111): https://www.boe.es/diario_boe/txt.php?id=BOE-A-2020-12111
- Manual de Check4SEC (adjunto) y código de Check4SEC v2.0 (adjunto)
- Curso de gestión catastral (material del tutor): Tema 3 «Servicios en internet del Catastro español» (v2026), Tema 8 «La coordinación Catastro-Registro de la Propiedad» (v2025) y «Preguntas y respuestas acerca de la coordinación Catastro-Registro» (DGC)
