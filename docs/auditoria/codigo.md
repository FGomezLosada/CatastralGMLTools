# Auditoría de código · Catastral GML Tools (estado del 09/10/2026)

**Alcance.** He leído `docs/DESARROLLO.md`, `docs/INVESTIGACION.md`, `help/index.html`, README, CREDITS, LICENSE, `metadata.txt` y todo el código: el plugin, el panel y su `.ui`, `core/`, `gui/`, `tests/` y `tools/`.

**Entorno de prueba.** QGIS 3.34.4 con Python 3.12, sin ventana. QGIS 4 no está instalado aquí, así que lo relativo a Qt6 se ha revisado solo leyendo el código.

**Resultados de partida.**
- `tools/run_tests.py`: 19 de 19 pruebas en OK.
- `ruff check .`: sin avisos.
- Nota: al lanzar las pruebas se reescribió `tests/resultados_qgis3.34.txt`, un fichero que ya ignora `.gitignore`. No he cambiado nada más del repositorio.

**Experimentos.** Los scripts están en `scratchpad/exp_codigo/` (`e1_…py` a `e13_…py`). Cargan el paquete igual que `run_tests.py` y, cuando hace falta red, usan `tests/simulador_catastro.py`.

**Etiquetas de cada hallazgo:**
- **[REPRODUCIDO]**: comprobado con un experimento.
- **[CÓDIGO]**: deducido leyendo el código, sin poder reproducirlo aquí (por ejemplo, porque necesita la red real o Windows).

---

## CRÍTICO

### C1. La pestaña Validar aplica a un fichero los resultados de las tareas lanzadas para otro, y puede llegar a decir «Listo para el ICUC» de un fichero que no se ha comparado [REPRODUCIDO, e3_carrera.py]
**Dónde:**
- `gui/pestana_validar.py:207-244`: `abrir` no invalida las tareas en marcha.
- `:337-344`: `esquema_comprobado`.
- `:362-394`: `comparado`.
- `:424-426` y `:446-448`: los `finished` de las dos tareas.

**Escenario:**
1. Se abre `A_edificio.gml`, que está dentro de la parcela, y se pulsa «Comparar con el Catastro».
2. Mientras la tarea sigue en marcha, se abre `B_edificio.gml`, que está 50 m fuera de la parcela (por arrastre o por «Validar» desde la pestaña Edificio).
3. Termina la tarea de A. `comparado()` añade su resultado al informe de B y añade al mapa la capa «Comparación B».

**Resultado obtenido:**
- Incidencias de B: `[('info','CMP-BU-DENTRO')]`.
- Mensaje verde: «Construcciones dentro de la parcela 1907401VK4810H. Listo para el ICUC: … suba **B_edificio.gml**».
- Si se compara B de verdad, sale `CMP-BU-FUERA`.

**Lo mismo con el XSD:**
- Al abrir B se lanza una segunda `TareaEsquema` sin cancelar la de A.
- El resultado de A (`XSD-VALIDO` o sus errores) se suma al informe de B.
- Además, `self.tarea = None` se pone en cuanto llega la primera tarea, así que la lista deja de mostrar «Comprobando…» aunque la de B siga en marcha.

**Corrección:**
- Que cada tarea guarde la ruta y una «generación» (un contador que `abrir()` incrementa).
- En `finished`, descartar el resultado si `tarea.generacion != pestana.generacion` o si `tarea.ruta != pestana.ruta`.
- En `abrir()`, cancelar las tareas anteriores (`tarea.cancel()`).
- Hacer que `run()` consulte `isCanceled()`.
- Prueba: abrir A, comparar, abrir B, terminar la tarea de A y comprobar que B queda sin incidencias CMP.

### C2. «Comparar con el Catastro» dice «contorno coincidente (±1 cm)» cuando hay desplazamientos de 2 a 6 cm, en parcelas y en edificios [REPRODUCIDO, e2_tolerancia.py y e12_icuc.py]
**Dónde:**
- `core/comparacion.py:31-32`: `TOLERANCIA = 0.01` y `AREA_MINIMA = 0.05`.
- `:129-170`: parcelas.
- `:252-272`: edificios.

**Causa.** La tolerancia se aplica como un buffer de ±1 cm. Después se descarta toda diferencia de menos de 0,05 m². Una tira de 4 cm × 1 m (0,04 m², o 0,03 m² tras restar el buffer) desaparece. La FAQ de la DGC habla de ±1 cm **por vértice**, sin margen de superficie.

**Resultados** (segregación de una parcela de 20 × 30 m sobre el simulador):

