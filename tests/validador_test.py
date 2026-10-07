"""
Prueba de core/validador.py: un GML correcto no da errores ni avisos, y cada regla detecta su fallo en un fichero
alterado a propósito. Ficheros sintéticos (coordenadas inventadas cerca de Nerja). Sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py validador_test.py)
"""
import os
import re
import tempfile

from qgis.core import Qgis, QgsGeometry

from catastral_gml_tools.core import gml_parcela as gp
from catastral_gml_tools.core import validador as va
from catastral_gml_tools.core.incidencias import AVISO, ERROR, codigos
from catastral_gml_tools.core.info import RAIZ

X0, Y0 = 421500.0, 4070500.0
carpeta = tempfile.mkdtemp(prefix='cgt_validador_')


def rect(x, y, a, b):
    return QgsGeometry.fromWkt(f"POLYGON(({x} {y}, {x + a} {y}, {x + a} {y + b}, {x} {y + b}, {x} {y}))")


def gml(parcelas, nombre='base.gml'):
    ruta = os.path.join(carpeta, nombre)
    ok, inc = gp.escribir(ruta, parcelas, 25830)
    assert ok, inc
    return ruta


def alterar(ruta, nombre, *cambios, regex=False):
    with open(ruta, encoding='utf-8') as f:
        texto = f.read()
    for viejo, nuevo in cambios:
        texto = re.sub(viejo, nuevo, texto, count=1) if regex else texto.replace(viejo, nuevo, 1)
    destino = os.path.join(carpeta, nombre)
    with open(destino, 'w', encoding='utf-8') as f:
        f.write(texto)
    return destino


def codigos_de(ruta):
    return codigos(va.validar(ruta).incidencias)


base = gml([gp.ParcelaGML('1907401VK4810H', gp.SDGC, rect(X0, Y0, 20, 30)),
            gp.ParcelaGML('Nueva_1', gp.LOCAL, rect(X0 + 20, Y0, 15, 30))])
informe = va.validar(base)
limpio = not informe.errores and not informe.avisos and va.resumen(informe).startswith('Sin errores')
estados = [informe.estado('1907401VK4810H'), informe.estado('Nueva_1')] == ['correcta', 'correcta']

#Primer posList de la primera parcela (exterior): '421500.00 4070500.00 421500.00 4070530.00 …'
casos = {
    'XLINK': alterar(base, 'xlink.gml', (f'xmlns:xlink="{gp.NS_XLINK}" ', '')),
    'SRC-NO-ADMITIDO': alterar(base, 'src.gml', *[('EPSG/0/25830"', 'EPSG/0/3857"')] * 99),
    'ID-REPETIDO': alterar(base, 'repetido.gml', ('<localId>Nueva_1</localId>', '<localId>1907401VK4810H</localId>')),
    'ID-CARACTERES': alterar(base, 'caracteres.gml', ('<localId>Nueva_1</localId>', '<localId>Nueva 1</localId>')),
    'NS-DESCONOCIDO': alterar(base, 'ns.gml', ('<namespace>ES.LOCAL.CP</namespace>', '<namespace>ES.OTRO.CP</namespace>')),
    'NS-SDGC-SIN-RC': alterar(base, 'sdgc.gml', ('<namespace>ES.LOCAL.CP</namespace>', '<namespace>ES.SDGC.CP</namespace>')),
    'RC-FORAL': alterar(base, 'foral.gml', ('<localId>1907401VK4810H</localId>', '<localId>31201A00100001</localId>')),
    'GMLID': alterar(base, 'gmlid.gml', ('gml:id="ES.LOCAL.CP.Nueva_1"', 'gml:id="ES.LOCAL.CP.Otro"')),
    'ANILLO-ABIERTO': alterar(base, 'abierto.gml', (r'(count="5">)([^<]*?) 421500\.00 4070500\.00<', r'count="4">\2<'),
                              regex=True),
    'ANILLO-COUNT': alterar(base, 'count.gml', ('count="5"', 'count="6"')),
    'ANILLO-SENTIDO': alterar(base, 'sentido.gml',
                              ('421500.00 4070500.00 421500.00 4070530.00 421520.00 4070530.00 421520.00 4070500.00 421500.00 4070500.00',
                               '421500.00 4070500.00 421520.00 4070500.00 421520.00 4070530.00 421500.00 4070530.00 421500.00 4070500.00')),
    'DECIMALES': alterar(base, 'decimales.gml', ('421500.00 4070530.00', '421500.001 4070530.00')),
    'GEO-INVALIDA': alterar(base, 'pajarita.gml',
                            ('421500.00 4070500.00 421500.00 4070530.00 421520.00 4070530.00 421520.00 4070500.00 421500.00 4070500.00',
                             '421500.00 4070500.00 421520.00 4070530.00 421500.00 4070530.00 421520.00 4070500.00 421500.00 4070500.00')),
    'SUP-DISTINTA': alterar(base, 'superficie.gml', ('<cp:areaValue uom="m2">600</cp:areaValue>', '<cp:areaValue uom="m2">610</cp:areaValue>')),
    'SUP-FALTA': alterar(base, 'sinsuperficie.gml', ('<cp:areaValue uom="m2">600</cp:areaValue>', '')),
    'REFPOINT': alterar(base, 'refpoint.gml', (r'(<gml:pos>)[^<]+(</gml:pos>)', r'\g<1>421000.00 4070000.00\2'), regex=True),
    'GEO-MULTIPARTE': alterar(base, 'multiparte.gml', (
        '</gml:surfaceMember>',
        '</gml:surfaceMember><gml:surfaceMember><gml:Surface gml:id="S2" srsName="http://www.opengis.net/def/crs/EPSG/0/25830">'
        '<gml:patches><gml:PolygonPatch><gml:exterior><gml:LinearRing><gml:posList srsDimension="2" count="5">'
        '421600.00 4070600.00 421600.00 4070610.00 421610.00 4070610.00 421610.00 4070600.00 421600.00 4070600.00'
        '</gml:posList></gml:LinearRing></gml:exterior></gml:PolygonPatch></gml:patches></gml:Surface></gml:surfaceMember>')),
}
casos['SOLAPE'] = gml([gp.ParcelaGML('A', gp.LOCAL, rect(X0, Y0, 20, 30)), gp.ParcelaGML('B', gp.LOCAL, rect(X0 + 15, Y0, 15, 30))],
                      'solape.gml')
