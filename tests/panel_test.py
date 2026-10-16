"""
Prueba del panel en pantallas bajas y de la rueda del ratón (prueba a mano del 14/10/2026, segundo monitor):
- el contenido de cada pestaña se desplaza (nada se corta) y la tabla de parcelas no baja de unas cuatro filas;
- la rueda sin foco no cambia las listas (así acabó el identificador en «pos»): desplaza el panel o la tabla;
- si el identificador elegido no tiene referencias catastrales y otro campo sí, se avisa con un enlace para usarlo;
- al quitar la capa elegida, el combo pasa a otra y los campos se proponen para ella;
- las notas de la operación van plegadas y los avisos, a la vista. Sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py panel_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import qgis.utils
from qgis.core import Qgis, QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import QPoint, QPointF, Qt
from qgis.PyQt.QtGui import QWheelEvent
from qgis.PyQt.QtWidgets import QApplication, QLabel, QMessageBox, QScrollArea

import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import alteraciones as alt  # noqa: E402
from catastral_gml_tools.gui import desplazable  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))

RC = '1472010VF2617S'
X0, Y0 = 421180.0, 4066925.0


def capa_gml(nombre):
    """Como una capa de un GML de la Sede abierta con QGIS: nationalCadastralReference y pos (punto de referencia)."""
    capa = QgsVectorLayer("MultiPolygon?crs=EPSG:25830&field=localId:string&field=nationalCadastralReference:string"
                          "&field=pos:string", nombre, 'memory')
    entidades = []
    for ref, x in ((RC, X0), ("Seg_1", X0 + 30)):
        f = QgsFeature(capa.fields())
        f.setGeometry(QgsGeometry.fromWkt(f"MULTIPOLYGON((({x} {Y0}, {x + 30} {Y0}, {x + 30} {Y0 + 20}, {x} {Y0 + 20}, {x} {Y0})))"))
        f.setAttributes([ref, ref, f"{x + 15:.2f} {Y0 + 10:.2f}"])
        entidades.append(f)
    capa.dataProvider().addFeatures(entidades)
    return capa


def rueda(widget, abajo=True):
    centro = QPointF(widget.width() / 2, widget.height() / 2)
    evento = QWheelEvent(centro, QPointF(widget.mapToGlobal(centro.toPoint())), QPoint(0, 0),
                         QPoint(0, -120 if abajo else 120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                         Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, evento)


dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
pt = dw.pestanaParcela
proyecto = QgsProject.instance()

# 1. Contenido desplazable en todas las pestañas; tabla con alto mínimo
#Solo Parcela (la larga) se desplaza si no cabe; las demás, sin zona desplazable (con ella parecían una página web: 15/10)
otras = (dw.pestanaDescargar, dw.pestanaEdificio, dw.pestanaValidar, dw.pestanaUtilidades)
desplazables = (isinstance(pt.parentWidget().parentWidget(), QScrollArea)
                and not any(isinstance(p.parentWidget().parentWidget(), QScrollArea) for p in otras))
#Utilidades: lista numerada, una abierta cada vez, sin la línea descriptiva; mensajes con las notas recortadas
caja = dw.pestanaUtilidades.utilidades
utilidades = ([caja.itemText(i) for i in range(caja.count())][:2] == ["1. Unir GML (multiparcela)", "2. Convertir a 4.0 o reparar"]
              and caja.count() == 3 and caja.itemText(2) == "3. Informe de superficies y coordenadas"
              and dw.tabUtilidadesInfo.isHidden())
_mensaje = dw.success("Prueba", notas=['a', 'b', 'c', 'd'])
utilidades = utilidades and '… y 2 más' in ' '.join(e.text() for e in _mensaje.findChildren(QLabel))
dw.messageBar.clearWidgets()
alto_tabla = pt.tabla.minimumHeight() >= desplazable.ALTO_MINIMO_TABLA

# 2. La rueda sin foco no cambia el identificador ni el modo de división
a = capa_gml('A')
b = capa_gml('B')
proyecto.addMapLayers([a, b])
pt.capaCombo.setLayer(a)
campo_inicial = pt.campoId.currentField()
rueda(pt.campoId)
rueda(pt.campoId)
rueda(pt.division.modo)
rueda_ok = (campo_inicial == 'nationalCadastralReference' and pt.campoId.currentField() == campo_inicial
            and pt.division.modo.currentIndex() == 0
            and pt.campoId.focusPolicy() == Qt.FocusPolicy.StrongFocus
            and all(pt.tabla.cellWidget(i, 2).property('cgt_rueda') for i in range(pt.tabla.rowCount())))

# 3. Identificador sin referencias catastrales (p. ej. «pos») y otro campo con ellas: aviso con enlace para usarlo
pt.campoId.setField('pos')
aviso_campo = 'Usar «localId»' in pt.resumen.text() or 'Usar «nationalCadastralReference»' in pt.resumen.text()
pt.enlace_resumen('campo:nationalCadastralReference')
filas = sorted(pt.tabla.item(i, 1).text() for i in range(pt.tabla.rowCount()))
aviso_campo = (aviso_campo and pt.campoId.currentField() == 'nationalCadastralReference' and filas == sorted([RC, 'Seg_1'])
               and 'Usar «' not in pt.resumen.text())

# 4. Se quita la capa elegida: el combo pasa a otra y sus campos se proponen
proyecto.removeMapLayer(a.id())
QApplication.processEvents()
quitada = pt.capa() is b and pt.campoId.layer() is b and pt.campoId.currentField() == 'nationalCadastralReference'

# 5. Notas de la operación plegadas; avisos a la vista
pt.alteracion.setCurrentIndex(alt.TIPOS.index(alt.SEGREGACION))
texto = pt.alteracionInfo.text()
notas = 'notas sobre la operación' in texto and 'licencia' not in texto
pt.alternar_notas()
notas = notas and 'licencia' in pt.alteracionInfo.text() and 'Ocultar las notas' in pt.alteracionInfo.text()
pt.alternar_notas()

proyecto.removeMapLayer(b.id())
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
dw.deleteLater()

checks = {
    "Parcela se desplaza si no cabe (las demás no); la tabla no se aplasta": desplazables and alto_tabla,
    "Utilidades numeradas, una abierta cada vez; notas del mensaje recortadas": utilidades,
    "la rueda sin foco no cambia listas (identificador, modo, namespace)": rueda_ok,
    "identificador sin RC y otro campo con ellas: aviso y enlace para usarlo": aviso_campo,
    "al quitar la capa elegida, los campos se proponen para la siguiente": quitada,
    "notas de la operación plegadas; se abren y cierran con el enlace": notas,
    "ninguna ventana emergente": not ventanas,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· panel en pantallas bajas y rueda del ratón")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'campo': (campo_inicial, pt.campoId.currentField()), 'modo': pt.division.modo.currentIndex(),
                        'resumen': pt.resumen.text(), 'filas': filas, 'quitada': (pt.capa(), pt.campoId.layer()),
                        'texto': texto})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
