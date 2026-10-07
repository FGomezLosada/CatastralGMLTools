"""
Lector de ficheros GML del Catastro: parcela catastral (INSPIRE CP 4.0 y el antiguo 3.0) y edificio
(BuildingExtended2D: Building y OtherConstruction). Convierte cada parcela o construcción en un ElementoGML y,
si se quiere, en una capa de memoria de QGIS para revisarlo sobre el mapa.

No depende de GDAL: lee el XML directamente (así no se crean ficheros .gfs junto al GML y se ven los mismos datos
que leerá la Sede: identificadores, namespace, superficie declarada…).

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
)

from . import geometria as geo
from .incidencias import AVISO, ERROR, INFO, Incidencia

PARCELA = 'parcela'
EDIFICIO = 'edificio'
OTRA = 'otra construcción'
DOMINIO_PUBLICO = 'dominio público'  #Parcela de rústica 9001-9999 (caminos, cauces…), en las descargas

#Espacios de nombres que identifican cada formato
CP_40 = 'http://inspire.ec.europa.eu/schemas/cp/4.0'
CP_30 = 'urn:x-inspire:specification:gmlas:CadastralParcels:3.0'
BU_EXT2D = 'http://inspire.jrc.ec.europa.eu/schemas/bu-ext2d/2.0'


@dataclass
class ElementoGML:
    """Una parcela o construcción leída del GML."""
    tipo: str                   #PARCELA, EDIFICIO u OTRA
    local_id: str
    namespace: str              #Tal cual viene, p. ej. ES.SDGC.CP
    geometria: QgsGeometry      #En el SRC del fichero
    label: str = ''
    referencia: str = ''        #nationalCadastralReference
    area_declarada: object = None  #areaValue (parcelas), entero o None
    gml_id: str = ''
    plantas: object = None      #numberOfFloorsAboveGround (edificios)
    naturaleza: str = ''        #constructionNature (otras construcciones), p. ej. openAirPool
    recintos: int = 0           #Nº de recintos (surfaceMember / Surface) de la parcela
    anillos: list = field(default_factory=list)  #Anillos leídos tal cual (lista de listas de (x, y)), sin corregir
    counts: list = field(default_factory=list)   #Atributo count de cada posList (None si no lo trae)
    roles: list = field(default_factory=list)    #'exterior' o 'interior' de cada anillo (mismo orden que anillos)
    decimales: int = 0          #Máximo de decimales de las coordenadas tal como están escritas
    punto_referencia: object = None  #(x, y) de cp:referencePoint, o None
    descripcion: str = ''       #En las descargas: paraje y uso según el Catastro (p. ej. «Camino · vía de comunicación…»)


@dataclass
class ResultadoLectura:
    version: str = ''           #'CP 4.0', 'CP 3.0', 'BU 2.0' o ''
    epsg: object = None
    elementos: list = field(default_factory=list)
    incidencias: list = field(default_factory=list)
    xlink_declarado: bool = False
    texto: str = ''             #Contenido del fichero (para el validador)
    datos: bytes = b''          #El fichero tal cual (para validarlo contra el esquema XSD)
    raiz: str = ''              #Etiqueta de la raíz, p. ej. '{http://www.opengis.net/wfs/2.0}FeatureCollection'


def nombre_local(etiqueta):
    """'{espacio}nombre' → 'nombre'."""
    return etiqueta.rsplit('}', 1)[-1]


def espacio(etiqueta):
    return etiqueta[1:].split('}', 1)[0] if etiqueta.startswith('{') else ''


def hijos(elemento, nombre):
    return [h for h in elemento if nombre_local(h.tag) == nombre]


def hijo(elemento, nombre):
    encontrados = hijos(elemento, nombre)
    return encontrados[0] if encontrados else None


def descendientes(elemento, nombre):
    return [d for d in elemento.iter() if nombre_local(d.tag) == nombre]


def texto_de(elemento, nombre):
    h = hijo(elemento, nombre) if elemento is not None else None
    return (h.text or '').strip() if h is not None and h.text else ''


def epsg_de_srsname(srs):
    """EPSG de un srsName en cualquiera de sus formas (URL de OGC, URN, 'EPSG:25830')."""
    if not srs:
        return None
    if 'EPSG' not in srs.upper():
        return None
    m = re.search(r'(\d{4,5})\s*$', srs.strip())  #El código va siempre al final (…/EPSG/0/25830, …EPSG::25830, …EPSG:6.6:25830)
    return int(m.group(1)) if m else None


def decimales_de(textos):
    """Máximo número de decimales en una serie de números escritos como texto."""
    return max((len(v.split('.', 1)[1]) for v in textos if '.' in v), default=0)


def coordenadas(elemento_anillo):
    """
    Vértices de un anillo (LinearRing) como lista de (x, y). Admite gml:posList (con srsDimension 2 o 3),
    una serie de gml:pos y el antiguo gml:coordinates ('x,y x,y').
    Devuelve (vertices, count_declarado, decimales).
    """
    pos_list = descendientes(elemento_anillo, 'posList')
    if pos_list:
        nodo = pos_list[0]
        dimension = int(nodo.get('srsDimension') or 2)
        textos = (nodo.text or '').split()
        valores = [float(v) for v in textos]
        vertices = [tuple(valores[i:i + 2]) for i in range(0, len(valores) - dimension + 1, dimension)]
        count = nodo.get('count')
        return vertices, int(count) if count and count.isdigit() else None, decimales_de(textos)
    posiciones = descendientes(elemento_anillo, 'pos')
    if posiciones:
        textos = [p.text or '' for p in posiciones]
        return ([tuple(float(v) for v in tx.split()[:2]) for tx in textos], None,
                decimales_de(' '.join(textos).split()))
    coords = descendientes(elemento_anillo, 'coordinates')
    if coords:
        vertices, textos = [], []
        for par in (coords[0].text or '').split():
            partes = par.split(',')
            if len(partes) >= 2:
                vertices.append((float(partes[0]), float(partes[1])))
                textos += partes[:2]
        return vertices, None, decimales_de(textos)
    return [], None, 0


def poligonos(elemento):
    """
    Polígonos (lista de anillos: exterior y huecos) bajo un elemento de geometría: PolygonPatch (Surface) o Polygon.
    Devuelve (poligonos, counts, roles, decimales).
    """
    resultado, counts, roles, decimales = [], [], [], 0
    contenedores = descendientes(elemento, 'PolygonPatch') + descendientes(elemento, 'Polygon')
    for contenedor in contenedores:
        anillos = []
        for parte in ('exterior', 'interior', 'outerBoundaryIs', 'innerBoundaryIs'):
            for borde in hijos(contenedor, parte):
                vertices, count, dec = coordenadas(borde)
                if vertices:
                    anillos.append(vertices)
                    counts.append(count)
                    roles.append('exterior' if parte in ('exterior', 'outerBoundaryIs') else 'interior')
                    decimales = max(decimales, dec)
        if anillos:
            resultado.append(anillos)
    return resultado, counts, roles, decimales


def geometria_de(lista_poligonos):
    """QgsGeometry (polígono o multipolígono) a partir de la lista de polígonos, sin corregir nada."""
    partes = [[[QgsPointXY(x, y) for x, y in anillo] for anillo in poligono] for poligono in lista_poligonos]
    if not partes:
        return QgsGeometry()
    return QgsGeometry.fromPolygonXY(partes[0]) if len(partes) == 1 else QgsGeometry.fromMultiPolygonXY(partes)


def _leer_parcela(cp_el):
    ident = descendientes(cp_el, 'Identifier')
    local_id = texto_de(ident[0], 'localId') if ident else ''
    namespace = texto_de(ident[0], 'namespace') if ident else ''
    geom_el = hijo(cp_el, 'geometry')
    lista, counts, roles, decimales = poligonos(geom_el) if geom_el is not None else ([], [], [], 0)
    recintos = len(descendientes(geom_el, 'surfaceMember')) if geom_el is not None else 0
    area_txt = texto_de(cp_el, 'areaValue')
    try:
        area = int(round(float(area_txt))) if area_txt else None
    except ValueError:
        area = None
    return ElementoGML(PARCELA, local_id, namespace, geometria_de(lista), texto_de(cp_el, 'label'),
                       texto_de(cp_el, 'nationalCadastralReference'), area,
                       cp_el.get(f'{{{geo_ns_gml()}}}id', ''), recintos=max(recintos, len(lista)),
                       anillos=[a for p in lista for a in p], counts=counts, roles=roles, decimales=decimales,
                       punto_referencia=_punto_referencia(cp_el))


def _punto_referencia(cp_el):
    ref = hijo(cp_el, 'referencePoint')
    pos = descendientes(ref, 'pos') if ref is not None else []
    try:
        valores = [float(v) for v in (pos[0].text or '').split()[:2]] if pos else []
    except ValueError:
        return None
    return tuple(valores) if len(valores) == 2 else None


def _leer_construccion(el):
    ident = descendientes(el, 'Identifier')
    local_id = texto_de(ident[0], 'localId') if ident else ''
    namespace = texto_de(ident[0], 'namespace') if ident else ''
    lista, counts, roles, decimales = poligonos(el)
    tipo = EDIFICIO if nombre_local(el.tag) == 'Building' else OTRA
    plantas_txt = texto_de(el, 'numberOfFloorsAboveGround')
    plantas = int(plantas_txt) if plantas_txt.isdigit() else None
    return ElementoGML(tipo, local_id, namespace, geometria_de(lista), plantas=plantas,
                       naturaleza=texto_de(el, 'constructionNature'), gml_id=el.get(f'{{{geo_ns_gml()}}}id', ''),
                       recintos=len(lista), anillos=[a for p in lista for a in p], counts=counts, roles=roles,
                       decimales=decimales)


def geo_ns_gml():
    return 'http://www.opengis.net/gml/3.2'


def leer(ruta):
    """Lee un GML de parcela o de edificio. Nunca lanza excepciones: los problemas van en resultado.incidencias."""
    nombre = os.path.basename(ruta)
    try:
        with open(ruta, 'rb') as f:
            datos = f.read()
    except OSError as e:
        resultado = ResultadoLectura()
        resultado.incidencias.append(Incidencia(ERROR, 'FICHERO', f"No se puede leer {nombre}: {e}"))
        return resultado
    return leer_datos(datos)


def leer_datos(datos):
    """Como leer(), pero a partir del contenido (p. ej. la respuesta de un servicio WFS del Catastro)."""
    resultado = ResultadoLectura()
    try:
        raiz = ET.fromstring(datos)
    except ET.ParseError as e:
        resultado.incidencias.append(Incidencia(ERROR, 'XML-MAL-FORMADO', f"El fichero no es un XML bien formado: {e}"))
        return resultado
    resultado.datos = datos
    resultado.raiz = raiz.tag
    resultado.texto = datos.decode('utf-8', 'replace') if b'utf-8' in datos[:100].lower() else datos.decode('latin-1')
    #xmlns:xlink en la etiqueta raíz: la Sede lo exige en el GML de parcela (docs/DESARROLLO.md, E-11)
    inicio_raiz = re.search(r'<(?:\w+:)?FeatureCollection\b[^>]*>', resultado.texto[:6000])
    resultado.xlink_declarado = bool(inicio_raiz) and 'xmlns:xlink=' in inicio_raiz.group(0)

    parcelas = [e for e in raiz.iter() if nombre_local(e.tag) == 'CadastralParcel']
    construcciones = [e for e in raiz.iter() if nombre_local(e.tag) in ('Building', 'OtherConstruction')
                      and (espacio(e.tag) == BU_EXT2D or 'bu-ext2d' in espacio(e.tag))]
    if parcelas:
        ns = espacio(parcelas[0].tag)
        resultado.version = 'CP 4.0' if ns == CP_40 else 'CP 3.0' if ns == CP_30 else f'CP ({ns})'
        resultado.elementos = [_leer_parcela(p) for p in parcelas]
    elif construcciones:
        resultado.version = 'BU 2.0'
        resultado.elementos = [_leer_construccion(c) for c in construcciones]
    else:
        resultado.incidencias.append(Incidencia(ERROR, 'GML-SIN-ELEMENTOS',
                                                "No se han encontrado parcelas catastrales ni construcciones en el fichero"))
        return resultado

    srs = {epsg_de_srsname(e.get('srsName')) for e in raiz.iter() if e.get('srsName')}
    srs.discard(None)
    if len(srs) == 1:
        resultado.epsg = srs.pop()
    elif len(srs) > 1:
        resultado.epsg = sorted(srs)[0]
        resultado.incidencias.append(Incidencia(ERROR, 'SRC-MEZCLADOS',
                                                f"El fichero mezcla sistemas de referencia: {', '.join(map(str, sorted(srs)))}"))
    else:
        resultado.incidencias.append(Incidencia(ERROR, 'SRC-FALTA', "El fichero no indica el sistema de referencia (srsName)"))
    vacios = [e for e in resultado.elementos if e.geometria.isNull() or e.geometria.isEmpty()]
    for e in vacios:
        resultado.incidencias.append(Incidencia(ERROR, 'GEO-VACIA', "Elemento sin geometría", e.local_id))
    n = len(resultado.elementos)
    resultado.incidencias.append(Incidencia(INFO, 'GML-LEIDO', f"{resultado.version} · {n} elemento{'s' if n != 1 else ''}"
                                            + (f" · EPSG:{resultado.epsg}" if resultado.epsg else '')))
    if resultado.version == 'CP 3.0':
        resultado.incidencias.append(Incidencia(AVISO, 'CP-30',
                                                "Esquema 3.0: la Sede ya solo admite el 4.0 (se podrá convertir en Utilidades)"))
    return resultado


# ------------------------------------------------------------------ Capa de QGIS

CAMPOS = (('tipo', 'string'), ('localId', 'string'), ('namespace', 'string'), ('label', 'string'),
          ('referencia', 'string'), ('sup_gml', 'integer'), ('sup_calc', 'integer'), ('plantas', 'integer'),
          ('naturaleza', 'string'), ('descripcion', 'string'))


def capa(resultado, nombre):
    """Capa de memoria (polígonos) con los elementos leídos, en el SRC del fichero."""
    epsg = resultado.epsg or 25830
    uri = f"MultiPolygon?crs=EPSG:{epsg}&" + '&'.join(
        f"field={n}:{('string(160)' if n == 'descripcion' else 'string(60)') if t == 'string' else t}" for n, t in CAMPOS)
    nueva = QgsVectorLayer(uri, nombre, 'memory')
    entidades = []
    for e in resultado.elementos:
        f = QgsFeature(nueva.fields())
        if not e.geometria.isNull():
            g = QgsGeometry(e.geometria)
            g.convertToMultiType()
            f.setGeometry(g)
        f.setAttributes([e.tipo, e.local_id, e.namespace, e.label, e.referencia, e.area_declarada,
                         geo.redondear_m2(e.geometria.area()) if not e.geometria.isNull() else None,
                         e.plantas, e.naturaleza, e.descripcion])
        entidades.append(f)
    nueva.dataProvider().addFeatures(entidades)
    nueva.updateExtents()
    nueva.setCrs(QgsCoordinateReferenceSystem(f'EPSG:{epsg}'))
    return nueva
