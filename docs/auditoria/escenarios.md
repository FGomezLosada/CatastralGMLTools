# Auditoría por escenarios · Catastral GML Tools

Fecha: 09/10/2026 · Código: `/home/claude/CatastralGMLTools` (sin modificar) · QGIS 3.34.4 sin ventana, python3.12 · sin internet (servicios con `tests/simulador_catastro.py`).

Scripts (se pueden volver a lanzar con `python3.12 <script>` desde la carpeta):
`scratchpad/escenarios/`

| Script | Qué prueba |
|---|---|
| `base.py` | Arranque común (como `tools/run_tests.py`: offscreen, `start_app`, iface simulada, plugin cargado como `catastral_gml_tools`, simulador) |
| `e1_refcat_parcela.py` | RC, geometrías, identificadores, SRC de la capa, lectura de la capa |
| `e2_ficheros.py` | GML de entrada poco habituales (lector y validador) |
| `e3_comparacion.py`, `e3b_tolerancia.py` | Comparación con el Catastro (IVG simulado), asistente de alteraciones, «Unir seleccionadas» |
| `e4_unir.py` | Multiparcela (Utilidades) |
| `e5_edificio.py` | GML de edificio, ICUC simulado, capas de líneas tipo DXF |
| `e6_descarga.py` | Descarga por RC y por clic (DGC, Navarra, País Vasco, Canarias, husos) |
| `e7_gui.py`, `e7b_gui.py` | Panel real (pestañas Parcela, Edificio, Utilidades, Validar, Descargar) |

Los resultados en bruto de cada caso están en `r_e*.json` en la misma carpeta. En el simulador añadí parcelas desde mis scripts (otra manzana, rústica, 9000, Canarias, huso 31, escalón y chaflán) sustituyendo `sim._todas`. No toqué el repositorio.

Veredictos: **OK** · **FALLA** (error del plugin: excepción, dato mal leído o falso negativo) · **NO SOPORTADO** · **NO DEBERÍA ACEPTARSE** (lo da por bueno y la Sede lo rechazaría o la DGC lo desaconseja; abreviado **NDA**).

---

## 1. Resumen

- **277 casos ejecutados** (`r_e*.json`). En la matriz se agrupan algunos que prueban lo mismo en el núcleo y en el panel. La gran mayoría salen OK. Problemas: 21 fichas de corrección (F1–F21) y 5 escenarios NO SOPORTADO.
- Lo más grave:
  1. **Excepción sin capturar en la pestaña Parcela** cuando la capa tiene coordenadas UTM y SRC EPSG:4326 y se elige el huso a mano (UI-P05b). Es un caso habitual con SHP o DXF que traen mal el SRC.
  2. **Excepción sin capturar en Utilidades › Unir GML** si la carpeta de destino no existe (MUL-10, UI-U02).
  3. **Una RC de inmueble (18 o 20 caracteres) en el campo de la capa se convierte en una parcela LOCAL nueva** con 20 caracteres de identificador, en vez de usar la RC de la parcela (CAPA-01/02/03, UI-P10). La Sede vería la operación equivocada.
  4. **La comparación da «contorno coincide (±1 cm)» con vértices desplazados 20 cm** si el área de la diferencia es menor de 0,05 m² (CMP-36). Ocurre por ejemplo al quitar un escalón de 20 × 20 cm de una fachada.
  5. **No avisa de que el GML es idéntico a la parcela catastral** (CMP-24/25). Lo presenta como «Subsanación de discrepancias» con contorno correcto, y la Sede da error si no hay cambio (INVESTIGACION §1.3).
  6. **Incorporación de viario con parcela LOCAL marcada como ERROR** (CMP-09), cuando la guía GML de la DGC la admite.
  7. **Las capas dibujadas a mano en Navarra o en el País Vasco generan GML para la DGC sin ningún aviso**, en las pestañas Parcela y Edificio (UI-P08, UI-P09, UI-E03). La ayuda dice que «el plugin los detecta y lo indica».
  8. **ED50 (EPSG:23030) se transforma sin avisar** con una operación de 2 m de precisión, porque no hay rejilla NTv2 (SRC-10, UI-P14). La tolerancia de la Sede es ±1 cm.
  9. **No avisa del huso de la provincia**: una parcela de Galicia en 25830 sale sin aviso (SRC-13, UI-P13). `geometria.comprobar_src()` existe, pero solo lo usan las pruebas.
  10. **La creación de GML no comprueba solapes**, ni entre parcelas (GEO-20, MUL-12) ni entre construcciones o recintos de un mismo edificio (BU-12/13/15). Solo los detecta después la pestaña Validar.

---

## 2. Matriz de escenarios

### 2.1 Referencia catastral (`core/refcat.py`)

| ID | Escenario | Qué hace el plugin | Qué debería hacer (DGC) | Veredicto |
|---|---|---|---|---|
| RC-01 | Urbana 14 | Correcta, urbana | Igual | OK |
| RC-02 | Rústica 14 | Correcta, rústica | Igual | OK |
| RC-03 | Inmueble 20 con control correcto (9872023VH5797S0001WX) | Correcta | Igual | OK |
| RC-04 | Inmueble 20 con control erróneo | Error y propone «WX» | Igual | OK |
| RC-05 | 18 caracteres | Correcta y calcula el control | Igual | OK |
| RC-06 | Rústica 20 | Correcta | Igual | OK |
| RC-07 | 13 caracteres | Error de longitud | Igual | OK |
| RC-08 | Con espacios, guiones y minúsculas | La limpia | Igual | OK |
| RC-09 | Con Ñ | Ñ=15, control coherente | Igual | OK |
| RC-10 | Navarra 9 dígitos y «201-4-112», «201/04/0112» | `navarra()` la reconoce; `comprobar()` da error de longitud (esperado) | Catastro propio | OK |
| RC-11 | País Vasco rústica (01, 20, 48) | Aviso de catastro propio | Igual | OK |
| RC-12 | Navarra con formato DGC (31…) | Aviso de foral | Igual | OK |
| RC-13 | Provincia 99 / municipio 000 | «Correcta» | La provincia no existe | NDA (leve) |
| RC-14 | 9001, 9999, 9000, 08999 | Dominio público solo 9001-9999 | Igual (la 9000 no es dominio público) | OK |
| RC-15 | Control en minúsculas | Correcta | Igual | OK |

