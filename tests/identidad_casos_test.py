"""
Batería de casos de Utilidades «7. Identidad gráfica con el Catastro (simulación)» (AU-58; plan de pruebas,
docs/PLAN_PRUEBAS.md). El criterio del anexo II de la Resolución de 2020: contorno del GML dentro de ±0,50 m (cartografía
urbana) o ±2,00 m (rústica) del perímetro catastral, y diferencia de superficie no mayor del 5 %. Casos justo dentro y
justo fuera de cada límite, urbana y rústica, varias parcelas, GML en grados, de edificios, roto, sin red, y la utilidad.
El Catastro está simulado (tests/simulador_catastro.py).

Uso: tools\\probar.bat (o tools\\run_tests.py identidad_casos_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import importlib.util
import os
import re
import tempfile
import time
import traceback

import qgis.utils
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsGeometry, QgsProject
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import geometria as geo  # noqa: E402
from catastral_gml_tools.core import gml_parcela as gp  # noqa: E402
from catastral_gml_tools.core import identidad as idg  # noqa: E402
from catastral_gml_tools.core import servicios  # noqa: E402
from catastral_gml_tools.core.info import RAIZ  # noqa: E402

spec = importlib.util.spec_from_file_location('simulador_catastro', os.path.join(RAIZ, 'tests', 'simulador_catastro.py'))
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)
original = sim.instalar()

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))
dock_module.CatastralGMLToolsDockWidget.open_path = lambda self, ruta: None

carpeta = tempfile.mkdtemp(prefix='cgt identidad casos ñ_')
DATOS = os.path.join(RAIZ, 'tests', 'data', 'gml')
X0, Y0 = sim.X0, sim.Y0
resultados, detalles = {}, {}


def caso(nombre, funcion):
    try:
        ok, detalle = funcion()
        resultados[nombre] = bool(ok)
        if not ok:
            detalles[nombre] = detalle
    except Exception:  # noqa: BLE001
        resultados[nombre] = False
        detalles[nombre] = traceback.format_exc()[-900:]


def poligono(puntos, huecos=()):
    return QgsGeometry.fromWkt('POLYGON(' + ', '.join('(' + ', '.join(f'{x} {y}' for x, y in a + [a[0]]) + ')'
                                                      for a in [puntos] + list(huecos)) + ')')


def rect(x, y, a, b):
    return poligono([(x, y), (x, y + b), (x + a, y + b), (x + a, y)])


def gml(nombre, recintos, epsg=25830):
    ruta = os.path.join(carpeta, nombre + '.gml')
    ok, inc = gp.escribir(ruta, [gp.ParcelaGML(f'Nueva_{k}', gp.LOCAL, g) for k, g in enumerate(recintos, start=1)], epsg)
    assert ok, (nombre, [str(i) for i in inc if i.nivel == 'error'])
    return ruta


def resumen(s):
    r = s.resultado
    if r is None:
        return [i.mensaje[:120] for i in s.errores]
    return (r.catastrales, r.cartografia, r.margen, r.dentro_margen, round(r.diferencia, 2), r.cumple, round(r.separacion, 3),
            [(round(t.longitud, 2), round(t.distancia, 2)) for t in r.tramos][:3], r.desplazamiento,
            [i.codigo for i in r.incidencias])


def simula(nombre, recintos, cumple, forzado=None, comprobar=None, epsg=25830):
    def prueba():
        s = idg.comprobar_gml(gml(nombre, recintos, epsg), forzado)
        ok = s.resultado is not None and s.resultado.cumple == cumple
        if ok and comprobar is not None:
            ok = comprobar(s.resultado)
        return ok, resumen(s)
    return prueba


RC = rect(X0, Y0, 20, 30)  #La parcela catastral 1907401VK4810H del simulador (urbana)

# 1. El margen, en urbana (±0,50 m)
caso("igual a la catastral", simula('igual', [RC], True, comprobar=lambda r: r.uno_a_uno and r.margen == 0.5
                                    and r.cartografia == 'urbana' and r.catastrales == [sim.RC]))
caso("desplazada 0,49 m: cumple", simula('d049', [rect(X0 + 0.49, Y0, 20, 30)], True))
caso("desplazada 0,51 m: no cumple, dice el tramo y el desplazamiento que la metería", simula(
    'd051', [rect(X0 + 0.51, Y0, 20, 30)], False, comprobar=lambda r: not r.dentro_margen and r.tramos
    and abs(r.tramos[0].distancia - 0.51) < 0.02 and r.desplazamiento is not None and abs(r.desplazamiento[0] + 0.51) < 0.02))
caso("un vértice 0,45 m hacia fuera (en diagonal): cumple", simula('v045', [poligono(
    [(X0, Y0), (X0, Y0 + 30), (X0 + 20.318, Y0 + 30.318), (X0 + 20, Y0)])], True))
caso("un vértice 0,45 m en X y 0,45 m en Y (0,64 m): no cumple, y no propone desplazar (es ese vértice)", simula(
    'v064', [poligono([(X0, Y0), (X0, Y0 + 30), (X0 + 20.45, Y0 + 30.45), (X0 + 20, Y0)])], False,
    comprobar=lambda r: r.desplazamiento is None and abs(r.separacion - 0.636) < 0.01))
caso("un vértice 0,70 m hacia fuera: no cumple y dice dónde", simula(
    'v070', [poligono([(X0, Y0), (X0, Y0 + 30), (X0 + 20.5, Y0 + 30.5), (X0 + 20, Y0)])], False,
    comprobar=lambda r: r.tramos and abs(r.tramos[0].distancia - 0.707) < 0.02 and r.tramos[0].x > X0 + 19
    and r.tramos[0].y > Y0 + 29 and r.desplazamiento is None))
caso("0,45 m hacia fuera por todos los lados: las esquinas quedan a 0,64 m", simula(
    'fuera045', [rect(X0 - 0.45, Y0 - 0.45, 20.9, 30.9)], False, comprobar=lambda r: not r.dentro_margen
    and abs(r.separacion - 0.636) < 0.01))
caso("0,40 m hacia dentro: contorno dentro, pero la superficie difiere un 6,6 %", simula(
    'dentro040', [rect(X0 + 0.4, Y0 + 0.4, 19.2, 29.2)], False, comprobar=lambda r: r.dentro_margen
    and not r.dentro_superficie and 6.5 < r.diferencia < 6.7))
caso("0,20 m hacia dentro: contorno y superficie (3,3 %) dentro", simula('dentro020', [rect(X0 + 0.2, Y0 + 0.2, 19.6, 29.6)], True))
caso("con un patio: los huecos no cuentan para el contorno", simula('patio', [poligono(
    [(X0, Y0), (X0, Y0 + 30), (X0 + 20, Y0 + 30), (X0 + 20, Y0)], [[(X0 + 8, Y0 + 12), (X0 + 9, Y0 + 12), (X0 + 9, Y0 + 13),
                                                                     (X0 + 8, Y0 + 13)]])], True))

# 2. Rústica (±2,00 m) y margen elegido a mano
CAMINO = rect(X0, Y0 - 6, 60, 6)  #29071A00709001, rústica
caso("rústica desplazada 1,5 m: cumple con ±2 m", simula('rustica15', [rect(X0 + 1.5, Y0 - 6, 60, 6)], True,
                                                       comprobar=lambda r: r.margen == 2.0 and r.cartografia == 'rústica'))
caso("rústica con el margen urbano elegido a mano: no cumple", simula('rustica15u', [rect(X0 + 1.5, Y0 - 6, 60, 6)], False,
                                                                     forzado='urbana'))
caso("urbana con el margen rústico elegido a mano: 1,2 m cumple", simula('urbana12r', [rect(X0 + 1.2, Y0, 20, 30)], True,
                                                                        forzado='rústica'))

# 3. Varias parcelas, ninguna, en grados
caso("el GML abarca dos parcelas catastrales: compara con las dos y avisa de que no es 1:1", simula(
    'dos', [rect(X0, Y0, 40, 30)], True, comprobar=lambda r: len(r.catastrales) == 2 and not r.uno_a_uno
    and 'IDG-NO-1A1' in [i.codigo for i in r.incidencias]))
caso("dos recintos (segregación) frente a una parcela: no es 1:1", simula(
    'segregacion', [rect(X0, Y0, 20, 18), rect(X0, Y0 + 18, 20, 12)], True, comprobar=lambda r: not r.uno_a_uno))
caso("lejos de cualquier parcela: lo dice", lambda: (lambda s: (
    s.resultado is not None and not s.resultado.catastrales and not s.resultado.cumple
    and 'IDG-SIN-PARCELA' in [i.codigo for i in s.resultado.incidencias], resumen(s)))(
    idg.comprobar_gml(gml('lejos', [rect(X0 + 300, Y0, 20, 30)]))))


def en_grados():
    g = geo.transformar(rect(X0 + 0.2, Y0, 20, 30), QgsCoordinateReferenceSystem('EPSG:25830'), 4326)
    texto, _ = gp.construir([gp.ParcelaGML('Nueva_1', gp.LOCAL, rect(X0, Y0, 1, 1))], 25830)
    lista = ' '.join(f'{q.y():.9f} {q.x():.9f}' for q in g.asPolygon()[0])
    texto = re.sub(r'(<gml:posList[^>]*>)[^<]*', lambda m: m.group(1) + lista, texto, count=1)
    ruta = os.path.join(carpeta, 'grados.gml')
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write(texto.replace('EPSG/0/25830', 'EPSG/0/4326'))
    s = idg.comprobar_gml(ruta)
    return (s.resultado is not None and s.resultado.cumple and s.epsg == 25830
            and 'IDG-GRADOS' in [i.codigo for i in s.resultado.incidencias]), resumen(s)


caso("GML en EPSG:4326 (latitud, longitud): se compara en su huso", en_grados)


def grande():
    inicio = time.time()
    s = idg.comprobar_gml(gml('grande', [rect(X0 + 5001, Y0, 1200, 1000)]))
    segundos = time.time() - inicio
    return (s.resultado is not None and not s.resultado.cumple and s.resultado.desplazamiento is not None
            and segundos < 30), (round(segundos, 1), resumen(s))


caso("parcela de 1,2 km desplazada 1 m: rápido, no cumple y dice el desplazamiento", grande)

# 4. Lo que no se puede comprobar
caso("GML de edificios: lo dice", lambda: (lambda s: (s.resultado is None and 'edificios' in s.errores[0].mensaje, resumen(s)))(
    idg.comprobar_gml(os.path.join(DATOS, 'edificio_sintetico.gml'))))
caso("GML mal formado: lo dice", lambda: (lambda s: (s.resultado is None and 'XML' in s.errores[0].mensaje, resumen(s)))(
    idg.comprobar_gml(os.path.join(DATOS, 'mal_formado.gml'))))


def sin_red():
    servicios.pedir = lambda url: (b'', 'Host ovc.catastro.meh.es not found (simulado)')
    try:
        s = idg.comprobar_gml(gml('sinred', [RC]))
    finally:
        servicios.pedir = sim.pedir
    return s.resultado is None and bool(s.errores), resumen(s)


caso("sin internet: lo dice", sin_red)


def informe():
    s = idg.comprobar_gml(gml('informe', [rect(X0 + 0.7, Y0, 20, 30)]))
    texto = idg.html(s)
    return ('No cumpliría' in texto and texto.count('<svg') == 2 and 'Detalle del tramo' in texto and 'Simulación no oficial' in texto
            and 'BOE-A-2020-12111' in texto and '&lt;' not in texto.split('<body>')[1][:50]), texto[:200]


caso("informe HTML: veredicto, croquis general y detalle del tramo, aviso de simulación y la norma", informe)


# 5. La utilidad
def barra(dw):
    return ' '.join([i.text() for i in dw.messageBar.items()] + [e.text() for i in dw.messageBar.items()
                                                                  for e in i.findChildren(QLabel)])


def utilidad():
    dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
    pu = dw.pestanaUtilidades
    pu.utilidades.setCurrentIndex(6)
    bloque = pu.identidad
    sin_fichero = not bloque.comprobarBoton.isEnabled()
    pu.soltar([gml('panel', [rect(X0 + 0.7, Y0, 20, 30)])])
    dw.messageBar.clearWidgets()
    informe_ruta = bloque.comprobar(segundo_plano=False)
    negativo = (informe_ruta is not None and os.path.isfile(informe_ruta) and 'No cumpliría' in bloque.resultado.text()
                and 'No cumpliría' in barra(dw))
    capas = bloque.ver_en_mapa()
    mapa = capas is not None and len(capas) == 4 and capas[0].name() == "Fuera del margen"
    #Otra vez: el grupo anterior se sustituye, no se acumula
    bloque.ver_en_mapa()
    grupos = [g for g in QgsProject.instance().layerTreeRoot().findGroups(True) if g.customProperty(idg.__name__) or
              g.name().startswith('Identidad gráfica')]
    un_grupo = len(grupos) == 1
    #Positivo
    bloque.fichero.setFilePath(gml('panel_bien', [rect(X0 + 0.2, Y0, 20, 30)]))
    dw.messageBar.clearWidgets()
    bloque.comprobar(segundo_plano=False)
    positivo = 'Cumpliría' in bloque.resultado.text() and 'Simulación no oficial' in barra(dw)
    #En segundo plano y se cierra el plugin a mitad: se cancela sin fallar
    bloque.comprobar()
    dw.cleanup()
    cerrado = bloque.tarea is None
    dw.deleteLater()
    QgsProject.instance().removeAllMapLayers()
    QgsProject.instance().layerTreeRoot().removeAllChildren()
    ok = sin_fichero and negativo and mapa and un_grupo and positivo and cerrado
    return ok, (sin_fichero, negativo, mapa, un_grupo, positivo, cerrado, bloque.resultado.text()[:300])


caso("utilidad: sin fichero, soltar, negativo con informe, ver en el mapa (sin acumular), positivo y cerrar a mitad", utilidad)

servicios.pedir = original
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
resultados["ninguna ventana emergente"] = not ventanas

print("=" * 60)
print("QGIS", Qgis.version(), "· Identidad gráfica: batería de casos")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, d in detalles.items():
    print("Detalles", nombre, ":", d)
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