| Caso | Resultado del plugin |
|---|---|
| Vértice NE desplazado 2 cm hacia el vecino | `CMP-CONTORNO-OK`, NPO 1 |
| Tramo de 2 m del lindero desplazado 3 cm | `CMP-CONTORNO-OK` |
| Entrante hacia dentro de 4 cm × 1 m | `CMP-CONTORNO-OK` |
| Edificio que sobresale 3, 4 o 6 cm × 1 m de la parcela | `CMP-BU-DENTRO` y, en el panel, «Listo para el ICUC» |

Es justo el peor caso: el plugin da por bueno algo que la Sede, con ±1 cm, previsiblemente no aceptará.

**Corrección:**
- Medir distancias, no superficies. Por ejemplo, `hausdorffDistance` entre los contornos (`union.convertToType(Line)` frente a `union_origen` como línea) mayor que 0,01 m implica error.
- O comprobar vértice a vértice: la distancia de cada vértice del GML al contorno de origen, y la de cada vértice de origen al contorno del GML, ha de ser ≤ 0,01 m.
- Para «afectada en parte» y para el ICUC: `difference(...)` sin descartar por superficie y, si el resto no está vacío, medir su anchura máxima (por ejemplo, `poleOfInaccessibility` del resto > 0,005 m) en lugar del área.
- Ajustar `AREA_MINIMA` solo para el ruido numérico (< 1e-4 m²).
- Añadir pruebas con desplazamientos de 0,5 cm (OK), 1,5 cm, 3 cm y 5 cm (error).

---

## ALTO

### A1. Una parcela no modificada (idéntica a la catastral) sale en verde como «Subsanación de discrepancias» [REPRODUCIDO, e11_identica.py]
**Dónde:** `core/comparacion.py:101-104` y `:165-170`.

**Escenario y resultado:** un GML con la parcela descargada sin cambios, en SDGC, da `CMP-CONTORNO-OK` y la operación «Subsanación de discrepancias», todo en verde. Según `INVESTIGACION.md §1.3`, la Sede da **error** si una parcela aportada es idéntica a su parcela de origen. La mejora 14 lo cita («parcelas sin cambios»), pero no está implementado.

**Corrección:**
- Por cada propuesta SDGC, buscar su homóloga en `afectadas` por `local_id`.
- Si la distancia de Hausdorff entre ambas es ≤ 0,01 m:
  - si todas están sin cambios, `ERROR CMP-SIN-CAMBIOS`;
  - si solo algunas, un aviso que las identifique.

### A2. Se aceptan como SDGC referencias en minúsculas o con guion o punto, y se escriben tal cual en `localId` y en `gml:id`; el validador las da por buenas [REPRODUCIDO, e1_ids.py]
**Dónde:**
- `core/gml_parcela.py:41` (`LOCAL_ID_VALIDO` admite `-` y `.`) y `:146-162`.
- `core/validador.py:47` y `:121-134`.
- `refcat.es_rc_parcela` limpia antes de comprobar.
- `gui/pestana_parcela.py:434-442` y `:466`: lo que se escribe en la tabla no se normaliza.

**Escenario:** se escribe en la tabla `9872023vh5797s`, `9872023-VH5797S` o `9872023.VH5797S`. El namespace pasa solo a SDGC, el GML se crea sin errores y el validador sale sin errores ni avisos.

**Resultado en el fichero:**
- `<localId>9872023vh5797s</localId>`, mientras que `nationalCadastralReference` sí va limpia.
- La Sede busca la RC por `localId`: la parcela no se reconoce como la catastral.
- `comparacion.py:178` consulta además el WFS con la referencia sin limpiar.

**Corrección:**
- Con SDGC, exigir que `local_id == refcat.limpiar(local_id)` y que tenga el formato urbano o rústico. Si no, error `NS-SDGC-RC-FORMATO` en el escritor y en el validador.
- En la tabla, normalizar el identificador cuando es una RC: `refcat.limpiar` y mayúsculas.

### A3. La pestaña Parcela sobrescribe sin aviso el fichero del que sale la capa [REPRODUCIDO, e8_sobrescribe.py]
**Dónde:**
- `gui/pestana_parcela.py:225-236` (`proponer_fichero`) y `:514-529`.
- Lo mismo en `gui/pestana_edificio.py:197-204`, aunque allí el sufijo `_edificio` lo hace menos probable.

**Escenario:**
1. El usuario añade al proyecto `C:\exp\parcela.gml` (un GML ajeno o uno anterior), que se abre con OGR y queda como capa «parcela».
2. El proyecto está guardado en `C:\exp`.
3. La pestaña propone como destino `C:\exp\parcela.gml`, que es el mismo fichero.
4. «Crear GML» lo sobrescribe sin preguntar, y el `.gfs` de GDAL queda desfasado.

**Resultado obtenido:** `destino == origen: True` y `fichero de origen sobrescrito: True`.

