"""
Servicios del Catastro simulados para las pruebas (sin internet y sin datos reales del Catastro en el repositorio).

Sustituye core.servicios.pedir por una función que contesta como los servicios reales (formato comprobado contra
ellos el 07/10/2026) con parcelas y construcciones SINTÉTICAS:
  - 1907401VK4810H: parcela en el huso 30 con una colindante (1907402), un camino de dominio público que linda por el
    sur (29071A00709001), otra a 20 m (1907403, entorno) y otra a 100 m (fuera del entorno), y construcciones (las del fichero tests/data/gml/edificio_sintetico.gml);
  - 1907404VK4810H: parcela situada en el huso 29 (al pedirla en el 30 hay que volver a pedirla en el 29);
  - 1907407VK4810H: parcela de 1,2 × 1 km, demasiado grande para pedir su entorno: se usa GetNeighbourParcel, que
    contesta «No se han encontrado parcelas colindantes» (como hace el real con parcelas rodeadas de calles);
  - las consultas por rectángulo (bbox) devuelven las parcelas sintéticas que lo tocan, en el SRC pedido;
  - cualquier otra: ExceptionReport «No se ha encontrado la parcela…»;
  - RED: si la referencia es 1907409VK4810H, error de red.
Consulta_DNPRC: el camino es «VT · vía de comunicación de dominio público»; las demás de rústica, matorral.
El clic en el mapa (Consulta_RCCOOR) devuelve 1907401VK4810H salvo en longitudes positivas (sin parcela).

No es una prueba: lo importan las pruebas con importlib (no está en la lista de tools/run_tests.py).
"""
import json
import os
from urllib.parse import parse_qs, urlparse

from qgis.core import QgsGeometry, QgsRectangle

from catastral_gml_tools.core import geometria as geo
from catastral_gml_tools.core import gml_parcela as gp
from catastral_gml_tools.core import servicios
from catastral_gml_tools.core.info import RAIZ

RC = '1907401VK4810H'
RC_HUSO_29 = '1907404VK4810H'
RC_SIN_RED = '1907409VK4810H'
RC_GRANDE = '1907407VK4810H'
NAVARRA = '201040112'  #Parcela sintética de Navarra (municipio 201, polígono 4, parcela 112)
NX, NY = 610000.0, 4740000.0  #Navarra, EPSG:25830
CAMINO = '29071A00709001'  #Camino de dominio público (parcela 9001 de rústica) que linda con RC por el sur
X0, Y0 = 421500.0, 4070500.0          #Huso 30 (Andalucía oriental)
X29, Y29 = 150000.0, 4700000.0        #En coordenadas del huso 30, pero cae en el 29 (Galicia)

EXCEPCION = ('<?xml version="1.0" encoding="ISO-8859-1"?>\r\n<ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows/1.1" '
             'version="2.0.0"><ows:Exception exceptionCode="InvalidParameterValue"><ows:ExceptionText><![CDATA[No se ha '
             'encontrado la parcela {rc} para el huso {huso}]]></ows:ExceptionText></ows:Exception></ows:ExceptionReport>')
VACIA = ('<?xml version="1.0" encoding="ISO-8859-1"?>\r\n<gml:FeatureCollection xmlns:gml="http://www.opengis.net/gml/3.2" '
         'xmlns:bu-ext2d="http://inspire.jrc.ec.europa.eu/schemas/bu-ext2d/2.0" gml:id="ES.SDGC.BU"></gml:FeatureCollection>')

SIN_COLINDANTES = ('<?xml version=\'1.0\' encoding="ISO-8859-1" standalone="no"?>\r\n<ExceptionReport '
                   'xmlns="http://www.opengis.net/ows/1.1" version="2.0.0">\r\n<Exception exceptionCode='
                   '"OperationProcessingFailed">\r\n<ExceptionText><![CDATA[No se han encontrado parcelas colindantes a la '
                   'solicitada]]></ExceptionText>\r\n</Exception>\r\n</ExceptionReport>\r\n')

DNPRC_CAIDO = False  #True: la consulta de datos de parcela falla (para probar la regla de numeración sola)
peticiones = []  #Direcciones pedidas, para comprobar qué se ha consultado


