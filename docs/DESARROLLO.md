# Catastral GML Tools · Plan de desarrollo

> Repositorio `FGomezLosada/CatastralGMLTools` · carpeta local `C:\Users\Usuario\Documents\dev\CatastralGMLTools` · carpeta del plugin en QGIS `catastral_gml_tools`.
> Herramientas para preparar, revisar y validar ficheros GML de parcela y de edificio para la Sede Electrónica del Catastro.
> Licencia: GPL-2.0-or-later. Compatibilidad: QGIS 3.34+ y 4.x (Qt5/Qt6).
> Herramienta **no oficial**: el resultado debe validarse siempre en la Sede Electrónica del Catastro.

Datos técnicos y licencias de terceros: ver [`INVESTIGACION.md`](INVESTIGACION.md).

---

## 1. Alcance

**Dentro**
- Crear GML de parcela (CP 4.0) desde una capa: una o varias parcelas por fichero, con localId/namespace según la alteración.
- Crear GML de edificio (BU ext2D 2.0): edificios y otras construcciones (piscinas).
- Abrir y revisar GML (v3, v4 y edificio) en QGIS.
- Validar un GML antes de subirlo: estructura, esquema, geometría y reglas conocidas de la SEC.
- Convertir GML de parcela 3.0 → 4.0 y reparar errores habituales.
- Unir varios GML de parcela en uno (multiparcela) y disolver parcelas (unión para agregación/agrupación).
- Descarga **puntual** por referencia catastral: la parcela, sus colindantes y sus construcciones. RC por clic en el mapa.
- Dividir parcelas: superficie objetivo, partes iguales, porcentaje, franja paralela, pivote.
- Asistente de alteraciones (segregación, división, agregación, agrupación, subsanación) que propone identificadores y comprueba NPO/NPP.
- Informe de superficies y coordenadas (HTML/CSV).
- Algoritmos de Processing para usar las herramientas en modelos y por lotes.

**Fuera**
- Descarga masiva (ATOM/municipio): ya la cubre *Spanish Inspire Catastral Downloader*.
- Datos protegidos (titulares, valores).
- Territorios con catastro propio: **Navarra** se estudia aparte (mejora 30) y se incorporará lo que su catastro admita; **País Vasco**, solo detección y aviso (mejora 31).
- Envío a la Sede: el plugin prepara el fichero; el trámite se hace en la Sede.

---

## 2. Arquitectura

```
CatastralGMLTools/                       (raíz del repositorio = carpeta del plugin)
├── __init__.py
├── metadata.txt                         (descripción en inglés, supportsQt6=True)
├── catastral_gml_tools.py               (initGui/unload, botón, menú Vectorial, proveedor Processing)
├── catastral_gml_tools_dockwidget.py / _base.ui  (panel: Parcela · Edificio · Validar · Descargar · Dividir · Utilidades)
├── icon.svg / icon.png
├── core/                                (sin interfaz; probado de forma aislada)
│   ├── info.py                          (nombre, versión, aviso legal, fuente, territorios forales)
│   ├── refcat.py                (formato y dígitos de control de la RC)
│   ├── geometria.py             (cierre, orientación, redondeo a 2 decimales, punto interior, área, limpieza)
│   ├── gml_parcela.py           (escritor CP 4.0)
│   ├── gml_edificio.py          (escritor BU ext2D 2.0)
│   ├── gml_lector.py            (lector CP 3.0/4.0 y BU → objetos propios → capa QGIS)
│   ├── conversor.py             (3.0 → 4.0 y reparaciones)
│   ├── validador.py             (reglas → lista de incidencias con nivel, código y mensaje)
│   ├── alteraciones.py          (NPO/NPP/namespace → alteraciones posibles; propuesta de localId)
│   ├── division.py              (algoritmos de división)
│   ├── servicios.py             (WFS CP/BU, Consulta_RCCOOR, Consulta_CPMRC; red de QGIS)
│   └── informe.py               (informe HTML/CSV)
├── processing/                  (proveedor y algoritmos que llaman a core/)
├── tareas.py                    (QgsTask para descargas, validación y división)
├── i18n/                        (es, en)
├── help/                        (ayuda HTML local)
├── tests/   tools/   docs/
└── .github/                     (Action de publicación y plantillas de issues)
```

