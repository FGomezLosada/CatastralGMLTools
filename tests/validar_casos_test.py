"""
Batería de casos de Validar (plan de pruebas, docs/PLAN_PRUEBAS.md): lectura y comprobaciones de cualquier GML que
traiga el usuario. Cada caso es un fichero «raro» con lo que el plugin debe decir (códigos de incidencia que tienen que
salir y que no deben salir); además, cada fichero se abre en la pestaña Validar, que no puede fallar ni abrir ventanas.

Uso: tools\\probar.bat (o tools\\run_tests.py validar_casos_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os
import re
import tempfile
import traceback

import qgis.utils
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsGeometry
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
import catastral_gml_tools.gui.pestana_validar as pv_module  # noqa: E402
from catastral_gml_tools.core import geometria as geo  # noqa: E402
from catastral_gml_tools.core import gml_lector as gl  # noqa: E402
from catastral_gml_tools.core import gml_parcela as gp  # noqa: E402
from catastral_gml_tools.core import validador  # noqa: E402
from catastral_gml_tools.core.incidencias import ERROR, INFO, Incidencia  # noqa: E402
from catastral_gml_tools.core.info import RAIZ  # noqa: E402

#Sin red: el esquema XSD se prueba en esquemas_test.py
pv_module.esquemas.validar = lambda datos, version, feedback=None: [Incidencia(INFO, 'XSD-VALIDO', "Cumple el esquema")]

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))

carpeta = tempfile.mkdtemp(prefix='cgt validar casos ñ_')  #Con espacios y una eñe en la ruta
DATOS = os.path.join(RAIZ, 'tests', 'data', 'gml')
X0, Y0 = 421500.0, 4070500.0
RC = '1907401VK4810H'


def rect(x, y, w, h):
    return QgsGeometry.fromWkt(f"POLYGON(({x} {y}, {x} {y + h}, {x + w} {y + h}, {x + w} {y}, {x} {y}))")


def leer(ruta):
    with open(ruta, 'rb') as f:
        return f.read()


def gml(parcelas, epsg=25830):
    texto, inc = gp.construir(parcelas, epsg)
    assert texto is not None, inc
    return texto


BASE = gml([gp.ParcelaGML(RC, gp.SDGC, rect(X0, Y0, 20, 30), '01')])
DOS = gml([gp.ParcelaGML(RC, gp.SDGC, rect(X0, Y0, 20, 30), '01'), gp.ParcelaGML('Seg_1', gp.LOCAL, rect(X0 + 20, Y0, 15, 30))])
POSLIST = re.search(r'(<gml:posList[^>]*>)([^<]*)(</gml:posList>)', BASE)


def con_poslist(texto, puntos, etiqueta=None):
    """El primer posList cambiado por esos puntos (y, si se da, por esa etiqueta de apertura)."""
    m = re.search(r'(<gml:posList[^>]*>)([^<]*)(</gml:posList>)', texto)
    numeros = ' '.join(f'{x} {y}' for x, y in puntos)
    return texto[:m.start()] + (etiqueta or m.group(1)) + numeros + m.group(3) + texto[m.end():]


R = [(X0, Y0), (X0, Y0 + 30), (X0 + 20, Y0 + 30), (X0 + 20, Y0), (X0, Y0)]
OGR = ('<?xml version="1.0" encoding="utf-8" ?>\n<ogr:FeatureCollection gml:id="aFeatureCollection" '
       'xmlns:ogr="http://ogr.maptools.org/" xmlns:gml="http://www.opengis.net/gml/3.2">\n'
       f'<ogr:featureMember><ogr:{RC} gml:id="x"><ogr:geometryProperty><gml:MultiSurface srsName="urn:ogc:def:crs:EPSG::25830" '
       'gml:id="g0"><gml:surfaceMember><gml:Polygon gml:id="g00"><gml:exterior><gml:LinearRing><gml:posList>'
       + ' '.join(f'{x} {y}' for x, y in R) + '</gml:posList></gml:LinearRing></gml:exterior></gml:Polygon>'
       f'</gml:surfaceMember></gml:MultiSurface></ogr:geometryProperty><ogr:localId>{RC}</ogr:localId></ogr:{RC}>'
       '</ogr:featureMember>\n</ogr:FeatureCollection>\n')
ARCO = BASE.replace('<gml:PolygonPatch>', '<gml:PolygonPatch>').replace(
    POSLIST.group(0), '<gml:posList srsDimension="2" count="5">' + ' '.join(f'{x} {y}' for x, y in R) + '</gml:posList>')
ARCO = ARCO.replace('<gml:LinearRing>', '<gml:Ring><gml:curveMember><gml:Curve gml:id="c1"><gml:segments><gml:Arc>', 1)
ARCO = ARCO.replace('</gml:LinearRing>', '</gml:Arc></gml:segments></gml:Curve></gml:curveMember></gml:Ring>', 1)
MUCHAS = gml([gp.ParcelaGML(f'P{i}', gp.LOCAL, rect(X0 + (i % 10) * 20, Y0 + (i // 10) * 30, 20, 30)) for i in range(35)])

#(nombre, contenido (texto o bytes), códigos que tienen que salir, códigos que no deben salir)
CASOS = [
    ("GML correcto", BASE, [], ['*ERROR']),
    ("dos parcelas correctas (segregación)", DOS, [], ['*ERROR']),
    ("esquema 3.0", leer(os.path.join(DATOS, 'parcela_cp30_sintetica.gml')), ['CP-30'], []),
    ("«Guardar como» de QGIS (genérico, etiqueta que empieza por número)", OGR, ['XML-MAL-FORMADO'], []),
    ("fichero vacío", b'', ['*ERROR'], []),
    ("texto que no es XML", "esto no es un GML", ['XML-MAL-FORMADO'], []),
    ("XML que no es un GML", '<?xml version="1.0"?><html><body>hola</body></html>', ['GML-SIN-ELEMENTOS'], []),
    ("UTF-8 con BOM", b'\xef\xbb\xbf' + BASE.encode('utf-8'), [], ['*ERROR']),
    ("ISO-8859-1 con acentos", BASE.replace('encoding="utf-8"', 'encoding="ISO-8859-1"').replace(
        '<cp:label>01</cp:label>', '<cp:label>01</cp:label><!-- Camiño, año -->').encode('iso-8859-1'), [], ['*ERROR']),
    ("UTM con srsName EPSG:4326: dice que el srsName está mal", BASE.replace('EPSG/0/25830', 'EPSG/0/4326'),
     ['SRC-NO-ADMITIDO'], []),
    #Prueba a mano del 20/10/2026: en grados, redondear al centímetro daba «sin superficie» y 0 m²
    ("EPSG:4326 de verdad (latitud, longitud): solo el SRC", con_poslist(BASE.replace('EPSG/0/25830', 'EPSG/0/4326'), [
        (f'{q.y():.9f}', f'{q.x():.9f}') for q in geo.transformar(QgsGeometry.fromWkt(
            'POLYGON((' + ', '.join(f'{x} {y}' for x, y in R) + '))'), QgsCoordinateReferenceSystem('EPSG:25830'),
            4326).asPolygon()[0]]), ['SRC-NO-ADMITIDO'], ['GEO-ALINEADOS', 'SUP-DISTINTA', 'DECIMALES', 'ANILLO-SENTIDO',
                                                         'ESBELTEZ']),
    ("sin srsName", re.sub(r' srsName="[^"]*"', '', BASE), ['SRC-FALTA'], []),
    ("srsName en un elemento distinto del resto", DOS.replace('EPSG/0/25830', 'EPSG/0/25829', 3), ['SRC-MEZCLADOS'], []),
    ("coordenadas con Z", con_poslist(BASE, [(x, y) for x, y in R], '<gml:posList srsDimension="3" count="5">').replace(
        ' '.join(f'{x} {y}' for x, y in R), ' '.join(f'{x} {y} 100.5' for x, y in R)), ['DIMENSION'], []),
    ("3 decimales", con_poslist(BASE, [(f'{x:.3f}', f'{y:.3f}') for x, y in R]), ['DECIMALES'], []),
    ("coma decimal", con_poslist(BASE, [(f'{x:.2f}'.replace('.', ','), f'{y:.2f}'.replace('.', ',')) for x, y in R]),
     ['COORDENADAS'], []),
    ("anillo abierto", con_poslist(BASE, R[:-1], '<gml:posList srsDimension="2" count="4">'), ['ANILLO-ABIERTO'], []),
    ("count que no cuadra", con_poslist(BASE, R, '<gml:posList srsDimension="2" count="7">'), ['ANILLO-COUNT'], []),
    ("anillo en sentido contrario", con_poslist(BASE, R[::-1]), ['ANILLO-SENTIDO'], []),
    ("pajarita (se corta a sí misma)", con_poslist(BASE, [(X0, Y0), (X0 + 20, Y0 + 30), (X0 + 20, Y0), (X0, Y0 + 30),
                                                          (X0, Y0)]), ['GEO-INVALIDA'], []),
    ("vértices repetidos seguidos", con_poslist(BASE, [R[0], R[1], R[1], R[2], R[3], R[0]],
                                                '<gml:posList srsDimension="2" count="6">'), ['ANILLO-REPETIDO'], ['*ERROR']),
    ("solo tres vértices alineados", con_poslist(BASE, [(X0, Y0), (X0 + 10, Y0), (X0 + 20, Y0), (X0, Y0)],
                                                 '<gml:posList srsDimension="2" count="4">'), ['*ERROR'], []),
    ("curvas (gml:Arc)", ARCO, ['GEO-CURVAS-GML'], []),
    ("hueco", gml([gp.ParcelaGML(RC, gp.SDGC, QgsGeometry.fromWkt(
        f"POLYGON(({X0} {Y0}, {X0} {Y0 + 30}, {X0 + 20} {Y0 + 30}, {X0 + 20} {Y0}, {X0} {Y0}),"
        f"({X0 + 5} {Y0 + 5}, {X0 + 9} {Y0 + 5}, {X0 + 9} {Y0 + 9}, {X0 + 5} {Y0 + 9}, {X0 + 5} {Y0 + 5}))"), '01')]), [], ['*ERROR']),
    ("identificador vacío", BASE.replace(f'<localId>{RC}</localId>', '<localId></localId>'), ['ID-VACIO'], []),
    ("identificador con espacios", DOS.replace('<localId>Seg_1</localId>', '<localId>Seg 1</localId>'), ['ID-CARACTERES'], []),
    ("identificador repetido", DOS.replace('<localId>Seg_1</localId>', f'<localId>{RC}</localId>'), ['ID-REPETIDO'], []),
    ("SDGC sin referencia catastral", DOS.replace('<localId>Seg_1</localId><namespace>ES.LOCAL.CP',
                                                  '<localId>Seg_1</localId><namespace>ES.SDGC.CP').replace(
        '<localId>Seg_1</localId>\n          <namespace>ES.LOCAL.CP</namespace>',
        '<localId>Seg_1</localId>\n          <namespace>ES.SDGC.CP</namespace>'), ['NS-SDGC-SIN-RC'], []),
    ("namespace desconocido", BASE.replace('<namespace>ES.SDGC.CP</namespace>', '<namespace>ES.CATASTRO</namespace>'),
     ['NS-DESCONOCIDO'], []),
    ("superficie declarada que no cuadra", BASE.replace('>600</cp:areaValue>', '>650</cp:areaValue>'), ['SUP-DISTINTA'], []),
    ("sin superficie declarada", re.sub(r'\s*<cp:areaValue[^<]*</cp:areaValue>', '', BASE), ['SUP-FALTA'], []),
    ("dos parcelas solapadas", None, ['SOLAPE'], []),
    ("dos parcelas separadas", gml([gp.ParcelaGML(RC, gp.SDGC, rect(X0, Y0, 20, 30), '01'),
                                    gp.ParcelaGML('Seg_1', gp.LOCAL, rect(X0 + 200, Y0, 15, 30))]), ['ZONAS-SEPARADAS'], []),
    ("sin xmlns:xlink", BASE.replace(' xmlns:xlink="http://www.w3.org/1999/xlink"', ''), ['XLINK'], []),
    ("referencia de Navarra (catastro foral)", BASE.replace(RC, '31001A00100001'), ['RC-FORAL'], []),
    ("35 parcelas (más de las que tramita la Sede)", MUCHAS, ['N-PARCELAS'], []),
    ("edificio correcto", leer(os.path.join(DATOS, 'edificio_sintetico.gml')), [], ['*ERROR']),
    ("edificio sin plantas", leer(os.path.join(DATOS, 'edificio_sintetico.gml')).replace(
        b'<bu-ext2d:numberOfFloorsAboveGround>2</bu-ext2d:numberOfFloorsAboveGround>', b''), ['BU-SIN-PLANTAS'], []),
    ("diminuta (0,5 m²), con la superficie de la grande", None, ['SUP-DISTINTA'], []),
]

#Los que el escritor del plugin no deja escribir: se fabrican a mano
_solapada = DOS.replace(f'{X0 + 20:.2f} {Y0:.2f} {X0 + 20:.2f} {Y0 + 30:.2f}',
                        f'{X0 + 18:.2f} {Y0:.2f} {X0 + 18:.2f} {Y0 + 30:.2f}', 1)
_solapada = _solapada.replace(f'{X0 + 35:.2f} {Y0:.2f} {X0 + 20:.2f} {Y0:.2f}', f'{X0 + 35:.2f} {Y0:.2f} {X0 + 18:.2f} {Y0:.2f}')
_diminuta = con_poslist(BASE, [(X0, Y0), (X0, Y0 + 0.5), (X0 + 1, Y0 + 0.5), (X0 + 1, Y0), (X0, Y0)])
CASOS = [(n, _solapada if n == "dos parcelas solapadas" else _diminuta if n.startswith("diminuta") else c, s, p)
         for n, c, s, p in CASOS]

resultados, detalles = {}, {}
dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
pv = dw.pestanaValidar


def codigos(incidencias):
    return {i.codigo for i in incidencias}


for numero, (nombre, contenido, salen, no_salen) in enumerate(CASOS, start=1):
    ruta = os.path.join(carpeta, f'caso {numero:02d}.gml')
    with open(ruta, 'wb') as f:
        f.write(contenido if isinstance(contenido, bytes) else contenido.encode('utf-8'))
    try:
        informe = validador.validar(ruta)
        hay = codigos(informe.incidencias)
        ok = all((bool(informe.errores) if c == '*ERROR' else c in hay) for c in salen)
        ok = ok and not any((bool(informe.errores) if c == '*ERROR' else c in hay) for c in no_salen)
        #Los mensajes se entienden: en castellano, sin trazas de Python
        ok = ok and all(i.mensaje and 'Traceback' not in i.mensaje and 'NoneType' not in i.mensaje for i in informe.incidencias)
        #En la pestaña: se abre sin fallar y la lista dice lo mismo
        dw.messageBar.clearWidgets()
        pv.fichero.setFilePath(ruta)
        ok = ok and pv.ruta == ruta and (pv.lista.count() > 0 or not informe.incidencias)
        if gl.leer(ruta).elementos:
            ok = ok and pv.tabla.rowCount() == len(gl.leer(ruta).elementos) and pv.cargarBoton.isEnabled()
        resultados[f"{numero:02d}. {nombre}"] = ok
        if not ok:
            detalles[nombre] = sorted(hay), [i.mensaje[:120] for i in informe.incidencias if i.nivel == ERROR][:4]
    except Exception:  # noqa: BLE001
        resultados[f"{numero:02d}. {nombre}"] = False
        detalles[nombre] = traceback.format_exc()[-900:]

#Lo que «Reparar» promete arreglar, lo arregla: cada caso reparable se repara y ya no tiene esos avisos ni errores
from catastral_gml_tools.core import conversor as cv  # noqa: E402

reparados = []
for numero, (nombre, _, _salen, _) in enumerate(CASOS, start=1):
    ruta = os.path.join(carpeta, f'caso {numero:02d}.gml')
    informe = validador.validar(ruta)
    reparables = codigos(informe.incidencias) & cv.REPARABLES
    if not reparables or not gl.leer(ruta).version.startswith('CP'):
        continue
    destino = os.path.join(carpeta, f'caso {numero:02d}_reparado.gml')
    ok, _, cambios, pendientes = cv.convertir(ruta, destino)
    quedan = codigos(validador.validar(destino).incidencias) & reparables if ok else reparables
    #Con errores que «Reparar» no arregla (geometría inválida, ids mal…), lo que promete es decir qué queda por revisar
    no_reparables = {i.codigo for i in informe.errores} - cv.REPARABLES
    bien = (not quedan) if not no_reparables else bool(pendientes) and (not ok or bool(cambios))
    reparados.append((nombre, ok and not quedan or bien, sorted(quedan), sorted(no_reparables),
                      [i.mensaje[:90] for i in pendientes][:3]))
resultados["«Reparar» arregla lo que dice que arregla (" + str(len(reparados)) + " casos)"] = all(r[1] for r in reparados)
if not all(r[1] for r in reparados):
    detalles['reparar'] = [r for r in reparados if not r[1]]

#Casos de la pestaña que no son de contenido
extra = {}
try:
    #En grados, la tabla da la superficie en m² (en el huso de la zona), no 0
    numero = [c[0] for c in CASOS].index("EPSG:4326 de verdad (latitud, longitud): solo el SRC") + 1
    pv.fichero.setFilePath(os.path.join(carpeta, f'caso {numero:02d}.gml'))
    #XML roto a mano (prueba del 20/10/2026): el mensaje dice qué falta y enseña el trozo de la línea
    rotos = {BASE[1:]: '¿se ha borrado el primer carácter?', BASE.replace('<cp:label>', '<cp:label', 1): '«<cp:label01'}
    extra["XML roto a mano: dice qué falta y dónde, con el trozo de línea"] = all(
        palabra in gl.leer_datos(texto.encode('utf-8')).incidencias[0].mensaje for texto, palabra in rotos.items())
    extra["en grados: la tabla da 600 m², no 0"] = pv.tabla.item(0, 4) is not None and pv.tabla.item(0, 4).text() == '600'
    dw.messageBar.clearWidgets()
    pv.fichero.setFilePath(os.path.join(carpeta, 'no existe.gml'))
    barra = ' '.join(e.text() for item in dw.messageBar.items() for e in item.findChildren(QLabel)) + ' '.join(
        item.text() for item in dw.messageBar.items())
    extra["fichero que no existe: aviso en el panel"] = 'No existe el fichero' in barra and pv.tabla.rowCount() == 0
    #El informe no se puede escribir (en su lugar hay una carpeta con ese nombre): aviso, sin fallar
    ruta_ok = os.path.join(carpeta, 'caso 01.gml')
    pv.fichero.setFilePath(ruta_ok)
    os.makedirs(pv_module.informe_html.ruta_por_defecto(ruta_ok), exist_ok=True)
    dw.messageBar.clearWidgets()
    pv.crear_informe()
    barra = ' '.join(e.text() for item in dw.messageBar.items() for e in item.findChildren(QLabel)) + ' '.join(
        item.text() for item in dw.messageBar.items())
    extra["informe que no se puede escribir: aviso, sin fallar"] = bool(barra.strip())
    #Abrir otro fichero y volver: la tabla es la del último
    pv.fichero.setFilePath(os.path.join(carpeta, 'caso 02.gml'))
    pv.fichero.setFilePath(ruta_ok)
    extra["abrir uno tras otro: se queda el último"] = pv.tabla.rowCount() == 1
except Exception:  # noqa: BLE001
    extra["casos de la pestaña"] = False
    detalles['pestaña'] = traceback.format_exc()[-900:]
resultados.update(extra)
dw.cleanup()
dw.deleteLater()
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
resultados["ninguna ventana emergente"] = not ventanas

print("=" * 60)
print("QGIS", Qgis.version(), "· Validar: batería de casos")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, d in detalles.items():
    print("Detalles", nombre, ":", d)
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
