"""
Batería de casos de la pestaña Parcela (crear el GML desde una capa; plan de pruebas, docs/PLAN_PRUEBAS.md). Cada caso
es una capa como las que traen los usuarios (dibujada a mano, de un DXF, un shape o un GeoPackage, en cualquier SRC, con
geometrías raras) y lo que debe pasar. Dos reglas para todos:

  - si el plugin crea el GML, su propia Validar no le encuentra ningún error (no se entrega un fichero que la Sede
    rechazaría por algo que el plugin sabe ver);
  - si no lo crea, lo explica en el panel (sin ventanas ni trazas de Python).

Uso: tools\\probar.bat (o tools\\run_tests.py parcela_casos_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os
import tempfile
import traceback

import qgis.utils
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import gml_lector as gl  # noqa: E402
from catastral_gml_tools.core import validador  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))
dock_module.CatastralGMLToolsDockWidget.open_path = lambda self, ruta: None

carpeta = tempfile.mkdtemp(prefix='cgt parcela casos ñ_')
X0, Y0 = 421500.0, 4070500.0
RC = '1907401VK4810H'
proyecto = QgsProject.instance()


def rect(x, y, w, h):
    return f"POLYGON(({x} {y}, {x} {y + h}, {x + w} {y + h}, {x + w} {y}, {x} {y}))"


def capa(nombre, filas, crs='EPSG:25830', tipo='Polygon'):
    """Capa de memoria: filas = [(wkt o QgsGeometry o None, refcat)]."""
    c = QgsVectorLayer(f"{tipo}?crs={crs}&field=refcat:string(30)", nombre, "memory")
    entidades = []
    for geometria, rc in filas:
        f = QgsFeature(c.fields())
        if geometria is not None:
            f.setGeometry(geometria if isinstance(geometria, QgsGeometry) else QgsGeometry.fromWkt(geometria))
        f.setAttributes([rc])
        entidades.append(f)
    c.dataProvider().addFeatures(entidades)
    proyecto.addMapLayer(c)
    return c


def en(crs, wkt):
    g = QgsGeometry.fromWkt(wkt)
    g.transform(QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:25830'), QgsCoordinateReferenceSystem(crs), proyecto))
    return g


def a_fichero(c, nombre, driver):
    ruta = os.path.join(carpeta, nombre)
    opciones = QgsVectorFileWriter.SaveVectorOptions()
    opciones.driverName = driver
    QgsVectorFileWriter.writeAsVectorFormatV3(c, ruta, proyecto.transformContext(), opciones)
    extension = {'ESRI Shapefile': '.shp', 'GPKG': '.gpkg'}[driver]
    nueva = QgsVectorLayer(ruta + extension, nombre, 'ogr')
    proyecto.addMapLayer(nueva)
    return nueva


SEG = [(rect(X0, Y0, 20, 18), RC), (rect(X0, Y0 + 18, 20, 12), None)]
CIRCULO = QgsGeometry.fromPointXY(qgis.core.QgsPointXY(X0 + 50, Y0 + 50)).buffer(10, 250)  #1000 vértices

#(nombre, función que devuelve la capa, qué debe pasar: 'crea', 'no crea' o 'cualquiera')
CASOS = [
    ("segregación dibujada en EPSG:25830", lambda: capa('seg', SEG), 'crea'),
    ("en EPSG:4326 (se transforma)", lambda: capa('geo', [(en('EPSG:4326', w), r) for w, r in SEG], 'EPSG:4326'), 'crea'),
    ("en EPSG:3857 (web)", lambda: capa('web', [(en('EPSG:3857', w), r) for w, r in SEG], 'EPSG:3857'), 'crea'),
    ("en ED50 (EPSG:23030)", lambda: capa('ed50', [(en('EPSG:23030', w), r) for w, r in SEG], 'EPSG:23030'), 'crea'),
    ("UTM marcada como 4326 (DXF sin SRC)", lambda: capa('utm4326', SEG, 'EPSG:4326'), 'no crea'),
    ("sin SRC", lambda: capa('sinsrc', SEG, ''), 'no crea'),
    ("capa vacía", lambda: capa('vacia', []), 'no crea'),
    ("una geometría nula entre las buenas", lambda: capa('nula', SEG + [(None, 'X')]), 'no crea', 'bórrelo, o seleccione'),
    ("polígono con hueco", lambda: capa('hueco', [(f"POLYGON(({X0} {Y0}, {X0} {Y0 + 30}, {X0 + 20} {Y0 + 30}, {X0 + 20} {Y0}, "
                                                   f"{X0} {Y0}), ({X0 + 5} {Y0 + 5}, {X0 + 9} {Y0 + 5}, {X0 + 9} {Y0 + 9}, "
                                                   f"{X0 + 5} {Y0 + 9}, {X0 + 5} {Y0 + 5}))", RC)]), 'crea'),
    ("vértices repetidos y sentido antihorario", lambda: capa('repetidos', [(
        f"POLYGON(({X0} {Y0}, {X0 + 20} {Y0}, {X0 + 20} {Y0}, {X0 + 20} {Y0 + 30}, {X0} {Y0 + 30}, {X0} {Y0}))", RC)]), 'crea'),
    ("con Z (PolygonZ)", lambda: capa('z', [(f"POLYGON Z(({X0} {Y0} 10, {X0} {Y0 + 30} 10, {X0 + 20} {Y0 + 30} 11, "
                                            f"{X0 + 20} {Y0} 12, {X0} {Y0} 10))", RC)], tipo='PolygonZ'), 'crea'),
    ("coordenadas con muchos decimales", lambda: capa('decimales', [(rect(X0 + 0.123456, Y0 + 0.987654, 20.333333, 30.111111),
                                                                     RC)]), 'crea'),
    ("círculo de 1000 vértices", lambda: capa('circulo', [(CIRCULO, 'Nueva_1')]), 'crea'),
    ("curva (CurvePolygon)", lambda: capa('curva', [(f"CURVEPOLYGON(CIRCULARSTRING({X0} {Y0}, {X0 + 10} {Y0 + 10}, {X0} {Y0}))",
                                                     'Nueva_1')], tipo='CurvePolygon'), 'cualquiera'),
    ("pajarita (se corta a sí misma)", lambda: capa('pajarita', [(f"POLYGON(({X0} {Y0}, {X0 + 20} {Y0 + 30}, {X0 + 20} {Y0}, "
                                                                  f"{X0} {Y0 + 30}, {X0} {Y0}))", RC)]), 'cualquiera'),
    ("astilla de 0,3 m²", lambda: capa('astilla', [(rect(X0, Y0, 20, 30), RC), (rect(X0 + 20, Y0, 0.01, 30), None)]), 'no crea',
     'es una astilla del dibujo'),
    ("multiparte (finca discontinua)", lambda: capa('multi', [(f"MULTIPOLYGON((({X0} {Y0}, {X0} {Y0 + 5}, {X0 + 5} {Y0 + 5}, "
                                                               f"{X0} {Y0})), (({X0 + 9} {Y0}, {X0 + 9} {Y0 + 3}, "
                                                               f"{X0 + 12} {Y0 + 3}, {X0 + 9} {Y0})))", RC)],
                                                    tipo='MultiPolygon'), 'no crea'),
    ("dos parcelas solapadas", lambda: capa('solape', [(rect(X0, Y0, 20, 30), RC), (rect(X0 + 18, Y0, 20, 30), None)]), 'no crea'),
    ("dos parcelas con un hueco de 5 cm entre ellas", lambda: capa('rendija', [(rect(X0, Y0, 20, 30), RC),
                                                                               (rect(X0 + 20.05, Y0, 20, 30), None)]), 'cualquiera'),
    ("identificadores con espacios, eñes y acentos", lambda: capa('raros', [(rect(X0, Y0, 20, 30), 'Parcela ñ 1'),
                                                                            (rect(X0 + 20, Y0, 20, 30), 'Línea/2')]), 'cualquiera'),
    ("la misma RC en dos parcelas", lambda: capa('repetida', [(rect(X0, Y0, 10, 30), RC), (rect(X0 + 10, Y0, 10, 30), RC)]),
     'crea'),
    #Una RC de parcela (14) no tiene caracteres de control: si está bien escrita pero no existe, lo dirá la comparación
    ("RC inventada con formato correcto", lambda: capa('rcmal', [(rect(X0, Y0, 20, 30), '1907401VK4810A')]), 'crea'),
    ("shape en una carpeta con eñe", lambda: a_fichero(capa('shp_origen', SEG), 'parcelas shape', 'ESRI Shapefile'), 'crea'),
    ("GeoPackage", lambda: a_fichero(capa('gpkg_origen', SEG), 'parcelas', 'GPKG'), 'crea'),
    ("40 parcelas: se crea y avisa de que la Sede no lo tramita sola",
     lambda: capa('cuarenta', [(rect(X0 + (i % 8) * 10, Y0 + (i // 8) * 10, 10, 10), None) for i in range(40)]), 'crea',
     'no tramita automáticamente'),
]

dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
pt = dw.pestanaParcela
resultados, detalles = {}, {}


def barra():
    return ' '.join([item.text() for item in dw.messageBar.items()]
                    + [e.text() for item in dw.messageBar.items() for e in item.findChildren(QLabel)])


for numero, (nombre, fabricar, esperado, *texto_esperado) in enumerate(CASOS, start=1):
    clave = f"{numero:02d}. {nombre}"
    try:
        c = fabricar()
        pt.soloSeleccion.setChecked(False)
        pt.capaCombo.setLayer(c)
        ruta = os.path.join(carpeta, f'caso {numero:02d}.gml')
        pt.destino.setFilePath(ruta)
        dw.messageBar.clearWidgets()
        pt.crear_gml()
        creado = os.path.isfile(ruta)
        mensaje = barra()
        ok = bool(mensaje.strip()) and 'Traceback' not in mensaje and 'Error inesperado' not in mensaje
        errores_propios = []
        if creado:
            informe = validador.validar(ruta)
            errores_propios = [f"{i.codigo}: {i.mensaje[:80]}" for i in informe.errores]
            ok = ok and not errores_propios and bool(gl.leer(ruta).elementos)
        if texto_esperado:
            ok = ok and texto_esperado[0] in mensaje
        if esperado == 'crea':
            ok = ok and creado
        elif esperado == 'no crea':
            ok = ok and not creado
        resultados[clave] = ok
        if not ok:
            detalles[nombre] = (('creado' if creado else 'no creado'), errores_propios[:3], mensaje[:300])
    except Exception:  # noqa: BLE001
        resultados[clave] = False
        detalles[nombre] = traceback.format_exc()[-900:]


#Interacción: la capa se borra con la pestaña abierta; se edita sin guardar; doble clic en «Crear»
def interaccion():
    c = capa('borrable', SEG)
    pt.capaCombo.setLayer(c)
    dw.messageBar.clearWidgets()
    proyecto.removeMapLayer(c.id())
    qgis.PyQt.QtWidgets.QApplication.processEvents()
    #El combo pasa solo a otra capa: se avisa (antes, «Crear GML» hacía el de otra capa sin decir nada)
    borrada = "«borrable» se ha quitado del proyecto" in barra() and 'Compruebe la tabla' in barra()
    #Editando sin guardar: el GML lleva lo que se ve en el mapa
    e = capa('editando', SEG)
    pt.capaCombo.setLayer(e)
    e.startEditing()
    fid = next(iter(e.getFeatures())).id()
    e.changeGeometry(fid, QgsGeometry.fromWkt(rect(X0, Y0, 20, 15)))
    pt.recargar()
    ruta = os.path.join(carpeta, 'editando.gml')
    pt.destino.setFilePath(ruta)
    pt.crear_gml()
    areas = sorted(x.area_declarada for x in gl.leer(ruta).elementos) if os.path.isfile(ruta) else []
    e.rollBack()
    editando = areas == [240, 300]
    #Dos veces seguidas: el segundo sustituye al primero sin fallar
    pt.crear_gml()
    dos_veces = os.path.isfile(ruta) and not validador.validar(ruta).errores
    return borrada and editando and dos_veces


try:
    resultados["capa borrada, editada sin guardar y crear dos veces"] = interaccion()
except Exception:  # noqa: BLE001
    resultados["capa borrada, editada sin guardar y crear dos veces"] = False
    detalles['interacción'] = traceback.format_exc()[-900:]

dw.cleanup()
dw.deleteLater()
proyecto.removeAllMapLayers()
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
resultados["ninguna ventana emergente"] = not ventanas

print("=" * 60)
print("QGIS", Qgis.version(), "· Parcela: batería de casos")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, d in detalles.items():
    print("Detalles", nombre, ":", d)
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
