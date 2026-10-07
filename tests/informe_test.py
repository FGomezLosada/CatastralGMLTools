"""
Prueba de core/informe.py y del botón «Informe» de la pestaña Validar: el HTML se guarda junto al GML, es autocontenido
(sin recursos externos), refleja el resultado, la tabla, las incidencias (con caracteres escapados), el croquis y las
coordenadas, y el botón lo abre. Sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py informe_test.py)
"""
import datetime
import os
import tempfile
from html.parser import HTMLParser

import qgis.utils
from qgis.core import Qgis, QgsGeometry
from qgis.PyQt.QtWidgets import QMessageBox

qgis.utils.reloadPlugin('catastral_gml_tools')
import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
import catastral_gml_tools.gui.pestana_validar as pv_module  # noqa: E402
from catastral_gml_tools.core import gml_parcela as gp  # noqa: E402
from catastral_gml_tools.core import informe  # noqa: E402
from catastral_gml_tools.core import validador as va  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))
abiertos = []
dock_module.CatastralGMLToolsDockWidget.open_path = lambda self, ruta: abiertos.append(ruta)
_validar_xsd = pv_module.esquemas.validar
pv_module.esquemas.validar = lambda datos, version: []

X0, Y0 = 421500.0, 4070500.0
carpeta = tempfile.mkdtemp(prefix='cgt_informe_')


def rect(x, y, a, b, hueco=False):
    wkt = f"(({x} {y}, {x + a} {y}, {x + a} {y + b}, {x} {y + b}, {x} {y})"
    if hueco:
        wkt += f", ({x + 2} {y + 2}, {x + 4} {y + 2}, {x + 4} {y + 4}, {x + 2} {y + 4}, {x + 2} {y + 2})"
    return QgsGeometry.fromWkt("POLYGON" + wkt + ")")


class Etiquetas(HTMLParser):
    """Comprueba que el HTML se puede recorrer y recoge recursos externos (no debe haber)."""

    def __init__(self):
        super().__init__()
        self.externos = []
        self.etiquetas = []

    def handle_starttag(self, tag, attrs):
        self.etiquetas.append(tag)
        for nombre, valor in attrs:
            if nombre in ('src', 'href') and valor and valor.startswith(('http:', 'https:', '//')):
                self.externos.append(valor)


# 1. Informe de un GML correcto (con un hueco)
ruta = os.path.join(carpeta, 'segregacion.gml')
gp.escribir(ruta, [gp.ParcelaGML('1907401VK4810H', gp.SDGC, rect(X0, Y0, 20, 30, hueco=True)),
                   gp.ParcelaGML('Nueva_1', gp.LOCAL, rect(X0 + 20, Y0, 15, 30))], 25830)
inf = va.validar(ruta)
texto = informe.html(inf, ahora=datetime.datetime(2026, 10, 7, 10, 0))
analisis = Etiquetas()
analisis.feed(texto)
contenido = ('segregacion.gml' in texto and 'CP 4.0' in texto and 'EPSG:25830' in texto and '07/10/2026 10:00' in texto
             and 'Sin errores' in texto and 'no oficial' in texto and texto.count('<tr><td>Parcela</td>') == 2
             and '1907401VK4810H' in texto and 'Nueva_1' in texto)
croquis = '<svg' in texto and texto.count('<path') == 2 and 'fill-rule="evenodd"' in texto
coordenadas = ('Hueco 1 · 4 vértices' in texto and 'Exterior · 4 vértices' in texto and '421500.00' in texto
               and texto.count('<details>') == 2)
autocontenido = not analisis.externos and 'table' in analisis.etiquetas and texto.strip().endswith('</html>')

# 2. Informe con errores: resultado en rojo e incidencias escapadas
malo = os.path.join(carpeta, 'malo.gml')
with open(ruta, encoding='utf-8') as f:
    original = f.read()
with open(malo, 'w', encoding='utf-8') as f:
    f.write(original.replace('<localId>Nueva_1</localId>', '<localId>Nueva&lt;1&gt;</localId>')
            .replace('<cp:areaValue uom="m2">450</cp:areaValue>', '<cp:areaValue uom="m2">460</cp:areaValue>'))
inf_malo = va.validar(malo)
texto_malo = informe.html(inf_malo)
errores = ('✖' in texto_malo and 'Con errores' in texto_malo and 'SUP-DISTINTA' in texto_malo
           and 'Nueva&lt;1&gt;' in texto_malo and 'Nueva<1>' not in texto_malo)

# 3. Fichero junto al GML
destino = informe.escribir(inf)
fichero = destino == os.path.join(carpeta, 'segregacion_informe.html') and os.path.isfile(destino)

# 4. Botón «Informe» de la pestaña Validar
dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
pv = dw.pestanaValidar
desactivado = not pv.informeBoton.isEnabled()
pv.fichero.setFilePath(ruta)
pv.esquema_comprobado([])  #Sin esperar a la tarea XSD
os.remove(destino)
pv.informeBoton.click()
boton = (desactivado and os.path.isfile(destino) and abiertos and abiertos[-1] == destino
         and any('Informe guardado: segregacion_informe.html' in e.text()
                 for e in dw.messageBar.currentItem().findChildren(dock_module.QLabel)))

pv_module.esquemas.validar = _validar_xsd
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
dw.deleteLater()

checks = {
    "contenido: fichero, esquema, SRC, fecha, resultado, aviso legal y tabla": contenido,
    "croquis SVG con un trazado por parcela y el hueco": croquis,
    "coordenadas por anillo (exterior y hueco), con 2 decimales": coordenadas,
    "HTML autocontenido, sin recursos de internet": autocontenido,
    "con errores: resultado en rojo, incidencias y texto escapado": errores,
    "se guarda junto al GML como _informe.html": fichero,
    "botón Informe: desactivado sin GML, guarda, abre y avisa": boton,
    "ninguna ventana emergente": not ventanas,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· informe HTML")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'externos': analisis.externos, 'paths': texto.count('<path'), 'abiertos': abiertos,
                        'barra': [e.text() for e in dw.messageBar.currentItem().findChildren(dock_module.QLabel)]
                        if dw.messageBar.currentItem() else None})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
