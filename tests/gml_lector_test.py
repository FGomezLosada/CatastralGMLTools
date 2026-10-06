"""
Prueba de core/gml_lector.py: lee el GML de parcela 4.0 que escribe el plugin, uno 3.0 antiguo y uno de edificio
(ficheros sintéticos de tests/data/gml), detecta errores de lectura y crea la capa de memoria. Sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py gml_lector_test.py)
"""
import os
import tempfile

from qgis.core import Qgis, QgsGeometry

from catastral_gml_tools.core import gml_lector as gl
from catastral_gml_tools.core import gml_parcela as gp
from catastral_gml_tools.core.incidencias import codigos
from catastral_gml_tools.core.info import RAIZ

DATOS = os.path.join(RAIZ, 'tests', 'data', 'gml')
X0, Y0 = 421500.0, 4070500.0
carpeta = tempfile.mkdtemp(prefix='cgt_lector_')


def rect(x, y, a, b):
    return QgsGeometry.fromWkt(f"POLYGON(({x} {y}, {x + a} {y}, {x + a} {y + b}, {x} {y + b}, {x} {y}))")


# 1. El GML 4.0 que escribe el propio plugin
ruta4 = os.path.join(carpeta, 'segregacion.gml')
gp.escribir(ruta4, [gp.ParcelaGML('1907401VK4810H', gp.SDGC, rect(X0, Y0, 20, 30)),
                    gp.ParcelaGML('Nueva_1', gp.LOCAL, rect(X0 + 20, Y0, 15.004, 30))], 25830)
r4 = gl.leer(ruta4)
e = r4.elementos
lectura4 = (r4.version == 'CP 4.0' and r4.epsg == 25830 and r4.xlink_declarado and len(e) == 2
            and [x.local_id for x in e] == ['1907401VK4810H', 'Nueva_1'] and [x.namespace for x in e] == ['ES.SDGC.CP', 'ES.LOCAL.CP']
            and [x.area_declarada for x in e] == [600, 450] and e[0].label == '01' and e[1].referencia == 'Nueva_1'
            and e[0].tipo == gl.PARCELA and e[0].recintos == 1 and e[0].counts == [5] and len(e[0].anillos) == 1
            and abs(e[1].geometria.area() - 450.0) < 0.5 and e[0].gml_id == 'ES.SDGC.CP.1907401VK4810H'
            and 'GML-LEIDO' in codigos(r4.incidencias))

# 2. Un GML 3.0 antiguo (posList y gml:coordinates, srsName en forma URN)
r3 = gl.leer(os.path.join(DATOS, 'parcela_cp30_sintetica.gml'))
lectura3 = (r3.version == 'CP 3.0' and r3.epsg == 25830 and 'CP-30' in codigos(r3.incidencias)
            and [x.local_id for x in r3.elementos] == ['Prueba_1', 'Prueba_2']
            and all(abs(x.geometria.area() - 200) < 0.01 for x in r3.elementos))

# 3. Un GML de edificio (ISO-8859-1): edificio en dos partes y una piscina
rb = gl.leer(os.path.join(DATOS, 'edificio_sintetico.gml'))
edificio, piscina = (rb.elementos + [None, None])[:2]
lectura_bu = (rb.version == 'BU 2.0' and rb.epsg == 25830 and len(rb.elementos) == 2
              and edificio.tipo == gl.EDIFICIO and edificio.plantas == 2 and edificio.recintos == 2
              and edificio.geometria.isMultipart() and abs(edificio.geometria.area() - 64) < 0.01
              and piscina.tipo == gl.OTRA and piscina.naturaleza == 'openAirPool' and abs(piscina.geometria.area() - 18) < 0.01
              and piscina.local_id == 'Edificio_1_PI.1')

