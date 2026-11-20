"""
Gráficos SVG de los informes (petición del 19/11/2026, maqueta G aprobada con los cuatro): core/graficos.py y su uso en
el informe de superficies (reparto entre parcelas y cabida inscrita), en «Comparar dos GML» (desplazamiento de cada
vértice frente a ±1 cm) y en la identidad gráfica de Validar (separación a lo largo del contorno frente al margen).

Se comprueba que cada gráfico sale cuando toca y no cuando no aporta, que marca en rojo lo que pasa la tolerancia y lo
cuenta, que cada marca lleva su valor al pasar el ratón (<title>), que el SVG es XML válido y que los informes los llevan.
Sin internet.

Uso: tools\\probar.bat graficos_test.py

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os
import tempfile
import traceback
import xml.etree.ElementTree as ET  # nosec B405 (solo lee el SVG que genera la propia prueba)
from types import SimpleNamespace

from qgis.core import Qgis, QgsGeometry

from catastral_gml_tools.core import comparar_gml as cg  # noqa: E402
from catastral_gml_tools.core import gml_lector as gl  # noqa: E402
from catastral_gml_tools.core import gml_parcela as gp  # noqa: E402
from catastral_gml_tools.core import graficos as g  # noqa: E402
from catastral_gml_tools.core import identidad as idg  # noqa: E402
from catastral_gml_tools.core import superficies as su  # noqa: E402

resultados, detalles = {}, {}
carpeta = tempfile.mkdtemp(prefix='cgt graficos ñ_')
X0, Y0 = 421500.0, 4070500.0
ROJO = g.FUERA


def comprobar(nombre, condicion, detalle=''):
    resultados[nombre] = bool(condicion)
    if not condicion and detalle:
        detalles[nombre] = detalle


def rect(x, y, w, h):
    return QgsGeometry.fromWkt(f"POLYGON(({x} {y}, {x} {y + h}, {x + w} {y + h}, {x + w} {y}, {x} {y}))")


def xml_valido(svg):
    try:
        ET.fromstring(svg)  # nosec B314
        return True
    except ET.ParseError as e:
        detalles['xml'] = str(e)
        return False


try:
    #Reparto
    comprobar("reparto: con una sola parcela no se dibuja", g.reparto([('A', 100, '#e8590c')]) == '')
    svg = g.reparto([('A', 300, '#e8590c'), ('B', 100, '#1971c2')])
    comprobar("reparto: dos parcelas, 75 % y 25 %, con su valor al pasar el ratón",
              '75,0 %' in svg and '25,0 %' in svg and svg.count('<title>') == 2 and xml_valido(svg), svg[:300])
    #Cabida
    comprobar("cabida: sin cabida inscrita no se dibuja", g.cabida(100, None) == '' and g.cabida(100, 0) == '')
    dentro, fuera = g.cabida(1475, 1430), g.cabida(1700, 1430)
    comprobar("cabida: dentro del 5 % en verde, con las bandas de ±5 % y ±10 %",
              g.BIEN in dentro and '+3,15 %' in dentro and '−5 %' in dentro and '+10 %' in dentro and xml_valido(dentro))
    comprobar("cabida: fuera del 10 % en rojo", ROJO in fuera and '+18,88 %' in fuera, fuera[-400:])
    #Vértices
    svg = g.barras_vertices([(1, 0.4), (2, 1.6), (3, 2.4), (4, 0.2)], 1.0, 'cm')
    comprobar("vértices: los que pasan ±1 cm en rojo y contados («2 de 4»)",
              svg.count(f'fill="{ROJO}"><title>') == 2 and '2 de 4 vértices pasan la tolerancia' in svg and xml_valido(svg),
              svg[-500:])
    svg = g.barras_vertices([(i, 0.3) for i in range(1, 300)], 1.0, 'cm')
    comprobar("vértices: con 299 vértices no se escriben los números (no se pisan) y dice que todos están dentro",
              'Los 299 vértices, dentro de la tolerancia' in svg and 'font-size="10">150<' not in svg and xml_valido(svg))
    comprobar("vértices: sin vértices no se dibuja", g.barras_vertices([], 1.0) == '')
    #Perfil
    muestras = [(d, 0.8 if 40 <= d <= 50 else 0.2) for d in range(0, 101)]
    svg = g.perfil(muestras, 0.5, 100.0)
    comprobar("perfil: el tramo fuera del margen, en rojo con su máximo y su recorrido al pasar el ratón",
              f'stroke="{ROJO}" stroke-width="3"' in svg and 'de 40,0 a 50,0 m' in svg and 'Margen ±0,50 m' in svg
              and xml_valido(svg), svg[-600:])
    #Perfil de la identidad: un GML 0,8 m al este de la catastral en un lado
    ref = rect(X0, Y0, 20, 30)
    rgga = QgsGeometry.fromWkt(f"POLYGON(({X0} {Y0}, {X0} {Y0 + 30}, {X0 + 20.8} {Y0 + 30}, {X0 + 20.8} {Y0}, {X0} {Y0}))")
    m, largo = idg.perfil(SimpleNamespace(rgga=rgga, referencia=ref))
    comprobar("identidad: el perfil recorre todo el contorno (101,6 m) y llega a 0,8 m en el lado movido",
              abs(largo - 101.6) < 0.01 and abs(max(s for _, s in m) - 0.8) < 0.01 and 100 <= len(m) <= 402,
              (largo, max(s for _, s in m) if m else None, len(m)))
    comprobar("identidad: sin resultado no hay perfil", idg.perfil(None) == ([], 0.0))

    #Informe de superficies: división en dos y cabida inscrita
    ruta = os.path.join(carpeta, 'division.gml')
    gp.escribir(ruta, [gp.ParcelaGML('Div_1', gp.LOCAL, rect(X0, Y0, 20, 18)),
                       gp.ParcelaGML('Div_2', gp.LOCAL, rect(X0, Y0 + 18, 20, 12))], 25830)
    lectura = gl.leer(ruta)
    texto = su.html(lectura, ruta, su.fichas(lectura), inscrita=580.0)
    comprobar("informe de superficies: lleva el reparto (60 % y 40 %) y la cabida inscrita",
              'Reparto de 600,00 m² entre 2 parcelas' in texto and '60,0 %' in texto and 'Inscrita 580,00 m²' in texto
              and '.grafico' in texto, texto[:200])

    comprobar("informe de superficies: apartados numerados con índice (1. Resumen…)",
              '<nav class="indice">' in texto and '<span class="num">1</span>Resumen</h2>' in texto
              and '<a href="#apartado-2">2. Comparación con la cabida inscrita</a>' in texto, texto[:400])
    #Comparar dos GML: el segundo con un vértice movido 3 cm
    a = os.path.join(carpeta, 'a.gml')
    b = os.path.join(carpeta, 'b.gml')
    gp.escribir(a, [gp.ParcelaGML('P1', gp.LOCAL, rect(X0, Y0, 20, 30))], 25830)
    movida = QgsGeometry.fromWkt(f"POLYGON(({X0} {Y0}, {X0} {Y0 + 30}, {X0 + 20.03} {Y0 + 30}, {X0 + 20} {Y0}, {X0} {Y0}))")
    gp.escribir(b, [gp.ParcelaGML('P1', gp.LOCAL, movida)], 25830)
    texto = cg.html(cg.comparar(a, b))
    comprobar("comparar dos GML: lleva el gráfico de vértices con la tolerancia de ±1 cm y el vértice que pasa",
              'Tolerancia de la Sede ±1 cm' in texto and '1 de 4 vértices pasan la tolerancia' in texto, texto[-1500:])
    comprobar("comparar dos GML: en el croquis, el vértice que pasa ±1 cm rodeado en rojo",
              texto.count('r="7" fill="none" stroke="#c92a2a"') == 1,
              texto.count('r="7" fill="none" stroke="#c92a2a"'))
    comprobar("los números llevan punto de miles (1.475,00)", g._num(1475.0) == '1.475,00' and g._num(1234567.891, 1) == '1.234.567,9',
              g._num(1475.0))
except Exception:  # noqa: BLE001
    resultados["sin excepciones"] = False
    detalles["excepción"] = traceback.format_exc()[-1500:]

print("=" * 60)
print("QGIS", Qgis.version(), "· Gráficos SVG de los informes")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, d in detalles.items():
    print("Detalles", nombre, ":", d)
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
