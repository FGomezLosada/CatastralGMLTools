# Auditoría normativa de Catastral GML Tools frente a la documentación de la DGC y del curso de gestión catastral

Fecha: 09/10/2026 · Revisado: el código de `/home/claude/CatastralGMLTools` (core/, gui/ por encima, docs/, help/index.html) y los 29 textos de `scratchpad/docs/`.

**Leyenda de estado:** CUBIERTO · PARCIAL · NO CUBIERTO · CONTRADICE (el plugin dice o hace algo distinto de lo que dicen los documentos, o sus propios docs dicen algo que el código no hace).

**Abreviaturas de las fuentes**
- **IVG-Op**: «Informe de Validación Gráfica de la SEC. Guía para la elaboración de ficheros GML según las operaciones sobre el parcelario» (DGC, v2.3, 20/09/2021). `IVG_Operaciones_Parcelario_GMLs.txt`
- **GML-CR**: «Documento de generación de archivo GML. Validación en la SEC. Coordinación Catastro-Registro» (DGC, sin fecha; usa CP 4.0). `FicheroGML_Coordinacion_Catastro-Registro.txt`
- **Dif34**: «GML de parcela catastral. Diferencias entre los esquemas 3.0 y 4.0» (DGC, diciembre de 2024).
- **BU-DGC**: «Formato GML de edificio» (DGC). **BU-Como**: «Cómo generar un GML de edificio» (DGC). **CP-Como**: «¿Cómo generar un GML de parcela catastral?» (DGC).
- **FAQ**: «Preguntas y respuestas acerca de la coordinación Catastro-Registro» (DGC, versión 28-06-2017).
- **Editor**: «Editor de parcelario de la SEC. Manual de usuario» (DGC, v1.5, 16/06/2020).
- **C4S**: «Manual de usuario de Check4SEC» (Unidad de Cartografía Catastral, DGC).
- **INSP**: «Conjunto de datos INSPIRE de la DGC» (v1.0, julio de 2016).
- **T8-26**: Tema 8 del curso, v2026. **T6.3**: Tema 6 parte 3, v2024. **T3-26**: Tema 3, v2026. **T4.4**: Tema 4 parte 4, v2026. **T2.1**: Tema 2.1, v2023.
- **Alumnos**: dos prácticas de alumnos del curso (agrupación, 30/11/2023, y segregación, 03/12/2023, con su IVG); **VGA**: «Explicación_VGA».

Documentos sin contenido útil: `Modelo_900D.txt` (3 bytes) y `Presentación_Practica_T8_v2023.txt` (11 bytes) están vacíos (PDF escaneados); `TEMA_8_..._v2025.txt` solo trae el índice (el contenido equivalente está en la v2026). Los de formato CAT, shapefile y descargas se han hojeado: lo útil está en los apartados G y DL.

---

## 0. Resumen: lo más importante

1. **CONTRADICE (docs internos ↔ código):** `docs/DESARROLLO.md`, mejora 14 (✅), dice que la comparación detecta «parcelas sin cambios». `core/comparacion.py` no lo hace. Check4SEC (DGC) lo trata como **error**: «si la parcela aportada fuera coincidente con la parcela catastral de origen, se mostrará un error, indicando que se debe eliminar dicha parcela aportada de la selección» (C4S §4.1.3).
2. **CONTRADICE:** `core/comparacion.py:comparar_edificio()` dice «Si la parcela aún no existe, el ICUC usa la del GML de parcela». Según la DGC, el ICUC de la Sede «no admite la aportación de geometrías de parcela» y hace falta «un trámite previo de alteración del parcelario catastral» (C4S §5.1.3).
3. **Desactualizado:** desde el **12/03/2025** la Sede **no certifica IVG negativos**. Muestra los errores y deja descargar el GML parcial (T8-26 §2.5). El plugin y la ayuda siguen hablando de «informe negativo» (`comparacion.py` CMP-PARCIAL y CMP-SIN-PARCELA; `help/index.html`).
4. **Falta el tipo «Reparcelación» en el asistente** (`core/alteraciones.py:TIPOS`). La DGC lo define (IVG-Op §3.3, GML-CR §2.3, Editor §2.3) y la tabla NPO/NPP lo ofrece.
5. **Falta la transformación por desplazamiento o giro de la cartografía** para parcelas: afín de 6 parámetros con 3 puntos, resuelta por Gauss-Jordan y comprobada con otros puntos (FAQ p. 11). Solo se menciona para el ICUC.
6. **Dominio público y viario urbano:** el plugin da ERROR (CMP-SIN-PARCELA). La DGC es contradictoria. FAQ 2017: «negativo». GML-CR: el GML «SÍ permite actuar sobre el dominio público en zona urbana tanto para los casos de cesión como de incorporación del viario». C4S: «el positivo solo será condicionado en caso de afección a dominio público». Conviene bajarlo a aviso con explicación.
7. **El umbral de agregación sigue sin resolver (E-17):** 80 % de la resultante (IVG-Op §3.1) frente al quíntuplo de las agregadas, ≈ 83,3 % (GML-CR §2.1, Editor §2.1, FAQ con art. 48 RH y Circular 07.04/06). Según la FAQ y la Circular, la calificación «atenderá a lo especificado en la escritura» y el umbral solo se aplica si la escritura no dice nada. La práctica real lo confirma: la Sede validó como «SEGREGACIÓN» una partición 50/50 (práctica de alumno: 5817 y 5814 m²).
8. **Falta el marco procedimental:** el plugin no avisa de licencia o unidad mínima de cultivo, de la coherencia con la escritura, del orden «primero subsanar y luego declarar», de la notificación a colindantes ni de los umbrales de cabida del 10 % y el 5 %. Todo esto está en los documentos y protege al usuario de errores de presentación.
9. **Resolución conjunta:** todos los documentos del curso citan la de **26/10/2015** (T8-26 y CP-Como dicen por error «26 de noviembre»). `docs/INVESTIGACION.md` cita además la Resolución conjunta DGSJFP-DGC BOE-A-2020-12111 (2020) con tolerancias de ±0,50 m, ±2 m y 5 % «anexo II». Esas cifras **no aparecen en ninguno de los documentos aportados**. Hay que verificarlas en el BOE antes de mostrarlas como norma: no he podido abrir el BOE desde aquí.
10. **Mejoras pendientes con base documental clara:** lector del XML del IVG (mejora 32), puntos de apoyo .txt (33), división «por cuotas» (no está en la mejora 22), conversor 3→4 (21), informe con datos de técnico y coordenadas (25), avisos de superficie (RD 1464/2007, art. 201.3 LH, anamorfosis).

---

## 1. Contradicciones entre documentos (y cuál parece vigente)

| # | Tema | Documento A | Documento B | Vigente / criterio |
|---|---|---|---|---|
| X-01 | Esquema CP | IVG-Op §4.1 (2021): valida contra «…/cp/3.0/CadastralParcels.xsd»; FAQ (2017) y INSP (2016) también 3.0 | Dif34 (dic. 2024): «deben realizarse utilizando el esquema 4.0»; 3.0 «(obsoleto)»; GML-CR, Editor v1.5 y T8-26: 4.0 | **4.0** (Dif34 es el más reciente). El plugin lo aplica |
| X-02 | Agregación | IVG-Op §3.1: «La parcela principal ha de tener una superficie de al menos el 80% de la parcela resultante» | GML-CR §2.1 y Editor §2.1: «el quíntuplo de la suma de las que se agreguen» (= 83,3 %); FAQ: art. 48 RH y Circular 07.04/06, **solo si la escritura no lo especifica** | Sin resolver. Tiene más base jurídica el **quíntuplo**, y siempre manda la escritura. El plugin usa el 80 % en `capa_parcelas.unir_seleccionadas` |
| X-03 | Agrupación | IVG-Op §3.1: «No se realiza ninguna validación relativa a las superficies» | Editor §2.1: las fincas agrupadas, cada una, «mayor … a la quinta parte de la superficie total» | La Sede **no valida** superficies en la agrupación. Lo del editor es un criterio de calificación |
| X-04 | Segregación | Editor §2.2 y FAQ: segregación si lo segregado es < 20 % de la matriz | Alumnos (práctica de segregación): IVG positivo «SEGREGACIÓN» con 50 %/50 % | La Sede califica **por namespaces**, no por superficie. El plugin ya lo trata como INFO |
| X-05 | Autenticación del IVG | FAQ 2017: «El servicio requiere la autenticación … certificado electrónico o con Cl@ve-Pin»; CP-Como: «precisa de autenticación» | T8-26 §2.5: «disponible para todo usuario sin necesidad de autentificarse», con botones «IVG autenticado» / «IVG sin autenticar» (también Editor v1.5) | **Las dos modalidades**. El técnico debería autenticarse (T8-26: da «mayor profesionalidad y veracidad») |
| X-06 | IVG negativo | FAQ 2017: el informe negativo expresa «los errores o defectos advertidos» y «no paraliza el tráfico jurídico»; T8-26: no puede ser motivo de denegación (art. 9 LH) | T8-26 (nota): desde el **12/03/2025** «ya no se certificarán informes de validación gráfica negativos»; se informa de los errores y se descarga el «GML Parcial» | **2025**: ya no hay IVG negativo certificado |
| X-07 | Plazo del IVG | FAQ: «El servicio remitirá en el plazo de 24 horas el informe» | Alumnos, VGA, T8-26: se descarga al momento | Inmediato (lo de la FAQ está desfasado) |
| X-08 | Fecha de la Resolución | FAQ, IVG-Op, T8-26 (bibliografía): «26 de octubre de 2015» | T8-26 §2.3 y CP-Como: «26 de noviembre de 2015» | **26/10/2015** (BOE 30/10/2015). «Noviembre» es una errata. Verificar si la sustituye la de 2020 (ver L-02) |
| X-09 | `nationalCadastralReference` de una parcela nueva | T8-26 §2.3: «Estará en blanco si se trata de una nueva parcela» | GML-CR §3.2: «Puede modificarse la RC por el contenido de la etiqueta localID» (ejemplo `Parcela1A_Agregación`) | Las dos se aceptan en la práctica. El plugin pone el localId (GML-CR) y la Sede lo valida (E-19, E-20) |
| X-10 | `label` de una parcela nueva | T8-26: «se pondrá exactamente el mismo texto que en localId» | GML-CR: «Etiqueta que no precisa modificación» (2 dígitos en urbana, hasta 5 en rústica) | El plugin sigue T8-26 para LOCAL. Coherente |
| X-11 | `areaValue` frente a la geometría | T8-26: «En el caso de nuevas parcelas tienen que coincidir con la superficie de la geometría» | IVG-Op v2.1: «Se elimina la validación de la etiqueta del área frente al área de la geometría» | La Sede no lo comprueba. Conviene que coincida. El plugin escribe la de la geometría y da aviso (E-16) |
| X-12 | Contenedor y zoning | T8-26 §2.3 describe el 4.0 con «featureMember», `cp:zoning`, `CadastralZoning` y `CadastralBoundary` (texto heredado del 3.0) | Dif34: en 4.0 desaparecen `featureMember`, `zoning`, `validFrom` y `validTo` | **Dif34** |
| X-13 | Namespaces con erratas | GML-CR: «ES.LOCAL.SDGC» y «(Para el caso de namespace ES.SDGC.CO)»; ejemplos con espacios y tildes («ES.LOCAL.CP. Parcela1A_Agregación») | IVG-Op §4.1: solo «ES.LOCAL.CP» y «ES.SDGC.CP» | Solo los dos namespaces, sin espacios ni tildes (Editor §2.5) |
| X-14 | Viario urbano ocupado | FAQ: «En el caso de viales urbanos … el informe de validación que se obtendrá será negativo» | GML-CR §3.1: el GML «SÍ permite actuar sobre el dominio público en zona urbana … cesión como de incorporación del viario público»; C4S §4.1.4: «el positivo solo será condicionado en caso de afección a dominio público» | Los más recientes (GML-CR y C4S): **positivo condicionado**, sin tramitación automática |
| X-15 | Precisión de la cartografía frente a la exigida a la RGA | FAQ: precisión nominal de la cartografía catastral ±0,5 m (urbana) y ±2 m (rústica), «en un 95% de los casos» | FAQ y T8-26: precisión exigida a la RGA: levantamiento con error < 25 cm y el 85 % ≤ 20 cm; digitalización ±0,20 m (urbana) y ±0,40 m (rústica); contorno ±1 cm | No se contradicen: son conceptos distintos. Las cifras de ±0,5 m, ±2 m y 5 % de INVESTIGACION §1.3 no están en estos documentos |
| X-16 | Namespace del edificio | BU-DGC (modelo simplificado): `ES.LOCAL.BU` en el edificio, pero `ES.SDGC.BU` en la piscina del mismo ejemplo | INSP y T8-26: `ES.SDGC.BU` (datos de la DGC) | Para un GML nuevo, **ES.LOCAL.BU** (texto de BU-DGC: «“LOCAL” para evitar definir un organismo»). El plugin lo hace |
| X-17 | Sufijo de la piscina | BU-DGC (texto): «_Piscina_xx»; BU-DGC (ejemplo) e INSP: «_PI.1» | — | Las dos formas. El plugin usa `_Piscina_N` |
| X-18 | Precisión del edificio | BU-DGC / INSP: `horizontalGeometryEstimatedAccuracy` = 0.1 | BU-Como: «se pondrá 10 metros porque este método no garantiza gran precisión» (huella medida en el visor de la Sede) | Depende del método. El plugin fija 0.1 |
| X-19 | Atributos del edificio | BU-DGC: modelo «reducido al máximo» | BU-Como (plantilla antigua): fecha de construcción, uso principal, nº de inmuebles, nº de viviendas, superficie construida | BU-DGC (vigente, el que valida el esquema de la DGC; E-22) |
| X-20 | Estados del edificio | BU-DGC: declined, demolished, «funtional» (errata), projected, ruin, underConstruction | INSP / T8-26: solo ruin, declined, functional (datos de la DGC) | BU-DGC para GML nuevos. Lo correcto es `functional` |
| X-21 | Artículo del TRLCI | FAQ (anexo): «53.1.b» | T8-26 (bibliografía): «54,1. b)» | Errata en uno de los dos. No afecta al plugin |
| X-22 | Las Palmas, Girona y Melilla en la tabla de husos | INVESTIGACION §1.3: «Las Palmas no aparece en la tabla … se supone 32628» | FAQ p. 10 (texto extraído): «Girona 25831 · Palmas (Las) 32628 · Melilla 25830» | **Confirmado en la FAQ**: se pueden quitar los asteriscos de `core/geometria.py:HUSOS_PROVINCIA` |

