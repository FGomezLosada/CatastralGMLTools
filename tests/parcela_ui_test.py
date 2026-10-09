"""
Prueba de la pestaña Parcela: capa de memoria con parcelas inventadas, tabla, namespaces propuestos, edición de la tabla,
creación del GML, transformación de SRC, errores en la barra del panel y botones del resultado. Sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py parcela_ui_test.py)
"""
import os
import tempfile
import xml.etree.ElementTree as ET

import qgis.utils
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QDate, QDateTime, QTime
from qgis.PyQt.QtWidgets import QLabel, QMessageBox, QPushButton

qgis.utils.reloadPlugin('catastral_gml_tools')
import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.gui import pestana_parcela as pp  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))
abiertos = []
dock_module.CatastralGMLToolsDockWidget.open_path = lambda self, ruta: abiertos.append(ruta)  #Sin abrir el explorador

X0, Y0 = 421500.0, 4070500.0
NS = {'wfs': 'http://www.opengis.net/wfs/2.0', 'cp': 'http://inspire.ec.europa.eu/schemas/cp/4.0',
      'gml': 'http://www.opengis.net/gml/3.2', 'base': 'http://inspire.ec.europa.eu/schemas/base/3.3'}


def capa_parcelas(nombre, crs, filas):
    """Capa de memoria con campos refcat y num, y una parcela por fila (wkt, refcat, num)."""
    #Campos en la URI: vale igual en QGIS 3 (QVariant) y en QGIS 4 (QMetaType)
    capa = QgsVectorLayer(f"Polygon?crs={crs}&field=refcat:string(20)&field=num:string(10)", nombre, "memory")
    entidades = []
    for wkt, rc, num in filas:
        f = QgsFeature(capa.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes([rc, num])
        entidades.append(f)
    capa.dataProvider().addFeatures(entidades)
    QgsProject.instance().addMapLayer(capa)
    return capa


def rect(x, y, a, b):
    return f"POLYGON(({x} {y}, {x + a} {y}, {x + a} {y + b}, {x} {y + b}, {x} {y}))"


def texto_barra(barra):
    item = barra.currentItem()
    if item is None:
        return ''
    etiquetas = [e.text() for e in item.findChildren(QLabel) if e.text()]
    return item.text() or (etiquetas[0] if etiquetas else '')


segregacion = capa_parcelas('segregacion', 'EPSG:25830', [
    (rect(X0, Y0, 20, 30), '1907401VK4810H', None),
    (rect(X0 + 20, Y0, 10, 30), None, None),
    (rect(X0 + 30, Y0, 15, 30), 'Seg 2', '7'),
])
carpeta = tempfile.mkdtemp(prefix='cgt_ui_')

dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
pt = dw.pestanaParcela
pestana_visible = dw.tabParcelaPendiente.isHidden() and pt.parent() is dw.tabParcela

# 1. Al elegir la capa: campo refcat propuesto, filas, namespaces y superficies
pt.capaCombo.setLayer(segregacion)
campo_propuesto = pt.campoId.currentField() == 'refcat'
ids = [pt.tabla.item(i, pp.COL_ID).text() for i in range(pt.tabla.rowCount())]
nss = [pt.namespace_fila(i) for i in range(pt.tabla.rowCount())]
labels = [pt.tabla.item(i, pp.COL_LABEL).text() for i in range(pt.tabla.rowCount())]
areas = [pt.tabla.item(i, pp.COL_AREA).text() for i in range(pt.tabla.rowCount())]
tabla_ok = (ids == ['1907401VK4810H', 'Parcela_2', 'Seg_2'] and nss == ['SDGC', 'LOCAL', 'LOCAL']
            and labels == ['01', 'Parcela_2', 'Seg_2'] and areas == ['600', '300', '450'] and 'EPSG:25830' in pt.resumen.text())
pt.campoLabel.setField('num')
label_campo = pt.tabla.item(2, pp.COL_LABEL).text() == '7'

# 2. El usuario cambia el identificador de la fila 2 y crea el GML
pt.tabla.item(1, pp.COL_ID).setText('Seg_1')
label_renombrado = pt.tabla.item(1, pp.COL_LABEL).text() == 'Seg_1' and pt.namespace_fila(1) == 'LOCAL'
pt.tabla.item(2, pp.COL_ID).setText('Seg_2')
label_respetado = pt.tabla.item(2, pp.COL_LABEL).text() == '7'  #Lo puso el usuario (campo num): no se toca
area_tabla = [pt.tabla.item(i, pp.COL_AREA).text() for i in range(pt.tabla.rowCount())]
pt.fecha.setDateTime(QDateTime(QDate(2026, 10, 1), QTime(9, 30)))
ruta = os.path.join(carpeta, 'segregacion.gml')
pt.destino.setFilePath(ruta)
pt.crear_gml()
creado = os.path.isfile(ruta)
raiz = ET.parse(ruta).getroot() if creado else None
locales = [e.text for e in raiz.iter(f"{{{NS['base']}}}localId")] if raiz is not None else []
labels_gml = [e.text for e in raiz.iter(f"{{{NS['cp']}}}label")] if raiz is not None else []
areas_gml = [e.text for e in raiz.iter(f"{{{NS['cp']}}}areaValue")] if raiz is not None else []
fecha_gml = raiz.find('.//cp:beginLifespanVersion', NS).text if raiz is not None else ''
resultado = texto_barra(dw.messageBar)
item = dw.messageBar.currentItem()
botones = [b.text() for b in item.findChildren(QPushButton)] if item is not None else []
gml_ok = (creado and locales == ['1907401VK4810H', 'Seg_1', 'Seg_2'] and fecha_gml == '2026-10-01T09:30:00'
          and labels_gml == ['01', 'Seg_1', '7'] and areas_gml == area_tabla)
barra_ok = ('GML creado: segregacion.gml' in resultado and '3 parcelas' in resultado and botones == ['Abrir carpeta', 'Cargar en el mapa']
            and item.level() == Qgis.MessageLevel.Success)
estados = [pt.tabla.item(i, pp.COL_ESTADO).text() for i in range(3)] == ['Correcta'] * 3

# 3. Botones del resultado
item.findChildren(QPushButton)[0].click()
carpeta_abierta = abiertos == [carpeta]
capa_gml = pt.cargar_en_mapa()
cargada = capa_gml is not None and capa_gml.isValid() and capa_gml.featureCount() == 3

# 4. Capa en EPSG:4326: se transforma automáticamente a 25830 con la misma superficie
a4326 = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:25830'), QgsCoordinateReferenceSystem('EPSG:4326'),
                               QgsProject.instance())