### 2.2 Geometría al crear el GML de parcela (`gml_parcela.escribir` + validador)

| ID | Escenario | Qué hace el plugin | Qué debería hacer | Veredicto |
|---|---|---|---|---|
| GEO-01 | Rectángulo 25830 | Crea el GML; el validador no da errores | Igual | OK |
| GEO-02 | Con patio (hueco) | Hueco antihorario | Igual | OK |
| GEO-03 | Hueco que toca el exterior en un punto | Lo acepta (válido en OGC) | Válido | OK |
| GEO-04 | Curva r = 10 m | Densifica: 33 vértices, flecha real 1,59 cm | Flecha < 2 cm | OK |
| GEO-05 | Vértices duplicados | Los quita (informa) | Igual | OK |
| GEO-06 | Vértices a 3 mm | Se funden al redondear | Igual | OK |
| GEO-07 | Autointersección | Error GEO-INVALIDA (además, un «0 m²» que confunde) | Rechazar | OK |
| GEO-08 | Multiparte | Error GEO-MULTIPARTE | Un recinto por parcela | OK |
| GEO-09 | Multipolígono de una parte | Lo acepta | Igual | OK |
| GEO-10 | Anillo abierto | Lo cierra | Igual | OK |
| GEO-11 | Menos de 4 vértices | Error | Igual | OK |
| GEO-12 | Triángulo | Lo acepta | Igual | OK |
| GEO-13 | Con Z/M | Quita Z/M (informa) | GML 2D | OK |
| GEO-14 | Diminuta 0,36 m² | **Error «La superficie es 0 m²»** | No hay superficie mínima (INVESTIGACION §7.1) | NO SOPORTADO |
| GEO-15 | Segregada de 0,64 m² + matriz | La acepta | Igual | OK |
| GEO-16 | Astilla de 2 mm | Error (desaparece al redondear al cm) | Igual | OK |
| GEO-17 | 6 × 5 km | La acepta | Igual | OK |
| GEO-18 | Esbeltez 30 | Aviso ESBELTEZ | Aviso de tramitación | OK |
| GEO-19 | Exterior antihorario | Lo reorienta | Igual | OK |
| GEO-20 | Dos parcelas que se solapan | **Crea el GML sin aviso**; solo Validar da SOLAPE | La Sede lo rechaza | NDA (al crear) |
| GEO-21 | Dos parcelas separadas 1 m | Sin aviso | Lo detecta la comparación (defecto) | OK |
| GEO-22 | Cuatro parcelas alrededor de un patio sin parcela | Validar: aviso HUECO; al crear, nada | Aviso | OK |
| GEO-23 | 6 decimales y 0,005 | Redondeo aritmético a 2 decimales | Igual | OK |
| GEO-24 | Línea | Error GEO-TIPO | Igual | OK |
| GEO-25 | Geometría vacía | Error | Igual | OK |
| ID-01 | SDGC con RC de 20 | Error NS-SDGC-SIN-RC | Igual | OK |
| ID-02 | LOCAL con tildes y espacios | Error ID-CARACTERES | Igual | OK |
| ID-03 | Identificadores repetidos | Error | Igual | OK |
| ID-04 | SDGC de Gipuzkoa | Error RC-FORAL | Igual | OK |
| ID-05 | LOCAL «201040112» (Navarra) | **Lo acepta sin aviso** | Detectar el territorio foral | NDA |
| ID-06 | LOCAL «1.2-b» | Lo acepta | Permitido | OK |
| ID-07 | LOCAL de 60 caracteres | Lo acepta | Sin límite publicado | OK |

### 2.3 SRC de la capa

| ID | Escenario | Qué hace el plugin | Qué debería hacer | Veredicto |
|---|---|---|---|---|
| SRC-01 | 25830 en Nerja | 25830, desplazamiento 0 cm | Igual | OK |
| SRC-02 | 4326 | Lo pasa a 25830 | Igual | OK |
| SRC-03 | 3857 | Lo pasa a 25830 | Igual | OK |
| SRC-04 | 4258 en Galicia | 25829 | Igual | OK |
| SRC-05 | 4326 en Barcelona | 25831 | Igual | OK |
| SRC-06 | 4326 en Tenerife | 32628 | Igual | OK |
| SRC-07 | 4083 (REGCAN95) | 32628 | Igual (E-03 pendiente) | OK |
| SRC-08 | 32628 | 32628 | Igual | OK |
| SRC-09 / UI-P06 | Capa sin SRC, «Automático» | Pide elegir el SRC | Igual | OK |
| UI-P07 | Capa sin SRC + 25830 a mano | Toma las coordenadas como 25830, sin aviso | Aceptable (convendría un aviso) | OK |
| SRC-10 / UI-P14 | Capa en ED50 (23030) | **Transforma con «ED50 to ETRS89 (10)», precisión 2 m, sin avisar**; la rejilla de 0,2 m no está disponible | Avisar o exigir la rejilla oficial (tolerancia ±1 cm) | NDA |
| SRC-11 | Desplazamiento ED50→ETRS89 | dX −100,17 m, dY −200,18 m (Helmert) | Rejilla NTv2 | Verificación |
| SRC-12 | Parcela que cruza el meridiano −6° (Badajoz) | Huso según el centroide (29 o 30) | Badajoz admite los dos | OK |
| SRC-13 / UI-P13 | Capa en 25830 con parcela de Galicia | **GML en 25830 sin aviso** (`comprobar_src` daría SRC-PROVINCIA, pero no se usa) | Avisar: A Coruña → 25829 | FALLA |
| SRC-14 / UI-P05b | Capa con UTM en 4326 + 25830 a mano | **`decimal.InvalidOperation` sin capturar** (al cambiar el SRC y al pulsar Crear GML) | Avisar como hace Edificio (`src_incorrecto`) | FALLA |
| UI-P05 | Lo mismo con «Automático» | «No se ha podido determinar el SRC», sin explicar la causa | Explicar que parece UTM | FALLA (leve; mismo arreglo) |