---

## 2. GML de parcela (CP 4.0)

**P-01 · Esquema 4.0 obligatorio**
- Regla: los GML para la SEC y el IVG deben ser CadastralParcels 4.0. El 3.0 está obsoleto.
- Fuente: Dif34: «deben realizarse utilizando el esquema 4.0 … (obsoleto)»; GML-CR p. 2.
- Estado: CUBIERTO (`gml_parcela.py`; `validador.py` CP-30 vía `gml_lector.py`).
- Hacer: nada.

**P-02 · Raíz y cabecera**
- Regla: raíz `FeatureCollection` en el espacio por defecto WFS 2.0, con `timeStamp`, `numberMatched` y `numberReturned`; `xsi:schemaLocation` con wfs.xsd y CadastralParcels.xsd 4.0; xmlns gml 3.2, cp 4.0, xlink, gmd y xsi. La cabecera «no es necesario modificar su contenido».
- Fuente: GML-CR §4 (estructura completa); Dif34.
- Estado: CUBIERTO (`gml_parcela.construir`; `validador.py` RAIZ, XLINK). El requisito de xlink (E-11) concuerda con los ejemplos oficiales, que lo declaran.
- Hacer: en el validador, comprobar también que `numberMatched` y `numberReturned` coinciden con el número de `member`. La Sede no lo menciona; sería un aviso.

**P-03 · Un `<member>` por parcela; varias parcelas por fichero**
- Fuente: GML-CR §1: «dispondrá de tantas etiquetas <member> como parcelas»; §3.2 («Diferencia con Multirrecinto»).
- Estado: CUBIERTO.

**P-04 · gml:id coherentes**
- Regla: `CadastralParcel gml:id="ES.<ns>.CP.<localId>"`; `MultiSurface_` + id; `Surface_` + id + «.1»; `ReferencePoint_` + id. El srsName es el mismo en MultiSurface, Surface y Point.
- Fuente: GML-CR §1 y §3.2 («Su identificador gml:id es el mismo que el de la etiqueta CadastralParcel al que se le añade el prefijo…»).
- Estado: PARCIAL. `gml_parcela.py` los escribe bien; `validador.py` (GMLID) solo comprueba el de `CadastralParcel`.
- Hacer: avisar también si los gml:id de MultiSurface, Surface y Point no siguen el patrón. Así se detectan ficheros editados a mano o generados por otras herramientas. Es un aviso: la Sede no lo lista.

**P-05 · `cp:areaValue`**
- Regla: superficie cartesiana de la geometría en m², «Redondeo al m2», «Relación directa con etiqueta posList». La Sede ya no la compara con la geometría.
- Fuente: GML-CR §1 y §3.2; IVG-Op (control de cambios, v2.1); CP-Como: «sin decimales».
- Estado: CUBIERTO (`Recinto.area_m2()`, ROUND_HALF_UP; aviso SUP-DISTINTA).
- Hacer: nada. Opcional: decir en el aviso que la Sede no la compara, pero el notario y el registrador cotejan esa superficie con la de la escritura (requisito d de la RGA).

**P-06 · `beginLifespanVersion` / `endLifespanVersion`**
- Regla: la fecha es de libre elección con el formato `AAAA-MM-DDThh:mm:ss`; `endLifespanVersion` es invariable: `xsi:nil="true" nilReason=".../VoidReasonValue/Unpopulated"`.
- Fuente: GML-CR §3.2 («Puede cambiarse por una fecha de libre elección … siempre y cuando se respete el formato»; «Etiqueta invariable»).
- Estado: CUBIERTO (E-19).

**P-07 · Geometría de un solo recinto**
- Regla: una MultiSurface con un solo surfaceMember y una sola Surface. Mensaje de la Sede: «Existe una parcela con varios recintos».
- Fuente: IVG-Op §4.1; GML-CR §1 y §3.2 («NO SE ADMITEN geometrías multirrecinto»); T8-26 §2.3.1 (nota).
- Estado: CUBIERTO (GEO-MULTIPARTE en `geometria.preparar` y en el validador; el lector cuenta surfaceMember y PolygonPatch).

**P-08 · Huecos (donut)**
- Regla: se admiten `gml:interior` dentro de PolygonPatch. El sentido de los huecos es el contrario al del exterior.
- Fuente: GML-CR §1 y §3.2; T8-26 §2.3.1 b.
- Estado: CUBIERTO.
- Hacer: si el hueco es otra parcela (un enclave), avisar de que esa parcela debe ir también en el GML o quedar intacta. Hoy el aviso HUECO solo se da entre parcelas aportadas.

**P-09 · posList**
- Regla: `srsDimension="2"`; `count` = número de vértices incluidos el primero y el último; mínimo 4; el primero igual al último.
- Fuente: GML-CR §1 y §3.2; IVG-Op §4.1 («que haya más de tres puntos»).
- Estado: CUBIERTO (ANILLO-ABIERTO, ANILLO-VERTICES, ANILLO-COUNT).

**P-10 · Sentido de los vértices**
- Regla: exterior en sentido horario; interiores al revés.
- Fuente: GML-CR §1 («El orden de los vértices es en el sentido de las agujas del reloj»); T8-26; INSP.
- Estado: CUBIERTO, pero más estricto que la Sede: `validador.py` da ERROR (ANILLO-SENTIDO), y IVG-Op §4.1 no lista el sentido entre sus validaciones.
- Hacer: en ficheros ajenos, dejarlo como aviso con «corregible» (lo hará el conversor y reparador, mejora 21). Al crear, el plugin lo corrige solo (ya lo hace).

**P-11 · srsName y EPSG**
- Regla: srsName en `gml:MultiSurface`, `Surface` y `gml:Point`, con el mismo código en todos los elementos y ficheros. Solo se admiten 25829, 25830, 25831 y 32628. Mensajes de la Sede: «no se ha especificado sistema de referencia válido», «Se han encontrado distintos sistemas de referencia…», «El sistema de referencia (código EPSG) no se encuentra entre los admitidos».
- Fuente: IVG-Op §4.1 y nota 1; GML-CR §1 y §3.2 («ha de ser el mismo para todas la geometrías … corresponderse con la zona geográfica correcta»).
- Estado: PARCIAL. `gml_lector.leer_datos` reúne todos los srsName (SRC-MEZCLADOS, SRC-FALTA) y el validador comprueba los admitidos. Pero un MultiSurface o un Point **sin** srsName pasa si otro elemento lo trae.
- Hacer: comprobar que cada MultiSurface, Surface y Point tiene srsName (error con el literal de la Sede). Aviso SRC-HUSO si el EPSG no es el de la provincia o la posición: ya existe al crear (`geometria.comprobar_src`); falta en el validador de ficheros ajenos.

**P-12 · 2 decimales; con más, solo cuentan los 2 primeros**
- Fuente: IVG-Op §4.1: «Las coordenadas deberán estar definidas con dos decimales, en caso de haber más, solo se tendrán en cuenta los dos primeros decimales». BU-DGC: «el número de decimales es 2».
- Estado: PARCIAL. Se escribe con 2 decimales redondeando. El validador da aviso DECIMALES, pero `comparacion.py` compara con todos los decimales y la Sede **trunca**: hasta 1 cm de diferencia, el mismo orden que la tolerancia de ±1 cm.
- Hacer: si el GML trae más de 2 decimales, truncar las coordenadas (no redondear) antes de comparar con el Catastro y avisar: «la Sede truncará a 2 decimales».

**P-13 · inspireId**
- Regla: `<Identifier xmlns="http://inspire.ec.europa.eu/schemas/base/3.3">` con `localId` y `namespace`.
- Fuente: GML-CR §3.2; Dif34.
- Estado: CUBIERTO.

**P-14 · Solo dos namespaces**
- Regla: «ES.LOCAL.CP» o «ES.SDGC.CP». Mensaje: «El namespace de la parcela no se encuentra entre los permitidos. (ES.SDGC.CP, ES.LOCAL.CP)».
- Fuente: IVG-Op §2 y §4.1.
- Estado: CUBIERTO (NS-DESCONOCIDO).
- Hacer: en el mensaje, incluir el literal de la Sede (ver V-tabla).

**P-15 · SDGC = referencia catastral de 14 caracteres que exista**
- Regla y mensajes: «El identificador introducido para el namespace ES.SDGC.CP, debe ser de 14 caracteres.» y «…no existe en Catastro.».
- Fuente: IVG-Op §4.1.
- Estado: CUBIERTO. El formato se comprueba sin conexión (NS-SDGC-SIN-RC, más estricto: exige un patrón urbano o rústico) y la existencia en `comparacion.py` (CMP-RC-NO-EXISTE, CMP-RC-AJENA).

**P-16 · Identificador LOCAL**
- Regla: libre, sin más validación que el esquema; «un identificador unívoco dentro del negocio jurídico»; solo alfanuméricos sin acentos, con «.», «_» o «-» como separadores; «El identificativo debe coincidir con el número de la parcela que vaya a constar en las escrituras».
- Fuente: IVG-Op §2; FAQ p. 19; Editor §2.5; CP-Como, paso 3.
- Estado: PARCIAL. Los caracteres están cubiertos (ID_VALIDO). Los nombres automáticos (`Seg_1`, `Div_1`, `Agrupa_1`, `Nueva_N`) no invitan a usar la denominación de la escritura.
- Hacer: en el asistente, una nota o un campo «Denominación en la escritura (finca A, lote 1…)» y avisar si se presenta con nombres automáticos.