g = QgsGeometry.fromWkt(rect(X0, Y0, 20, 30))
g.transform(a4326)
geograficas = capa_parcelas('geograficas', 'EPSG:4326', [(g.asWkt(12), 'Nueva', None)])
pt.capaCombo.setLayer(geograficas)
ruta2 = os.path.join(carpeta, 'geograficas')  #Sin extensión: se añade .gml
pt.destino.setFilePath(ruta2)
pt.crear_gml()
raiz2 = ET.parse(ruta2 + '.gml').getroot() if os.path.isfile(ruta2 + '.gml') else None
srs2 = {e.get('srsName') for e in raiz2.iter() if e.get('srsName')} if raiz2 is not None else set()
area2 = raiz2.find('.//cp:areaValue', NS).text if raiz2 is not None else ''
transformado = (srs2 == {'http://www.opengis.net/def/crs/EPSG/0/25830'} and area2 == '600'
                and 'se transforma desde EPSG:4326' in pt.resumen.text())

# 5. Errores: multiparte y SDGC sin RC → no se crea el fichero y se explica en la barra
multi = capa_parcelas('multi', 'EPSG:25830', [
    (f"MULTIPOLYGON((({X0} {Y0}, {X0 + 5} {Y0}, {X0 + 5} {Y0 + 5}, {X0} {Y0})), "
     f"(({X0 + 9} {Y0}, {X0 + 12} {Y0}, {X0 + 12} {Y0 + 3}, {X0 + 9} {Y0})))", 'Discontinua', None),
    (rect(X0, Y0 + 50, 10, 10), 'Seg_9', None),
])
pt.capaCombo.setLayer(multi)
estado_previo = pt.tabla.item(0, pp.COL_ESTADO).text()
pt.tabla.cellWidget(1, pp.COL_NS).setCurrentText('SDGC')
ruta3 = os.path.join(carpeta, 'multi.gml')
pt.destino.setFilePath(ruta3)
pt.crear_gml()
error_barra = texto_barra(dw.messageBar)
errores_ok = (not os.path.exists(ruta3) and error_barra.startswith('No se ha creado el GML')
              and dw.messageBar.currentItem().level() == Qgis.MessageLevel.Critical and estado_previo == 'Varias partes'
              and 'recinto' in pt.tabla.item(0, pp.COL_ESTADO).text()
              and 'SDGC' in pt.tabla.item(1, pp.COL_ESTADO).text())