### 2.4 Lectura de la capa de parcelas (`capa_parcelas.leer_capa`)

| ID | Escenario | Qué hace el plugin | Qué debería hacer | Veredicto |
|---|---|---|---|---|
| CAPA-01 / UI-P10 | Campo con RC de inmueble (20) | **LOCAL «9872023VH5797S0001WX»** | SDGC con los 14 primeros caracteres | FALLA |
| CAPA-02 | RC de 18 | LOCAL con 18 caracteres | SDGC con 14 | FALLA |
| CAPA-03 | RC de 20 con control erróneo | LOCAL, sin aviso | Aviso de control y SDGC con 14 | FALLA |
| CAPA-04 | RC con espacios y minúsculas | SDGC limpia, label «23» | Igual | OK |
| CAPA-05 | RC de 13 (errata) | LOCAL sin aviso | Avisar «parece una RC mal escrita» | FALLA (leve) |
| CAPA-06 | Misma RC en dos trozos + vacío | RC / Nueva_1 / Parcela_3 | Igual | OK |
| CAPA-07 | Rústica | SDGC, label «123» | Igual | OK |
| CAPA-08 | «Finca 1» | Finca_1 | Igual | OK |
| CAPA-09 | 5.000 entidades (núcleo) + GML de 150 | 0,0 s y 0,1 s | — | OK |

### 2.5 Ficheros GML de entrada (lector y validador)

| ID | Escenario | Qué hace el plugin | Qué debería hacer | Veredicto |
|---|---|---|---|---|
| FIC-01 | Ruta con tildes y espacios | Lo lee y valida | Igual | OK |
| FIC-02 | UTF-8 con BOM | Lo lee | Igual | OK |
| FIC-03 | ISO-8859-1 declarado | Lee bien las tildes | Igual | OK |
| FIC-04 | Declara UTF-8 pero está en latin-1 | XML mal formado | Igual | OK |
| FIC-05 | UTF-16 | Lo lee, pero da **error XLINK falso** (busca xlink en el texto decodificado como latin-1) | No es un error de xlink | FALLA (leve) |
| FIC-06..08 | srsName URN, «EPSG:25830», `epsg.xml#25830` | EPSG 25830 | Igual | OK |
| FIC-09 | srsName 4258 | Error SRC-NO-ADMITIDO | Igual | OK |
| FIC-10 | Sin srsName | Error SRC-FALTA | Igual | OK |
| FIC-11 | SRC mezclados | Error SRC-MEZCLADOS | Igual | OK |
| FIC-12 | `gml:pos` | Lo lee, sin errores | Válido en XSD | OK |
| FIC-13 | `gml:coordinates` | Lo lee, sin errores | Formato DGC: posList | OK (lectura) |
| FIC-14 | 3D con `srsDimension="3"` | **«Sin errores: listo para validarlo en la Sede»** (hoy, sin comparar: «Sin errores en el fichero: falta «Comparar con el Catastro»») | La DGC exige 2D | NDA |
| FIC-15 | 3D con srsDimension heredado de `gml:Surface` | **Lo lee como 2D**: geometría basura y errores que confunden | Leer la dimensión heredada o avisar | FALLA |
| FIC-16..18 | Mal formado, vacío, sin parcelas | Error claro | Igual | OK |
| FIC-19 | Sin xmlns:xlink | Error XLINK | Igual (E-11) | OK |
| FIC-20 | count erróneo | Error ANILLO-COUNT | Probablemente igual (E-11 no lo aclara) | OK |
| FIC-21 | Anillo abierto | Error | Igual | OK |
| FIC-22 | Exterior antihorario | Error | Igual | OK |
| FIC-23 | 3 decimales | Aviso | Igual (la Sede trunca) | OK |
| FIC-24 | areaValue distinto de la geometría | Aviso | Igual (E-16) | OK |
| FIC-25 | Sin areaValue | Error | Igual | OK |
| FIC-26 | referencePoint fuera | Aviso | Igual | OK |
| FIC-27 | gml:id incoherente | Aviso | Igual | OK |
| FIC-28 | Namespace inventado | Error | Igual | OK |
| FIC-29 | Dos surfaceMember | Error GEO-MULTIPARTE | Igual | OK |
| FIC-30 | `gml:Polygon` directo en `cp:geometry` | **Sin errores** (sin internet no hay XSD) | La Sede lo rechaza (no es MultiSurface) | NDA (sin conexión) |
| FIC-31 | CP 3.0 | Aviso CP-30 | Igual | OK |
| FIC-32 | BU 2.0 | Lo lee | Igual | OK |
| FIC-33 | KML | Sin elementos | Igual | OK |
| FIC-34 | No existe | Error FICHERO | Igual | OK |
| FIC-35 | DOCTYPE con entidad externa | No la resuelve; mal formado | Seguro | OK |
| FIC-36 | Hueco horario | Error | Igual | OK |
| FIC-37 | CRLF y sin sangría | Lo lee | Igual | OK |
| FIC-38 | 400 parcelas | Aviso N-PARCELAS | Igual | OK |
| FIC-39 | Prefijo `cpx:` | Lo lee (por espacio de nombres) | Igual | OK |
| FIC-40 | RC SDGC en minúsculas | Solo aviso GMLID | La RC debe ir en mayúsculas | NDA (leve) |
| FIC-41 | posList sin srsDimension | Lo lee | Igual | OK |
| UI-V01..03 | Validar: no existe, ruta con tildes sin internet, vacío | Avisos correctos; XSD «no se ha podido comprobar» | Igual | OK |