Decisiones técnicas:
- **XML con `xml.etree.ElementTree`** (biblioteca estándar) para escribir y leer; validación XSD con `lxml` solo si está disponible y con los esquemas descargados bajo demanda a una caché del usuario (no se empaquetan). Sin `lxml`, la validación estructural propia sigue funcionando.
- **Red con `QgsBlockingNetworkRequest`** dentro de `QgsTask`: respeta el proxy y la autenticación configurados en QGIS.
- **Geometría con `QgsGeometry`**: orientación con `forceRHR()`/inversión controlada, punto interior con `pointOnSurface()`, validez con `isGeosValid()`.
- Todos los mensajes al usuario en una `QgsMessageBar` dentro del panel; nada de `QMessageBox`.

---

## 3. Fases

| Fase | Contenido | Estado |
|---|---|---|
| 0 | Investigación, licencias, alcance, nombre y arquitectura | ✅ |
| 1 | Esqueleto: estructura, metadata, panel vacío, icono, ayuda, infraestructura de pruebas, empaquetado, plantillas de GitHub | ✅ (0.1.0) |
| 2 | Núcleo: RC y geometría | ✅ |
| 3 | GML de parcela (crear) | ✅ |
| 4 | Lector y visor de GML | ✅ |
| 5 | Validador e informe | ✅ |
| 6 | Servicios: descarga por RC y RC por clic; Navarra y territorios forales | ✅ |
| 7 | Alteraciones: asistente, multiparcela y unión | ✅ |
| 8 | GML de edificio y comprobaciones ICUC | — |
| 9 | Conversor 3.0 → 4.0 y reparación | — |
| 10 | División de parcelas | — |
| 11 | Informe de superficies y coordenadas | — |
| 12 | Processing | — |
| 13 | Documentación, capturas, traducción, ZIP para compañeros y publicación estable | — |

---

## 4. Mejoras