#Hueco cerrado de 5 × 10 m entre A (con un entrante) y B (con otro entrante enfrentado)
casos['HUECO'] = gml([gp.ParcelaGML('A', gp.LOCAL, QgsGeometry.fromWkt(
                          f"POLYGON(({X0} {Y0}, {X0 + 20} {Y0}, {X0 + 20} {Y0 + 10}, {X0 + 15} {Y0 + 10}, {X0 + 15} {Y0 + 20}, "
                          f"{X0 + 20} {Y0 + 20}, {X0 + 20} {Y0 + 30}, {X0} {Y0 + 30}, {X0} {Y0}))")),
                      gp.ParcelaGML('B', gp.LOCAL, QgsGeometry.fromWkt(
                          f"POLYGON(({X0 + 20} {Y0}, {X0 + 40} {Y0}, {X0 + 40} {Y0 + 30}, {X0 + 20} {Y0 + 30}, {X0 + 20} {Y0 + 20}, "
                          f"{X0 + 25} {Y0 + 20}, {X0 + 25} {Y0 + 10}, {X0 + 20} {Y0 + 10}, {X0 + 20} {Y0}))"))], 'hueco.gml')
casos['ESBELTEZ'] = gml([gp.ParcelaGML('Larga', gp.LOCAL, rect(X0, Y0, 200, 10))], 'esbeltez.gml')
casos['N-PARCELAS'] = gml([gp.ParcelaGML(f'P_{i}', gp.LOCAL, rect(X0 + i * 10, Y0, 10, 10)) for i in range(31)], 'muchas.gml')
casos['CP-30'] = os.path.join(RAIZ, 'tests', 'data', 'gml', 'parcela_cp30_sintetica.gml')
casos['XML-MAL-FORMADO'] = os.path.join(RAIZ, 'tests', 'data', 'gml', 'mal_formado.gml')

detectados = {}
for codigo, ruta in casos.items():
    encontrados = codigos_de(ruta)
    detectados[codigo] = (codigo in encontrados, encontrados)

#Nivel de algunas reglas y que un error se atribuye a su parcela
inf_sup = va.validar(casos['SUP-DISTINTA'])
niveles = ([i.nivel for i in inf_sup.incidencias if i.codigo == 'SUP-DISTINTA'] == [ERROR]
           and inf_sup.estado('1907401VK4810H') == ERROR and inf_sup.estado('Nueva_1') == 'correcta'
           and [i.nivel for i in va.validar(casos['ESBELTEZ']).incidencias if i.codigo == 'ESBELTEZ'] == [AVISO]
           and '1 error' in va.resumen(inf_sup))
edificio = va.validar(os.path.join(RAIZ, 'tests', 'data', 'gml', 'edificio_sintetico.gml'))
edificio_ok = not edificio.errores

checks = {
    "GML correcto: sin errores ni avisos y todas las parcelas correctas": limpio and estados,
    "niveles de error y aviso, y error atribuido a su parcela": niveles,
    "GML de edificio sintético: sin errores": edificio_ok,
}
checks.update({f"detecta {c}": ok for c, (ok, _) in detectados.items()})

print("=" * 60)
print("QGIS", Qgis.version(), "· validador")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'base': [str(i) for i in informe.incidencias], 'edificio': [str(i) for i in edificio.incidencias],
                        'fallos': {c: e for c, (ok, e) in detectados.items() if not ok}})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