### 2.6 Alteraciones y comparación con el Catastro (simulado)

| ID | Escenario | Qué hace el plugin | Qué debería hacer | Veredicto |
|---|---|---|---|---|
| CMP-01 | Segregación | NPO 1, NPP 2, contorno OK | Igual | OK |
| CMP-02 | División | División | Igual | OK |
| CMP-03 | Agregación | Agregación | Igual | OK |
| CMP-04 | Agrupación | Agrupación | Igual | OK |
| CMP-05 | Subsanación, lindero común movido 2 m | Subsanación de discrepancias, contorno OK | Igual | OK |
| CMP-06 | Rectificación aportando solo la propia | Error CMP-PARCIAL de la colindante | IVG negativo | OK |
| CMP-07 | Reparcelación 3 → 4 LOCAL | Aviso «subsanación o reparcelación» | Igual | OK |
| CMP-08 | Cesión de viario (LOCAL) | Segregación, contorno OK | Igual | OK |
| CMP-09 | **Incorporación de viario con parcela LOCAL** | **ERROR CMP-SIN-PARCELA** | La guía GML lo permite con parcela LOCAL | FALLA |
| CMP-10 | Ampliación sobre la calle sin LOCAL | Error | IVG negativo | OK |
| CMP-11 | Expropiación | Segregación | Igual | OK |
| CMP-12 | Ocupa dominio público (camino 9001) sin incluirlo | Error de afección parcial y aviso de dominio público | Igual | OK |
| CMP-13 | Dominio público incluido, delimitando la parte afectada | Subsanación con aviso de dominio público y de mezcla urbana/rústica | Igual | OK |
| CMP-14 | 9000 de rústica | No es dominio público, segregación | Igual | OK |
| CMP-15 | División en 31 | Avisos >30 y esbeltez (31 avisos repetidos) | Igual (mucho ruido) | OK |
| CMP-16 | Distinta manzana | Aviso CMP-TRAMITE | Igual | OK |
| CMP-17 | Urbana + rústica | Aviso CMP-TIPOS | Igual | OK |
| CMP-18 | Traslación de 0,5 cm | Contorno OK | Dentro de ±1 cm | OK |
| CMP-19 | Traslación de 3 cm | Errores (el texto habla de «afectada en parte», no de un desplazamiento) | Negativo | OK |
| CMP-20..22 | Un vértice desplazado 4, 10 y 25 cm (lados de 20–30 m) | Errores | Negativo | OK |
| CMP-23 | Vértice extra sin cambiar la forma | Contorno OK | Igual | OK |
| CMP-24 | **GML idéntico a la parcela catastral** | «Subsanación de discrepancias», contorno OK, **sin errores** | Error: no hay cambio | NDA |
| CMP-25 | Dos parcelas SDGC sin cambios | Lo mismo | Error | NDA |
| CMP-26 | GML en 25829 para parcela del huso 30 | Compara bien | Igual | OK |
| CMP-27 | Dos segregaciones separadas | Aviso «subsanación o reparcelación» | Igual (E-20) | OK |
| CMP-28 | RC inexistente | Error CMP-RC-NO-EXISTE | Igual | OK |
| CMP-29 | Dos SDGC de una parcela | «No permitida» | Igual | OK |
| CMP-30 | Parcela de 6 × 5 km | «Demasiado extenso» (más de 25 peticiones) | Comparar | NO SOPORTADO |
| CMP-31 | GML de Navarra (LOCAL) | «No está sobre ninguna parcela: compruebe la posición y el SRC» | Decir que es Navarra | FALLA |
| CMP-32 | Parcela del huso 29 | Compara bien | Igual | OK |
| CMP-33 | Sin conexión | Aviso «no comparado» | Igual | OK |
| CMP-34 | Patio que pasa a ser parcela LOCAL | Segregación, contorno OK | Igual | OK |
| CMP-35 | Segregación con resto (SDGC) menor que la segregada | El asistente da la RC a la **mayor** | La RC es del resto de la matriz | FALLA (leve, editable) |
| CMP-36 | **Quitar un escalón de 20 × 20 cm** (Hausdorff 20 cm, 0,04 m²) | **«El contorno coincide (±1 cm)»** | IVG negativo (±1 cm en vértices) | NDA |
| CMP-37 | Chaflán: vértice desplazado 7 cm | Error | Negativo | OK |
| ALT-01..06 | Avisos del asistente (NPP, SDGC, 1/5, RC perdida, ids del usuario) | Correctos | Igual | OK |
| UNI-01/02 | Unir seleccionadas: 85 % → agregación, 60 % → agrupación | Correcto | Igual | OK |
| UNI-03/04 | No colindantes o solo un vértice en común | Error | Igual | OK |
| UNI-05 | **Hueco de 1 mm** (digitalización) | Error «no colindantes» | Unir dentro de la tolerancia (1 cm) | FALLA (leve) |
| UNI-06 | Solape de 1 cm | Las une | Igual | OK |

### 2.7 Multiparcela (Utilidades › Unir GML)

