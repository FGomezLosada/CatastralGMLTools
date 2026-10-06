# Historial de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versiones según [SemVer](https://semver.org/lang/es/).

## [0.1.0] - 2026-10-06

### Añadido
- Fase 0: investigación de formatos, servicios y condiciones de uso del Catastro y de las licencias de los plugins y webs de referencia (`docs/INVESTIGACION.md`) y plan de desarrollo (`docs/DESARROLLO.md`).
- Esqueleto del plugin: botón en la barra de herramientas y entrada en el menú Vectorial; panel con las pestañas Parcela, Edificio, Validar, Descargar, Dividir y Utilidades (con iconos nativos de QGIS); aviso legal de herramienta no oficial siempre visible; cita de la fuente de los datos; barra de avisos dentro del panel; ayuda local; icono propio en SVG.
- Detección de los territorios con catastro propio (Navarra, Álava/Araba, Gipuzkoa, Bizkaia).
- Pruebas automáticas (`tools/run_tests.py`, `tools/probar.bat`) y empaquetado (`tools/package.py`).
- Licencia GPL-2.0-or-later, README bilingüe, CREDITS.md, plantillas de issues y Action de publicación por etiqueta.

### Corregido
- El panel no se abría en QGIS 4 (PyQt6): los espaciadores del .ui no tenían tamaño. La prueba de empaquetado lo comprueba ahora en todas las versiones.