# 4. Errores de lectura: nunca excepciones, siempre incidencias
r_mal = gl.leer(os.path.join(DATOS, 'mal_formado.gml'))
r_falta = gl.leer(os.path.join(carpeta, 'no_existe.gml'))
vacio = os.path.join(carpeta, 'vacio.gml')
with open(vacio, 'w', encoding='utf-8') as f:
    f.write('<?xml version="1.0"?><FeatureCollection xmlns="http://www.opengis.net/wfs/2.0"></FeatureCollection>')
r_vacio = gl.leer(vacio)
mezcla = os.path.join(carpeta, 'mezcla.gml')
with open(ruta4, encoding='utf-8') as f:
    texto = f.read()
with open(mezcla, 'w', encoding='utf-8') as f:
    f.write(texto.replace('EPSG/0/25830"', 'EPSG/0/25829"', 2))
r_mezcla = gl.leer(mezcla)
sin_xlink = os.path.join(carpeta, 'sin_xlink.gml')
with open(sin_xlink, 'w', encoding='utf-8') as f:
    f.write(texto.replace(f'xmlns:xlink="{gp.NS_XLINK}" ', ''))
errores = ('XML-MAL-FORMADO' in codigos(r_mal.incidencias) and 'FICHERO' in codigos(r_falta.incidencias)
           and 'GML-SIN-ELEMENTOS' in codigos(r_vacio.incidencias) and 'SRC-MEZCLADOS' in codigos(r_mezcla.incidencias)
           and not gl.leer(sin_xlink).xlink_declarado)

# 5. srsName en todas sus formas
srs = [gl.epsg_de_srsname(s) for s in ('http://www.opengis.net/def/crs/EPSG/0/25830', 'urn:ogc:def:crs:EPSG::25829',
                                        'EPSG:32628', 'urn:ogc:def:crs:EPSG:6.6:25831', '', None)]
srs_ok = srs == [25830, 25829, 32628, 25831, None, None]

# 6. Capa de memoria para el mapa
capa = gl.capa(r4, 'segregacion')
capa_bu = gl.capa(rb, 'edificio')
atributos = [f['localId'] for f in capa.getFeatures()]
capa_ok = (capa.isValid() and capa.featureCount() == 2 and capa.crs().authid() == 'EPSG:25830' and atributos == ['1907401VK4810H', 'Nueva_1']
           and [f['sup_gml'] for f in capa.getFeatures()] == [600, 450] and [f['sup_calc'] for f in capa.getFeatures()] == [600, 450]
           and capa_bu.featureCount() == 2 and [f['tipo'] for f in capa_bu.getFeatures()] == [gl.EDIFICIO, gl.OTRA]
           and not os.path.exists(os.path.splitext(ruta4)[0] + '.gfs'))

checks = {
    "lee el GML 4.0 del plugin: identificadores, superficies, label, count y xlink": lectura4,
    "lee un GML 3.0 (posList y coordinates) y avisa de que está obsoleto": lectura3,
    "lee un GML de edificio en ISO-8859-1: edificio en dos partes y piscina": lectura_bu,
    "errores de lectura sin excepciones (mal formado, sin fichero, vacío, SRC mezclados, sin xlink)": errores,
    "srsName en forma de URL, URN y EPSG": srs_ok,
    "capa de memoria con atributos, SRC del fichero y sin crear .gfs": capa_ok,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· lector de GML")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'v4': (r4.version, r4.epsg, r4.xlink_declarado, [(x.local_id, x.area_declarada, x.label, x.counts, x.recintos) for x in e]),
                        'v3': (r3.version, r3.epsg, codigos(r3.incidencias), [x.geometria.area() for x in r3.elementos]),
                        'bu': (rb.version, [(x.tipo, x.plantas, x.recintos, x.naturaleza, x.geometria.area()) for x in rb.elementos], codigos(rb.incidencias)),
                        'mal': codigos(r_mal.incidencias), 'vacio': codigos(r_vacio.incidencias), 'mezcla': codigos(r_mezcla.incidencias),
                        'srs': srs})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
