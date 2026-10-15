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

Sin interfaz. Nunca sobrescribe el fichero original.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import datetime
import os
import re

from . import gml_lector as gl
from . import gml_parcela as gp
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
              'ANILLO-COUNT', 'ANILLO-SENTIDO', 'DECIMALES', 'SUP-DISTINTA', 'SUP-FALTA', 'REFPOINT'}
SUFIJO_30 = '_v4'
SUFIJO_40 = '_reparado'


def destino_propuesto(ruta, version='CP 3.0'):
    """Fichero de salida junto al original («parcela_v4.gml» o «parcela_reparado.gml»), sin pisar uno que ya exista."""
    base, _ = os.path.splitext(ruta)
    sufijo = SUFIJO_30 if version == 'CP 3.0' else SUFIJO_40
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


def _codigos(informe):
    """{código: primer mensaje} de los errores y avisos de un informe de validación."""
    resultado = {}
    for i in informe.incidencias:
        if i.nivel in (ERROR, AVISO) and i.codigo not in resultado:
            resultado[i.codigo] = i.mensaje
    return resultado


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
    bloqueantes = [i for i in lectura.incidencias if i.nivel == ERROR and i.codigo in BLOQUEANTES]
    if bloqueantes:
        return False, version, [], bloqueantes
    if not version.startswith('CP'):
        return False, version, [], [Incidencia(ERROR, 'CONV-NO-PARCELA', "Solo se convierten GML de parcela catastral "
                                                                         f"(este es {version or 'de formato desconocido'})")]
    if version not in ('CP 3.0', 'CP 4.0'):
        return False, version, [], [Incidencia(ERROR, 'CONV-VERSION', f"Esquema de parcela desconocido ({version})")]

    incidencias, cambios, parcelas = [], [], []
    if version == 'CP 3.0':
        cambios.append(CAMBIOS_30_40)
    for e in lectura.elementos:
        namespace = NAMESPACES.get(e.namespace)
        if namespace is None:
            namespace = gp.LOCAL
            cambios.append(f"{e.local_id}: namespace «{e.namespace or 'vacío'}» escrito como ES.LOCAL.CP (parcela nueva)")
        parcelas.append(gp.ParcelaGML(e.local_id, namespace, e.geometria, e.label, e.referencia))
    original = fecha_original(lectura.texto)
    if original is None:
        original = fecha or datetime.datetime.now().replace(second=0, microsecond=0)
        cambios.append(f"Fecha (beginLifespanVersion): el original no la tiene; se pone {original:%d/%m/%Y %H:%M}")
    ok, escritura = gp.escribir(destino, parcelas, lectura.epsg, original, origenes=(ruta,))
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
    corregidos = {c: m for c, m in _codigos(va.validar(ruta, lectura)).items() if c not in quedan}
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
