"""
Prueba de la unión de parcelas seleccionadas (mejora 17): capa_parcelas.unir_seleccionadas() y el botón «Unir
seleccionadas» de la pestaña Parcela. Agregación (la mayor conserva su referencia y es el 80 % o más), agrupación,
parcelas no colindantes, deshacer con la pila de edición de QGIS y menos de dos seleccionadas. Sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py union_test.py)
"""
import os
import tempfile

import qgis.utils
from qgis.core import Qgis, QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

qgis.utils.reloadPlugin('catastral_gml_tools')
import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import alteraciones as alt  # noqa: E402
from catastral_gml_tools.core import capa_parcelas as cp  # noqa: E402
from catastral_gml_tools.core.incidencias import codigos  # noqa: E402
from catastral_gml_tools.gui import pestana_parcela as pp  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))

X0, Y0 = 421500.0, 4070500.0
carpeta_union = tempfile.mkdtemp(prefix='cgt_union_')


def rect(x, y, a, b):
    return f"POLYGON(({x} {y}, {x + a} {y}, {x + a} {y + b}, {x} {y + b}, {x} {y}))"


def capa(nombre, filas, tipo='Polygon'):
    c = QgsVectorLayer(f"{tipo}?crs=EPSG:25830&field=refcat:string(20)", nombre, 'memory')
    entidades = []
    for wkt, rc in filas:
        f = QgsFeature(c.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes([rc])
        entidades.append(f)
    c.dataProvider().addFeatures(entidades)
    QgsProject.instance().addMapLayer(c)
    return c


def ids(c, rcs):
    return [f.id() for f in c.getFeatures() if f['refcat'] in rcs]


# 1. Núcleo: agregación (la mayor tiene el 80 %), deshacer, no colindantes, pocas
agregar = capa('agregar', [(rect(X0, Y0, 20, 30), '1907401VK4810H'), (rect(X0 + 20, Y0, 5, 30), '1907402VK4810H'),
                           (rect(X0 + 100, Y0, 10, 10), 'Lejos')])
agregar.selectByIds(ids(agregar, ['1907401VK4810H', '1907402VK4810H']))
fid, tipo, inc = cp.unir_seleccionadas(agregar, 'refcat')
resultante = agregar.getFeature(fid) if fid is not None else None
nucleo = (fid is not None and tipo == alt.AGREGACION and agregar.featureCount() == 2 and agregar.isEditable()
          and resultante['refcat'] == '1907401VK4810H' and abs(resultante.geometry().area() - 750) < 0.01
          and not resultante.geometry().isMultipart() and agregar.selectedFeatureIds() == [fid]
          and codigos(inc) == ['UNION-HECHA', 'UNION-UMBRAL'])  #80 %: guía del IVG sí, quíntuplo del RH no
agregar.undoStack().undo()
deshacer = agregar.featureCount() == 3
agregar.selectByIds(ids(agregar, ['1907401VK4810H', 'Lejos']))
_, _, inc_lejos = cp.unir_seleccionadas(agregar, 'refcat')
agregar.selectByIds(ids(agregar, ['1907401VK4810H']))
_, _, inc_una = cp.unir_seleccionadas(agregar, 'refcat')
errores = (codigos(inc_lejos) == ['UNION-NO-COLINDANTES'] and codigos(inc_una) == ['UNION-POCAS']
           and agregar.featureCount() == 3)
agregar.rollBack()

# Capa de multipolígonos: la geometría unida se guarda como multipolígono
multi = capa('multi', [(rect(X0, Y0, 20, 30).replace('POLYGON((', 'MULTIPOLYGON(((') + ')', 'A'),
                       (rect(X0 + 20, Y0, 20, 30).replace('POLYGON((', 'MULTIPOLYGON(((') + ')', 'B')], 'MultiPolygon')
multi.selectAll()
fid_m, tipo_m, inc_m = cp.unir_seleccionadas(multi, 'refcat')
multipoligono = (fid_m is not None and multi.featureCount() == 1 and tipo_m == alt.SIN_INDICAR  #A y B no son RC: retoque
                 and multi.getFeature(fid_m).geometry().isMultipart() and abs(multi.getFeature(fid_m).geometry().area() - 1200) < 0.01)
multi.rollBack()

# Rendijas de digitalización (AU-42): B empieza 4 mm a la derecha de A (antes «no colindantes») y C deja un hueco de 3 mm
rendija = capa('rendija', [(rect(X0, Y0, 20, 30), 'A'), (rect(X0 + 20.004, Y0, 20, 30), 'B')])
rendija.selectAll()
fid_r, _, inc_r = cp.unir_seleccionadas(rendija, 'refcat')
g_r = rendija.getFeature(fid_r).geometry() if fid_r is not None else QgsGeometry()
hueco = capa('hueco', [(rect(X0, Y0, 20, 30), 'A'),
                       (f"POLYGON(({X0 + 20} {Y0}, {X0 + 40} {Y0}, {X0 + 40} {Y0 + 30}, {X0 + 20} {Y0 + 30}, {X0 + 20} {Y0 + 20}, "
                        f"{X0 + 20.003} {Y0 + 20}, {X0 + 20.003} {Y0 + 10}, {X0 + 20} {Y0 + 10}, {X0 + 20} {Y0}))", 'B')])
hueco.selectAll()
fid_h, _, inc_h = cp.unir_seleccionadas(hueco, 'refcat')
g_h = hueco.getFeature(fid_h).geometry() if fid_h is not None else QgsGeometry()
#Un patio de verdad (2 × 2 m) se conserva
patio = capa('patio', [(f"POLYGON(({X0} {Y0}, {X0 + 20} {Y0}, {X0 + 20} {Y0 + 30}, {X0} {Y0 + 30}, {X0} {Y0}), "
                        f"({X0 + 5} {Y0 + 5}, {X0 + 5} {Y0 + 7}, {X0 + 7} {Y0 + 7}, {X0 + 7} {Y0 + 5}, {X0 + 5} {Y0 + 5}))", 'A'),
                       (rect(X0 + 20, Y0, 20, 30), 'B')])
patio.selectAll()
fid_p, _, inc_p = cp.unir_seleccionadas(patio, 'refcat')
g_p = patio.getFeature(fid_p).geometry() if fid_p is not None else QgsGeometry()
rendijas = (fid_r is not None and 'UNION-RENDIJAS' in codigos(inc_r) and not g_r.isMultipart()
            and abs(g_r.area() - 1200) < 0.2 and fid_h is not None and len(g_h.asPolygon()) == 1
            and 'UNION-RENDIJAS' in codigos(inc_h) and fid_p is not None and len(g_p.asPolygon()) == 2
            and 'UNION-RENDIJAS' not in codigos(inc_p))
#Rendija en cuña de hasta 5 cm (el dibujo no encaja, como en la prueba a mano del 14/10/2026): se une, pero se avisa
cuna = capa('cuna', [(rect(X0, Y0, 20, 30), 'A'),
                     (f"POLYGON(({X0 + 20} {Y0}, {X0 + 40} {Y0}, {X0 + 40} {Y0 + 30}, {X0 + 20} {Y0 + 30}, {X0 + 20.05} {Y0 + 20}, "
                      f"{X0 + 20} {Y0 + 10}, {X0 + 20} {Y0}))", 'B')])
cuna.selectAll()
fid_c, _, inc_c = cp.unir_seleccionadas(cuna, 'refcat')
g_c = cuna.getFeature(fid_c).geometry() if fid_c is not None else QgsGeometry()
#Se rellena la cuña (0,5 m²) y se avisa; la parcela unida queda sin huecos, válida y con la superficie de las dos más la cuña
rendijas = (rendijas and fid_c is not None and 'UNION-RELLENO' in codigos(inc_c) and 'UNION-INVALIDA' not in codigos(inc_c)
            and g_c.isGeosValid() and len(g_c.asPolygon() or g_c.asMultiPolygon()[0]) == 1 and abs(g_c.area() - 1200) < 0.01
            and 'UNION-RELLENO' not in codigos(inc_p) and len(g_p.asPolygon()) == 2)
#Rendija paralela de 0,07 mm abierta al borde (prueba a mano del 14/10/2026): se cierra al ajustar los vértices
paralela = capa('paralela', [(rect(X0, Y0, 20, 30), 'A'),
                             (f"POLYGON(({X0 + 20} {Y0}, {X0 + 40} {Y0}, {X0 + 40} {Y0 + 30}, {X0 + 20.00007} {Y0 + 30}, "
                              f"{X0 + 20} {Y0}))", 'B')])
paralela.selectAll()
fid_l, _, inc_l = cp.unir_seleccionadas(paralela, 'refcat')
g_l = paralela.getFeature(fid_l).geometry() if fid_l is not None else QgsGeometry()
rendijas = rendijas and fid_l is not None and g_l.isGeosValid() and abs(g_l.area() - 1200) < 0.01 and len(g_l.asPolygon() or [0]) == 1
paralela.rollBack()
for _c in (rendija, hueco, patio, cuna):
    _c.rollBack()

# 2. Pestaña Parcela: botón, agrupación propuesta (mitades iguales) y tabla resultante
agrupar = capa('agrupar', [(rect(X0, Y0, 20, 30), '1907401VK4810H'), (rect(X0 + 20, Y0, 20, 30), '1907402VK4810H'),
                           (rect(X0 + 100, Y0, 10, 10), '1907409VK4810H')])  #Otra parcela de la capa, no seleccionada
dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
pt = dw.pestanaParcela
pt.capaCombo.setLayer(agrupar)
desactivado = not pt.unirBoton.isEnabled()
agrupar.selectByIds(ids(agrupar, ['1907401VK4810H', '1907402VK4810H']))
activado = pt.unirBoton.isEnabled()
pt.unirBoton.click()
filas = [(pt.tabla.item(i, pp.COL_ID).text(), pt.namespace_fila(i)) for i in range(pt.tabla.rowCount())]
barra = ' '.join(e.text() for e in dw.messageBar.currentItem().findChildren(QLabel)) if dw.messageBar.currentItem() else ''
interfaz = (desactivado and activado and agrupar.featureCount() == 2 and pt.soloSeleccion.isChecked() and pt.tipo_alteracion() == alt.AGRUPACION
            and filas == [('Agrupa_1', 'LOCAL')] and 'Unidas 2 parcelas en una de 1200 m²' in barra
            and 'propuesta: Agrupación' in barra and 'no llega al 80 %' in barra and not pt.unirBoton.isEnabled()
            and dw.messageBar.currentItem().level() == Qgis.MessageLevel.Success
            and 'Agrupación · 1 parcela (0 SDGC)' in pt.alteracionInfo.text())
agrupar.rollBack()

# 3. El caso de la prueba a mano del 14/10/2026, de principio a fin: parcela descargada, dividida en dos, una franja de vial
#dibujada junto a un trozo y unida a él; la tabla sigue a la capa (también con Ctrl+Z) y nunca pierde la referencia
from catastral_gml_tools.core import gml_lector as gl  # noqa: E402

RC = '2090304VF2629S'
_lectura = gl.ResultadoLectura()
_lectura.epsg = 25830
_lectura.elementos = [gl.ElementoGML(gl.PARCELA, RC, 'ES.SDGC.CP', QgsGeometry.fromWkt(rect(X0, Y0, 10, 11)),
                                     label='04', referencia=RC, area_declarada=110)]
descargada = gl.capa(_lectura, f'Parcela {RC}')
QgsProject.instance().addMapLayer(descargada)
pt.capaCombo.setLayer(descargada)
pt.campoId.setField('referencia')
pt.alteracion.setCurrentIndex(0)  #Sin indicar
descargada.startEditing()
_f0 = next(descargada.getFeatures())
_arriba = QgsGeometry.fromWkt(rect(X0, Y0 + 4.2, 10, 6.8))
_arriba.convertToMultiType()
descargada.changeGeometry(_f0.id(), _arriba)  #Dividir: el trozo de arriba (68 m²) y el de abajo (42 m²) copian la RC
_abajo = QgsFeature(descargada.fields())
_abajo.setAttributes(_f0.attributes())
_g = QgsGeometry.fromWkt(rect(X0, Y0, 10, 4.2))
_g.convertToMultiType()
_abajo.setGeometry(_g)
descargada.addFeature(_abajo)
_vial = QgsFeature(descargada.fields())  #Franja de vial (13 m²) dibujada junto al trozo de abajo
_g = QgsGeometry.fromWkt(rect(X0 + 10, Y0, 3.1, 4.2))
_g.convertToMultiType()
_vial.setGeometry(_g)
descargada.addFeature(_vial)


def textos_barra():
    item = dw.messageBar.currentItem()
    return ' '.join([item.text()] + [e.text() for e in item.findChildren(QLabel)]) if item is not None else ''


def ids_tabla():
    return [(pt.tabla.item(i, pp.COL_ID).text(), pt.namespace_fila(i)) for i in range(pt.tabla.rowCount())]


def fila_de(fid):
    return next(i for i in range(pt.tabla.rowCount()) if pt.tabla.item(i, pp.COL_N).data(Qt.ItemDataRole.UserRole) == fid)


_vial_fid = [f.id() for f in descargada.getFeatures() if not f['referencia']][0]
sigue_capa = sorted(ids_tabla()) == sorted([(RC, 'SDGC'), ('Nueva_1', 'LOCAL'), ('Parcela_2', 'LOCAL')])  #Sin Recargar
deduce = 'la Sede propondrá' in pt.alteracionInfo.text() and not pt.alteracionInfo.isHidden()
#Un nombre escrito a mano se conserva al seguir editando la capa
pt.tabla.item(fila_de(_vial_fid), pp.COL_ID).setText('Vial_1')
_g = QgsGeometry.fromWkt(rect(X0 + 10, Y0, 3.2, 4.2))
_g.convertToMultiType()
descargada.changeGeometry(_vial_fid, _g)
manual = ids_tabla()[fila_de(_vial_fid)] == ('Vial_1', 'LOCAL')
#Un identificador escrito a mano en la fila de la RC: al recargar conserva también su namespace (LOCAL, no SDGC)
_fila_rc = [i for i, t in enumerate(ids_tabla()) if t[0] == RC][0]
_fid_rc = pt.tabla.item(_fila_rc, pp.COL_N).data(Qt.ItemDataRole.UserRole)
pt.tabla.item(_fila_rc, pp.COL_ID).setText('Otra_1')
pt.recargar()
manual = manual and ids_tabla()[fila_de(_fid_rc)] == ('Otra_1', 'LOCAL')
pt.tabla.item(fila_de(_fid_rc), pp.COL_ID).setText(RC)
pt.recargar()
manual = manual and ids_tabla()[fila_de(_fid_rc)] == (RC, 'SDGC')
#Unir el trozo de abajo con la franja: es un retoque del dibujo (una sola RC), no una agrupación
ids_un = [f.id() for f in descargada.getFeatures() if f.geometry().boundingBox().yMaximum() < Y0 + 4.3]
descargada.selectByIds(ids_un)
pt.unir_seleccionadas()
retoque = (descargada.featureCount() == 2 and pt.tipo_alteracion() == alt.SIN_INDICAR and not pt.soloSeleccion.isChecked()
           and sorted(ids_tabla()) == sorted([(RC, 'SDGC'), ('Nueva_1', 'LOCAL')]) and 'retoque del dibujo' in textos_barra())
#Ctrl+Z: la capa y la tabla vuelven a las 3 parcelas
descargada.undoStack().undo()
deshecho = descargada.featureCount() == 3 and len(ids_tabla()) == 3
#Unir dos parcelas catastrales distintas (agregación) y deshacerlo: vuelven la alteración y la casilla de antes
descargada.undoStack().redo()
otra = QgsFeature(descargada.fields())
otra.setAttributes(['parcela', '2090305VF2629S', 'ES.SDGC.CP', '05', '2090305VF2629S', 20, 20, None, '', '', ''])
_g = QgsGeometry.fromWkt(rect(X0 - 2, Y0 + 4.2, 2, 6.8))
_g.convertToMultiType()
otra.setGeometry(_g)
descargada.addFeature(otra)
descargada.selectByIds([f.id() for f in descargada.getFeatures() if f.geometry().boundingBox().yMinimum() > Y0 + 4])
pt.unir_seleccionadas()
agregada = pt.tipo_alteracion() == alt.AGREGACION and pt.soloSeleccion.isChecked()
descargada.undoStack().undo()
agregada = (agregada and pt.tipo_alteracion() == alt.SIN_INDICAR and not pt.soloSeleccion.isChecked()
            and pt.tabla.rowCount() == 3)
#El GML: la RC en el trozo mayor y la parcela nueva LOCAL (segregación con la franja de vial)
descargada.selectByIds([])
pt.destino.setFilePath(os.path.join(carpeta_union, 'caso_real.gml'))
pt.crear_gml()
_gml = gl.leer(os.path.join(carpeta_union, 'caso_real.gml'))
caso_real = (sigue_capa and deduce and manual and retoque and deshecho and agregada
             and sorted((e.local_id, e.namespace) for e in _gml.elementos)
             == sorted([(RC, 'ES.SDGC.CP'), ('Nueva_1', 'ES.LOCAL.CP'), ('2090305VF2629S', 'ES.SDGC.CP')]))
descargada.rollBack()

for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
dw.deleteLater()

checks = {
    "agregación: la mayor conserva sus datos y la geometría unida": nucleo,
    "se deshace con la pila de edición de QGIS": deshacer,
    "errores: no colindantes y una sola seleccionada": errores,
    "capa de multipolígonos": multipoligono,
    "rendijas de menos de 1 cm y cuñas de 5 cm: se cierran (con aviso); un patio se conserva; resultado válido": rendijas,
    "pestaña Parcela: botón, agrupación propuesta y tabla": interfaz,
    "caso real: dividir, dibujar vial, unir (retoque), Ctrl+Z y GML con la RC": caso_real,
    "ninguna ventana emergente": not ventanas,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· unir parcelas seleccionadas")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Caso real:", {'sigue': sigue_capa, 'deduce': deduce, 'manual': manual, 'retoque': retoque, 'deshecho': deshecho,
                         'agregada': agregada, 'tabla': ids_tabla(), 'gml': [(e.local_id, e.namespace) for e in _gml.elementos],
                         'barra': textos_barra()})
    print("Detalles:", {'tipo': tipo, 'inc': [str(i) for i in inc], 'lejos': [str(i) for i in inc_lejos],
                        'una': [str(i) for i in inc_una], 'multi': (tipo_m, [str(i) for i in inc_m]),
                        'filas': filas, 'barra': barra, 'info': pt.alteracionInfo.text()})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
