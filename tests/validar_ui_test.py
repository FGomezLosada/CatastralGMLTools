"""
Prueba de la pestaña Validar (parte de lectura): abrir un GML, tabla con su contenido, aviso de superficie que no
coincide, avisos de esquema 3.0 y de fichero mal formado en la barra del panel y carga en el mapa con estilo. Sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py validar_ui_test.py)
"""
import os
import tempfile

import qgis.utils
from qgis.core import Qgis, QgsGeometry, QgsProject
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

qgis.utils.reloadPlugin('catastral_gml_tools')
import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import gml_parcela as gp  # noqa: E402
from catastral_gml_tools.core.info import RAIZ  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))

DATOS = os.path.join(RAIZ, 'tests', 'data', 'gml')
X0, Y0 = 421500.0, 4070500.0
carpeta = tempfile.mkdtemp(prefix='cgt_validar_')


def rect(x, y, a, b):
    return QgsGeometry.fromWkt(f"POLYGON(({x} {y}, {x + a} {y}, {x + a} {y + b}, {x} {y + b}, {x} {y}))")


def texto_barra(barra):
    item = barra.currentItem()
    if item is None:
        return ''
    etiquetas = [e.text() for e in item.findChildren(QLabel) if e.text()]
    return item.text() or (etiquetas[0] if etiquetas else '')


ruta = os.path.join(carpeta, 'segregacion.gml')
gp.escribir(ruta, [gp.ParcelaGML('1907401VK4810H', gp.SDGC, rect(X0, Y0, 20, 30)),
                   gp.ParcelaGML('Nueva_1', gp.LOCAL, rect(X0 + 20, Y0, 15, 30))], 25830)
#Copia con la superficie declarada alterada a mano (600 → 650)
alterado = os.path.join(carpeta, 'alterado.gml')
with open(ruta, encoding='utf-8') as f:
    texto = f.read()
with open(alterado, 'w', encoding='utf-8') as f:
    f.write(texto.replace('<cp:areaValue uom="m2">600</cp:areaValue>', '<cp:areaValue uom="m2">650</cp:areaValue>'))

dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
pv = dw.pestanaValidar
pestana_visible = dw.tabValidarPendiente.isHidden() and pv.parent() is dw.tabValidar and not pv.cargarBoton.isEnabled()

# 1. Abrir un GML correcto
pv.fichero.setFilePath(ruta)
filas = [[pv.tabla.item(i, c).text() for c in range(5)] for i in range(pv.tabla.rowCount())]
tabla_ok = filas == [['Parcela', '1907401VK4810H', 'ES.SDGC.CP', '600', '600'], ['Parcela', 'Nueva_1', 'ES.LOCAL.CP', '450', '450']]
resumen_ok = 'segregacion.gml' in pv.resumen.text() and 'CP 4.0' in pv.resumen.text() and '2 elementos' in pv.resumen.text()
sin_avisos = dw.messageBar.currentItem() is None and pv.cargarBoton.isEnabled()

# 2. Cargar en el mapa: capa con estilo por tipo y etiquetas, sin .gfs
antes = len(QgsProject.instance().mapLayers())
capa = pv.cargarBoton.click() or [c for c in QgsProject.instance().mapLayers().values() if c.name() == 'segregacion']
capa = capa[0] if capa else None
cargada = (capa is not None and len(QgsProject.instance().mapLayers()) == antes + 1 and capa.featureCount() == 2
           and capa.renderer().type() == 'categorizedSymbol' and capa.labelsEnabled()
           and not os.path.exists(os.path.join(carpeta, 'segregacion.gfs')))

# 3. Superficie declarada que no coincide: en rojo
pv.fichero.setFilePath(alterado)
rojo = pv.tabla.item(0, 3).text() == '650' and pv.tabla.item(0, 3).foreground().color() == Qt.GlobalColor.red

# 4. GML 3.0: aviso en la barra
pv.fichero.setFilePath(os.path.join(DATOS, 'parcela_cp30_sintetica.gml'))
aviso30 = ('1 problema' in texto_barra(dw.messageBar) and dw.messageBar.currentItem().level() == Qgis.MessageLevel.Warning
           and pv.tabla.rowCount() == 2)

