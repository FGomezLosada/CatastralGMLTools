"""
Prueba de core/gml_parcela.py: estructura del GML de parcela 4.0, identificadores, geometría y errores. Sin internet.
Geometrías inventadas cerca de Nerja (EPSG:25830); las RC son de formato válido pero se usan solo como identificador.

Uso: tools\\probar.bat (o tools\\run_tests.py gml_parcela_test.py)
"""
import datetime
import os
import tempfile
import xml.etree.ElementTree as ET

from qgis.core import Qgis, QgsGeometry

from catastral_gml_tools.core import geometria as geo
from catastral_gml_tools.core import gml_parcela as gp
from catastral_gml_tools.core.incidencias import codigos

X0, Y0 = 421500.0, 4070500.0
N = {'wfs': gp.NS_WFS, 'gml': gp.NS_GML, 'cp': gp.NS_CP, 'base': gp.NS_BASE, 'xsi': gp.NS_XSI}


def rect(x, y, ancho, alto, hueco=None):
    wkt = f"(({x} {y}, {x + ancho} {y}, {x + ancho} {y + alto}, {x} {y + alto}, {x} {y})"
    if hueco:
        hx, hy, ha = hueco
        wkt += f", ({hx} {hy}, {hx + ha} {hy}, {hx + ha} {hy + ha}, {hx} {hy + ha}, {hx} {hy})"
    return QgsGeometry.fromWkt("POLYGON" + wkt + ")")


def anillo_de(poslist):
    v = [float(n) for n in poslist.split()]
    return list(zip(v[0::2], v[1::2]))


# 1. Segregación: la matriz conserva su RC (SDGC) y dos parcelas nuevas (LOCAL); una con hueco
parcelas = [
    gp.ParcelaGML('1907401VK4810H', gp.SDGC, rect(X0, Y0, 20, 30)),
    gp.ParcelaGML('Seg_1', gp.LOCAL, rect(X0 + 20, Y0, 10.004, 30)),
    gp.ParcelaGML('Seg_2', gp.LOCAL, rect(X0 + 30.004, Y0, 15, 30, hueco=(X0 + 35, Y0 + 10, 2))),
]
ahora = datetime.datetime(2026, 10, 6, 12, 30, 15)
texto, inc1 = gp.construir(parcelas, 25830, fecha=datetime.date(2026, 10, 1), ahora=ahora)
raiz = ET.fromstring(texto.encode('utf-8'))
miembros = raiz.findall('wfs:member', N)
cps = [m.find('cp:CadastralParcel', N) for m in miembros]
primera = cps[0]
hijos = [h.tag.split('}')[1] for h in primera]
orden = ['areaValue', 'beginLifespanVersion', 'endLifespanVersion', 'geometry', 'inspireId', 'label',
         'nationalCadastralReference', 'referencePoint']
gid = primera.get(f"{{{gp.NS_GML}}}id")
ident = primera.find('cp:inspireId/base:Identifier', N)
end = primera.find('cp:endLifespanVersion', N)
superficies = [c.find('cp:geometry/gml:MultiSurface', N) for c in cps]
poslists = [c.findall('.//gml:posList', N) for c in cps]
ext = poslists[0][0]
anillo = anillo_de(ext.text)
srs = {e.get('srsName') for c in cps for e in c.iter() if e.get('srsName')}
pos = [float(v) for v in primera.find('cp:referencePoint/gml:Point/gml:pos', N).text.split()]

cabecera = (texto.startswith('<?xml version="1.0" encoding="utf-8"?>') and 'herramienta no oficial' in texto
            and raiz.tag == f"{{{gp.NS_WFS}}}FeatureCollection" and raiz.get('numberMatched') == '3'
            and raiz.get('numberReturned') == '3' and raiz.get('timeStamp') == '2026-10-06T12:30:15'
            and 'cp/4.0/CadastralParcels.xsd' in raiz.get(f"{{{gp.NS_XSI}}}schemaLocation"))
estructura = len(miembros) == 3 and hijos == orden and gid == 'ES.SDGC.CP.1907401VK4810H'
identificador = (ident is not None and ident.find('base:localId', N).text == '1907401VK4810H'
                 and ident.find('base:namespace', N).text == 'ES.SDGC.CP'
                 and cps[1].find('cp:inspireId/base:Identifier/base:namespace', N).text == 'ES.LOCAL.CP'
                 and cps[1].get(f"{{{gp.NS_GML}}}id") == 'ES.LOCAL.CP.Seg_1')
atributos = (primera.find('cp:areaValue', N).text == '600' and primera.find('cp:areaValue', N).get('uom') == 'm2'
             and primera.find('cp:beginLifespanVersion', N).text == '2026-10-01T00:00:00'
             and end.get(f"{{{gp.NS_XSI}}}nil") == 'true' and end.get('nilReason') == gp.NIL_UNPOPULATED
             and primera.find('cp:label', N).text == '01'
             and primera.find('cp:nationalCadastralReference', N).text == '1907401VK4810H'
             and cps[1].find('cp:label', N).text == 'Seg_1' and cps[1].find('cp:nationalCadastralReference', N).text == 'Seg_1')