| Nº | Mejora | Motivo | Hecha |
|---|---|---|---|
| 1 | Estructura del repositorio, LICENSE, README bilingüe, CHANGELOG, CREDITS, .gitattributes, .gitignore | Base del proyecto | ✅ |
| 2 | `metadata.txt`, carga/descarga limpia del plugin, panel con pestañas, barra de mensajes, aviso legal, ayuda local e icono propio | Esqueleto que funcione en 3.40 y 4.x | ✅ |
| 3 | `tools/run_tests.py`, `tools/probar.bat`, `tools/package.py` | Pruebas en las dos versiones y ZIP limpio | ✅ |
| 4 | Action de publicación por etiqueta y plantillas de issues (`para_github/` si hace falta) | Publicación reproducible | ✅ |
| 5 | `core/refcat.py`: validar RC de 14/18/20 caracteres y dígitos de control | Evitar RC mal escritas | ✅ |
| 6 | `core/geometria.py`: cierre, orientación, 2 decimales, vértices duplicados, punto interior, área redondeada, curvas densificadas con flecha < 2 cm, huso propuesto según la provincia | Reglas de geometría del Catastro | ✅ |
| 7 | Escritor GML de parcela CP 4.0 (una o varias parcelas, un recinto por parcela) | Función central | ✅ |
| 8 | Pestaña Parcela: elegir capa, campos de RC/localId/label, namespace por fila, fecha, SRC, destino | Generar el GML desde una capa dibujada | ✅ |
| 9 | Lector de GML (CP 3.0/4.0, BU) y carga como capa con estilo | Revisar ficheros propios o ajenos | ✅ |
| 10 | Validador: estructura, esquema, coherencia de ids, `count`, `areaValue`, orientación, cierre, solapes, multiparte, SRC | Detectar errores antes de subir | ✅ |
| 11 | Informe de validación en el panel con botón para abrir el informe HTML y el fichero | Resultado claro | ✅ |
| 12 | Descarga por RC: parcela, colindantes y construcciones (WFS) con atribución a la DGC | Partir de la cartografía vigente | ✅ |
| 13 | RC por clic en el mapa (Consulta_RCCOOR) | Comodidad | ✅ |
| 14 | Comparación con la parcela de origen: parcelas sin cambios, contorno total (tolerancia ±1 cm en vértices: «IVG positivo cuando el contorno exterior resultante sea igual al original»), parcelas afectadas total o parcialmente (parcial → negativo), NPO, que las RC SDGC existan en el Catastro; avisos de tramitación no automática (esbeltez >15, distinto municipio, polígono o manzana, urbana y rústica mezcladas, diseminado, >30 parcelas por operación); dominio público catastrado afectado: debe ir en el GML delimitando la parte afectada (FAQ DGC); viales urbanos sin parcela: IVG negativo salvo cesión/incorporación con parcela LOCAL; avisar si la nueva geometría ocupa suelo sin parcela (vía pública) o parcelas no incluidas en el GML, o mueve un lindero con dominio público (con superficie en m² y zona en el mapa) | Simular comprobaciones de la SEC | ✅ |
| 15 | Asistente de alteraciones: desplegable «Tipo de alteración» (segregación, división, agregación, agrupación, subsanación; umbrales del Reglamento Hipotecario como aviso: segregada <20 % de la matriz, resultantes de división y fincas agrupadas >1/5, agregación: principal ≥80 % según el documento de validación de la DGC o quíntuplo según el editor — E-17) que pone identificadores (`Seg_`, `Div_`, `Agrupa_`) y namespaces y comprueba la tabla NPO/NPP/namespace de la Sede. Mientras tanto, las parcelas nuevas se proponen como `Nueva_N` | Evitar errores de identificadores sin presuponer la alteración | ✅ |
| 16 | Multiparcela: unir varios GML en uno | Equivalente a "multiparcela" | ✅ |
| 17 | Unión/disolución de parcelas seleccionadas en una sola | Agregación y agrupación | ✅ |
| 18 | Escritor GML de edificio (Building y OtherConstruction; ver INVESTIGACION §7.2: varios PolygonPatch por edificio, piscina con un Polygon, `conditionOfConstruction`, `numberOfFloorsAboveGround` máximo) | GML para el ICUC | |
| 19 | Pestaña Edificio: capa de huellas, tipo, plantas, estado, RC de parcela | Generar el GML de edificio | |
| 20 | Comprobaciones ICUC: dentro de la parcela, ≤100 m, sin solapes, ids, nº de ficheros | Simular el ICUC | |
| 21 | Conversor 3.0 → 4.0 y reparaciones (cierre, orientación, `count`, `areaValue`, srsName; lista de cambios del documento «Diferencias GML parcela v3 v4» de la DGC en INVESTIGACION §7.3) | Aprovechar ficheros antiguos | |
| 22 | División: superficie objetivo, partes iguales, porcentaje | Segregaciones y divisiones | |
| 23 | División: franja de ancho fijo, línea paralela/perpendicular a un lado, pivote | Casos reales de campo | |
| 24 | Ajuste de lindero entre dos parcelas colindantes manteniendo el contorno | Subsanaciones | |
| 25 | Informe de superficies y coordenadas (HTML/CSV), con superficie gráfica y diferencia con la catastral | Documentación técnica | |
| 26 | Proveedor de Processing con los algoritmos principales | Modelos y lotes | |
| 27 | Traducción al inglés (Qt Linguist) | Publicación internacional | |
| 28 | Manual de usuario detallado en la ayuda local (help/), una sección por pestaña y por operación (segregación, división, agregación, agrupación, subsanación, comparación, descarga, Navarra), con capturas reales hechas en QGIS 3.40 y 4.x con datos públicos; también en PDF para compañeros. Se hace al final, con la interfaz ya cerrada, para que las capturas no queden viejas | Uso sin conexión y formación | |
| 29 | README con capturas reales, ZIP de prueba y publicación estable (`experimental=False` en 1.0.0) | Cierre | |
| 30 | Navarra: investigar el formato y los servicios del Registro de la Riqueza Territorial (IDENA) e incorporar lo que admita (descarga y GML) | El plugin es para toda España | ✅ |
| 32 | Lector del XML del informe de validación gráfica (IVG): cargar en QGIS las parcelas propuestas y las afectadas total y parcialmente (`parcelasGML`, `parcelasAfecT`, `parcelasAfectP`, ZIP en base64) | Revisar un IVG negativo sobre el mapa | |
| 33 | Exportar los vértices como puntos de apoyo para el editor parcelario de la Sede (.txt «x y» por línea) | Usar el editor en línea con datos de campo | |
| 31 | Detección de territorios con catastro propio (Navarra, Álava/Araba, Gipuzkoa, Bizkaia) con aviso antes de generar GML para la Sede de la DGC | Evitar ficheros que no sirven | ✅ |

