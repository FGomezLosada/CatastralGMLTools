"""
Batería de casos de Utilidades «3. Informe de superficies y coordenadas» (plan de pruebas, docs/PLAN_PRUEBAS.md):
parcelas de cualquier forma, tamaño, número y huso, con y sin el Catastro (simulado), y lo que el usuario escribe en la
utilidad. Reglas de cada GML:
  - el informe se escribe sin excepción y es un HTML bien formado, con un croquis general y uno por parcela;
  - con el Catastro consultado, los linderos de cada parcela suman su perímetro (también con patios);
  - superficie UTM = la de la geometría; sobre el elipsoide, a menos del 0,3 % (factor de escala UTM en España);
  - la tabla de coordenadas tiene todos los vértices de cada anillo;
  - los textos del usuario (autor, identificadores) salen escapados.

Uso: tools\\probar.bat (o tools\\run_tests.py superficies_casos_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import datetime
import importlib.util
import math
import os
import tempfile
import time
import traceback
from html.parser import HTMLParser

import qgis.utils
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsGeometry
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import geometria as geo  # noqa: E402
from catastral_gml_tools.core import gml_lector as gl  # noqa: E402
from catastral_gml_tools.core import gml_parcela as gp  # noqa: E402
from catastral_gml_tools.core import superficies as su  # noqa: E402
from catastral_gml_tools.core.info import RAIZ  # noqa: E402
from catastral_gml_tools.gui import pestana_utilidades as pu_module  # noqa: E402

spec = importlib.util.spec_from_file_location('simulador_catastro', os.path.join(RAIZ, 'tests', 'simulador_catastro.py'))
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)
original = sim.instalar()

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))
dock_module.CatastralGMLToolsDockWidget.open_path = lambda self, ruta: None

carpeta = tempfile.mkdtemp(prefix='cgt superficies casos ñ_')
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
    anillos = [puntos] + list(huecos)
    return QgsGeometry.fromWkt('POLYGON(' + ', '.join('(' + ', '.join(f'{x} {y}' for x, y in a + [a[0]]) + ')'
                                                      for a in anillos) + ')')


def rect(x, y, a, b):
    return poligono([(x, y), (x, y + b), (x + a, y + b), (x + a, y)])


def circulo(cx, cy, r, n):
    return poligono([(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)])


def girado(geometria, angulo):
    copia = QgsGeometry(geometria)
    copia.rotate(angulo, copia.centroid().asPoint())
    return copia


def gml(nombre, parcelas, epsg=25830):
    ruta = os.path.join(carpeta, nombre + '.gml')
    lista = [gp.ParcelaGML(i, gp.SDGC if gp.refcat.es_rc_exacta(i) else gp.LOCAL, g, f'{n:02d}')
             for n, (i, g) in enumerate(parcelas, start=1)]
    ok, inc = gp.escribir(ruta, lista, epsg)
    assert ok, (nombre, [str(i) for i in inc if i.nivel == 'error'])
    return ruta


class Etiquetas(HTMLParser):
    """Comprueba que las etiquetas se abren y se cierran en orden (las vacías de HTML aparte)."""
    VACIAS = {'meta', 'br', 'img', 'hr', 'input', 'link', 'image', 'circle', 'path', 'line', 'polygon', 'polyline', 'rect',
              'use', 'stop'}

    def __init__(self):
        super().__init__()
        self.pila, self.errores, self.svg = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag == 'svg':
            self.svg += 1
        if tag not in self.VACIAS:
            self.pila.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag == 'svg':
            self.svg += 1

    def handle_endtag(self, tag):
        if tag in self.VACIAS:
            return
        if not self.pila or self.pila[-1] != tag:
            self.errores.append(f'</{tag}> con {self.pila[-3:]}')
        else:
            self.pila.pop()


def informe(ruta, consultar=True, autor='', inscrita=None):
    """(fichas, html, problemas) del informe del GML, como lo hace la utilidad."""
    lectura = gl.leer(ruta)
    catastrales, errores, _ = pu_module.consultar_red(lectura, consultar, False) if consultar else (None, [], b'')
    vecinas = catastrales or []
    lista = su.fichas(lectura, None if catastrales is None else [(e.local_id, e.geometria) for e in vecinas])
    texto = su.html(lectura, ruta, lista, inscrita, autor, consulta=None if catastrales is None else datetime.datetime.now(),
                    vecinas=vecinas)
    problemas = [f'red: {e.mensaje}' for e in errores]
    analizador = Etiquetas()
    analizador.feed(texto)
    if analizador.errores or analizador.pila:
        problemas.append(f'HTML: {analizador.errores[:2]} {analizador.pila[-3:]}')
    if analizador.svg != 1 + len(lista):
        problemas.append(f'croquis: {analizador.svg} (deben ser {1 + len(lista)})')
    for f, e in zip(lista, lectura.elementos):
        if abs(f.area_utm - e.geometria.area()) > 1e-6:
            problemas.append(f'{f.local_id}: superficie UTM')
        if not (f.area_utm > 0 and abs(f.area_elipsoide / f.area_utm - 1) < 0.003):
            problemas.append(f'{f.local_id}: elipsoide {f.area_elipsoide:.2f} frente a {f.area_utm:.2f}')
        suma = sum(li.longitud for li in f.linderos)
        if consultar and abs(suma - f.perimetro) > 0.01:
            problemas.append(f'{f.local_id}: linderos {suma:.3f} ≠ perímetro {f.perimetro:.3f}')
        if suma > f.perimetro + 0.01:
            problemas.append(f'{f.local_id}: linderos {suma:.3f} > perímetro {f.perimetro:.3f}')
        if any(li.rumbo not in su.RUMBOS for li in f.linderos):
            problemas.append(f'{f.local_id}: rumbo')
        for rol, puntos in f.anillos:
            if f'{rol} · {len(puntos)} vértices' not in texto:
                problemas.append(f'{f.local_id}: tabla de {rol}')
        if f'>{f.local_id}<' not in texto.replace('&amp;', '&'):
            problemas.append(f'{f.local_id}: no está en el informe')
    return lista, texto, problemas


def bien(ruta, comprobar=None):
    def prueba():
        lista, texto, problemas = informe(ruta)
        _, _, sin_red = informe(ruta, consultar=False)
        problemas += [f'sin consultar: {p}' for p in sin_red]
        if comprobar is not None:
            problemas += comprobar(lista, texto)
        return not problemas, (problemas[:6], [(f.local_id, [(li.rumbo, li.con[:20], round(li.longitud, 2))
                                                             for li in f.linderos]) for f in lista][:3])
    return prueba


# 1. Formas y tamaños
caso("segregación junto al Catastro", bien(gml('segregacion', [(sim.RC, rect(X0, Y0, 20, 18)), ('Seg_1', rect(X0, Y0 + 18, 20, 12))])))
caso("girada 30°", bien(gml('girada', [('Nueva_1', girado(rect(X0 + 300, Y0, 20, 30), 30))])))
caso("triángulo", bien(gml('triangulo', [('Nueva_1', poligono([(X0 + 300, Y0), (X0 + 300, Y0 + 30), (X0 + 330, Y0)]))])))
caso("en L", bien(gml('ele', [('Nueva_1', poligono([(X0 + 300, Y0), (X0 + 300, Y0 + 30), (X0 + 310, Y0 + 30),
                                                    (X0 + 310, Y0 + 10), (X0 + 330, Y0 + 10), (X0 + 330, Y0)]))])))


def con_hueco(lista, texto):
    huecos = [li for li in lista[0].linderos if li.tipo == 'hueco']
    total = sum(li.longitud for li in huecos)
    #El patio de 4 × 4 son 16 m de lindero «hacia el hueco»; su lado sur da al N (hacia dentro del patio)
    return ([] if abs(total - 16) < 0.01 and {li.rumbo for li in huecos} == {'N', 'E', 'S', 'O'} and 'Hueco 1' in texto
            else [f'hueco: {[(li.rumbo, round(li.longitud, 2)) for li in huecos]}'])


caso("con patio: los lados del patio son linderos y suman el perímetro", bien(gml('patio', [('Nueva_1', poligono(
    [(X0 + 300, Y0), (X0 + 300, Y0 + 30), (X0 + 320, Y0 + 30), (X0 + 320, Y0)],
    [[(X0 + 305, Y0 + 5), (X0 + 309, Y0 + 5), (X0 + 309, Y0 + 9), (X0 + 305, Y0 + 9)]]))]), con_hueco))
caso("con el patio como otra parcela del GML", bien(gml('patio_parcela', [
    ('Nueva_1', poligono([(X0 + 300, Y0), (X0 + 300, Y0 + 30), (X0 + 320, Y0 + 30), (X0 + 320, Y0)],
                         [[(X0 + 305, Y0 + 5), (X0 + 309, Y0 + 5), (X0 + 309, Y0 + 9), (X0 + 305, Y0 + 9)]])),
    ('Nueva_2', rect(X0 + 305, Y0 + 5, 4, 4))]),
    lambda lista, texto: [] if abs(sum(li.longitud for li in lista[0].linderos if li.con == 'Nueva_2') - 16) < 0.01
    and not any(li.tipo == 'hueco' for li in lista[0].linderos) else ['patio']))
caso("redonda de 64 vértices", bien(gml('redonda', [('Nueva_1', circulo(X0 + 300, Y0, 15, 64))])))
caso("500 vértices", bien(gml('quinientos', [('Nueva_1', circulo(X0 + 300, Y0, 60, 500))])))
caso("estrecha de 200 × 2 m", bien(gml('estrecha', [('Nueva_1', rect(X0 + 300, Y0, 200, 2))])))
caso("de 1 m²", bien(gml('pequena', [('Nueva_1', rect(X0 + 300, Y0, 1, 1))])))
caso("de 1,2 km junto a otra grande", bien(gml('grande', [('Nueva_1', rect(X0 + 6200, Y0, 1200, 900))])))
caso("isla: rodeada de suelo sin parcela", bien(gml('isla', [('Nueva_1', rect(X0 + 300, Y0, 20, 30))]),
                                               lambda lista, texto: [] if {li.tipo for li in lista[0].linderos} == {'sin parcela'}
                                               else ['isla']))
caso("dos zonas separadas", bien(gml('separadas', [('Nueva_1', rect(X0 + 300, Y0, 20, 30)), ('Nueva_2', rect(X0 + 800, Y0, 20, 30))])))
_inicio = time.time()
caso("35 parcelas en cuadrícula (menos de 60 s)", lambda: (lambda r: (r[0] and time.time() - _inicio < 60, (
    round(time.time() - _inicio), r[1])))(bien(gml('treinta_y_cinco', [(f'P_{i}', rect(X0 + 300 + (i % 7) * 20, Y0 + (i // 7) * 30, 20, 30))
                                                                       for i in range(35)]))()))
caso("huso 29 (Galicia), junto a una catastral", bien(gml('huso29', [('Nueva_1', geo.transformar(
    rect(sim.X29 - 20, sim.Y29, 20, 30), QgsCoordinateReferenceSystem('EPSG:25830'), 25829))], 25829),
    lambda lista, texto: [] if any(li.con == sim.RC_HUSO_29 for li in lista[0].linderos) else ['no linda con la catastral']))
caso("Canarias (EPSG:32628)", bien(gml('canarias', [('Nueva_1', rect(450000, 3100000, 20, 30))], 32628)))


# 2. Lo que escribe el usuario
def cabida(texto, esperado):
    def prueba():
        try:
            valor = su.leer_cabida(texto)
        except ValueError:
            valor = 'error'
        return valor == esperado, valor
    return prueba


for _texto, _esperado in (('1250', 1250.0), ('1250,5', 1250.5), ('1250.5', 1250.5), ('1.250', 1250.0), ('1.250,5', 1250.5),
                          ('1 250,5', 1250.5), ('12.500.000', 12500000.0), ('1,250.5', 1250.5), (' 620,50 m² ', 620.5),
                          ('', None), ('0', 'error'), ('-5', 'error'), ('abc', 'error'), ('1,2,3', 'error')):
    caso(f"cabida «{_texto}»", cabida(_texto, _esperado))


def autor_escapado():
    _, texto, _ = informe(os.path.join(carpeta, 'segregacion.gml'), autor='<script>alert(1)</script> & Cía')
    return '<script>' not in texto and '&lt;script&gt;' in texto and '&amp; Cía' in texto, texto[texto.find('Cía') - 80:][:120]


caso("autor con < > &: escapado en el informe", autor_escapado)


def umbrales():
    lista = su.fichas(gl.leer(os.path.join(carpeta, 'segregacion.gml')))
    total = sum(f.area_utm for f in lista)  #600 m²
    salen = [len(su.comparar_cabida(total, inscrita)[2]) for inscrita in (600, 590, 560, 500)]
    return salen[0] >= 1 and salen[0] >= salen[1] >= salen[2] and salen[3] == 0, salen


caso("umbrales de la Ley Hipotecaria según la diferencia", umbrales)


# 3. La utilidad
def barra(dw):
    return ' '.join([i.text() for i in dw.messageBar.items()] + [e.text() for i in dw.messageBar.items()
                                                                  for e in i.findChildren(QLabel)])


def no_valen():
    dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
    pu = dw.pestanaUtilidades
    pu.utilidades.setCurrentIndex(2)
    textos = {}
    otros = {'edificios': os.path.join(DATOS, 'edificio_sintetico.gml'),
             'mal formado': os.path.join(DATOS, 'mal_formado.gml'), 'no existe': os.path.join(carpeta, 'no_existe.gml')}
    with open(os.path.join(carpeta, 'segregacion.gml'), encoding='utf-8') as f:
        en4326 = f.read().replace('EPSG/0/25830', 'EPSG/0/4326')
    otros['EPSG:4326'] = os.path.join(carpeta, 'en4326.gml')
    with open(otros['EPSG:4326'], 'w', encoding='utf-8') as f:
        f.write(en4326)
    for nombre, ruta in otros.items():
        pu.origenSup.setFilePath(ruta)
        textos[nombre] = (pu.informeBoton.isEnabled(), 'conviértalo' in pu.estadoSup.text() or nombre == 'no existe')
    #Un 3.0 sí vale (el informe solo lee la geometría) y lo dice
    pu.origenSup.setFilePath(os.path.join(DATOS, 'parcela_cp30_sintetica.gml'))
    textos['3.0'] = (not pu.informeBoton.isEnabled(), 'CP 3.0' in pu.estadoSup.text())
    dw.deleteLater()
    return all(not activo and dice for activo, dice in textos.values()), textos


caso("utilidad: edificios, mal formado, 4326 o inexistente no dejan crear el informe; un 3.0 sí", no_valen)


def utilidad():
    dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
    pu = dw.pestanaUtilidades
    pu.utilidades.setCurrentIndex(2)
    pu.ortofoto.setChecked(False)
    ruta = os.path.join(carpeta, 'segregacion.gml')
    pu.origenSup.setFilePath(ruta)
    #Cabida «1.250» (millares): se toma como 1250 m², no 1,25
    pu.cabida.setText('1.250')
    hecho = pu.crear_informe(segundo_plano=False)
    with open(hecho, encoding='utf-8') as f:
        millares = '1 250,00 m²' in f.read()
    #El sitio del informe ocupado por una carpeta: aviso, sin fallar
    otro = gml('ocupado', [('Nueva_1', rect(X0 + 300, Y0, 20, 30))])
    os.makedirs(su.ruta_por_defecto(otro), exist_ok=True)
    pu.origenSup.setFilePath(otro)
    dw.messageBar.clearWidgets()
    ocupado = pu.crear_informe(segundo_plano=False) is None and 'No se ha podido escribir' in barra(dw)
    #El GML se borra después de elegirlo: aviso, no un informe vacío
    borrado = gml('borrado', [('Nueva_1', rect(X0 + 300, Y0, 20, 30))])
    pu.origenSup.setFilePath(borrado)
    os.remove(borrado)
    dw.messageBar.clearWidgets()
    sin_fichero = (pu.crear_informe(segundo_plano=False) is None and 'No existe el fichero' in barra(dw)
                   and not os.path.isfile(su.ruta_por_defecto(borrado)))
    #Sin internet: el informe se hace sin linderos con el Catastro y lo dice
    pu.origenSup.setFilePath(ruta)
    pu.cabida.setText('')
    sim_pedir = pu_module.cmp.servicios.pedir
    pu_module.cmp.servicios.pedir = lambda url: (b'', 'Host ovc.catastro.meh.es not found (simulado)')
    dw.messageBar.clearWidgets()
    sin_red = pu.crear_informe(segundo_plano=False) is not None and 'Sin linderos con el Catastro' in barra(dw)
    pu_module.cmp.servicios.pedir = sim_pedir
    #Se cierra el plugin con la consulta en marcha: se cancela sin fallar
    pu.crear_informe()
    tarea = pu.tarea_sup
    dw.cleanup()
    cerrado = pu.tarea_sup is None and (tarea is None or tarea.isCanceled() or tarea.status() >= 3)
    dw.deleteLater()
    ok = millares and ocupado and sin_fichero and sin_red and cerrado
    return ok, (millares, ocupado, sin_fichero, sin_red, cerrado, barra(dw)[:200])


caso("utilidad: cabida con millares, informe que no se puede escribir, GML borrado, sin red y cerrar a mitad", utilidad)

pu_module.cmp.servicios.pedir = original
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
resultados["ninguna ventana emergente"] = not ventanas

print("=" * 60)
print("QGIS", Qgis.version(), "· Informe de superficies: batería de casos")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, d in detalles.items():
    print("Detalles", nombre, ":", d)
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