**P-17 · `cp:label`**
- Regla: número de parcela del plano: 2 dígitos en urbana, hasta 5 en rústica; en parcelas nuevas, el mismo texto que el localId.
- Fuente: GML-CR §1; INSP; T8-26.
- Estado: CUBIERTO (`gml_parcela.label_por_defecto`).

**P-18 · `cp:nationalCadastralReference`**
- Ver X-09. Estado: CUBIERTO (pone la RC o el localId).

**P-19 · `cp:referencePoint`**
- Regla: punto interior del recinto, donde se sitúa el label; con srsName. Para parcelas nuevas no es obligatorio (T8-26).
- Fuente: GML-CR §1; INSP; T8-26.
- Estado: CUBIERTO (`geometria.punto_interior`; aviso REFPOINT).

**P-20 · Sin `boundedBy`, `zoning`, `validFrom` ni `validTo` en 4.0; CadastralZoning y CadastralBoundary**
- Regla: en 4.0 desaparecen (Dif34). `CadastralZoning` «no se debe incluir esta información en la entrega de nuevas reparcelaciones». `CadastralBoundary` es opcional («Particularmente en el caso de deslindes»).
- Fuente: Dif34; T8-26 §2.3.
- Estado: CUBIERTO al escribir (no los pone). NO CUBIERTO al validar: el validador no avisa si un 4.0 trae `boundedBy`, `zoning` o `CadastralZoning`.
- Hacer: aviso «elemento propio del 3.0 o de las descargas del Catastro: elimínelo» (y el conversor, mejora 21, que lo quite).

**P-21 · Codificación**
- Fuente: GML-CR §4 y Dif34 (`utf-8`); INSP 3.0 (`ISO-8859-1`).
- Estado: CUBIERTO (E-04; E-11 comprobó que la codificación no influye).

**P-22 · Curvas como vértices con flecha < 2 cm**
- Fuente: FAQ p. 13 (tabla: radio 1 m → 0,3 m … > 60 m → 3,0 m).
- Estado: PARCIAL. `geometria.densificar` solo actúa sobre geometrías curvas de QGIS. Los arcos que ya llegan segmentados de un DXF (GDAL los convierte con su propio paso) no se comprueban.
- Hacer: comprobar las rachas de vértices casi colineales y cocirculares con un radio estimado y una separación mayor que la de la tabla, y avisar «posible arco con flecha > 2 cm». Es de prioridad baja.

**P-23 · Topología**
- Regla: «no existan auto intersecciones … no pueden superponerse entre sí ni dejar huecos». Se admiten recintos inscritos (huecos, construcciones).
- Fuente: FAQ p. 23; T8-26 §2.2.
- Estado: CUBIERTO (GEO-INVALIDA, SOLAPE y HUECO). HUECO es un aviso; si el hueco deja fuera parte de una parcela catastral, `comparacion.py` lo eleva a CMP-PARCIAL.

**P-24 · Fincas discontinuas**
- Regla: «se efectuará una representación gráfica de cada una de las porciones».
- Fuente: FAQ p. 23; T8-26.
- Estado: CUBIERTO (mensaje de GEO-MULTIPARTE).
- Hacer: añadir que cada porción tendrá su propia referencia catastral y que la finca registral puede comprender varias parcelas (FAQ p. 37; ver L-23).

**P-25 · El GML representa todas las parcelas afectadas, también las de dominio público colindantes**
- Regla: «todas las parcelas catastrales que deban ser objeto de alteración o modificación, total o parcialmente, incluyendo … las parcelas catastrales o bienes de dominio público colindantes cuando resulten afectados».
- Fuente: FAQ p. 23; T8-26 §2.2.
- Estado: CUBIERTO (CMP-PARCIAL, CMP-DOMINIO-PUBLICO).

**P-26 · Conformidad con el esquema XSD**
- Regla: un GML mal formado no llega a leerlo el validador. Mensaje: «Los siguientes ficheros no se han cargado al no ser válidos, El archivo no cumple el esquema Inspire GML».
- Fuente: IVG-Op §4.1; FAQ p. 19; Editor §2.2.1.4.2.
- Estado: CUBIERTO (`esquemas.py`, E-10, y XLINK).

---

## 3. IVG: validaciones, mensajes de la Sede y resultado

### 3.1 Mensajes literales de la Sede y su equivalente en el plugin

| Mensaje de la Sede (IVG-Op §4.1) | Código del plugin | Estado |
|---|---|---|
| «Los siguientes ficheros no se han cargado al no ser válidos, El archivo no cumple el esquema Inspire GML» | XSD (esquemas.py), XLINK, CP-30 | CUBIERTO |
| «Los ficheros proporcionados tienen una geometría incorrecta» | ANILLO-VERTICES, GEO-VACIA | CUBIERTO |
| «En alguna de las geometrías del fichero gml falta que último punto sea igual al primero…» | ANILLO-ABIERTO | CUBIERTO |
| «Existe una parcela con varios recintos» | GEO-MULTIPARTE | CUBIERTO |
| «Se ha encontrado una geometría vacía dentro del fichero gml.» | GEO-VACIA | CUBIERTO |
| «no se ha especificado sistema de referencia válido» | SRC-FALTA | PARCIAL (ver P-11) |
| «Se han encontrado distintos sistemas de referencia (códigos EPSG) en el fichero gml…» | SRC-MEZCLADOS | CUBIERTO |
| «El sistema de referencia (código EPSG) no se encuentra entre los admitidos» | SRC-NO-ADMITIDO | CUBIERTO |
| «Se ha encontrado una parcela sin identificar dentro del fichero gml.» | ID-VACIO | CUBIERTO |
| «El namespace de la parcela no se encuentra entre los permitidos. (ES.SDGC.CP, ES.LOCAL.CP)» | NS-DESCONOCIDO | CUBIERTO |
| «El identificador introducido para el namespace ES.SDGC.CP, debe ser de 14 caracteres.» | NS-SDGC-SIN-RC | CUBIERTO |
| «El identificador introducido, referenciado por el namespace ES.SDGC.CP, no existe en Catastro.» | CMP-RC-NO-EXISTE (en línea) | CUBIERTO |
| Check4SEC: parcela aportada idéntica a la de origen → error (C4S §4.1.3) | — | **NO CUBIERTO (CONTRADICE DESARROLLO, mejora 14)** |
| Check4SEC: solape entre aportadas → error (C4S §4.1.2) | SOLAPE | CUBIERTO |
| Check4SEC: el contorno total no coincide → «el positivo solo será condicionado en caso de afección a dominio público» (C4S §4.1.4) | CMP-PARCIAL / CMP-SIN-PARCELA (ERROR) | PARCIAL (ver D-03) |

- Hacer (V-00): guardar el literal de la Sede en cada incidencia (p. ej. `Incidencia.sede = "…"`) y mostrarlo en la descripción emergente y en el informe. El usuario reconocerá el mensaje cuando lo vea en la Sede.

**V-01 · Criterio del IVG positivo**
- Regla: «El IVG resultará positivo cuando, el contorno exterior de la geometría resultante sea igual al contorno exterior de la geometría original», con una tolerancia de ±1 cm en los vértices.
- Fuente: IVG-Op §4.1; FAQ p. 23; T8-26 §2.2.
- Estado: CUBIERTO (`comparacion.py`: TOLERANCIA = 0,01; CMP-CONTORNO-OK).

**V-02 · Parcela sin cambios**
- Ver la tabla. Estado: NO CUBIERTO; DESARROLLO lo da por hecho.
- Hacer: en `comparar()`, para cada parcela propuesta, si existe una afectada con distancia de Hausdorff ≤ 1 cm (y el mismo id si es SDGC), dar ERROR «CMP-SIN-CAMBIOS: quítela del GML (la Sede la rechaza)». Excepción: la subsanación de discrepancias no tiene parcelas idénticas por definición. Añadir una prueba.

**V-03 · NPO y NPP**
- Regla: NPO = parcelas de la cartografía catastral bajo el parcelario propuesto; NPP = parcelas del GML.
- Fuente: IVG-Op §4.2.
- Estado: CUBIERTO (parcelas afectadas con área > 0,05 m² dentro del buffer de −1 cm).
- Hacer: excluir la parcela 09000 de rústica (artificio de continuidad: «Deben ser ignoradas», modelo shapefile) si el WFS la devolviera. Hay que comprobar si el WFS la sirve.

**V-04 · Contenido del IVG**
- Regla: PDF firmado con CSV como actuación administrativa automatizada. Incluye: datos del solicitante y del técnico; sentido del informe; parcelación propuesta, catastral y superpuesta; parcelas afectadas total o parcialmente; en los positivos, linderos (Alumnos: «LINDEROS LOCALES / LINDEROS EXTERNOS», «Mantiene RC»), coordenadas, superficie y, en su caso, nuevas RC y «la necesaria declaración de conformidad del titular»; XML adjunto. Texto del positivo: «respeta la delimitación … conforme a las normas dictadas en desarrollo del artículo 10.6 de la Ley Hipotecaria y del artículo 36.2 del texto refundido…».
- Fuente: FAQ p. 26 y 28–29; T8-26 §2.5; CP-Como; Alumnos.
- Estado: PARCIAL. `informe.py` saca el croquis, las incidencias y las coordenadas, pero no los colindantes de cada parcela resultante.
- Hacer: en la comparación y el informe, listar por parcela resultante sus «linderos locales» (otras parcelas del GML) y «externos» (catastrales a ≤ 1 cm, que ya calcula `servicios._separar`), y «Mantiene RC» o «nueva». Es la lista que el notario y el registrador usan para las notificaciones (L-06).

**V-05 · XML del IVG**
- Regla: el XML adjunto trae `<parcelasGML>`, `<parcelasAfecT>` y `<parcelasAfectP>` (ZIP en base64 con los GML). Se descarga por CSV («XML del informe formateado»).
- Fuente: FAQ p. 29–30; T3-26 §2.2.C.5.
- Estado: NO CUBIERTO (mejora 32 pendiente).
- Hacer: lector en Validar o Utilidades: abrir el PDF o XML, extraer las tres capas y cargarlas; **no** guardar ni mostrar los datos del solicitante ni del técnico (ver DL-04).

**V-06 · IVG negativo (desde el 12/03/2025)**
- Ver X-06. Estado: CONTRADICE (textos de `comparacion.py` y `help/index.html`).
- Hacer: cambiar «la Sede dará informe negativo» por «la Sede no emitirá IVG positivo (desde marzo de 2025 no certifica negativos: muestra los errores y deja descargar el GML parcial)».

**V-07 · Autenticado o sin autenticar**
- Ver X-05. Estado: NO CUBIERTO en la ayuda (solo se menciona para el ICUC).
- Hacer: nota en la ayuda: «IVG autenticado (certificado o Cl@ve) para que el informe recoja los datos del técnico competente».

**V-08 · El IVG acompaña, no sustituye; se puede repetir**
- Regla: «puede obtenerse … cuantas veces sea preciso. El informe de validación acompaña, pero no sustituye, al correspondiente procedimiento de actualización catastral».
- Fuente: FAQ p. 27–28.
- Estado: NO CUBIERTO (ayuda).
- Hacer: una línea en la ayuda («Flujo de trabajo», U-07).

**V-09 · El IVG no valida la legalidad**
- Regla: «en ningún caso valida que las operaciones jurídicas … se ajusten a la legalidad vigente o dispongan de las autorizaciones necesarias». Ejemplo: licencia municipal de segregación y unidad mínima de cultivo.
- Fuente: FAQ p. 27–28; T8-26 §2.5; texto del propio IVG (Alumnos).
- Estado: NO CUBIERTO.
- Hacer: aviso fijo en el asistente para segregación y división (y en el informe): «IVG positivo ≠ operación legal: licencia o declaración de innecesariedad, unidad mínima de cultivo (p. ej. C. Valenciana, Decreto 217/1999: 2,5 ha de secano y 0,5 ha de regadío), planeamiento». Opcional: un campo «Unidad mínima de cultivo (m²)» que avise si alguna resultante rústica queda por debajo.

