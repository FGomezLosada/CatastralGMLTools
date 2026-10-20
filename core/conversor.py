"""
Conversor de GML de parcela catastral del esquema 3.0 al 4.0, y reparación de un GML 4.0 (fase 9, AU-53; mejora 21).

La Sede Electrónica del Catastro solo admite el esquema 4.0 desde el 12/12/2024. Las diferencias (DGC, «Diferencias GML
parcela v3 v4», docs/INVESTIGACION.md §1.4 y §7.3): raíz FeatureCollection de WFS 2.0 con timeStamp, numberMatched y
numberReturned; cp 4.0; member en lugar de gml:featureMember; sin gml:boundedBy; Identifier de base 3.3; srsName
http://www.opengis.net/def/crs/EPSG/0/…; nilReason de INSPIRE; sin validFrom, validTo ni zoning.

En lugar de cambiar etiquetas una a una, el fichero se lee (gml_lector) y se vuelve a escribir con el escritor del plugin
(gml_parcela), el mismo que crea los GML de la pestaña Parcela. Así, además del esquema, quedan bien de paso: xmlns:xlink,
srsName en cada geometría, gml:MultiSurface, anillos cerrados y con su count, exterior horario y huecos antihorarios,
coordenadas al centímetro (2 decimales), superficie (areaValue) igual a la de la geometría y punto de referencia dentro
de la parcela. Se conservan identificadores, namespaces, label, nationalCadastralReference y beginLifespanVersion.

El informe dice qué ha cambiado (comparando la validación del original con la del resultado) y qué queda por corregir a
mano (p. ej. una referencia catastral mal escrita o un solape), que el conversor no inventa.

Un GML en coordenadas geográficas (EPSG:4326 o 4258, p. ej. exportado de una app o de un visor) se pasa al huso UTM
de la zona, que es lo que admite la Sede.

Sin interfaz. Nunca sobrescribe el fichero original.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import datetime
import os
import re
import xml.etree.ElementTree as ET

from qgis.core import QgsCoordinateReferenceSystem, QgsGeometry

from . import geometria as geo
from . import gml_lector as gl
from . import gml_parcela as gp
from . import refcat
from . import validador as va
from .ficheros import comprobar_destino, misma_ruta
from .incidencias import AVISO, ERROR, INFO, Incidencia

NAMESPACES = {'ES.SDGC.CP': gp.SDGC, 'ES.LOCAL.CP': gp.LOCAL}
#Problemas de lectura que impiden convertir (el resto los arregla el escritor: srsName, Z, estructura de la geometría…)
BLOQUEANTES = {'XML-MAL-FORMADO', 'GML-SIN-ELEMENTOS', 'FICHERO', 'COORDENADAS', 'GEO-VACIA', 'SRC-FALTA', 'SRC-MEZCLADOS',
               'GEO-CURVAS-GML'}
CAMBIOS_30_40 = ("Esquema 3.0 → 4.0: raíz FeatureCollection (WFS 2.0), «member» en lugar de «featureMember», Identifier de "
                 "base 3.3, srsName http://www.opengis.net/def/crs/EPSG/0/…, nilReason de INSPIRE; se quitan boundedBy, "
                 "validFrom, validTo y zoning")
#Lo que el conversor deja bien al reescribir (en Validar se ofrece «Reparar» si el GML 4.0 tiene alguno de estos)
REPARABLES = {'CP-30', 'XLINK', 'RAIZ', 'GMLID', 'SRC-ELEMENTO', 'DIMENSION', 'GEO-ESTRUCTURA', 'ANILLO-ABIERTO',
              'ANILLO-COUNT', 'ANILLO-SENTIDO', 'ANILLO-REPETIDO', 'DECIMALES', 'SUP-DISTINTA', 'SUP-FALTA', 'REFPOINT'}
SUFIJO_30 = '_v4'
SUFIJO_40 = '_reparado'


GENERICO = 'GML genérico'
#Etiqueta cuyo nombre empieza por un número (p. ej. <ogr:2082108VF2628S>): XML no válido. Lo produce «Guardar como» GML de
#QGIS (OGR) con una capa que se llama como la referencia catastral (fichero del curso, 15/10/2026)
ETIQUETA_NUMERO = re.compile(rb'<(/?)([A-Za-z_][\w.-]*:)?(\d[\w.-]*)')
CAMPOS_ID = ('localId', 'localid', 'LOCALID', 'nationalCadastralReference', 'refcat', 'REFCAT', 'referencia', 'rc', 'RC')
GEOMETRIAS = ('MultiSurface', 'Polygon', 'Surface', 'MultiPolygon')
#Elementos de una parcela del esquema INSPIRE (3.0 y 4.0); lo demás (fuera del espacio gml) son datos ajenos que la Sede
#rechaza (p. ej. Clave_Obra, Clave_Exp… dentro de Identifier en GML de expropiaciones)
CONOCIDOS = {'CadastralParcel', 'areaValue', 'beginLifespanVersion', 'endLifespanVersion', 'geometry', 'inspireId',
             'Identifier', 'localId', 'namespace', 'versionId', 'label', 'nationalCadastralReference', 'referencePoint',
             'validFrom', 'validTo', 'zoning', 'administrativeUnit', 'basicPropertyUnit', 'boundary'}
MAX_AJENOS = 6


def leer_generico(datos):
    """
    Lee un GML que no es INSPIRE (p. ej. el de «Guardar como» GML de QGIS u ogr2ogr): cada objeto con geometría poligonal
    y los campos localId, namespace, label, nationalCadastralReference y areaValue que tenga (o refcat, referencia…).
    Devuelve (ResultadoLectura con version GENERICO, avisos de lo arreglado) o (None, []) si no hay parcelas.
    """
    arreglado = ETIQUETA_NUMERO.sub(rb'<\1\2_\3', datos)
    avisos = []
    if arreglado != datos:
        ejemplo = ETIQUETA_NUMERO.search(datos).group(0).decode('utf-8', 'replace')
        avisos.append(f"El original no es XML válido: tiene etiquetas que empiezan por un número ({ejemplo}…>), algo que "
                      "hace «Guardar como» GML de QGIS con una capa cuyo nombre empieza por un número")
    try:
        raiz = ET.fromstring(arreglado)
    except ET.ParseError:
        return None, []
    resultado = gl.ResultadoLectura(version=GENERICO, datos=arreglado, texto=gl._texto(arreglado), raiz=raiz.tag)
    srs = set()
    for miembro in raiz.iter():
        if gl.nombre_local(miembro.tag) not in ('featureMember', 'member', 'featureMembers'):
            continue
        for objeto in list(miembro):
            propiedad = next((h for h in objeto if any(gl.nombre_local(d.tag) in GEOMETRIAS for d in h.iter())), None)
            if propiedad is None:
                continue
            lista, _, _, decimales, _, curvas, problema = gl._geometria_segura(propiedad)
            if not lista or curvas or problema:
                continue
            srs |= {gl.epsg_de_srsname(d.get('srsName')) for d in objeto.iter() if d.get('srsName')}
            campos = {gl.nombre_local(h.tag): (h.text or '').strip() for h in objeto if len(h) == 0}
            local_id = next((campos[c] for c in CAMPOS_ID if campos.get(c)), '')
            try:
                area = int(round(float(campos['areaValue']))) if campos.get('areaValue') else None
            except ValueError:
                area = None
            resultado.elementos.append(gl.ElementoGML(gl.PARCELA, local_id, campos.get('namespace', ''),
                                                      gl.geometria_de(lista), campos.get('label', ''),
                                                      campos.get('nationalCadastralReference', ''), area,
                                                      decimales=decimales))
    srs.discard(None)
    if not resultado.elementos:
        return None, []
    if not srs:
        resultado.incidencias.append(Incidencia(ERROR, 'SRC-FALTA', "El GML no dice en qué sistema de referencia están las "
                                                                   "coordenadas (srsName): vuelva a exportar la capa desde "
                                                                   "QGIS con su SRC (p. ej. EPSG:25830)"))
    elif len(srs) > 1:
        resultado.incidencias.append(Incidencia(ERROR, 'SRC-MEZCLADOS', "Las parcelas del GML están en sistemas de "
                                                                       "referencia distintos (" + ", ".join(
                                                                           f"EPSG:{s}" for s in sorted(srs)) + ")"))
    else:
        resultado.epsg = srs.pop()
    return resultado, avisos


def generico(ruta):
    """Número de parcelas que se pueden convertir de un GML genérico (no INSPIRE), o 0."""
    try:
        with open(ruta, 'rb') as f:
            lectura, _ = leer_generico(f.read())
    except OSError:
        return 0
    return len(lectura.elementos) if lectura is not None else 0


def ajenos(datos):
    """Nombres de los elementos de las parcelas que no son del esquema INSPIRE (ni de gml), sin repetir y en orden."""
    try:
        raiz = ET.fromstring(datos)
    except ET.ParseError:
        return []
    vistos = []
    for parcela in raiz.iter():
        if gl.nombre_local(parcela.tag) != 'CadastralParcel':
            continue
        for d in parcela.iter():
            nombre = gl.nombre_local(d.tag)
            if 'opengis.net/gml' not in gl.espacio(d.tag) and nombre not in CONOCIDOS and nombre not in vistos:
                vistos.append(nombre)
    return vistos


def destino_propuesto(ruta, version='CP 3.0'):
    """Fichero de salida junto al original («parcela_v4.gml» o «parcela_reparado.gml»), sin pisar uno que ya exista."""
    base, _ = os.path.splitext(ruta)
    sufijo = SUFIJO_40 if version == 'CP 4.0' else SUFIJO_30
    propuesta = f"{base}{sufijo}.gml"
    n = 2
    while os.path.exists(propuesta):
        propuesta = f"{base}{sufijo}_{n}.gml"
        n += 1
    return propuesta


def fecha_original(texto):
    """beginLifespanVersion del original (la de la primera parcela que la tenga), o None si no la tiene o es nula."""
    for valor in re.findall(r'beginLifespanVersion[^>]*>\s*([^<\s][^<]*?)\s*<', texto or ''):
        for formato in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d'):
            try:
                return datetime.datetime.strptime(valor[:19], formato)
            except ValueError:
                continue
    return None


def geograficas(lectura):
    """¿Coordenadas geográficas (grados: EPSG:4326, 4258…) que el conversor puede pasar al huso UTM de la zona?"""
    crs = QgsCoordinateReferenceSystem(f'EPSG:{lectura.epsg}') if lectura.epsg else None
    return (lectura.epsg not in geo.SRC_ADMITIDOS and crs is not None and crs.isValid() and crs.isGeographic()
            and bool(lectura.elementos))


def a_src_admitido(lectura):
    """
    (epsg, geometrías, nota) para escribir el GML en un SRC que admita la Sede. En geográficas (p. ej. EPSG:4326 de una
    app o de «Guardar como»), se pasan al huso UTM de la zona; el GML 3.2 escribe latitud, longitud, y si el primer número
    parece la latitud de España se leen en ese orden. Otros SRC no admitidos (ED50, 3857…) se dejan para que los avise el
    escritor: su paso a ETRS89 necesita la rejilla oficial, y eso es mejor hacerlo en QGIS con la capa.
    epsg None si no se puede: la nota dice por qué.
    """
    geometrias = [e.geometria for e in lectura.elementos]
    if not geograficas(lectura):
        return lectura.epsg, geometrias, ''
    crs = QgsCoordinateReferenceSystem(f'EPSG:{lectura.epsg}')
    girar = geo.orden_lat_lon(geometrias)
    if girar:
        geometrias = [geo.girar_ejes(g) for g in geometrias]
    epsg = geo.epsg_recomendado(QgsGeometry.collectGeometry(geometrias), crs)
    if epsg is None:
        return None, [], (f"Las coordenadas están en EPSG:{lectura.epsg} (grados) y no caen en España: no se puede saber "
                          "a qué huso pasarlas")
    transformadas = [geo.transformar(g, crs, epsg) for g in geometrias]
    if any(g is None for g in transformadas):
        return None, [], f"No se han podido pasar las coordenadas de EPSG:{lectura.epsg} a EPSG:{epsg}"
    return epsg, transformadas, (f"Coordenadas en grados (EPSG:{lectura.epsg}) pasadas a EPSG:{epsg}, el huso UTM de la "
                                 "zona (la Sede solo admite ETRS89 UTM 29, 30 y 31 y, en Canarias, 32628)"
                                 + ("; venían en el orden latitud, longitud" if girar else ''))


def _codigos(informe):
    """{código: primer mensaje} de los errores y avisos de un informe de validación."""
    resultado = {}
    for i in informe.incidencias:
        if i.nivel in (ERROR, AVISO) and i.codigo not in resultado:
            resultado[i.codigo] = i.mensaje
    return resultado


def _leer_bytes(ruta):
    try:
        with open(ruta, 'rb') as f:
            return f.read()
    except OSError:
        return b''


def convertir(ruta, destino, fecha=None):
    """
    Convierte (CP 3.0) o repara (CP 4.0) el GML de parcela ruta y lo escribe en destino.
    fecha: beginLifespanVersion si el original no la tiene (por defecto, ahora).
    Devuelve (escrito, versión del original, cambios: lista de textos, incidencias).
    """
    if misma_ruta(ruta, destino):
        return False, '', [], [Incidencia(ERROR, 'CONV-DESTINO', "El fichero de salida no puede ser el original: elija "
                                                                 "otro nombre")]
    problema = comprobar_destino(destino, (ruta,))
    if problema is not None:
        return False, '', [], [problema]
    lectura = gl.leer(ruta)
    version = lectura.version
    previos = []
    if not version.startswith(('CP', 'BU')) and any(i.codigo in ('XML-MAL-FORMADO', 'GML-SIN-ELEMENTOS')
                                                    for i in lectura.incidencias):
        generica, previos = leer_generico(lectura.datos or _leer_bytes(ruta))
        if generica is not None:
            lectura, version = generica, GENERICO
    bloqueantes = [i for i in lectura.incidencias if i.nivel == ERROR and i.codigo in BLOQUEANTES]
    if bloqueantes:
        return False, version, [], bloqueantes
    if version != GENERICO and not version.startswith('CP'):
        return False, version, [], [Incidencia(ERROR, 'CONV-NO-PARCELA', "Solo se convierten GML de parcela catastral "
                                                                         f"(este es {version or 'de formato desconocido'})")]
    if version not in ('CP 3.0', 'CP 4.0', GENERICO):
        return False, version, [], [Incidencia(ERROR, 'CONV-VERSION', f"Esquema de parcela desconocido ({version})")]

    incidencias, cambios, parcelas = [], [], []
    if version == 'CP 3.0':
        cambios.append(CAMBIOS_30_40)
    elif version == GENERICO:
        cambios.append("GML genérico (no INSPIRE; p. ej. «Guardar como» GML de QGIS) → INSPIRE CadastralParcels 4.0: se "
                       "toman la geometría y los campos localId, namespace, label y nationalCadastralReference")
        cambios += previos
    epsg, geometrias, nota = a_src_admitido(lectura)
    if epsg is None:
        return False, version, cambios, [Incidencia(ERROR, 'SRC-NO-ADMITIDO', nota)]
    if nota:
        cambios.append(nota)
    quitados = ajenos(lectura.datos) if version != GENERICO else []
    if quitados:
        cambios.append("Se quitan datos que no son del esquema INSPIRE (la Sede rechaza el fichero si los lleva): "
                       + ", ".join(quitados[:MAX_AJENOS]) + (f"… ({len(quitados)})" if len(quitados) > MAX_AJENOS else ''))
    for e, geometria in zip(lectura.elementos, geometrias):
        namespace = NAMESPACES.get(e.namespace)
        if namespace is None and version == GENERICO and not e.namespace and refcat.es_rc_exacta(e.local_id):
            namespace = gp.SDGC
            cambios.append(f"{e.local_id}: sin namespace y con referencia catastral: se escribe como ES.SDGC.CP")
        elif namespace is None:
            namespace = gp.LOCAL
            cambios.append(f"{e.local_id}: namespace «{e.namespace or 'vacío'}» escrito como ES.LOCAL.CP (parcela nueva)")
        parcelas.append(gp.ParcelaGML(e.local_id, namespace, geometria, e.label, e.referencia))
    original = fecha_original(lectura.texto)
    if original is None:
        original = fecha or datetime.datetime.now().replace(second=0, microsecond=0)
        cambios.append(f"Fecha (beginLifespanVersion): el original no la tiene; se pone {original:%d/%m/%Y %H:%M}")
    ok, escritura = gp.escribir(destino, parcelas, epsg, original, origenes=(ruta,))
    incidencias += escritura
    if not ok:
        return False, version, cambios, incidencias

    #Qué ha cambiado: superficies, decimales y lo que el validador ya no encuentra en el resultado
    nueva = gl.leer(destino)
    for antes, despues in zip(lectura.elementos, nueva.elementos):
        if antes.area_declarada is not None and antes.area_declarada != despues.area_declarada:
            cambios.append(f"{antes.local_id}: superficie (areaValue) {antes.area_declarada} → {despues.area_declarada} m², "
                           "la de su geometría (la Sede exige que coincidan)")
    decimales = max((e.decimales for e in lectura.elementos), default=0)
    if decimales > va.MAX_DECIMALES:
        cambios.append(f"Coordenadas con {decimales} decimales redondeadas al centímetro (2 decimales)")
    informe_nuevo = va.validar(destino, nueva)
    quedan = _codigos(informe_nuevo)
    antes = _codigos(va.validar(ruta, lectura)) if version != GENERICO else {}
    corregidos = {c: m for c, m in antes.items() if c not in quedan}
    corregidos.pop('CP-30', None)    #Ya dicho en el cambio de esquema
    corregidos.pop('SUP-DISTINTA', None)  #Ya dicho por parcela
    corregidos.pop('DECIMALES', None)
    cambios += [f"Corregido: {m}" for m in corregidos.values()]
    pendientes = [i for i in informe_nuevo.incidencias if i.nivel in (ERROR, AVISO)]
    if pendientes:
        incidencias += [Incidencia(i.nivel, i.codigo, f"Queda por revisar: {i.mensaje}", i.elemento) for i in pendientes]
    if not cambios:
        incidencias.append(Incidencia(INFO, 'CONV-SIN-CAMBIOS', "El fichero ya estaba bien: el resultado es equivalente"))
    return True, version, cambios, incidencias
