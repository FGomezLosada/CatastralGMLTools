"""
Prueba de la multiparcela (mejora 16): core/unir.py y la pestaña Utilidades. Une GML sintéticos (dos ficheros con
parcelas distintas y una repetida), rechaza identificadores repetidos con geometría distinta y GML de edificio,
pasa al mismo SRC ficheros de husos distintos y reescribe en 4.0 un GML 3.0. Sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py unir_test.py)
"""
import os
import tempfile

import qgis.utils
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsGeometry
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

qgis.utils.reloadPlugin('catastral_gml_tools')
import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import geometria as geo  # noqa: E402
from catastral_gml_tools.core import gml_lector as gl  # noqa: E402
from catastral_gml_tools.core import gml_parcela as gp  # noqa: E402
from catastral_gml_tools.core import unir as un  # noqa: E402
from catastral_gml_tools.core.incidencias import codigos  # noqa: E402
from catastral_gml_tools.core.info import RAIZ  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))
abiertos = []
dock_module.CatastralGMLToolsDockWidget.open_path = lambda self, ruta: abiertos.append(ruta)

X0, Y0 = 421500.0, 4070500.0
carpeta = tempfile.mkdtemp(prefix='cgt_unir_')


def rect(x, y, a, b):
    return QgsGeometry.fromWkt(f"POLYGON(({x} {y}, {x + a} {y}, {x + a} {y + b}, {x} {y + b}, {x} {y}))")


def gml(nombre, parcelas, epsg=25830):
    ruta = os.path.join(carpeta, nombre)
    gp.escribir(ruta, parcelas, epsg)
    return ruta


a = gml('a.gml', [gp.ParcelaGML('1907401VK4810H', gp.SDGC, rect(X0, Y0, 20, 30)),
                  gp.ParcelaGML('Seg_1', gp.LOCAL, rect(X0 + 20, Y0, 10, 30))])
b = gml('b.gml', [gp.ParcelaGML('1907402VK4810H', gp.SDGC, rect(X0 + 30, Y0, 20, 30)),
                  gp.ParcelaGML('Seg_1', gp.LOCAL, rect(X0 + 20, Y0, 10, 30))])  #Seg_1 repetida, misma geometría
conflicto = gml('c.gml', [gp.ParcelaGML('Seg_1', gp.LOCAL, rect(X0 + 60, Y0, 10, 30))])
#La misma parcela 1907402 en el huso 29
crs30 = QgsCoordinateReferenceSystem('EPSG:25830')
huso29 = gml('d29.gml', [gp.ParcelaGML('1907403VK4810H', gp.SDGC, geo.transformar(rect(X0 + 50, Y0, 20, 30), crs30, 25829))],
             25829)
edificio = os.path.join(RAIZ, 'tests', 'data', 'gml', 'edificio_sintetico.gml')
cp30 = os.path.join(RAIZ, 'tests', 'data', 'gml', 'parcela_cp30_sintetica.gml')

# 1. Unión correcta con una parcela repetida
salida = os.path.join(carpeta, 'multiparcela.gml')
ok, n, inc = un.unir([a, b], salida)
lectura = gl.leer(salida) if ok else None
union = (ok and n == 3 and lectura.version == 'CP 4.0' and lectura.xlink_declarado
         and [e.local_id for e in lectura.elementos] == ['1907401VK4810H', 'Seg_1', '1907402VK4810H']
         and [e.namespace for e in lectura.elementos] == ['ES.SDGC.CP', 'ES.LOCAL.CP', 'ES.SDGC.CP']
         and 'UNIR-REPETIDA' in codigos(inc) and 'UNIR-SEPARADAS' not in codigos(inc) and [e.area_declarada for e in lectura.elementos] == [600, 300, 600])