**Corrección:**
- No proponer nunca una ruta igual a `capa.source().split('|')[0]`: añadir sufijo `_sede` o `_v2`.
- Antes de escribir, si el fichero existe:
  - y es la fuente de alguna capa del proyecto, error;
  - en otro caso, aviso en la barra con un botón «Sobrescribir».
- Escribir en un temporal y hacer `os.replace` al final (escritura atómica).

### A4. Volver a descargar una parcela borra las capas de su grupo con las ediciones sin guardar [REPRODUCIDO, e9_redescarga.py]
**Dónde:** `gui/pestana_descargar.py:364-368`, en `cargar_descarga`.

**Escenario:**
1. Se descarga una parcela.
2. Se divide la capa «Parcela …» (en edición y sin guardar, como propone la ayuda: «Es una copia para trabajar…, para dividir la parcela»). También vale haber usado «Unir seleccionadas».
3. Se vuelve a descargar la misma referencia, por ejemplo para ver las colindantes.

**Resultado:** `proyecto.removeMapLayers(...)` elimina la capa editada sin preguntar. La pestaña Parcela pierde la capa y el trabajo se pierde.

**Corrección:**
- No borrar capas modificadas (`isModified()` o `isEditable()`) ni capas añadidas por el usuario al grupo.
- O renombrar el grupo viejo a «Catastro RC (anterior)».
- O avisar en la barra con un botón «Sustituir».

### A5. El lector lanza excepciones con GML anómalos, y el informe HTML falla con anillos degenerados [REPRODUCIDO, e4_lector.py]
**Dónde:**
- `core/gml_lector.py:125-128` (`int(srsDimension)` y `float(v)`).
- `:134` (`gml:pos` con una sola coordenada).
- `:142`.
- `:172`: `geometria_de` desempaqueta `x, y`.
- `core/informe.py:55`: `pointOnSurface().asPoint()` sobre una geometría nula.

**Casos y resultado:**

| Caso | Resultado |
|---|---|
| Coma decimal (`421500,00`) | `ValueError` |
| `srsDimension="dos"` | `ValueError` |
| `gml:pos` con una sola coordenada | `ValueError: not enough values to unpack` |
| Anillo de 2 vértices: lector y validador | Bien (`ANILLO-VERTICES`, `GEO-INVALIDA`) |
| Anillo de 2 vértices: «Informe» | `ValueError: Null geometry cannot be converted to a point` |

La docstring dice «nunca lanza excepciones». Todas estas llamadas se hacen en el hilo principal, desde slots:
- `PestanaValidar.abrir`;
- `PestanaUtilidades.unir` (pasa por `unir.reunir`);
- `crear_informe`, que solo captura `OSError`.

En QGIS eso abre el diálogo de error de Python, con lo que se incumple la regla de «nada de ventanas» y el panel queda a medias.

**Corrección:**
- Envolver `_leer_parcela` y `_leer_construccion` en `try/except (ValueError, TypeError, IndexError)`. Ante un fallo, devolver un `ElementoGML` con geometría vacía y `Incidencia(ERROR, 'COORDENADAS', …)`.
- Validar `srsDimension` con `isdigit()`.
- En `croquis_svg`, saltar los elementos cuyo `pointOnSurface()` sea nulo.
- En `crear_informe`, capturar también `Exception` y mostrarla con `dock.warn`.

### A6. Una capa cuyas coordenadas no encajan con su SRC, con el SRC del GML elegido a mano, rompe las pestañas Parcela y Edificio con una excepción [REPRODUCIDO, e7_src.py]
**Dónde:**
- `core/geometria.py:84` (`Decimal(repr(inf))` lanza `InvalidOperation`), a través de `transformar()`, que devuelve coordenadas `inf` sin avisar.
- `core/capa_parcelas.py:116` y `core/capa_edificios.py:206`.
- Llamadas desde `actualizar_superficies` al cambiar de capa.

**Escenario:** un DXF, o un shape sin `.prj`, con coordenadas UTM que QGIS asigna a EPSG:4326, y en el combo de SRC EPSG:25830 elegido a mano.

**Resultado:** traza en `pestana_parcela.py:223 → 320 → 341 → capa_parcelas.py:116 → geometria.py:185 → 118 → 84` y diálogo de error de Python. En Edificio, `src_incorrecto()` solo se comprueba al pulsar «Crear»: `recargar()` ya ha fallado antes. Con «Automático» no ocurre, porque `epsg_para` devuelve `None`.

**Corrección:**
- En `transformar()`, capturar `QgsCsException` y comprobar `math.isfinite` en el `boundingBox()` del resultado. Si falla, devolver `None` y añadir `Incidencia(ERROR, 'SRC-TRANSFORMACION')`.
- En `preparar()`, rechazar coordenadas no finitas.
- En las pestañas, comprobar `src_incorrecto()` (generalizado a cualquier SRC) antes de calcular superficies.

---

## MEDIO

