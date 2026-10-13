# Auditoría completa y plan de corrección (09/10/2026)

Revisión de todo el plugin antes de seguir con las fases pendientes, para que no se escape nada: normativa y documentos
oficiales, Check4SEC (herramienta de la DGC), código, y una batería de escenarios reales probados con el código.

| Informe detallado | Qué revisa | Resultado |
|---|---|---|
| [auditoria/normativa.md](auditoria/normativa.md) | 29 documentos de la DGC y del curso: guía de validación del IVG, guía GML Catastro-Registro, formato GML de edificio, diferencias 3.0/4.0, editor parcelario, Tema 8 v2026, Tema 6.3, FAQ, manual de Check4SEC, prácticas con Check4SEC… | 22 contradicciones entre documentos (X-01…X-22), reglas con su cita y su estado en el plugin, 32 casos no contemplados y 14 riesgos legales |
| [auditoria/web.md](auditoria/web.md) | Fuentes oficiales actuales en internet: ayudas del IVG, del ICUC y de identidad gráfica, asistente Catastro-Registro, BOE (Ley 13/2015, TRLCI, Resoluciones conjuntas 2015/2020/2021 y de la DGSJFP 2020-2026), WFS e licencias de la DGC, territorios forales, Check4SEC, repositorio de QGIS | Correcciones a INVESTIGACION y lista priorizada |
| [auditoria/codigo.md](auditoria/codigo.md) | Todo el código, con experimentos que reproducen cada fallo | 2 críticos, 6 altos, 13 medios, 14 bajos |
| [auditoria/escenarios.md](auditoria/escenarios.md) | 277 escenarios sintéticos (RC, SRC, geometrías, ficheros raros, alteraciones, multiparcela, edificio, DXF, descarga, panel) | 21 fallos o casos que no deberían aceptarse |

Limitaciones: sin acceso a la Sede ni al certificado (lo que «la Sede rechazaría» sale de la documentación y de las pruebas
reales ya hechas, E-11…E-23); Check4SEC no tiene repositorio público (solo se ha usado su manual: funciones y reglas, sin
código, que es GPL-3); los escenarios se probaron en QGIS 3.34 sin ventana (3.40 y 4.2 se prueban con `tools\probar.bat`).

## 1. Lo más importante

1. **El plugin puede dar por bueno lo que no lo es** (bloque A):
   - la comparación con el Catastro tolera varios centímetros (mide superficies, no distancias): un vértice movido 2 cm o
     un escalón de 20 cm salen «contorno coincidente (±1 cm)», y un edificio que sobresale 6 cm, «dentro»;
   - Validar puede pegar a un fichero el resultado de la tarea lanzada para otro (y decir «Listo para el ICUC» del que no
     se ha comparado);
   - una parcela idéntica a la catastral sale como «Subsanación de discrepancias» (la Sede da error; la mejora 14 decía
     hacerlo y no está);
   - RC escritas en minúsculas o con guiones se escriben tal cual como SDGC; una RC de inmueble (18 o 20) en la capa se
     convierte en una parcela LOCAL.
2. **Excepciones y pérdidas de datos**: SRC de la capa que no encaja (Parcela), carpeta inexistente (Unir), errores de
   escritura sin capturar, GML anómalos en el lector, volver a descargar borra ediciones sin guardar, destino igual al
   fichero de la capa.
3. **Normativa actualizada que el plugin no refleja**: desde el 12/03/2025 la Sede no certifica IVG negativos (informa
   de los errores y deja descargar el «GML parcial»); el viario urbano y las cesiones admiten IVG positivo condicionado;
   falta la reparcelación; el ICUC no admite parcelas que aún no existen (el texto del plugin decía lo contrario) y, con
   cartografía desplazada, se pide con el GML desplazado como el Catastro y el real va como documentación; dos
   municipios en un GML no se validan; recinto con vértices alineados; avisos legales que protegen al técnico.
4. **INVESTIGACION.md tiene datos a corregir**: las tolerancias de ±0,50 m / ±2 m y 5 % son del informe de *identidad
   gráfica*, no del IVG (que exige ±1 cm de contorno); la Sede solo admite el esquema 4.0 desde el 12/12/2024; faltan la
   Resolución conjunta de 29/03/2021 (dos GML con parámetros de transformación) y las resoluciones recientes de la DGSJFP.

## 2. Plan

Cada punto tiene un identificador (AU-xx) y remite al informe detallado. Orden: primero lo que hace que el plugin se
equivoque o se rompa; después la normativa; luego robustez y documentación; por último, las fases pendientes ampliadas
con lo aprendido. Cada bloque se cierra con pruebas en `tests/` (una por caso), pruebas en el PC (3.40 y 4.2),
CHANGELOG, DESARROLLO y la ayuda.

