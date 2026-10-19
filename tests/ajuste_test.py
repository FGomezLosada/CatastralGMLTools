"""
Prueba del ajuste a la cartografía catastral desplazada o girada (fase 8e, AU-52): core/ajuste.py y la utilidad «4.» de
Utilidades. Parámetros de la Sede (X' = AX·X + BX·Y + CX…) por traslación, semejanza y afín con mínimos cuadrados,
residuos, lectura de puntos en TXT/CSV, GML ajustado de parcela y de edificio, fichero de parámetros, y la interfaz:
tabla, parámetros escritos a mano, captura en el mapa (con el mapa en otro SRC), arrastrar el GML, cambiar de
herramienta, cerrar el panel.

Uso: tools\\probar.bat (o tools\\run_tests.py ajuste_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import math
import os
import shutil
import tempfile

import qgis.utils
from qgis.core import Qgis, QgsGeometry, QgsPointXY, QgsProject
from qgis.gui import QgsMapToolPan
from qgis.PyQt.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt, QUrl
from qgis.PyQt.QtGui import QDragEnterEvent, QDropEvent, QKeyEvent
from qgis.PyQt.QtWidgets import QApplication, QLabel, QMessageBox

import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import ajuste as aj  # noqa: E402
from catastral_gml_tools.core import gml_lector as gl  # noqa: E402
from catastral_gml_tools.core import gml_parcela as gp  # noqa: E402
from catastral_gml_tools.core.info import RAIZ  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))

carpeta = tempfile.mkdtemp(prefix='cgt_ajuste_')
X0, Y0 = 421500.0, 4070500.0


def cerca(a, b, tolerancia):
    return abs(a - b) <= tolerancia


def pares_de(t, puntos, ruido=()):
    ruido = list(ruido) + [(0, 0)] * (len(puntos) - len(ruido))
    salida = []
    for (x, y), (ex, ey) in zip(puntos, ruido):
        xc, yc = t.aplicar(x, y)
        salida.append(aj.Par(x, y, xc + ex, yc + ey))
    return salida


PUNTOS = [(X0, Y0), (X0 + 40, Y0 + 5), (X0 + 35, Y0 + 60), (X0 - 10, Y0 + 45)]

# 1. Se recuperan los parámetros de una transformación conocida (giro de 0,01°, escala +50 ppm, traslación 1,2 E y 0,8 S)
g = math.radians(0.01)
a, b = 1.00005 * math.cos(g), 1.00005 * math.sin(g)
#Giro y escala alrededor de (X0, Y0), que además se traslada (1,2; −0,8)
conocida = aj.Transformacion(a, -b, X0 + 1.2 - (a * X0 - b * Y0), b, a, Y0 - 0.8 - (b * X0 + a * Y0))
semejanza = aj.calcular(pares_de(conocida, PUNTOS[:3]), aj.SEMEJANZA)
recupera = (all(cerca(u, v, 1e-9) for u, v in zip(semejanza.transformacion.valores()[0:2], conocida.valores()[0:2]))
            and cerca(semejanza.transformacion.cx, conocida.cx, 1e-4) and cerca(semejanza.transformacion.cy, conocida.cy, 1e-4)
            and max(semejanza.residuos) < 1e-6 and semejanza.redundancia == 2)
afin_conocida = aj.Transformacion(1.0001, 0.0002, -812.3, -0.0003, 0.9998, 1350.7)
afin = aj.calcular(pares_de(afin_conocida, PUNTOS), aj.AFIN)
recupera = (recupera and all(cerca(u, v, 1e-4 if i in (2, 5) else 1e-9)
                             for i, (u, v) in enumerate(zip(afin.transformacion.valores(), afin_conocida.valores())))
            and afin.redundancia == 2)
#Traslación: la media de las diferencias; con ruido, residuos y error medio cuadrático
desplazada = aj.Transformacion(cx=1.5, cy=-0.75)
traslacion = aj.calcular(pares_de(desplazada, PUNTOS[:2], [(0.02, 0), (-0.02, 0)]), aj.TRASLACION)
recupera = (recupera and cerca(traslacion.transformacion.cx, 1.5, 1e-9) and cerca(traslacion.transformacion.cy, -0.75, 1e-9)
            and traslacion.transformacion.es_traslacion() and cerca(traslacion.emc, 0.02, 1e-9))
#Signo de la Sede: si el Catastro está más al este y al norte que la realidad, CX y CY positivos
signo = aj.calcular([aj.Par(X0, Y0, X0 + 2, Y0 + 3)], aj.TRASLACION).transformacion
recupera = recupera and signo.cx == 2 and signo.cy == 3

# 2. Un punto mal tomado se ve en los residuos
malo = aj.calcular(pares_de(afin_conocida, PUNTOS + [(X0 + 20, Y0 + 30)], [(0, 0)] * 4 + [(0.5, 0)]), aj.AFIN)
residuos = malo.residuos.index(max(malo.residuos)) == 4 and malo.emc > 0.1

#Avisos: dos puntos a 33 cm (prueba a mano del 19/10/2026) no sirven para giro y escala; escala impropia de un desplazamiento
juntos = aj.calcular([aj.Par(421834.85, 4067953.39, 421834.852, 4067953.387),
                      aj.Par(421834.87, 4067953.72, 421834.871, 4067953.718)], aj.SEMEJANZA)
dudas = aj.avisos(juntos, [aj.Par(421834.85, 4067953.39, 0, 0), aj.Par(421834.87, 4067953.72, 0, 0)], 30.0)
residuos = (residuos and len(dudas) == 2 and 'muy juntos (0.33 m' in dudas[0] and 'al menos 8 m' in dudas[0]
            and 'Escala anómala' in dudas[1] and aj.avisos(semejanza, pares_de(conocida, PUNTOS[:3]), 60.0) == [])

# 3. Errores: pocos puntos, puntos alineados; inversa
errores = []
for pares, metodo in (([aj.Par(X0, Y0, X0, Y0)], aj.SEMEJANZA),
                      ([aj.Par(X0 + i, Y0 + i, X0 + i, Y0 + i) for i in range(3)], aj.AFIN),
                      ([aj.Par(X0, Y0, X0, Y0), aj.Par(X0, Y0, X0 + 1, Y0)], aj.SEMEJANZA)):
    try:
        aj.calcular(pares, metodo)
        errores.append(False)
    except ValueError:
        errores.append(True)
ida = afin_conocida.aplicar(X0 + 3, Y0 + 7)
vuelta = afin_conocida.inversa().aplicar(*ida)
errores = all(errores) and cerca(vuelta[0], X0 + 3, 1e-6) and cerca(vuelta[1], Y0 + 7, 1e-6)

# 4. Puntos desde TXT o CSV (cabeceras y líneas sueltas se saltan)
texto = ("# levantamiento -> catastro\nP;X;Y;X';Y'\nP1;421500,10;4070500,20;421501,30;4070499,40\n"
         "2 421540.00 4070505.00 421541.20 4070504.20\n421535.0,4070560.0,421536.2,4070559.2\n"
         "421490\t4070545\t421491.2\t4070544.2\nlínea suelta\n")
leidos, saltadas = aj.leer_pares(texto)
lectura_txt = (len(leidos) == 4 and leidos[0].nombre == 'P1' and cerca(leidos[0].xc, 421501.30, 1e-9)
               and leidos[1].nombre == '2' and cerca(leidos[3].yc, 4070544.2, 1e-9) and saltadas == [2, 7])

# 5. GML ajustado: parcela reescrita con el escritor (superficie recalculada, mismos identificadores y número)
ruta = os.path.join(carpeta, 'levantamiento.gml')
casa = QgsGeometry.fromWkt(f"POLYGON(({X0} {Y0}, {X0} {Y0 + 30}, {X0 + 20} {Y0 + 30}, {X0 + 20} {Y0}, {X0} {Y0}))")
nueva = QgsGeometry.fromWkt(f"POLYGON(({X0 + 20} {Y0}, {X0 + 20} {Y0 + 30}, {X0 + 35} {Y0 + 30}, {X0 + 35} {Y0}, {X0 + 20} {Y0}))")
gp.escribir(ruta, [gp.ParcelaGML('1907401VK4810H', gp.SDGC, casa, '01'), gp.ParcelaGML('Seg_1', gp.LOCAL, nueva)], 25830)
with open(ruta, encoding='utf-8') as f:
    original = f.read()
destino = aj.ruta_ajustada(ruta)
t_parcela = aj.Transformacion(cx=1.25, cy=-0.5)
hecho, inc = aj.escribir_ajustado(ruta, destino, t_parcela)
ajustada = gl.leer(destino)
primer = ajustada.elementos[0].geometria.asPolygon()[0][0] if hecho else None
gml_parcela = (hecho and not inc and [e.local_id for e in ajustada.elementos] == ['1907401VK4810H', 'Seg_1']
               and ajustada.elementos[0].label == '01' and cerca(primer.x(), X0 + 1.25, 1e-6) and cerca(primer.y(), Y0 - 0.5, 1e-6)
               and ajustada.elementos[0].area_declarada == 600 and ajustada.version == 'CP 4.0')
with open(ruta, encoding='utf-8') as f:
    gml_parcela = gml_parcela and f.read() == original  #El del levantamiento no se toca
#Con escala, la superficie del GML ajustado se recalcula
hecho_escala, _ = aj.escribir_ajustado(ruta, os.path.join(carpeta, 'escala.gml'), aj.Transformacion(1.01, 0, 0, 0, 1.01, 0))
gml_parcela = gml_parcela and hecho_escala and gl.leer(os.path.join(carpeta, 'escala.gml')).elementos[0].area_declarada == 612
#No puede sustituir al original
mismo, inc_mismo = aj.escribir_ajustado(ruta, ruta, t_parcela)
gml_parcela = gml_parcela and not mismo and inc_mismo[0].codigo == 'AJ-DESTINO'

# 6. Edificio: solo cambian las coordenadas (también el resto del fichero, en UTF-8)
edificio = os.path.join(carpeta, 'edificio.gml')
shutil.copy(os.path.join(RAIZ, 'tests', 'data', 'gml', 'edificio_sintetico.gml'), edificio)
hecho_bu, inc_bu = aj.escribir_ajustado(edificio, aj.ruta_ajustada(edificio), t_parcela)
bu = gl.leer(aj.ruta_ajustada(edificio))
with open(aj.ruta_ajustada(edificio), encoding='utf-8') as f:
    texto_bu = f.read()
gml_edificio = (hecho_bu and not inc_bu and bu.version.startswith('BU') and len(bu.elementos) == len(gl.leer(edificio).elementos)
                and '421503.25 4070501.50' in texto_bu and 'encoding="utf-8"' in texto_bu and 'SINTÉTICO' in texto_bu
                and 'openAirPool' in texto_bu and '<bu-ext2d:numberOfFloorsAboveGround>2<' in texto_bu)
try:
    aj.transformar_texto('<gml:posList srsDimension="3">1 2 3</gml:posList>', t_parcela)
    gml_edificio = False
except ValueError as e:
    gml_edificio = gml_edificio and 'srsDimension 3' in str(e)

# 7. Fichero de parámetros: fórmula, convenio de signos, valores, residuos y la Resolución
parametros = aj.texto_parametros(malo, pares_de(afin_conocida, PUNTOS + [(X0 + 20, Y0 + 30)]), ruta, destino, 25830)
fichero_parametros = ("X' = AX·X + BX·Y + CX" in parametros and 'más al este o al norte' in parametros
                      and f"AX = {malo.transformacion.textos()[0]}" in parametros and 'Error medio cuadrático' in parametros
                      and 'BOE-A-2021-5949' in parametros and 'levantamiento_ajustado.gml' in parametros)

# 8. Interfaz: Utilidades «4.»
iface = qgis.utils.iface
lienzo = iface.mapCanvas()
proyecto = QgsProject.instance()
dw = dock_module.CatastralGMLToolsDockWidget(iface)
dw.show()
pu = dw.pestanaUtilidades
dw.tabWidget.setCurrentWidget(dw.tabUtilidades)
pu.utilidades.setCurrentIndex(3)
ba = pu.ajuste


def textos_barra():
    textos = []
    for item in dw.messageBar.items():
        textos.append(item.text())
        textos += [e.text() for e in item.findChildren(QLabel)]
    return ' | '.join(textos)


#Sin GML no se captura en el mapa
pan = QgsMapToolPan(lienzo)
lienzo.setMapTool(pan)
ba.capturarBoton.setChecked(True)
sin_gml = not ba.capturarBoton.isChecked() and lienzo.mapTool() is pan and 'Elija antes el GML' in textos_barra()

ba.origenAj.setFilePath(ruta)
propuesto = os.path.normpath(ba.destinoAj.filePath()) == os.path.normpath(destino) and 'CP 4.0 · EPSG:25830' in ba.resumenAj.text()
ba.metodo.setCurrentIndex(ba.metodo.findData(aj.TRASLACION))
for par in pares_de(desplazada, PUNTOS[:3], [(0.01, 0), (-0.01, 0), (0, 0)]):
    ba.anadir_par(par)
ba.recalcular()
tabla = (ba.parametros[2].text() == '1.5000' and ba.parametros[5].text() == '-0.7500' and ba.crearAjBoton.isEnabled()
         and ba.tabla.item(0, 4).text() == '0,010' and 'error medio' in ba.resumenAj.text()
         and 'Catastro está 1,50 m al E y 0,75 m al S' in ba.resumenAj.text())
#Un número mal escrito se señala; corregirlo en la tabla recalcula
ba.tabla.item(1, 0).setText('abc')
tabla = tabla and 'Filas con números que no se entienden: 2' in ba.resumenAj.text()
ba.tabla.item(1, 0).setText(f"{PUNTOS[1][0]:.3f}")
tabla = tabla and 'Filas con' not in ba.resumenAj.text() and ba.tabla.item(1, 4).text() == '0,010'
#Semejanza con 3 puntos; con 1 punto, el aviso de que faltan
ba.metodo.setCurrentIndex(ba.metodo.findData(aj.SEMEJANZA))
tabla = tabla and 'giro' in ba.resumenAj.text() and ba.crearAjBoton.isEnabled()
ba.tabla.selectRow(2)
ba.quitar()
ba.tabla.selectRow(1)
ba.quitar()
ba.metodo.setCurrentIndex(ba.metodo.findData(aj.AFIN))
tabla = tabla and 'al menos 3' in ba.resumenAj.text() and not ba.crearAjBoton.isEnabled()
#Parámetros escritos a mano (los de la Sede): se pueden editar y se comprueban con los puntos
ba.metodo.setCurrentIndex(ba.metodo.findData(aj.CONOCIDOS))
for campo, valor in zip(ba.parametros, ('1', '0', '1,5', '0', '1', '-0.75')):
    campo.setText(valor)
ba.recalcular()
conocidos = (not ba.parametros[0].isReadOnly() and ba.ajuste is not None and ba.ajuste.transformacion.cx == 1.5
             and ba.crearAjBoton.isEnabled())
ba.parametros[0].setText('uno')
ba.recalcular()
conocidos = conocidos and 'deben ser números' in ba.resumenAj.text() and not ba.crearAjBoton.isEnabled()
ba.parametros[0].setText('1')
ba.recalcular()
#Importar puntos de un fichero
puntos_txt = os.path.join(carpeta, 'puntos.txt')
with open(puntos_txt, 'w', encoding='utf-8') as f:
    f.write(texto)
antes = ba.tabla.rowCount()
ba.importar_fichero(puntos_txt)
conocidos = conocidos and ba.tabla.rowCount() == antes + 4 and 'se han saltado las líneas 2, 7' in textos_barra()
for _ in range(4):
    ba.tabla.selectRow(ba.tabla.rowCount() - 1)
    ba.quitar()

#Crear: GML ajustado y parámetros; «Validar» lo abre en Validar
dw.messageBar.clearWidgets()
creado = ba.crear()
from qgis.PyQt.QtWidgets import QPushButton  # noqa: E402

botones_barra = [b.text() for item in dw.messageBar.items() for b in item.findChildren(QPushButton)]
crear = (creado is not None and os.path.isfile(destino) and os.path.isfile(aj.ruta_parametros(destino))
         and 'GML ajustado: levantamiento_ajustado.gml' in textos_barra() and 'apartado octavo' in textos_barra()
         and 'Ver parámetros' in botones_barra and ba.parametros_ruta == aj.ruta_parametros(destino))
ba.validar()
crear = crear and os.path.normpath(dw.pestanaValidar.fichero.filePath()) == os.path.normpath(destino)
dw.tabWidget.setCurrentWidget(dw.tabUtilidades)

# 9. Capturar en el mapa: el mapa de las pruebas está en EPSG:4326 y los puntos se pasan al SRC del GML
ba.metodo.setCurrentIndex(ba.metodo.findData(aj.TRASLACION))
filas = ba.tabla.rowCount()
lienzo.setMapTool(pan)
ba.capturarBoton.setChecked(True)
activa = (lienzo.mapTool() is ba.herramienta and ba.herramienta is not None and ba.pasoCaptura.isVisible()
          and '1/2' in ba.pasoCaptura.text())
ba.punto_capturado(QgsPointXY(-3.9, 36.75))
pendiente = ba.pendiente is not None and ba.marca is not None and '2/2' in ba.pasoCaptura.text()
#Esc anula el punto a medias
ba.herramienta.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
anulado = ba.pendiente is None and ba.marca is None
ba.punto_capturado(QgsPointXY(-3.9, 36.75))
ba.punto_capturado(QgsPointXY(-3.89999, 36.75001))
fila = ba.tabla.rowCount() - 1
x_utm = float(ba.tabla.item(fila, 0).text())
captura = (activa and pendiente and anulado and ba.tabla.rowCount() == filas + 1 and 380000 < x_utm < 420000
           and 0.5 < float(ba.tabla.item(fila, 2).text()) - x_utm < 1.5 and ba.pendiente is None)
#Las líneas de los pares en el mapa: solo con el ajuste abierto y el panel a la vista
lineas = ba.banda.numberOfVertices() if ba.banda is not None else 0
pu.utilidades.setCurrentIndex(2)
oculto = ba.banda.numberOfVertices() == 0
pu.utilidades.setCurrentIndex(3)
captura = captura and lineas == 2 * ba.tabla.rowCount() and oculto and ba.banda.numberOfVertices() == lineas
#Por la herramienta de verdad: clic izquierdo (con o sin vértice cerca) y clic derecho que anula
from qgis.gui import QgsMapMouseEvent  # noqa: E402

centro = QPoint(lienzo.width() // 2, lienzo.height() // 2)
ba.herramienta.canvasReleaseEvent(QgsMapMouseEvent(lienzo, QEvent.Type.MouseButtonRelease, centro,
                                                   Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton))
por_clic = ba.pendiente is not None
ba.herramienta.canvasReleaseEvent(QgsMapMouseEvent(lienzo, QEvent.Type.MouseButtonRelease, centro,
                                                   Qt.MouseButton.RightButton, Qt.MouseButton.RightButton))
captura = captura and por_clic and ba.pendiente is None
#Otra herramienta sustituye a la nuestra: el botón se desmarca y se olvida el punto a medias
ba.punto_capturado(QgsPointXY(-3.9, 36.75))
lienzo.setMapTool(pan)
cambio = not ba.capturarBoton.isChecked() and ba.pendiente is None and ba.marca is None and not ba.pasoCaptura.isVisible()
#Cerrar el panel: suelta la herramienta y quita las líneas
ba.capturarBoton.setChecked(True)
dw.visibilidad_cambiada(False)
cerrar = lienzo.mapTool() is pan and not ba.capturarBoton.isChecked() and ba.banda.numberOfVertices() == 0
dw.visibilidad_cambiada(True)
cerrar = cerrar and ba.banda.numberOfVertices() == lineas

# 10. Arrastrar un GML sobre una casilla del ajuste: va al levantamiento
mime = QMimeData()
mime.setUrls([QUrl.fromLocalFile(edificio)])
acciones = Qt.DropAction.MoveAction | Qt.DropAction.CopyAction
casilla = ba.parametros[0]
QApplication.sendEvent(casilla, QDragEnterEvent(casilla.rect().center(), acciones, mime, Qt.MouseButton.LeftButton,
                                                Qt.KeyboardModifier.NoModifier))
soltar = QDropEvent(QPointF(casilla.rect().center()), acciones, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
QApplication.sendEvent(casilla, soltar)
arrastre = (soltar.isAccepted() and os.path.normpath(ba.origenAj.filePath()) == os.path.normpath(edificio)
            and ba.version.startswith('BU') and 'BU' in ba.resumenAj.text())
#Un fichero que no se puede leer no vale
ba.origenAj.setFilePath(os.path.join(carpeta, 'no_existe.gml'))
arrastre = arrastre and ba.epsg is None and not ba.crearAjBoton.isEnabled()

# 11. Al cerrar el plugin: la herramienta se devuelve y las líneas desaparecen
ba.origenAj.setFilePath(ruta)
ba.capturarBoton.setChecked(True)
dw.cleanup()
limpieza = lienzo.mapTool() is pan and ba.banda is None and ba.marca is None

proyecto.removeAllMapLayers()
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
dw.hide()
dw.deleteLater()

checks = {
    "se recuperan los parámetros de semejanza, afín y traslación (signo de la Sede)": recupera,
    "un punto mal tomado destaca en los residuos; avisos de puntos juntos y escala anómala": residuos,
    "pocos puntos, puntos alineados o repetidos: error; inversa": errores,
    "pares de puntos desde TXT o CSV (cabeceras saltadas)": lectura_txt,
    "GML de parcela ajustado: mismos ids, superficie recalculada, original intacto": gml_parcela,
    "GML de edificio ajustado: solo cambian las coordenadas; con Z, error": gml_edificio,
    "fichero de parámetros: fórmula, signos, valores, residuos y Resolución": fichero_parametros,
    "sin GML no se captura en el mapa": sin_gml,
    "tabla: parámetros, residuos, filas mal escritas, quitar y métodos": propuesto and tabla,
    "parámetros escritos a mano e importar puntos": conocidos,
    "crear el GML ajustado y los parámetros; Validar y Ver parámetros": crear,
    "capturar en el mapa (otro SRC) con el paso a la vista, Esc, clic derecho y líneas": captura,
    "otra herramienta o cerrar el panel sueltan la captura": cambio and cerrar,
    "arrastrar un GML a una casilla del ajuste": arrastre,
    "al cerrar el plugin no queda nada en el mapa": limpieza,
    "ninguna ventana emergente": not ventanas,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· ajuste a la cartografía catastral")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'semejanza': semejanza.transformacion.valores(), 'conocida': conocida.valores(),
                        'afin': afin.transformacion.valores(), 'residuos': malo.residuos, 'leidos': leidos,
                        'saltadas': saltadas, 'inc': inc, 'inc_bu': inc_bu, 'resumen': ba.resumenAj.text(),
                        'parametros': [c.text() for c in ba.parametros], 'barra': textos_barra()})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