def rect(x, y, a, b):
    return QgsGeometry.fromWkt(f"POLYGON(({x} {y}, {x + a} {y}, {x + a} {y + b}, {x} {y + b}, {x} {y}))")


def _todas():
    """Todas las parcelas sintéticas (referencia, geometría en coordenadas del huso 30)."""
    return [(RC, rect(X0, Y0, 20, 30)), ('1907402VK4810H', rect(X0 + 20, Y0, 20, 30)),
            ('1907403VK4810H', rect(X0 + 40, Y0, 20, 30)), (CAMINO, rect(X0, Y0 - 6, 60, 6)), ('1907408VK4810H', rect(X0 + 120, Y0, 20, 30)),
            (RC_HUSO_29, rect(X29, Y29, 20, 30)), ('1907405VK4810H', rect(X29 + 20, Y29, 20, 30)),
            (RC_GRANDE, rect(X0 + 5000, Y0, 1200, 1000))]


def _parcelas(lista, epsg):
    if not lista:  #Colección vacía, como la del servicio cuando no encuentra nada
        return (b'<?xml version="1.0" encoding="UTF-8"?><wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" '
                b'numberMatched="0" numberReturned="0"/>')
    texto, _ = gp.construir(lista, epsg)
    return texto.encode('utf-8')


def _en(geom, epsg):
    """Geometría escrita en coordenadas del huso 30, pasada al EPSG pedido (como reproyecta el servicio real)."""
    if epsg == 25830:
        return geom
    from qgis.core import QgsCoordinateReferenceSystem
    return geo.transformar(geom, QgsCoordinateReferenceSystem('EPSG:25830'), epsg)


def pedir(url):
    peticiones.append(url)
    partes = urlparse(url)
    q = {k.lower(): v[0] for k, v in parse_qs(partes.query).items()}
    if 'consulta_dnprc' in partes.path.lower():
        if DNPRC_CAIDO:
            return b'', 'Connection refused (simulado)'
        rc = q['refcat']
        camino = rc == CAMINO
        lspr = [{"cspr": "0", "dspr": {"ccc": "VT" if camino else "MT", "ip": "00",
                                       "dcc": "VÍA DE COMUNICACIÓN DE DOMINIO PÚBLICO" if camino else "MATORRAL"}}]
        return json.dumps({"consulta_dnprcResult": {"control": {"cudnp": 1}, "bico": {
            "bi": {"idbi": {"cn": "RU"}, "dt": {"locs": {"lors": {"lorus": {"npa": "CAMINO" if camino else "PARAJE INVENTADO"}}}},
                   "ldt": f"Polígono {int(rc[6:9])} Parcela {int(rc[9:14])} (ficticia)"}, "lspr": lspr}}}).encode('utf-8'), ''
    if 'consulta_rccoor' in partes.path.lower():
        if -2.55 <= float(q['coorx']) <= -0.70 and 41.88 <= float(q['coory']) <= 43.35:  #Navarra: referencia de 9
            return json.dumps({"Consulta_RCCOORResult": {"control": {"cucoor": 1}, "coordenadas": {"coord": [
                {"pc": {"pc1": NAVARRA[:7], "pc2": NAVARRA[7:]}, "ldt": ""}]}}}).encode('utf-8'), ''
        if float(q['coorx']) > 0:
            return json.dumps({"Consulta_RCCOORResult": {"control": {"cuerr": 1}, "lerr": [
                {"cod": "16", "des": "PARA ESAS COORDENADAS NO HAY REFERENCIA DISPONIBLE"}]}}).encode('utf-8'), ''
        return json.dumps({"Consulta_RCCOORResult": {"control": {"cucoor": 1}, "coordenadas": {"coord": [
            {"pc": {"pc1": RC[:7], "pc2": RC[7:]}, "geo": {"xcen": q['coorx'], "ycen": q['coory'], "srs": q['srs']},
             "ldt": "CL INVENTADA 1 MUNICIPIO FICTICIO (PROVINCIA)"}]}}}).encode('utf-8'), ''
    if 'inspire.navarra.es' in partes.netloc:
        return _navarra(partes.path, q), ''
    rc, consulta = q.get('refcat', ''), q.get('storedquerie_id', '')
    epsg = int(q.get('srsname', 'EPSG::25830').rsplit(':', 1)[-1])
    if 'bbox' in q:
        caja = QgsGeometry.fromRect(QgsRectangle(*[float(v) for v in q['bbox'].split(',')]))
        todas = [gp.ParcelaGML(r, gp.SDGC, _en(g, epsg)) for r, g in _todas()]
        return _parcelas([p for p in todas if p.geometria.intersects(caja)], epsg), ''
    if rc == RC_SIN_RED:
        return b'', 'Host ovc.catastro.meh.es not found (simulado)'
    propias = dict(_todas())
    if rc not in propias:
        return EXCEPCION.format(rc=rc, huso=epsg).encode('latin-1'), ''
    if consulta == 'GetParcel':
        return _parcelas([gp.ParcelaGML(rc, gp.SDGC, _en(propias[rc], epsg))], epsg), ''
    if consulta == 'GetNeighbourParcel':
        return SIN_COLINDANTES.encode('latin-1'), ''
    if consulta == 'GetBuildingByParcel' and rc == RC:
        with open(os.path.join(RAIZ, 'tests', 'data', 'gml', 'edificio_sintetico.gml'), 'rb') as f:
            return f.read(), ''
    return VACIA.encode('latin-1'), ''