**V-10 · La validación se hace contra la cartografía vigente**
- Regla: el IVG compara «con la cartografía catastral vigente en el momento de la comparación». El WFS está «continuamente actualizado»; las descargas ATOM y Shapefile se renuevan unas dos veces al año («frecuencia estimada … 6 meses»).
- Fuente: IVG-Op §1; INSP §1.2; T3-26 §2.4.
- Estado: PARCIAL. «Comparar con el Catastro» usa el WFS vigente, pero no se avisa si la capa de partida viene de un Shapefile o ATOM antiguo.
- Hacer: en la pestaña Parcela, si la capa no es una descarga del plugin, recomendar «Comparar con el Catastro» antes de subir. En el informe, la fecha y hora de la comparación.

---

## 4. Tipos de alteración, tabla NPO/NPP y tramitación automática

**A-01 · Segregación**
- Regla: de una parcela salen varias. La principal, «solo puede haber una», conserva la RC (SDGC); las segregadas son LOCAL. Superficie y contorno iguales a la original; NPP ≥ NPO + 1.
- Fuente: IVG-Op §3.2; GML-CR §2.2 y §3.1; RD 417/2006, art. 18.3 (FAQ p. 20).
- Estado: CUBIERTO (`alteraciones.proponer/comprobar`, `comparacion.operacion`).
- Problema: el plugin elige como matriz **la mayor** (`_mayor`). En el editor, la matriz se elige con «Seleccionar parcela principal» y la escritura puede designar como matriz el resto menor.
- Hacer: dejar elegir la matriz (columna o botón «Matriz») y mantener «la mayor» como propuesta.

**A-02 · División**
- Regla: todas las resultantes son LOCAL; desaparece la RC; al menos dos nuevas. «no se contempla que sea una subsanación si no se conserva ninguna RC».
- Fuente: IVG-Op §3.2 y §4.2; GML-CR §2.2.
- Estado: CUBIERTO.

**A-03 · Agregación**
- Regla: la resultante conserva la RC de la principal (SDGC, «Debe ser una RC existente … la misma que la de la parcela principal»); las parcelas han de ser colindantes; el umbral es el de X-02.
- Fuente: IVG-Op §3.1; GML-CR §2.1; Editor §2.1; FAQ p. 20.
- Estado: PARCIAL. `capa_parcelas.unir_seleccionadas` aplica el 80 %. `alteraciones.comprobar` no avisa del umbral en la agregación (sí en la segregación y la división). `comparacion.py` no lo mira (aunque IVG-Op lo formula como requisito).
- Hacer: en `alteraciones.comprobar` (AGREGACION), un INFO con los dos criterios: «principal ≥ 80 % de la resultante (guía del IVG) o ≥ 5 × la suma de las agregadas, ≈ 83,3 % (Reglamento Hipotecario, editor); manda la escritura». En `comparacion.py`, con NPO > 1, NPP = 1 y SDGC, un aviso si la parcela catastral de esa RC es < 80 % de la resultante. Cerrar E-17 con esta redacción.

**A-04 · Agrupación**
- Regla: la resultante es LOCAL y recibe una RC nueva; las parcelas han de ser colindantes; la Sede no valida superficies. El editor exige que cada finca sea > 1/5.
- Fuente: IVG-Op §3.1; GML-CR §2.1; Editor §2.1.
- Estado: CUBIERTO (la unión exige colindancia: UNION-NO-COLINDANTES). El criterio de 1/5 no se menciona.
- Hacer: INFO orientativo, como en la división.

**A-05 · Reparcelación**
- Regla: combina uniones y particiones respetando el contorno del conjunto. Unas parcelas conservan alguna RC de origen (SDGC) y otras son LOCAL.
- Fuente: IVG-Op §3.3; GML-CR §2.3 y §3.1; Editor §2.3.
- Estado: **NO CUBIERTO** en el asistente (`alteraciones.TIPOS` no la tiene). `comparacion.operacion` solo la nombra como «Subsanación o reparcelación».
- Hacer: añadir REPARCELACION. Propuesta: conservar las RC de origen en las parcelas que el usuario marque (por defecto, la resultante que más solape con cada origen, como máximo una por RC) y poner LOCAL `Rep_N` en las demás. Comprobaciones: cada SDGC debe ser una RC de origen (ya lo hace CMP-RC-AJENA), sin RC repetidas, y nota «no se tramita de forma automática».

**A-06 · Subsanación de discrepancias**
- Regla general: las mismas parcelas, todas SDGC. **Excepción** «acreditada o instruida por el fedatario»: NPO ≠ NPP y namespaces LOCAL (p. ej. «alineación de una fachada con cesión de terreno a dominio público no catastrado»). «Cada caso excepcional requerirá de estudio».
- Fuente: IVG-Op §3.4; GML-CR §2.4.
- Estado: PARCIAL. `alteraciones.comprobar` (SUBSANACION) avisa si hay alguna LOCAL sin ofrecer la excepción.
- Hacer: si se elige subsanación con alguna LOCAL, no dar aviso sino INFO: «solo en casos acreditados por el fedatario (p. ej. cesión de una franja a vial no catastrado); no se tramita de forma automática».

**A-07 · Subsanar y declarar por separado**
- Regla: «La subsanación es una operación de alteración catastral independiente que no ha de realizarse conjuntamente con ninguna de las operaciones anteriores … el orden será siempre primero SUBSANAR y luego DECLARAR, con procesos independientes».
- Fuente: GML-CR §2.4.
- Estado: NO CUBIERTO.
- Hacer: en el asistente, al elegir segregación, división, agregación, agrupación o reparcelación, recordar: «si además hay que corregir linderos con colindantes, haga antes un GML e IVG de subsanación y, cuando se haya incorporado, el de la operación». En «Comparar», si NPO incluye parcelas que no son la matriz y además NPP ≠ NPO, sugerirlo.

**A-08 · Tabla NPO/NPP/namespace y tramitación automática**
- Regla (IVG-Op §4.2):

| NPO | NPP | Namespaces | Operación | Automática |
|---|---|---|---|---|
| 1 | > 1 | 1 SDGC | Segregación / Subsanación | Sí / **No** |
| 1 | > 1 | 0 SDGC | División | Sí |
| 1 | > 1 | ≥ 2 SDGC | No permitido | — |
| > 1 | 1 | 1 SDGC | Agregación / Subsanación | Sí / **No** |
| > 1 | 1 | 1 LOCAL | Agrupación | Sí |
| = | = | Todos SDGC (y los mismos) | Subsanación | Sí |
| = | = | Alguno LOCAL | Subsanación o reparcelación | No |
| ≠ (resto) | | | Subsanación o reparcelación | No |

- Estado: CUBIERTO en `comparacion.operacion`, pero el texto «Segregación (o subsanación)» no dice que la subsanación en ese caso **no** es automática.
- Hacer: «Segregación (automática) o subsanación (la revisa la Gerencia)», y lo mismo en la agregación.

**A-09 · Qué significa «tramitación automática»**
- Regla: al registrar el fedatario la comunicación, se emite un «Certificado de alteración gráfica» y se asignan RC a las LOCAL.
- Fuente: IVG-Op §4.2, nota 2.
- Estado: NO CUBIERTO (ayuda).
- Hacer: una línea en la ayuda.

**A-10 · Condiciones de la tramitación automática**
- Regla (IVG-Op §5): (1) sin incidencias pendientes ni «ediciones en avance» de la cartografía; (2) esbeltez ≤ 15; (3) mismo municipio y mismo polígono o manzana; (4) mismo tipo urbana o rústica; (5) ninguna parcela «diseminado de urbana (parcelas de urbana en terreno rústico)»; (6) como mucho 30 resultantes de una y 30 a unir.
- Estado:
  - (1) NO VERIFICABLE: avisarlo como limitación.
  - (2) CUBIERTO (ESBELTEZ, con el rectángulo orientado: es una aproximación).
  - (3) CUBIERTO (CMP-TRAMITE).
  - (4) CUBIERTO (CMP-TIPOS).
  - (5) **NO CUBIERTO**.
  - (6) CUBIERTO (N-PARCELAS, CMP-MAS-30).
- Hacer para (5): detectar el diseminado (RC con formato rústico y naturaleza urbana según Consulta_DNPRC, o TIPO «D» del modelo shapefile) y avisar. Para (1): añadir en el texto de la ayuda «la Sede puede no tramitar automáticamente si hay expedientes abiertos sobre las parcelas».

**A-11 · Coherencia con la escritura**
- Regla: «El IVG positivo, deberá ser coherente con la operación notarial … los técnicos … deben consultar en la notaría el tipo de operación … los notarios deberán comprobar esta coherencia». El valor de namespace y localId «debe coincidir con la descripción de la parcela en el título».
- Fuente: IVG-Op §1–2; GML-CR §3.1.
- Estado: NO CUBIERTO.
- Hacer: frase fija en el asistente: «Elija la operación que figurará en la escritura (consúltelo con la notaría)».

**A-12 · Calificación por la escritura (Circular 07.04/06) y asignación de RC (RD 417/2006, art. 18.3)**
- Regla: división o agrupación → RC nuevas; segregación → la matriz conserva la RC; agregación → se mantiene la RC de la finca sobre la que se agrega. «se atenderá a lo especificado en la escritura … En el caso de no constar…» se aplican el quíntuplo o el 20 %.
- Fuente: FAQ p. 19–20.
- Estado: PARCIAL (las RC sí; falta decir que los umbrales solo valen sin escritura).
- Hacer: incluirlo en el texto de ALT-UMBRAL.

**A-13 · Multiparcela con operaciones separadas**
- Hecho comprobado (E-20): la Sede valida, pero muestra «Seleccione operación».
- Estado: CUBIERTO (UNIR-SEPARADAS).

**A-14 · Número máximo en la división automática del editor: 100**
- Fuente: Editor §2.2.2.1.
- Estado: no aplica directamente; tenerlo en cuenta en la fase 10. Por encima de 30 ya hay aviso de tramitación no automática.

---

## 5. Dominio público, viales, cesiones y expropiación

**D-01 · Dominio público catastrado (rústica: parcelas 9001–9999)**
- Regla: hay que incluirlo en el GML «delimitando la parte afectada y no afectada». Usos HG, HC, VT, FF y OT. La 9000 tributa en urbano y no es dominio público. En el shapefile, el tipo «X» es «Dominio público y ajustes topográficos».
- Fuente: FAQ p. 37–38; T2.1; modelo shapefile.
- Estado: CUBIERTO (`refcat.es_dominio_publico`, `servicios._marcar_dominio_publico`, CMP-DOMINIO-PUBLICO). La clase OT no se toma como prueba por sí sola (prudente).

**D-02 · Viales urbanos (no catastrados)**
- Regla: las calles no son parcelas. Una RGA que ocupe viario no tiene parcela con la que cuadrar el contorno.
- Fuente: FAQ p. 37–38; T2.1 («Los viales y cualquier…»).
- Estado: CUBIERTO (CMP-SIN-PARCELA).

**D-03 · Cesión al dominio público y ocupación o incorporación del viario mediante GML**
- Regla:
  - Cesión: la franja cedida debe ir en la RGA como parcela (LOCAL), aunque en urbana «pueda no ser reflejada finalmente en el Catastro».
  - El GML (no el editor) permite la cesión y la incorporación del viario.
  - El positivo queda «condicionado».
  - Hace falta audiencia o informe de la Administración titular (el notario da audiencia; el registrador pide informe).
  - El Catastro lo incorpora automáticamente solo con IVG positivo (art. 18.2 y 18.3 TRLCI); si no, el interesado debe ir a la Gerencia.
- Fuente: FAQ p. 37–38; GML-CR §3.1; IVG-Op §3.4; C4S §4.1.4.
- Estado: PARCIAL. CMP-SIN-PARCELA es ERROR y el texto ya cita la «cesión o incorporación con una parcela propia (LOCAL)». No hay un flujo guiado: el asistente no tiene la cesión.
- Hacer:
  1. Si la superficie sin parcela está **cubierta por una parcela LOCAL** del GML, bajarlo a AVISO: «Ocupación o incorporación de viario no catastrado: el IVG puede salir positivo condicionado; necesita audiencia o informe de la Administración titular y no se tramita de forma automática».
  2. En el asistente, la opción «Subsanación con cesión a vial», que propone una LOCAL `Cesion_1` para la franja.
  3. En la ayuda, el texto de la FAQ.