| ID | Escenario | Qué hace el plugin | Qué debería hacer | Veredicto |
|---|---|---|---|---|
| MUL-01 | Colindantes | Une 4 parcelas | Igual | OK |
| MUL-02 | Zonas separadas | Aviso UNIR-SEPARADAS | Igual (E-20) | OK |
| MUL-03 | Husos 25830 y 25829 | Pasa todo al primero; el lindero común encaja (0 mm) | Igual | OK |
| MUL-04 | Parcela repetida e igual | La incluye una vez | Igual | OK |
| MUL-05 | Mismo id con geometría distinta | Error | Igual | OK |
| MUL-06 | GML 3.0 + 4.0 | Reescribe en 4.0 | Igual | OK |
| MUL-07 | Incluye un GML de edificio | Error | Igual | OK |
| MUL-08/09 | Un solo fichero; destino = entrada | Error | Igual | OK |
| MUL-10 / UI-U02 | **Carpeta de destino inexistente** | **FileNotFoundError sin capturar** | Aviso como en Parcela | FALLA |
| MUL-11 | Uno mal formado | Error | Igual | OK |
| MUL-12 | **Ficheros que se solapan** | **Unido «sin incidencias»** | Error de solape (la Sede lo rechaza) | NDA (en Unir; Validar lo detecta) |
| MUL-13 | Rutas con tildes y espacios | Bien | Igual | OK |
| MUL-14 | 35 ficheros | Sin aviso de más de 30 al unir (Validar sí lo da) | Aviso | OK |
| MUL-15/16 | Ajeno con 3 decimales o sin xlink | Lo reescribe bien | Igual | OK |
| UI-U01 | Nombre sin .gml | Añade .gml | Igual | OK |
| UI-U03 | «MAYUS.GML» | Lo admite | Igual | OK |

### 2.8 GML de edificio (ICUC)

| ID | Escenario | Qué hace el plugin | Qué debería hacer | Veredicto |
|---|---|---|---|---|
| BU-01..04 | Un edificio; dos edificios + piscina; varios recintos; patio | Correcto, ids `_Edificio_N` / `_Piscina_N`, ICUC simulado «dentro» | Igual | OK |
| BU-05 | Piscina en dos partes | Error | Igual | OK |
| BU-06 | Plantas vacías | Error BU-SIN-PLANTAS | Obligatorio (E-22) | OK |
| BU-07 | 0 plantas (solo bajo rasante) | Error BU-PLANTAS | INSPIRE admite 0; la DGC no lo aclara | NO SOPORTADO (dudoso) |
| BU-08 | «2B» | Error | Igual | OK |
| BU-09 | Sale 1 m de la parcela | Error CMP-BU-FUERA | Negativo | OK |
| BU-10 | A 150 m | Error CMP-BU-LEJOS | Sin informe | OK |
| BU-11 | Fuera, a 60 m | Error fuera | Negativo | OK |
| BU-12/13 | **Construcciones que se solapan** | **Crea el GML sin aviso**; Validar: SOLAPE; ICUC simulado: «dentro» | El ICUC no emite informe | NDA (al crear) |
| BU-14 | Adosados | Correcto | Igual | OK |
| BU-15 | **Recintos del mismo edificio que se solapan** | **Crea el GML**; Validar: GEO-INVALIDA; `comparar_edificio` lanza una TopologyException de GEOS y aun así dice «dentro» | Rechazar al crear | NDA |
| BU-16 | Sin RC (Edificio_1) | No compara (aviso) | Igual | OK |
| BU-17 | Id repetido | Error | Igual | OK |
| BU-18 | Construcciones de dos parcelas | No compara (aviso) | Igual | OK |
| BU-19/20 | Estados válidos / inventado | OK / error | Igual | OK |
| BU-21/22/23 | Curva / Z / autointersección | Densifica / 2D / error | Igual | OK |
| BU-24 | EPSG 4326 para el fichero | Error | Igual | OK |
| BU-25 | **Huella de 0,5 × 0,5 m** | **Error «0 m²»** | El GML de edificio no lleva superficie | FALLA |
| BU-26/27 | En el lindero; sobresale 5 mm | Dentro (±1 cm) | Igual | OK |
| BU-28 | 61 construcciones | Lo acepta (el límite de 60 es de ficheros) | Igual | OK |
| BU-29 | Id con RC de 20 | Compara con los 14 primeros | Aceptable | OK |
| BU-30 | RC de Gipuzkoa | Error RC-FORAL | Igual | OK |
| DXF-01/02 | Cerrada + abierta; hueco de 5 mm y de 3 cm | 1 huella, 1 abierta | Igual | OK |
| DXF-03 | **Huella dibujada con 4 LINE sueltas** | 0 huellas, 4 abiertas | Habitual en CAD: poligonizar | NO SOPORTADO |
| DXF-04 | Capa «PISCINA» | Piscina | Igual | OK |
| DXF-05 | **Patio como segunda polilínea de la misma entidad** | **Lo pierde**: 256 m² en vez de 240 (`unaryUnion` lo absorbe) | Hueco | FALLA |
| DXF-06 | Patio como entidad aparte | Dos «edificios», uno dentro del otro (Validar: solape) | Hueco | NO SOPORTADO |
| DXF-07 | DXF en UTM con SRC 4326 | Aviso claro | Igual | OK |
| DXF-08 | Lazo | Error | Igual | OK |

### 2.9 Descarga y clic

| ID | Escenario | Qué hace el plugin | Veredicto |
|---|---|---|---|
| DES-01..04 | RC de 14, 20 correcta, 20 con control erróneo (error sin petición), con espacios | Correcto | OK |
| DES-05 | Huso 29 | La vuelve a pedir en 25829 | OK |
| DES-06 | Canarias | La vuelve a pedir en 32628 | OK |
| DES-07 | Barcelona | 25831 | OK |
| DES-08 | Rústica | Correcto | OK |
| DES-09 | Mayor de 1 km² | GetNeighbourParcel | OK |
| DES-10/11/16/18 | Inexistente, sin red, 13 caracteres, todo caído | Mensajes claros | OK |
| DES-12/13 | Navarra (9 dígitos, «201-4-112») | Servicio de Navarra y aviso | OK |
| DES-14/15 | Navarra y Bizkaia con formato DGC | RC-FORAL sin petición | OK |
| DES-17 | Solo la parcela | 1 petición | OK |
| DES-19 | El servicio devuelve HTML (mantenimiento) | «No se ha encontrado la parcela» (falso: el servicio no ha contestado) | FALLA (leve) |
| CLIC-01..03 | Nerja, Pamplona (9 dígitos), sin parcela | Correcto | OK |
| UI-D01..04 | Panel: descargar urbana, Navarra, sin red, control erróneo | Correcto | OK |