---

## 5. Entorno de pruebas

- **Windows** (tu PC) con QGIS 3.40.13 LTR (`C:\Program Files\QGIS 3.40.13`) y QGIS 4.2.2 (`C:\Program Files\QGIS 4.2.2`).
- `tools/run_tests.py`: cada prueba en un proceso propio, QGIS sin ventana (`qgis.testing.start_app`, iface simulada, `QT_QPA_PLATFORM=offscreen`).
- `tools/probar.bat`: lanza las pruebas con las dos versiones; con `PB_SIN_PAUSA` definida no hace pausa. Resultados en `tests/resultados_qgis<versión>.txt`.
- `tests/data/`: GML de ejemplo **propios y sintéticos** (válidos e inválidos: anillo abierto, orientación invertida, `count` erróneo, multiparte, esquema 3.0, SRC no admitido, ids repetidos…). Nada copiado de terceros ni descargado del Catastro.
- Las pruebas de red (WFS) se marcan aparte y se pueden saltar sin conexión.
- Si QGIS está abierto con el complemento MCP, se lanzan pruebas también desde ahí.
- En mi espacio de trabajo (Linux) las pruebas se lanzan además con **QGIS 3.34** (la versión mínima), sin ventana. QGIS 4 solo se prueba en tu PC.

---

## 6. Errores conocidos y puntos por confirmar