### Bloque A · Fiabilidad: que nunca dé por bueno algo que no lo es (fase 8b)

| ID | Qué | Origen | Corrección |
|---|---|---|---|
| AU-01 | Tolerancia real de varios cm en «Comparar con el Catastro» (parcelas y edificios) | código C2; escenarios F4 | Medir distancias entre contornos (distancia de Hausdorff y vértice a contorno) con 1 cm; quitar el umbral de 0,05 m² como criterio de coincidencia; misma regla en edificios (cualquier punto a más de 1 cm fuera = fuera) |
| AU-02 | Validar mezcla resultados de dos ficheros (comparación y XSD) | código C1 | Cada tarea guarda la ruta y una «generación»; al abrir otro fichero se cancelan las anteriores y se descarta lo que llegue tarde |
| AU-03 | Parcela sin cambios (idéntica a la catastral) | código A1; normativa V-02; Check4SEC §4.1.3 | Error «parcela sin cambios: quítela del GML»; prueba; corregir DESARROLLO (mejora 14) |
| AU-04 | RC mal escritas como SDGC (minúsculas, guiones, puntos) | código A2; escenarios F16 | Normalizar con `refcat.limpiar` al leer la capa y en la tabla; el validador da error si un SDGC no está en mayúsculas sin separadores |
| AU-05 | RC de inmueble (18/20) en la capa → LOCAL | escenarios F3 | Tomar los 14 primeros como SDGC (avisando si el control no cuadra); mismo arreglo en la referencia de Edificio (código B10) |
| AU-06 | Excepción con capa en un SRC que no encaja (Parcela; también Edificio con SRC manual) | código A6; escenarios F1 | `src_incorrecto` también en Parcela, y blindar `area_m2`/`transformar` ante resultados no finitos |
| AU-07 | Excepciones de E/S: carpeta inexistente en Unir, escritura sin permiso, ruta que es carpeta | escenarios F2; código M10 | Comprobar carpeta y capturar `OSError` en Parcela, Edificio, Unir e Informe, con aviso en la barra |
| AU-08 | El lector se rompe con GML anómalos (coma decimal, `srsDimension` raro, `pos` incompleto, curvas, 3D heredado) y el informe con anillos degenerados | código A5, M11; escenarios F13 | Lector «a prueba de todo»: cada elemento en su `try`, incidencia en vez de excepción; leer `srsDimension` heredado; curvas: avisar de que la Sede no las admite |
| AU-09 | Destino igual al fichero de la capa (se sobrescribe la fuente) | código A3 | No proponerlo nunca; si el usuario lo elige, error |
| AU-10 | Volver a descargar borra capas con ediciones sin guardar | código A4 | Si alguna capa del grupo está en edición o modificada, no sustituir: crear «Catastro <RC> (2)» y avisar |
| AU-11 | Crear GML con solapes o huecos entre parcelas (verde) y edificios con partes solapadas | código M1, M2; escenarios F10 | Comprobar solapes al crear (error) y huecos (aviso), como el validador; en edificio, unir partes contiguas y rechazar las solapadas |
| AU-12 | «Listo para el ICUC» con el XSD pendiente o sin comprobar | código M3 | Solo con XSD válido (o con aviso claro si no hay conexión) |
| AU-13 | Texto del ICUC sobre parcelas que no existen | normativa E-12; Check4SEC §5.1.3 | «El ICUC solo trabaja con parcelas catastrales vigentes: tramite antes la alteración» |
| AU-14 | Desplazamiento de la cartografía en el ICUC explicado al revés | web (ICUC_desp) | Corregir la ayuda: el ICUC se pide con el GML desplazado como el Catastro y el GML real se adjunta; dejar preparada la transformación (AU-52) |
| AU-15 | Comparación de GML forales: dice «compruebe la posición» | código B3; escenarios CMP-31 | Detectar el territorio por la RC y por la posición (AU-31) y decirlo |
| AU-16 | Agregación con varias filas: todas reciben la misma RC | código B2 | La RC solo para la mayor (o la elegida, AU-24) |
| AU-17 | Edificio: la tabla pierde lo escrito al editar la capa | código M12 | Conservar tipo, plantas, estado e id por fid al recargar |
| AU-18 | Plantas con decimales se truncan; huella diminuta rechazada por «0 m²» | código B1; escenarios F11 | Error si no es entero; el GML de edificio no lleva superficie: no exigir 1 m² |
| AU-19 | DXF: patio dibujado como segunda polilínea de la misma entidad se pierde | escenarios F12 | Anillos interiores contenidos = huecos (no `unaryUnion`) |

### Bloque B · Normativa y avisos (fase 8c)