### M1. El escritor de parcelas no comprueba solapes ni huecos: «GML creado» sale en verde para un fichero que la Sede rechaza [REPRODUCIDO, e6_varios.py]
**Dónde:** `core/gml_parcela.py:132-166` y `gui/pestana_parcela.py:529-544`.

**Escenario y resultado:** dos parcelas que se solapan 50 m² dan `escrito: True` y solo incidencias `GEO-ORIENTACION`. El usuario tiene que acordarse de pasar por Validar; la ayuda (Parcela) solo cita multiparte, identificador repetido y SDGC sin RC.

**Corrección:** llamar a `validador.validar_conjunto()` sobre los recintos ya preparados. Hacer el solape un error que impida crear el fichero y el hueco un aviso que pinte el mensaje en naranja.

### M2. GML de edificio: el escritor acepta partes que se solapan y el validador rechaza partes contiguas [REPRODUCIDO, e5_edificio.py]
**Dónde:**
- `core/gml_edificio.py:183-191`: cada parte se valida por separado y se quita `GEO-MULTIPARTE`.
- `core/validador.py:171-175`: valida el multipolígono entero con GEOS.

**Resultados:**
- Dos partes solapadas: «escrito», pero el validador da `GEO-INVALIDA`.
- Dos partes que comparten un lado: «escrito», y el validador da `GEO-INVALIDA`. Es un falso error: los `PolygonPatch` de una `gml:Surface` son, por definición, contiguos.

**Corrección:**
- En el escritor, error si las partes se solapan con área > 0, comprobado con `intersection` por pares.
- En el validador, en los edificios, validar cada recinto por separado y comprobar solapes entre partes, en lugar de `isGeosValid()` sobre el multipolígono.
- Decidir con la Sede si las partes que se tocan se deben fusionar.

### M3. «Listo para el ICUC» aparece aunque el XSD no se haya comprobado o siga en marcha [CÓDIGO]
**Dónde:** `gui/pestana_validar.py:387-391`.

**Causa:** la condición solo mira que no haya errores. Se dan los dos casos siguientes:
- La comparación termina antes que el XSD. La primera vez hay que descargar unos 80 esquemas, así que es lo normal. Se muestra «Listo» y los errores XSD llegan después.
- Sin lxml, o sin conexión para los esquemas, el XSD queda como `XSD-SIN-LXML` o `XSD-SIN-COMPROBAR`, que son avisos, y aun así sale «Listo».

La ayuda dice que «Listo» exige que no haya errores en Validar, incluido el XSD.

**Corrección:** exigir `XSD-VALIDO` en `informe.incidencias` y que `self.tarea is None`. Si no se cumple, mensaje naranja: «Comparación correcta; falta comprobar el esquema XSD».

### M4. Validar bloquea QGIS con ficheros grandes: el validador es O(n²) y corre en el hilo principal [REPRODUCIDO, e10_rend.py]
**Dónde:** `core/validador.py:205-211`, llamado desde `pestana_validar.py:219`.

**Tiempos medidos:**

| Parcelas | Tamaño | Leer | Validar |
|---|---|---|---|
| 1.600 | 2,8 MB | 0,2 s | 1,6 s |
| 4.900 | 8,6 MB | 0,7 s | 15,2 s |

Con un GML de manzana o de municipio, QGIS se queda «No responde» durante minutos. Es el mismo problema que E-12 resolvió en la pestaña Parcela.

**Corrección:**
- Usar `QgsSpatialIndex` para los pares candidatos.
- Mover lectura y validación a una `QgsTask`.
- Limitar `validar_conjunto` a N ≤ 500 y avisar por encima.

### M5. El mapa de fondo crea capas WMS en el hilo principal, y la descarga de capacidades es síncrona [CÓDIGO, no reproducible sin red real]
**Dónde:**
- `gui/fondo.py:345`: `QgsRasterLayer(..., 'wms')`.
- Llamado desde `pestana_descargar.py:196` (en `descargada`) y `:249` (al pulsar «Elegir en el mapa»).

**Escenario:** red lenta o un servicio WMS caído. Cada capa espera al timeout de red de QGIS (60 s por defecto) y hay 3 capas, lo que da hasta unos 3 minutos con la interfaz bloqueada. Incumple «nunca bloquear la interfaz».

**Corrección:**
- Crear las capas con `QgsRasterLayer.LayerOptions` y `skipCrsValidation`, o comprobar las capacidades antes en una `QgsTask` con `QgsBlockingNetworkRequest`.
- Recordar en la sesión que el servicio no responde.
- Desmarcar «Mapa de fondo» si falla.

