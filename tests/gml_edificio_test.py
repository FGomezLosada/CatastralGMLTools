"""
Prueba del escritor del GML de edificio (mejora 18): core/gml_edificio.py. Edificio con dos recintos y un hueco, una
piscina, identificadores según el formato de la DGC, lectura con el lector del plugin, validador sin errores, errores
previos (piscina en dos partes, estado, plantas, SRC, identificador repetido) y esquema XSD (si hay conexión o caché).
Sin internet salvo el esquema.

Uso: tools\\probar.bat (o tools\\run_tests.py gml_edificio_test.py)
"""
import datetime
import os
import tempfile

from qgis.core import Qgis, QgsGeometry

from catastral_gml_tools.core import esquemas
from catastral_gml_tools.core import gml_edificio as ge
from catastral_gml_tools.core import gml_lector as gl
from catastral_gml_tools.core import validador
from catastral_gml_tools.core.incidencias import AVISO, ERROR, INFO, codigos

X0, Y0 = 421500.0, 4070500.0
RC = '1907401VK4810H'
carpeta = tempfile.mkdtemp(prefix='cgt_bu_')


def rect(x, y, a, b):
    return f"(({x} {y}, {x + a} {y}, {x + a} {y + b}, {x} {y + b}, {x} {y}))"


#Edificio: dos cuerpos separados, el primero con patio interior; piscina aparte
cuerpos = QgsGeometry.fromWkt(f"MULTIPOLYGON(((421502 4070502, 421502 4070512, 421512 4070512, 421512 4070502, "
                              f"421502 4070502), (421505 4070505, 421507 4070505, 421507 4070507, 421505 4070507, "
                              f"421505 4070505)), {rect(X0 + 15, Y0 + 2, 4, 4)})")
piscina = QgsGeometry.fromWkt('POLYGON' + rect(X0 + 2, Y0 + 15, 6, 3))

# 1. Identificadores según el formato de la DGC
ids_uno = ge.identificadores(RC, [ge.EDIFICIO, ge.PISCINA])
ids_varios = ge.identificadores(RC, [ge.EDIFICIO, ge.PISCINA, ge.EDIFICIO, ge.PISCINA])
identificadores = (ids_uno == [RC, f'{RC}_Piscina_1']
                   and ids_varios == [f'{RC}_Edificio_1', f'{RC}_Piscina_1', f'{RC}_Edificio_2', f'{RC}_Piscina_2'])

# 2. Escritura y lectura
construcciones = [ge.Construccion(ids_uno[0], cuerpos, ge.EDIFICIO, plantas=2),
                  ge.Construccion(ids_uno[1], piscina, ge.PISCINA)]
ruta = os.path.join(carpeta, 'edificio.gml')
ok, inc = ge.escribir(ruta, construcciones, 25830, datetime.datetime(2026, 10, 9, 9, 25))
with open(ruta, 'rb') as f:
    datos = f.read()
texto = datos.decode('iso-8859-1')
lectura = gl.leer(ruta)
edificio = lectura.elementos[0] if lectura.elementos else None
pisc = lectura.elementos[1] if len(lectura.elementos) > 1 else None
lectura_ok = (ok and all(i.nivel == INFO for i in inc) and lectura.version == 'BU 2.0' and lectura.epsg == 25830 and len(lectura.elementos) == 2
              and edificio.tipo == gl.EDIFICIO and edificio.local_id == RC and edificio.namespace == 'ES.LOCAL.BU'
              and edificio.plantas == 2 and abs(edificio.geometria.area() - (100 - 4 + 16)) < 0.01
              and pisc.local_id == f'{RC}_Piscina_1' and pisc.naturaleza == 'openAirPool'
              and abs(pisc.geometria.area() - 18) < 0.01)
