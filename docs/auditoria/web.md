# Auditoría web de fuentes oficiales · Catastral GML Tools

> Fecha de la consulta: 09/10/2026. Solo fuentes oficiales: DGC, SEC, BOE, Gobierno de Navarra, diputaciones forales, IDEE y datos.gob.es, y plugins.qgis.org. Se usan además dos noticias colegiales, solo para fechar o localizar un documento oficial; se indica en cada caso.
> Marcas respecto a `docs/INVESTIGACION.md` (INV) y `docs/DESARROLLO.md` (DES): **[CONFIRMA]**, **[AMPLÍA]**, **[CONTRADICE/CORRIGE]**, **[NUEVO]**.
> Limitación del entorno: el proxy bloquea la descarga directa (curl) de catastro.hacienda.gob.es, sedecatastro.gob.es, ovc.catastro.meh.es, plugins.qgis.org, inspire.navarra.es y coamu.es. Todo se ha leído con WebFetch, que resume el contenido; las citas son literales pero breves. Algunas URL no se pudieron abrir (se indica). Los servicios en vivo (WFS, Consulta_*) no se han podido probar desde aquí.

---

## 1. Documentación técnica de la DGC/SEC

### 1.1 Documento de validación del IVG («Operaciones_Parcelario_GMLs»)
- URL: https://www.catastro.hacienda.gob.es/ayuda/Operaciones_Parcelario_GMLs.pdf (se enlaza desde ayuda_vga.htm).
- Título: «Informe de Validación Gráfica de la Sede Electrónica del Catastro. Guía para la elaboración de ficheros GML según las diferentes operaciones sobre el parcelario». Subdirección General de Tecnología y Despliegue Digital.
- **Versión vigente 2.3, de 20/09/2021.** No hay versión posterior publicada (2024-2026). Control de cambios: 1.0 (10/12/2020) · 2.0 (18/12/2020) · 2.1 (03/02/2021: «se elimina la validación de la etiqueta del área frente al área de la geometría») · 2.2 (01/03/2021) · 2.3 (20/09/2021: redacción del punto 4.1, namespace incorrecto). **[CONFIRMA]** E-16.
- Reglas: «Las coordenadas deberán estar definidas con dos decimales» (si hay más, solo cuentan los dos primeros). EPSG 25829, 25830, 25831 y 32628, el mismo en todo el fichero. Tabla NPO/NPP idéntica a INV §1.2. Tramitación automática: esbeltez ≤ 15, máximo 30 resultantes o 30 unidas, mismo municipio y polígono o manzana, misma naturaleza, sin diseminado y sin incidencias ni ediciones en avance. **[CONFIRMA]**
- Agregación: la principal debe tener **≥ 80 %** de la resultante (no menciona el quíntuplo). **[CONFIRMA]** E-17.

### 1.2 IVGA.pdf (asistente Catastro-Registro)
- URL: https://www.catastro.hacienda.gob.es/asistente_catreg/img/IVGA.pdf. **Sin versión ni fecha.** La norma más reciente que cita es la Resolución de 8/4/2021.
- Agregación: «la parcela receptora debe tener al menos cinco veces la superficie de la suma de las agregadas», con el mismo contorno exterior. Segregación: la superficie y el contorno totales deben coincidir.
- Causas de IVG negativo: no respetar la delimitación catastral (salvo afección de dominio público en zona urbana), GML no válido, combinaciones NPO/NPP/namespace no admitidas e incoherencia con la operación notarial, municipal o administrativa.
- **[AMPLÍA]** E-17. Dos documentos oficiales usan el **quíntuplo** (IVGA.pdf y GML.pdf, que dice «el quíntuplo de la suma de las que se agreguen»), y la ayuda del IVG lo atribuye al **art. 48 del Reglamento Hipotecario**. Solo el documento de validación v2.3 usa el 80 %. Las dos reglas no son equivalentes: la agregada ≤ 20 % de la resultante con el 80 %, y ≤ 16,67 % con el quíntuplo.