BU_NAVARRA = ('<?xml version="1.0" encoding="UTF-8"?><wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" '
              'xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:BU="http://inspire.ec.europa.eu/schemas/bu-core2d/4.0" '
              'xmlns:bu-base="http://inspire.ec.europa.eu/schemas/bu-base/4.0" '
              'xmlns:base="http://inspire.ec.europa.eu/schemas/base/3.3">{miembros}</wfs:FeatureCollection>')
EDIFICIO_NAVARRA = ('<wfs:member><BU:Building gml:id="ES.RRTN.BU.{id}"><bu-base:inspireId><base:Identifier><base:localId>{id}'
                    '</base:localId><base:namespace>ES.RRTN.BU</base:namespace></base:Identifier></bu-base:inspireId>'
                    '<bu-base:numberOfFloorsAboveGround>3</bu-base:numberOfFloorsAboveGround><BU:geometry2D><gml:Polygon '
                    'srsName="http://www.opengis.net/def/crs/EPSG/0/25830"><gml:exterior><gml:LinearRing><gml:posList>'
                    '{x0} {y0} {x0} {y1} {x1} {y1} {x1} {y0} {x0} {y0}</gml:posList></gml:LinearRing></gml:exterior>'
                    '</gml:Polygon></BU:geometry2D></BU:Building></wfs:member>')


def _todas_navarra():
    return [(NAVARRA, rect(NX, NY, 20, 30)), ('201040113', rect(NX + 20, NY, 20, 30)), ('201040114', rect(NX + 40, NY, 20, 30))]


def _navarra(ruta, q):
    """Servicios INSPIRE de Navarra simulados: parcela por ResourceId, parcelas y edificios por rectángulo."""
    if 'BU' in ruta:
        caja = QgsRectangle(*[float(v) for v in q['bbox'].split(',')[:4]])
        edificios = [(NAVARRA + 'A', NX + 2, NY + 2, NX + 12, NY + 12), ('201049999A', NX + 15, NY + 2, NX + 18, NY + 5)]
        miembros = ''.join(EDIFICIO_NAVARRA.format(id=i, x0=a, y0=b, x1=c, y1=d) for i, a, b, c, d in edificios
                           if caja.intersects(QgsRectangle(a, b, c, d)))
        return BU_NAVARRA.format(miembros=miembros).encode('utf-8')
    todas = dict(_todas_navarra())
    if 'filter' in q:
        rid = q['filter'].split('rid="')[1].split('"')[0].replace('ES.RRTN.CP.', '')
        return _parcelas([gp.ParcelaGML(rid, gp.LOCAL, todas[rid])] if rid in todas else [], 25830)
    caja = QgsGeometry.fromRect(QgsRectangle(*[float(v) for v in q['bbox'].split(',')[:4]]))
    return _parcelas([gp.ParcelaGML(r, gp.LOCAL, g) for r, g in todas.items() if g.intersects(caja)], 25830)


def instalar():
    """Sustituye la red por el simulador. Devuelve la función original para poder restaurarla."""
    original = servicios.pedir
    servicios.pedir = pedir
    peticiones.clear()
    return original
