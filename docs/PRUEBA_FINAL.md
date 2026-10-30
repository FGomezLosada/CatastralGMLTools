# Prueba final antes de publicar la 1.0.0

Recorrido completo a mano, con el **ZIP de la versión** instalado como lo instalará cualquiera, y con parcelas reales
(urbana y rústica). Lo que falle se anota en «Incidencias» y se corrige antes de crear la etiqueta `v1.0.0`.

La prueba de verdad es el paso 6: **subir a la Sede los GML que crea el plugin** y ver que la Sede los acepta y dice lo
mismo que el plugin.

## 0. Preparación (una vez)

- [ ] QGIS 3.40: *Configuración → Perfiles de usuario → Nuevo perfil* «prueba_1.0.0» (sin el plugin de desarrollo).
- [ ] En ese perfil: *Complementos → Instalar a partir de ZIP* → `catastral_gml_tools-1.0.0.zip`. Sale el panel y en
      *Complementos → Instalados* pone versión 1.0.0, sin «experimental».
- [ ] Botón «?» del panel: la ayuda se abre y se ven las capturas.
- [ ] Elegir las parcelas reales de la prueba (anotarlas en la tabla del final):
  - **U**: una urbana con construcción (para segregar y para el ICUC).
  - **R**: una rústica que linde con un camino (dominio público).
  - **A** y **B**: dos urbanas colindantes (para agregar).
- [ ] Carpeta vacía para los ficheros de la prueba (p. ej. `pruebacat\1.0.0`).

## 1. Descargar

- [ ] U por referencia: llegan parcela, colindantes, entorno y construcciones en «Descargas del Catastro (temporales)»;
      mensaje verde con «Ir a Parcela» e «Ir a Edificio»; cita de la Dirección General del Catastro y fecha.
- [ ] R con «Elegir en el mapa»: el camino sale en otro color y se avisa del dominio público.
- [ ] Segunda descarga: la anterior queda plegada debajo de la nueva.
- [ ] Una referencia mal escrita (cambiar una letra): el aviso lo dice en castellano, sin errores de Python.

## 2. Parcela: segregación de U

- [ ] Junto a «1. Parcelas»: «1 de 1 seleccionada · capa temporal».
- [ ] «Dividir parcela ▸»: superficies (p. ej. 40 % para la nueva), lado marcado en rojo en el mapa, vista previa, «Dividir».
- [ ] Tabla: la mayor con la RC (SDGC) y `Seg_1` (LOCAL); alteración «Segregación»; aparece «con cambios sin guardar».
- [ ] Ctrl+Z deshace la división y la tabla vuelve a una parcela; Ctrl+Mayús+Z (rehacer) la vuelve a dividir.
- [ ] «Crear GML» → mensaje verde con «Validar»; el fichero está en la carpeta de la prueba.

## 3. Parcela: agregación de A y B

- [ ] Descargar A; seleccionar A y B en «Colindantes» antes de elegir esa capa: «2 de N seleccionadas».
- [ ] «Unir parcelas»: una sola parcela, alteración «Agregación» o «Agrupación» según superficies.
- [ ] Crear el GML.

## 4. Edificio de U (ICUC)

- [ ] Junto a «1. Construcciones»: «N construcciones · capa temporal»; referencia de U puesta sola.
- [ ] Plantas y estado en la tabla; «Opciones avanzadas»: precisión 0,1 m.
- [ ] Crear el GML; con el mensaje y las opciones abiertas el panel no sale de la ventana.

## 5. Validar (los tres GML)

- [ ] Segregación: sin errores, «Comparar con el Catastro» → NPO 1 · NPP 2 → Segregación; contorno coincidente;
      mensaje con «Abrir la Sede» (abre la página de Validaciones gráficas).
- [ ] Agregación: NPO 2 · NPP 1 → Agregación (o agrupación).
- [ ] Edificio: construcciones dentro de la parcela → «Listo para el ICUC».
- [ ] «Informe»: se abre en el navegador, con croquis, leyenda y «No es un documento oficial».
- [ ] R con un vértice movido 1 m (en Parcela, herramienta de vértices de QGIS sobre la capa de R, y Crear GML): en
      Validar, «Comparar» da la línea de identidad gráfica con el margen de rústica (±2 m), que cumpliría.

## 6. La prueba de verdad: la Sede

En la Sede Electrónica del Catastro (con certificado), sin presentar ninguna solicitud:

- [ ] Validación gráfica de la segregación: la Sede la acepta y propone la misma operación que el plugin.
- [ ] Validación gráfica de la agregación: ídem.
- [ ] ICUC del edificio: la Sede acepta el fichero (informe positivo si las construcciones están dentro).
- [ ] Si la Sede rechaza algo, guardar su informe (PDF o XML) para corregirlo.

## 7. Utilidades (rápido)

- [ ] 1. Unir ficheros GML: segregación + agregación en uno; Validar lo abre sin errores.
- [ ] 2. Convertir a 4.0: un GML 3.0 antiguo, si hay alguno.
- [ ] 3. Informe de superficies y coordenadas del GML de la segregación.
- [ ] 5. Comparar dos GML: el de la segregación con él mismo → iguales.

## 8. QGIS 4.2

- [ ] Repetir 0, 1, 2 y 5 (solo la segregación) en QGIS 4.2 con el mismo ZIP.

## Parcelas de la prueba

| | Referencia catastral | Notas |
|---|---|---|
| U | | |
| R | | |
| A | | |
| B | | |

## Incidencias

| Paso | Qué pasa | Captura |
|---|---|---|
| | | |