formato = (texto.startswith('<?xml version="1.0" encoding="ISO-8859-1"?>') and 'gml:id="ES.LOCAL.BU"' in texto
           and texto.count('<gml:PolygonPatch>') == 2 and 'srsName="urn:ogc:def:crs:EPSG::25830"' in texto
           and '2026-10-09T09:25:00' in texto and 'herramienta no oficial' in texto
           and '<bu-core2d:conditionOfConstruction>functional</bu-core2d:conditionOfConstruction>' in texto
           and 'xsi:nil="true"' in texto and '421502.00 4070502.00' in texto)
informe = validador.validar(ruta)
errores_validador = [str(i) for i in informe.incidencias if i.nivel == ERROR] if hasattr(informe, 'incidencias') else []
validado = not errores_validador

# 3. Errores previos: no escribe nada
def errores(lista, epsg=25830):
    destino = os.path.join(carpeta, 'mal.gml')
    if os.path.exists(destino):
        os.remove(destino)
    escrito, incidencias = ge.escribir(destino, lista, epsg)
    return [] if escrito or os.path.exists(destino) else codigos([i for i in incidencias if i.nivel == ERROR])


dos_piscinas = QgsGeometry.fromWkt(f"MULTIPOLYGON({rect(X0, Y0, 3, 3)}, {rect(X0 + 10, Y0, 3, 3)})")
casos = {
    'piscina en dos partes': (errores([ge.Construccion(f'{RC}_Piscina_1', dos_piscinas, ge.PISCINA)]), 'BU-PISCINA-PARTES'),
    'estado no válido': (errores([ge.Construccion(RC, piscina, estado='terminado', plantas=1)]), 'BU-ESTADO'),
    'plantas no válidas': (errores([ge.Construccion(RC, piscina, plantas='dos')]), 'BU-PLANTAS'),
    'SRC no admitido': (errores([ge.Construccion(RC, piscina, plantas=1)], 4326), 'SRC-NO-ADMITIDO'),
    'identificador repetido': (errores([ge.Construccion(RC, piscina, plantas=1), ge.Construccion(RC, cuerpos, plantas=1)]),
                               'ID-REPETIDO'),
    'sin construcciones': (errores([]), 'BU-VACIO'),
}
errores_ok = all(codigo in obtenido for obtenido, codigo in casos.values())
_, inc_plantas = ge.construir([ge.Construccion(RC, piscina)], 25830)
sin_plantas = codigos([i for i in inc_plantas if i.nivel == AVISO]) == ['BU-SIN-PLANTAS']

# 4. Esquema XSD (copia de la DGC): válido con conexión o caché; sin ella, «sin comprobar», nunca «válido»
xsd = esquemas.validar(datos, 'BU 2.0')
conexion = 'XSD-SIN-COMPROBAR' not in codigos(xsd) and 'XSD-ESQUEMA' not in codigos(xsd)
esquema_ok = codigos(xsd) == ['XSD-VALIDO'] if conexion else 'XSD-VALIDO' not in codigos(xsd)

checks = {
    "identificadores según el formato de la DGC": identificadores,
    "escribe y el lector lo lee (BU 2.0, recintos, hueco, plantas, piscina)": lectura_ok,
    "formato: ISO-8859-1, PolygonPatch por recinto, srsName urn, fecha y hora": formato,
    "el validador del plugin no da errores": validado,
    "errores previos (no escribe nada)": errores_ok,
    "aviso si faltan las plantas": sin_plantas,
    "esquema XSD " + ("(con conexión): válido" if conexion else "(sin conexión): no dice «válido»"): esquema_ok,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· GML de edificio")
for nombre, ok_ in checks.items():
    print(("  OK   " if ok_ else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'inc': [str(i) for i in inc], 'version': lectura.version,
                        'elementos': [(e.tipo, e.local_id, e.plantas, e.naturaleza, round(e.geometria.area(), 2))
                                      for e in lectura.elementos], 'validador': errores_validador,
                        'casos': {k: v[0] for k, v in casos.items()}, 'plantas': [str(i) for i in inc_plantas],
                        'xsd': [str(i) for i in xsd]})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