**D-04 · Lindero con dominio público**
- Regla: no se puede mover sin el deslinde y sin su Administración titular. Protección registral del dominio público aunque no esté inmatriculado.
- Fuente: FAQ; T6.3 («Protección registral del dominio público»).
- Estado: CUBIERTO (LINDA-DOMINIO-PUBLICO, CMP-DOMINIO-PUBLICO).

**D-05 · Inmatriculación de dominio público sin CCDG (art. 206 LH)**
- Regla: RGA «acompañada de informe del Catastro»; el titular aporta planos a la Gerencia, que informa que «no invade otras parcelas».
- Fuente: FAQ p. 38–39; T8-26 §2.4.
- Estado: NO CUBIERTO (fuera del alcance).
- Hacer: nota en la ayuda («Casos especiales»).

**D-06 · Expropiación, concentración parcelaria, equidistribución y deslinde administrativo**
- Regla: la RGA aprobada por la Administración competente no necesita firma de técnico, pero sí cumplir la georreferenciación, la topología y la representación sobre la cartografía catastral. Hay que usar la cartografía catastral desde el principio.
- Fuente: FAQ p. 25 y 39; T8-26 §2.2.7.
- Estado: PARCIAL. Hay límites técnicos: más de 30 parcelas da aviso; `comparacion.MAX_TROZOS` = 25 trozos de 1 km² («demasiado extenso»).
- Hacer: documentar el límite y, en ámbitos grandes, recomendar dividir en polígonos o manzanas. Nota en la ayuda.

**D-07 · Reparcelación urbanística con una parcela afectada en parte**
- Regla: ejemplo de la parcela 53. O bien subsanación previa (art. 18 TRLCI) para ajustar su lindero, o bien incluir la parcela 53 entera, con su resto.
- Fuente: FAQ p. 39–40.
- Estado: CUBIERTO en el diagnóstico (CMP-PARCIAL ya dice «inclúyala entera … o ajuste el lindero»).
- Hacer: completar el mensaje con «o tramite antes una subsanación de esa parcela».

---

## 6. Multiparcela y límites

**M-01 · Varias parcelas por fichero**
- Estado: CUBIERTO (`unir.py`).

**M-02 · Un solo SRC en todo el fichero**
- Fuente: GML-CR §3.2, nota 2: «el srsName debe ser SIEMPRE el mismo».
- Estado: CUBIERTO (UNIR-SRC transforma al del primero).
- Riesgo: transformar entre husos 29/30/31 está bien en ETRS89, pero las parcelas de una provincia con dos husos deben ir en el huso de la cartografía catastral de **ese municipio**. Si se transforma al huso del primer fichero, las coordenadas ya no son las de la cartografía catastral (redondeo al cm tras reproyectar → diferencias de ±1 cm en vértices de lindero común).
- Hacer: si hay husos mezclados, avisar más fuerte: «La Sede compara en el huso del fichero; los vértices reproyectados pueden diferir hasta 1 cm de la cartografía» y proponer el huso de la mayoría o de la provincia.

**M-03 · Más de 30 parcelas → no automática**
- Estado: CUBIERTO.

**M-04 · Mismo municipio, polígono o manzana y tipo**
- Estado: CUBIERTO en la comparación; `unir.py` no lo avisa al juntar ficheros.
- Hacer: llamar a la misma comprobación (por los prefijos de las RC SDGC) en `unir.reunir`.

**M-05 · Parcelas repetidas e ids distintos**
- Estado: CUBIERTO (UNIR-REPETIDA, UNIR-ID-DISTINTO).

**M-06 · El IVG lista las parcelas afectadas total o parcialmente de todo el conjunto**
- Estado: CUBIERTO.

**M-07 · Límites de los servicios**
- Regla: BBOX ≤ ~1 km² en el WFS de parcelas («Area of extension out of limits»); C4S: «tras realizar un determinado número de peticiones … se produzca un error».
- Fuente: C4S §3; E-14.
- Estado: CUBIERTO (trozos de 1 km², máximo de 25; máximo de 60 consultas DNPRC).
- Hacer: si el servicio corta por número de peticiones, mensaje claro («reintente más tarde»).

---

## 7. GML de edificio e ICUC

**E-01 · Esquema y cabecera**
- Regla: BuildingExtended2D 2.0 (borrador modificado por la DGC); `gml:FeatureCollection gml:id="ES.LOCAL.BU"` con `gml:featureMember`; ISO-8859-1; srsName `urn:ogc:def:crs:EPSG::xxxxx`.
- Fuente: BU-DGC.
- Estado: CUBIERTO (`gml_edificio.py`; E-04, E-05, E-22).

**E-02 · Definición de edificio y huella**
- Regla: «construcciones con paredes y techo y que no sean un voladizo fuera de la parcela»; «línea envolvente de todas las construcciones con volumetría sobre rasante de cada parcela catastral, excluyendo voladizos y terrazas o balcones»; `footPrint` = «intersección del edificio con el terreno».
- Fuente: BU-DGC; INSP §3; T8-26 §2.3.1 c.
- Estado: CUBIERTO en la ayuda («sin vuelos, terrazas ni balcones»). Falta decir «solo lo construido **sobre rasante**»: un sótano que sobresale de la huella no se dibuja.
- Hacer: añadirlo a la ayuda y a la descripción emergente del campo.

**E-03 · Building: varios recintos**
- Regla: una `gml:Surface` con un `PolygonPatch` por construcción separada; huecos con `interior`.
- Fuente: BU-DGC.
- Estado: CUBIERTO.

**E-04 · OtherConstruction (piscina)**
- Regla: un `gml:Polygon`; `constructionNature` = `openAirPool`; `conditionOfConstruction` nil; solo piscinas.
- Fuente: BU-DGC; INSP §3.1.3.
- Estado: CUBIERTO (BU-PISCINA-PARTES).

**E-05 · localId**
- Regla: la RC de la parcela existente o, si es nueva, «el identificativo de su parcela en su escritura de constitución»; sufijos «_Edificio_xx» y «_Piscina_xx».
- Fuente: BU-DGC.
- Estado: CUBIERTO (`gml_edificio.identificadores`).

**E-06 · conditionOfConstruction**
- Valores: declined, demolished, functional, projected, ruin, underConstruction.
- Fuente: BU-DGC; BU-Como («underConstruction»).
- Estado: CUBIERTO.

**E-07 · numberOfFloorsAboveGround**
- Regla: si hay varias alturas, la máxima. Es obligatorio en el esquema de la DGC.
- Fuente: BU-DGC; E-22.
- Estado: CUBIERTO (y E-23 completa con BuildingPart).

**E-08 · horizontalGeometryEstimatedAccuracy**
- Ver X-18. Estado: **NO CUBIERTO**: fijo en 0.1 (`Construccion.precision`) y no está en la interfaz.
- Hacer: columna o campo «Precisión (m)» con opciones según el método: 0,1 (levantamiento o proyecto), 0,5, 1, 10 (medida sobre la ortofoto en el visor). Por defecto 0,1 si la huella viene del Catastro o de un DXF del proyecto.

**E-09 · Sin autointersecciones; 2 decimales; anillos cerrados; exterior horario**
- Fuente: BU-DGC.
- Estado: CUBIERTO (`geometria.preparar`).

**E-10 · SRC admitidos**
- Estado: CUBIERTO.

**E-11 · Uso del GML de edificio (art. 202 LH)**
- Regla: sirve para aportar al Registro las coordenadas de la porción de suelo ocupada por la edificación (declaración de obra nueva). El ICUC verifica que está «en su integridad dentro de la parcela … no extralimitándola». El ICUC no valida RGA de parcela.
- Fuente: FAQ p. 17 y 31; T6.3.
- Estado: CUBIERTO (`comparar_edificio`, ayuda).

**E-12 · El ICUC exige una parcela catastral vigente por RC**
- Regla: «el procedimiento de generación de ICUC … no admite la aportación de geometrías de parcela … debe realizarse un trámite previo de alteración del parcelario catastral»; en la Sede, solo «Por Referencia Catastral».
- Fuente: C4S §5 y §5.1.3.
- Estado: **CONTRADICE**. El aviso CMP-BU-SIN-RC dice «Si la parcela aún no existe, el ICUC usa la del GML de parcela».
- Hacer: sustituirlo por «El ICUC necesita la referencia de una parcela catastral vigente: si la parcela es nueva, tramite antes su alteración (GML de parcela, IVG y comunicación o declaración) y después haga el ICUC».

**E-13 · Comprobaciones de Check4SEC para el ICUC**
- Regla: tipo «BU» o «PI»; sin solapes entre huellas; parcela coincidente con el Catastro; cada huella dentro (verde o rojo).
- Fuente: C4S §5.1.
- Estado: CUBIERTO.

**E-14 · BICE, 60 ficheros y 100 m**
- Fuente: ayuda del ICUC (citada en INVESTIGACION; no está en estos documentos).
- Estado: 100 m CUBIERTO; BICE NO CUBIERTO (E-21).
- Hacer: detectar los BICE con Consulta_DNPRC (clase de inmueble) y avisar.

**E-15 · División horizontal**
- Regla: la coordinación es por parcela; «no es preciso facilitar información georreferenciada del inmueble o de sus locales».
- Fuente: FAQ p. 41.
- Estado: NO CUBIERTO (ayuda).
- Hacer: nota en la ayuda para evitar GML innecesarios.

**E-16 · BuildingPart y atributos ampliados**
- Ver X-19. Estado: no aplica. Mantener el modelo simplificado; solo se leen las partes para las plantas.

---

## 8. Conversión 3.0 → 4.0 (fase 9, mejora 21)

Lista completa de cambios (Dif34, más lo que dicen GML-CR y E-11). Estado de todos: NO CUBIERTO (pendiente). El lector ya lee el 3.0 y `unir.py` ya lo reescribe en 4.0 de hecho.

| # | Cambio | Fuente |
|---|---|---|
| C-01 | `gml:FeatureCollection gml:id="ES.SDGC.CP"` → `FeatureCollection` (espacio por defecto wfs/2.0) con `timeStamp`, `numberMatched` y `numberReturned` | Dif34 |
| C-02 | `xmlns:cp` `urn:x-inspire:specification:gmlas:CadastralParcels:3.0` → `http://inspire.ec.europa.eu/schemas/cp/4.0`; schemaLocation con wfs.xsd | Dif34 |
| C-03 | `gml:featureMember` → `member` | Dif34 |
| C-04 | Quitar `gml:boundedBy` | Dif34 |
| C-05 | srsName `urn:ogc:def:crs:EPSG::258xx` → `http://www.opengis.net/def/crs/EPSG/0/258xx` (en MultiSurface, Surface y Point) | Dif34 |
| C-06 | `base:Identifier` (`…BaseTypes:3.2`) → `Identifier xmlns="…/base/3.3"` | Dif34 |
| C-07 | nilReason `other:unpopulated` → `http://inspire.ec.europa.eu/codelist/VoidReasonValue/Unpopulated` | Dif34 |
| C-08 | Quitar `cp:validFrom`, `cp:validTo` y `cp:zoning` | Dif34 |
| C-09 | Declarar `xmlns:xlink` (aunque ya no se use) | E-11; ejemplos de Dif34 y GML-CR |
| C-10 | Quitar `CadastralZoning` si viene (ficheros descargados) | T8-26 |
| C-11 | Codificación UTF-8 (el 3.0 de la DGC venía en ISO-8859-1) | INSP; GML-CR |

**Reparaciones asociadas (mejora 21):**
- cierre de anillos, sentido de los vértices, `count`, `areaValue` y 2 decimales (truncar o redondear; ver P-12);
- `gml:coordinates` → `posList` (CP-Como, anexo);
- `referencePoint` interior;
- gml:id coherentes.

**Lo que no se puede convertir solo:** parcelas con varios `surfaceMember` (la Sede no las admite). Hay que pedir al usuario un identificador para cada parte y avisar de que cambia la operación.

---