# 6. Sin fichero de destino y solo seleccionados sin selección
pt.destino.setFilePath('')
pt.crear_gml()
sin_destino = texto_barra(dw.messageBar) == 'Indique el fichero GML de salida'
pt.soloSeleccion.setChecked(True)
sin_seleccion = pt.tabla.rowCount() == 0 and 'seleccionado' in pt.resumen.text()
multi.selectByIds([list(multi.allFeatureIds())[1]])
pt.recargar()
con_seleccion = pt.tabla.rowCount() == 1

# 7. Capa grande (un municipio entero): no se carga entera ni bloquea; se trabaja con la selección
import time  # noqa: E402

grande = capa_parcelas('municipio', 'EPSG:25830', [(rect(X0 + (i % 20) * 12, Y0 + 200 + (i // 20) * 12, 10, 10), None, None)
                                                   for i in range(400)])
pt.soloSeleccion.setChecked(False)
llamadas = []
_recargar = pp.PestanaParcela.recargar
pp.PestanaParcela.recargar = lambda self, *a: (llamadas.append(1), _recargar(self, *a))[1]
inicio = time.time()
pt.capaCombo.setLayer(grande)
segundos = time.time() - inicio
una_vez = len(llamadas) == 1
pp.PestanaParcela.recargar = _recargar
grande_ok = (pt.tabla.rowCount() == 0 and 'tiene 400 parcelas' in pt.resumen.text() and segundos < 2)
pt.crear_gml()
aviso_grande = texto_barra(dw.messageBar).startswith('Demasiadas parcelas')
ids_grande = list(grande.allFeatureIds())
grande.selectByIds(ids_grande[:2])
pt.capaCombo.setLayer(segregacion)
pt.capaCombo.setLayer(grande)  #Con selección: se marca «Solo los elementos seleccionados» y salen las 2
auto_seleccion = pt.soloSeleccion.isChecked() and pt.tabla.rowCount() == 2
grande.selectByIds(ids_grande[:3])  #Al seleccionar en el mapa, la tabla se actualiza sola
sigue_seleccion = pt.tabla.rowCount() == 3

# 8. Parcela dividida: los dos trozos copian la misma RC → el mayor la conserva y el otro se propone como Nueva_1
dividida = capa_parcelas('Parcela dividida — prueba', 'EPSG:25830', [
    (rect(X0, Y0 + 400, 10, 30), '1907401VK4810H', None),
    (rect(X0 + 10, Y0 + 400, 20, 30), '1907401VK4810H', None),
])
pt.soloSeleccion.setChecked(False)
pt.destino.setFilePath('')
pt.destino_automatico = ''
pt.capaCombo.setLayer(dividida)
ids_div = [pt.tabla.item(i, pp.COL_ID).text() for i in range(pt.tabla.rowCount())]
nss_div = [pt.namespace_fila(i) for i in range(pt.tabla.rowCount())]
labels_div = [pt.tabla.item(i, pp.COL_LABEL).text() for i in range(pt.tabla.rowCount())]
division_ok = ids_div == ['Nueva_1', '1907401VK4810H'] and nss_div == ['LOCAL', 'SDGC'] and labels_div == ['Nueva_1', '01']
fichero_propuesto = os.path.basename(pt.destino.filePath()) == 'Parcela_dividida_prueba.gml'
pt.capaCombo.setLayer(segregacion)
sigue_capa = os.path.basename(pt.destino.filePath()) == 'segregacion.gml'
mio = os.path.join(carpeta, 'mi_fichero.gml')
pt.destino.setFilePath(mio)
pt.capaCombo.setLayer(dividida)
respeta_mio = pt.destino.filePath() == mio

for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
dw.deleteLater()

from qgis.PyQt.QtWidgets import QHeaderView  # noqa: E402

columnas = (all(pt.tabla.horizontalHeader().sectionResizeMode(c) == QHeaderView.ResizeMode.Interactive
                for c in range(pt.tabla.columnCount()))
            and pt.tabla.columnWidth(pp.COL_ID) >= 130 and pt.fecha.displayFormat() == 'dd/MM/yyyy HH:mm')
checks = {
    "columnas que se pueden ensanchar a mano y fecha con hora": columnas,
    "la pestaña Parcela sustituye al texto provisional": pestana_visible,
    "propone el campo refcat": campo_propuesto,
    "tabla: identificadores, namespaces, nº de parcela y superficies": tabla_ok,
    "nº de parcela tomado de un campo": label_campo,
    "al cambiar el identificador se recalculan namespace y nº de parcela": label_renombrado,
    "el nº de parcela escrito por el usuario se respeta": label_respetado,
    "crea el GML con los cambios de la tabla, la fecha y la misma superficie que muestra la tabla": gml_ok,
    "resultado en la barra del panel con botones": barra_ok,
    "estado «Correcta» en todas las filas": estados,
    "botón Abrir carpeta": carpeta_abierta,
    "cargar el GML creado en el mapa": cargada,
    "capa en EPSG:4326: transforma a 25830 y añade .gml": transformado,
    "errores: no crea el fichero y los marca en la tabla y la barra": errores_ok,
    "aviso si falta el fichero de destino": sin_destino,
    "solo los elementos seleccionados": sin_seleccion and con_seleccion,
    "capa de 400 parcelas: no se carga entera, avisa y tarda menos de 2 s": grande_ok and aviso_grande,
    "al cambiar de capa la tabla se calcula una sola vez": una_vez,
    "capa grande con selección: usa la selección automáticamente": auto_seleccion,
    "la tabla sigue la selección del mapa": sigue_seleccion,
    "parcela dividida: el trozo mayor conserva la RC y el otro se propone como Nueva_1 (sin presuponer la alteración)": division_ok,
    "fichero propuesto con el nombre de la capa, sin espacios ni símbolos": fichero_propuesto,
    "el fichero propuesto cambia con la capa": sigue_capa,
    "el fichero elegido por el usuario se respeta": respeta_mio,
    "ninguna ventana emergente": not ventanas,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· pestaña Parcela")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'ids': ids, 'nss': nss, 'labels': labels, 'areas': areas, 'resumen': pt.resumen.text(),
                        'locales': locales, 'labels_gml': labels_gml, 'areas_gml': areas_gml, 'area_tabla': area_tabla, 'resultado': resultado, 'botones': botones, 'srs2': srs2, 'area2': area2,
                        'error_barra': error_barra[:200], 'estado_previo': estado_previo,
                        'estados3': [pt.tabla.item(i, pp.COL_ESTADO).text() for i in range(pt.tabla.rowCount())],
                        'abiertos': abiertos, 'ventanas': ventanas,
                        'grande': (pt.resumen.text(), segundos, len(llamadas)),
                        'division': (ids_div, nss_div, labels_div), 'fichero': pt.destino.filePath()})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