### M6. Las tareas de red no se pueden cancelar y no tienen límite de tiempo propio [CÓDIGO]
**Dónde:**
- `core/servicios.py:144-152`: `pedir()` llama a `red.get(peticion, True)` sin `feedback`.
- `gui/pestana_descargar.py:326-331` y `gui/pestana_validar.py:416-422` y `:439-444`: `run()` no consulta `isCanceled()`.
- `core/comparacion.py:75-81`: hasta 25 peticiones.
- `core/servicios.py:403`: hasta 60 peticiones `Consulta_DNPRC` en serie.
- `catastral_gml_tools.py:41-55`: `unload()` no cancela las tareas.

**Escenario:** con el servicio lento, una descarga con 60 consultas DNPRC puede tardar muchos minutos.
- «Cancelar» en el gestor de tareas no hace nada.
- El botón «Descargar» sigue desactivado (`self.tarea is not None`) hasta que la tarea acaba.
- Si se recarga el plugin, las tareas siguen vivas con el código antiguo.

**Corrección:**
- Pasar un `QgsFeedback` a `QgsBlockingNetworkRequest.get()`, enlazado a la tarea mediante `taskTerminated` o `progressChanged`.
- Consultar `isCanceled()` entre peticiones.
- Fijar un timeout propio (por ejemplo, `QgsNetworkAccessManager.setTimeout` o un control del tiempo total).
- Cancelar las tareas en `cleanup()`.

### M7. Huso UTM: `comprobar_src` y `HUSOS_PROVINCIA` están escritos y probados, pero nadie los usa [CÓDIGO]
**Dónde:**
- `core/geometria.py:295-316`: no se llama desde ninguna pestaña ni desde el validador.
- `core/capa_parcelas.py:97-105`: `epsg_para` devuelve el SRC de la capa si es uno de los admitidos, aunque la parcela esté en otro huso.

**Escenario:** una parcela de A Coruña dibujada en una capa EPSG:25830. El GML sale en 25830 sin ningún aviso, y el validador tampoco lo detecta. INVESTIGACION §1.3 bis asigna a A Coruña solo el 25829.

**Corrección:**
- Llamar a `comprobar_src(capa.crs(), unión, provincia de la RC SDGC)` en las pestañas Parcela y Edificio y mostrar el resultado en el resumen.
- En el validador, añadir `SRC-HUSO` usando `epsg_recomendado` sobre la unión de las geometrías.
- Con «Automático», usar el huso de la posición o de la provincia, no el de la capa.

### M8. Unir GML: dos ficheros con `Seg_1` (el nombre que el propio plugin propone) no se pueden unir [REPRODUCIDO, e6_varios.py]
**Dónde:** `core/unir.py:51-67`.

**Escenario:** dos segregaciones independientes, cada una con su `Seg_1`, que es el caso E-20. Resultado: `ok=False` con `UNIR-ID-DISTINTO`, sin ofrecer solución.

**Corrección:** si el identificador está repetido y es LOCAL, renombrarlo automáticamente (`Seg_1` → `Seg_1_b`, o con el prefijo del fichero) con una incidencia `INFO`. Mantener el error solo para SDGC.

**Además, en el mismo módulo:**
- `:58`: un namespace desconocido se convierte en LOCAL sin avisar.
- `:96`: la comparación de rutas con `abspath` distingue mayúsculas en Windows. En el experimento, `C:/x/A.gml` frente a `c:/x/a.gml` da `False`. Usar `os.path.normcase` o `os.path.samefile`.

### M9. La caché de esquemas XSD puede quedar «envenenada» para siempre [CÓDIGO]
**Dónde:** `core/esquemas.py:49-66`.

**Causa:**
- Cualquier respuesta que empiece por `<` se guarda en caché, también una página HTML de un proxy o portal cautivo, o de un error servido con código 200.
- La escritura no es atómica: dos validaciones a la vez, o un cierre de QGIS a medias, pueden dejar un XSD truncado.

**Consecuencia:** a partir de entonces el resultado es siempre `XSD-ESQUEMA` («No se han podido cargar…»). El fallo va en la dirección segura (nunca dice «válido»), pero no se recupera solo.

**Corrección:**
- Guardar solo si el contenido se puede analizar como XML con raíz `{http://www.w3.org/2001/XMLSchema}schema`.
- Escribir en `.tmp` y hacer `os.replace`.
- Ante `XMLSchemaParseError`, borrar la caché y reintentar una vez.
- Añadir un botón o acción «Vaciar caché de esquemas».

### M10. Los errores de escritura de ficheros no se capturan en las pestañas Parcela, Edificio y Utilidades [CÓDIGO]
**Dónde:**
- `gui/pestana_parcela.py:529`;
- `gui/pestana_edificio.py:506`;
- `gui/pestana_utilidades.py:132`, a través de `gp.escribir` y `ge.escribir`.

**Escenario:** destino en una carpeta sin permiso de escritura, un fichero bloqueado en Windows, una ruta que es una carpeta o un disco lleno. Se produce `OSError` y aparece el diálogo de error de Python. Solo `crear_informe` lo captura.

