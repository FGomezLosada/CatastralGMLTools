"""
Batería de casos de Utilidades «4. Ajustar a la cartografía catastral» (plan de pruebas, docs/PLAN_PRUEBAS.md):
transformaciones conocidas que el cálculo debe recuperar, puntos con ruido, con un error grueso, alineados, repetidos o
muy juntos, ficheros de puntos de cualquier forma, y GML de parcela y de edificio de cualquier tipo. Reglas:
  - nunca una excepción ni una ventana; el GML del levantamiento no se toca;
  - con puntos exactos, los parámetros se recuperan (1 mm en el GML); con ruido, el error medio lo refleja;
  - lo que no determina la transformación o hace dudar de ella se dice con un mensaje que se entiende;
  - el GML de parcela ajustado pasa la Validar del plugin sin errores, conserva identificadores y no abre solapes ni
    rendijas entre parcelas; el de edificio solo cambia de coordenadas.

Uso: tools\\probar.bat (o tools\\run_tests.py ajuste_casos_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import math
import os
import random
import re
import tempfile
import traceback

import qgis.utils
from qgis.core import Qgis, QgsGeometry
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import ajuste as aj  # noqa: E402
from catastral_gml_tools.core import gml_lector as gl  # noqa: E402
from catastral_gml_tools.core import gml_parcela as gp  # noqa: E402
from catastral_gml_tools.core import validador  # noqa: E402
from catastral_gml_tools.core.info import RAIZ  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))
dock_module.CatastralGMLToolsDockWidget.open_path = lambda self, ruta: None

carpeta = tempfile.mkdtemp(prefix='cgt ajustar casos ñ_')
DATOS = os.path.join(RAIZ, 'tests', 'data', 'gml')
X0, Y0 = 421500.0, 4070500.0
RC = '1907401VK4810H'
resultados, detalles = {}, {}
azar = random.Random(20261019)


def caso(nombre, funcion):
    try:
        ok, detalle = funcion()
        resultados[nombre] = bool(ok)
        if not ok:
            detalles[nombre] = detalle
    except Exception:  # noqa: BLE001
        resultados[nombre] = False
        detalles[nombre] = traceback.format_exc()[-900:]


def rect(x, y, a, b):
    return QgsGeometry.fromWkt(f"POLYGON(({x} {y}, {x} {y + b}, {x + a} {y + b}, {x + a} {y}, {x} {y}))")


def leer(ruta):
    with open(ruta, 'rb') as f:
        return f.read()


def semejanza(giro_grados, ppm, cx, cy, centro=(X0, Y0)):
    """Transformación de la Sede que gira y escala alrededor de centro y luego desplaza (cx, cy)."""
    g = math.radians(giro_grados)
    k = 1 + ppm * 1e-6
    a, b = k * math.cos(g), k * math.sin(g)
    x0, y0 = centro
    return aj.Transformacion(a, -b, x0 - a * x0 + b * y0 + cx, b, a, y0 - b * x0 - a * y0 + cy)


def pares_de(t, puntos, ruido=0.0):
    pares = []
    for n, (x, y) in enumerate(puntos, start=1):
        xc, yc = t.aplicar(x, y)
        pares.append(aj.Par(x, y, xc + azar.gauss(0, ruido) if ruido else xc, yc + azar.gauss(0, ruido) if ruido else yc,
                            str(n)))
    return pares


ESQUINAS = [(X0, Y0), (X0, Y0 + 30), (X0 + 20, Y0 + 30), (X0 + 20, Y0), (X0 + 10, Y0 + 15)]
LEJOS = [(X0 - 50, Y0 - 50), (X0 - 50, Y0 + 80), (X0 + 70, Y0 + 80), (X0 + 70, Y0 - 50)]


def diferencia_en(t1, t2, puntos=ESQUINAS):
    """Mayor distancia (m) entre lo que dan las dos transformaciones en esos puntos."""
    return max(math.hypot(t1.aplicar(x, y)[0] - t2.aplicar(x, y)[0], t1.aplicar(x, y)[1] - t2.aplicar(x, y)[1])
               for x, y in puntos)


# 1. El cálculo recupera transformaciones conocidas
def recupera(metodo, t, puntos, ruido=0.0, tolerancia=0.001, emc=None):
    def prueba():
        ajuste = aj.calcular(pares_de(t, puntos, ruido), metodo)
        d = diferencia_en(ajuste.transformacion, t)
        ok = d <= tolerancia and (emc is None or emc[0] <= ajuste.emc <= emc[1])
        return ok, (round(d, 4), round(ajuste.emc, 4), ajuste.transformacion.textos())
    return prueba


T_TRAS = aj.Transformacion(cx=0.44, cy=-0.12)
T_SEM = semejanza(0.1, 50, 1.3, -0.8)
T_AFIN = aj.Transformacion(1.0001, 0.0002, 0.0, -0.0001, 0.9998, 0.0)
T_AFIN = aj.Transformacion(T_AFIN.ax, T_AFIN.bx, X0 - T_AFIN.ax * X0 - T_AFIN.bx * Y0 + 0.5,
                           T_AFIN.ay, T_AFIN.by, Y0 - T_AFIN.ay * X0 - T_AFIN.by * Y0 - 0.3)
caso("traslación con 1 punto", recupera(aj.TRASLACION, T_TRAS, ESQUINAS[:1]))
caso("traslación con 5 puntos", recupera(aj.TRASLACION, T_TRAS, ESQUINAS))
caso("semejanza (0,1°, +50 ppm) con 2 puntos", recupera(aj.SEMEJANZA, T_SEM, LEJOS[::2]))
caso("semejanza con 4 puntos", recupera(aj.SEMEJANZA, T_SEM, LEJOS))
caso("afín con 3 puntos", recupera(aj.AFIN, T_AFIN, LEJOS[:3]))
caso("afín con 4 puntos", recupera(aj.AFIN, T_AFIN, LEJOS))
caso("semejanza con ruido de 2 cm: error medio de unos 2 cm", recupera(aj.SEMEJANZA, T_SEM, LEJOS + ESQUINAS, ruido=0.02,
                                                                      tolerancia=0.05, emc=(0.005, 0.05)))
caso("en el huso 29 (X de 150 000) y en Canarias (Y de 3 100 000)", lambda: (lambda a, b: (
    a[0] and b[0], (a[1], b[1])))(recupera(aj.SEMEJANZA, semejanza(0.05, 20, 2, 1, (150000, 4700000)),
                                           [(150000 + dx, 4700000 + dy) for dx, dy in ((0, 0), (90, 10), (40, 80))])(),
                                  recupera(aj.AFIN, semejanza(-0.05, -30, -1, 2, (450000, 3100000)),
                                           [(450000 + dx, 3100000 + dy) for dx, dy in ((0, 0), (90, 10), (40, 80), (5, 60))])()))


def inversa():
    t = T_SEM.inversa()
    vuelta = max(math.hypot(*(a - b for a, b in zip(t.aplicar(*T_SEM.aplicar(x, y)), (x, y)))) for x, y in ESQUINAS)
    return vuelta < 1e-6, vuelta


caso("la inversa deshace el ajuste", inversa)


def grueso():
    pares = pares_de(T_SEM, LEJOS + ESQUINAS)
    pares[2] = aj.Par(pares[2].x, pares[2].y, pares[2].xc + 1.0, pares[2].yc, pares[2].nombre)
    ajuste = aj.calcular(pares, aj.SEMEJANZA)
    peor = ajuste.residuos.index(max(ajuste.residuos))
    return peor == 2 and ajuste.residuos[2] > 0.5 and ajuste.emc > 0.1, [round(r, 3) for r in ajuste.residuos]


caso("un punto con 1 m de error: es el de mayor residuo", grueso)


# 2. Puntos que no sirven: lo dice
def no_sirve(metodo, pares, palabra):
    def prueba():
        try:
            aj.calcular(pares, metodo)
        except ValueError as e:
            return palabra in str(e), str(e)
        return False, 'sin error'
    return prueba


caso("semejanza con 1 punto", no_sirve(aj.SEMEJANZA, pares_de(T_SEM, ESQUINAS[:1]), 'al menos 2'))
caso("afín con 2 puntos", no_sirve(aj.AFIN, pares_de(T_AFIN, LEJOS[:2]), 'al menos 3'))
caso("afín con 3 puntos alineados", no_sirve(aj.AFIN, pares_de(T_AFIN, [(X0, Y0), (X0 + 10, Y0 + 10), (X0 + 20, Y0 + 20)]),
                                              'alineados'))
caso("semejanza con el mismo punto dos veces", no_sirve(aj.SEMEJANZA, pares_de(T_SEM, [(X0, Y0), (X0, Y0)]), 'repetidos'))
caso("sin puntos", no_sirve(aj.TRASLACION, [], 'al menos 1'))


def avisa(metodo, pares, palabra, tamano=40.0):
    def prueba():
        ajuste = aj.calcular(pares, metodo)
        textos = aj.avisos(ajuste, pares, tamano)
        return any(palabra in t for t in textos), textos
    return prueba


def no_avisa(metodo, pares, tamano=40.0):
    def prueba():
        textos = aj.avisos(aj.calcular(pares, metodo), pares, tamano)
        return not textos, textos
    return prueba


caso("dos puntos a 33 cm: muy juntos", avisa(aj.SEMEJANZA, pares_de(T_SEM, [(X0, Y0), (X0 + 0.33, Y0)]), 'muy juntos'))
caso("escala de +2000 ppm: anómala", avisa(aj.SEMEJANZA, pares_de(semejanza(0, 2000, 0, 0), LEJOS), 'Escala anómala'))
caso("giro de 2°: anómalo", avisa(aj.SEMEJANZA, pares_de(semejanza(2, 0, 0, 0), LEJOS), 'Giro anómalo'))
caso("desplazamiento de 11 km (otro huso): lo dice", avisa(aj.TRASLACION, pares_de(aj.Transformacion(cx=11000, cy=300), ESQUINAS),
                                                          'Desplazamiento de'))
caso("desplazamiento de 11 km con giro (CX grande): lo dice", avisa(
    aj.SEMEJANZA, pares_de(semejanza(0.1, 20, 11000, 0), LEJOS), 'Desplazamiento de'))
caso("un ajuste normal (1,5 m y 0,1°): sin avisos", no_avisa(aj.SEMEJANZA, pares_de(T_SEM, LEJOS)))


# 3. Ficheros de puntos
def lee(texto, n, saltadas=(), primero=None):
    def prueba():
        pares, salto = aj.leer_pares(texto)
        ok = len(pares) == n and list(salto) == list(saltadas)
        if primero is not None and pares:
            ok = ok and all(abs(a - b) < 1e-9 for a, b in zip((pares[0].x, pares[0].y, pares[0].xc, pares[0].yc), primero))
        return ok, (len(pares), salto, [(p.nombre, p.x, p.y, p.xc, p.yc) for p in pares][:2])
    return prueba


P1 = (421500.0, 4070500.0, 421500.44, 4070499.88)
caso("puntos separados por espacios", lee("421500 4070500 421500.44 4070499.88\n421520 4070530 421520.44 4070529.88", 2,
                                         primero=P1))
caso("punto y coma con coma decimal (Excel)", lee("X;Y;X';Y'\n421500,00;4070500,00;421500,44;4070499,88\n", 1, [1], P1))
caso("CSV con comas y cabecera", lee("x,y,xc,yc\n421500.00,4070500.00,421500.44,4070499.88\r\n", 1, [1], P1))
caso("tabuladores y número de punto delante", lee("1\t421500\t4070500\t421500.44\t4070499.88\n2\t421520\t4070530\t421520.44\t4070529.88",
                                                 2, primero=P1))
caso("nombre del punto delante", lee("EsquinaNO 421500 4070500 421500.44 4070499.88", 1, primero=P1))
caso("nombre con espacios delante", lee("Esquina NO 421500 4070500 421500.44 4070499.88", 1, primero=P1))
caso("comentarios, líneas vacías y una con tres números", lee("# puntos del levantamiento\n\n421500 4070500 421500.44 4070499.88\n"
                                                              "421520 4070530 421520.44\n", 1, [4], P1))
caso("fichero sin ningún punto", lee("esto no son puntos\n", 0, [1]))


# 4. El GML ajustado
def gml(nombre, parcelas, epsg=25830):
    ruta = os.path.join(carpeta, nombre + '.gml')
    ok, inc = gp.escribir(ruta, parcelas, epsg)
    assert ok, inc
    return ruta


def guardar(nombre, contenido):
    ruta = os.path.join(carpeta, nombre)
    with open(ruta, 'wb') as f:
        f.write(contenido.encode('utf-8') if isinstance(contenido, str) else contenido)
    return ruta


SEGREGACION = gml('segregacion', [gp.ParcelaGML(RC, gp.SDGC, rect(X0, Y0, 20, 18), '01'),
                                  gp.ParcelaGML('Seg_1', gp.LOCAL, rect(X0, Y0 + 18, 20, 12))])


def ajusta(ruta, t, escribe=True, palabra=''):
    def prueba():
        antes = leer(ruta)
        destino = aj.ruta_ajustada(ruta)
        if os.path.isfile(destino):
            os.remove(destino)
        ok, inc = aj.escribir_ajustado(ruta, destino, t)
        problemas = []
        if leer(ruta) != antes:
            problemas.append('original tocado')
        if ok != escribe:
            problemas.append(f'escrito={ok}')
        mensajes = ' '.join(i.mensaje for i in inc if i.nivel == 'error')
        if palabra and palabra not in mensajes:
            problemas.append(f'falta «{palabra}»')
        if ok:
            a, b = gl.leer(ruta), gl.leer(destino)
            if [e.local_id for e in a.elementos] != [e.local_id for e in b.elementos]:
                problemas.append('identificadores')
            for ea, eb in zip(a.elementos, b.elementos):
                esperada = t.geometria(ea.geometria)
                if esperada.hausdorffDistance(eb.geometria) > 0.0072:  #Redondeo al centímetro (0,5 cm en X y en Y)
                    problemas.append(f'{ea.local_id}: no está donde dice la transformación')
            informe = validador.validar(destino)
            if informe.errores:
                problemas.append(f'Validar: {[i.codigo for i in informe.errores]}')
            if any(i.codigo in ('SOLAPE', 'HUECO', 'HUECOS') for i in informe.incidencias):
                problemas.append('solapes o rendijas entre parcelas')
        return not problemas, (problemas, [i.mensaje[:100] for i in inc][:3])
    return prueba


caso("segregación con traslación", ajusta(SEGREGACION, T_TRAS))
caso("segregación con giro y escala: sin rendijas entre las dos", ajusta(SEGREGACION, T_SEM))
caso("parcela con hueco y afín", ajusta(gml('hueco', [gp.ParcelaGML(RC, gp.SDGC, QgsGeometry.fromWkt(
    f"POLYGON(({X0} {Y0}, {X0} {Y0 + 30}, {X0 + 20} {Y0 + 30}, {X0 + 20} {Y0}, {X0} {Y0}),"
    f"({X0 + 5} {Y0 + 5}, {X0 + 9} {Y0 + 5}, {X0 + 9} {Y0 + 9}, {X0 + 5} {Y0 + 9}, {X0 + 5} {Y0 + 5}))"), '01')]), T_AFIN))


def con_fecha():
    texto = leer(SEGREGACION).decode('utf-8')
    texto = re.sub(r'(<cp:beginLifespanVersion>)[^<]*', r'\g<1>2019-05-02T10:30:00', texto)
    ruta = guardar('con_fecha.gml', texto)
    ok, _ = aj.escribir_ajustado(ruta, aj.ruta_ajustada(ruta), T_TRAS)
    return ok and '2019-05-02T10:30:00' in leer(aj.ruta_ajustada(ruta)).decode('utf-8'), ok


caso("se conserva la fecha del levantamiento", con_fecha)


def edificio(ruta, t):
    def prueba():
        destino = aj.ruta_ajustada(ruta)
        ok, inc = aj.escribir_ajustado(ruta, destino, t)
        if not ok:
            return False, [i.mensaje for i in inc]
        a, b = gl.leer(ruta), gl.leer(destino)
        donde = max(t.geometria(ea.geometria).hausdorffDistance(eb.geometria) for ea, eb in zip(a.elementos, b.elementos))
        quitar = re.compile(rb'<gml:pos(?:List)?\b[^>]*>[^<]*<')
        resto_igual = quitar.sub(b'', leer(ruta)).replace(b'ISO-8859-1', b'utf-8') == quitar.sub(b'', leer(destino)) \
            or a.version != b.version
        validos = not [i for i in validador.validar(destino).errores]
        return donde < 0.0072 and validos and b.version == a.version, (donde, resto_igual, validos)
    return prueba


EDIFICIO = leer(os.path.join(DATOS, 'edificio_sintetico.gml')).decode('iso-8859-1')  #En ISO-8859-1, con acentos
caso("edificio (BU 2.0) en UTF-8: solo cambian las coordenadas", edificio(guardar(
    'edificio_utf8.gml', EDIFICIO.replace('encoding="ISO-8859-1"', 'encoding="utf-8"')), T_SEM))
caso("edificio en ISO-8859-1 con acentos: sale en UTF-8 legible", lambda: (lambda r: (
    r[0] and 'SINTÉTICO' in leer(aj.ruta_ajustada(os.path.join(DATOS, 'edificio_sintetico.gml'))).decode('utf-8'), r[1]))(
    edificio(os.path.join(DATOS, 'edificio_sintetico.gml'), T_TRAS)()))
caso("parcela 3.0: pide convertirla antes", ajusta(os.path.join(DATOS, 'parcela_cp30_sintetica.gml'), T_TRAS, False, 'conviértalo'))
caso("edificio con Z: pide 2D", ajusta(guardar('edificio_z.gml', re.sub(
    r'<gml:posList srsDimension="2"([^>]*)>([^<]*)<', lambda m: '<gml:posList srsDimension="3"' + m.group(1) + '>' + ' '.join(
        f'{a} {b} 10' for a, b in zip(m.group(2).split()[::2], m.group(2).split()[1::2])) + '<',
    EDIFICIO.replace('encoding="ISO-8859-1"', 'encoding="utf-8"'))), T_TRAS, False, 'Z'))
caso("GML mal formado: error", ajusta(os.path.join(DATOS, 'mal_formado.gml'), T_TRAS, False))


def destino_igual():
    ok, inc = aj.escribir_ajustado(SEGREGACION, SEGREGACION, T_TRAS)
    return not ok and 'la Sede pide los dos' in inc[0].mensaje, [i.mensaje for i in inc]


def carpeta_falta():
    ok, inc = aj.escribir_ajustado(SEGREGACION, os.path.join(carpeta, 'no hay', 'x.gml'), T_TRAS)
    return not ok and bool(inc), [i.mensaje for i in inc]


caso("el ajustado no puede sustituir al levantamiento", destino_igual)
caso("carpeta de destino que no existe: error claro", carpeta_falta)


def parametros():
    pares = pares_de(T_SEM, LEJOS)
    ajuste = aj.calcular(pares, aj.SEMEJANZA)
    texto = aj.texto_parametros(ajuste, pares, SEGREGACION, aj.ruta_ajustada(SEGREGACION), 25830, tamano=36)
    numeros = dict(re.findall(r'^(AX|BX|CX|AY|BY|CY) = (\S+)$', texto, re.M))
    t = aj.Transformacion(*(float(numeros[n]) for n in ('AX', 'BX', 'CX', 'AY', 'BY', 'CY')))
    #Lo que se escribe (12 y 4 decimales) basta: da el mismo GML al milímetro
    return (len(numeros) == 6 and diferencia_en(t, T_SEM) < 0.001 and 'BOE-A-2021-5949' in texto and 'AVISOS' not in texto
            and texto.count('\n') > 20), (numeros, diferencia_en(t, T_SEM))


caso("fichero de parámetros: los valores escritos reproducen el ajuste", parametros)


# 5. La utilidad
def barra(dw):
    return ' '.join([i.text() for i in dw.messageBar.items()] + [e.text() for i in dw.messageBar.items()
                                                                  for e in i.findChildren(QLabel)])


def utilidad():
    dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
    pu = dw.pestanaUtilidades
    pu.utilidades.setCurrentIndex(3)
    bloque = pu.ajuste
    #Un 3.0: no deja crear y dice por qué
    bloque.origenAj.setFilePath(os.path.join(DATOS, 'parcela_cp30_sintetica.gml'))
    antiguo = not bloque.crearAjBoton.isEnabled() and 'conviértalo' in bloque.resumenAj.text()
    #Puntos de un fichero con una cabecera, uno mal y uno con 1 m de error: el aviso de líneas saltadas y el residuo en naranja
    bloque.origenAj.setFilePath(SEGREGACION)
    pares = pares_de(T_SEM, LEJOS + ESQUINAS)
    lineas = ["X;Y;X';Y'"] + [f"{p.x:.3f};{p.y:.3f};{p.xc + (1.0 if n == 2 else 0):.3f};{p.yc:.3f}".replace('.', ',')
                              for n, p in enumerate(pares)] + ["421500;4070500;1"]
    puntos = guardar('puntos.csv', '﻿' + '\n'.join(lineas))
    bloque.metodo.setCurrentIndex(bloque.metodo.findData(aj.SEMEJANZA))
    dw.messageBar.clearWidgets()
    importados = bloque.importar_fichero(puntos) == len(pares) and 'saltado las líneas 1, 11' in barra(dw)
    naranja = bloque.tabla.item(2, 4) is not None and bloque.tabla.item(2, 4).font().bold()
    #Se quita el punto malo: sin naranja, y se crea el ajustado con sus parámetros
    bloque.tabla.clearSelection()
    bloque.tabla.selectRow(2)
    bloque.quitar()
    limpio = all(not (bloque.tabla.item(f, 4) and bloque.tabla.item(f, 4).font().bold()) for f in range(bloque.tabla.rowCount()))
    destino = os.path.join(carpeta, 'desde_panel.gml')
    bloque.destinoAj.setFilePath(destino)
    dw.messageBar.clearWidgets()
    creado = bloque.crear() == destino and os.path.isfile(aj.ruta_parametros(destino)) and 'GML ajustado' in barra(dw)
    #Una celda con letras: la fila se señala y no cuenta
    bloque.tabla.item(0, 0).setText('cuatrocientos')
    letras = 'Filas con números que no se entienden: 1' in bloque.resumenAj.text()
    #Parámetros conocidos con coma decimal
    bloque.metodo.setCurrentIndex(bloque.metodo.findData(aj.CONOCIDOS))
    for campo, valor in zip(bloque.parametros, ('1', '0', '0,44', '0', '1', '-0,12')):
        campo.setText(valor)
    bloque.recalcular()
    conocidos = bloque.ajuste is not None and abs(bloque.ajuste.transformacion.cx - 0.44) < 1e-12
    bloque.parametros[0].setText('uno')
    bloque.recalcular()
    mal_escritos = bloque.ajuste is None and 'deben ser números' in bloque.resumenAj.text() and not bloque.crearAjBoton.isEnabled()
    #Se cierra el panel con la captura activa: la herramienta se suelta
    bloque.capturarBoton.setChecked(True)
    pu.cancelar_tareas()
    suelta = not bloque.capturarBoton.isChecked()
    dw.deleteLater()
    ok = antiguo and importados and naranja and limpio and creado and letras and conocidos and mal_escritos and suelta
    return ok, (antiguo, importados, naranja, limpio, creado, letras, conocidos, mal_escritos, suelta, barra(dw)[:200])


caso("utilidad: 3.0, importar con líneas malas, residuo naranja, quitar, crear, letras, conocidos y cerrar", utilidad)

for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
resultados["ninguna ventana emergente"] = not ventanas

print("=" * 60)
print("QGIS", Qgis.version(), "· Ajustar a la cartografía catastral: batería de casos")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, d in detalles.items():
    print("Detalles", nombre, ":", d)
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
