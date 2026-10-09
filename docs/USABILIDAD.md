# Revisión de usabilidad (pendiente)

Lista de lo que confunde o complica el uso, recogida en las pruebas a mano. Se resolverá en la **fase de revisión de
usabilidad**, cuando estén terminadas todas las funciones y el manual con capturas reales: así se puede reorganizar el
panel de una vez, viéndolo entero, en lugar de parchearlo pieza a pieza.

| Nº | Dónde | Qué confunde | Idea para resolverlo |
|---|---|---|---|
| U-01 | Parcela | Demasiadas opciones a la vez: capa, campos, alteración, tabla, unir, fecha, SRC y fichero | Orden por pasos (1 capa → 2 operación → 3 revisar → 4 crear) y «Opciones avanzadas» plegables (nº de parcela, fecha, SRC) |
| U-02 | Parcela | La alteración se aplica a todas las filas de la capa; si la capa tiene más parcelas que las de la operación (p. ej. «Colindantes»), salen nombres como Agrupa_1, Agrupa_2, Agrupa_3 | Trabajar siempre con las parcelas de la operación (selección) o pedirlas explícitamente. Parche del 09/10/2026: tras «Unir seleccionadas» la tabla pasa a mostrar solo la parcela unida |
| U-03 | Parcela y Utilidades | Dos «unir» distintos: «Unir seleccionadas» (parcelas de una capa) y «Unir GML» (ficheros, multiparcela) | Nombres distintos («Unir parcelas» / «Juntar ficheros GML») y explicar cuándo se usa cada uno |
| U-04 | Mapa | Capas temporales (descarga, «vista del GML») frente al fichero GML que se sube a la Sede | Mensaje claro en cada paso; quizá no cargar vistas temporales salvo que se pidan |
| U-05 | Validar | Textos largos en la lista de incidencias | Texto corto en la lista y explicación completa al pasar el ratón o en el informe |
| U-06 | Descargar | Los grupos «Catastro <RC>» se acumulan en el proyecto | Opción de sustituir la descarga anterior o agrupar todas bajo «Catastral GML Tools» |
| U-07 | General | No hay un recorrido guiado del trabajo habitual (descargar → dividir o unir → crear GML → validar → Sede) | Sección «Flujo de trabajo» al principio del manual y, quizá, en la cabecera del panel |
| U-08 | Edificio | La pestaña admitía cualquier capa de polígonos (se eligió la de la parcela como si fuera la huella) y, si la parcela no tiene construcciones en el Catastro, no quedaba claro qué hacer | Parche del 09/10/2026: se rechazan las capas de parcelas y el botón «Dibujar huellas» crea la capa y activa el dibujo. En la revisión: quizá un asistente «1 parcela → 2 huellas → 3 crear» |
