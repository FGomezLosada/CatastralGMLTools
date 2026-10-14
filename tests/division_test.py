"""
Prueba de la división de parcelas (fase 10, AU-54): core/division.py y el bloque «Dividir la parcela seleccionada» de la
pestaña Parcela. Los cinco modos con la regla del resto del editor de la Sede, errores, dirección paralela o
perpendicular a un lado y desde el lado opuesto, parcela en U, capa en coordenadas geográficas y el flujo completo:
dividir, la tabla y el asistente siguen a la capa, Ctrl+Z y rehacer, GML válido sin solapes ni huecos. Sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py division_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os
import tempfile

import qgis.utils
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsExpression,
    QgsExpressionContext,
    QgsGeometry,
    QgsProject,
)
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import alteraciones as alt  # noqa: E402
from catastral_gml_tools.core import division as dv  # noqa: E402
from catastral_gml_tools.core import geometria as geo  # noqa: E402
from catastral_gml_tools.core import gml_lector as gl  # noqa: E402
from catastral_gml_tools.core import validador as va  # noqa: E402
from catastral_gml_tools.core.incidencias import codigos  # noqa: E402
from catastral_gml_tools.gui import pestana_validar as pv  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))

X0, Y0 = 421500.0, 4070500.0
RC = '2090304VF2629S'
carpeta = tempfile.mkdtemp(prefix='cgt_division_')
#Cuadrilátero irregular de 1080 m²
PARCELA = QgsGeometry.fromWkt(f"POLYGON(({X0} {Y0}, {X0 + 30} {Y0 + 5}, {X0 + 28} {Y0 + 40}, {X0 - 3} {Y0 + 35}, {X0} {Y0}))")
TOTAL = PARCELA.area()


def areas(piezas):
    return [round(p.area(), 2) for p in piezas]


def encaja(piezas):
    """Las piezas cubren la parcela sin solapes ni huecos."""
    union = QgsGeometry.unaryUnion(piezas)
    return (not geo.solapes(piezas) and geo.huecos(piezas) == 0 and abs(union.area() - TOTAL) < 1e-3
            and union.symDifference(PARCELA).area() < 1e-3)


# 1. Modos y regla del resto (editor de la Sede)
p_partes, _ = dv.dividir(PARCELA, dv.PARTES, [3])
p_porc, _ = dv.dividir(PARCELA, dv.PORCENTAJES, [40, 30])         #Suman 70: el 30 % restante es otra parcela
p_sup, _ = dv.dividir(PARCELA, dv.SUPERFICIES, [300, 200])        #El resto (580 m²) es otra parcela
p_cuotas, _ = dv.dividir(PARCELA, dv.CUOTAS, [10, 10, 20])        #= 1 1 2
p_franjas, _ = dv.dividir(PARCELA, dv.FRANJAS, [5, 5])
modos = (areas(p_partes) == [360.0] * 3 and areas(p_porc) == [432.0, 324.0, 324.0]
         and areas(p_sup) == [300.0, 200.0, 580.0] and areas(p_cuotas) == [270.0, 270.0, 540.0]
         and len(p_franjas) == 3 and all(encaja(p) for p in (p_partes, p_porc, p_sup, p_cuotas, p_franjas)))
#Resto menor de 0,5 m²: no da otra parcela, se suma a la última
p_casi, _ = dv.dividir(PARCELA, dv.SUPERFICIES, [500, 579.8])
modos = modos and len(p_casi) == 2 and abs(sum(p.area() for p in p_casi) - TOTAL) < 1e-3

# 2. Errores
errores = {
    'porcentajes > 100': dv.dividir(PARCELA, dv.PORCENTAJES, [60, 50])[1],
    'superficies > total': dv.dividir(PARCELA, dv.SUPERFICIES, [800, 400])[1],
    'más de 100 partes': dv.dividir(PARCELA, dv.PARTES, [101])[1],
    'una parte': dv.dividir(PARCELA, dv.PARTES, [1])[1],
    'partes no entero': dv.dividir(PARCELA, dv.PARTES, [2.5])[1],
    'franjas más anchas que la parcela': dv.dividir(PARCELA, dv.FRANJAS, [30, 30])[1],
    'valor negativo': dv.dividir(PARCELA, dv.CUOTAS, [1, -1])[1],
    'sin valores': dv.dividir(PARCELA, dv.CUOTAS, [])[1],
    'lado inexistente': dv.dividir(PARCELA, dv.PARTES, [2], lado=9)[1],
}
errores_ok = all(inc and inc[0].nivel == 'error' for inc in errores.values())
lectura_ok = (dv.leer_valores("40 30,5;20") == [40, 30.5, 20] and dv.leer_valores("40,30,30") == [40, 30, 30])
try:
    dv.leer_valores("40 treinta")
    lectura_ok = False
except ValueError:
    pass

# 3. Dirección: paralelos al lado 1 (sur) la primera parcela queda al sur; al invertir, al norte; perpendicular, al oeste
sur, _ = dv.dividir(PARCELA, dv.PORCENTAJES, [20], lado=0)
norte, _ = dv.dividir(PARCELA, dv.PORCENTAJES, [20], lado=0, invertir=True)
perpendicular, _ = dv.dividir(PARCELA, dv.PARTES, [2], lado=0, perpendicular=True)
direccion = (sur[0].centroid().asPoint().y() < sur[1].centroid().asPoint().y()
             and norte[0].centroid().asPoint().y() > norte[1].centroid().asPoint().y()
             and abs(sur[0].area() - 216) < 0.01 and abs(norte[0].area() - 216) < 0.01
             and perpendicular[0].centroid().asPoint().x() < perpendicular[1].centroid().asPoint().x()
             and encaja(perpendicular))
#Parcela en U: un lindero recto atraviesa los dos brazos: aviso de parcela en varios trozos
en_u = QgsGeometry.fromWkt(f"POLYGON(({X0} {Y0}, {X0 + 30} {Y0}, {X0 + 30} {Y0 + 30}, {X0 + 20} {Y0 + 30}, {X0 + 20} {Y0 + 10}, "
                           f"{X0 + 10} {Y0 + 10}, {X0 + 10} {Y0 + 30}, {X0} {Y0 + 30}, {X0} {Y0}))")
_, inc_u = dv.dividir(en_u, dv.PORCENTAJES, [80], lado=0)
direccion = direccion and 'DIV-PARTES' in codigos(inc_u)

# 4. Pestaña Parcela: el flujo completo sobre una parcela descargada
iface = qgis.utils.iface
if 'mock' in type(iface).__module__:  #qgis.testing.mocked (unittest.mock o el paquete mock)
    #Interfaz simulada: capa activa de verdad (en QGIS, al añadir una capa pasa a ser la activa)
    _activa = {'capa': None}
    iface.activeLayer = lambda: _activa['capa']
    iface.setActiveLayer = lambda c: _activa.__setitem__('capa', c) or True
dw = dock_module.CatastralGMLToolsDockWidget(iface)
pt = dw.pestanaParcela
bloque = pt.division
dw.tabWidget.setCurrentWidget(dw.tabParcela)
_lectura = gl.ResultadoLectura()
_lectura.epsg = 25830
_lectura.elementos = [gl.ElementoGML(gl.PARCELA, RC, 'ES.SDGC.CP', QgsGeometry(PARCELA), label='04', referencia=RC,
                                     area_declarada=1080)]
capa = gl.capa(_lectura, f'Parcela {RC}')
QgsProject.instance().addMapLayer(capa)
pt.capaCombo.setLayer(capa)
pt.campoId.setField('referencia')
plegado = bloque.isCollapsed() and not bloque.dividirBoton.isEnabled()
bloque.setCollapsed(False)
sin_seleccion = 'Seleccione en el mapa una sola parcela' in bloque.vista.text()
capa.selectAll()
lados_ok = bloque.lado.count() == 4 and bloque.lado.itemText(0).startswith('Lado 1 · 30.41 m')
bloque.modo.setCurrentIndex(dv.MODOS.index(dv.PORCENTAJES))
bloque.valores.setText("60 70")
error_vista = 'no pueden pasar de 100' in bloque.vista.text() and not bloque.dividirBoton.isEnabled()
bloque.valores.setText("50")
vista = ('2 parcelas: 540.00 m² (50 %) · 540.00 m² (50 %)' in bloque.vista.text() and bloque.dividirBoton.isEnabled()
         and bloque.banda is not None and bloque.banda.numberOfVertices() == 2)
#La marca roja solo con la pestaña Parcela a la vista y el panel abierto
dw.tabWidget.setCurrentWidget(dw.tabValidar)
marca = bloque.banda.numberOfVertices() == 0
dw.tabWidget.setCurrentWidget(dw.tabParcela)
marca = marca and bloque.banda.numberOfVertices() == 2
dw.visibilidad_cambiada(False)
marca = marca and bloque.banda.numberOfVertices() == 0
dw.visibilidad_cambiada(True)
marca = marca and bloque.banda.numberOfVertices() == 2
bloque.operacion.setCurrentIndex(0)  #Segregación
fids = bloque.dividir()


def textos_barra():
    item = dw.messageBar.currentItem()
    return ' '.join([item.text()] + [e.text() for e in item.findChildren(QLabel)]) if item is not None else ''


def tabla():
    return sorted((pt.tabla.item(i, 1).text(), pt.namespace_fila(i)) for i in range(pt.tabla.rowCount()))


dividida = (fids is not None and capa.featureCount() == 2 and pt.tipo_alteracion() == alt.SEGREGACION
            and tabla() == sorted([(RC, 'SDGC'), ('Seg_1', 'LOCAL')]) and 'Parcela dividida en 2' in textos_barra()
            and sorted(f['sup_calc'] for f in capa.getFeatures()) == [540, 540]
            and all(not f['sup_gml'] for f in capa.getFeatures() if f.id() != fids[0]))
#Ctrl+Z: una parcela, sin alteración (como estaba); rehacer: otra vez las dos
capa.undoStack().undo()
deshecha = capa.featureCount() == 1 and pt.tipo_alteracion() == alt.SIN_INDICAR and pt.tabla.rowCount() == 1
capa.undoStack().redo()
deshecha = deshecha and capa.featureCount() == 2 and pt.tabla.rowCount() == 2
#El GML: la RC en la matriz y la parcela segregada LOCAL, sin errores (sin solapes ni huecos entre ellas)
pt.alteracion.setCurrentIndex(alt.TIPOS.index(alt.SEGREGACION))
pt.destino.setFilePath(os.path.join(carpeta, 'division.gml'))
pt.crear_gml()
_ruta = os.path.join(carpeta, 'division.gml')
_inf = va.validar(_ruta) if os.path.isfile(_ruta) else None
gml_ok = (_inf is not None and not _inf.errores
          and sorted((e.local_id, e.namespace) for e in _inf.lectura.elementos) == sorted([(RC, 'ES.SDGC.CP'),
                                                                                           ('Seg_1', 'ES.LOCAL.CP')])
          and 'SOLAPE' not in codigos(_inf.incidencias) and 'HUECO' not in codigos(_inf.incidencias))
#Prueba a mano del 14/10: tras validar el GML su vista queda como capa activa; de vuelta en Parcela, la capa de trabajo
#vuelve a ser la activa, así que Ctrl+Z (que actúa en la capa activa) deshace la división y se puede volver a dividir
dw.tabWidget.setCurrentWidget(dw.tabValidar)
_vista = pv.cargar(_inf.lectura, _ruta, iface) if _inf is not None else None
iface.setActiveLayer(_vista)
dw.tabWidget.setCurrentWidget(dw.tabParcela)
activa_ok = iface.activeLayer() is capa
iface.activeLayer().undoStack().undo()
activa_ok = activa_ok and capa.featureCount() == 1 and pt.tabla.rowCount() == 1
#Con dos parcelas seleccionadas el bloque dice qué hacer; la ayuda del modo explica que caben uno o varios porcentajes
capa.undoStack().redo()
capa.selectAll()
activa_ok = activa_ok and 'Hay 2 parcelas seleccionadas' in bloque.vista.text()
capa.undoStack().undo()
bloque.modo.setCurrentIndex(dv.MODOS.index(dv.PORCENTAJES))
activa_ok = activa_ok and 'Uno o varios %' in bloque.ayuda.text() and '«30» da 30 % + 70 %' in bloque.ayuda.text()
if _vista is not None:
    QgsProject.instance().removeMapLayer(_vista.id())
#División en 3 con la operación «División»: todas LOCAL
capa.selectAll()
bloque.modo.setCurrentIndex(dv.MODOS.index(dv.PARTES))
bloque.valores.setText("3")
bloque.operacion.setCurrentIndex(1)
bloque.dividir()
division_op = pt.tipo_alteracion() == alt.DIVISION and tabla() == [('Div_1', 'LOCAL'), ('Div_2', 'LOCAL'), ('Div_3', 'LOCAL')]
capa.rollBack()
#Prueba a mano del 14/10: las parcelas nuevas no copian la referencia catastral (el mapa rotulaba la RC en todas y la
#tabla decía Seg_1…); en una segregación la RC se queda en la mayor, aunque no sea la primera desde el lado elegido
from catastral_gml_tools.gui import estilos  # noqa: E402
estilos.aplicar(capa)
capa.selectAll()
pt.poner_alteracion(alt.SIN_INDICAR, True)
bloque.modo.setCurrentIndex(dv.MODOS.index(dv.PORCENTAJES))
bloque.valores.setText("30")
bloque.operacion.setCurrentIndex(0)
_fids = bloque.dividir() or []
_f = {f.id(): f for f in capa.getFeatures()}
_contexto = QgsExpressionContext()
_expresion = QgsExpression(capa.labeling().settings().fieldName)


def _rotulo(f):
    _contexto.setFeature(f)
    return _expresion.evaluate(_contexto)
_ref = {i: _f[i]['referencia'] for i in _fids}
def _vacio(v):
    return v is None or str(v) in ('', 'NULL')


identidad = (len(_fids) == 2 and _ref[_fids[0]] == RC and _vacio(_ref[_fids[1]])
             and abs(_f[_fids[0]].geometry().area() - 0.7 * TOTAL) < 0.01
             and all(_vacio(_f[i]['localId']) and _vacio(_f[i]['label']) for i in _fids[1:])
             and _rotulo(_f[_fids[0]]) == RC and _rotulo(_f[_fids[1]]) == estilos.ETIQUETA_NUEVA
             and tabla() == sorted([(RC, 'SDGC'), ('Seg_1', 'LOCAL')]) and pt.tipo_alteracion() == alt.SEGREGACION)
capa.rollBack()

# 5. Capa en coordenadas geográficas: se divide en UTM (superficies en m²) y vuelve a la capa
a4326 = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:25830'), QgsCoordinateReferenceSystem('EPSG:4326'),
                               QgsProject.instance())
_g = QgsGeometry(PARCELA)
_g.transform(a4326)
_geo = gl.ResultadoLectura()
_geo.epsg = 4326
_geo.elementos = [gl.ElementoGML(gl.PARCELA, RC, 'ES.SDGC.CP', _g, referencia=RC)]
capa_geo = gl.capa(_geo, 'geograficas')
QgsProject.instance().addMapLayer(capa_geo)
pt.capaCombo.setLayer(capa_geo)
capa_geo.selectAll()
bloque.modo.setCurrentIndex(dv.MODOS.index(dv.PARTES))
bloque.valores.setText("2")
vista_geo = '2 parcelas: 540.00 m² (50 %) · 540.00 m² (50 %)' in bloque.vista.text()
bloque.dividir()
_utm = [geo.transformar(f.geometry(), capa_geo.crs(), 25830).area() for f in capa_geo.getFeatures()]
geograficas = vista_geo and capa_geo.featureCount() == 2 and all(abs(a - 540) < 0.5 for a in _utm)
capa_geo.rollBack()
bloque.soltar()

for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
dw.deleteLater()

checks = {
    "modos: partes, porcentajes, superficies, cuotas y franjas, con la regla del resto": modos,
    "errores: sumas de más, 101 partes, una parte, franjas, negativos, sin valores, lado": errores_ok and lectura_ok,
    "dirección: paralela, desde el lado opuesto, perpendicular; parcela en U con aviso": direccion,
    "bloque plegado y lados de la parcela seleccionada": plegado and sin_seleccion and lados_ok,
    "previsualización: error al momento y superficies antes de dividir": error_vista and vista,
    "marca del lado: se quita al cambiar de pestaña o cerrar el panel": marca,
    "dividir: la capa, la tabla y la segregación propuesta; superficies recalculadas": dividida,
    "Ctrl+Z y rehacer: capa, tabla y alteración": deshecha,
    "GML de la división sin errores, solapes ni huecos": gml_ok,
    "tras validar, de vuelta en Parcela: capa activa, Ctrl+Z y ayuda de los valores": activa_ok,
    "parcelas nuevas sin la referencia catastral (rótulo «(nueva)»); la RC, en la mayor": identidad,
    "operación «División»: todas LOCAL (Div_1…Div_3)": division_op,
    "capa en coordenadas geográficas: se divide en UTM": geograficas,
    "ninguna ventana emergente": not ventanas,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· división de parcelas")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'modos': [areas(p) for p in (p_partes, p_porc, p_sup, p_cuotas, p_franjas, p_casi)],
                        'errores': {k: [str(i) for i in v] for k, v in errores.items()},
                        'lados': [bloque.lado.itemText(i) for i in range(bloque.lado.count())],
                        'vista': bloque.vista.text(), 'barra': textos_barra(), 'tabla': tabla(),
                        'inf': [str(i) for i in _inf.incidencias] if _inf else None, 'utm': _utm})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
