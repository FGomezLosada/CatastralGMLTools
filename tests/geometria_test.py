"""
Prueba de core/geometria.py con geometrías inventadas (coordenadas sintéticas cerca de Nerja, EPSG:25830). Sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py geometria_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import math

from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsGeometry, QgsPointXY

from catastral_gml_tools.core import geometria as geo
from catastral_gml_tools.core.incidencias import codigos, hay_errores

X0, Y0 = 421500.0, 4070500.0  #Origen de las geometrías de prueba


def wkt_rect(x, y, ancho, alto, antihorario=True):
    pts = [(x, y), (x + ancho, y), (x + ancho, y + alto), (x, y + alto), (x, y)]
    if not antihorario:
        pts.reverse()
    return '(' + ', '.join(f"{a} {b}" for a, b in pts) + ')'


# 1. Cuadrado dibujado en sentido antihorario: se reorienta a horario
cuadrado = QgsGeometry.fromWkt(f"POLYGON({wkt_rect(X0, Y0, 20, 10)})")
rec1, inc1 = geo.preparar(cuadrado, 'P1')
paso1 = (len(rec1) == 1 and geo.es_horario(rec1[0].exterior) and 'GEO-ORIENTACION' in codigos(inc1)
         and not hay_errores(inc1) and rec1[0].area_m2() == 200 and len(rec1[0].exterior) == 5)

# 2. Con un hueco dibujado en sentido horario: el hueco pasa a antihorario
con_hueco = QgsGeometry.fromWkt(f"POLYGON({wkt_rect(X0, Y0, 30, 30)}, {wkt_rect(X0 + 10, Y0 + 10, 5, 5, antihorario=False)})")
rec2, inc2 = geo.preparar(con_hueco)
paso2 = (geo.es_horario(rec2[0].exterior) and len(rec2[0].interiores) == 1 and not geo.es_horario(rec2[0].interiores[0])
         and rec2[0].area_m2() == 875)

# 3. Anillo abierto, repetidos y redondeo
anillo, repetidos, cerrado = geo.limpiar_anillo([(0.004, 0.0), (10.0, 0.0), (10.001, 0.002), (10.0, 10.0), (0.0, 10.0)])
paso3 = cerrado and repetidos == 1 and anillo[0] == anillo[-1] == (0.0, 0.0) and len(anillo) == 5
redondeo = geo.redondear(0.125) == 0.13 and geo.redondear(2.675) == 2.68 and geo.formatear(5) == '5.00'
m2 = geo.redondear_m2(10.5) == 11 and geo.redondear_m2(10.49) == 10

# 4. Multiparte: error y un recinto por parte
multi = QgsGeometry.fromWkt(f"MULTIPOLYGON(({wkt_rect(X0, Y0, 10, 10)}), ({wkt_rect(X0 + 50, Y0, 10, 10)}))")
rec4, inc4 = geo.preparar(multi)
paso4 = len(rec4) == 2 and 'GEO-MULTIPARTE' in codigos(inc4)

# 5. Pajarita (autointersección): error de geometría no válida
pajarita = QgsGeometry.fromWkt(f"POLYGON(({X0} {Y0}, {X0 + 10} {Y0 + 10}, {X0 + 10} {Y0}, {X0} {Y0 + 10}, {X0} {Y0}))")
_, inc5 = geo.preparar(pajarita)
paso5 = 'GEO-INVALIDA' in codigos(inc5)

# 6. Curvas: un círculo de radio 10 m se densifica con flecha < 2 cm
circulo = QgsGeometry.fromWkt(f"CURVEPOLYGON(CIRCULARSTRING({X0 + 10} {Y0}, {X0 - 10} {Y0}, {X0 + 10} {Y0}))")
rec6, inc6 = geo.preparar(circulo)
ext = rec6[0].exterior if rec6 else []
flecha = max((10 - math.hypot((a[0] + b[0]) / 2 - X0, (a[1] + b[1]) / 2 - Y0)) for a, b in zip(ext, ext[1:])) if ext else 99
paso6 = 'GEO-CURVAS' in codigos(inc6) and not hay_errores(inc6) and flecha < 0.02 and abs(rec6[0].area() - math.pi * 100) < 1

# 7. Punto interior en una parcela en U (el centroide cae fuera)
u = QgsGeometry.fromWkt(f"POLYGON(({X0} {Y0}, {X0 + 30} {Y0}, {X0 + 30} {Y0 + 30}, {X0 + 25} {Y0 + 30}, {X0 + 25} {Y0 + 5}, "
                        f"{X0 + 5} {Y0 + 5}, {X0 + 5} {Y0 + 30}, {X0} {Y0 + 30}, {X0} {Y0}))")
rec7, _ = geo.preparar(u)
centroide_fuera = not u.contains(u.centroid())
px, py = geo.punto_interior(rec7[0])
paso7 = centroide_fuera and u.contains(QgsGeometry.fromWkt(f"POINT({px} {py})")) and (px, py) == (geo.redondear(px), geo.redondear(py))

# 8. Z y M se quitan
con_z = QgsGeometry.fromWkt(f"POLYGON Z(({X0} {Y0} 5, {X0 + 10} {Y0} 5, {X0 + 10} {Y0 + 10} 5, {X0} {Y0} 5))")
rec8, inc8 = geo.preparar(con_z)
paso8 = 'GEO-2D' in codigos(inc8) and len(rec8[0].exterior) == 4 and not hay_errores(inc8)

# 9. Errores de entrada
_, inc9a = geo.preparar(QgsGeometry())
_, inc9b = geo.preparar(QgsGeometry.fromWkt(f"LINESTRING({X0} {Y0}, {X0 + 1} {Y0 + 1})"))
_, inc9c = geo.preparar(QgsGeometry.fromWkt(f"POLYGON(({X0} {Y0}, {X0 + 0.001} {Y0}, {X0} {Y0 + 0.001}, {X0} {Y0}))"))
_, inc9d = geo.preparar(QgsGeometry.fromWkt(f"POLYGON(({X0} {Y0}, {X0 + 5} {Y0}, {X0 + 10} {Y0}, {X0} {Y0}))"))
rec9e, inc9e = geo.preparar(QgsGeometry.fromWkt(f"POLYGON(({X0} {Y0}, {X0 + 5} {Y0}, {X0 + 10} {Y0}, {X0 + 10} {Y0 + 1}, {X0} {Y0}))"))
paso9 = ('GEO-VACIA' in codigos(inc9a) and 'GEO-TIPO' in codigos(inc9b) and 'GEO-POCOS-VERTICES' in codigos(inc9c)
         and 'GEO-ALINEADOS' in codigos(inc9d) and 'GEO-ALINEADOS' not in codigos(inc9e) and len(rec9e) == 1)

# 10. Sistemas de referencia
c25830 = QgsCoordinateReferenceSystem('EPSG:25830')
c4326 = QgsCoordinateReferenceSystem('EPSG:4326')
nerja_4326 = QgsGeometry.fromWkt("POINT(-3.876 36.758)")
canarias_4326 = QgsGeometry.fromWkt("POINT(-16.25 28.46)")
cataluna_4326 = QgsGeometry.fromWkt("POINT(2.17 41.39)")
galicia_4326 = QgsGeometry.fromWkt("POINT(-8.54 42.88)")
recomendados = [geo.epsg_recomendado(g, c4326) for g in (nerja_4326, canarias_4326, cataluna_4326, galicia_4326)]
src_ok = (geo.src_admitido(c25830) and not geo.src_admitido(c4326) and geo.epsg_de(c25830) == 25830
          and recomendados == [25830, 32628, 25831, 25829])
inc_4326 = geo.comprobar_src(c4326, nerja_4326)
inc_prov = geo.comprobar_src(QgsCoordinateReferenceSystem('EPSG:25829'), codigo_provincia='29')
inc_bien = geo.comprobar_src(c25830, cuadrado, codigo_provincia='29')
src_avisos = ('SRC-NO-ADMITIDO' in codigos(inc_4326) and 'EPSG:25830' in inc_4326[0].mensaje
              and 'SRC-PROVINCIA' in codigos(inc_prov) and not inc_bien)
husos = geo.husos_provincia('29') == (25830,) and geo.husos_provincia(3) == (25830, 25831) and geo.husos_provincia('31') == ()
transformada = geo.transformar(nerja_4326, c4326, 25830).asPoint()
transf = 420000 < transformada.x() < 423000 and 4067000 < transformada.y() < 4072000

#Huso que no corresponde a la posición o a la provincia (AU-30)
def punto_en(lon, lat, epsg):
    g = QgsGeometry.fromWkt(f"POINT({lon} {lat})").buffer(0.0005, 4)
    return geo.transformar(g, QgsCoordinateReferenceSystem('EPSG:4258'), epsg)


def huso(lon, lat, epsg, provincia=''):
    aviso = geo.aviso_huso(punto_en(lon, lat, epsg), QgsCoordinateReferenceSystem(f'EPSG:{epsg}'), epsg, provincia)
    return aviso.codigo if aviso else None


husos_ok = (huso(-3.88, 36.75, 25830) is None and huso(-8.4, 43.3, 25830) == 'SRC-HUSO'       #Nerja bien; A Coruña en 30
            and huso(2.65, 39.57, 25830) == 'SRC-HUSO' and huso(-15.4, 28.1, 25830) == 'SRC-HUSO'  #Palma y Las Palmas
            and huso(-15.4, 28.1, 32628) is None and huso(-8.4, 43.3, 25829) is None
            and huso(-7.0, 38.9, 25830, '06') is None and huso(-8.4, 43.3, 25830, '15') == 'SRC-PROVINCIA')
#Datum (AU-32): ED50 y Madrid 1870 avisan; ETRS89, WGS84 y REGCAN95 (a 32628) no
_datum = {e: geo.aviso_datum(QgsCoordinateReferenceSystem(f'EPSG:{e}'), d)
          for e, d in ((23030, 25830), (4230, 25830), (2062, 25830), (4326, 25830), (4258, 25830), (4083, 32628), (25830, 25830))}
datum_ok = ([e for e, a in _datum.items() if a is not None] == [23030, 4230, 2062]
            and _datum[23030].codigo == 'SRC-DATUM' and 'ED50' in _datum[23030].mensaje)
#REGCAN95 → WGS84 UTM 28: las mismas coordenadas (al centímetro)
_canaria = geo.transformar(QgsGeometry.fromWkt('POINT(458000 3110000)'), QgsCoordinateReferenceSystem('EPSG:4083'), 32628)
datum_ok = datum_ok and _canaria is not None and _canaria.asPoint().distance(QgsPointXY(458000, 3110000)) < 0.01

# 11. Huecos y solapes entre parcelas (AU-37, AU-40)
def _g(wkt):
    return QgsGeometry.fromWkt(wkt)


#A y B dejan entre sus entrantes (5 × 10 m cada uno) un hueco cerrado de 100 m²; C tiene un patio que rellena D (no es hueco)
_a = _g(f"POLYGON(({X0} {Y0}, {X0 + 20} {Y0}, {X0 + 20} {Y0 + 10}, {X0 + 15} {Y0 + 10}, {X0 + 15} {Y0 + 20}, {X0 + 20} {Y0 + 20}, "
        f"{X0 + 20} {Y0 + 30}, {X0} {Y0 + 30}, {X0} {Y0}))")
_b = _g(f"POLYGON(({X0 + 20} {Y0}, {X0 + 40} {Y0}, {X0 + 40} {Y0 + 30}, {X0 + 20} {Y0 + 30}, {X0 + 20} {Y0 + 20}, {X0 + 25} {Y0 + 20}, "
        f"{X0 + 25} {Y0 + 10}, {X0 + 20} {Y0 + 10}, {X0 + 20} {Y0}))")
_c = _g(f"POLYGON(({X0 + 100} {Y0}, {X0 + 130} {Y0}, {X0 + 130} {Y0 + 30}, {X0 + 100} {Y0 + 30}, {X0 + 100} {Y0}), "
        f"({X0 + 110} {Y0 + 10}, {X0 + 110} {Y0 + 20}, {X0 + 120} {Y0 + 20}, {X0 + 120} {Y0 + 10}, {X0 + 110} {Y0 + 10}))")
_d = _g(f"POLYGON(({X0 + 110} {Y0 + 10}, {X0 + 120} {Y0 + 10}, {X0 + 120} {Y0 + 20}, {X0 + 110} {Y0 + 20}, {X0 + 110} {Y0 + 10}))")
_patio = _g(f"POLYGON(({X0 + 200} {Y0}, {X0 + 230} {Y0}, {X0 + 230} {Y0 + 30}, {X0 + 200} {Y0 + 30}, {X0 + 200} {Y0}), "
            f"({X0 + 210} {Y0 + 10}, {X0 + 210} {Y0 + 20}, {X0 + 220} {Y0 + 20}, {X0 + 220} {Y0 + 10}, {X0 + 210} {Y0 + 10}))")
#Antes, el patio relleno de C contaba como «propio» y anulaba el hueco real entre A y B
_lejos = QgsGeometry(_d)
_lejos.translate(500, 0)
huecos_ok = (abs(geo.huecos([_a, _b, _c, _d]) - 100) < 0.01 and geo.huecos([_c, _d]) == 0
             and geo.huecos([_patio, _lejos]) == 0)
#Cuadrícula de 900 parcelas contiguas: ningún solape y rápido con el índice espacial
import time  # noqa: E402

_rejilla = [_g(f"POLYGON(({X0 + i * 10} {Y0 + j * 10}, {X0 + i * 10 + 10} {Y0 + j * 10}, {X0 + i * 10 + 10} {Y0 + j * 10 + 10}, "
               f"{X0 + i * 10} {Y0 + j * 10 + 10}, {X0 + i * 10} {Y0 + j * 10}))") for i in range(30) for j in range(30)]
_t = time.time()
_sol = geo.solapes(_rejilla + [_g(f"POLYGON(({X0 + 5} {Y0 + 5}, {X0 + 8} {Y0 + 5}, {X0 + 8} {Y0 + 8}, {X0 + 5} {Y0 + 8}, {X0 + 5} {Y0 + 5}))")])
solapes_ok = [(i, j) for i, j, *_ in _sol] == [(0, 900)] and time.time() - _t < 5

checks = {
    "huecos entre parcelas por geometría (patio relleno no compensa un hueco)": huecos_ok,
    "solapes con índice espacial (900 parcelas)": solapes_ok,
    "aviso de huso según la posición y la provincia": husos_ok,
    "aviso de datum antiguo (ED50, Madrid 1870); REGCAN95 pasa a 32628 sin moverse": datum_ok,
    "exterior a sentido horario, superficie y vértices": paso1,
    "hueco a sentido antihorario y superficie sin el hueco": paso2,
    "cierra anillos, quita repetidos y redondea a 2 decimales": paso3,
    "redondeo aritmético (0,125 → 0,13; 2,675 → 2,68)": redondeo,
    "superficie al m² (10,5 → 11)": m2,
    "multiparte: error y un recinto por parte": paso4,
    "autointersección: geometría no válida": paso5,
    "curvas densificadas con flecha < 2 cm": paso6,
    "punto interior aunque el centroide caiga fuera": paso7,
    "quita Z y M": paso8,
    "geometría vacía, no poligonal, con pocos vértices o alineados": paso9,
    "SRC admitidos y huso recomendado (península, Canarias, Cataluña, Galicia)": src_ok,
    "avisos de SRC no admitido y de huso de la provincia": src_avisos,
    "husos por provincia (Málaga, Alicante, Navarra)": husos,
    "transformación de SRC": transf,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· geometría")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'inc1': codigos(inc1), 'area2': rec2[0].area() if rec2 else None, 'inc6': codigos(inc6),
                        'flecha': flecha, 'recomendados': recomendados, 'inc8': codigos(inc8),
                        'inc9': (codigos(inc9a), codigos(inc9b), codigos(inc9c)), 'inc_prov': codigos(inc_prov),
                        'inc_bien': [str(i) for i in inc_bien], 'transf': (transformada.x(), transformada.y())})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