geometria_ok = (all(len(s.findall('gml:surfaceMember', N)) == 1 for s in superficies)
                and superficies[0].get(f"{{{gp.NS_GML}}}id") == 'MultiSurface_ES.SDGC.CP.1907401VK4810H'
                and cps[0].find('.//gml:Surface', N).get(f"{{{gp.NS_GML}}}id") == 'Surface_ES.SDGC.CP.1907401VK4810H.1'
                and ext.get('srsDimension') == '2' and ext.get('count') == str(len(anillo)) == '5'
                and anillo[0] == anillo[-1] and geo.es_horario(anillo)
                and srs == {'http://www.opengis.net/def/crs/EPSG/0/25830'})
decimales = all(len(v.split('.')[1]) == 2 for p in poslists for e in p for v in e.text.split())
redondeo = '421530.00' in poslists[1][0].text and cps[1].find('cp:areaValue', N).text == '300'
hueco = (len(poslists[2]) == 2 and cps[2].find('.//gml:interior', N) is not None
         and not geo.es_horario(anillo_de(poslists[2][1].text)) and cps[2].find('cp:areaValue', N).text == '446')
punto = rect(X0, Y0, 20, 30).contains(QgsGeometry.fromWkt(f"POINT({pos[0]} {pos[1]})"))

# 2. Labels por defecto
labels = (gp.label_por_defecto('1907401VK4810H', gp.SDGC) == '01' and gp.label_por_defecto('29053A00100123', gp.SDGC) == '123'
          and gp.label_por_defecto('Div_1_1', gp.LOCAL) == 'Div_1_1')

# 3. Errores: no se escribe nada
casos = {
    'GML-SIN-PARCELAS': ([], 25830),
    'SRC-NO-ADMITIDO': ([gp.ParcelaGML('Seg_1', gp.LOCAL, rect(X0, Y0, 5, 5))], 4326),
    'ID-REPETIDO': ([gp.ParcelaGML('A', gp.LOCAL, rect(X0, Y0, 5, 5)), gp.ParcelaGML('A', gp.LOCAL, rect(X0 + 5, Y0, 5, 5))], 25830),
    'ID-CARACTERES': ([gp.ParcelaGML('Parcela 1', gp.LOCAL, rect(X0, Y0, 5, 5))], 25830),
    'ID-VACIO': ([gp.ParcelaGML('', gp.LOCAL, rect(X0, Y0, 5, 5))], 25830),
    'NS-SDGC-SIN-RC': ([gp.ParcelaGML('Seg_1', gp.SDGC, rect(X0, Y0, 5, 5))], 25830),
    'NS-DESCONOCIDO': ([gp.ParcelaGML('Seg_1', 'OTRO', rect(X0, Y0, 5, 5))], 25830),
    'RC-FORAL': ([gp.ParcelaGML('31201A00100001', gp.SDGC, rect(X0, Y0, 5, 5))], 25830),
    'GEO-MULTIPARTE': ([gp.ParcelaGML('M', gp.LOCAL, QgsGeometry.fromWkt(
        f"MULTIPOLYGON((({X0} {Y0}, {X0 + 5} {Y0}, {X0 + 5} {Y0 + 5}, {X0} {Y0})), "
        f"(({X0 + 9} {Y0}, {X0 + 12} {Y0}, {X0 + 12} {Y0 + 3}, {X0 + 9} {Y0})))"))], 25830),
}
errores = {}
for codigo, (lista, epsg) in casos.items():
    t, inc = gp.construir(lista, epsg)
    errores[codigo] = t is None and codigo in codigos(inc)

# 4. Escribir el fichero
carpeta = tempfile.mkdtemp(prefix='cgt_gml_')
ruta = os.path.join(carpeta, 'segregacion.gml')
ok, _ = gp.escribir(ruta, parcelas, 25830)
with open(ruta, encoding='utf-8') as f:
    leido = f.read()
fichero = ok and ET.fromstring(leido.encode('utf-8')).tag.endswith('FeatureCollection') and '\r\n' not in leido
no_escribe, _ = gp.escribir(os.path.join(carpeta, 'mal.gml'), [], 25830)
no_escribe = not no_escribe and not os.path.exists(os.path.join(carpeta, 'mal.gml'))

checks = {
    "cabecera, raíz WFS 2.0, número de parcelas y esquema 4.0": cabecera,
    "un member por parcela, orden de elementos y gml:id": estructura,
    "inspireId con base 3.3: SDGC con RC y LOCAL con identificador propio": identificador,
    "superficie, fechas, endLifespanVersion nulo, label y referencia": atributos,
    "un recinto por parcela, ids de geometría, count, cierre, sentido horario y srsName": geometria_ok,
    "todas las coordenadas con 2 decimales": decimales,
    "coordenadas y superficie redondeadas": redondeo,
    "hueco como gml:interior en sentido antihorario y superficie sin el hueco": hueco,
    "punto de referencia dentro de la parcela": punto,
    "label por defecto (urbana, rústica, LOCAL)": labels,
    "fichero UTF-8 bien formado y con saltos de línea LF": fichero,
    "con errores no se crea el fichero": no_escribe,
}
checks.update({f"error detectado: {c}": v for c, v in errores.items()})

print("=" * 60)
print("QGIS", Qgis.version(), "· GML de parcela 4.0")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'hijos': hijos, 'gid': gid, 'areas': [c.find('cp:areaValue', N).text for c in cps],
                        'poslist1': poslists[1][0].text[:80], 'inc1': codigos(inc1)})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