## 9. Editor parcelario de la Sede y métodos de división (fases 10 y 11)

**ED-01 · División automática con linderos paralelos a una línea elegida**
- Fuente: Editor §2.2.2.
- Modos:
  1. **Por número de parcelas:** n partes de igual superficie, «o en la combinación más óptima»; máximo 100.
  2. **Por porcentajes:** la suma debe ser 100; si es menor, la última parcela se queda la diferencia; si es mayor, error.
  3. **Por superficies:** igual: el resto va a una última parcela y, si la suma supera la superficie, error.
  4. **Por cuotas:** proporciones; «10 10 20» = «1 1 2».
- El orden de las parcelas sigue la línea de referencia («la parcela de más a la izquierda… 40 %»).
- Estado: NO CUBIERTO (fase 10). La mejora 22 no incluye **cuotas** ni la regla del resto.
- Hacer: implementar los cuatro modos con esa semántica, el aviso de suma > 100 % o > superficie, y el orden respecto a la línea; el resultado, con 2 decimales y redondeo controlado para que la suma cuadre al m². Después, que la división proponga segregación o división según la elección del usuario (la Sede no lo deduce de la superficie).

**ED-02 · Trazado con ángulos y distancias (DAD), paralelas y perpendiculares, snap a vértices y puntos medios, líneas de apoyo**
- Fuente: Editor §2.2.1.
- Estado: NO CUBIERTO por el plugin, pero QGIS ya lo tiene: digitalización avanzada (CAD), forzado de autoensamblado e intersecciones de trazado.
- Hacer: en el manual (fase 12), equivalencias «DAD del editor → herramientas de QGIS». La mejora 23 (franja, paralela y perpendicular a un lado, pivote) cubre los casos de los ejemplos 3.2–3.5 del editor.

**ED-03 · Puntos de apoyo**
- Regla: se cargan desde un GML de parcela o edificio, un DXF FXCC o un TXT «x y» (una fila por punto o todos en una; punto decimal; solo dígitos).
- Fuente: Editor §2.2.1.4.
- Estado: NO CUBIERTO (mejora 33).
- Hacer: exportar los vértices seleccionados con ese formato exacto, en el huso de la parcela y con 2 decimales.

**ED-04 · «Descargar GML Modificaciones» del editor**
- Fuente: Editor v1.5; VGA (el alumno abre «EdicionParcelario.gml» en QGIS).
- Estado: CUBIERTO si es CP 4.0 (lector y validador). Probar con un fichero real del editor y añadirlo a tests/data (sintético).

**ED-05 · Identificadores del editor**
- Regla: alfanuméricos sin acentos, con «.», «_» o «-»; no se pueden cambiar las RC de origen ni las que se conservan (agregación y segregación).
- Fuente: Editor §2.5.
- Estado: CUBIERTO (ID_VALIDO).
- Hacer: no dejar editar el localId de una fila SDGC en la tabla (o avisar).

**ED-06 · Subsanación en el editor: «Documento de conformidad con la representación gráfica catastral»**
- Regla: al pedir el IVG de una subsanación, el editor ofrece ese documento para recoger la aceptación de los titulares afectados.
- Fuente: Editor §2.4.1.
- Estado: NO CUBIERTO.
- Hacer: **no** generar un documento parecido (riesgo de suplantar un modelo oficial). Basta un aviso: «la Sede ofrece, con el IVG de subsanación, el documento de conformidad de los titulares afectados; en rústica, la Gerencia suele pedir la conformidad de todos los colindantes (foro del curso)».

**ED-07 · Unión en el editor**
- Regla: solo colindantes; propone agregación o agrupación y hay que marcar la principal.
- Estado: CUBIERTO (`unir_seleccionadas`).

**ED-08 · Informe de superficies y coordenadas (fase 11, mejora 25)**
- Qué debe incluir según los documentos:
  - la superficie gráfica de cada resultante (la del GML, al m²);
  - la diferencia con la catastral y, opcionalmente, con la registral, con los umbrales de L-08 y L-30;
  - el listado de coordenadas de los vértices («un listado de coordenadas de sus vértices», FAQ p. 24 y 26);
  - los colindantes (V-04);
  - el SRC y el huso;
  - la fecha de la cartografía comparada.
- Fuente: FAQ p. 24, 26 y 34–36; T8-26.
- Estado: NO CUBIERTO (`informe.py` ya trae coordenadas y croquis).
- Hacer: ver G-05 y L-30, y los campos del técnico de L-19.

---

## 10. Georreferenciación, precisión, desplazamientos y superficies

**G-01 · Sistema oficial**
- Regla: ETRS89 (REGCAN95 en Canarias) en UTM (RD 1071/2007). Códigos admitidos: 25829, 25830, 25831 y **32628** («Proyección UTM WGS84 Huso 28N»).
- Fuente: FAQ p. 9 y 23; IVG-Op, nota 1; T8-26.
- Estado: CUBIERTO.
- E-03 (4083): ningún documento lo admite. El mensaje de la Sede sería «El sistema de referencia (código EPSG) no se encuentra entre los admitidos». La DGC rotula su cartografía de Canarias (REGCAN95) como 32628.
- Hacer: si la capa viene en 4083, **reetiquetar** a 32628 sin transformar el datum, que es lo que hace la DGC; confirmarlo con una prueba en la Sede, descargando una parcela de Canarias en 32628 y comparando coordenadas. Verificar también que el WFS en 32628 coincide con el GML de la Sede para esa parcela (E-02).

**G-02 · Husos por provincia**
- Fuente: FAQ p. 9–10 (tabla completa, incluidas Girona 25831, Las Palmas 32628 y Melilla 25830).
- Estado: CUBIERTO (`geometria.HUSOS_PROVINCIA`).
- Hacer: quitar los asteriscos de 17, 35 y 52 y corregir INVESTIGACION §1.3 (X-22).

**G-03 · La base es siempre la cartografía catastral**
- Regla: no se toman coordenadas de una ortofoto ni de un GPS sin más. «Si se georreferencia sin considerar la cartografía catastral es probable que el informe … salga negativo».
- Fuente: FAQ p. 11–12.
- Estado: PARCIAL (implícito en «Comparar»).
- Hacer: frase en la ayuda y en el informe.

**G-04 · Desplazamiento o giro de la cartografía**
- Regla: la RGA «se deberá apoyar en la cartografía catastral existente respetando las distancias relativas». El técnico consignará «la magnitud y dirección del desplazamiento o giro», con los parámetros AX, BX, CX, AY, BY, CY obtenidos de 3 puntos homólogos («Se sugiere resolver las ecuaciones por el método Gauss-Jordan») y comprobados con otros puntos. Un desplazamiento respecto a la ortofoto no justifica una RGA («no porque se vea un desplazamiento con la ortofotografía»).
- Fuente: FAQ p. 11–12; T8-26 §2.2.4.
- Estado: **NO CUBIERTO** para parcelas (solo se cita en la ayuda del ICUC).
- Hacer: herramienta «Ajustar levantamiento a la cartografía catastral». Entrada: pares de puntos (levantamiento ↔ cartografía). Salida:
  - afín de 6 parámetros con 3 puntos (exacta) o por mínimos cuadrados con más de 3, con sus residuos;
  - opción de Helmert de 4 parámetros, que conserva las «distancias relativas»;
  - aplicación a la capa;
  - informe con desplazamiento medio (módulo y acimut), giro y factor de escala.
  Avisar si la escala se aleja de 1 (la afín deforma; la FAQ pide «respetando las distancias relativas»).

**G-05 · Precisión exigida a la RGA**
- Regla: levantamiento con error máximo < 25 cm y el 85 % de los puntos ≤ 20 cm; digitalización sobre la cartografía catastral ±0,20 m (urbana) y ±0,40 m (rústica); contorno ±1 cm.
- Fuente: FAQ p. 23–24; T8-26.
- Estado: PARCIAL. El ±1 cm se comprueba. Los demás valores no se pueden medir en el plugin.
- Hacer: en el informe, el campo «Metodología» (levantamiento, digitalización, proyecto) y una frase con el requisito que corresponde. Si G-04 tiene puntos de control, comprobar los residuos con los umbrales de 25/20 cm.

**G-06 · Precisión nominal de la cartografía y anamorfosis**
- Regla: ±0,5 m (urbana) y ±2 m (rústica) en el 95 % de los casos; «Los metros de cartografía catastral no son iguales a los metros oficiales … oscila entre +/- 0,06% (aplicación del coeficiente de anamorfosis)».
- Fuente: FAQ p. 12.
- Estado: NO CUBIERTO.
- Hacer: en el informe de superficies, explicar que la superficie del GML es la **cartesiana UTM** (la que usan Catastro y Registro) y, como dato informativo, mostrar la superficie corregida del factor de escala, con un rótulo claro. No sustituir nunca la del GML.

**G-07 · Transformación de sistemas antiguos**
- Regla: sistema oficial según el RD 1071/2007 (ETRS89).
- Fuente: FAQ; T8-26.
- Estado: PARCIAL. El plugin transforma desde cualquier SRC (`geometria.transformar`) sin avisar de la calidad de la transformación de datum.
- Hacer: si el origen es ED50 (230xx, 4230), avisar: «compruebe que QGIS usa la rejilla oficial ED50→ETRS89 (PENR2009/NTv2); con Helmert puede haber errores métricos». Mostrar la operación de transformación que elige QGIS.

**G-08 · Margen de tolerancia técnica de la superficie (RD 1464/2007, DA 2.ª)**
- Regla: si la diferencia entre la superficie catastral y la medida no supera el margen, «la superficie catastral se reputará válida» (el Catastro no aceptaría la modificación). Cuando el límite supera el 10 %, se toma 0,1·S. La fórmula completa no se puede extraer del texto (está en una imagen de T2.1).
- Fuente: T2.1, pp. 7–8.
- Estado: NO CUBIERTO.
- Hacer: en el informe de superficies, aviso de que la subsanación de una diferencia pequeña puede no aceptarse. Copiar la fórmula del RD (BOE) antes de implementarla.

**G-09 · Calidad del parcelario**
- Regla: la cartografía catastral «no es perfecta y contiene errores históricos»; hay inconsistencias entre «mapas» (urbana y rústica) del mismo municipio.
- Fuente: T8-26 §2.1; modelo shapefile (tabla MAPA); foro.
- Estado: PARCIAL (CMP-TIPOS).
- Hacer: nota en la ayuda.

---

## 11. Procedimiento legal Catastro-Registro

Todo este bloque está **NO CUBIERTO** en el plugin salvo que se indique otra cosa. No hace falta programarlo: basta una sección «Marco legal y flujo» en la ayuda, avisos en el asistente y campos en el informe.

**L-01 · Ley 13/2015**
- BOE de 25/06/2015, en vigor el 1/11/2015. Introduce la base gráfica georreferenciada, la coordinación, el CRU en el Catastro (art. 3.1 TRLCI), las alertas geográficas, la desjudicialización y la protección del dominio público.
- Fuente: T6.3 §4.1; FAQ.

**L-02 · Resoluciones de requisitos técnicos**
- Regla: Resolución conjunta DGRN-DGC de 26/10/2015 (BOE de 30/10), apartado séptimo (requisitos de la RGA), y Resolución de la DGC de 26/10/2015 (suministro de los notarios).
- Fuente: FAQ p. 8; IVG-Op §1.
- Estado: CONTRADICE en parte. INVESTIGACION y DESARROLLO citan una Resolución conjunta de 2020 (BOE-A-2020-12111) con tolerancias que no aparecen en ningún documento aportado.
- Hacer: comprobar en el BOE si la de 2020 sustituye a la de 2015 y qué dice su anexo; corregir INVESTIGACION §1.3 o citar la fuente exacta. Los textos del plugin no deben dar cifras sin una cita verificable.

**L-03 · Cuándo es obligatoria la representación gráfica (art. 10.3 LH)**
- Regla: procedimientos de concordancia (arts. 199, 200, 201, 202, 203 y 206) y actos de «parcelación, reparcelación, segregación, división, agrupación, agregación o deslinde judicial». Es obligatoria en la reordenación y en la inmatriculación; voluntaria en los demás casos (compraventas…).
- Fuente: T8-26 §2.4; FAQ pp. 4, 6 y 35; T6.3.

