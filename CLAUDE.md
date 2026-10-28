# Notas de trabajo para Claude (no van en el ZIP del plugin)

Resumen de las reglas y del estado del proyecto para no perderlos entre conversaciones. Se actualiza en cada entrega.
Detalle del plan en `docs/DESARROLLO.md`; pendientes de usabilidad en `docs/USABILIDAD.md`; auditoría en
`docs/AUDITORIA.md`; pruebas en `docs/PLAN_PRUEBAS.md`.

## Forma de trabajar (acordada con Francisco)
- Claude decide e implementa; solo pregunta lo irreversible o los cambios grandes de diseño. Los cambios grandes de
  interfaz (p. ej. Parcela por pasos) se enseñan antes en capturas o maquetas.
- Opiniones sinceras con alternativas, no darle la razón por defecto. Soluciones automatizadas. Baterías de casos de
  todo; una prueba por función.
- Tras cada cambio: pruebas en QGIS 3.40 y 4.2 en el PC (TODO CORRECTO y registro limpio), CHANGELOG y documentación
  al día, y aviso corto en castellano: qué hay nuevo, qué probar a mano y los comandos git.
- Git para CMD de Windows, un comando por bloque: `cd /d C:\Users\Usuario\Documents\dev\CatastralGMLTools && …`.
  Commits en castellano, con `-m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"` y
  `-m "Claude-Session: https://claude.ai/code/session_01KsmgE6bxdpbGHsdP3uadVg"`.

## Reglas legales y de licencia
- GPL-2.0-or-later. No copiar código, textos, iconos ni diseño de fuentes sin licencia, propietarias o GPL-3
  (gmlweb, Check4SEC, ParCatGML, ATOMCPDownloader, ATNL).
- Sin marcas ni logotipos; sin apariencia oficial. Decir siempre que el plugin no es oficial.
- Solo datos públicos de fuentes oficiales, citadas («Dirección General del Catastro»; catastros forales con su
  licencia: Álava CC BY 4.0, Gipuzkoa CC BY-SA 3.0 ES, Bizkaia CC BY 3.0 ES, Navarra). Sin datos protegidos ni
  personales (en capas ni en memoria), sin scraping. Datos de prueba sintéticos.

## Reglas técnicas
- supportsQt6; lógica en `core/`, interfaz en `gui/`; QgsTask para lo largo.
- Señales conectadas a métodos (no lambdas); widgets con padre; iconos nativos de QGIS.
- Avisos solo en la barra de mensajes del panel (encima de las pestañas), nunca ventanas emergentes.
- Bandit: los `# nosec Bxxx` van solos, sin explicación en la misma línea.
- Términos: «Unir parcelas» (pestaña Parcela, une parcelas de una capa) y «1. Unir ficheros GML (multiparcela)»
  (Utilidades). Francisco prefiere «Unir» a «Juntar» (no es término SIG).

## Entorno
- Repositorio FGomezLosada/CatastralGMLTools. PC: `C:\Users\Usuario\Documents\dev\CatastralGMLTools`, QGIS 3.40.13 LTR
  y 4.2.2 en Windows. Copia en el contenedor: `/home/claude/CatastralGMLTools`.
- Pruebas locales: `QT_QPA_PLATFORM=offscreen python3.12 tools/run_tests.py [--una x.py]` y `ruff check .`
  (esperar a «RESULTADO GLOBAL»). Pruebas en el PC: `tools\probar.bat` (con `PB_SIN_PAUSA=1`, unos 12 min; resultado
  en `tests\resultados_qgis3.40.txt` y `…4.2.txt`); después el registro `HKCU\Software\QGIS` solo debe tener
  `QGIS-TEST` y `QGIS3`.
- Despliegue al PC: copiar a la salida y escribir con el puente con force; comprobar md5 (sin `\r`).
  `.github/workflows` no se puede escribir a distancia: se deja una copia `_nombre.yml` y Francisco la mueve.
- Las capas temporales que crea el plugin llevan atributos que las expliquen (se pueden guardar y consultar).
- Las fuentes en offscreen son más anchas que las reales: las pruebas de tamaño deben ser relativas.

## Estado (28/10/2026)
- Hecho: identidad gráfica en Validar (AU-58), País Vasco, guarda DOCTYPE, escaneo de seguridad en la publicación,
  U-03, U-05, U-06, panel sin caja gris y capas de identidad gráfica con atributos.
- Hecho el 28/10: punto 2, **Parcela por pasos (U-01/U-02)** (`parcela_pasos_test.py`). Esperando la prueba a mano.
- Siguiente: punto 3, **flujo guiado (U-07)** en la ayuda y quizá en la cabecera; quedan U-04, U-08, U-09.
- En espera: AU-56 (IVG con XML adjunto, falta un PDF real), AU-54 (división con pivote y puntos de apoyo),
  «doble GML» (ninguna fuente oficial; preguntar al COAM), campaña de pruebas a mano.