# 5. Edificio
pv.fichero.setFilePath(os.path.join(DATOS, 'edificio_sintetico.gml'))
tipos = [pv.tabla.item(i, 0).text() for i in range(pv.tabla.rowCount())]
edificio_ok = tipos == ['Edificio', 'Otra construcción'] and 'BU 2.0' in pv.resumen.text()

# 6. Mal formado: error en la barra, tabla vacía y botón desactivado
pv.fichero.setFilePath(os.path.join(DATOS, 'mal_formado.gml'))
mal = (pv.tabla.rowCount() == 0 and not pv.cargarBoton.isEnabled()
       and dw.messageBar.currentItem().level() == Qgis.MessageLevel.Critical)

# 7. Arrastrar y soltar un GML desde el Explorador
from qgis.PyQt.QtCore import QMimeData, QPointF, QUrl  # noqa: E402
from qgis.PyQt.QtGui import QDropEvent  # noqa: E402

mime = QMimeData()
mime.setUrls([QUrl.fromLocalFile(ruta), QUrl.fromLocalFile(os.path.join(carpeta, 'otro.txt'))])
solo_gml = pv.rutas_gml(mime) == [ruta.replace('\\', '/')] or pv.rutas_gml(mime) == [ruta]
evento = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier)
pv.dropEvent(evento)
soltado = (os.path.normpath(pv.fichero.filePath()) == os.path.normpath(ruta) and pv.tabla.rowCount() == 2
           and pv.acceptDrops())
mime_txt = QMimeData()
mime_txt.setUrls([QUrl.fromLocalFile(os.path.join(carpeta, 'otro.txt'))])
ignora_otros = pv.rutas_gml(mime_txt) == []

# 7b. Arrastrar la capa cargada desde el panel de Capas: se abre su GML
from qgis.core import QgsMimeDataUtils  # noqa: E402

pv.fichero.setFilePath(alterado)
mime_capa = QgsMimeDataUtils.encodeUriList([QgsMimeDataUtils.Uri(capa)])
desde_capas = pv.rutas_gml(mime_capa) == [ruta]
pv.dropEvent(QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime_capa, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier))
desde_capas = desde_capas and os.path.normpath(pv.fichero.filePath()) == os.path.normpath(ruta)
leyenda = [c.label() for c in capa.renderer().categories()] == ['Parcela']

# 8. Estilo: relleno naranja casi transparente (no morado opaco)
categorias = capa.renderer().categories() if capa is not None else []  #Se guarda la lista: el símbolo es de la categoría
color = QColor(categorias[0].symbol().color()) if categorias else None
estilo_ok = color is not None and (color.red(), color.green(), color.blue()) == (232, 89, 12) and color.alpha() < 60

for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
dw.deleteLater()

checks = {
    "la pestaña Validar sustituye al texto provisional": pestana_visible,
    "tabla con tipo, identificador, namespace y superficies": tabla_ok,
    "resumen con fichero, esquema y número de elementos": resumen_ok,
    "GML correcto: sin avisos y botón de carga activo": sin_avisos,
    "carga en el mapa con estilo por tipo, etiquetas y sin .gfs": cargada,
    "superficie declarada distinta de la calculada, en rojo": rojo,
    "GML 3.0: aviso de esquema obsoleto": aviso30,
    "GML de edificio: edificio y otra construcción": edificio_ok,
    "GML mal formado: error y nada que cargar": mal,
    "arrastrar un GML a la pestaña lo abre (solo .gml/.xml)": solo_gml and soltado and ignora_otros,
    "arrastrar la capa cargada desde el panel de Capas abre su GML": desde_capas,
    "la leyenda solo muestra los tipos presentes": leyenda,
    "estilo: relleno naranja casi transparente": estilo_ok,
    "ninguna ventana emergente": not ventanas,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· pestaña Validar (lectura)")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'filas': filas, 'resumen': pv.resumen.text(), 'barra': texto_barra(dw.messageBar), 'tipos': tipos,
                        'capa': None if capa is None else (capa.featureCount(), capa.renderer().type()),
                        'color': None if color is None else color.name(QColor.NameFormat.HexArgb) if hasattr(QColor, 'NameFormat') else str(color),
                        'soltado': pv.fichero.filePath()})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