| ID | Qué | Origen | Corrección |
|---|---|---|---|
| AU-20 | Ya no hay IVG negativo certificado (desde 12/03/2025): GML parcial | normativa X-06, V-06 | Cambiar «informe negativo» por «la Sede no emitirá el informe (mostrará los errores)» en código y ayuda |
| AU-21 | Viario urbano y cesiones: positivo condicionado | normativa X-14, D-03 | Con una parcela LOCAL que cubre el suelo sin parcela: aviso «positivo condicionado, sin tramitación automática; necesita la conformidad de la Administración titular»; sin parcela que lo cubra, se mantiene el error |
| AU-22 | Falta «Reparcelación» en el asistente | normativa A-05 | Añadir tipo con su regla NPO/NPP y su ayuda |
| AU-23 | Subsanación excepcional con parcelas LOCAL (cesión, alineación) | normativa A-06 | Admitirla en el asistente con aviso |
| AU-24 | Elegir la parcela matriz en la segregación (hoy siempre la mayor) | normativa A-01; escenarios F17 | Botón/columna «matriz» en la tabla; la RC va a la elegida |
| AU-25 | Umbral de la agregación: quíntuplo (art. 48 RH) frente al 80 % (guía v2.3); manda la escritura | normativa X-02; web E-17 | Aviso con el quíntuplo, citando el 80 %, y recordando que manda la escritura; agrupación sin umbral de superficie en la Sede |
| AU-26 | Dos municipios en un GML: la Sede no lo valida (CdU_12) | web | Error al crear, en el validador y en la comparación |
| AU-27 | Recinto con menos de 4 vértices no alineados (CdU_4/5) | web | Error en escritor y validador |
| AU-28 | Superficie declarada distinta: aviso fuerte (ayuda del IVG y asistente CdU_9) | web E-16 | Mantener aviso con texto más claro; el escritor ya pone la de la geometría |
| AU-29 | `srsName` en cada elemento y truncado a 2 decimales al comparar ficheros ajenos | normativa P-11, P-12 | Validador: error si falta en alguno; comparación con coordenadas truncadas como la Sede |
| AU-30 | Huso de la provincia sin comprobar (Galicia en 25830…) | código M7; escenarios F9 | Usar `comprobar_src` en Parcela, Edificio y validador (aviso) |
| AU-31 | Navarra y País Vasco por posición (capas dibujadas a mano) | normativa F-02; escenarios F7 | Detectar por la posición (límites aproximados o RCCOOR) y bloquear con el aviso foral |
| AU-32 | ED50 y otros SRC transformados sin rejilla (2 m de error) | escenarios F8 | Aviso «transformación aproximada: use la rejilla oficial o la capa en ETRS89»; Canarias: REGCAN95 (4083) siempre a 32628 |
| AU-33 | Diseminado de urbana y BICE | normativa A-10, E-14 | Avisos (no tramitación automática; los BICE no tienen ICUC) |
| AU-34 | Avisos legales que protegen al técnico | normativa §11, §16 | En el asistente y la ayuda: la operación debe coincidir con la escritura; IVG positivo no es licencia ni respeta por sí la unidad mínima de cultivo; primero subsanar y luego declarar (dos GML); notificación a colindantes (art. 199 LH); diferencias de cabida del 10 % y 5 % (art. 201 LH); superficie UTM frente a la del terreno |
| AU-35 | Precisión del edificio (0,1 m o 10 m según el método) | normativa X-18 | Campo «precisión» (por defecto 0,1) con ayuda |
| AU-36 | Corregir INVESTIGACION y la tabla de husos | web; normativa X-22 | Tolerancias de identidad gráfica (no del IVG); 4.0 desde el 12/12/2024; Resoluciones 2015, 2020 y 2021 y DGSJFP 2025-2026; Las Palmas, Girona y Melilla confirmados |

### Bloque C · Robustez, rendimiento y compatibilidad (fase 8d)

| ID | Qué | Origen |
|---|---|---|
| AU-37 | Validar en segundo plano y sin O(n²) (índice espacial) para ficheros grandes | código M4 |
| AU-38 | Mapa de fondo sin bloquear sin red; tareas cancelables y con tiempo máximo; `unload` con tareas en marcha | código M5, M6 |
| AU-39 | Caché de esquemas XSD que no guarde páginas de error | código M9 |
| AU-40 | Huecos abiertos (franjas al borde) en el validador; solapes por anchura, no por área | código M13, B7 |
| AU-41 | «Unir GML» con `Seg_1` en ambos ficheros: renombrar (Seg_1, Seg_2…) en vez de error | código M8 |
| AU-42 | «Unir seleccionadas» con huecos de digitalización < 1 cm | escenarios F18 |
| AU-43 | Lector: xlink y codificación por el parser (UTF-16, espacios) | código B4; escenarios F15 |
| AU-44 | Elegir en el mapa activa tras cerrar el panel; motivo real de los fallos de descarga; respuesta HTML del servicio | código B6, B14; escenarios DES-19 |
| AU-45 | `setFilters` con `Qgis.LayerFilters(...)`; revisar el resto de APIs para Qt6 | código B5 |
| AU-46 | «Solo los elementos seleccionados» se queda marcado al cambiar de capa | escenarios F20 |
| AU-61 | Vértices nuevos sobre el lindero: al redondear al cm, un vértice de la línea de división que cae sobre un lindero inclinado queda hasta 0,7 cm fuera de él (en prueba2.gml, 0,38 y 0,61 cm; 0,09 m² de rendijas en total). Está dentro de ±1 cm y la Sede lo valida, pero se puede afinar: elegir, de los cuatro puntos de la rejilla de 1 cm que lo rodean, el más cercano al lindero catastral, y avisar si un vértice nuevo queda a más de 0,5 cm | Prueba a mano del 13/10/2026 |
| AU-47 | Pruebas que faltan (lista en código §«Pruebas que faltan» y escenarios) | código, escenarios |