### 1.3 Ayuda del IVG (ayuda_vga.htm)
- URL: https://www.catastro.hacienda.gob.es/ayuda/vga/ayuda_vga.htm. Sin fecha ni versión.
- «A partir del 12 de marzo» no se certifican IVG negativos. **No indica el año.** Los negativos se pueden consultar, pero no tienen CSV. **[NUEVO]**
- Comprobaciones: validación sintáctica, `localId` no repetidos y ausencia de solapes en el parcelario aportado. **Si se indica `<cp:areaValue>`, debe coincidir con la superficie del polígono redondeada al m².** Esto **[CONTRADICE parcialmente]** E-16: la ayuda y el asistente (CdU_9, §6) mantienen la regla aunque el documento v2.3 la eliminó. Conclusión práctica: seguir escribiendo `areaValue` = área redondeada al m² (ya se hace) y mantener SUP-DISTINTA como **aviso fuerte**, no como información.
- Tipos de operación preseleccionados por superficie: Agregación/Segregación si la mayor supera «el quíntuplo» de la suma del resto (art. 48 RH); si no, Agrupación/División. Códigos en el XML del informe: **1 Agregación, 2 Agrupación, 3 Segregación, 4 División, 5 Subsanación de discrepancias, 6 Reparcelación**. Resultado: `<resultado>` 0/1. Esquema del informe: https://www.catastro.hacienda.gob.es/ws/esquemas/informeGrafAlt.xsd. **[NUEVO]**, útil para la mejora 32.
- Reglas de identificador: Agregación → `localId` = RC de la mayor y `ES.SDGC.CP`; Agrupación → `ES.LOCAL.CP`; Segregación → `localId` de la mayor = RC de la afectada y `ES.SDGC.CP`; División → `ES.LOCAL.CP`. **[CONFIRMA]**
- Desplazamiento (CX, CY o los 6 parámetros afines) también en el IVG. **[CONFIRMA]**
- Otros documentos enlazados: Circular de referencias catastrales (https://www.catastro.hacienda.gob.es/documentos/07042006.pdf) y ejemplo de IVG (https://www.catastro.hacienda.gob.es/ayuda/vga/Informe_4RNYQXDDY38G1QZA-MODIFICADO.PDF).

### 1.4 Novedades del IVG (novedades_vga.htm)
- URL: https://www.catastro.hacienda.gob.es/ayuda/novedades_vga.htm (sin fechas). **[NUEVO]**
- Novedades: identificadores cortos en el informe (1, 2, 3… para el nuevo parcelario; a, b… aa para el catastral), rótulo «Mantiene RC», linderos externos en rojo y **coordenadas fuera del PDF** (están en el GML).
- En los informes del editor de la SEC, **«el CSV y el tipo de operación se incluyen como comentario en el GML del nuevo parcelario»**. El lector de GML podría mostrarlo.

### 1.5 Esquema 3.0 → 4.0
- «Diferencias GML parcela 3 4» (IDEE): https://idee.es/resources/documentos/blog/Diferencias_GML_parcela_3_4.pdf. Fecha «Diciembre 2024» (timeStamp de ejemplo 2024-12-16), sin autor ni versión. Contenido **[CONFIRMA]** INV §1.4/§7.3.
- **Fecha de inicio:** COIGT (noticia colegial, 17/12/2024, https://www.coigt.com/VerNoticias.aspx?Cod=3856): «Desde el pasado jueves 12 de diciembre» la SEC usa el esquema 4.0, es decir, desde el **12/12/2024**. Ya no admite multirrecintos. El blog de la IDEE (17/01/2025, https://blog-idee.blogspot.com/2025/01/limitacion-de-archivos-gml-de-parcela.html) dice que «únicamente se aceptará este esquema vigente», sin fecha. **[CORRIGE]** INV §1, que habla de un «aviso de la DGC, enero de 2025»: la restricción efectiva es del 12/12/2024 y la entrada del blog es de enero de 2025. No hay ninguna nota de la DGC con fecha exacta.

### 1.6 Formato GML de parcela y edificio, y GML.pdf
- «Formato GML parcela catastral.pdf» y «Formato GML edificio.pdf» (catastro.hacienda.gob.es/documentos/formatos_intercambio/…): **no se pudieron abrir**, porque WebFetch pidió un permiso que no llegó a tiempo. Siguen enlazados desde CoordinacionCatastroRegistro.html junto a `edificio.zip`, `edificio y piscina.zip`, `CP ejemplo explicativo.zip` y «portal generacion GML.pdf».
- GML.pdf (https://www.catastro.hacienda.gob.es/asistente_catreg/img/GML.pdf), sin versión: esquema **4.0**, EPSG 25829/30/31 y 32628 iguales en todo el fichero, exterior horario e interiores antihorarios, ≥ 4 vértices, `areaValue` = «Área matemática del interior del perímetro» redondeada al m², `label` de 2 dígitos en urbana y hasta 5 en rústica, un `member` por parcela, «archivos GML de un solo recinto», el GML sí puede actuar sobre el dominio público urbano (cesión e incorporación de viario) y agregación por quíntuplo. **[CONFIRMA]** (salvo el quíntuplo, véase §1.2).
- La página de FAQ Catastro-Registro aún dice que el GML sigue INSPIRE CP «v3.0.1»: es texto **desactualizado**. Prevalecen el 4.0 y la SEC.

### 1.7 Ayuda del ICUC y desplazamientos
- ayuda_ICUC.htm (https://www.catastro.hacienda.gob.es/ayuda/vga/ayuda_ICUC.htm), sin fecha. **[CONFIRMA]** E-21: 60 ficheros, 100 m, ≥ 4 puntos con 2 coordenadas, BICE, solapes y huso.
- **[AMPLÍA]** con estos datos:
  - Solo se lee la geometría de `Building` con `horizontalGeometryReference = "footPrint"` y de `OtherConstruction`.
  - La parcela se toma de las **14 primeras posiciones** de la RC.
  - Namespaces admitidos: `ES.SDGC.BU` y `ES.LOCAL.BU`.
  - Esquema: copia local modificada para admitir `openAirPool`.
  - Esquema del informe: https://www.catastro.hacienda.gob.es/ws/esquemas/informeICUC.XSD (etiquetas `parcelaCatGml`, `construcExcedentes`, `superficie`, `resultado`).
- Mensajes literales de la SEC (para replicarlos en el validador):
  - «Se debe aportar la geometría de la huella en el caso de edificio, o bien la geometría en el caso de otras construcciones.»
  - «En alguna de las geometrías del fichero gml falta que último punto sea igual al primero»
  - «Se ha encontrado una geometría vacía dentro del fichero gml.»
  - «Falta indicar el huso en el que se encuentran las coordenadas de alguna de las geometrías.»
  - «Se ha encontrado una geometrías sin identificar dentro del fichero gml.»
  - «La construcción gml_id se encuentra repetida en las geometrías presentadas.»
  - «Existe superposición entre la geometrías presentadas.»
  - «Alguna de las parcelas catastrales indicadas contienen Bienes inmuebles de características especiales.»
  - «Alguna de las construcciones se encuentra a más de 100 metros de la parcela.»
- ICUC_desp.htm (https://www.catastro.hacienda.gob.es/ayuda/vga/ICUC_desp.htm): X' = AX·X + BX·Y + CX; Y' = AY·X + BY·Y + CY (de las coordenadas reales a las catastrales). CX y CY son positivos si la cartografía catastral está más al Este o al Norte. **[CORRIGE/AMPLÍA]** INV §2 («el GML va en la posición real»): hay que adjuntar en «+ Documentación» un GML con las construcciones **en su posición real**, pero **el ICUC se obtiene con otro GML en el que las construcciones están desplazadas como la cartografía catastral**. Hacen falta dos GML.

### 1.8 Asistente Catastro-Registro: incidencias de la SEC
- https://www.catastro.hacienda.gob.es/asistente_catreg/asistente_catreg.html (sección Técnicos → Incidencias de la SEC). Los textos están en imágenes; se conocen sus títulos y soluciones:

| Código | Incidencia | Solución oficial | En el plugin |
|---|---|---|---|
| CdU_2 | Fallo de esquema INSPIRE | Ajustar a GML.pdf | XSD, XLINK |
| CdU_3 | Fichero «MUTIRRECINTO» | Un `member` por geometría | GEO-MULTIPARTE |
| CdU_4/5 | Geometrías incorrectas | ≥ 4 pares **no alineados**, primero = último | ANILLO-*; **falta comprobar los vértices alineados o degenerados** |
| CdU_6 | EPSG no admitido | 32628, 25829, 25830, 25831 «acorde con provincia/municipio» | SRC-NO-ADMITIDO, SRC-PROVINCIA |
| CdU_7 | EPSG ausente | Poner el EPSG en `posList`, `MultiSurface`, `Surface` y `Point` | SRC-FALTA (comprobar que mira los 4) |
| CdU_8 | EPSG distinto | El mismo en las 4 etiquetas | SRC-MEZCLADOS |
| CdU_9 | **Área gráfica ≠ numérica** | `areaValue` = área de `posList` al m² | SUP-DISTINTA (hoy aviso) |
| CdU_10 | Solape de parcelas intervinientes | Validar las descargadas sin modificar | SOLAPE |
| CdU_11 | Solape con parcelas **no** intervinientes (discordancias) | Solo se admite la afección de dominio público urbano | CMP-RC-AJENA / CMP-DOMINIO-PUBLICO |
| CdU_12 | **Solape entre dos municipios** | «No se validan archivos GML con geometrías de dos municipios» | Solo aviso de tramitación (CMP-TRAMITE) → **subir a error** |

- **[NUEVO]** Soporte técnico: «SOPORTE GML-IVGA-CARTOGRAFIA» (https://www.sedecatastro.gob.es/Formulariosusuario/inicio.aspx).
- **[NUEVO]** Fincas coordinadas: https://www.sedecatastro.gob.es/portalcatastro/datoscoordinacion.aspx.
- **[NUEVO]** Vigencia gráfica de certificaciones: https://www.sedecatastro.gob.es/ValidacionesGraficas/SECValidarGC.aspx (no se pudo abrir).

### 1.9 Informe de identidad gráfica [NUEVO, importante]
- https://www.catastro.hacienda.gob.es/ayuda/ayuda_identidad.htm. Servicio en la SEC: https://www1.sedecatastro.gob.es/Cartografia/mapa.aspx?identidad=SI. Se basa en las resoluciones de 2020 y 2021.
- Entrada: un GML con la RGA y **una sola parcela** (relación 1:1).
- Criterio: margen de «0.5 metros» hacia dentro y hacia fuera del perímetro catastral en urbana, y ±2,00 m en rústica; diferencia de superficie ≤ 5 % (la ayuda lo cita en rústica). Admite desplazamiento o giro, manual o parametrizado, para encajar.
- «Este informe sólo se emitirá en sentido positivo.» Incluye CSV, los dos GML, un XML, las coordenadas y un croquis.
- **[CORRIGE]** INV §1.3, que presenta las tolerancias ±0,50 m / ±2,00 m / 5 % como tolerancias del IVGA. Son los **márgenes del criterio de identidad gráfica** (Anexo II de la Resolución de 2020) y se aplican en el **informe de identidad**. El IVG positivo sigue exigiendo que el contorno coincida con **±1 cm** (Resolución 2015 y FAQ), como ya aplica `comparacion.py`.

### 1.10 Editor parcelario
- https://www.catastro.hacienda.gob.es/ayuda/ayuda_editor_parcelario.htm. Sin fechas; remite a un manual en PDF y a 6 vídeos (el 6.º trata la «División automática por superficies»). No hay cambios publicados. El editor exporta GML y «no modifica la base de datos catastral».

### 1.11 Página «Validaciones gráficas» de la SEC
- https://www.sedecatastro.gob.es/Accesos/SECAccValidacionesGraficas.aspx, sin avisos fechados.
- Servicios:
  - Identidad gráfica.
  - IVG: https://www1.sedecatastro.gob.es/Cartografia/mapa.aspx?IVGActivo=S
  - Descarga de un IVG por CSV: `https://www1.sedecatastro.gob.es/Cartografia/mapa.aspx?CSVIVG=<CSV>` **[NUEVO]**. El plugin podría abrir esta URL para recuperar el XML o los GML de un IVG.
  - Vigencia gráfica, Mis informes e ICUC.
- **Check4SEC no aparece** en esta página (véase §3).

---

## 2. Normativa vigente

### 2.1 Ley Hipotecaria (redacción de la Ley 13/2015)
- Ley 13/2015: https://www.boe.es/buscar/doc.php?id=BOE-A-2015-7046. El consolidado de la LH (BOE-A-1946-2453) no se pudo abrir por permiso. No se ha encontrado ninguna reforma de los arts. 9, 10, 199, 201 o 202 posterior a 2015.
- Art. 9.b: hay correspondencia si «las diferencias de cabida, si las hubiera, no excedan del diez por ciento de la cabida inscrita».
- Art. 10.3: «Únicamente podrá aportarse una representación gráfica georreferenciada complementaria o alternativa» en los supuestos tasados. Art. 10.6.c: los requisitos técnicos se fijan por resolución conjunta.
- Art. 199: alegaciones de colindantes «en el plazo de los veinte días siguientes».
- Art. 201.3: diferencias ≤ 10 % (3.a) o ≤ 5 % solo de superficie (3.b), sin expediente.
- Art. 202: la porción de suelo ocupada «habrá de estar identificada mediante sus coordenadas de referenciación geográfica».
- Doctrina DGSJFP reciente **[NUEVO]**:
  - Res. 8/10/2025 (BOE-A-2026-1526): https://boe.es/boe/dias/2026/01/22/pdfs/BOE-A-2026-1526.pdf
  - Res. 30/12/2025 (BOE-A-2026-9152): https://boe.es/boe/dias/2026/04/27/pdfs/BOE-A-2026-9152.pdf
  - Res. 6/5/2026 (BOE-A-2026-17137): https://www.boe.es/boe/dias/2026/08/06/pdfs/BOE-A-2026-17137.pdf
  - Ideas comunes: el juicio de identidad debe ser motivado; el umbral es el 10 %; la invasión de geometrías catastrales es «propia» de una RGA y no basta para denegar; una representación que abarca **dos fincas registrales** sin delimitar cada una vulnera el principio de especialidad, por lo que hace falta una representación por finca; la oposición municipal debe ser concreta y no basta una «invasión virtual» por cartografía desplazada. El registrador puede usar la aplicación homologada (Res. 2/8/2016).
- Art. 202, Res. 19/6/2020 (BOE-A-2020-9071): las coordenadas de la edificación «no necesita ser aportada en formato GML». Basta una representación sobre plano georreferenciado. Sistema oficial: ETRS89, REGCAN95 en Canarias. **[AMPLÍA]**: el GML de edificio sirve para el ICUC, pero el Registro no lo exige en ese formato.

### 2.2 TRLCI
- Consolidado: https://www.boe.es/eli/es/rdlg/2004/03/05/1/con, con última actualización **24/12/2022**.
- Art. 18.2: subsanación ante notario, con veinte días para los colindantes. Art. 18.3: el registrador comunica al Catastro en un plazo máximo de cinco días. No se han encontrado cambios de 2023 a 2026 en lo consultado.

### 2.3 Resoluciones conjuntas vigentes
1. **Res. conjunta DGRN-DGC de 26/10/2015** (BOE 30/10/2015, BOE-A-2015-11655): https://www.boe.es/eli/es/res/2015/10/29/(1)/con. Solo «Texto inicial», sin modificaciones. **Sigue siendo la norma base de requisitos técnicos** **[AMPLÍA]**; INV solo cita la de 2020.
   - Formato: «en formato GML, previsto en el Anexo».
   - Sistema: ETRS89 (REGCAN95 en Canarias) en UTM.
   - Precisión: levantamiento con error < 25 cm y el 85 % de los puntos ≤ 20 cm; digitalización ±0,20 m (urbana) y ±0,40 m (rústica); vértices sobre la cartografía catastral ±1 cm.
   - Metadatos de la RGA: fecha, solicitante, **metodología**, parcelas afectadas, superficie y listado de coordenadas. El técnico firma y declara el cumplimiento.
   - IVG en 24 h, con CSV.
   - Construcciones: coordenadas de la porción de suelo ocupada y si consta el libro del edificio.
2. **Res. conjunta DGSJFP-DGC de 23/09/2020** (publicada por Res. de 7/10/2020, BOE núm. 269 de 10/10/2020, BOE-A-2020-12111): https://www.boe.es/eli/es/res/2020/10/07/(1)/con y https://www.catastro.hacienda.gob.es/documentos/BOE-A-2020-12111.pdf. Solo «Texto inicial», **sin modificaciones posteriores**.
   - Anexo II: márgenes de identidad (±0,50 m urbana, ±2,00 m rústica y superficie ≤ 5 %).
   - Construcciones: sus coordenadas «habrán de estar referidas siempre a su posicionamiento absoluto sobre el terreno».
   - Giros y desplazamientos: **dos GML** (levantamiento y catastral) con los parámetros de transformación; la finca queda pre-coordinada pendiente de ajuste. Su mera existencia «no supone, por sí misma, la invasión».
   - Dominio público: el margen de tolerancia «no será aplicable» frente al dominio público; en el no deslindado no hay colindancia si este atraviesa la finca o afecta a «más de un 10%».
   - El Catastro «podrá crear las parcelas catastrales necesarias» para los viales.
   - Propiedad horizontal: certificación de parcela con identificador propio.
   - Estados: coordinada, no coordinada y pre-coordinada. Plazo de oposición de 20 días.
3. **Res. conjunta DGSJFP-DGC de 29/03/2021** (BOE 15/04/2021, BOE-A-2021-5949), sobre la representación gráfica en documentos notariales: https://boe.es/boe/dias/2021/04/15/pdfs/BOE-A-2021-5949.pdf. **[NUEVO]**: no estaba en INV.
   - El IVGA debe contener **dos GML**: el del levantamiento en el sistema oficial (RD 1071/2007) y el ajustado a la cartografía catastral, con los parámetros de transformación. La SEC tiene un servicio para calcularlos.
   - El ICUC muestra las coordenadas del técnico y las catastrales.
   - Con giro y discrepancia a la vez, primero se corrige el giro y después se aplica el criterio de identidad.
   - Alegaciones en 20 días hábiles.
- No se ha encontrado ninguna resolución conjunta posterior a 2021 sobre requisitos técnicos (búsquedas en BOE para 2024, 2025 y 2026).

---

## 3. Check4SEC
- **No está en plugins.qgis.org.** La etiqueta `sec` solo lista SEC4QGIS 1.0.5 (6/11/2017, QGIS 2.12–2.99, sin mantenimiento). Las búsquedas por nombre no lo encuentran, ni hay repositorio público en GitHub o GitLab (las búsquedas web no devuelven ninguno).
- Distribución oficial: Sede Electrónica del Catastro, apartado «Validaciones Gráficas», según los colegios profesionales (COAATZ y COAMU). COAMU publicó el 21/03/2023 un ZIP con el manual y el plugin (https://coamu.es/wcoamuficheros/noticias/noticias_doc/21_03_2023_13_58_43_manual_y_plug_check4.zip), que **no se pudo descargar**. Hoy la página de Validaciones Gráficas de la SEC no muestra el enlace (véase §1.11).
- Funciones declaradas (Geoinnova, 11/09/2023, modificado el 04/03/2026, https://geoinnova.org/blog-territorio/complementos-qgis-datos-catastrales/; COAATZ y COAMU):
  - genera GML INSPIRE desde los servicios de descarga INSPIRE de Parcela Catastral;
  - convierte Shapefile, DXF, SVG, etc. a GML;
  - «realiza las mismas validaciones que el validador de la SEC e informa de su estado»;
  - genera GML de parcela (IVGA) y GML de huellas de edificio y piscina (ICUC);
  - permite llegar a un IVGA positivo, un informe de identidad o un ICUC.
- No hay changelog, issues ni versión publicados en línea. La lista detallada de comprobaciones solo está en el manual adjunto (ya analizado en INV §2 y §5: tipo BU/PI, solapes y parcela que contiene cada huella). No se copia código (GPL-3).
- Comparación (a partir de lo público y de INV):

| Función | Check4SEC | Catastral GML Tools |
|---|---|---|
| GML CP 4.0 desde WFS | Sí | Sí |
| Importar DXF/SVG | Sí | No (solo capas de QGIS: DXF vía OGR) |
| Validaciones de la SEC (IVGA) | Sí | Sí, y más amplias (NPO/NPP, ±1 cm, dominio público, tramitación) |
| ICUC (BU/PI, solapes, dentro de la parcela) | Sí | Sí |
| Informe de identidad (±0,5/±2 m, 5 %) | Declarado | **No** |
| Desplazamiento (CX/CY o afín) y doble GML | No consta | **No** |

- **[NUEVO, publicación]** Seguridad de plugins.qgis.org (desde el 23/04/2026, https://blog.qgis.org/2026/04/23/plugin-repository-security-enhancements/ y https://plugins.qgis.org/docs/security-scanning/rules):
  - Bandit y detect-secrets bloquean (CRITICAL).
  - `xml.etree` (B314/B405) y `lxml` (B320/B410) dan WARNING/INFO, con recomendación de defusedxml.
  - **FILE_SUSPICIOUS** (.bat, .sh, .exe…) es CRITICAL.
  - Las peticiones sin timeout (B113) dan aviso.
  - Los plugins nuevos deben tener insignia verde.
  - El ZIP actual se arma con una lista blanca (`tools/package.py`), así que `tools/probar.bat` no entra. Conviene comprobarlo en una prueba.
  - `core/esquemas.py` ya usa `resolve_entities=False, no_network=True` (bien). `gml_lector.py` y `servicios.py` usan `xml.etree`, que solo genera aviso.

---

## 4. Servicios web de la DGC
- Portal INSPIRE (https://www.catastro.hacienda.gob.es/webinspire/index.html): WMS, WFS CP/AD/BU y ATOM. «Los datos se actualizan 2 veces al año» (ATOM). **Sin avisos de cambios ni cortes.**
- WFS CP (inspire-cp-WFS.pdf, **v1.0 de julio de 2016**): GetParcel, GetNeighbourParcel, GetZoning y GetParcelsByZoning. BBOX ≤ 1 km² y 5.000 elementos para CadastralParcel; ≤ 25 km² y 500 elementos para CadastralZoning. EPSG 4326, 4258, 25829-31, 3785 y 3857. GML 3.2.1. El documento solo cita el esquema CP **3.0**. **[AMPLÍA]**: la documentación oficial está desfasada respecto al servicio, y E-02 comprobó en vivo que también sirve 32628.
- WFS BU (inspire-bu-WFS.pdf, **v1.0 de julio de 2016**): GetBuildingByParcel, GetBuildingPartByParcel y GetOtherBuildingByParcel (REFCAT y SRSNAME opcional). BBOX ≤ 4 km² y 5.000 elementos. **[CONFIRMA]**
- WFS AD (inspire-ad-wfs.pdf, v1.0 de julio de 2016): GetADByCodVIA, GetADByRefCat y GetADByPostalCode. BBOX ≤ 4 km² y 5.000 elementos. **[NUEVO]**: la dirección por RC podría ir en el informe.
- Servicios libres (Webservices_Libres.pdf): **v2.6, de 01/12/2025** **[CONFIRMA]**.
  - Cambios recientes: 2.4 (22/05/2024, nuevo dominio), **2.5 (09/10/2025: «información de la finca en los datos del inmueble», 2.1.5-2.1.7)** y 2.6 (códigos INE en el listado de vías).
  - Servicios: Consulta_RCCOOR, **Consulta_RCCOOR_Distancia** (RC cercanas a un punto) y Consulta_CPMRC; Consulta_DNPRC/DNPLOC/DNPPP y sus versiones por códigos. Formatos SOAP, REST y JSON (`.svc/json/`).
  - SRS de Consulta_RCCOOR: 4230, 4326, 4258, 32627-32631, 25829-25831 y 23029-23031. **No admite REGCAN95 (4081/4083).**
  - El propio documento mezcla `http` y `https` en sus URL.
- Licencias:
  - INSPIRE (Licencia.pdf, **v1.0 de julio de 2016**): uso comercial de la información **transformada**; prohíbe difundir la original y suplantar («cartografía catastral», «información catastral»). **No impone una fórmula de cita.**
  - Licencia de descarga (licdescargaES.pdf, Res. 23/3/2011, cláusula 12): «deberá citarse como fuente en todos los productos o servicios que se elaboren a partir de la información» y «deberá indicarse la fecha en la que se produjo el acceso». **[CONFIRMA]** INV §4. La obligación de citar viene de esta licencia, no de la INSPIRE; el plugin cumple ambas.
- No se han encontrado avisos oficiales de cortes de los WFS en 2024-2026.

---

## 5. Territorios forales, Canarias, Ceuta y Melilla
- **Productos de la DGC** (https://www.catastro.hacienda.gob.es/es-ES/productos.html): la validación gráfica y la ubicación de construcciones cubren «Todo el territorio español excepto País Vasco y Navarra». **[CONFIRMA]** mejora 31.
- **Navarra:** WFS https://inspire.navarra.es/services/CP/wfs con licencia CC BY 4.0 y contacto sitna@navarra.es (datos.gob.es). **[CONFIRMA]** E-18. No se ha encontrado ningún procedimiento ni formato GML oficial de validación para la coordinación con el Registro (búsquedas en navarra.es y en el BOE y el Parlamento de Navarra). La página del Parlamento devolvió datos binarios ilegibles.
- **Álava/Araba:**
  - Metadatos IDEE (https://www.idee.es/csw-codsi-idee/srv/api/records/CP_cadastralparcel_dataset, sellados el 03/04/2025): WFS 2.0 `http://geo.araba.eus/WFS_INSPIRE_CP` (y una variante `WFS_INSPIRE_CP_V4` y `WFS_INSPIRE_BU_V4` que usa el paquete rOpenSpain/CatastRoEus), ATOM https://geo.araba.eus/atom/ATOM.atom y WMS.
  - Licencia **CC BY 4.0**, «Arabako Foru Aldundia / Diputación Foral de Álava».
  - EPSG 4326, 3042 y 25830. GML 3.2. **[NUEVO]**
- **Gipuzkoa:** b5m (https://b5m.gipuzkoa.eus/web5000/en/datasets): «INSPIRE Cadastral Parcels» y «INSPIRE Buildings», actualizados el **05/10/2026**. Endpoints WFS 2.0 (según CatastRoEus): `https://b5m.gipuzkoa.eus/inspire/wfs/gipuzkoa_wfs_cp` y `…_bu` (y `…_ad`). La licencia no se indica en el listado; véase https://b5m.gipuzkoa.eus/web5000/en/legal-information (no abierta). datos.gob.es avisa de que no sirve «para ningún tipo de certificado». **[NUEVO]**
- **Bizkaia:** INSPIREBIZKAIA (https://www.bizkaia.eus/es/inspirebizkaia, no abierta). WFS ArcGIS Server (según CatastRoEus):
  - `https://geo.bizkaia.eus/arcgisserverinspire/rest/services/Catastro/Annex1/MapServer/exts/InspireFeatureDownload/service` con `cp:CadastralParcel`;
  - `…/Catastro/Buildings/MapServer/exts/InspireFeatureDownload/service` con `bu-core2d:Building`;
  - ATOM en apli.bizkaia.eus.
  - Licencia no verificada. **[NUEVO]**
- No se ha encontrado en ningún territorio foral un formato GML propio ni un validador equivalente al IVG. **[CONFIRMA]** INV §3.1.
- **Canarias:** el asistente (CdU_6) solo admite **32628, 25829, 25830 y 25831**. **[RESUELVE E-03]**: EPSG:4083 (REGCAN95 UTM 28) **no** está entre los admitidos. Hay que convertir a 32628 (la DGC trata REGCAN95 y WGS84 como equivalentes a efectos del huso 28). La FAQ de la DGC confirma **Las Palmas: 32628**.
- **Ceuta y Melilla: 25830** (FAQ DGC). También **Girona: 25831**. **[CONFIRMA]** los supuestos marcados con asterisco en `core/geometria.py`. URL: https://www.catastro.hacienda.gob.es/es-ES/faqs_catastro_registro.html

---

## 6. Otros requisitos y casos particulares
- **Dominio público:**
  - Las tolerancias no se aplican frente al dominio público (Res. 2020).
  - Viales urbanos no catastrados como parcela: IVG negativo (FAQ). Aun así, el GML puede incorporar viario o cesiones con una parcela LOCAL (GML.pdf).
  - La DGC puede crear parcelas de viales.
  - **Expropiación sin acta de entrega:** el terreno sigue siendo privado (DGSJFP 6/5/2026).
- **Fincas discontinuas:** una representación por porción, sin multiparte. **Una RGA que abarque dos fincas registrales sin separarlas vulnera la especialidad** (DGSJFP 2026).
- **División horizontal:** se coordina la parcela, no los elementos. La Res. 2020 prevé una certificación de parcela en propiedad horizontal con identificador propio.
- **Edificio que invade otra parcela:** ICUC negativo, con la superficie excedente marcada. El ICUC no valida RGA.
- **Desplazamiento de cartografía:** doble GML (levantamiento y catastral) con los 6 parámetros. El FAQ propone calcularlos con 3 puntos comunes (Gauss-Jordan) y comprobarlos con otros.
- **Metros catastrales:** la UTM provoca diferencias de hasta ±0,06 % entre la superficie de proyección y la real (FAQ). Conviene indicarlo en el informe de superficies.
- **Precisión nominal** de la cartografía catastral: ±0,5 m en urbana y ±2 m en rústica (FAQ).
- **Coordenadas:** 2 decimales; la SEC trunca el resto.
- **Huso:** uno solo por fichero y «acorde con provincia/municipio». Un GML con dos municipios no se valida (CdU_12).
- **Validez del informe:** no tiene caducidad publicada y puede repetirse «cuantas veces sea preciso». Sin CSV no hay comunicación al Catastro.
- **Diferencia de cabida:** 10 % (art. 9.b y 201.3.a LH) y 5 % (201.3.b). Pueden servir como avisos jurídicos en el informe de superficies (mejora 25).

---

## 7. Qué debería añadir o cambiar el plugin (priorizado)

**Alta**
1. **Corregir INV §1.3.** Las tolerancias ±0,50/±2,00 m y 5 % son del criterio de identidad gráfica (Anexo II, Res. 2020), no del IVG, que exige ±1 cm. Revisar también cualquier texto de la ayuda o la interfaz que las presente como tolerancias del IVG.
2. **Municipios distintos (CdU_12) como ERROR**, no como aviso de tramitación: la SEC no valida GML con geometrías de dos municipios.
3. **SUP-DISTINTA como aviso fuerte o error al crear.** La ayuda del IVG y el asistente (CdU_9) siguen exigiendo que `areaValue` coincida con el área al m², aunque el documento v2.3 lo quitara. El escritor ya lo cumple; en el validador, «la SEC puede rechazarlo».
4. **Vértices alineados o degenerados (CdU_4/5).** Al menos 4 pares no alineados y sin anillos de área ≈ 0 ni espigas. Nuevo código, p. ej. GEO-ALINEADOS.
5. **E-03 resuelto:** EPSG:4083 no se admite. Si el SRC de la capa es REGCAN95 (4081/4082/4083), convertir a 32628 y avisar; nunca escribir 4083.
6. **E-17:** el umbral oficial mayoritario es el **quíntuplo** (art. 48 RH; IVGA.pdf, GML.pdf y ayuda del IVG), frente al 80 % del documento v2.3. El aviso debería basarse en el quíntuplo y citar ambos. Es también el criterio que usa la SEC para **preseleccionar** el tipo de operación.

**Media**
7. **Informe de identidad gráfica (simulación).** Para 1 GML con 1 parcela: banda de ±0,50 m (urbana) o ±2,00 m (rústica) alrededor del perímetro catastral y |ΔS| ≤ 5 %. Mostrar las zonas fuera de la banda. Opcionalmente, ajuste por traslación o giro.
8. **Desplazamiento de cartografía y doble GML** (Res. 2020/2021, ICUC_desp, ayuda del IVG):
   - calcular los 6 parámetros afines (o solo CX, CY) con ≥ 3 pares de puntos, ajuste por mínimos cuadrados y residuos de comprobación;
   - generar los dos GML (levantamiento y catastral);
   - para el ICUC, generar el GML desplazado para el informe y el real para «+ Documentación». Signo: CX/CY > 0 si la cartografía catastral está más al Este o al Norte.
9. **Lector del XML de los informes** (mejora 32):
   - IVG: `informeGrafAlt.xsd`, tipos de operación 1-6 y `resultado`;
   - ICUC: `informeICUC.XSD`, con `construcExcedentes` y `superficie`;
   - comentario con el CSV y el tipo de operación en los GML del editor;
   - abrir `mapa.aspx?CSVIVG=<CSV>` desde el panel.
10. **Mensajes de la SEC en el validador:** usar los textos literales de los errores del ICUC (§1.7) y los títulos CdU_x del asistente, para que el usuario reconozca el error que verá en la Sede.
11. **Comprobaciones del ICUC:** solo `Building` con `footPrint` u `OtherConstruction`; RC de 14 posiciones (avisar si se dan 18 o 20); namespace `ES.SDGC.BU`/`ES.LOCAL.BU`; **BICE** como aviso (Consulta_DNPRC puede indicar si la parcela tiene BICE; si no, nota de «no comprobado»).

**Baja**
12. **Territorios forales:** documentar los WFS de Álava (CC BY 4.0), Gipuzkoa y Bizkaia para una posible descarga en el futuro. Hoy la decisión es solo detectar y avisar, y no generar GML. Antes de usarlos, verificar las licencias de Gipuzkoa y Bizkaia.
13. **Informe de superficies** (mejora 25): añadir la nota de ±0,06 % por la proyección UTM y los umbrales del 10 % y el 5 % de la LH (arts. 9.b y 201.3) como avisos jurídicos orientativos.
14. **Normativa en la ayuda:** añadir la Res. 26/10/2015 (requisitos base) y la Res. 29/03/2021 (notarial, doble GML) junto a la de 2020. Fecha de entrada del esquema 4.0: **12/12/2024**.
15. **Publicación en plugins.qgis.org:** pasar Bandit y detect-secrets en local; ningún .bat/.sh/.exe en el ZIP; `timeout` en todas las peticiones; valorar `defusedxml` o parsers con `resolve_entities=False` para quitar los avisos B314/B405.
16. **Consulta_RCCOOR_Distancia** como alternativa cuando el clic cae en vía pública (RC más cercana). Los datos de finca de Consulta_DNPRC v2.5 se pueden mostrar en la ficha.

---

## 8. Páginas que no se pudieron abrir (no se ha inventado su contenido)
- Formato GML parcela catastral.pdf y Formato GML edificio.pdf (URL con `%20`): permiso de WebFetch no concedido a tiempo.
- boe.es consolidado de la Ley Hipotecaria (ELI d/1946/02/08) y act.php?id=BOE-A-2020-12111: ídem. Se usaron el texto de la Ley 13/2015 y el ELI de la Res. 2020.
- SECValidarGC.aspx (vigencia gráfica), legal-information de b5m e inspirebizkaia: sin abrir.
- ZIP de Check4SEC en coamu.es: el proxy lo bloquea. No hay repositorio público de Check4SEC.
- Página del Parlamento de Navarra: devolvió datos binarios.