**Corrección:** usar `try/except OSError` y `dock.warn(...)`, y escritura atómica (ver A3).

### M11. GML con curvas: el lector toma solo el primer `posList` del anillo, la geometría y la superficie son falsas y el error que se muestra es engañoso [REPRODUCIDO, e13_curvas.py]
**Dónde:** `core/gml_lector.py:122-130`: `descendientes(...,'posList')[0]`.

**Escenario:** exterior como `gml:Ring` con dos `curveMember`, un `LineStringSegment` y un `Arc`.

**Resultado:**
- Se leen 4 vértices.
- La superficie es de 100 m², cuando la real es de unos 139 m².
- El validador muestra `ANILLO-ABIERTO`, cuando el problema real es que hay curvas, que la Sede no admite (hay que densificar con flecha < 2 cm).
- La capa en el mapa y el informe muestran una geometría que no es la del fichero.

**Corrección:**
- Detectar `Arc`, `ArcString`, `Circle`, `CircleByCenterPoint` y `Ring`/`curveMember` y emitir `ERROR GEO-CURVAS-GML` («la Sede no admite curvas: densifíquelas»).
- Concatenar todos los `posList` de un `Ring`.

### M12. Pestaña Edificio: cada edición de la capa reconstruye la tabla y borra lo escrito en ella [CÓDIGO]
**Dónde:** `gui/pestana_edificio.py:218-225`: `featureAdded`, `attributeValueChanged`, `geometryChanged` y `afterRollBack` llaman a `recargar()`.

**Escenario:**
1. El usuario escribe las plantas en la tabla y cambia una fila a «Piscina» o un identificador.
2. Mueve un vértice en el mapa.
3. La tabla se regenera desde la capa: se pierden las plantas, el tipo vuelve al de la capa y los identificadores se recalculan.

Con «Solo seleccionados» pasa lo mismo en Parcela (`pestana_parcela.py:248-253`): cambiar la selección borra los identificadores escritos a mano.

**Corrección:**
- Conservar lo editado en un diccionario por `fid` y reaplicarlo en `recargar()`.
- O escribir los cambios de la tabla en la capa cuando la capa es de huellas.
- Reducir las recargas con un `QTimer` de un solo disparo, hijo del panel.

### M13. El validador no detecta los huecos abiertos (franjas entre parcelas que llegan al borde exterior) [REPRODUCIDO, e6_varios.py]
**Dónde:** `core/validador.py:212-220`: solo cuenta los anillos interiores de la unión.

**Escenario y resultado:** dos parcelas separadas por una franja de 5 cm que llega al borde dan un validador sin incidencias. Además, si una parcela tiene un hueco relleno por otra (−1) y a la vez hay un hueco real (+1), las cuentas se compensan y tampoco se avisa.

**Corrección:** calcular `union.buffer(+t).buffer(-t)` frente a `union` (cierre morfológico con t de unos 5 cm) y avisar si la diferencia es mayor de 0,01 m². Comparar los huecos por geometría, no por número.

---

## BAJO

**B1. Plantas con decimales se truncan sin aviso.** Un valor de 2,7 se escribe como 2 [REPRODUCIDO, e5]. Ocurre en `core/gml_edificio.py:96` y `:176` y en `core/capa_edificios.py:140`. Corrección: error si `float(plantas) != int(plantas)`.

**B2. Agregación con varias filas: todas reciben la misma RC.** En `core/alteraciones.py:91-92`, el resultado es `[('1907401VK4810H','SDGC'), ('1907401VK4810H','SDGC')]` [REPRODUCIDO, e6]. Hay aviso `ALT-NPP`, pero el escritor luego falla con `ID-REPETIDO`. Corrección: asignar la RC solo a la mayor y dejar las demás como están.

**B3. La comprobación foral de `comparar()` nunca se cumple.** En `core/comparacion.py:117` se busca `RC-FORAL` en `lectura.incidencias`, pero esa incidencia la añade el validador, no el lector. Un GML foral se compara contra el WFS de la DGC y sale `CMP-SIN-ORIGEN` («compruebe la posición y el SRC»), lo que confunde. Corrección: llamar a `refcat.comprobar(...).foral` sobre los `local_id` SDGC.

**B4. Detección de `xmlns:xlink` y de la codificación** (`core/gml_lector.py:260-263`):
- `xmlns:xlink = "…"`, con espacios, se lee como no declarado, lo que da un falso `XLINK` [REPRODUCIDO, e4].
- Un fichero UTF-16 también da `xlink_declarado=False` [REPRODUCIDO].
- Un fichero UTF-8 sin declaración XML se decodifica como latin-1 en `resultado.texto`.

