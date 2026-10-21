# Plan de pruebas por casos

Objetivo: que los usuarios no encuentren errores ni cosas que no entiendan. Cada herramienta del plugin tiene una
**batería de casos** (`tests/<herramienta>_casos_test.py`) con los problemas que se pueden dar, no solo el caso
normal. La batería busca los fallos de hoy y deja escritos los de mañana: si un cambio futuro rompe algo, la prueba
lo dice antes que el usuario.

## 1. Reglas

1. **Una herramienta no está terminada sin su batería**, y la batería pasa en QGIS 3.40 y 4.2 (`tools\probar.bat`).
   Vale para las nuevas y para las que ya existen (sección 4).
2. **Cada fallo que se encuentre a mano se convierte en un caso** de la batería antes de corregirlo (así no vuelve).
3. **Ningún caso puede romper la herramienta**: una excepción es un fallo aunque el caso sea absurdo. Lo absurdo debe
   dar un mensaje claro en el panel, no un error de Python ni una ventana.
4. **Los mensajes también se prueban**: que digan qué pasa y qué hacer, en castellano y sin cortarse.
5. Las pruebas no usan internet: los servicios del Catastro y del IGN están simulados (`tests/simulador_catastro.py`),
   también caídos, en mantenimiento, lentos o devolviendo algo inesperado.

## 2. Qué se prueba en cada herramienta (lista común)

Cada batería recorre las categorías que le apliquen:

| Categoría | Casos |
|---|---|
| Ficheros de entrada | esquema 3.0 / 4.0 / genérico de QGIS / BU; otro huso, geográficas (lat-lon y lon-lat), sin srsName; con Z; 2, 3 o 9 decimales; ISO-8859-1 y UTF-8 con BOM; vacío, mal formado, que no existe, que no es GML, enorme; ruta con espacios, acentos o en una carpeta de solo lectura |
| Geometría | inválida (pajarita), anillo abierto, vértices repetidos, orientación al revés, huecos, varios recintos, minúscula (< 1 m²), enorme, curvas (gml:Arc), coordenadas ilegibles (coma decimal) |
| Datos | identificadores vacíos, repetidos, con espacios o símbolos; RC con letras de control mal; namespace raro; superficie declarada que no cuadra |
| Capas de QGIS | capa vacía, sin selección, en otro SRC, geográfica, con campos que faltan, editándose, borrada a mitad, de otro proveedor (shape, GeoPackage, memoria) |
| Red | sin internet, mantenimiento de la Sede, respuesta lenta (cancelar), respuesta inesperada (HTML, XML de error), parcela que no existe |
| Interacción | doble clic, cancelar, cerrar el panel o el plugin a mitad, cambiar de pestaña, Ctrl+Z, arrastrar y soltar (sobre las casillas), proyecto nuevo, mapa en otro SRC |
| Resultado | fichero que la Sede aceptaría (validador del plugin y XSD), no sobrescribe el original, informe legible, mensajes claros |

## 3. Estado por herramienta

| Herramienta | Batería | Estado |
|---|---|---|
| Utilidades «5. Comparar dos GML» | `comparar_casos_test.py` (29 casos) | ✅ 19/10/2026 |
| Validar: lectura del GML y comprobaciones | `validar_casos_test.py` (38 ficheros + «Reparar» + pestaña) | ✅ 19/10/2026: faltaba avisar de vértices repetidos seguidos (ANILLO-REPETIDO, ahora reparable) |
| Validar: comparación con el Catastro | `comparacion_casos_test.py` (44 casos) | ✅ 19/10/2026: una RC inexistente en un GML de edificio decía «no se ha podido comparar»; si la red caía a mitad, una referencia se daba por inexistente; con geometría inválida, GEOS fallaba por dentro |
| Parcela: crear GML desde una capa y asistente de alteraciones | `parcela_casos_test.py` (25 capas + interacción) | ✅ 19/10/2026: quitar la capa en uso pasaba a otra sin avisar; mensajes de astilla y de elemento sin geometría que no se entendían; más de 30 parcelas sin aviso al crear |
| Parcela: dividir y unir seleccionadas | `division_casos_test.py` (9 formas × modos × valores × lados: 1404 divisiones; unión con rendijas, huecos y patios) | ✅ 19/10/2026 |
| Edificio: GML de construcciones (ICUC) | `edificio_casos_test.py` (20 capas + sin referencia) | ✅ 19/10/2026 |
| Descargar: por referencia y en el mapa | `descargar_casos_test.py` (22 casos + pestaña) | ✅ 19/10/2026: una RC inexistente decía «…no se ha encontrado la parcela X para el huso 25830» (el huso confundía) |
| Utilidades «1. Unir GML» | `unir_casos_test.py` | ✅ |
| Utilidades «2. Convertir a 4.0 o reparar» | `conversor_casos_test.py` | ✅ |
| Utilidades «3. Informe de superficies» | `superficies_casos_test.py` | ✅ |
| Utilidades «4. Ajustar a la cartografía catastral» | `ajuste_casos_test.py` | ✅ |
| Panel: avisos, pestañas, cerrar y recargar | `panel_casos_test.py` | ✅ |
| Ficheros rotos a mano (cualquier carácter quitado, de más o cortado) | `xml_roto_casos_test.py` | ✅ |
| Utilidades «6. Parcela desde coordenadas» (AU-57) | `coordenadas_casos_test.py` | ✅ |
| Validar: simulación de identidad gráfica en la comparación con el Catastro (AU-58) | `identidad_casos_test.py` | ✅ |

Las pruebas que ya hay (`*_test.py`) cubren el uso normal y los fallos encontrados hasta ahora; las baterías añaden
los casos de la sección 2 que falten.

## 4. Orden

Primero lo que recibe ficheros o capas de cualquier origen (es donde más cosas raras entran), después lo que depende de
la red y al final lo que trabaja sobre lo ya comprobado:

1. Validar (lectura y comprobaciones) y su comparación con el Catastro.
2. Parcela (crear GML, alteraciones, dividir, unir) y Edificio.
3. Descargar.
4. Utilidades 1 a 4 y el panel.

Las herramientas nuevas (lector del IVG, parcela desde coordenadas…) se hacen ya con su batería.

## 5. Campaña final a mano

Lo que no se puede automatizar es si se **entiende**: textos, orden de los pasos, aspecto en otra pantalla. Antes de
publicar:

- recorrido completo de cada flujo real (segregación, división, agregación, ICUC, cartografía desplazada) con ficheros
  del curso, hasta la validación en la Sede;
- prueba con **personas que no hayan visto el plugin** (alumnos o compañeros), con una tarea y sin explicaciones, apuntando
  dónde dudan: cada duda es un texto o un paso que cambiar;
- pantallas pequeñas, segundo monitor, tema oscuro de QGIS, QGIS en inglés.

## 6. Cómo se ejecutan

`tools\probar.bat` (las dos versiones) o `tools\probar.bat validar_casos_test.py` (una). Cada batería imprime un caso
por línea (OK / FALLO); si algo lanza una excepción, se imprime la traza del caso.