**L-04 · Requisitos de la RGA**
- a) aprobada expresamente por el propietario (o la autoridad), manifestando que la CCDG no se corresponde con la realidad;
- b) coordenadas de los vértices;
- c) GML;
- d) los datos coinciden con la escritura (descripción y superficie);
- e) sobre la cartografía catastral, respetando la delimitación.
- Fuente: FAQ p. 22; T8-26 §2.2.
- Hacer: lista de comprobación en el informe (casillas que marca el técnico; el plugin no las puede verificar).

**L-05 · Art. 9.b LH: prevalece la superficie gráfica**
- Regla: una vez inscrita la representación, la cabida es la de la representación; se inscriben la RC y el hecho de estar o no coordinada. El art. 34.1 TRLCI define forma, dimensiones y situación.
- Fuente: FAQ pp. 34 y 37.

**L-06 · Notificación a colindantes (art. 199 LH)**
- Regla: si la base gráfica es catastral, se notifica a los colindantes **registrales**; si es alternativa, a los colindantes **registrales y catastrales**. El notario, en la subsanación (art. 18.2 TRLCI), da audiencia a los titulares colindantes. El registrador tramita el procedimiento si no se les ha oído antes.
- Fuente: T6.3 §4.1; FAQ pp. 32–33.
- Hacer: con V-04, listar en el informe las **parcelas catastrales colindantes** afectadas. Solo las RC, sin titulares (ver DL-02).

**L-07 · Presunción de ubicación y delimitación (arts. 10.5 y 38 LH)**
- Regla: con una base no catastral, la presunción no rige hasta que pasan **6 meses** desde la comunicación al Catastro sin oposición técnica de este. Mientras tanto, la publicidad registral indica que no está validada. La validación del registrador «a los solos efectos de hacer constar la referencia catastral» no basta (art. 53.5 Ley 13/1996).
- Fuente: T6.3 §4.1.

**L-08 · Rectificación de cabida (art. 201 LH)**
- Regla:
  - 201.2: se rectifican sin expediente los datos que no son superficie ni linderos;
  - 201.3: sin expediente si la diferencia es ≤ 10 % de la cabida inscrita con CCDG y coincidencia plena, o ≤ 5 % en la rectificación de superficie;
  - por encima, expediente con citación a los colindantes;
  - un exceso de más del 5 % (10 % con datos catastrales) requiere expediente (199 o 201);
  - antes de 2015 había hasta el 25 % sin colindantes;
  - solo afecta a terrenos (las construcciones van por obra nueva; la propiedad horizontal, por su modificación).
- Fuente: T6.3 §4.1 y §4.3; T8-26 §2.4; FAQ p. 35.
- Hacer: en el informe de superficies, un campo opcional «Superficie inscrita» que muestre la diferencia en % con el rótulo «≤ 5 % / ≤ 10 % / > 10 %: consulte con la notaría o el registro». Sin calificar el caso.

**L-09 · Subsanación de discrepancias (art. 18 TRLCI)**
- Regla: hay discrepancia cuando el error no se debe al incumplimiento del deber de declarar o comunicar (arts. 13 y 14). Procedimiento notarial (18.2) con audiencia a los colindantes; ahora solo se interrumpe con «oposición expresa, y no simple incomparecencia» (18.3.c). También hay vía registral (18.3).
- Fuente: GML-CR §2; T6.3; FAQ p. 32.

**L-10 · Obra nueva (art. 202 LH)**
- Regla: coordenadas de la porción ocupada (GML de edificio + ICUC); libro del edificio; en propiedad horizontal, representación de cada elemento según el proyecto.
- Fuente: T6.3; FAQ p. 17.
- Estado: CUBIERTO en lo técnico (ICUC).

**L-11 · Inmatriculación (arts. 203, 205 y 206 LH)**
- Regla: CCDG obligatoria; la superficie y los datos de identificación coinciden con el Catastro y los linderos los manifiestan los interesados. Expediente de dominio notarial (art. 203, 8 reglas), título público con acta de notoriedad (art. 205) y Administraciones públicas (art. 206, ver D-05).
- Fuente: T6.3; FAQ p. 38.

**L-12 · Descoordinación sobrevenida (art. 11.3 TRLCI)**
- Regla: la coordinación se puede perder por actos no inscritos.
- Fuente: T6.3.

**L-13 · CRU en el Catastro (art. 3.1 TRLCI) y búsqueda por CRU en la Sede**
- Fuente: T6.3; T3-26.
- Estado: NO CUBIERTO. Prioridad baja: descargar por CRU sería posible si existe un servicio.

**L-14 · Intercambio solo telemático**
- Regla: «no es posible la presentación de documentación papel, por correo electrónico, ni vía inicio de expediente electrónico individualizado» entre el Catastro y los fedatarios.
- Fuente: FAQ p. 8.

**L-15 · Flujo y quién presenta qué**
1. El técnico elabora la RGA y el GML y obtiene el IVG (CSV), que entrega al cliente.
2. El notario comprueba la coherencia, protocoliza por CSV o firma el fichero y vigila «la exacta equivalencia entre dicho fichero y la documentación impresa». Puede instar la subsanación.
3. El registrador califica, tramita el art. 199 o 201, inscribe y comunica al Catastro.
4. El Catastro incorpora (automáticamente si se cumple A-10) y devuelve la CCDG actualizada.
- Fuente: T8-26 §2.5; FAQ p. 32–33.
- Si no llega por fedatario o no se tramita: declaración catastral modelo 900D. La puede presentar el titular con planos convencionales, y el IVG le sirve de documentación (Editor §1). Asistente con DNI o NIE, certificado o Cl@ve; tipos de documento obligatorios; expedientes 901N–904N. El «Recordatorio de deber de declarar» permite declarar con su CSV.
- Fuente: asistente de declaraciones; T3-26; T6.3; FAQ p. 25.
- Hacer: diagrama del flujo en la ayuda (U-07).

**L-16 · Comprobación de la vigencia gráfica de la CCDG**
- Regla: la hace el registrador, por CSV. Las CCDG antiguas certificaban la superficie alfanumérica de suelo; hoy certifican la gráfica. No hace falta modificar la escritura si la diferencia es ≤ 10 %.
- Fuente: FAQ p. 36; T3-26.

**L-17 · Una finca registral con varias parcelas catastrales**
- Regla: se puede coordinar si todas sus RC figuran en el folio.
- Fuente: FAQ p. 37.
- Hacer: nota en la ayuda; caso de las parcelas partidas por un término municipal o por la clase de suelo.

**L-18 · Alertas geográficas registrales y planeamiento accesible**
- Regla: sistema de alertas; los municipios ponen el planeamiento a disposición de los registradores (DA 5.ª, plazo de 3 meses).
- Fuente: T6.3.
- Estado: informativo; no aplica.

**L-19 · Contenido del trabajo del técnico**
- Regla: fecha, datos del solicitante, metodología, parcelas afectadas, representación de cada resultante sobre la cartografía catastral, superficie, listado de coordenadas y **declaración bajo su responsabilidad** (metodología seguida, sin incompatibilidades). La RGA de una Administración en sus expedientes no necesita técnico; cualquier interesado puede digitalizar indicando la documentación de apoyo.
- Fuente: FAQ p. 24–25; T8-26 §2.2.6–8.
- Hacer: en el informe (fase 11), campos opcionales (técnico, colegiación, metodología, documentación de apoyo, fecha del trabajo) y un apartado «Declaración del técnico» que **redacta y firma el técnico**, no el plugin. Con el pie: «documento elaborado con una herramienta no oficial; no sustituye al IVG».

**L-20 · Negativo e informe del IVG**
- Ver X-06 y V-06. Los documentos jurídicos antiguos (art. 9 LH: no impide la inscripción) siguen siendo ciertos en lo jurídico, pero hoy no hay un IVG negativo que presentar.

**L-21 · Plazos que aparecen en los documentos**
- 6 meses (presunción, L-07);
- 3 meses (planeamiento municipal);
- unos 6 meses (actualización de ATOM y Shapefile);
- 24 h del IVG (obsoleto, X-07);
- 1/11/2015 (entrada en vigor);
- 12/03/2025 (fin de los IVG negativos).
- Los plazos de notificación a colindantes del art. 199 **no aparecen** en los documentos: no ponerlos en el plugin sin consultar el texto legal.

---

## 12. Navarra y País Vasco

**F-01 · Catastros propios**
- Regla: los conjuntos INSPIRE de la DGC cubren el 95 % del territorio «(excepto País Vasco y Navarra)». Los catastros de Navarra, Álava, Bizkaia y Gipuzkoa también publican CadastralParcels 4.0.
- Fuente: INSP §1.2; GML-CR, p. 2.
- Estado: CUBIERTO (RC-FORAL, descarga de Navarra, bloqueo de la creación de GML).
- Matiz: GML-CR solo dice que **publican** en 4.0, no que acepten el IVG de la DGC. La decisión del plugin (E-18) es correcta con la información disponible.

**F-02 · Detección por la RC**
- Estado: PARCIAL. Solo se detectan las RC **rústicas** por la provincia (01, 20, 31, 48). Las urbanas no llevan provincia y una RC de 9 dígitos de Navarra sí se reconoce. Un GML urbano dibujado en Bizkaia no se detecta: `comparacion.py` acabará en «CMP-SIN-ORIGEN … compruebe la posición y el SRC».
- Hacer: detección **por posición** (cajas o polígonos de Navarra y de los tres territorios del País Vasco, como `CAJA_NAVARRA`) en la pestaña Parcela y en la comparación, con el aviso foral en lugar de CMP-SIN-ORIGEN.

**F-03 · Navarra: licencia CC BY 4.0 y cita**
- Fuente: INVESTIGACION (no está en estos documentos).
- Estado: CUBIERTO (FUENTE_NAVARRA).

---

## 13. Protección de datos y licencia de los datos

**DL-01 · Datos libres y protegidos**
- Regla: la DGC liberó lo que no es «protección de datos» (Ley de Economía Sostenible). La titularidad y el valor necesitan autenticarse como titular; la CCDG la obtiene solo el titular o una administración; la consulta descriptiva y gráfica es libre y no lleva coordenadas.
- Fuente: T3-26 §2.4; FAQ pp. 7 y 15.
- Estado: CUBIERTO (solo WFS, RCCOOR y DNPRC, sin titulares).

**DL-02 · Colindantes**
- Regla: para notificar hacen falta los titulares, que son datos protegidos.
- Estado: CUBIERTO (el plugin solo maneja RC).
- Hacer: no ampliarlo nunca a titulares; avisarlo en la ayuda (los obtiene el fedatario).

**DL-03 · Licencia de uso**
- Regla: «licencia de cesión de derechos que se obtendrá de manera automática, suponiendo su uso el conocimiento y aceptación». Las descargas masivas exigen aceptar las cláusulas y ceder datos personales a la DGC.
- Fuente: INSP §1.2 y §3.2; T3-26; manuales de descarga.
- Estado: CUBIERTO (cita y fecha en los metadatos; descarga puntual; sin datos de la DGC en el ZIP; INVESTIGACION §4).
- Hacer: añadir en la ayuda «el uso de los datos implica aceptar la licencia de la DGC» con enlace.

**DL-04 · IVG y XML**
- Regla: contienen datos personales del solicitante y del técnico.
- Estado: no aplica todavía (mejora 32).
- Hacer: el lector del XML no debe copiar ni mostrar esos campos ni guardarlos en las capas.

**DL-05 · CSV**
- Regla: el CSV de una CCDG da acceso al documento completo, con datos protegidos.
- Fuente: FAQ p. 15–16.
- Hacer: si algún día se lee una CCDG por CSV, no conservar los datos protegidos.

**DL-06 · Mapa de fondo**
- Regla: PNOA con la cita «PNOA cedido por © Instituto Geográfico Nacional (CC BY 4.0)».
- Estado: CUBIERTO (`gui/fondo.py`).