### 2.10 Panel (pestañas reales)

| ID | Escenario | Qué hace el plugin | Veredicto |
|---|---|---|---|
| UI-P01 | Segregación, nombre sin .gml | Seg_1 y .gml añadido | OK |
| UI-P02 | Ruta con tildes, eñes y espacios | Bien | OK |
| UI-P03/P04 | Carpeta inexistente; destino vacío | Avisos | OK |
| UI-P08 | **Capa dibujada a mano en Navarra** | **GML creado sin aviso** | NDA |
| UI-P09 | **Capa dibujada en Gipuzkoa** | **GML creado sin aviso** | NDA |
| UI-P11 | 101 parcelas sin selección | Pide seleccionar | OK |
| UI-P12 | **101 seleccionadas** (reparcelación) | No deja crear el GML (máximo 100 filas) | NO SOPORTADO |
| UI-P15 | El fichero ya existe (ruta escrita) | Lo sobrescribe sin preguntar | OK (observación) |
| UI-P17 | Capa de líneas | No se ofrece | OK |
| UI-P18 | «Solo los elementos seleccionados» se queda marcado al cambiar a otra capa sin selección | Tabla vacía: «La capa no tiene polígonos (o no hay ninguno seleccionado)» | FALLA (leve, usabilidad) |
| UI-E01 | Edificio: dos huellas, sin .gml | Correcto | OK |
| UI-E02/E05/E06/E07 | Sin referencia, carpeta inexistente, UTM en 4326, capa de parcelas | Avisos correctos | OK |
| UI-E03 | **Referencia de Navarra (9 dígitos)** | **GML de edificio creado sin aviso** | NDA |
| UI-E04 | Referencia de 13 caracteres | Lo crea sin aviso sobre la RC | FALLA (leve) |
| UI-E08 | Referencia de inmueble (20) | Ids `…0001WI_Edificio_1` | FALLA (leve) |

---

## 3. Detalle de cada FALLA y NO DEBERÍA ACEPTARSE

En los ejemplos de código, «carpeta» es `escenarios/`. Cada caso se reproduce lanzando su script.

### F1. Excepción con capa UTM y SRC EPSG:4326 en la pestaña Parcela (UI-P05b, SRC-14)

- **Cómo reproducirlo.** Capa de polígonos con coordenadas UTM (421500, 4070500) y SRC EPSG:4326. Pestaña Parcela › SRC «EPSG:25830». Al cambiar el SRC, `actualizar_superficies` lanza `decimal.InvalidOperation`: la transformación da `inf` y `geometria.redondear` falla. Al pulsar Crear GML vuelve a fallar. Script: `e7b_gui.py` (y `e1_refcat_parcela.py`, SRC-14).
- **Corrección.**
  - En `PestanaParcela.crear_gml` y en `actualizar_superficies`, usar `capa_edificios.src_incorrecto(capa)`, como ya hace la pestaña Edificio.
  - En `geometria.preparar` (o en `transformar`), rechazar coordenadas no finitas con `math.isfinite` y devolver la incidencia `GEO-SRC` («coordenadas no válidas tras transformar: revise el SRC de la capa»).
  - Con «Automático», explicar la causa en vez de «No se ha podido determinar el SRC».

### F2. Excepción en Unir GML con carpeta de destino inexistente (MUL-10, UI-U02)

- **Cómo reproducirlo.** `unir.unir([a, b], '/no/existe/multi.gml')` lanza FileNotFoundError, y la pestaña Utilidades no la captura.
- **Corrección.** En `PestanaUtilidades.unir`, la misma comprobación `os.path.isdir(os.path.dirname(...))` que hacen Parcela y Edificio. Además, en `gml_parcela.escribir` y `gml_edificio.escribir`, capturar `OSError` y devolverlo como `Incidencia(ERROR, 'FICHERO', …)`.

### F3. RC de inmueble (18/20) en la capa → parcela LOCAL (CAPA-01/02/03, UI-P10)

- **Cómo reproducirlo.** Capa con el campo `refcat = '1907401VK4810H0001WI'` y alteración «Subsanación». La tabla queda en LOCAL con el identificador de 20 caracteres y se crea el GML; solo aparece el aviso del asistente. La Sede lo trataría como una parcela nueva.
- **Corrección.** En `capa_parcelas.leer_capa`:
  - si `limpiar(valor)` tiene 18 o 20 caracteres y `es_rc_parcela(valor[:14])`, usar `valor[:14]` (SDGC);
  - si tiene 20 caracteres, comprobar el control con `refcat.comprobar` y avisar si no coincide;
  - si tiene la forma «casi RC» (13–15 alfanuméricos con dígitos y letras), avisar de que puede ser una errata (CAPA-05).
- Lo mismo para la referencia de la pestaña Edificio (UI-E04, UI-E08): recortar a 14 en `proponer_ids` y avisar si `refcat.comprobar` da error.

### F4. Contorno «coincide» con vértices a 20 cm (CMP-36)

- **Cómo reproducirlo.** `e3b_tolerancia.py`. La parcela catastral tiene un escalón de 20 × 20 cm y el GML lo endereza. Hausdorff 20 cm, área 0,04 m² (por debajo de `AREA_MINIMA` = 0,05). Resultado: «CMP-CONTORNO-OK (±1 cm)».
- **Corrección.** En `comparacion.comparar`, además del área, medir la distancia de Hausdorff entre el contorno exterior del GML (`union`) y el de las afectadas (`union_origen`). Si pasa de `TOLERANCIA` + 0,005 m, dar un error `CMP-CONTORNO-DIST` con la distancia máxima y el vértice, y no emitir CMP-CONTORNO-OK.

