"""
Escritor del GML de parcela catastral (INSPIRE CadastralParcels 4.0) para la Sede Electrónica del Catastro.

Estructura según los documentos de la DGC «Formato GML de parcela catastral» y «Fichero GML coordinación
Catastro-Registro» (ver docs/INVESTIGACION.md, apartado 1). Escrito desde cero a partir de esa documentación.

  - Raíz FeatureCollection (WFS 2.0) con un <member> por parcela; varias parcelas por fichero.
  - Un solo recinto por parcela (MultiSurface con un único surfaceMember).
  - Identificador: namespace ES.SDGC.CP con la referencia catastral de 14 caracteres (parcela que existe en el
    Catastro y se conserva) o ES.LOCAL.CP con un identificador propio (parcela nueva).
  - Coordenadas con 2 decimales, exterior horario, huecos antihorarios, superficie al m², punto interior.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import datetime
import re
from dataclasses import dataclass
from xml.sax.saxutils import escape, quoteattr

from . import geometria as geo
from . import refcat
from .incidencias import ERROR, Incidencia, hay_errores
from .info import NOMBRE, version

NS_WFS = 'http://www.opengis.net/wfs/2.0'
NS_GML = 'http://www.opengis.net/gml/3.2'
NS_CP = 'http://inspire.ec.europa.eu/schemas/cp/4.0'
NS_BASE = 'http://inspire.ec.europa.eu/schemas/base/3.3'
NS_XSI = 'http://www.w3.org/2001/XMLSchema-instance'
NS_GMD = 'http://www.isotc211.org/2005/gmd'
SCHEMA_LOCATION = (f'{NS_WFS} http://schemas.opengis.net/wfs/2.0/wfs.xsd '
                   f'{NS_CP} http://inspire.ec.europa.eu/schemas/cp/4.0/CadastralParcels.xsd')
NIL_UNPOPULATED = 'http://inspire.ec.europa.eu/codelist/VoidReasonValue/Unpopulated'

SDGC = 'SDGC'
LOCAL = 'LOCAL'
LOCAL_ID_VALIDO = re.compile(r'^[A-Za-z0-9_.\-]+$')  #Va dentro de gml:id: sin espacios ni símbolos


@dataclass
class ParcelaGML:
    """Una parcela para el GML. La geometría debe estar ya en el SRC del fichero."""
    local_id: str
    namespace: str              #SDGC o LOCAL
    geometria: object           #QgsGeometry (polígono)
    label: str = ''             #Número de parcela en el plano; si se deja vacío se deduce
    referencia: str = ''        #nationalCadastralReference; si se deja vacía, la RC (SDGC) o el localId (LOCAL)


def srs_name(epsg):
    return f'http://www.opengis.net/def/crs/EPSG/0/{epsg}'


def label_por_defecto(local_id, namespace):
    """
    Número de parcela que se ve en el plano catastral:
      urbana  (7 dígitos de finca: 5 de manzana + 2 de parcela) → los 2 de parcela, p. ej. '01'
      rústica (5 últimos caracteres) → el número de parcela sin ceros a la izquierda, p. ej. '123'
      LOCAL → el propio identificador.
    """
    if namespace == SDGC and refcat.es_rc_parcela(local_id):
        rc = refcat.limpiar(local_id)
        if refcat.tipo_parcela(rc) == 'urbana':
            return rc[5:7]
        return str(int(rc[9:14]))
    return local_id


def _poslist(anillo):
    return ' '.join(f"{geo.formatear(x)} {geo.formatear(y)}" for x, y in anillo)


def _anillo_xml(etiqueta, anillo, sangria):
    s = ' ' * sangria
    return (f"{s}<gml:{etiqueta}>\n"
            f"{s}  <gml:LinearRing>\n"
            f"{s}    <gml:posList srsDimension=\"2\" count=\"{len(anillo)}\">{_poslist(anillo)}</gml:posList>\n"
            f"{s}  </gml:LinearRing>\n"
            f"{s}</gml:{etiqueta}>\n")


def _parcela_xml(parcela, recinto, epsg, fecha):
    ns = f"ES.{parcela.namespace}.CP"
    gid = f"{ns}.{parcela.local_id}"
    srs = quoteattr(srs_name(epsg))
    px, py = geo.punto_interior(recinto)
    anillos = _anillo_xml('exterior', recinto.exterior, 18)
    anillos += ''.join(_anillo_xml('interior', a, 18) for a in recinto.interiores)
    label = parcela.label or label_por_defecto(parcela.local_id, parcela.namespace)
    referencia = parcela.referencia or (refcat.limpiar(parcela.local_id) if parcela.namespace == SDGC else parcela.local_id)
    return (
        "  <member>\n"
        f"    <cp:CadastralParcel gml:id={quoteattr(gid)}>\n"
        f"      <cp:areaValue uom=\"m2\">{recinto.area_m2()}</cp:areaValue>\n"
        f"      <cp:beginLifespanVersion>{fecha}</cp:beginLifespanVersion>\n"
        f"      <cp:endLifespanVersion xsi:nil=\"true\" nilReason=\"{NIL_UNPOPULATED}\"></cp:endLifespanVersion>\n"
        "      <cp:geometry>\n"
        f"        <gml:MultiSurface gml:id={quoteattr('MultiSurface_' + gid)} srsName={srs}>\n"
        "          <gml:surfaceMember>\n"
        f"            <gml:Surface gml:id={quoteattr('Surface_' + gid + '.1')} srsName={srs}>\n"
        "              <gml:patches>\n"
        "                <gml:PolygonPatch>\n"
        f"{anillos}"
        "                </gml:PolygonPatch>\n"
        "              </gml:patches>\n"
        "            </gml:Surface>\n"
        "          </gml:surfaceMember>\n"
        "        </gml:MultiSurface>\n"
        "      </cp:geometry>\n"
        "      <cp:inspireId>\n"
        f"        <Identifier xmlns=\"{NS_BASE}\">\n"
        f"          <localId>{escape(parcela.local_id)}</localId>\n"
        f"          <namespace>{ns}</namespace>\n"
        "        </Identifier>\n"
        "      </cp:inspireId>\n"
        f"      <cp:label>{escape(str(label))}</cp:label>\n"
        f"      <cp:nationalCadastralReference>{escape(referencia)}</cp:nationalCadastralReference>\n"
        "      <cp:referencePoint>\n"
        f"        <gml:Point gml:id={quoteattr('ReferencePoint_' + gid)} srsName={srs}>\n"
        f"          <gml:pos>{geo.formatear(px)} {geo.formatear(py)}</gml:pos>\n"
        "        </gml:Point>\n"
        "      </cp:referencePoint>\n"
        "    </cp:CadastralParcel>\n"
        "  </member>\n"
    )


def comprobar_parcelas(parcelas, epsg):
    """Comprobaciones previas a escribir: SRC, identificadores y geometrías. Devuelve (recintos, incidencias)."""
    incidencias = []
    if not parcelas:
        return [], [Incidencia(ERROR, 'GML-SIN-PARCELAS', "No hay parcelas que escribir")]
    if epsg not in geo.SRC_ADMITIDOS:
        incidencias.append(Incidencia(ERROR, 'SRC-NO-ADMITIDO',
                                      f"EPSG:{epsg} no lo admite la Sede: use 25829, 25830, 25831 o 32628"))
    vistos = set()
    recintos = []
    for i, parcela in enumerate(parcelas, start=1):
        nombre = parcela.local_id or f"fila {i}"
        if not parcela.local_id:
            incidencias.append(Incidencia(ERROR, 'ID-VACIO', "La parcela no tiene identificador (localId)", nombre))
        elif not LOCAL_ID_VALIDO.match(parcela.local_id):
            incidencias.append(Incidencia(ERROR, 'ID-CARACTERES',
                                          "El identificador solo puede tener letras sin tilde, números, '_', '-' y '.'",
                                          nombre))
        elif parcela.local_id in vistos:
            incidencias.append(Incidencia(ERROR, 'ID-REPETIDO', "Identificador repetido en el fichero", nombre))
        vistos.add(parcela.local_id)
        if parcela.namespace not in (SDGC, LOCAL):
            incidencias.append(Incidencia(ERROR, 'NS-DESCONOCIDO', "El namespace debe ser SDGC o LOCAL", nombre))
        elif parcela.namespace == SDGC and not refcat.es_rc_parcela(parcela.local_id):
            incidencias.append(Incidencia(ERROR, 'NS-SDGC-SIN-RC',
                                          "Con namespace SDGC el identificador debe ser la referencia catastral de 14 caracteres "
                                          "(si es una parcela nueva, use LOCAL)", nombre))
        elif parcela.namespace == SDGC:
            resultado = refcat.comprobar(parcela.local_id)
            if resultado.foral:
                incidencias.append(Incidencia(ERROR, 'RC-FORAL', resultado.mensaje, nombre))
        partes, inc = geo.preparar(parcela.geometria, nombre)
        incidencias += inc
        recintos.append(partes[0] if len(partes) == 1 else None)
    return recintos, incidencias


def construir(parcelas, epsg, fecha=None, ahora=None):
    """
    Texto del GML de parcela catastral para las parcelas dadas (geometrías ya en EPSG epsg).
    fecha: beginLifespanVersion (datetime o date); por defecto, hoy a las 00:00:00.
    Devuelve (texto, incidencias); texto es None si hay algún error.
    """
    recintos, incidencias = comprobar_parcelas(parcelas, epsg)
    if hay_errores(incidencias):
        return None, incidencias
    ahora = ahora or datetime.datetime.now().replace(microsecond=0)
    if fecha is None:
        fecha = ahora.date()
    if not isinstance(fecha, datetime.datetime):
        fecha = datetime.datetime.combine(fecha, datetime.time())
    texto_fecha = fecha.strftime('%Y-%m-%dT%H:%M:%S')
    cuerpo = ''.join(_parcela_xml(p, r, epsg, texto_fecha) for p, r in zip(parcelas, recintos))
    texto = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<!-- Generado con {NOMBRE} {version()} (herramienta no oficial). '
        'Valide el fichero en la Sede Electrónica del Catastro. -->\n'
        f'<FeatureCollection xmlns:xsi="{NS_XSI}" xmlns:gml="{NS_GML}" xmlns:cp="{NS_CP}" xmlns:gmd="{NS_GMD}" '
        f'xsi:schemaLocation="{SCHEMA_LOCATION}" xmlns="{NS_WFS}" '
        f'timeStamp="{ahora.strftime("%Y-%m-%dT%H:%M:%S")}" numberMatched="{len(parcelas)}" numberReturned="{len(parcelas)}">\n'
        f'{cuerpo}'
        '</FeatureCollection>\n'
    )
    return texto, incidencias


def escribir(ruta, parcelas, epsg, fecha=None):
    """Escribe el GML en ruta (UTF-8). Devuelve (True/False, incidencias)."""
    texto, incidencias = construir(parcelas, epsg, fecha)
    if texto is None:
        return False, incidencias
    with open(ruta, 'w', encoding='utf-8', newline='\n') as f:
        f.write(texto)
    return True, incidencias
