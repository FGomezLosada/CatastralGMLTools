"""
Prueba de la unión de parcelas seleccionadas (mejora 17): capa_parcelas.unir_seleccionadas() y el botón «Unir
seleccionadas» de la pestaña Parcela. Agregación (la mayor conserva su referencia y es el 80 % o más), agrupación,
parcelas no colindantes, deshacer con la pila de edición de QGIS y menos de dos seleccionadas. Sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py union_test.py)
"""
import qgis.utils
from qgis.core import Qgis, QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
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
multipoligono = (fid_m is not None and multi.featureCount() == 1 and tipo_m == alt.AGRUPACION
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
    "ninguna ventana emergente": not ventanas,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· unir parcelas seleccionadas")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'tipo': tipo, 'inc': [str(i) for i in inc], 'lejos': [str(i) for i in inc_lejos],
                        'una': [str(i) for i in inc_una], 'multi': (tipo_m, [str(i) for i in inc_m]),
                        'filas': filas, 'barra': barra, 'info': pt.alteracionInfo.text()})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