| Nº | Descripción | Estado |
|---|---|---|
| E-01 | Los servicios del Catastro se publican en `http://`; comprobar si responden por `https://` y usarlo si es así | Resuelto: los servicios libres y los WFS INSPIRE (CP y BU) responden por `https://` (comprobado el 06 y el 07/10/2026). El plugin solo usa `https://` |
| E-02 | Se temía que los WFS no ofrecieran EPSG:32628 (Canarias) | Resuelto: el WFS de parcelas reproyecta a cualquier SRC pedido, también 32628 (07/10/2026). El plugin pide la parcela en el huso 30 y, si su posición corresponde a otro huso (o a Canarias), la vuelve a pedir en el suyo; todo lo demás se pide en ese huso. Ojo: en EPSG:4258/4326 devuelve lat-lon, por eso se pide siempre en UTM |
| E-03 | Confirmar si la SEC acepta EPSG:4083 (REGCAN95 UTM 28) además de 32628 | Por confirmar |
| E-04 | El GML de parcela usa UTF-8 y el de edificio ISO-8859-1 según los documentos oficiales; mantener cada uno | Decisión |
| E-05 | El esquema BU de la DGC es un borrador modificado localmente; la validación XSD de edificios debe usar la copia de la DGC | Por resolver (fase 8) |
| E-06 | Las reglas de la SEC no están publicadas de forma completa: el validador avisa de lo conocido y siempre remite a la Sede | Limitación asumida |
| E-07 | `metadata.txt` lleva `experimental=True` durante el desarrollo; se cambia a `False` en la 1.0.0, que será la primera que se suba a plugins.qgis.org | Decisión |
| E-09 | QGIS 4.2.2 no abría el panel: el uic de PyQt6 genera `QSpacerItem(Policy, Policy)` para los espaciadores del .ui sin `sizeHint`. Todos los espaciadores llevan ahora `sizeHint` y `package_test.py` lo comprueba en cualquier versión | Resuelto (0.1.0) |
| E-10 | libxml2 (lxml) no descarga por https ni sigue redirecciones: si no encuentra un esquema importado, **valida sin comprobar nada y da «válido»**. El validador XSD (mejora 10) descargará los esquemas con la red de QGIS (`QgsBlockingNetworkRequest` con redirecciones), los guardará en una caché del perfil y avisará si falta alguno. Comprobado el 06/10/2026: el GML de `gml_parcela.py` es válido contra WFS 2.0 + CP 4.0 (81 esquemas) y un fichero alterado se rechaza | Decisión (mejora 10) |
| E-11 | La Sede rechazaba nuestro GML de parcela («no cumple el esquema Inspire GML») aunque era válido contra los XSD públicos. Con 9 ficheros de control subidos a la Sede (06/10/2026) se aisló la causa: **la raíz debe declarar `xmlns:xlink`** aunque no se use. No influyen la codificación (UTF-8 o ISO-8859-1), los saltos de línea, la sangría, `count`, la fecha, el punto de referencia ni el formato de las coordenadas. `gml_parcela.py` declara xlink y la prueba lo comprueba | Resuelto |
| E-12 | Abrir el panel con una capa grande en el proyecto (p. ej. el municipio descargado) bloqueaba QGIS: la pestaña Parcela calculaba todas sus parcelas, y además 3 o 4 veces al rellenar los campos. Resuelto: capa activa por defecto, máximo de 100 parcelas en la tabla (se trabaja con la selección), señales bloqueadas al rellenar los campos. Prueba con 400 parcelas en `parcela_ui_test.py` | Resuelto |
| E-13 | `GetNeighbourParcel` a veces incluye la propia parcela entre las colindantes (p. ej. 9872023VH5797S) y otras no: `servicios.py` la quita siempre. `GetOtherBuildingByParcel` devuelve una colección vacía si no hay otras construcciones, y una RC inexistente devuelve un `ExceptionReport` (OWS 1.1) con el motivo, que se muestra al usuario | Resuelto |
| E-14 | `GetNeighbourParcel` no es fiable: para 1669001VF2616N (manzana entera, rodeada de calles) contesta «No se han encontrado parcelas colindantes», lo que es cierto, pero da un aviso que confunde, y en otros casos devuelve menos parcelas de las que hay. Las colindantes se calculan ahora por geometría: se piden al WFS las parcelas de un rectángulo 25 m mayor que la parcela (`GetFeature` con `bbox`, límite del servicio ~1 km²: «Area of extension out of limits») y se separan las que están a menos de 20 cm (colindantes) de las demás (entorno). Solo si la parcela es demasiado grande se usa `GetNeighbourParcel`. «Sin colindantes» es una nota, no un aviso | Resuelto |
| E-15 | Dominio público. Fuentes oficiales: (1) *Modelo de datos de cartografía vectorial (shapefile) v2.0* de la DGC: el campo TIPO de PARCELA distingue «(X) Dominio público y ajustes topográficos», y la parcela 09000 es un artificio de la cartografía rústica que debe ignorarse; (2) datos vigentes de Consulta_DNPRC (07/10/2026): las parcelas 9001-9999 de rústica de Nerja que lindan con las de prueba son «VT · Vía de comunicación de dominio público» (caminos, A-7) o «HG · Hidrografía natural» (arroyos, barrancos), y la 29075A90009700 es «(BIEN DE DOMINIO PUBLICO) ZONA MARITIMO TERRESTRE». El plugin no se fía solo de la numeración: consulta Consulta_DNPRC para cada colindante de rústica y cada 9000-9999 del entorno (máx. 60 por descarga) y marca dominio público si la DGC lo dice; si no responde, usa la numeración y lo indica como «sin confirmar». En urbana las calles no son parcelas (no tienen RC). Que la nueva geometría no invada vía pública sin parcela se comprobará en la mejora 14. Pendiente: si la DGC publica una lista oficial completa de clases de cultivo de dominio público, ampliar `CULTIVOS_DOMINIO_PUBLICO` (ahora VT y HG, las comprobadas) | Decisión |
| E-16 | Según el documento de validación de la DGC (IVG_Operaciones_Parcelario_GMLs, v2.3): la Sede **ya no compara `areaValue` con la geometría** (desde la v2.1) y, si hay más de 2 decimales, **solo tiene en cuenta los dos primeros** (trunca). El validador pasa SUP-DISTINTA a aviso; el escritor sigue poniendo la superficie de la geometría y 2 decimales | Resuelto |
| E-17 | Umbral de la agregación: la DGC da dos cifras distintas, 80 % de la resultante (documento de validación) y quíntuplo de las agregadas, ≈83,3 % (guía GML y editor). Solo serán avisos (mejora 15) | Por confirmar |
| E-18 | Navarra (07/10/2026): el Registro de la Riqueza Territorial publica parcelas y edificios en WFS INSPIRE (`inspire.navarra.es/services/CP/wfs` y `/BU/wfs`, CC BY 4.0, cita obligatoria «Servicio proporcionado por el Gobierno de Navarra»). Identificador de 9 dígitos, municipio (3) + polígono (2) + parcela (4), namespace `ES.RRTN.CP`; coordenadas con 3 decimales en EPSG:25830. La parcela se pide con un filtro FES `ResourceId` (`GetFeatureById` y `resourceId` dan error en ese servidor); Consulta_RCCOOR de la DGC devuelve en Navarra la referencia de 9 dígitos. No se ha encontrado un procedimiento equivalente al IVG ni un formato GML de alteraciones propio: el plugin descarga, pero no crea GML para Navarra (la pestaña Parcela lo impide con un aviso). País Vasco: solo se detecta | Decisión |
| E-19 | La guía GML de la DGC pone `beginLifespanVersion` como `AAAA-MM-DDT00:00:00` y dice que la fecha es de libre elección «siempre y cuando se respete el formato». Desde el 09/10/2026 el plugin escribe también la hora (al minuto). Comprobado en la Sede el 09/10/2026: segregación de 29075A00900138 con `2026-10-09T09:25:00` → validación positiva, operación «Segregación» | Resuelto |
| E-20 | Multiparcela con dos operaciones separadas (segregaciones de 1472010VF2617S y 29075A00900138 en un solo GML), subida a la Sede el 09/10/2026: validación positiva, 2 afectadas y 4 presentadas, pero «Tipo de operación: Seleccione operación» (no propone ninguna). El plugin avisa al unir zonas separadas (UNIR-SEPARADAS) | Comprobado |
| E-08 | El icono `mActionCheckGeometry.svg` no existe en QGIS 3.34: la pestaña Validar usa `algorithms/mAlgorithmCheckGeometry.svg` | Resuelto (0.1.0) |

---

## 7. Método

- Una mejora cada vez. Tras cada cambio: pruebas en 3.40 y 4.x, CHANGELOG y esta tabla actualizados, y mensaje de commit en español.
- Solo rama `main`. Comandos git para CMD, uno por bloque, empezando por `cd /d <carpeta>`.
- Reglas de estabilidad (lecciones de ProjectBuilder y de este plugin): todo espaciador de un .ui lleva `sizeHint` (PyQt6); no usar objetos de una copia temporal de QGIS (p. ej. `renderer().categories()[0].symbol()`: guardar antes la lista, si no, QGIS se cierra); colores con transparencia en formato «R,G,B,A», no `#RRGGBBAA`; señales a métodos (no lambdas); QTimer hijos del panel y comprobación `sip.isdeleted(self)`; todo widget con padre o referencia; sin `QTreeWidgetItemIterator`; enums con nombre completo y comparación explícita.
