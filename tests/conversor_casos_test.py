"""
Batería de casos de Utilidades «2. Convertir a 4.0 o reparar» y del botón «Convertir a 4.0» / «Reparar» de Validar (plan
de pruebas, docs/PLAN_PRUEBAS.md): GML 3.0, 4.0 con fallos y genéricos de cualquier origen.

Reglas de cada caso:
  - nunca una excepción ni una ventana; el original no se toca y no se pisa ningún fichero;
  - si se escribe, el resultado no tiene ninguno de los fallos que el conversor dice arreglar (REPARABLES), y lo que
    quede con error en la Validar del plugin está en el mensaje como «Queda por revisar»;
  - si no se escribe, lo dice con un mensaje que se entiende (sin textos de Python);
  - lo que se dice que ha cambiado (o que hay que revisar) es lo que se espera para ese fichero.

Uso: tools\\probar.bat (o tools\\run_tests.py conversor_casos_test.py)

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
from catastral_gml_tools.core import conversor as cv  # noqa: E402
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
dock_module.CatastralGMLToolsDockWidget.open_path = lambda self, ruta: None

carpeta = tempfile.mkdtemp(prefix='cgt convertir casos ñ_')
DATOS = os.path.join(RAIZ, 'tests', 'data', 'gml')
X0, Y0 = 421500.0, 4070500.0
RC = '1907401VK4810H'
resultados, detalles = {}, {}
TEXTOS_PYTHON = ('Errno', 'Traceback', 'line ', 'column ', 'NoneType', 'object has no')


def leer(ruta):
    with open(ruta, 'rb') as f:
        return f.read()


def rect(x, y, w, h):
    return QgsGeometry.fromWkt(f"POLYGON(({x} {y}, {x} {y + h}, {x + w} {y + h}, {x + w} {y}, {x} {y}))")


def gml(parcelas, epsg=25830):
    texto, inc = gp.construir(parcelas, epsg)
    assert texto is not None, inc
    return texto


def con_poslist(texto, puntos, etiqueta=None, cual=0):
    """El posList número cual cambiado por esos puntos (y, si se da, por esa etiqueta de apertura)."""
    m = list(re.finditer(r'(<gml:posList[^>]*>)([^<]*)(</gml:posList>)', texto))[cual]
    numeros = ' '.join(f'{x} {y}' for x, y in puntos)
    return texto[:m.start()] + (etiqueta or m.group(1)) + numeros + m.group(3) + texto[m.end():]


BASE = gml([gp.ParcelaGML(RC, gp.SDGC, rect(X0, Y0, 20, 30), '01')])
DOS = gml([gp.ParcelaGML(RC, gp.SDGC, rect(X0, Y0, 20, 30), '01'), gp.ParcelaGML('Seg_1', gp.LOCAL, rect(X0 + 20, Y0, 15, 30))])
R = [(X0, Y0), (X0, Y0 + 30), (X0 + 20, Y0 + 30), (X0 + 20, Y0), (X0, Y0)]
CP30 = leer(os.path.join(DATOS, 'parcela_cp30_sintetica.gml')).decode('utf-8')
R30 = [(X0, Y0), (X0, Y0 + 10), (X0 + 20, Y0 + 10), (X0 + 20, Y0), (X0, Y0)]


def ogr(campos, puntos=R, srs='urn:ogc:def:crs:EPSG::25830', etiqueta='parcela', n=1):
    """GML de «Guardar como» de QGIS (OGR), con n objetos y esos campos."""
    miembros = ''
    for k in range(n):
        lista = ' '.join(f'{float(x) + 30 * k} {y}' if k else f'{x} {y}' for x, y in puntos)
        valores = ''.join(f'<ogr:{c}>{v}</ogr:{c}>' for c, v in campos.items())
        miembros += (f'<ogr:featureMember><ogr:{etiqueta} gml:id="p{k}"><ogr:geometryProperty><gml:Polygon srsName="{srs}" '
                     f'gml:id="g{k}"><gml:exterior><gml:LinearRing><gml:posList>{lista}</gml:posList></gml:LinearRing>'
                     f'</gml:exterior></gml:Polygon></ogr:geometryProperty>{valores}</ogr:{etiqueta}></ogr:featureMember>\n')
    return ('<?xml version="1.0" encoding="utf-8" ?>\n<ogr:FeatureCollection gml:id="aFeatureCollection" '
            'xmlns:ogr="http://ogr.maptools.org/" xmlns:gml="http://www.opengis.net/gml/3.2">\n' + miembros
            + '</ogr:FeatureCollection>\n')


def en_grados(puntos, lat_lon=True):
    """Puntos en EPSG:4326 (por defecto en el orden latitud, longitud del GML 3.2)."""
    g = geo.transformar(QgsGeometry.fromWkt('POLYGON((' + ', '.join(f'{x} {y}' for x, y in puntos) + '))'),
                        QgsCoordinateReferenceSystem('EPSG:25830'), 4326)
    return [(f'{q.y():.9f}', f'{q.x():.9f}') if lat_lon else (f'{q.x():.9f}', f'{q.y():.9f}') for q in g.asPolygon()[0]]


AJENOS = BASE.replace('</cp:label>', '</cp:label><cp:Clave_Obra>A-12</cp:Clave_Obra><cp:Clave_Exp>99</cp:Clave_Exp>', 1)
SOLAPE = gml([gp.ParcelaGML(RC, gp.SDGC, rect(X0, Y0, 20, 30), '01'), gp.ParcelaGML('Seg_1', gp.LOCAL, rect(X0 + 25, Y0, 15, 30))])
SOLAPE = con_poslist(SOLAPE, [(X0 + 10, Y0), (X0 + 10, Y0 + 30), (X0 + 25, Y0 + 30), (X0 + 25, Y0), (X0 + 10, Y0)], cual=1)
CON_FECHA = CP30.replace('<cp:beginLifespanVersion xsi:nil="true" nilReason="other:unpopulated"></cp:beginLifespanVersion>',
                         '<cp:beginLifespanVersion>2019-05-02T10:30:00</cp:beginLifespanVersion>')
MUCHAS30 = CP30.split('<gml:featureMember>')[0] + ''.join(
    CP30.split('<gml:featureMember>')[1].replace('Prueba_1', f'P_{i}').replace(
        '421500.00 4070500.00 421500.00 4070510.00 421520.00 4070510.00 421520.00 4070500.00 421500.00 4070500.00',
        ' '.join(f'{x + 20 * i:.2f} {y + 40:.2f}' for x, y in R30)).join(['<gml:featureMember>', '']).replace(
        '</gml:FeatureCollection>', '') for i in range(40)) + '</gml:FeatureCollection>\n'
DOS_PARTES = BASE.replace('</gml:surfaceMember>', '</gml:surfaceMember><gml:surfaceMember><gml:Surface gml:id="s2" '
                          'srsName="http://www.opengis.net/def/crs/EPSG/0/25830"><gml:patches><gml:PolygonPatch><gml:exterior>'
                          '<gml:LinearRing><gml:posList srsDimension="2" count="5">'
                          + ' '.join(f'{x + 100} {y}' for x, y in R) + '</gml:posList></gml:LinearRing></gml:exterior>'
                          '</gml:PolygonPatch></gml:patches></gml:Surface></gml:surfaceMember>', 1)

#(nombre, contenido, ¿se escribe?, textos que tienen que salir en cambios o mensajes, códigos que no deben quedar)
CASOS = [
    # Esquema 3.0
    ("3.0 de la Sede antigua", CP30, True, ['Esquema 3.0 → 4.0', 'Fecha']),
    ("3.0 con su fecha: se conserva", CON_FECHA, True, ['Esquema 3.0 → 4.0', '!Fecha']),
    ("3.0 con 3 decimales", con_poslist(CP30, [(f'{x:.3f}', f'{y:.3f}') for x, y in R30]), True, ['3 decimales']),
    ("3.0 con la superficie mal", CP30.replace('<cp:areaValue uom="m2">200</cp:areaValue>',
                                               '<cp:areaValue uom="m2">250</cp:areaValue>', 1), True, ['250 → 200']),
    ("3.0 con 40 parcelas", MUCHAS30, True, ['Esquema 3.0 → 4.0', 'Queda por revisar']),
    ("3.0 en EPSG:4326 (latitud, longitud)", con_poslist(CP30.replace('EPSG::25830', 'EPSG::4326'), en_grados(R30)).replace(
        '<gml:coordinates>', '<gml:posList>').replace('</gml:coordinates>', '</gml:posList>').replace(
        '421520.00,4070500.00 421520.00,4070510.00 421540.00,4070510.00 421540.00,4070500.00 421520.00,4070500.00',
        ' '.join(f'{a} {b}' for a, b in en_grados([(x + 20, y) for x, y in R30]))), True, ['EPSG:4326', 'EPSG:25830']),
    # 4.0 con fallos que se reparan
    ("4.0 correcto: sin cambios", BASE, True, ['ya estaba bien']),
    ("4.0 con 3 decimales", con_poslist(BASE, [(f'{x:.3f}', f'{y:.3f}') for x, y in R]), True, ['3 decimales']),
    ("4.0 con el anillo al revés", con_poslist(BASE, R[::-1]), True, ['Corregido']),
    ("4.0 con el anillo abierto", con_poslist(BASE, R[:-1], '<gml:posList srsDimension="2" count="4">'), True, ['Corregido']),
    ("4.0 con count que no cuadra", con_poslist(BASE, R, '<gml:posList srsDimension="2" count="7">'), True, ['Corregido']),
    ("4.0 con vértices repetidos", con_poslist(BASE, [R[0], R[1], R[1], R[2], R[3], R[0]],
                                               '<gml:posList srsDimension="2" count="6">'), True, ['Corregido']),
    ("4.0 con Z", con_poslist(BASE, [(x, f'{y} 100.5') for x, y in R], '<gml:posList srsDimension="3" count="5">'), True,
     ['Corregido']),
    ("4.0 con la superficie mal", re.sub(r'(<cp:areaValue[^>]*>)\d+', r'\g<1>999', BASE), True, ['999 → 600']),
    ("4.0 sin xmlns:xlink", BASE.replace(' xmlns:xlink="http://www.w3.org/1999/xlink"', ''), True, []),
    ("4.0 con datos ajenos (expropiaciones)", AJENOS, True, ['Clave_Obra', 'Clave_Exp']),
    ("4.0 con BOM", b'\xef\xbb\xbf' + BASE.encode('utf-8'), True, []),
    ("4.0 en ISO-8859-1 con acentos", BASE.replace('encoding="utf-8"', 'encoding="ISO-8859-1"').replace(
        '<cp:label>01</cp:label>', '<cp:label>01</cp:label><!-- Camiño, año -->').encode('iso-8859-1'), True, []),
    ("4.0 con hueco: se conserva", gml([gp.ParcelaGML(RC, gp.SDGC, QgsGeometry.fromWkt(
        f"POLYGON(({X0} {Y0}, {X0} {Y0 + 30}, {X0 + 20} {Y0 + 30}, {X0 + 20} {Y0}, {X0} {Y0}),"
        f"({X0 + 5} {Y0 + 5}, {X0 + 9} {Y0 + 5}, {X0 + 9} {Y0 + 9}, {X0 + 5} {Y0 + 9}, {X0 + 5} {Y0 + 5}))"), '01')]),
     True, ['ya estaba bien']),
    ("4.0 en EPSG:4326 (latitud, longitud)", con_poslist(BASE.replace('EPSG/0/25830', 'EPSG/0/4326'), en_grados(R)), True,
     ['EPSG:4326', 'EPSG:25830', 'latitud, longitud']),
    ("4.0 en EPSG:4326 (longitud, latitud)", con_poslist(BASE.replace('EPSG/0/25830', 'EPSG/0/4326'),
                                                         en_grados(R, lat_lon=False)), True, ['EPSG:25830', '!latitud, longitud']),
    ("4.0 en EPSG:4258 en Canarias", con_poslist(BASE.replace('EPSG/0/25830', 'EPSG/0/4258'),
                                                 [('28.1', '-15.4'), ('28.1003', '-15.4'), ('28.1003', '-15.3998'),
                                                  ('28.1', '-15.3998'), ('28.1', '-15.4')]), True, ['EPSG:32628']),
    ("4.0 en EPSG:4326 en mitad del Atlántico", con_poslist(BASE.replace('EPSG/0/25830', 'EPSG/0/4326'),
                                                            [('40.0', '-40.0'), ('40.0003', '-40.0'), ('40.0003', '-39.9998'),
                                                             ('40.0', '-39.9998'), ('40.0', '-40.0')]), False, ['no caen en España']),
    ("4.0 en ED50 (EPSG:23030): no se adivina", BASE.replace('EPSG/0/25830', 'EPSG/0/23030'), False, ['23030']),
    # Lo que el conversor no puede deducir: lo dice
    ("SDGC sin referencia catastral", DOS.replace('<localId>Seg_1</localId><namespace>ES.LOCAL.CP',
                                                  '<localId>Seg_1</localId><namespace>ES.SDGC.CP').replace(
        '<localId>Seg_1</localId>\n          <namespace>ES.LOCAL.CP</namespace>',
        '<localId>Seg_1</localId>\n          <namespace>ES.SDGC.CP</namespace>'), False,
     ['referencia catastral de 14']),
    ("identificador repetido", DOS.replace('<localId>Seg_1</localId>', f'<localId>{RC}</localId>'), False, ['repet']),
    ("dos parcelas que se solapan", SOLAPE, False, ['superpone']),
    ("parcela en dos trozos", DOS_PARTES, False, ['trozos|partes|recintos']),
    ("pajarita", con_poslist(BASE, [(X0, Y0), (X0 + 20, Y0 + 30), (X0 + 20, Y0), (X0, Y0 + 30), (X0, Y0)]), False,
     ['se corta a sí mismo']),
    # GML genéricos
    ("«Guardar como» de QGIS con la RC de nombre de capa", ogr({'localId': RC}, etiqueta=RC), True,
     ['GML genérico', 'ES.SDGC.CP']),
    ("«Guardar como» de QGIS con campo refcat", ogr({'refcat': RC}), True, ['GML genérico', 'ES.SDGC.CP']),
    ("«Guardar como» de QGIS sin ningún identificador", ogr({'nombre': 'casa'}, n=2), False, ['identificador']),
    ("«Guardar como» de QGIS en EPSG:4326", ogr({'localId': 'Nueva_1'}, en_grados(R), 'urn:ogc:def:crs:EPSG::4326'),
     True, ['EPSG:4326', 'EPSG:25830']),
    ("«Guardar como» de QGIS sin SRC", ogr({'localId': 'Nueva_1'}, srs=''), False, ['sistema de referencia|SRC']),
    # Lo que no se convierte
    ("GML de edificios", leer(os.path.join(DATOS, 'edificio_sintetico.gml')), False, ['edificio|parcela catastral']),
    ("XML mal formado", leer(os.path.join(DATOS, 'mal_formado.gml')), False, ['XML']),
    ("fichero vacío", b'', False, ['vacío|XML']),
    ("texto que no es XML", "esto no es un GML", False, ['XML']),
    ("sin srsName", re.sub(r' srsName="[^"]*"', '', BASE), False, ['sistema de referencia|SRC|srsName']),
    ("coma decimal", con_poslist(BASE, [(f'{x:.2f}'.replace('.', ','), f'{y:.2f}'.replace('.', ',')) for x, y in R]),
     False, ['coordenadas']),
]


def caso(nombre, funcion):
    try:
        ok, detalle = funcion()
        resultados[nombre] = bool(ok)
        if not ok:
            detalles[nombre] = detalle
    except Exception:  # noqa: BLE001
        resultados[nombre] = False
        detalles[nombre] = traceback.format_exc()[-900:]


def contiene(texto, patron):
    return any(p.lower() in texto.lower() for p in patron.split('|'))


def convertir_caso(k, nombre, contenido, escribe, textos):
    def prueba():
        ruta = os.path.join(carpeta, f'caso_{k}.gml')
        with open(ruta, 'wb') as f:
            f.write(contenido.encode('utf-8') if isinstance(contenido, str) else contenido)
        antes = leer(ruta)
        version = gl.leer(ruta).version or cv.GENERICO
        destino = cv.destino_propuesto(ruta, version)
        ok, version, cambios, inc = cv.convertir(ruta, destino)
        mensajes = cambios + [i.mensaje for i in inc]
        todo = ' '.join(mensajes)
        problemas = []
        if leer(ruta) != antes:
            problemas.append('original tocado')
        if ok != escribe:
            problemas.append(f'escrito={ok}')
        if ok != os.path.isfile(destino):
            problemas.append('fichero de salida no coincide con el resultado')
        if not ok and not any(i.nivel == ERROR for i in inc):
            problemas.append('no escrito y sin error')
        if any(t in todo for t in TEXTOS_PYTHON):
            problemas.append('texto de Python')
        for t in textos:
            if t.startswith('!'):
                if contiene(todo, t[1:]):
                    problemas.append(f'sobra «{t[1:]}»')
            elif not contiene(todo, t):
                problemas.append(f'falta «{t}»')
        if ok:
            informe = validador.validar(destino)
            quedan = {i.codigo for i in informe.incidencias if i.nivel in (ERROR, 'aviso')}
            reparables = quedan & cv.REPARABLES
            if reparables:
                problemas.append(f'quedan reparables {sorted(reparables)}')
            avisados = {i.codigo for i in inc if i.mensaje.startswith('Queda por revisar')}
            sin_decir = {i.codigo for i in informe.errores} - avisados
            if sin_decir:
                problemas.append(f'errores que no dice {sorted(sin_decir)}')
            if gl.leer(destino).epsg not in geo.SRC_ADMITIDOS:
                problemas.append(f'SRC {gl.leer(destino).epsg}')
            #Otro clic no pisa el creado
            if cv.destino_propuesto(ruta, version) == destino:
                problemas.append('se propondría pisar el creado')
        return not problemas, (problemas, ok, [m[:110] for m in mensajes][:8])
    return prueba


for _k, (_nombre, _contenido, _escribe, _textos) in enumerate(CASOS):
    caso(_nombre, convertir_caso(_k, _nombre, _contenido, _escribe, _textos))


def destino_original():
    ruta = os.path.join(carpeta, 'caso_0.gml')
    antes = leer(ruta)
    ok, _, _, inc = cv.convertir(ruta, ruta)
    return not ok and leer(ruta) == antes and any('original' in i.mensaje for i in inc), [i.mensaje for i in inc]


def no_existe():
    ok, _, _, inc = cv.convertir(os.path.join(carpeta, 'no_existe.gml'), os.path.join(carpeta, 'x.gml'))
    texto = ' '.join(i.mensaje for i in inc)
    return not ok and 'No existe el fichero' in texto and 'Errno' not in texto, texto


def carpeta_destino():
    ok, _, _, inc = cv.convertir(os.path.join(carpeta, 'caso_0.gml'), os.path.join(carpeta, 'no hay', 'x.gml'))
    return not ok and bool(inc), [i.mensaje for i in inc]


caso("salida igual al original: no lo pisa", destino_original)
caso("un fichero que no existe: lo dice en castellano", no_existe)
caso("carpeta de salida que no existe: error claro", carpeta_destino)


# La utilidad y el botón de Validar
def barra(dw):
    return ' '.join([i.text() for i in dw.messageBar.items()] + [e.text() for i in dw.messageBar.items()
                                                                  for e in i.findChildren(QLabel)])


def panel():
    dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
    pu = dw.pestanaUtilidades
    pu.utilidades.setCurrentIndex(1)
    origen = os.path.join(carpeta, 'caso_0.gml')
    pu.soltar([origen])
    propuesto = pu.destinoConv.filePath()
    estado = pu.convertirBoton.isEnabled() and pu.convertirBoton.text() == "Convertir a 4.0" and propuesto.endswith('_v4_2.gml')
    dw.messageBar.clearWidgets()
    hecho = pu.convertir()
    creado = hecho == propuesto and os.path.isfile(hecho) and 'Convertido a 4.0' in barra(dw)
    otro = pu.destinoConv.filePath() != hecho  #Un segundo clic no pisa el creado
    #Un GML de edificios: botón desactivado y dice por qué
    pu.soltar([os.path.join(DATOS, 'edificio_sintetico.gml')])
    edificio = not pu.convertirBoton.isEnabled() and 'edificios' in pu.estadoConv.text()
    #Uno que no se puede convertir (solape): aviso en el panel, sin ventanas
    pu.soltar([os.path.join(carpeta, f'caso_{[c[0] for c in CASOS].index("dos parcelas que se solapan")}.gml')])
    dw.messageBar.clearWidgets()
    malo = pu.convertir() is None and 'No se ha podido convertir' in barra(dw)
    #Validar: un 4.0 con 3 decimales muestra «Reparar»; al pulsarlo se abre el reparado
    pv = dw.pestanaValidar
    ruta = os.path.join(carpeta, f'caso_{[c[0] for c in CASOS].index("4.0 con 3 decimales")}.gml')
    dw.abrir_en_validar(ruta)
    reparar = not pv.convertirBoton.isHidden() and pv.convertirBoton.text() == "Reparar"
    abierto = pv.convertir()
    validar = abierto is not None and pv.ruta == abierto and pv.convertirBoton.isHidden()
    dw.deleteLater()
    ok = estado and creado and otro and edificio and malo and reparar and validar
    return ok, (estado, creado, otro, edificio, malo, reparar, validar, propuesto, barra(dw)[:200])


caso("panel: soltar, proponer nombre, convertir sin pisar, edificios, error y «Reparar» de Validar", panel)

for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
resultados["ninguna ventana emergente"] = not ventanas

print("=" * 60)
print("QGIS", Qgis.version(), "· Convertir a 4.0 o reparar: batería de casos")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, d in detalles.items():
    print("Detalles", nombre, ":", d)
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
