"""
Batería de «Puntos de apoyo para el editor de la Sede» (Utilidades «7.», mejora 33): capas de puntos, líneas y polígonos,
solo la selección, coordenadas geográficas, puntos repetidos, redondeo al centímetro, formato del TXT, capa vacía y
demasiados puntos. Datos sintéticos, sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py apoyo_casos_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os
import re
import tempfile
import traceback

import qgis.utils
from qgis.core import Qgis, QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

qgis.utils.reloadPlugin('catastral_gml_tools')
import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import apoyo as ap  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))
dock_module.CatastralGMLToolsDockWidget.open_path = lambda self, ruta: None

X0, Y0 = 421500.0, 4070500.0
carpeta = tempfile.mkdtemp(prefix='cgt apoyo ñ_')
resultados, detalles = {}, {}
LINEA = re.compile(r'^\d+\.\d{2} \d+\.\d{2}$')


def caso(nombre, funcion):
    try:
        ok, detalle = funcion()
        resultados[nombre] = bool(ok)
        if not ok:
            detalles[nombre] = detalle
    except Exception:  # noqa: BLE001
        resultados[nombre] = False
        detalles[nombre] = traceback.format_exc()[-900:]


def capa(tipo, wkts, crs='EPSG:25830', nombre='Prueba'):
    c = QgsVectorLayer(f"{tipo}?crs={crs}", nombre, "memory")
    for w in wkts:
        f = QgsFeature(c.fields())
        f.setGeometry(QgsGeometry.fromWkt(w))
        c.dataProvider().addFeature(f)
    QgsProject.instance().addMapLayer(c)
    return c


dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
pu = dw.pestanaUtilidades
bloque = pu.apoyo
pu.utilidades.setCurrentWidget(bloque)


def barra():
    item = dw.messageBar.currentItem()
    return ' '.join([item.text()] + [e.text() for e in item.findChildren(QLabel)]) if item is not None else ''


def leer(ruta):
    with open(ruta, 'rb') as f:
        crudo = f.read()
    return crudo, crudo.decode('ascii').splitlines()


def puntos_levantamiento():
    c = capa('Point', [f'POINT({X0 + i * 1.234} {Y0 + i * 2.345})' for i in range(5)] + [f'POINT({X0} {Y0})'],
             nombre='Levantamiento ñ')
    bloque.capa.setLayer(c)
    ruta = os.path.join(carpeta, 'levantamiento.txt')
    bloque.destino.setFilePath(ruta)
    hecho = bloque.crear()
    crudo, lineas = leer(ruta)
    ok = (hecho == ruta and len(lineas) == 5 and all(LINEA.match(x) for x in lineas)
          and lineas[1] == f"{X0 + 1.23:.2f} {Y0 + 2.35:.2f}" and b'\r' not in crudo and crudo.endswith(b'\n')
          and 'Puntos de apoyo: levantamiento.txt · 5 puntos · EPSG:25830' in barra())
    QgsProject.instance().removeMapLayer(c.id())
    return ok, (lineas[:3], barra()[:150])


caso("puntos de un levantamiento: uno por línea, «x y» con 2 decimales, sin repetir", puntos_levantamiento)


def poligonos_y_lineas():
    pol = capa('Polygon', [f'POLYGON(({X0} {Y0}, {X0 + 20} {Y0}, {X0 + 20} {Y0 + 30}, {X0} {Y0 + 30}, {X0} {Y0}))',
                           f'POLYGON(({X0 + 20} {Y0}, {X0 + 40} {Y0}, {X0 + 40} {Y0 + 30}, {X0 + 20} {Y0 + 30}, '
                           f'{X0 + 20} {Y0}))'])
    bloque.capa.setLayer(pol)
    #Dos parcelas que comparten un lado: 6 vértices distintos, sin repetir el de cierre ni los comunes
    n_pol = len(ap.puntos(bloque.geometrias()[0]))
    lin = capa('LineString', [f'LINESTRING({X0} {Y0}, {X0 + 5} {Y0 + 5}, {X0 + 10} {Y0})'])
    bloque.capa.setLayer(lin)
    n_lin = len(ap.puntos(bloque.geometrias()[0]))
    for c in (pol, lin):
        QgsProject.instance().removeMapLayer(c.id())
    return n_pol == 6 and n_lin == 3, (n_pol, n_lin)


caso("polígonos y líneas: sus vértices, sin el de cierre ni los compartidos", poligonos_y_lineas)


def seleccion():
    c = capa('Point', [f'POINT({X0 + i} {Y0})' for i in range(10)])
    c.selectByIds([1, 2, 3])
    bloque.capa.setLayer(None)
    bloque.capa.setLayer(c)  #Con elementos seleccionados se marca sola la casilla
    marcada = bloque.soloSeleccion.isChecked()
    tres = len(ap.puntos(bloque.geometrias()[0])) == 3 and '3 puntos sin repetir' in bloque.estado.text()
    bloque.soloSeleccion.setChecked(False)
    diez = len(ap.puntos(bloque.geometrias()[0])) == 10
    QgsProject.instance().removeMapLayer(c.id())
    return marcada and tres and diez, (marcada, tres, diez, bloque.estado.text())


caso("solo los seleccionados (marcada sola si hay selección) o todos", seleccion)


def geograficas():
    c = capa('Point', ['POINT(-3.85 36.75)', 'POINT(-3.849 36.751)'], crs='EPSG:4258')
    bloque.capa.setLayer(c)
    geometrias, epsg = bloque.geometrias()
    lista = ap.puntos(geometrias)
    ok = epsg == 25830 and len(lista) == 2 and 400000 < lista[0][0] < 500000 and 4000000 < lista[0][1] < 4100000
    bloque.huso.setCurrentIndex(bloque.huso.findData(25829))  #Elegido a mano: se respeta
    forzado = bloque.geometrias()[1] == 25829
    bloque.huso.setCurrentIndex(0)
    QgsProject.instance().removeMapLayer(c.id())
    return ok and forzado, (epsg, lista[:1], forzado)


caso("capa en coordenadas geográficas: pasa al huso de la Sede (automático o elegido)", geograficas)


def vacia_y_demasiados():
    vacia = capa('Point', [])
    bloque.capa.setLayer(vacia)
    sin = not bloque.crearBoton.isEnabled() and 'no tiene vértices' in bloque.estado.text()
    muchos = capa('LineString', ['LINESTRING(' + ', '.join(f'{X0 + i * 0.1} {Y0 + (i % 7)}' for i in range(ap.MAX_PUNTOS + 5))
                                 + ')'])
    bloque.capa.setLayer(muchos)
    demasiados = not bloque.crearBoton.isEnabled() and 'demasiados' in bloque.estado.text()
    bloque.capa.setLayer(None)
    nada = not bloque.crearBoton.isEnabled() and 'Elija la capa' in bloque.estado.text()
    for c in (vacia, muchos):
        QgsProject.instance().removeMapLayer(c.id())
    return sin and demasiados and nada, (sin, demasiados, nada)


caso("capa vacía, demasiados puntos o sin capa: no deja crear el TXT y dice por qué", vacia_y_demasiados)


def no_se_puede_escribir():
    c = capa('Point', [f'POINT({X0} {Y0})'])
    bloque.capa.setLayer(c)
    ocupado = os.path.join(carpeta, 'ocupado.txt')
    os.makedirs(ocupado, exist_ok=True)  #Una carpeta con ese nombre
    bloque.destino.setFilePath(ocupado)
    dw.messageBar.clearWidgets()
    fallo = bloque.crear() is None and 'No se han guardado los puntos' in barra()
    bloque.destino.setFilePath(os.path.join(carpeta, 'sin_extension'))
    extension = bloque.crear() == os.path.join(carpeta, 'sin_extension.txt')
    QgsProject.instance().removeMapLayer(c.id())
    return fallo and extension, (fallo, extension, barra()[:150])


caso("fichero que no se puede escribir: aviso; sin extensión: añade .txt", no_se_puede_escribir)

dw.cleanup()
dw.deleteLater()
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
resultados["ninguna ventana emergente"] = not ventanas

print("=" * 60)
print("QGIS", Qgis.version(), "· Puntos de apoyo: batería de casos")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, d in detalles.items():
    print("Detalles", nombre, ":", d)
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
