"""
Batería de casos de Utilidades «6. Parcela desde coordenadas» (AU-57; plan de pruebas, docs/PLAN_PRUEBAS.md): ficheros
de puntos de levantamiento de cualquier forma —separadores, coma decimal, millares, cabeceras, nombres, Z, códigos, una
o varias parcelas, codificaciones— y los que no forman parcela (grados, orden Y X, contorno cruzado, pocos puntos,
alineados, binarios, vacíos). Reglas:
  - nunca una excepción ni una ventana;
  - cada parcela sale con la superficie que encierran sus puntos (al m²) y con su identificador;
  - lo que no se puede deducir se dice, sin inventar parcelas;
  - con «Crear capa», la pestaña Parcela trabaja con la capa nueva y el GML que se crea pasa la Validar del plugin.

Uso: tools\\probar.bat (o tools\\run_tests.py coordenadas_casos_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import math
import os
import tempfile
import traceback

import qgis.utils
from qgis.core import Qgis, QgsProject
from qgis.PyQt.QtCore import QMimeData, QPointF, Qt, QUrl
from qgis.PyQt.QtGui import QDragEnterEvent, QDropEvent
from qgis.PyQt.QtWidgets import QApplication, QLabel, QMessageBox

import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import coordenadas as co  # noqa: E402
from catastral_gml_tools.core import geometria as geo  # noqa: E402
from catastral_gml_tools.core import gml_lector as gl  # noqa: E402
from catastral_gml_tools.core import validador  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))
dock_module.CatastralGMLToolsDockWidget.open_path = lambda self, ruta: None

carpeta = tempfile.mkdtemp(prefix='cgt coordenadas casos ñ_')
resultados, detalles = {}, {}
X0, Y0 = 421500.0, 4070500.0
R = [(X0, Y0), (X0, Y0 + 30), (X0 + 20, Y0 + 30), (X0 + 20, Y0)]          #600 m²
R2 = [(X0 + 20, Y0), (X0 + 20, Y0 + 30), (X0 + 40, Y0 + 30), (X0 + 40, Y0)]  #600 m², al lado


def caso(nombre, funcion):
    try:
        ok, detalle = funcion()
        resultados[nombre] = bool(ok)
        if not ok:
            detalles[nombre] = detalle
    except Exception:  # noqa: BLE001
        resultados[nombre] = False
        detalles[nombre] = traceback.format_exc()[-900:]


def lineas(puntos, formato="{x} {y}", **extra):
    return "\n".join(formato.format(x=x, y=y, n=n, **extra) for n, (x, y) in enumerate(puntos, start=1))


def coma(v, millares=False):
    texto = f"{v:,.2f}" if millares else f"{v:.2f}"
    return texto.replace(',', '#').replace('.', ',').replace('#', '.')


def todos(lectura):
    return {i.codigo for i in lectura.incidencias + [i for p in lectura.parcelas for i in p.incidencias]}


def lee(texto, superficies, ids=None, salen=(), no_salen=('*ERROR',)):
    """superficies: m² de cada parcela que debe formarse (en orden); ids: sus identificadores, si se comprueban."""
    def prueba():
        lectura = co.leer(texto)
        validas = [p for p in lectura.parcelas if p.geometria is not None and not any(i.nivel == 'error' for i in p.incidencias)]
        obtenidas = [round(p.geometria.area()) for p in validas]
        codigos = todos(lectura)
        hay_error = bool(co.errores(lectura))
        ok = obtenidas == list(superficies) and all(c in codigos for c in salen)
        ok = ok and all((not hay_error) if c == '*ERROR' else c not in codigos for c in no_salen)
        if ids is not None:
            ok = ok and [p.identificador for p in validas] == list(ids)
        return ok, (obtenidas, [p.identificador for p in validas], sorted(codigos), lectura.saltadas[:5])
    return prueba


def no_forma(texto, salen):
    def prueba():
        lectura = co.leer(texto)
        validas = [p for p in lectura.parcelas if p.geometria is not None and not any(i.nivel == 'error' for i in p.incidencias)]
        codigos = todos(lectura)
        mensajes = ' '.join(i.mensaje for i in co.errores(lectura))
        return not validas and all(c in codigos for c in salen) and 'Traceback' not in mensajes, (sorted(codigos), mensajes[:200])
    return prueba


# 1. Formatos de una parcela
caso("X Y separadas por espacios", lee(lineas(R), [600]))
caso("número de punto, X, Y y Z", lee(lineas(R, "{n} {x:.3f} {y:.3f} 102.35"), [600]))
caso("nombre de punto, X, Y y código", lee(lineas(R, "V{n} {x:.2f} {y:.2f} LINDE"), [600]))
caso("punto y coma y coma decimal (Excel), con cabecera", lee("Punto;X;Y\n" + "\n".join(f"V{n};{coma(x)};{coma(y)}"
                                                                                      for n, (x, y) in enumerate(R, 1)), [600]))
caso("punto y coma con punto de millares y coma decimal", lee("\n".join(f"V{n};{coma(x, True)};{coma(y, True)}"
                                                                        for n, (x, y) in enumerate(R, 1)), [600]))
caso("CSV con comas y cabecera", lee("id,x,y\n" + lineas(R, "{n},{x:.2f},{y:.2f}"), [600]))
caso("tabuladores", lee(lineas(R, "{n}\t{x:.2f}\t{y:.2f}"), [600]))
caso("con el primer punto repetido al final (cerrado)", lee(lineas(R + R[:1]), [600], no_salen=('COORD-REPETIDOS', '*ERROR')))
caso("un punto repetido seguido: se quita y se dice", lee(lineas([R[0], R[1], R[1], R[2], R[3]]), [600], salen=('COORD-REPETIDOS',)))
caso("en sentido contrario", lee(lineas(R[::-1]), [600]))
caso("comentarios y líneas de texto: se saltan", lee("# Levantamiento finca\n// GPS RTK\n" + lineas(R) + "\nFin del fichero", [600]))
caso("CRLF de Windows y espacios de sobra", lee("\r\n".join(f"   {x:.2f}    {y:.2f}   " for x, y in R), [600]))
caso("orden Y X: se lee bien y se avisa", lee(lineas([(y, x) for x, y in R]), [600], salen=('COORD-YX',)))
caso("1000 puntos (curva)", lee("\n".join(f"{X0 + 20 * math.cos(k / 1000 * 6.2831853):.3f} "
                                          f"{Y0 + 20 * math.sin(k / 1000 * 6.2831853):.3f}" for k in range(1000)),
                                 [1257]))

# 2. Varias parcelas
caso("dos parcelas separadas por una línea en blanco", lee(lineas(R) + "\n\n" + lineas(R2), [600, 600], ['Parcela_1', 'Parcela_2']))
caso("dos parcelas con título («Parcela A», «Parcela B:»)", lee("Parcela A\n" + lineas(R) + "\nParcela B:\n" + lineas(R2), [600, 600],
                                                                  ['A', 'B']))
caso("columna con el identificador de cada parcela", lee("\n".join(f"P1;{coma(x)};{coma(y)}" for x, y in R) + "\n"
                                                         + "\n".join(f"P2;{coma(x)};{coma(y)}" for x, y in R2), [600, 600],
                                                         ['P1', 'P2']))
caso("35 parcelas", lee("\n\n".join(lineas([(x + 30 * k, y) for x, y in R]) for k in range(35)), [600] * 35))
caso("varias líneas en blanco seguidas no crean parcelas vacías", lee(lineas(R) + "\n\n\n\n" + lineas(R2) + "\n\n", [600, 600]))

# 3. Lo que no forma parcela: lo dice
caso("grados (latitud, longitud)", no_forma("36.7541 -3.8757\n36.7543 -3.8757\n36.7543 -3.8755\n36.7541 -3.8755", ['COORD-GRADOS']))
caso("los puntos no van en orden (el contorno se cruza)", no_forma(lineas([R[0], R[2], R[1], R[3]]), ['COORD-CRUZA']))
caso("dos puntos", no_forma(lineas(R[:2]), ['COORD-POCOS']))
caso("puntos alineados", no_forma(lineas([(X0, Y0), (X0 + 10, Y0 + 10), (X0 + 20, Y0 + 20)]), ['COORD-ALINEADOS']))
caso("fichero sin coordenadas", no_forma("Esto es una nota\nsin números", ['COORD-SIN-PUNTOS']))
caso("fichero vacío", no_forma("", ['COORD-SIN-PUNTOS']))
caso("una coordenada mal tecleada: no forma la parcela y dice qué línea", lambda: (lambda lectura: (
    not [p for p in lectura.parcelas if p.geometria is not None and not any(i.nivel == 'error' for i in p.incidencias)]
    and any(i.codigo == 'COORD-FUERA' and 'línea 3' in i.mensaje for i in lectura.parcelas[0].incidencias),
    sorted(todos(lectura))))(co.leer(lineas([R[0], R[1], (42152000.0, Y0 + 30), R[3]]))))
caso("una parcela buena y otra con dos puntos: sale la buena y se dice", lambda: (lambda lectura: (
    [round(p.geometria.area()) for p in lectura.parcelas if p.geometria is not None] == [600] and 'COORD-POCOS' in todos(lectura),
    sorted(todos(lectura))))(co.leer(lineas(R) + "\n\n" + lineas(R2[:2]))))


# 4. ¿En España? (para avisar de un huso equivocado: con EPSG:25829, unas coordenadas de Nerja caen frente a Portugal)
ESPANA = {'Nerja': (-3.876, 36.75), 'Cádiz': (-6.29, 36.53), 'Finisterre': (-9.26, 42.88), 'Cabo de Gata': (-2.19, 36.72),
          'Cap de Creus': (3.32, 42.32), 'Hondarribia': (-1.79, 43.37), 'Ayamonte': (-7.40, 37.21), 'Badajoz': (-6.97, 38.88),
          'Madrid': (-3.7, 40.4), 'Palma': (2.65, 39.57), 'Menorca': (4.27, 39.89), 'Formentera': (1.45, 38.7),
          'Las Palmas': (-15.43, 28.12), 'El Hierro': (-17.98, 27.75), 'Lanzarote': (-13.55, 29.03), 'Ceuta': (-5.32, 35.89),
          'Melilla': (-2.94, 35.29), 'Gijón': (-5.66, 43.54), 'Tarifa': (-5.6, 36.01), 'Huelva': (-6.95, 37.26),
          'Vigo': (-8.72, 42.24), 'Bielsa': (0.22, 42.63), 'Llívia': (1.98, 42.46), 'Alborán': (-3.03, 35.94),
          'Chafarinas': (-2.42, 35.18)}
FUERA = {'Nerja con EPSG:25829': (-9.88, 36.75), 'Nerja con EPSG:25831': (2.12, 36.75), 'Lisboa': (-9.14, 38.72),
         'Argel': (3.06, 36.75), 'Burdeos': (-0.58, 44.84), 'Atlántico': (-12, 40)}
caso("en España: 25 lugares de costa, frontera e islas sí; 6 de fuera no", lambda: (
    all(geo.en_espana(*p) for p in ESPANA.values()) and not any(geo.en_espana(*p) for p in FUERA.values()),
    [n for n, p in ESPANA.items() if not geo.en_espana(*p)] + [n for n, p in FUERA.items() if geo.en_espana(*p)]))


# 5. Codificación
def codificaciones():
    texto = "Vértice;X;Y\n" + "\n".join(f"Esquiña{n};{coma(x)};{coma(y)}" for n, (x, y) in enumerate(R, 1))
    salen = []
    for datos in (texto.encode('utf-8'), texto.encode('utf-8-sig'), texto.encode('cp1252')):
        lectura = co.leer(co.decodificar(datos))
        salen.append([round(p.geometria.area()) for p in lectura.parcelas if p.geometria is not None])
    return salen == [[600]] * 3, salen


caso("UTF-8, UTF-8 con BOM y ANSI (Windows-1252) con eñes", codificaciones)


# 6. La utilidad
def guardar(nombre, contenido):
    ruta = os.path.join(carpeta, nombre)
    with open(ruta, 'wb') as f:
        f.write(contenido.encode('utf-8') if isinstance(contenido, str) else contenido)
    return ruta


def barra(dw):
    return ' '.join([i.text() for i in dw.messageBar.items()] + [e.text() for i in dw.messageBar.items()
                                                                  for e in i.findChildren(QLabel)])


def utilidad():
    dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
    pu = dw.pestanaUtilidades
    pu.utilidades.setCurrentIndex(5)
    bloque = pu.coordenadas
    #Arrastrar el fichero sobre la casilla, como en QGIS
    ruta = guardar('levantamiento.txt', lineas(R) + "\n\n" + lineas(R2))
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(ruta)])
    casilla = bloque.fichero.lineEdit()
    acciones = Qt.DropAction.MoveAction | Qt.DropAction.CopyAction
    QApplication.sendEvent(casilla, QDragEnterEvent(casilla.rect().center(), acciones, mime, Qt.MouseButton.LeftButton,
                                                    Qt.KeyboardModifier.NoModifier))
    QApplication.sendEvent(casilla, QDropEvent(QPointF(casilla.rect().center()), acciones, mime,
                                               Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    arrastrado = os.path.normpath(bloque.fichero.filePath()) == os.path.normpath(ruta)
    resumen = bloque.crearBoton.isEnabled() and 'Parcela_1: 4 puntos, 600 m²' in bloque.estado.text()
    #Crear la capa: la pestaña Parcela trabaja con ella y crea un GML que pasa Validar
    dw.messageBar.clearWidgets()
    capa = bloque.crear()
    pt = dw.pestanaParcela
    en_parcela = (capa is not None and capa.featureCount() == 2 and pt.capa() is capa
                  and dw.tabWidget.currentWidget() is dw.tabParcela and 'desde coordenadas' in barra(dw))
    destino = os.path.join(carpeta, 'levantamiento.gml')
    pt.destino.setFilePath(destino)
    pt.crear_gml()
    gml = os.path.isfile(destino) and not validador.validar(destino).errores and len(gl.leer(destino).elementos) == 2
    #Un fichero que no es de texto, uno que no existe y uno sin parcelas: el botón se desactiva y se dice por qué
    pu.utilidades.setCurrentIndex(5)
    bloque.fichero.setFilePath(guardar('foto.txt', b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + bytes(200)))
    binario = not bloque.crearBoton.isEnabled() and 'no es un fichero de texto' in bloque.estado.text()
    bloque.fichero.setFilePath(os.path.join(carpeta, 'no_existe.txt'))
    no_existe = not bloque.crearBoton.isEnabled() and 'No existe el fichero' in bloque.estado.text()
    bloque.fichero.setFilePath(guardar('grados.csv', "36.7541;-3.8757\n36.7543;-3.8757\n36.7543;-3.8755"))
    grados = not bloque.crearBoton.isEnabled() and 'grados' in bloque.estado.text()
    #Coordenadas del oeste de Galicia (huso 29, X = 110 000) con el huso 30 elegido: aviso del huso
    bloque.fichero.setFilePath(guardar('galicia.txt', lineas([(x - 311500, y + 629500) for x, y in R])))
    bloque.huso.setCurrentIndex(bloque.huso.findData(25830))
    huso = 'huso' in bloque.estado.text()
    texto_huso = bloque.estado.text()
    #Con errores en una parcela, «Crear capa» crea las buenas y lo dice
    bloque.fichero.setFilePath(guardar('mixto.txt', lineas(R) + "\n\n" + lineas(R2[:2])))
    dw.messageBar.clearWidgets()
    mixta = bloque.crear()
    mixto = mixta is not None and mixta.featureCount() == 1 and 'no se ha podido formar' in barra(dw)
    dw.deleteLater()
    QgsProject.instance().removeAllMapLayers()
    ok = arrastrado and resumen and en_parcela and gml and binario and no_existe and grados and huso and mixto
    return ok, (arrastrado, resumen, en_parcela, gml, binario, no_existe, grados, huso, mixto, texto_huso[:300])


caso("utilidad: arrastrar, crear la capa, GML válido desde Parcela, binario, inexistente, grados, huso y mixto", utilidad)

for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
resultados["ninguna ventana emergente"] = not ventanas

print("=" * 60)
print("QGIS", Qgis.version(), "· Parcela desde coordenadas: batería de casos")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, d in detalles.items():
    print("Detalles", nombre, ":", d)
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