Corrección: tomar los namespaces del parser (`ET.iterparse` con `start-ns`) en lugar de una expresión regular, y respetar la declaración de codificación.

**B5. Aviso de API obsoleta en QGIS 3.x.** En `gui/pestana_edificio.py:78`, `setFilters(Qgis.LayerFilter.PolygonLayer | Qgis.LayerFilter.LineLayer)`: con PyQt5 el `|` devuelve un entero y entra por la sobrecarga obsoleta (`DeprecationWarning: QgsMapLayerComboBox.setFilters() is deprecated`, visto en 3.34). Funciona, pero en QGIS 4 conviene comprobar que el `|` da `Qgis.LayerFilters`. Corrección: `Qgis.LayerFilters(Qgis.LayerFilter.PolygonLayer | Qgis.LayerFilter.LineLayer)`. El uso de la pestaña Parcela (`:87`) es correcto.

**B6. Al cerrar el panel con la ×, la herramienta «Elegir en el mapa» sigue activa.** `cleanup()` solo se llama en `unload` (`catastral_gml_tools_dockwidget.py:129-132`), así que un clic en el mapa lanza descargas desde un panel oculto [CÓDIGO]. Corrección: llamar a `soltar_herramienta()` en `visibilityChanged(False)`.

**B7. Umbral de solape de 0,01 m².** `core/validador.py:50` y `:210` ignoran rendijas de 1 cm × 90 cm. Corrección: medir la anchura, como en C2.

**B8. Informe HTML** (`core/informe.py`):
- `:163` dice «Coordenadas … tal como están en el fichero», pero `formatear` las redondea a 2 decimales y un fichero con 3 decimales se muestra alterado.
- Cuando el informe incluye los resultados de la comparación, no cita «Dirección General del Catastro» ni la fecha de consulta.
- Las capas de «Comparación» llevan la fuente, pero no la fecha (`pestana_validar.py:497-499`).

**B9. «Vuelve a comprobar» revalida los bytes leídos al abrir.** `xsdBoton` (`pestana_validar.py:323-335`) no vuelve a leer el fichero. Si se corrige fuera y se vuelve a elegir la misma ruta, `fileChanged` no se emite. Corrección: un botón «Volver a abrir» o volver a leer en `comprobar_esquema`.

**B10. Pestaña Edificio: una referencia de 20 caracteres** (de inmueble) se usa entera como base de los identificadores (`pestana_edificio.py:310-311`). Corrección: usar `refcat.comprobar(...).parcela`.

**B11. País Vasco y Navarra con parcelas solo LOCAL.** No hay detección por posición: solo por la RC SDGC o por la propiedad de las capas descargadas. Una segregación dibujada a mano en Bizkaia, toda LOCAL, genera un GML para la DGC.

**B12. Cabeceras GPL.** Faltan en `tests/*.py`, `tools/*.py`, `core/__init__.py` y `gui/__init__.py`. Estos dos últimos sí van en el ZIP.

**B13. Incoherencias de documentación y metadatos:**
- La ayuda (Parcela) pone como ejemplos `Div_1_1` y `Agrupa_1_2`, pero el asistente propone `Div_1`, `Div_2` y `Agrupa_1`.
- La ayuda presenta Dividir, «convierte del esquema 3.0 al 4.0» e «informes de superficies y coordenadas» como funciones de las pestañas, y no existen. `metadata.txt` (campo `about`) también promete convertir del 3.0 al 4.0, dividir parcelas e informes de superficies y coordenadas.
- El README dice «versión 0.1.0, esqueleto».
- La versión sigue en 0.1.0 con todas las fases 2 a 8 hechas, y el `changelog` de `metadata.txt` solo recoge el esqueleto. El gestor de complementos no verá la actualización. Conviene subir a 0.2.0 y sincronizar.
- La arquitectura de `DESARROLLO.md §2` cita `conversor.py`, `division.py`, `tareas.py`, `processing/` e `i18n/`, que no existen todavía.
- E-05 sigue «Por resolver», pero el código ya usa la copia de la DGC.
- `INVESTIGACION.md §3` dice que el WFS no ofrece 32628, lo que contradice E-02.
- La ayuda dice que «el grupo se sustituye» al volver a descargar, pero no avisa de que se pierden las ediciones (ver A4).

**B14. `TareaCatastro.run` se traga cualquier excepción** (`pestana_descargar.py:326-331`): el usuario solo ve «No se ha podido descargar la parcela», sin el motivo. Corrección: guardar `str(e)` y mostrarlo.