### F5. GML idéntico a la parcela catastral (CMP-24/25) — NDA

- **Cómo reproducirlo.** GML con `1907401VK4810H` y su misma geometría. El resultado es «Subsanación de discrepancias», contorno OK y ningún error.
- **Corrección.** Para cada propuesta SDGC cuya geometría coincide con su parcela de origen (Hausdorff ≤ 1 cm): si **todas** coinciden, error `CMP-SIN-CAMBIOS` («la Sede rechaza un GML sin cambios»); si solo algunas, aviso.

### F6. Incorporación de viario con parcela LOCAL marcada como error (CMP-09)

- **Cómo reproducirlo.** `1907403VK4810H` sin cambios y `Viario_1` LOCAL sobre la calle. Resultado: ERROR CMP-SIN-PARCELA (599,7 m²).
- **Corrección.** Si `sin_parcela` queda cubierto (±1 cm) por parcelas LOCAL del GML, bajar a AVISO `CMP-VIARIO` («cesión o incorporación del viario: requiere la conformidad del Ayuntamiento»). Mantener ERROR solo si el suelo sin parcela queda dentro de una parcela SDGC.

### F7. Territorios forales no detectados por posición (UI-P08, UI-P09, UI-E03, ID-05, CMP-31) — NDA

- **Cómo reproducirlo.** Capa en 25830 con polígonos en (610000, 4740000) (Navarra), o en 4258 en San Sebastián. Crear GML: «GML creado». En Edificio, la referencia `201040112` también genera el GML. La comparación de un GML de Navarra solo dice «compruebe la posición y el SRC».
- **Corrección.** Función `info.territorio_por_posicion(geometria, crs)` con el polígono aproximado de Navarra y del País Vasco (cajas o un GeoJSON simplificado en el plugin). Llamarla en `crear_gml` de Parcela y Edificio (error, como con la propiedad `PROPIEDAD_TERRITORIO`) y en `comparacion.comparar` (incidencia `RC-FORAL`). En Edificio, si `refcat.navarra(referencia)` no está vacía, bloquear.

### F8. ED50 transformado con 2 m de precisión sin aviso (SRC-10/11, UI-P14) — NDA

- **Cómo reproducirlo.** Capa EPSG:23030. QGIS usa «ED50 to ETRS89 (10)» (precisión 2,0 m) porque la operación de 0,2 m (rejilla) no está disponible; el GML se crea sin aviso.
- **Corrección.** En `comprobar_parcelas` o en la pestaña, si el datum de la capa no es ETRS89/WGS84/REGCAN95, consultar `QgsCoordinateTransform(...).instantiatedCoordinateOperationDetails()`. Si su `accuracy` es mayor de 0,05 m o desconocida, mostrar un aviso con la precisión y recomendar instalar la rejilla oficial del IGN (PENR2009 / SPED2ETV2) o transformar antes la capa.

### F9. Huso de la provincia no comprobado (SRC-13, UI-P13)

- **Cómo reproducirlo.** Capa en 25830 con la parcela en A Coruña: GML en 25830 sin aviso. `comprobar_src()` daría SRC-PROVINCIA, pero nadie lo llama.
- **Corrección.** Llamar a `geo.comprobar_src(crs_salida, union, provincia)` desde `crear_gml`. La provincia sale de la RC rústica o, si no la hay, de `epsg_recomendado`. Mostrar el resultado como aviso. Hacer lo mismo en el validador (posición frente a `lectura.epsg`).

### F10. Solapes al crear (GEO-20, BU-12/13/15, MUL-12) — NDA al crear

- **Cómo reproducirlo.** Dos polígonos solapados en la capa, o dos huellas solapadas, o un multipolígono de edificio con partes solapadas: «GML creado». Unir GML: «sin incidencias».
- **Corrección.**
  - Tras escribir, ejecutar `validador.validar_conjunto` sobre las geometrías preparadas y pasar SOLAPE a error de creación, o como mínimo a aviso naranja.
  - Para un edificio multiparte, comprobar `isGeosValid()` del conjunto o unir las partes antes de escribir.
  - En `comparar_edificio`, usar `makeValid()` para evitar la TopologyException.

### F11. Superficie mínima en edificios (BU-25) y en parcelas diminutas (GEO-14)

- **Cómo reproducirlo.** Huella de 0,5 × 0,5 m: «La superficie es 0 m²». El GML de edificio no lleva `areaValue`.
- **Corrección.** En `geometria.preparar`, comprobar `area() <= 0` sin redondear, y dejar el redondeo solo para `areaValue` de parcela. En parcelas menores de 0,5 m², aviso en lugar de error (escribir `areaValue` 0, o 1 si se prefiere).

### F12. Patio de DXF perdido (DXF-05) y huellas con LINE sueltas (DXF-03, NO SOPORTADO)

- **Cómo reproducirlo.** Capa de líneas con un MULTILINESTRING exterior + patio: área 256 m² en vez de 240.
- **Corrección.** En `capa_edificios.poligono_de_lineas`, en vez de `unaryUnion` de los anillos, construir los polígonos con `QgsGeometry.polygonize` (o anidar por contención: un anillo dentro de otro es un hueco). Con la misma función se pueden poligonizar las LINE sueltas de una capa (DXF-03) y los patios que vienen como entidad aparte (DXF-06).

### F13. Lector: srsDimension heredado (FIC-15) y 3D aceptado (FIC-14)

- **Corrección.**
  - En `gml_lector.coordenadas`, si el posList no trae `srsDimension`, subir por los ancestros (`Surface`, `MultiSurface`, `Polygon`) hasta encontrarlo; ElementTree no tiene «parent», así que hay que pasar la dimensión al recorrer.
  - En el validador, dar error `DIMENSION` si alguna geometría tiene dimensión 3: la DGC exige `srsDimension="2"`.

### F14. Geometría de tipo no admitido sin XSD (FIC-30) — NDA sin conexión