# 2. Errores: mismo identificador con geometría distinta, GML de edificio, un solo fichero, salida igual a una entrada
ok_c, _, inc_c = un.unir([a, conflicto], os.path.join(carpeta, 'mal.gml'))
ok_e, _, inc_e = un.unir([a, edificio], os.path.join(carpeta, 'mal2.gml'))
ok_1, _, inc_1 = un.unir([a], os.path.join(carpeta, 'mal3.gml'))
ok_d, _, inc_d = un.unir([a, b], a)
errores = (not ok_c and 'UNIR-ID-DISTINTO' in codigos(inc_c) and not ok_e and 'UNIR-NO-PARCELA' in codigos(inc_e)
           and not ok_1 and codigos(inc_1) == ['UNIR-POCOS'] and not ok_d and codigos(inc_d) == ['UNIR-DESTINO']
           and not os.path.exists(os.path.join(carpeta, 'mal.gml')))

# 3. Husos distintos: se pasa al del primer fichero, con aviso
ok_h, n_h, inc_h = un.unir([a, huso29], os.path.join(carpeta, 'husos.gml'))
lectura_h = gl.leer(os.path.join(carpeta, 'husos.gml')) if ok_h else None
husos = (ok_h and n_h == 3 and lectura_h.epsg == 25830 and 'UNIR-SRC' in codigos(inc_h)
         and 'UNIR-SEPARADAS' in codigos(inc_h)
         and abs(lectura_h.elementos[-1].geometria.boundingBox().xMinimum() - (X0 + 50)) < 0.05)

# 4. Un GML 3.0 se reescribe en 4.0
ok_3, n_3, inc_3 = un.unir([cp30, b], os.path.join(carpeta, 'con30.gml'))
version_3 = gl.leer(os.path.join(carpeta, 'con30.gml')).version if ok_3 else ''
cp30_ok = ok_3 and version_3 == 'CP 4.0' and 'UNIR-CP30' in codigos(inc_3)

# 5. Pestaña Utilidades
dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
pu = dw.pestanaUtilidades
integrada = dw.tabUtilidadesPendiente.isHidden() and pu.parent() is dw.tabUtilidades and not pu.unirBoton.isEnabled()
pu.agregar([a, b, a, os.path.join(carpeta, 'no_existe.gml')])
lista = pu.rutas() == [a, b] and pu.unirBoton.isEnabled() and pu.destino.filePath().endswith('multiparcela.gml')
pu.destino.setFilePath(os.path.join(carpeta, 'desde_panel.gml'))
hecho = pu.unir()
barra = ' '.join(e.text() for e in dw.messageBar.currentItem().findChildren(QLabel)) if dw.messageBar.currentItem() else ''
panel = (hecho == os.path.join(carpeta, 'desde_panel.gml') and os.path.isfile(hecho)
         and 'GML unido: desde_panel.gml · 3 parcelas de 2 ficheros' in barra)
pu.validar()
validar = dw.tabWidget.currentWidget() is dw.tabValidar and dw.pestanaValidar.fichero.filePath() == hecho
pu.lista.setCurrentRow(0)
pu.lista.item(0).setSelected(True)
pu.quitar()
quitar = pu.rutas() == [b] and not pu.unirBoton.isEnabled()

for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
dw.deleteLater()

checks = {
    "une dos GML (parcela repetida una vez, namespaces y superficies)": union,
    "errores: id repetido con otra geometría, edificio, un solo fichero, salida = entrada": errores,
    "husos distintos: al SRC del primero, con aviso": husos,
    "un GML 3.0 se reescribe en 4.0": cp30_ok,
    "pestaña Utilidades integrada y lista sin repetidos": integrada and lista,
    "unir desde el panel: fichero y resultado en la barra": panel,
    "botón Validar: abre el GML unido en la pestaña Validar": validar,
    "quitar ficheros de la lista": quitar,
    "ninguna ventana emergente": not ventanas,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· multiparcela (unir GML)")
for nombre, ok_ in checks.items():
    print(("  OK   " if ok_ else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'inc': [str(i) for i in inc], 'c': [str(i) for i in inc_c], 'e': [str(i) for i in inc_e],
                        'h': [str(i) for i in inc_h], '3': [str(i) for i in inc_3], 'barra': barra,
                        'rutas': pu.rutas(), 'union': [(e.local_id, e.namespace, e.area_declarada) for e in lectura.elementos]
                        if lectura else None})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