### Cumplimiento (licencia, atribución y aviso de no oficial)
**Bien:**
- Aviso de herramienta no oficial: en el panel (`legalLabel`), la ayuda, el README, el comentario de los GML, el informe y los metadatos de las capas.
- Fuente «Dirección General del Catastro» en las capas descargadas, con fecha; Navarra, con la cita obligatoria de su licencia CC BY 4.0.
- Sin logos ni escudos: solo iconos nativos de QGIS e icono propio.
- Licencia GPL-2.0-or-later y CREDITS sin código de terceros. No he visto rastros de código copiado de Check4SEC ni ParCatGML: estilo, nombres y estructura son propios.

**A mejorar:** la cita en el informe y en las capas de comparación (B8) y las cabeceras GPL que faltan (B12). El título «Informe de validación de GML» puede confundirse con el «Informe de validación gráfica» oficial; propongo «Informe de comprobación (no oficial)».

---

## Pruebas que faltan

**Las que habrían detectado los fallos de este informe:**
1. **Carrera en Validar (C1):** abrir A, comparar, abrir B, terminar la tarea de A; B no debe tener incidencias CMP ni «Listo para el ICUC». Lo mismo con `TareaEsquema`.
2. **Tolerancia de ±1 cm (C2):** vértice y tramo desplazados 0,5, 1,5, 3 y 5 cm, y entrante de 4 cm × 1 m. Edificio que sobresale 2, 4 y 6 cm.
3. **Parcela idéntica a la catastral (A1)** y parcela SDGC sin cambios dentro de una multiparcela.
4. **RC SDGC mal escrita (A2):** minúsculas, guion y punto, en el escritor, el validador y la tabla de la pestaña Parcela.
5. **Destino igual a la fuente de la capa (A3)** y fichero existente.
6. **Volver a descargar con la capa en edición (A4).**
7. **Lector «a prueba de todo» (A5):** coma decimal, `srsDimension` no numérico, `gml:pos` con 1 o 3 valores, `posList` impar, UTF-8 con BOM o sin declaración, UTF-16, curvas (`Arc`, `Ring` con varios `curveMember`). Informe con un anillo degenerado.
8. **SRC incoherente con SRC manual (A6)** en Parcela y Edificio; `transformar` con resultado infinito.
9. **Crear GML con parcelas solapadas o con huecos (M1);** edificio con partes solapadas o contiguas (M2).
10. **«Listo para el ICUC» con el XSD pendiente o sin comprobar (M3).**
11. **Rendimiento:** validar 5.000 parcelas en menos de N s, o en segundo plano (M4).
12. **Cancelación:** `TareaCatastro`, `TareaComparacion` y `TareaEsquema` canceladas a mitad; `unload()` con tareas en marcha (M6).
13. **Huso incorrecto:** capa 25830 en Galicia o Baleares; aviso en Parcela, Edificio y validador (M7).
14. **Unir con `Seg_1` en ambos ficheros;** namespace desconocido; destino con distinta capitalización (M8).
15. **Caché XSD con contenido HTML o truncado** y recuperación (M9).
16. **Errores de E/S al escribir** (carpeta de solo lectura, ruta que es carpeta) en las tres pestañas (M10).
17. **Edición de la capa de huellas con la tabla modificada** (M12).
18. **Huecos abiertos y compensados** en el validador (M13).

**Funciones y casos sin prueba directa** (según `grep` en `tests/`):
- `geometria.densificar` con flecha medida tras el redondeo al cm, y `poleOfInaccessibility` como último candidato de `punto_interior`.
- `capa_edificios.poligono_de_lineas`:
  - multilínea con varias líneas cerradas;
  - anillos anidados (patio);
  - cierre a menos de 1 cm.
- `src_incorrecto`, `lineas_abiertas`, `es_capa_de_parcelas`, `nueva_capa_huellas` (solo de forma indirecta en la prueba de interfaz).
- `servicios.datos_rustica`: respuestas JSON con `lspr` como diccionario o como lista, y JSON roto.
- `_navarra_en_punto`.
- `informe.croquis_svg` con huecos y multipartes.
- `unir.zonas_separadas` con parcelas a menos de 1 cm.
- `comparacion.parcelas_catastrales` con más de 25 trozos (`CMP-DEMASIADO-GRANDE`) y con un trozo que falla a mitad.
- `PestanaDescargar.soltar_herramienta` y la herramienta de mapa tras cerrar el panel.
- `catastral_gml_tools.unload()` con el panel abierto y con tareas en marcha (`smoke_test` solo cubre el caso sin tareas).
- `fondo.asegurar` sin red: no bloquear y no añadir capas no válidas.
- `refcat` con «Ñ» en la RC urbana y caracteres de control con Ñ.
- `alteraciones.proponer(AGREGACION)` con varias filas (B2).
- Plantas con decimales (B1).
- Ninguna prueba se ejecuta en QGIS 4 dentro de este entorno. La compatibilidad con Qt6 depende de `probar.bat` en Windows; convendría una tarea de CI con la imagen `qgis/qgis:latest` (Qt6) que lance `run_tests.py`.