- **Corrección.** En el validador estructural, comprobar que `cp:geometry` contiene `gml:MultiSurface/gml:surfaceMember/gml:Surface/gml:patches/gml:PolygonPatch` (CP 4.0) y dar error `GEO-ESTRUCTURA` si no. No debe depender de que el XSD se haya podido descargar.

### F15. Detección de xlink en UTF-16 (FIC-05)

- **Corrección.** En `gml_lector.leer_datos`, decodificar con la codificación de la declaración XML o del BOM. Más sencillo: comprobar xlink con ElementTree (`ET.iterparse` con `events=('start-ns',)`) en vez de con una expresión regular sobre el texto.

### F16. RC SDGC en minúsculas (FIC-40) — NDA leve

- **Corrección.** En `validador.validar_elemento`, si `e.local_id != refcat.limpiar(e.local_id)` con namespace SDGC, dar error («la referencia debe ir en mayúsculas y sin espacios»).

### F17. Asistente: RC a la parcela mayor en la segregación (CMP-35)

- **Corrección.** Si la capa traía la RC en una fila concreta (`filas_capa`), dejarla en esa fila, que es el resto de la matriz que el usuario dibujó con su referencia, en vez de dársela a la mayor. Si se usa la mayor, decirlo en el resumen («la RC se ha puesto en la mayor: cámbiela si el resto es otra»).

### F18. «Unir seleccionadas» con huecos de digitalización (UNI-05)

- **Corrección.** En `capa_parcelas.unir_seleccionadas`, unir con `buffer(+0,005)` y luego `buffer(-0,005)`, o con un snap previo de 1 cm, y avisar de que se ha cerrado un hueco de X mm.

### F19. Mensajes engañosos

- **DES-19.** Si `leer_datos` no encuentra FeatureCollection, `consultar_wfs` debe decir «respuesta inesperada del servicio (¿mantenimiento?)» y no «no se ha encontrado la parcela». Se distingue por `resultado.raiz`.
- **CMP-31.** Ver F7.
- **CMP-19.** Si todas las afectadas en parte lo están por menos de 5 cm de anchura, sugerir «el contorno está desplazado X cm» en lugar de «inclúyala entera».

### F20. «Solo los elementos seleccionados» se queda marcado (UI-P18)

- **Corrección.** En `cambiar_capa`, desmarcarlo cuando la capa nueva tenga `MAX_FILAS` o menos entidades, o no tenga selección.

### F21. Provincia inexistente (RC-13) — NDA leve

- **Corrección.** En `refcat.comprobar`, aviso si `provincia(parcela[:2])` está vacía.

### NO SOPORTADO (para decidir)

- **GEO-14.** Parcelas de menos de 0,5 m² (ver F11).
- **BU-07.** Edificios con 0 plantas sobre rasante: confirmar con la DGC si el esquema y el ICUC lo admiten.
- **CMP-30.** Comparación de parcelarios mayores de unos 5 × 5 km. Se podrían pedir solo los trozos que tocan el contorno, en vez del rectángulo entero.
- **UI-P12.** GML de más de 100 parcelas desde la pestaña Parcela. Las reparcelaciones pueden superarlo: permitir crear el GML sin cargar la tabla, con un aviso.
- **DXF-03 y DXF-06.** Ver F12.

---

## 4. Escenarios que no he podido probar y por qué

| Escenario | Motivo |
|---|---|
| Aceptación real en la Sede (IVG, ICUC, Tipo de operación) | Sin internet ni certificado. Los veredictos «la Sede lo rechazaría» salen de docs/INVESTIGACION.md, DESARROLLO.md (E-11, E-16, E-20, E-21, E-22) y de la normativa de la DGC, no de una prueba en la Sede. |
| Validación XSD contra los esquemas oficiales (`core/esquemas.py`) | Sin internet y sin caché de esquemas: solo comprobé que avisa con «no se ha podido comprobar» (UI-V02). No sé si FIC-13 (`gml:coordinates`) o FIC-30 los rechazaría el XSD. |
| Servicios reales (WFS CP/BU, Consulta_RCCOOR, Consulta_DNPRC, WFS de Navarra) | Sin internet: todo con el simulador y con parcelas que añadí yo (Canarias, huso 31, otra manzana, rústica, 9000). Las superficies en Canarias y en el huso 31 salen deformadas por cómo el simulador guarda las coordenadas, y no afectan al veredicto. |
| QGIS 3.40 LTR y 4.x (Qt6), Windows | Aquí solo hay QGIS 3.34.4 en Linux. Rutas de Windows (unidad, `\`, UNC, OneDrive) y bloqueo de ficheros abiertos sin probar. |
| Carpeta sin permiso de escritura (UI-P16) | El entorno corre como root y escribe en cualquier carpeta: la prueba no es válida. Por el código (`escribir` sin try), el resultado esperado es una excepción sin capturar, como en F2. |
| ED50 con la rejilla oficial (PENR2009 / SPED2ETV2) | La rejilla no está instalada: solo comprobé que sin ella se usa la operación de 2 m. |
| Herramienta de clic en el mapa, arrastrar y soltar, tareas en segundo plano (QgsTask), botones de la barra, «Mapa de fondo» (WMS) | Son interacciones; las probé llamando a los métodos en primer plano (`segundo_plano=False`). |
| DXF/DWG reales leídos por GDAL, shapefiles con .prj raros | Simulados con capas de memoria de líneas y polígonos, con el campo `Layer`. |
| Parcelas BICE en el ICUC | El plugin no lo comprueba (E-21) y no hay datos. |
| Conversor 3.0 → 4.0, división de parcelas, informe de superficies, Processing (mejoras 21–26) | No están implementados (fases 9–11 y 14). |
| Rendimiento del panel con capas municipales reales (decenas de miles de entidades) en Windows | Solo probado en el núcleo (5.000 entidades, CAPA-09) y en el panel con 101. |