### Bloque D · Documentación, metadatos y presentación (con cada bloque y al final)

| ID | Qué |
|---|---|
| AU-48 | `metadata.txt`, ayuda y README sin funciones que aún no existen; versión 0.2.0 con su `changelog` |
| AU-49 | Informe HTML: título «Informe de comprobación (no oficial, sin CSV)», cita de la DGC y fecha de la consulta; capas de comparación con fecha |
| AU-50 | Cabeceras GPL en todos los `.py`; ejemplos de la ayuda iguales a lo que propone el asistente (`Div_1`, `Agrupa_1`) |
| AU-51 | Sección «Marco legal y flujo de trabajo» en la ayuda y el manual (fase 12) |

### Bloque E · Fases pendientes, ampliadas con lo aprendido

| ID | Fase | Requisitos añadidos por la auditoría |
|---|---|---|
| AU-52 | Ajuste por desplazamiento o giro (nuevo) | Transformación afín (6 parámetros, 3 puntos) o traslación CX/CY; comprobación con puntos de control; dos GML (levantamiento y ajustado al Catastro) con los parámetros en el informe (Resolución de 29/03/2021); también para el ICUC |
| AU-53 | 9 · Conversor 3.0 → 4.0 | Lista de cambios de normativa §8 (raíz, namespaces, srsName, nilReason, quitar `boundedBy`, `zoning`, `validFrom/To`) |
| AU-54 | 10 · División | Por superficie, partes iguales, porcentaje, franjas paralelas **y cuotas**, con la regla del resto del editor de la Sede; puntos de apoyo .txt (mejora 33) |
| AU-55 | 11 · Informe de superficies y coordenadas | Linderos por parcela resultante (colindantes catastrales), superficie UTM y nota sobre la del terreno, tolerancias de cabida (10 %/5 %), datos del técnico, pie «no oficial» |
| AU-56 | Lector del XML del IVG/ICUC y apertura por CSV (mejora 32) | Sin datos personales en capas ni en memoria |
| AU-57 | Crear parcela desde coordenadas (TXT/CSV de levantamiento) | Nuevo: entrada habitual del topógrafo |
| AU-58 | Simulación del informe de identidad gráfica (±0,5 m urbana, ±2 m rústica, 5 % superficie) | Opcional, como ayuda previa al notario o al registro |
| AU-59 | WFS forales (Álava, Gipuzkoa, Bizkaia) solo para descargar y ver | Opcional; comprobar sus licencias antes |
| AU-60 | Publicación: escaneo de seguridad del repositorio de QGIS (desde 23/04/2026) | Sin `.bat` en el ZIP; revisar Bandit/detect-secrets |

Decisiones tomadas (no requieren consulta): viario y cesión → aviso «positivo condicionado» (AU-21); agregación →
aviso con el quíntuplo y mención del 80 % (AU-25); ED50 → aviso, no bloqueo (AU-32); BICE → aviso (AU-33).

## 3. Estado

| Bloque | Estado |
|---|---|
| A · Fiabilidad | ✅ 13/10/2026 (AU-01…AU-19; también AU-43 y parte de AU-40) |
| B · Normativa y avisos | ✅ 13/10/2026 (AU-20…AU-36). AU-31 solo en la comparación: las cajas de Navarra y del País Vasco cogen bordes de La Rioja, Burgos y Cantabria, así que no se bloquea al crear; AU-33 con Consulta_DNPRC, comprobado con parcelas reales: BICE = clase «BI» (Almaraz, aeropuerto de Málaga) y diseminado = RC urbana con vía «DS» (Murcia) |
| C · Robustez | Pendiente (siguiente) |
| D · Documentación | Pendiente (se avanza con cada bloque) |
| E · Fases pendientes | Pendiente (tras A-C; luego manual, usabilidad y publicación) |
