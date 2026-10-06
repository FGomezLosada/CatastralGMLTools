# Historial de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versiones según [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

### Añadido
- `core/refcat.py`: comprobación de referencias catastrales de 14, 18 y 20 caracteres (limpieza de espacios y guiones, formato urbano o rústico, provincia y municipio en rústica, caracteres de control y cálculo de los que faltan) con aviso para Navarra y los territorios forales del País Vasco. Prueba `refcat_test.py` con referencias reales.
- `core/geometria.py`: preparación de recintos para el GML (coordenadas con 2 decimales y redondeo aritmético, cierre de anillos, vértices repetidos, exterior en sentido horario y huecos en antihorario, superficie al m², punto interior aunque el centroide caiga fuera, curvas densificadas con flecha menor de 2 cm, Z y M eliminadas), detección de parcelas multiparte y geometrías no válidas, SRC admitidos por la Sede, huso recomendado según la posición (incluida Canarias) y husos por provincia. Prueba `geometria_test.py`.
- `core/gml_parcela.py`: escritor del GML de parcela catastral (INSPIRE CadastralParcels 4.0): una o varias parcelas por fichero, namespace SDGC (con la referencia catastral) o LOCAL (identificador propio), superficie, fecha, label por defecto (urbana, rústica o LOCAL), punto de referencia interior, huecos y comprobaciones previas (SRC, identificadores repetidos o con caracteres no válidos, RC de territorio foral, parcelas multiparte). Si hay errores no se escribe el fichero. Prueba `gml_parcela_test.py`. Comprobado contra los esquemas XSD oficiales (WFS 2.0 + INSPIRE CP 4.0).
- Pestaña **Parcela** (`gui/pestana_parcela.py`, `core/capa_parcelas.py`): crea el GML de parcela desde una capa de polígonos (toda o solo la selección). Propone el campo de referencia catastral, numera las parcelas sin identificador, propone SDGC o LOCAL y el número de parcela, y permite cambiarlos en la tabla. Superficie de cada parcela y resumen, fecha, SRC automático según la posición (o elegido) con transformación de la capa, fichero de destino, estado de cada fila tras crear el GML, resultado en la barra del panel con los botones «Abrir carpeta» y «Cargar en el mapa». Al elegir filas se seleccionan las parcelas en la capa. Prueba `parcela_ui_test.py`.
- Pestaña Parcela: al cambiar el identificador de una fila se proponen de nuevo su namespace y su número de parcela (si no lo ha escrito el usuario), y la superficie de la tabla se calcula como en el GML, con las coordenadas redondeadas al centímetro (antes podía diferir en 1 m²). Detectado en la primera prueba real en QGIS 4.2.
- GML de parcela: la raíz declara `xmlns:xlink`. Sin esa declaración la Sede Electrónica rechaza el fichero («no cumple el esquema Inspire GML») aunque sea válido contra los esquemas públicos; causa aislada con ficheros de control subidos a la Sede.
- Pestaña Parcela: el panel tardaba mucho en abrirse (QGIS «No responde») con una capa grande en el proyecto, porque se calculaban todas sus parcelas. Ahora empieza por la capa activa, no carga capas de más de 100 parcelas (pide seleccionarlas y, si ya hay selección, la usa), la tabla sigue la selección del mapa y se calcula una sola vez al cambiar de capa.
- Pestaña Parcela: tras dividir una parcela (todos los trozos copian su referencia), el trozo mayor conserva la referencia catastral (SDGC) y los demás se proponen como `Seg_1`, `Seg_2`… (LOCAL). El fichero de salida se propone con el nombre de la capa, sin espacios ni símbolos, y cambia al cambiar de capa salvo que el usuario haya elegido el suyo.
- Primera validación real en la Sede Electrónica del Catastro (06/10/2026): un GML de segregación creado con el plugin se carga correctamente.
- `core/incidencias.py`: avisos y errores comunes que devuelven las funciones de `core/` para que el panel los muestre.

## [0.1.0] - 2026-10-06

### Añadido
- Fase 0: investigación de formatos, servicios y condiciones de uso del Catastro y de las licencias de los plugins y webs de referencia (`docs/INVESTIGACION.md`) y plan de desarrollo (`docs/DESARROLLO.md`).
- Esqueleto del plugin: botón en la barra de herramientas y entrada en el menú Vectorial; panel con las pestañas Parcela, Edificio, Validar, Descargar, Dividir y Utilidades (con iconos nativos de QGIS); aviso legal de herramienta no oficial siempre visible; cita de la fuente de los datos; barra de avisos dentro del panel; ayuda local; icono propio en SVG.
- Detección de los territorios con catastro propio (Navarra, Álava/Araba, Gipuzkoa, Bizkaia).
- Pruebas automáticas (`tools/run_tests.py`, `tools/probar.bat`) y empaquetado (`tools/package.py`).
- Licencia GPL-2.0-or-later, README bilingüe, CREDITS.md, plantillas de issues y Action de publicación por etiqueta.

### Corregido
- El panel no se abría en QGIS 4 (PyQt6): los espaciadores del .ui no tenían tamaño. La prueba de empaquetado lo comprueba ahora en todas las versiones.
