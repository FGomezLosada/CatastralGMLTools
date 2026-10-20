"""
Batería de casos de Utilidades «1. Unir GML» (plan de pruebas, docs/PLAN_PRUEBAS.md): ficheros de cualquier origen y
combinación. Lo que se une debe pasar la Validar del plugin sin errores; lo que no se puede unir lo dice, sin fallar ni
abrir ventanas, y sin tocar los ficheros de origen.

Uso: tools\\probar.bat (o tools\\run_tests.py unir_casos_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os
import re
import tempfile
import traceback

import qgis.utils
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsGeometry
from qgis.PyQt.QtCore import QMimeData, QPointF, Qt, QUrl
from qgis.PyQt.QtGui import QDragEnterEvent, QDropEvent
from qgis.PyQt.QtWidgets import QApplication, QLabel, QMessageBox

import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import geometria as geo  # noqa: E402
from catastral_gml_tools.core import gml_lector as gl  # noqa: E402
from catastral_gml_tools.core import gml_parcela as gp  # noqa: E402
from catastral_gml_tools.core import unir as un  # noqa: E402
from catastral_gml_tools.core import validador  # noqa: E402
from catastral_gml_tools.core.info import RAIZ  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))
dock_module.CatastralGMLToolsDockWidget.open_path = lambda self, ruta: None

carpeta = tempfile.mkdtemp(prefix='cgt unir casos ñ_')
DATOS = os.path.join(RAIZ, 'tests', 'data', 'gml')
X0, Y0 = 421500.0, 4070500.0
RC, R2 = '1907401VK4810H', '1907402VK4810H'
resultados, detalles = {}, {}


def rect(x, y, a, b):
    return QgsGeometry.fromWkt(f"POLYGON(({x} {y}, {x + a} {y}, {x + a} {y + b}, {x} {y + b}, {x} {y}))")


def escribir(nombre, parcelas, epsg=25830):
    ruta = os.path.join(carpeta, nombre + '.gml')
    ok, inc = gp.escribir(ruta, parcelas, epsg)
    assert ok, (nombre, inc)
    return ruta


def guardar(nombre, texto):
    ruta = os.path.join(carpeta, nombre + '.gml')
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write(texto)
    return ruta


def leer_texto(ruta):
    with open(ruta, encoding='utf-8') as f:
        return f.read()


def contenido(ruta):
    if not os.path.isfile(ruta):
        return None
    with open(ruta, 'rb') as f:
        return f.read()


def unir(nombre, rutas):
    destino = os.path.join(carpeta, nombre + '_unido.gml')
    if os.path.isfile(destino):
        os.remove(destino)
    antes = {r: contenido(r) for r in rutas}
    ok, n, inc = un.unir(rutas, destino)
    intactos = all(contenido(r) == b for r, b in antes.items())
    informe = validador.validar(destino) if ok else None
    return ok, n, inc, informe, intactos, destino


def codigos(inc):
    return {i.codigo for i in inc}


def caso(nombre, funcion):
    try:
        ok, detalle = funcion()
        resultados[nombre] = bool(ok)
        if not ok:
            detalles[nombre] = detalle
    except Exception:  # noqa: BLE001
        resultados[nombre] = False
        detalles[nombre] = traceback.format_exc()[-900:]


def resumen(r):
    ok, n, inc, informe, intactos, _ = r
    return ok, n, sorted(codigos(inc)), [i.mensaje[:90] for i in (informe.errores if informe else [])][:3], intactos


A = escribir('a', [gp.ParcelaGML(RC, gp.SDGC, rect(X0, Y0, 20, 18), '01'), gp.ParcelaGML('Seg_1', gp.LOCAL, rect(X0, Y0 + 18, 20, 12))])
B = escribir('b', [gp.ParcelaGML(R2, gp.SDGC, rect(X0 + 20, Y0, 20, 18), '02'),
                   gp.ParcelaGML('Seg_1', gp.LOCAL, rect(X0 + 20, Y0 + 18, 20, 12))])


def bien(nombre, rutas, n_esperado, codigos_esperados=(), sin=()):
    def prueba():
        r = unir(nombre, rutas)
        ok, n, inc, informe, intactos, _ = r
        return (ok and n == n_esperado and informe is not None and not informe.errores and intactos
                and all(c in codigos(inc) for c in codigos_esperados) and not any(c in codigos(inc) for c in sin)), resumen(r)
    return prueba


def mal(nombre, rutas, codigo=None):
    def prueba():
        r = unir(nombre, rutas)
        ok, n, inc, _, intactos, destino = r
        mensajes = [i.mensaje for i in inc if i.nivel == 'error']
        return (not ok and not os.path.isfile(destino) and intactos and bool(mensajes)
                and (codigo is None or codigo in codigos(inc))), resumen(r)
    return prueba


# 1. Combinaciones normales
caso("dos segregaciones vecinas: Seg_1 del segundo pasa a Seg_2", bien('vecinas', [A, B], 4, ['UNIR-RENOMBRADA']))
caso("el mismo fichero dos veces: cada parcela una vez", bien('repetido', [A, A], 2, ['UNIR-REPETIDA']))
C = escribir('c', [gp.ParcelaGML('Seg_1', gp.LOCAL, rect(X0 + 40, Y0, 20, 30))])
caso("Seg_1 en tres ficheros: Seg_1, Seg_2 y Seg_3", lambda: (lambda r: (
    r[0] and sorted(e.local_id for e in gl.leer(r[5]).elementos) == sorted([RC, R2, 'Seg_1', 'Seg_2', 'Seg_3']), resumen(r)))(
    unir('tres', [A, B, C])))
#La muestra 3.0 está en el mismo sitio que A: se une con una segregación al sur, sin solape
CP30 = os.path.join(DATOS, 'parcela_cp30_sintetica.gml')
SUR = escribir('sur', [gp.ParcelaGML('Nueva_3', gp.LOCAL, rect(X0, Y0 - 40, 20, 30))])
caso("esquema 3.0 con uno 4.0", bien('con30', [CP30, SUR], len(gl.leer(CP30).elementos) + 1, ['UNIR-CP30']))
caso("esquema 3.0 encima de un 4.0: el solape se dice", mal('con30_solape', [CP30, A]))


def husos():
    otro = escribir('huso29', [gp.ParcelaGML('Nueva_9', gp.LOCAL, geo.transformar(
        rect(X0 + 40, Y0, 20, 30), QgsCoordinateReferenceSystem('EPSG:25830'), 25829))], 25829)
    return bien('husos', [A, otro], 3, ['UNIR-SRC'])()


caso("en husos distintos: se pasa al del primero y se avisa", husos)
caso("zonas separadas: se avisa", bien('separadas', [A, escribir('lejos', [gp.ParcelaGML('Nueva_7', gp.LOCAL,
                                                                                          rect(X0 + 500, Y0, 20, 30))])],
                                       3, ['UNIR-SEPARADAS']))
_muchos = [escribir(f'm{k}', [gp.ParcelaGML(f'P{k}_{i}', gp.LOCAL, rect(X0 + i * 10, Y0 + k * 30, 10, 30)) for i in range(20)])
           for k in range(2)]
caso("40 parcelas: se unen y salen los avisos de Validar", lambda: (lambda r: (
    r[0] and r[1] == 40 and 'N-PARCELAS' in {i.codigo for i in r[3].avisos}, resumen(r)))(unir('muchos', _muchos)))

# 2. Lo que no se puede unir
caso("la misma RC con geometrías distintas: error", mal('rc_distinta', [A, escribir('a_mod', [gp.ParcelaGML(
    RC, gp.SDGC, rect(X0, Y0, 21, 18), '01')])], 'UNIR-ID-DISTINTO'))
caso("parcelas de dos ficheros que se solapan: no se escribe", mal('solape', [A, escribir('solapa', [gp.ParcelaGML(
    'Nueva_5', gp.LOCAL, rect(X0 + 10, Y0, 20, 30))])]))
caso("un GML de edificios: error", mal('con_bu', [A, os.path.join(DATOS, 'edificio_sintetico.gml')], 'UNIR-NO-PARCELA'))
caso("un GML mal formado: error", mal('malformado', [A, os.path.join(DATOS, 'mal_formado.gml')]))
caso("un fichero que no existe: error", mal('noexiste', [A, os.path.join(carpeta, 'no_existe.gml')]))
caso("un fichero vacío: error", mal('vacio', [A, guardar('vacio', '')]))
caso("un fichero que no existe: lo dice en castellano", lambda: (lambda r: (
    any('No existe el fichero' in i.mensaje for i in r[2]) and 'Errno' not in ' '.join(i.mensaje for i in r[2]),
    resumen(r)))(unir('noexiste2', [A, os.path.join(carpeta, 'no_existe.gml')])))
caso("una carpeta en lugar de un fichero: error", mal('carpeta', [A, carpeta]))
caso("«Guardar como» de QGIS: error que dice que se convierta", lambda: (lambda r: (
    not r[0] and any('Convertir' in i.mensaje for i in r[2]), resumen(r)))(unir('generico', [A, guardar(
        'generico', '<?xml version="1.0"?><ogr:FeatureCollection xmlns:ogr="http://ogr.maptools.org/" '
                    f'xmlns:gml="http://www.opengis.net/gml/3.2"><ogr:featureMember><ogr:{RC}/></ogr:featureMember>'
                    '</ogr:FeatureCollection>')])))
def en_4326(nombre, ruta):
    lectura = gl.leer(ruta)
    origen = QgsCoordinateReferenceSystem(f'EPSG:{lectura.epsg}')
    return escribir_libre(nombre, [gp.ParcelaGML(e.local_id, gp.SDGC if e.namespace == 'ES.SDGC.CP' else gp.LOCAL,
                                                 geo.transformar(e.geometria, origen, 4326)) for e in lectura.elementos])


def escribir_libre(nombre, parcelas):
    """GML en EPSG:4326 (el escritor del plugin no lo admite): uno en 25830 con el SRC y las coordenadas cambiados."""
    ruta = escribir(nombre, [gp.ParcelaGML(p.local_id, p.namespace, rect(X0 + 10 * k, Y0, 1, 1))
                             for k, p in enumerate(parcelas)])
    listas = iter(' '.join(f"{q.y():.9f} {q.x():.9f}" for q in p.geometria.asPolygon()[0]) for p in parcelas)
    texto = re.sub(r'(<gml:posList[^>]*>)[^<]*(<)', lambda m: m.group(1) + next(listas) + m.group(2), leer_texto(ruta))
    return guardar(nombre, texto.replace('EPSG/0/25830', 'EPSG/0/4326'))


def wgs84_primero():
    r = unir('wgs84', [en_4326('en4326', B), A])
    #En su sitio: pegado a A (si se leyera longitud, latitud acabaría lejos y saldría «zonas separadas»)
    return (r[0] and gl.leer(r[5]).epsg == 25830 and 'UNIR-SRC' in codigos(r[2]) and 'UNIR-LAT-LON' in codigos(r[2])
            and 'UNIR-SEPARADAS' not in codigos(r[2])), resumen(r)


def wgs84_todos():
    r = unir('wgs84_todos', [en_4326('a4326', A), en_4326('b4326', B)])
    return r[0] and gl.leer(r[5]).epsg == 25830 and r[1] == 4 and 'UNIR-SEPARADAS' not in codigos(r[2]), resumen(r)


caso("el primero en EPSG:4326: se une en el huso del segundo, no en grados", wgs84_primero)
caso("todos en EPSG:4326: se unen en su huso (30)", wgs84_todos)
caso("un solo fichero: pide dos", mal('uno', [A], 'UNIR-POCOS'))


def destino_es_origen():
    ok, n, inc = un.unir([A, B], A)
    return not ok and 'UNIR-DESTINO' in codigos(inc), sorted(codigos(inc))


def carpeta_inexistente():
    ok, n, inc = un.unir([A, B], os.path.join(carpeta, 'no existe', 'x.gml'))
    return not ok and bool(inc), [i.mensaje for i in inc]


caso("el destino es uno de los ficheros: no lo pisa", destino_es_origen)
caso("carpeta de destino que no existe: error claro", carpeta_inexistente)


# 3. La utilidad en el panel
def panel():
    dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
    pu = dw.pestanaUtilidades
    pu.utilidades.setCurrentIndex(0)
    #Arrastrar los dos a la lista, y otra vez uno de ellos: no se repite
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(A), QUrl.fromLocalFile(B)])
    acciones = Qt.DropAction.MoveAction | Qt.DropAction.CopyAction
    for urls in ([A, B], [A]):
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(u) for u in urls])
        objetivo = pu.lista.viewport()
        QApplication.sendEvent(objetivo, QDragEnterEvent(objetivo.rect().center(), acciones, mime, Qt.MouseButton.LeftButton,
                                                         Qt.KeyboardModifier.NoModifier))
        QApplication.sendEvent(objetivo, QDropEvent(QPointF(objetivo.rect().center()), acciones, mime,
                                                    Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    arrastre = pu.lista.count() == 2 and pu.unirBoton.isEnabled()
    #Unir con un fichero malo: aviso en el panel, sin ventanas
    pu.agregar([os.path.join(DATOS, 'mal_formado.gml')])
    pu.destino.setFilePath(os.path.join(carpeta, 'panel_unido.gml'))
    dw.messageBar.clearWidgets()
    malo = pu.unir() is None and bool(dw.messageBar.items())
    #Quitar el malo y unir
    pu.lista.setCurrentRow(2)
    pu.lista.item(2).setSelected(True)
    pu.quitar()
    hecho = pu.unir()
    barra = ' '.join([i.text() for i in dw.messageBar.items()] + [e.text() for i in dw.messageBar.items()
                                                                   for e in i.findChildren(QLabel)])
    unido = hecho is not None and 'GML unido' in barra and '4 parcelas' in barra
    #Quitar todo: el botón se desactiva
    pu.lista.selectAll()
    pu.quitar()
    vacio = not pu.unirBoton.isEnabled() and pu.lista.count() == 0
    dw.deleteLater()
    return arrastre and malo and unido and vacio, (arrastre, malo, unido, vacio, barra[:200])


caso("panel: arrastrar a la lista sin repetir, fichero malo, quitar y unir", panel)

for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
resultados["ninguna ventana emergente"] = not ventanas

print("=" * 60)
print("QGIS", Qgis.version(), "· Unir GML: batería de casos")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, d in detalles.items():
    print("Detalles", nombre, ":", d)
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
