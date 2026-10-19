"""
Batería de casos de «Comparar dos GML» (mejora 34): no sabemos qué van a comparar los usuarios, así que se prueban los
casos posibles para que el resultado sea correcto (o, si no se puede, lo diga) y nunca falle:

  - el mismo recinto escrito de otra forma (otro vértice de inicio, sentido contrario, más decimales, otro huso, en
    geográficas con un orden de ejes u otro, sin srsName, con Z, como GML genérico de QGIS, esquema 3.0 frente a 4.0);
  - cambios de forma (vértice quitado, alineado o no; hueco; recinto de una parcela en varios trozos);
  - operaciones (división o segregación: una parcela frente a varias; agrupación);
  - ficheros de otra cosa (parcelas frente a construcciones, fincas distintas, el mismo id en otro sitio, ids repetidos,
    geometría inválida, sin geometría legible, vacío, mal formado, que no existe);
  - muchos recintos (tiempo) y cancelar a medias; la tarea en segundo plano de la interfaz.

Uso: tools\\probar.bat (o tools\\run_tests.py comparar_casos_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os
import re
import shutil
import tempfile
import time

import qgis.utils
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsFeedback,
    QgsGeometry,
    QgsPointXY,
)
from qgis.PyQt.QtWidgets import QMessageBox

import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import comparar_gml as cg  # noqa: E402
from catastral_gml_tools.core import conversor as cv  # noqa: E402
from catastral_gml_tools.core import gml_parcela as gp  # noqa: E402
from catastral_gml_tools.core.info import RAIZ  # noqa: E402
from catastral_gml_tools.gui import bloque_comparar as bc_mod  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))

carpeta = tempfile.mkdtemp(prefix='cgt_comparar_casos_')
X0, Y0 = 421500.0, 4070500.0
RC = '1907401VK4810H'
resultados = {}
fallos = {}


def wkt(puntos, huecos=()):
    anillos = [puntos] + list(huecos)
    return QgsGeometry.fromWkt('POLYGON(' + ', '.join('(' + ', '.join(f'{x} {y}' for x, y in a + [a[0]]) + ')'
                                                      for a in anillos) + ')')


def rect(x, y, w, h):
    return [(x, y), (x, y + h), (x + w, y + h), (x + w, y)]


def escribir(nombre, parcelas, epsg=25830):
    ruta = os.path.join(carpeta, nombre)
    ok, inc = gp.escribir(ruta, parcelas, epsg)
    assert ok, (nombre, inc)
    return ruta


def guardar(nombre, texto):
    ruta = os.path.join(carpeta, nombre)
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write(texto)
    return ruta


def texto(ruta):
    with open(ruta, encoding='utf-8') as f:
        return f.read()


def coords(texto_gml, funcion):
    """Cambia los números de cada posList/pos con funcion(x, y) -> texto del par."""
    def cambiar(m):
        n = [float(v) for v in m.group(2).split()]
        return m.group(1) + ' '.join(funcion(n[i], n[i + 1]) for i in range(0, len(n), 2)) + m.group(3)
    return re.sub(r'(<gml:pos(?:List)?\b[^>]*>)([^<]*)(</gml:pos(?:List)?>)', cambiar, texto_gml)


def caso(nombre, funcion):
    """Ejecuta un caso; una excepción es un fallo (la comparación no debe fallar nunca)."""
    try:
        resultados[nombre] = bool(funcion())
    except Exception as e:  # noqa: BLE001
        import traceback
        resultados[nombre] = False
        fallos[nombre] = traceback.format_exc()[-800:] + repr(e)


def veredictos(c):
    return [p.veredicto() for p in c.parejas]


BASE = rect(X0, Y0, 20, 30)
A = escribir('a.gml', [gp.ParcelaGML(RC, gp.SDGC, wkt(BASE), '01')])


# 1. El mismo recinto escrito de otra forma
def inicio_y_sentido():
    otro = [BASE[2], BASE[3], BASE[0], BASE[1]][::-1]  #Otro vértice de inicio y sentido contrario
    ruta = guardar('sentido.gml', texto(A).replace(
        re.search(r'<gml:posList[^>]*>([^<]*)<', texto(A)).group(1),
        ' '.join(f'{x:.2f} {y:.2f}' for x, y in otro + [otro[0]])))
    return cg.comparar(A, ruta).iguales()


def mas_decimales():
    ruta = guardar('decimales.gml', coords(texto(A), lambda x, y: f'{x + 0.004:.4f} {y - 0.003:.4f}'))
    c = cg.comparar(A, ruta)
    return c.iguales() and ('Decimales de las coordenadas', '2', '4') in c.generales


def otro_huso():
    t = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:25830'), QgsCoordinateReferenceSystem('EPSG:25829'),
                               QgsCoordinateTransformContext())

    def a29(x, y):
        q = t.transform(QgsPointXY(x, y))
        return f'{q.x():.3f} {q.y():.3f}'
    ruta = guardar('huso29.gml', coords(texto(A), a29).replace('EPSG/0/25830', 'EPSG/0/25829'))
    c = cg.comparar(A, ruta)
    return c.iguales() and any('EPSG:25829' in n for n in c.notas)


def geograficas(orden_lat_lon, epsg):
    t = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:25830'), QgsCoordinateReferenceSystem(f'EPSG:{epsg}'),
                               QgsCoordinateTransformContext())

    def a_geo(x, y):
        q = t.transform(QgsPointXY(x, y))
        return f'{q.y():.9f} {q.x():.9f}' if orden_lat_lon else f'{q.x():.9f} {q.y():.9f}'
    ruta = guardar(f'geo_{epsg}_{orden_lat_lon}.gml', coords(texto(A), a_geo).replace('EPSG/0/25830', f'EPSG/0/{epsg}'))
    c = cg.comparar(A, ruta)
    nota = any('latitud, longitud' in n for n in c.notas)
    return c.iguales() and nota == orden_lat_lon


def los_dos_geograficos():
    lat_lon = os.path.join(carpeta, 'geo_4258_True.gml')
    lon_lat = os.path.join(carpeta, 'geo_4326_False.gml')
    c = cg.comparar(lat_lon, lon_lat)
    return c.iguales() and any('EPSG:25830' in n for n in c.notas)  #Se comparan en el huso UTM de la zona


def sin_srsname():
    ruta = guardar('sin_srs.gml', re.sub(r' srsName="[^"]*"', '', texto(A)))
    c = cg.comparar(A, ruta)
    return c.iguales() and any('no declara el sistema de referencia' in n for n in c.notas)


def con_z():
    ruta = guardar('con_z.gml', coords(texto(A), lambda x, y: f'{x:.2f} {y:.2f} 125.40').replace(
        'srsDimension="2"', 'srsDimension="3"'))
    return cg.comparar(A, ruta).iguales()


def generico_qgis():
    ogr = ('<?xml version="1.0" encoding="utf-8" ?>\n<ogr:FeatureCollection gml:id="aFeatureCollection" '
           'xmlns:ogr="http://ogr.maptools.org/" xmlns:gml="http://www.opengis.net/gml/3.2">\n'
           f'<ogr:featureMember><ogr:{RC} gml:id="ES.SDGC.CP.{RC}"><ogr:geometryProperty><gml:MultiSurface '
           'srsName="urn:ogc:def:crs:EPSG::25830" gml:id="g0"><gml:surfaceMember><gml:Polygon gml:id="g00"><gml:exterior>'
           '<gml:LinearRing><gml:posList>' + ' '.join(f'{x} {y}' for x, y in BASE + [BASE[0]]) + '</gml:posList>'
           '</gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></ogr:geometryProperty>'
           f'<ogr:localId>{RC}</ogr:localId><ogr:namespace>ES.SDGC.CP</ogr:namespace><ogr:label>01</ogr:label>'
           f'</ogr:{RC}></ogr:featureMember>\n</ogr:FeatureCollection>\n')
    c = cg.comparar(A, guardar('generico.gml', ogr))
    return (not c.errores and len(c.parejas) == 1 and c.parejas[0].iguales_geometria()
            and any('GML genérico' in n for n in c.notas))


def esquema_30():
    cp30 = os.path.join(RAIZ, 'tests', 'data', 'gml', 'parcela_cp30_sintetica.gml')
    destino = os.path.join(carpeta, 'cp30_v4.gml')
    ok, _, _, _ = cv.convertir(cp30, destino)
    c = cg.comparar(cp30, destino)
    return ok and not c.errores and all(p.iguales_geometria() for p in c.parejas) and c.generales[0][1] == 'CP 3.0'


caso("otro vértice de inicio y sentido contrario: iguales", inicio_y_sentido)
caso("más decimales (diferencias de milímetros): iguales", mas_decimales)
caso("otro huso UTM (25829): se pasa y son iguales", otro_huso)
caso("geográficas ETRS89 en latitud-longitud: iguales, y lo dice", lambda: geograficas(True, 4258))
caso("geográficas WGS84 en longitud-latitud: iguales, sin girar los ejes", lambda: geograficas(False, 4326))
caso("los dos en geográficas: se comparan en el huso UTM de la zona", los_dos_geograficos)
caso("sin srsName: se supone el del otro, y lo dice", sin_srsname)


def primero_geografico():
    lat_lon = os.path.join(carpeta, 'geo_4258_True.gml')
    c = cg.comparar(lat_lon, A)
    #Se compara en el UTM del segundo y la vista del primero queda en su sitio (no en el mar por los ejes girados)
    caja = c.vista_a.elementos[0].geometria.boundingBox()
    return c.iguales() and c.vista_a.epsg == 25830 and abs(caja.xMinimum() - X0) < 0.01 and abs(caja.yMinimum() - Y0) < 0.01


caso("el primero en geográficas latitud-longitud: se compara en el UTM del otro y se ve en su sitio", primero_geografico)
caso("coordenadas con Z: iguales", con_z)
caso("GML genérico (Guardar como de QGIS): se lee y lo dice", generico_qgis)
caso("esquema 3.0 frente a su conversión a 4.0: misma geometría", esquema_30)


# 2. Cambios de forma
def vertice_alineado():
    con = [BASE[0], (X0, Y0 + 15), BASE[1], BASE[2], BASE[3]]
    p = cg.comparar(A, escribir('alineado.gml', [gp.ParcelaGML(RC, gp.SDGC, wkt(con), '01')])).parejas[0]
    return p.veredicto() == "Misma geometría; cambian datos" and p.anadidos == 1 and p.quitados == 0


def vertice_quitado():
    sin = [BASE[0], BASE[1], BASE[2]]  #Triángulo: la esquina SE desaparece
    p = cg.comparar(A, escribir('triangulo.gml', [gp.ParcelaGML(RC, gp.SDGC, wkt(sin), '01')])).parejas[0]
    return p.veredicto().startswith("Distinto") and p.quitados == 1 and p.pierde > 290


def hueco():
    p = cg.comparar(A, escribir('hueco.gml', [gp.ParcelaGML(RC, gp.SDGC, wkt(BASE, [rect(X0 + 5, Y0 + 5, 4, 4)]), '01')])
                    ).parejas[0]
    return p.veredicto().startswith("Distinto") and abs(p.area_b - 584) < 1e-6 and p.anadidos == 4 and p.pierde > 15


def varios_recintos():
    #El escritor del plugin no deja escribir dos recintos (la Sede no los admite); otros programas sí
    miembro = re.search(r'<gml:surfaceMember>.*?</gml:surfaceMember>', texto(A), re.S).group(0)
    segundo = miembro.replace(re.search(r'<gml:posList[^>]*>([^<]*)<', miembro).group(1),
                              ' '.join(f'{x:.2f} {y:.2f}' for x, y in rect(X0 + 40, Y0, 5, 5) + [(X0 + 40, Y0)]))
    segundo = re.sub(r'gml:id="([^"]*)"', r'gml:id="\1_2"', segundo)
    ruta = guardar('dos_recintos.gml', texto(A).replace(miembro, miembro + segundo))
    igual = cg.comparar(ruta, ruta).iguales()
    p = cg.comparar(A, ruta).parejas[0]
    return igual and p.veredicto().startswith("Distinto") and p.gana > 24 and p.anadidos == 4


caso("vértice añadido en un lado (alineado): misma geometría, cambian los vértices", vertice_alineado)
caso("vértice quitado (cambia la forma): distinto, con lo que pierde", vertice_quitado)
caso("hueco nuevo: distinto, superficie y vértices del hueco", hueco)
caso("parcela en dos recintos: iguales consigo misma; frente a uno, lo que gana", varios_recintos)


# 3. Operaciones
def division():
    partes = escribir('division.gml', [gp.ParcelaGML('Div_1', gp.LOCAL, wkt(rect(X0, Y0, 20, 18))),
                                       gp.ParcelaGML('Div_2', gp.LOCAL, wkt(rect(X0, Y0 + 18, 20, 12)))])
    c = cg.comparar(A, partes)
    por_nombre = {p.nombre: p for p in c.parejas}
    pareja = por_nombre.get(f'{RC} ↔ Div_1')
    sola = por_nombre.get('Div_2')
    return (pareja is not None and pareja.por == 'geometría' and sola is not None and sola.a is None
            and any('Div_2' in q[2] for q in pareja.solapes) and any(RC in q[2] for q in sola.solapes)
            and any('comparte suelo con (del segundo): Div_2' in x for x in cg.resumen(c)))


def agrupacion():
    dos = escribir('dos.gml', [gp.ParcelaGML('P1', gp.LOCAL, wkt(rect(X0, Y0, 10, 30))),
                               gp.ParcelaGML('P2', gp.LOCAL, wkt(rect(X0 + 10, Y0, 10, 30)))])
    c = cg.comparar(dos, A)
    return (len(c.parejas) == 2 and sum(p.b is not None for p in c.parejas) == 1
            and all(p.solapes for p in c.parejas))


caso("división: la matriz con la mayor y «comparte suelo» con la otra", division)
caso("agrupación: dos parcelas frente a una", agrupacion)


# 4. Ficheros de otra cosa
def parcela_y_edificio():
    edificio = os.path.join(RAIZ, 'tests', 'data', 'gml', 'edificio_sintetico.gml')
    c = cg.comparar(A, edificio)
    return (not c.errores and all(p.a is None or p.b is None for p in c.parejas)
            and any('parcelas y el otro de construcciones' in n for n in c.notas))


def edificios_plantas():
    edificio = os.path.join(RAIZ, 'tests', 'data', 'gml', 'edificio_sintetico.gml')
    with open(edificio, encoding='iso-8859-1') as f:
        original = f.read()
    otro = os.path.join(carpeta, 'edificio_3plantas.gml')
    with open(otro, 'w', encoding='iso-8859-1') as f:
        f.write(original.replace('numberOfFloorsAboveGround>2<', 'numberOfFloorsAboveGround>3<'))
    c = cg.comparar(edificio, otro)
    edif = next(p for p in c.parejas if p.a is not None and p.a.local_id == 'Edificio_1')
    return edif.veredicto() == "Misma geometría; cambian datos" and ('Plantas', '2', '3') in edif.datos


def fincas_distintas():
    lejos = escribir('lejos.gml', [gp.ParcelaGML('2001001VK4820H', gp.SDGC, wkt(rect(X0 + 5000, Y0, 20, 30)), '01')])
    c = cg.comparar(A, lejos)
    return (veredictos(c) == ["Solo en el primero", "Solo en el segundo"]
            and any('no se tocan' in n and '5,00 km' not in n for n in c.notas))


def mismo_id_en_otro_sitio():
    lejos = escribir('mismo_id_lejos.gml', [gp.ParcelaGML(RC, gp.SDGC, wkt(rect(X0 + 2000, Y0 + 1000, 20, 30)), '01')])
    c = cg.comparar(A, lejos)
    return (len(c.parejas) == 1 and c.parejas[0].veredicto().startswith("Desplazado 2 236,07 m")
            and any('no se tocan' in n for n in c.notas))


def ids_repetidos():
    texto_a = texto(A)
    bloque = re.search(r'<member>.*</member>', texto_a, re.S)
    ruta = guardar('repetidos.gml', texto_a.replace(bloque.group(0), bloque.group(0) * 2)) if bloque else None
    if ruta is None:
        return True  #El escritor no usa <member>: el caso se cubre con el lector (no aplica)
    c = cg.comparar(A, ruta)
    return not c.errores and any('repite identificadores' in n for n in c.notas)


def geometria_invalida():
    pajarita = [(X0, Y0), (X0 + 20, Y0 + 30), (X0 + 20, Y0), (X0, Y0 + 30)]
    ruta = guardar('pajarita.gml', texto(A).replace(
        re.search(r'<gml:posList[^>]*>([^<]*)<', texto(A)).group(1),
        ' '.join(f'{x:.2f} {y:.2f}' for x, y in pajarita + [pajarita[0]])))
    c = cg.comparar(A, ruta)
    return not c.errores and len(c.parejas) >= 1 and bool(cg.html(c))


def sin_geometria():
    ruta = guardar('coma_decimal.gml', coords(texto(A), lambda x, y: f'{x:.2f} {y:.2f}'.replace('.', ',')))
    c = cg.comparar(A, ruta)
    return bool(c.errores) or any('sin geometría legible' in n for n in c.notas)


def vacios_y_malos():
    vacio = guardar('vacio.gml', '')
    malo = os.path.join(RAIZ, 'tests', 'data', 'gml', 'mal_formado.gml')
    c1, c2, c3 = cg.comparar(A, vacio), cg.comparar(malo, A), cg.comparar(A, os.path.join(carpeta, 'no_existe.gml'))
    return all(c.errores and not c.parejas and cg.resumen(c) for c in (c1, c2, c3))


caso("parcela frente a edificios: no se emparejan, y lo dice", parcela_y_edificio)
caso("edificios: cambian las plantas", edificios_plantas)
caso("fincas distintas: solo en uno y otro, y avisa de que no se tocan", fincas_distintas)
caso("el mismo id en otro sitio (srsName mal puesto): desplazado km, y avisa", mismo_id_en_otro_sitio)
caso("identificadores repetidos: se dice", ids_repetidos)
caso("geometría inválida (pajarita): compara sin fallar", geometria_invalida)
caso("coordenadas ilegibles (coma decimal): error o nota, sin fallar", sin_geometria)
caso("vacío, mal formado o inexistente: error claro", vacios_y_malos)


# 5. Muchos recintos, cancelar y la tarea de la interfaz
def muchos():
    parcelas = [gp.ParcelaGML(f'P{i}_{j}', gp.LOCAL, wkt(rect(X0 + i * 20, Y0 + j * 20, 20, 20)))
                for i in range(15) for j in range(15)]
    a = escribir('muchos.gml', parcelas)
    b = os.path.join(carpeta, 'muchos_desplazados.gml')
    with open(b, 'w', encoding='utf-8') as f:
        f.write(coords(texto(a), lambda x, y: f'{x + 0.05:.2f} {y:.2f}'))
    inicio = time.monotonic()
    c = cg.comparar(a, b)
    segundos = time.monotonic() - inicio
    return (len(c.parejas) == 225 and all(v.startswith("Desplazado 5,0 cm hacia E") for v in veredictos(c))
            and segundos < 60), segundos


def cancelar():
    feedback = QgsFeedback()
    feedback.cancel()
    c = cg.comparar(A, os.path.join(carpeta, 'decimales.gml'), feedback)
    return c.errores == ["Cancelado"]


_muchos = {}
caso("225 parcelas desplazadas: todas «Desplazado 5,0 cm» y en poco tiempo",
     lambda: _muchos.setdefault('r', muchos())[0])
caso("cancelar a medias: no da resultados a medias", cancelar)


def tarea_interfaz():
    dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
    bloque = dw.pestanaUtilidades.comparador
    bloque.gmlA.setFilePath(A)
    bloque.gmlB.setFilePath(os.path.join(carpeta, 'decimales.gml'))
    tarea = bc_mod.TareaComparar(bloque.rutas()[0], bloque.rutas()[1], bloque)
    bloque.tarea = tarea
    bloque.compararBoton.setEnabled(False)
    correcto = tarea.run()
    tarea.finished(correcto)
    hecho = 'Son iguales' in bloque.resultado.text() and bloque.compararBoton.isEnabled() and bloque.tarea is None
    #Cancelada: el botón vuelve y no se muestra nada nuevo
    bloque.resultado.clear()
    tarea = bc_mod.TareaComparar(bloque.rutas()[0], bloque.rutas()[1], bloque)
    bloque.tarea = tarea
    tarea.cancel()
    tarea.finished(False)
    cancelada = bloque.resultado.text() == '' and bloque.compararBoton.text() == "Comparar" and bloque.tarea is None
    #Al cerrar el plugin, la tarea en curso se cancela
    tarea = bc_mod.TareaComparar(bloque.rutas()[0], bloque.rutas()[1], bloque)
    bloque.tarea = tarea
    dw.cleanup()
    cierre = tarea.feedback.isCanceled() and bloque.tarea is None
    dw.deleteLater()
    return hecho and cancelada and cierre


caso("interfaz: tarea en segundo plano, cancelar y cerrar el plugin", tarea_interfaz)
shutil.rmtree(os.path.join(carpeta, 'no_existe'), ignore_errors=True)

for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
resultados["ninguna ventana emergente"] = not ventanas

print("=" * 60)
print("QGIS", Qgis.version(), "· comparar dos GML: batería de casos")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if 'r' in _muchos:
    print(f"  (225 parcelas: {_muchos['r'][1]:.1f} s)")
for nombre, traza in fallos.items():
    print("Excepción en", nombre, ":", traza)
if not all(resultados.values()):
    print("Detalles:", {n: '' for n, ok in resultados.items() if not ok})
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
