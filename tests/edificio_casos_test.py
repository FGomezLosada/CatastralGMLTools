"""
Batería de casos de la pestaña Edificio (GML de construcciones para el ICUC; plan de pruebas, docs/PLAN_PRUEBAS.md).
Capas de huellas como las que traen los usuarios (dibujadas, de un DXF con líneas cerradas, en otro SRC, con plantas
mal escritas, solapes, patios, curvas…) con las mismas reglas que Parcela:

  - si crea el GML, la Validar del plugin no le encuentra errores;
  - si no lo crea, lo explica en el panel (sin ventanas ni trazas).

Uso: tools\\probar.bat (o tools\\run_tests.py edificio_casos_test.py)

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
    QgsVectorLayer,
)
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import gml_lector as gl  # noqa: E402
from catastral_gml_tools.core import validador  # noqa: E402
from catastral_gml_tools.gui import pestana_edificio as pe_mod  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))
dock_module.CatastralGMLToolsDockWidget.open_path = lambda self, ruta: None

carpeta = tempfile.mkdtemp(prefix='cgt edificio casos ñ_')
X0, Y0 = 421500.0, 4070500.0
RC = '1907401VK4810H'
proyecto = QgsProject.instance()


def rect(x, y, w, h):
    return f"POLYGON(({x} {y}, {x} {y + h}, {x + w} {y + h}, {x + w} {y}, {x} {y}))"


def capa(nombre, filas, crs='EPSG:25830', tipo='Polygon', tipo_plantas='string(10)'):
    """filas = [(geometría, plantas)]."""
    c = QgsVectorLayer(f"{tipo}?crs={crs}&field=plantas:{tipo_plantas}", nombre, "memory")
    entidades = []
    for geometria, plantas in filas:
        f = QgsFeature(c.fields())
        if geometria is not None:
            f.setGeometry(geometria if isinstance(geometria, QgsGeometry) else QgsGeometry.fromWkt(geometria))
        f.setAttributes([plantas])
        entidades.append(f)
    c.dataProvider().addFeatures(entidades)
    proyecto.addMapLayer(c)
    return c


def en(crs, wkt):
    g = QgsGeometry.fromWkt(wkt)
    g.transform(QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:25830'), QgsCoordinateReferenceSystem(crs), proyecto))
    return g


CASA = [(rect(X0 + 2, Y0 + 2, 8, 6), '2'), (rect(X0 + 12, Y0 + 2, 4, 4), '1')]
CASOS = [
    ("dos edificios en EPSG:25830", lambda: capa('casa', CASA), 'crea'),
    ("en EPSG:4326", lambda: capa('geo', [(en('EPSG:4326', w), p) for w, p in CASA], 'EPSG:4326'), 'crea'),
    ("UTM marcada como 4326", lambda: capa('utm4326', CASA, 'EPSG:4326'), 'no crea'),
    ("sin SRC", lambda: capa('sinsrc', CASA, ''), 'no crea'),
    ("capa vacía", lambda: capa('vacia', []), 'no crea'),
    ("un elemento sin geometría", lambda: capa('nula', CASA + [(None, '1')]), 'cualquiera'),
    ("edificio en dos partes (multiparte)", lambda: capa('dospartes', [(
        f"MULTIPOLYGON((({X0} {Y0}, {X0} {Y0 + 5}, {X0 + 5} {Y0 + 5}, {X0 + 5} {Y0}, {X0} {Y0})), "
        f"(({X0 + 9} {Y0}, {X0 + 9} {Y0 + 3}, {X0 + 12} {Y0 + 3}, {X0 + 12} {Y0}, {X0 + 9} {Y0})))", '2')],
        tipo='MultiPolygon'), 'crea'),
    ("edificio con patio", lambda: capa('patio', [(f"POLYGON(({X0} {Y0}, {X0} {Y0 + 12}, {X0 + 12} {Y0 + 12}, {X0 + 12} {Y0}, "
                                                   f"{X0} {Y0}), ({X0 + 4} {Y0 + 4}, {X0 + 8} {Y0 + 4}, {X0 + 8} {Y0 + 8}, "
                                                   f"{X0 + 4} {Y0 + 8}, {X0 + 4} {Y0 + 4}))", '3')]), 'crea'),
    ("dos edificios solapados", lambda: capa('solape', [(rect(X0, Y0, 10, 10), '1'), (rect(X0 + 8, Y0, 10, 10), '1')]), 'no crea'),
    ("caseta diminuta (0,5 m²)", lambda: capa('caseta', [(rect(X0, Y0, 1, 0.5), '1')]), 'crea'),
    ("plantas con decimales", lambda: capa('decimal', [(rect(X0, Y0, 10, 10), '2,5')]), 'no crea'),
    ("plantas con texto", lambda: capa('texto', [(rect(X0, Y0, 10, 10), 'dos')]), 'cualquiera'),
    ("plantas negativas o cero", lambda: capa('cero', [(rect(X0, Y0, 10, 10), '0'), (rect(X0 + 12, Y0, 5, 5), '-1')]),
     'cualquiera'),
    ("plantas vacías", lambda: capa('vacias', [(rect(X0, Y0, 10, 10), None)]), 'cualquiera'),
    ("plantas en campo numérico", lambda: capa('numerico', [(rect(X0, Y0, 10, 10), 3)], tipo_plantas='integer'), 'crea'),
    ("con Z", lambda: capa('z', [(f"POLYGON Z(({X0} {Y0} 5, {X0} {Y0 + 6} 5, {X0 + 8} {Y0 + 6} 5, {X0 + 8} {Y0} 5, "
                                 f"{X0} {Y0} 5))", '1')], tipo='PolygonZ'), 'crea'),
    ("curva (piscina redonda)", lambda: capa('curva', [(f"CURVEPOLYGON(CIRCULARSTRING({X0} {Y0}, {X0 + 4} {Y0 + 4}, {X0} {Y0}))",
                                                        '1')], tipo='CurvePolygon'), 'cualquiera'),
    ("pajarita", lambda: capa('pajarita', [(f"POLYGON(({X0} {Y0}, {X0 + 10} {Y0 + 10}, {X0 + 10} {Y0}, {X0} {Y0 + 10}, "
                                            f"{X0} {Y0}))", '1')]), 'cualquiera'),
    ("líneas cerradas de un DXF", lambda: capa('dxf', [(f"LINESTRING({X0} {Y0}, {X0} {Y0 + 6}, {X0 + 8} {Y0 + 6}, {X0 + 8} {Y0}, "
                                                        f"{X0} {Y0})", '2'), (f"LINESTRING({X0 + 20} {Y0}, {X0 + 25} {Y0})", '')],
                                                 tipo='LineString'), 'cualquiera'),
    ("70 construcciones", lambda: capa('setenta', [(rect(X0 + (i % 10) * 3, Y0 + (i // 10) * 3, 2, 2), '1') for i in range(70)]),
     'cualquiera'),
]

dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
pe = dw.pestanaEdificio
resultados, detalles = {}, {}


def barra():
    return ' '.join([item.text() for item in dw.messageBar.items()]
                    + [e.text() for item in dw.messageBar.items() for e in item.findChildren(QLabel)])


for numero, (nombre, fabricar, esperado) in enumerate(CASOS, start=1):
    clave = f"{numero:02d}. {nombre}"
    try:
        c = fabricar()
        pe.soloSeleccion.setChecked(False)
        pe.capaCombo.setLayer(c)
        if c.fields().indexOf('plantas') >= 0:
            pe.campoPlantas.setField('plantas')
        pe.referencia.setText(RC)
        ruta = os.path.join(carpeta, f'caso {numero:02d}.gml')
        pe.destino.setFilePath(ruta)
        dw.messageBar.clearWidgets()
        pe.crear_gml()
        creado = os.path.isfile(ruta)
        mensaje = barra()
        ok = bool(mensaje.strip()) and 'Traceback' not in mensaje and 'Error inesperado' not in mensaje
        propios = []
        if creado:
            propios = [f"{i.codigo}: {i.mensaje[:80]}" for i in validador.validar(ruta).errores]
            ok = ok and not propios and bool(gl.leer(ruta).elementos)
        if esperado == 'crea':
            ok = ok and creado
        elif esperado == 'no crea':
            ok = ok and not creado
        resultados[clave] = ok
        if esperado == 'cualquiera':
            print(f"  ({nombre}: {'creado' if creado else 'no creado'} · {mensaje[:170]})")
        if not ok:
            detalles[nombre] = (('creado' if creado else 'no creado'), propios[:3], mensaje[:300])
    except Exception:  # noqa: BLE001
        resultados[clave] = False
        detalles[nombre] = traceback.format_exc()[-900:]

#Sin referencia: no se crea y se pide
try:
    pe.capaCombo.setLayer(capa('sinref', CASA))
    pe.referencia.setText('')
    pe.destino.setFilePath(os.path.join(carpeta, 'sinref.gml'))
    dw.messageBar.clearWidgets()
    pe.crear_gml()
    resultados["sin referencia: se pide, sin fichero"] = (not os.path.exists(os.path.join(carpeta, 'sinref.gml'))
                                                          and 'referencia' in barra())
except Exception:  # noqa: BLE001
    resultados["sin referencia: se pide, sin fichero"] = False
    detalles['sin referencia'] = traceback.format_exc()[-900:]

dw.cleanup()
dw.deleteLater()
proyecto.removeAllMapLayers()
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
resultados["ninguna ventana emergente"] = not ventanas
_ = pe_mod

print("=" * 60)
print("QGIS", Qgis.version(), "· Edificio: batería de casos")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, d in detalles.items():
    print("Detalles", nombre, ":", d)
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
