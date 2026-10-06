# Historial de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versiones según [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

### Añadido
- `core/refcat.py`: comprobación de referencias catastrales de 14, 18 y 20 caracteres (limpieza de espacios y guiones, formato urbano o rústico, provincia y municipio en rústica, caracteres de control y cálculo de los que faltan) con aviso para Navarra y los territorios forales del País Vasco. Prueba `refcat_test.py` con referencias reales.
- `core/geometria.py`: preparación de recintos para el GML (coordenadas con 2 decimales y redondeo aritmético, cierre de anillos, vértices repetidos, exterior en sentido horario y huecos en antihorario, superficie al m², punto interior aunque el centroide caiga fuera, curvas densificadas con flecha menor de 2 cm, Z y M eliminadas), detección de parcelas multiparte y geometrías no válidas, SRC admitidos por la Sede, huso recomendado según la posición (incluida Canarias) y husos por provincia. Prueba `geometria_test.py`.
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
