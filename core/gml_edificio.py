"""
Escritor del GML de edificio (mejora 18) según el «Formato GML de edificio» de la DGC (modelo simplificado de edificios
y piscinas, INSPIRE BuildingExtended2D 2.0), para el Informe Catastral de Ubicación de las Construcciones (ICUC).

Reglas del documento de la DGC (docs/INVESTIGACION.md §7.2):
  - gml:FeatureCollection con gml:featureMember; codificación ISO-8859-1; namespace ES.LOCAL.BU;
  - Building: gml:id = namespace + localId; localId = referencia de la parcela (o el identificador de la parcela en la
    escritura) y, si hay varios edificios, sufijo «_Edificio_N»; una gml:Surface con un PolygonPatch por recinto (el
    edificio sí admite varios recintos: huella de todas sus construcciones sobre rasante);
  - OtherConstruction (piscinas): un gml:Polygon, constructionNature=openAirPool, sufijo «_Piscina_N», sin estado;
  - exterior horario, huecos antihorarios, sin autointersecciones, 2 decimales, anillos cerrados;
  - SRC 25829, 25830, 25831 o 32628 (srsName urn:ogc:def:crs:EPSG::xxxxx, como el ejemplo oficial);
  - conditionOfConstruction: declined, demolished, functional, projected, ruin o underConstruction;
  - numberOfFloorsAboveGround: plantas sobre rasante (la máxima si varía); horizontalGeometryEstimatedAccuracy en m.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import datetime
import re
from dataclasses import dataclass
from xml.sax.saxutils import escape, quoteattr

from . import geometria as geo
from . import refcat
from .incidencias import AVISO, ERROR, Incidencia, hay_errores

EDIFICIO = 'edificio'
PISCINA = 'piscina'
NAMESPACE = 'ES.LOCAL.BU'
ESTADOS = ('functional', 'underConstruction', 'projected', 'declined', 'ruin', 'demolished')
NOMBRES_ESTADO = {'functional': 'Terminado (functional)', 'underConstruction': 'En construcción (underConstruction)',
                  'projected': 'Proyectado (projected)', 'declined': 'Deteriorado (declined)', 'ruin': 'En ruina (ruin)',
                  'demolished': 'Demolido (demolished)'}
ID_VALIDO = re.compile(r'^[A-Za-z0-9_.\-]+$')
NS = {
    'base': 'urn:x-inspire:specification:gmlas:BaseTypes:3.2',
    'bu-core2d': 'http://inspire.jrc.ec.europa.eu/schemas/bu-core2d/2.0',
    'bu-ext2d': 'http://inspire.jrc.ec.europa.eu/schemas/bu-ext2d/2.0',
    'gml': 'http://www.opengis.net/gml/3.2',
    'xlink': 'http://www.w3.org/1999/xlink',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
}
ESQUEMA = ('http://inspire.jrc.ec.europa.eu/schemas/bu-ext2d/2.0 '
           'http://inspire.ec.europa.eu/draft-schemas/bu-ext2d/2.0/BuildingExtended2D.xsd')


@dataclass
class Construccion:
    """Un edificio o una piscina para el GML. La geometría debe estar ya en el SRC del fichero."""
    local_id: str
    geometria: object              #QgsGeometry (polígono o multipolígono)
    tipo: str = EDIFICIO           #EDIFICIO o PISCINA
    plantas: object = None         #Plantas sobre rasante (edificios)
    estado: str = 'functional'     #conditionOfConstruction (edificios)
    precision: float = 0.1         #horizontalGeometryEstimatedAccuracy en m


def identificadores(referencia, tipos):
    """
    Identificadores propuestos según el formato de la DGC: con un solo edificio, la referencia de la parcela; con
    varios, «_Edificio_1», «_Edificio_2»…; las piscinas, «_Piscina_1»…
    Sin referencia, «Edificio_1», «Piscina_1»… (hay que poner después la de la parcela).
    """
    n_edificios = sum(1 for t in tipos if t == EDIFICIO)
    prefijo = f"{referencia}_" if referencia else ''
    ids, n_ed, n_pi = [], 0, 0
    for t in tipos:
        if t == PISCINA:
            n_pi += 1
            ids.append(f"{prefijo}Piscina_{n_pi}")
        else:
            n_ed += 1
            ids.append(referencia if referencia and n_edificios == 1 else f"{prefijo}Edificio_{n_ed}")
    return ids


def _anillo(etiqueta, anillo, s):
    puntos = ' '.join(f"{geo.formatear(x)} {geo.formatear(y)}" for x, y in anillo)
    return (f"{s}<gml:{etiqueta}>\n{s}  <gml:LinearRing>\n"
            f"{s}    <gml:posList srsDimension=\"2\" count=\"{len(anillo)}\">{puntos}</gml:posList>\n"
            f"{s}  </gml:LinearRing>\n{s}</gml:{etiqueta}>\n")


def _anillos(recinto, s):
    return _anillo('exterior', recinto.exterior, s) + ''.join(_anillo('interior', a, s) for a in recinto.interiores)


def _edificio_xml(c, recintos, epsg, fecha):
    gid = f"{NAMESPACE}.{c.local_id}"
    parches = ''.join("                <gml:PolygonPatch>\n" + _anillos(r, ' ' * 18) + "                </gml:PolygonPatch>\n"
                      for r in recintos)
    plantas = (f"      <bu-ext2d:numberOfFloorsAboveGround>{int(c.plantas)}</bu-ext2d:numberOfFloorsAboveGround>\n"
               if c.plantas not in (None, '') else '')
    return (
        "  <gml:featureMember>\n"
        f"    <bu-ext2d:Building gml:id={quoteattr(gid)}>\n"
        f"      <bu-core2d:beginLifespanVersion>{fecha}</bu-core2d:beginLifespanVersion>\n"
        f"      <bu-core2d:conditionOfConstruction>{c.estado}</bu-core2d:conditionOfConstruction>\n"
        "      <bu-core2d:inspireId>\n"
        "        <base:Identifier>\n"
        f"          <base:localId>{escape(c.local_id)}</base:localId>\n"
        f"          <base:namespace>{NAMESPACE}</base:namespace>\n"
        "        </base:Identifier>\n"
        "      </bu-core2d:inspireId>\n"
        "      <bu-ext2d:geometry>\n"
        "        <bu-core2d:BuildingGeometry>\n"
        "          <bu-core2d:geometry>\n"
        f"            <gml:Surface gml:id={quoteattr('Surface_' + gid)} srsName=\"urn:ogc:def:crs:EPSG::{epsg}\">\n"
        "              <gml:patches>\n"
        f"{parches}"
        "              </gml:patches>\n"
        "            </gml:Surface>\n"
        "          </bu-core2d:geometry>\n"
        f"          <bu-core2d:horizontalGeometryEstimatedAccuracy uom=\"m\">{c.precision:g}</bu-core2d:horizontalGeometryEstimatedAccuracy>\n"
        "          <bu-core2d:horizontalGeometryReference>footPrint</bu-core2d:horizontalGeometryReference>\n"
        "          <bu-core2d:referenceGeometry>true</bu-core2d:referenceGeometry>\n"
        "        </bu-core2d:BuildingGeometry>\n"
        "      </bu-ext2d:geometry>\n"
        f"{plantas}"
        "    </bu-ext2d:Building>\n"
        "  </gml:featureMember>\n"
    )


def _piscina_xml(c, recinto, epsg, fecha):
    gid = f"{NAMESPACE}.{c.local_id}"
    return (
        "  <gml:featureMember>\n"
        f"    <bu-ext2d:OtherConstruction gml:id={quoteattr(gid)}>\n"
        f"      <bu-core2d:beginLifespanVersion>{fecha}</bu-core2d:beginLifespanVersion>\n"
        "      <bu-core2d:conditionOfConstruction xsi:nil=\"true\" nilReason=\"other:unpopulated\"></bu-core2d:conditionOfConstruction>\n"
        "      <bu-core2d:inspireId>\n"
        "        <base:Identifier>\n"
        f"          <base:localId>{escape(c.local_id)}</base:localId>\n"
        f"          <base:namespace>{NAMESPACE}</base:namespace>\n"
        "        </base:Identifier>\n"
        "      </bu-core2d:inspireId>\n"
        "      <bu-ext2d:constructionNature>openAirPool</bu-ext2d:constructionNature>\n"
        "      <bu-ext2d:geometry>\n"
        f"        <gml:Polygon gml:id={quoteattr('Polygon_' + gid)} srsName=\"urn:ogc:def:crs:EPSG::{epsg}\">\n"
        f"{_anillos(recinto, ' ' * 10)}"
        "        </gml:Polygon>\n"
        "      </bu-ext2d:geometry>\n"
        "    </bu-ext2d:OtherConstruction>\n"
        "  </gml:featureMember>\n"
    )


def comprobar(construcciones, epsg):
    """Comprobaciones previas. Devuelve (lista de recintos por construcción, incidencias)."""
    incidencias, todos = [], []
    if epsg not in geo.SRC_ADMITIDOS:
        incidencias.append(Incidencia(ERROR, 'SRC-NO-ADMITIDO', f"EPSG:{epsg} no es un SRC admitido (25829, 25830, 25831 "
                                                                "o 32628)"))
    if not construcciones:
        incidencias.append(Incidencia(ERROR, 'BU-VACIO', "No hay construcciones"))
    vistos = set()
    for c in construcciones:
        nombre = c.local_id or '(sin identificador)'
        if not c.local_id:
            incidencias.append(Incidencia(ERROR, 'ID-VACIO', "Falta el identificador", nombre))
        elif not ID_VALIDO.match(c.local_id):
            incidencias.append(Incidencia(ERROR, 'ID-CARACTERES', "El identificador solo puede tener letras sin tilde, "
                                                                  "números, '_', '-' y '.'", nombre))
        elif c.local_id in vistos:
            incidencias.append(Incidencia(ERROR, 'ID-REPETIDO', "Identificador repetido", nombre))
        vistos.add(c.local_id)
        if c.tipo == EDIFICIO and c.estado not in ESTADOS:
            incidencias.append(Incidencia(ERROR, 'BU-ESTADO', f"Estado «{c.estado}» no válido", nombre))
        if c.tipo == EDIFICIO and c.plantas not in (None, ''):
            try:
                if int(c.plantas) < 1:
                    raise ValueError
            except (TypeError, ValueError):
                incidencias.append(Incidencia(ERROR, 'BU-PLANTAS', f"Plantas sobre rasante no válidas: {c.plantas}", nombre))
        if c.tipo == EDIFICIO and c.plantas in (None, ''):
            incidencias.append(Incidencia(AVISO, 'BU-SIN-PLANTAS', "No se indica el número de plantas sobre rasante",
                                          nombre))
        recintos, inc = geo.preparar(c.geometria, nombre)
        #El edificio admite varios recintos (huella de construcciones separadas); la piscina, uno
        incidencias += [i for i in inc if not (i.codigo == 'GEO-MULTIPARTE' and c.tipo == EDIFICIO)]
        if c.tipo == PISCINA and len(recintos) > 1:
            incidencias = [i for i in incidencias if not (i.codigo == 'GEO-MULTIPARTE' and i.elemento == nombre)]
            incidencias.append(Incidencia(ERROR, 'BU-PISCINA-PARTES', f"La piscina tiene {len(recintos)} partes: cada piscina "
                                                                      "va por separado (_Piscina_1, _Piscina_2…)", nombre))
        rc = c.local_id.split('_')[0]
        if refcat.es_rc_parcela(rc) and refcat.comprobar(rc).foral:
            incidencias.append(Incidencia(ERROR, 'RC-FORAL', refcat.comprobar(rc).mensaje, nombre))
        todos.append(recintos)
    return todos, incidencias


def construir(construcciones, epsg, fecha=None):
    """Texto del GML de edificio (o None si hay errores) y sus incidencias."""
    recintos, incidencias = comprobar(construcciones, epsg)
    if hay_errores(incidencias):
        return None, incidencias
    fecha = fecha or datetime.datetime.now().replace(second=0, microsecond=0)
    if not isinstance(fecha, datetime.datetime):
        fecha = datetime.datetime.combine(fecha, datetime.time())
    texto_fecha = fecha.strftime('%Y-%m-%dT%H:%M:%S')
    cuerpo = ''.join(_edificio_xml(c, r, epsg, texto_fecha) if c.tipo == EDIFICIO else _piscina_xml(c, r[0], epsg, texto_fecha)
                     for c, r in zip(construcciones, recintos))
    espacios = ' '.join(f'xmlns:{p}="{u}"' for p, u in NS.items())
    texto = ('<?xml version="1.0" encoding="ISO-8859-1"?>\n'
             '<!-- GML de edificio creado con Catastral GML Tools (herramienta no oficial): valídelo en la Sede '
             'Electrónica del Catastro -->\n'
             f'<gml:FeatureCollection gml:id="{NAMESPACE}" {espacios} xsi:schemaLocation="{ESQUEMA}">\n'
             f'{cuerpo}'
             '</gml:FeatureCollection>\n')
    return texto, incidencias


def escribir(ruta, construcciones, epsg, fecha=None):
    """Escribe el GML de edificio en ISO-8859-1. Devuelve (escrito, incidencias)."""
    texto, incidencias = construir(construcciones, epsg, fecha)
    if texto is None:
        return False, incidencias
    with open(ruta, 'w', encoding='iso-8859-1', errors='xmlcharrefreplace', newline='\n') as f:
        f.write(texto)
    return True, incidencias