**DL-07 · Calidad: los datos catastrales son una guía, no la verdad**
- Regla: «verificar y validar los datos si es crucial».
- Fuente: foro del curso (respuesta del tutor).
- Hacer: frase en la ayuda («Datos»).

---

## 14. Lo que una herramienta no oficial debe avisar y lo que no debe prometer

| # | Aviso o límite | Fuente | Estado |
|---|---|---|---|
| N-01 | No es oficial; hay que validar siempre en la Sede | INVESTIGACION §4; E-06 | CUBIERTO (`info.AVISO_LEGAL`, ayuda, comentario en el GML) |
| N-02 | No garantiza un IVG positivo: hay reglas no publicadas; la cartografía puede cambiar o tener ediciones en curso; no se ven las incidencias pendientes | IVG-Op §5; E-06 | PARCIAL: añadir en el resultado de «Comparar»: «simulación con la cartografía vigente a las hh:mm» |
| N-03 | IVG positivo ≠ operación legal (licencia, unidad mínima de cultivo, autorizaciones) | FAQ; T8-26 | **NO CUBIERTO** (V-09) |
| N-04 | Ni el plugin ni el IVG sustituyen al procedimiento (notario, registro, Catastro) ni a la responsabilidad del técnico | FAQ p. 27–28; T8-26 | NO CUBIERTO (ayuda) |
| N-05 | Los productos derivados no pueden presentarse como «cartografía catastral» ni suplantar a la DGC: el informe HTML no debe parecerse a un IVG (sin CSV, sin escudo, sin «certifica») | Licencia DGC (INVESTIGACION §4) | CUBIERTO en el espíritu; revisar el título del informe: «Informe de comprobación (no oficial)», nunca «Informe de validación gráfica» |
| N-06 | La operación elegida debía coincidir con la escritura (decide el notario) | IVG-Op §1 | NO CUBIERTO (A-11) |
| N-07 | Desde el 12/03/2025 no hay IVG negativo certificado | T8-26 | CONTRADICE (V-06) |
| N-08 | Navarra y País Vasco: el GML de la DGC no sirve | INSP; E-18 | CUBIERTO / PARCIAL (F-02) |
| N-09 | La superficie del GML es la cartesiana UTM, no «la real» | FAQ p. 12 | NO CUBIERTO (G-06) |
| N-10 | La subsanación necesita conformidad o audiencia de los colindantes; el dominio público, de su Administración | FAQ; Editor §2.4.1; foro | PARCIAL (solo dominio público) |
| N-11 | El ICUC solo sirve con una parcela catastral vigente | C4S | **CONTRADICE** (E-12) |
| N-12 | No prometer en `metadata.txt` funciones que aún no existen («convert old 3.0 files…», «divide parcels», «area and coordinate reports») | metadata.txt `about` | CONTRADICE (estado 0.1.0): ajustar el texto o marcar «planned» hasta la 1.0.0 |
| N-13 | «Listo para el ICUC» (`gui/pestana_validar.py:389`) | — | Matizar: «sin errores conocidos: preséntelo en la Sede» |
| N-14 | No usar construcciones o parcelas ficticias para obtener informes firmados («use solo construcciones reales») | ayuda | CUBIERTO (ICUC); añadir lo mismo para el IVG |
| N-15 | Las RC que se conservan y las nuevas las asigna el Catastro; el plugin no «asigna» RC | IVG-Op | CUBIERTO en los textos |

---

## 15. Casos y opciones que el plugin no contempla

1. **Reparcelación** como tipo de alteración (A-05).
2. **Subsanación excepcional con parcelas LOCAL** (cesión al dominio público no catastrado, alineación de fachada) (A-06, D-03).
3. **Incorporación u ocupación de viario** con una parcela LOCAL y «positivo condicionado» (D-03, X-14).
4. **Subsanar primero y declarar después** en dos GML separados; aviso al combinar (A-07).
5. **Parcela sin cambios** incluida por error en el GML (V-02).
6. **Elegir la parcela matriz** en la segregación cuando no es la mayor (A-01).
7. **Umbral de la agregación** (80 % o quíntuplo) en la comparación y el asistente; **1/5** en la agrupación (A-03, A-04).
8. **Diseminado de urbana** (no se tramita de forma automática) (A-10).
9. **BICE** en el ICUC (E-14).
10. **Desplazamiento o giro**: transformación afín o Helmert con informe de parámetros (G-04).
11. **Precisión del edificio** según el método: 0,1 frente a 10 m (E-08).
12. **División por cuotas** y regla del resto o error en porcentajes y superficies (ED-01).
13. **Puntos de apoyo** .txt para el editor de la Sede (ED-03, mejora 33).
14. **Lector del XML del IVG** (V-05, mejora 32).
15. **Colindantes por parcela resultante** («linderos locales y externos») en el informe (V-04, L-06).
16. **Crear una parcela a partir de una lista de coordenadas** (TXT o CSV de levantamiento, «Puntos a ruta» de T4.4; gmlweb lo ofrece). No está en el plan.
17. **Detección foral por posición** (urbana del País Vasco) (F-02).
18. **Truncado a 2 decimales** al comparar ficheros ajenos (P-12).
19. **srsName ausente en algún elemento** (P-11).
20. **Elementos del 3.0 o de descargas dentro de un 4.0** (`boundedBy`, `zoning`, `CadastralZoning`) (P-20).
21. **Enclaves** (huecos que son otra parcela) (P-08).
22. **Finca registral con varias parcelas** y **fincas partidas por el término municipal o la clase de suelo** (L-17, G-09).
23. **Inmatriculación de dominio público (art. 206)** e **inmatriculación con CCDG**: solo informativo (D-05, L-11).
24. **Expedientes administrativos grandes** (concentración, equidistribución, expropiación) por encima de 25 km² o de 30 parcelas (D-06).
25. **Arcos ya segmentados con flecha > 2 cm** (P-22).
26. **Superficie inscrita frente a gráfica** (umbrales del 5 % y el 10 %) y **tolerancia del RD 1464/2007** en el informe (L-08, G-08).
27. **Transformación desde ED50** sin rejilla (G-07).
28. **4083 → 32628** en Canarias (G-01).
29. **Deslinde con `CadastralBoundary`**: opcional y nada habitual; basta no rechazarlo.
30. **División horizontal**: explicar que no necesita GML (E-15).
31. **Mensajes literales de la Sede** en cada incidencia (V-00).
32. **Aviso de cartografía antigua** si la capa no viene del WFS vigente (V-10).

---

## 16. Riesgos legales y de presentación

1. **Operación distinta de la escritura.** El asistente propone nombres y namespaces y el usuario podría presentar como «segregación» lo que la escritura llama «división». El IVG sería positivo, pero el notario lo rechazaría o el Catastro lo trataría mal (IVG-Op §1). → Aviso A-11 y elección explícita.
2. **Promesa implícita de resultado.** «Listo para…» y «El contorno coincide» pueden leerse como una garantía. La Sede tiene reglas no publicadas y bloqueos que el plugin no ve (incidencias, ediciones en curso). → N-02, N-13.
3. **Mensajes desactualizados sobre el IVG negativo.** Pueden llevar al usuario a creer que obtendrá un IVG negativo «válido» para el notario (FAQ 2017). → V-06.
4. **ICUC de una parcela nueva.** El mensaje actual induce a un intento que la Sede no admite. → E-12.
5. **Dominio público y viario.** Presentar un GML que ocupa calle o camino sin informe de su Administración: problemas registrales y no tramitación automática. El mensaje actual (ERROR) puede impedir un caso legítimo (cesión o incorporación). → D-03.
6. **Legalidad urbanística o agraria.** Una segregación con IVG positivo puede ser nula (unidad mínima de cultivo) o necesitar licencia. → V-09, N-03.
7. **Cifras normativas sin fuente verificable.** Tolerancias de «anexo II», 0,5/2 m y 5 % atribuidas a la Resolución de 2020 sin estar en los documentos. Si se muestran como norma y son incorrectas, el riesgo es de confianza y de responsabilidad. → L-02.
8. **Informe HTML confundible con un documento oficial.** Croquis, coordenadas y «resultado» pueden adjuntarse a una escritura como si fueran el IVG. → N-05: título, pie y marca de agua «no oficial, sin CSV»; ningún logo.
9. **Datos personales.** El futuro lector del XML del IVG maneja datos del solicitante y del técnico; una ampliación a colindantes podría tentar a pedir titulares. → DL-02, DL-04.
10. **Licencia de los datos.** Redistribuir capas descargadas sin transformar o presentarlas como «cartografía catastral». → Mantener INVESTIGACION §4; añadir la aceptación de la licencia en la ayuda (DL-03).
11. **Reproyecciones silenciosas.** Unir ficheros de husos distintos o transformar desde ED50 puede mover vértices de linderos comunes más de 1 cm y dar un IVG no positivo, o lo que es peor, uno positivo con una geometría desplazada. → M-02, G-07.
12. **Territorios forales.** Un GML urbano de Bizkaia o Gipuzkoa no se detecta. → F-02.
13. **Funciones anunciadas que aún no existen** (`metadata.txt`). → N-12.
14. **Docs internos que afirman lo que el código no hace** (mejora 14, «parcelas sin cambios»): las pruebas a mano podrían dar por buena una comprobación inexistente. → V-02.

---

## 17. Incoherencias internas del repositorio detectadas

| Dónde | Qué | Arreglo |
|---|---|---|
| `docs/DESARROLLO.md`, mejora 14 (✅) | Dice que detecta «parcelas sin cambios»; `core/comparacion.py` no lo hace (no hay código ni prueba) | Implementar V-02 o quitar la frase |
| `core/comparacion.py`, CMP-BU-SIN-RC | «el ICUC usa la del GML de parcela» contradice C4S | E-12 |
| `docs/INVESTIGACION.md` §1.3 | Tolerancias de la «Resolución conjunta … BOE-A-2020-12111, anexo II» sin respaldo en los documentos | L-02: verificar en el BOE y citar el apartado exacto |
| `docs/INVESTIGACION.md` §1.3 y `core/geometria.py` | «Las Palmas no aparece en la tabla»: sí aparece (FAQ p. 10, junto con Girona y Melilla) | X-22 / G-02 |
| `core/alteraciones.py` (docstring) | «Criterios orientativos del editor … segregada menor del 20 %», pero no el de la agregación (80 % o quíntuplo) que sí usa `capa_parcelas.py` | A-03 |
| `help/index.html` («Agregación o agrupación») | Solo el 80 %; no el quíntuplo ni que manda la escritura | A-03, A-12 |
| `help/index.html` y `comparacion.py` | «informe negativo» | V-06 |
| `metadata.txt` | Anuncia la conversión 3.0, la división y los informes, aún sin hacer | N-12 |
| `core/validador.py` | ANILLO-SENTIDO como ERROR, más estricto que la lista de la Sede | P-10 (aviso con «corregible») |

---

## 18. Prioridades propuestas

**Alta** (corrigen errores o contradicciones, poco trabajo):
- V-02: parcela sin cambios.
- E-12: texto del ICUC.
- V-06 / N-07: IVG negativo.
- A-05: reparcelación en el asistente.
- A-11, V-09, A-07: avisos de escritura, legalidad y orden subsanar–declarar.
- D-03: viario y cesión como aviso «positivo condicionado».
- L-02: verificar la Resolución de 2020.
- X-22: tabla de husos.
- N-12: metadata.

**Media:**
- P-11: srsName por elemento.
- P-12: truncado.
- A-03: umbral de la agregación en la comparación.
- A-01: elegir la matriz.
- A-10(5): diseminado.
- F-02: detección foral por posición.
- E-08: precisión del edificio.
- V-04: colindantes por parcela.
- P-20: restos del 3.0.
- M-02: aviso de husos.
- G-07: ED50.

**Fases pendientes con los requisitos de este informe:**
- Conversor (§8).
- División (ED-01, con cuotas y la regla del resto).
- Informe de superficies (ED-08, G-06, G-08, L-08, L-19).
- XML del IVG (V-05).
- Puntos de apoyo (ED-03).
- Ajuste por desplazamiento o giro (G-04).
- Sección «Marco legal y flujo» del manual (§11).
