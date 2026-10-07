"""
Prueba de core/esquemas.py (validación contra el esquema XSD oficial).

Con internet (o con los esquemas ya guardados en la caché): el GML del plugin cumple el esquema y uno alterado no.
Sin internet: el resultado debe ser «no se ha podido comprobar», NUNCA «válido» (lección E-10 de docs/DESARROLLO.md).
La prueba pasa en los dos casos, pero dice en cuál se ha ejecutado.

Uso: tools\\probar.bat (o tools\\run_tests.py esquemas_test.py)
"""
import os
import tempfile
import time

from qgis.core import Qgis, QgsGeometry

from catastral_gml_tools.core import esquemas
from catastral_gml_tools.core import gml_parcela as gp
from catastral_gml_tools.core.incidencias import ERROR, codigos
from catastral_gml_tools.core.info import RAIZ

X0, Y0 = 421500.0, 4070500.0
carpeta = tempfile.mkdtemp(prefix='cgt_xsd_')


def rect(x, y, a, b):
    return QgsGeometry.fromWkt(f"POLYGON(({x} {y}, {x + a} {y}, {x + a} {y + b}, {x} {y + b}, {x} {y}))")


texto, _ = gp.construir([gp.ParcelaGML('1907401VK4810H', gp.SDGC, rect(X0, Y0, 20, 30)),
                         gp.ParcelaGML('Nueva_1', gp.LOCAL, rect(X0 + 20, Y0, 15, 30))], 25830)
bueno = texto.encode('utf-8')
malo = texto.replace('<cp:label>', '<cp:etiqueta>').replace('</cp:label>', '</cp:etiqueta>').encode('utf-8')

conexion = bool(esquemas.descargar(esquemas.ESQUEMA_PARCELA['http://inspire.ec.europa.eu/schemas/cp/4.0']))
inicio = time.time()
r_bueno = esquemas.validar(bueno, 'CP 4.0')
primera = time.time() - inicio
r_malo = esquemas.validar(malo, 'CP 4.0')
inicio = time.time()
esquemas.validar(bueno, 'CP 4.0')
segunda = time.time() - inicio

if conexion:
    modo = f"con conexión (primera vez {primera:.1f} s, segunda {segunda:.1f} s desde la caché)"
    checks = {
        "el GML del plugin cumple el esquema oficial (WFS 2.0 + CP 4.0)": codigos(r_bueno) == ['XSD-VALIDO'],
        "un GML alterado no lo cumple y dice dónde": 'XSD' in codigos(r_malo) and any('etiqueta' in i.mensaje for i in r_malo)
                                                     and all(i.nivel == ERROR for i in r_malo),
        "la segunda vez usa la caché (menos de 3 s)": segunda < 3,
    }
else:
    modo = "sin conexión"
    checks = {
        "sin conexión NO dice «válido»": 'XSD-VALIDO' not in codigos(r_bueno) and 'XSD-VALIDO' not in codigos(r_malo),
        "sin conexión avisa de que no se ha podido comprobar": codigos(r_bueno) == ['XSD-SIN-COMPROBAR'],
    }
otros = (codigos(esquemas.validar(bueno, 'CP 3.0')) == ['XSD-VERSION']
         and os.path.isdir(esquemas.carpeta_cache()))
with open(os.path.join(RAIZ, 'tests', 'data', 'gml', 'mal_formado.gml'), 'rb') as f:
    mal_formado = esquemas.validar(f.read(), 'CP 4.0')
checks["versiones sin esquema y carpeta de caché"] = otros
checks["XML mal formado: error o sin comprobar, nunca válido"] = 'XSD-VALIDO' not in codigos(mal_formado)

print("=" * 60)
print("QGIS", Qgis.version(), "· esquema XSD ·", modo)
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'bueno': [str(i) for i in r_bueno], 'malo': [str(i) for i in r_malo][:3],
                        'mal_formado': [str(i) for i in mal_formado]})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
