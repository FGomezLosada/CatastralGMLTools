"""
Prueba de robustez (auditoría, bloque C, AU-47): funciones y casos que no tenían prueba directa. Líneas de un DXF
(varias cerradas, patio, cierre a menos de 1 cm), utilidades de capas, datos de rústica con respuestas raras, croquis
con huecos y multipartes, zonas separadas en la multiparcela, comparación demasiado grande o con un trozo que falla,
referencias con Ñ, punto interior en parcelas en U y descarga del plugin con tareas en marcha. Sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py robustez_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import json
import time

import qgis.utils
from qgis.core import Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QMessageBox

import catastral_gml_tools  # noqa: E402
from catastral_gml_tools.core import capa_edificios as ce
from catastral_gml_tools.core import capa_parcelas as cp
from catastral_gml_tools.core import comparacion as cmp
from catastral_gml_tools.core import geometria as geo
from catastral_gml_tools.core import gml_edificio as ge
from catastral_gml_tools.core import gml_lector as gl
from catastral_gml_tools.core import gml_parcela as gp
from catastral_gml_tools.core import informe, refcat, servicios
from catastral_gml_tools.core import unir as un
from catastral_gml_tools.core.incidencias import codigos
from catastral_gml_tools.gui import pestana_descargar as pd

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))

X0, Y0 = 421500.0, 4070500.0


def rect(x, y, a, b):
    return QgsGeometry.fromWkt(f"POLYGON(({x} {y}, {x + a} {y}, {x + a} {y + b}, {x} {y + b}, {x} {y}))")


def anillo(x, y, a, b, cierre=0.0):
    return f"({x} {y}, {x + a} {y}, {x + a} {y + b}, {x} {y + b}, {x + cierre} {y})"


# 1. Líneas de un DXF: dos cerradas (una con un patio dentro), una que cierra a 5 mm y una abierta
lineas = QgsGeometry.fromWkt("MULTILINESTRING(" + ", ".join([
    anillo(X0, Y0, 20, 20), anillo(X0 + 5, Y0 + 5, 4, 4), anillo(X0 + 40, Y0, 10, 10, cierre=0.005),
    f"({X0 + 60} {Y0}, {X0 + 70} {Y0}, {X0 + 70} {Y0 + 10})"]) + ")")
poligono, abiertas = ce.poligono_de_lineas(lineas)
partes = poligono.asMultiPolygon() if poligono is not None and poligono.isMultipart() else []
dxf = (abiertas == 1 and len(partes) == 2 and sorted(len(p) for p in partes) == [1, 2]
       and abs(poligono.area() - (400 - 16 + 100)) < 0.1)

# 2. Utilidades de capas: SRC que no encaja, líneas abiertas, capa de parcelas y capa nueva de huellas
def capa(tipo, crs, geometrias, campos=''):
    c = QgsVectorLayer(f"{tipo}?crs={crs}{campos}", 'prueba', 'memory')
    entidades = []
    for g, valores in geometrias:
        f = QgsFeature(c.fields())
        f.setGeometry(g)
        f.setAttributes(valores)
        entidades.append(f)
    c.dataProvider().addFeatures(entidades)
    return c


utm_en_geograficas = capa('Polygon', 'EPSG:4326', [(rect(X0, Y0, 10, 10), [])])
bien = capa('Polygon', 'EPSG:25830', [(rect(X0, Y0, 10, 10), [])])
de_lineas = capa('LineString', 'EPSG:25830', [(QgsGeometry.fromWkt(f"LINESTRING({X0} {Y0}, {X0 + 5} {Y0})"), [])])
parcelas = capa('Polygon', 'EPSG:25830', [(rect(X0, Y0, 10, 10), [gl.PARCELA])], '&field=tipo:string(20)')
huellas = ce.nueva_capa_huellas(QgsCoordinateReferenceSystem('EPSG:25830'))
utilidades = (bool(cp.src_incorrecto(utm_en_geograficas)) and cp.src_incorrecto(bien) == ''
              and ce.lineas_abiertas(de_lineas) == 1 and ce.es_capa_de_parcelas(parcelas)
              and not ce.es_capa_de_parcelas(bien) and huellas.fields().names() == ['tipo', 'plantas', 'estado']
              and huellas.defaultValueDefinition(0).expression() == f"'{ge.EDIFICIO}'")

# 3. Datos de rústica (Consulta_DNPRC): subparcelas como lista o como diccionario, y JSON roto
_pedir = servicios.pedir


def respuesta(lspr):
    datos = {"consulta_dnprcResult": {"bico": {"bi": {"dt": {"locs": {"lors": {"lorus": {"npa": "PARAJE"}}}},
                                                      "ldt": "Polígono 1 Parcela 1"}, "lspr": lspr}}}
    return lambda url: (json.dumps(datos).encode('utf-8'), '')


una = {"cspr": "0", "dspr": {"ccc": "MT", "dcc": "MATORRAL"}}
servicios.pedir = respuesta([una, {"cspr": "1", "dspr": {"ccc": "VT", "dcc": "VÍA"}}])
lista = servicios.datos_rustica('29071A00700001')
servicios.pedir = respuesta(una)
diccionario = servicios.datos_rustica('29071A00700001')
servicios.pedir = lambda url: (b'{"consulta_dnprcResult": {roto', '')
roto = servicios.datos_rustica('29071A00700001')
servicios.pedir = _pedir
rustica = (lista['cultivos'] == [('MT', 'MATORRAL'), ('VT', 'VÍA')] and diccionario['cultivos'] == [('MT', 'MATORRAL')]
           and lista['paraje'] == 'PARAJE' and roto is None)

# 4. Croquis del informe con un hueco y una parcela de dos partes (no debe fallar y dibuja todas)
con_hueco = QgsGeometry.fromWkt(f"POLYGON({anillo(X0, Y0, 20, 20)}, {anillo(X0 + 5, Y0 + 5, 4, 4)})")
dos_partes = QgsGeometry.fromWkt(f"MULTIPOLYGON(({anillo(X0 + 30, Y0, 5, 5)}), ({anillo(X0 + 40, Y0, 5, 5)}))")
svg = informe.croquis_svg([gl.ElementoGML(gl.PARCELA, 'Hueco', 'ES.LOCAL.CP', con_hueco),
                           gl.ElementoGML(gl.PARCELA, 'DosPartes', 'ES.LOCAL.CP', dos_partes)])
croquis = svg.startswith('<svg') and 'Hueco' in svg and 'DosPartes' in svg and 'evenodd' in svg

# 5. Multiparcela: parcelas a 5 mm son una zona; a 5 cm, dos
cerca = [gp.ParcelaGML('A', gp.LOCAL, rect(X0, Y0, 10, 10)), gp.ParcelaGML('B', gp.LOCAL, rect(X0 + 10.005, Y0, 10, 10))]
lejos = [gp.ParcelaGML('A', gp.LOCAL, rect(X0, Y0, 10, 10)), gp.ParcelaGML('B', gp.LOCAL, rect(X0 + 10.05, Y0, 10, 10))]
zonas = un.zonas_separadas(cerca) == 1 and un.zonas_separadas(lejos) == 2

# 6. Comparación: parcelario demasiado extenso (sin pedir nada) y un trozo que falla a mitad
peticiones = []
servicios.pedir = lambda url: (peticiones.append(url), (b'', 'error simulado'))[1]
_, err_grande = cmp.parcelas_catastrales(QgsRectangle(X0, Y0, X0 + 6000, Y0 + 6000), 25830)
grande = codigos(err_grande) == ['CMP-DEMASIADO-GRANDE'] and not peticiones
vacia = (b'<?xml version="1.0" encoding="UTF-8"?><wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" '
         b'numberMatched="0" numberReturned="0"/>')
servicios.pedir = lambda url: (peticiones.append(url), (vacia, '') if len(peticiones) == 1 else (b'', 'caído'))[1]
_, err_trozo = cmp.parcelas_catastrales(QgsRectangle(X0, Y0, X0 + 1500, Y0 + 500), 25830)
servicios.pedir = _pedir
trozo = bool(err_trozo) and any('caído' in i.mensaje for i in err_trozo)
comparacion = grande and trozo

# 7. Referencias con Ñ: el carácter de control se calcula (Ñ vale 15) y la referencia se comprueba sin errores
rc18 = '0000Ñ01VF2700S0001'
control = refcat.caracteres_control(rc18)
con_enye = (len(control) == 2 and refcat.comprobar(rc18 + control).nivel != 'error'
            and refcat.comprobar(rc18 + ('A' if control[1] != 'A' else 'B') + control[1]).nivel == 'error')

# 8. Punto interior de una parcela en U (el centroide cae fuera): dentro y con 2 decimales
en_u = QgsGeometry.fromWkt(f"POLYGON(({X0} {Y0}, {X0 + 30} {Y0}, {X0 + 30} {Y0 + 30}, {X0 + 25} {Y0 + 30}, {X0 + 25} {Y0 + 5}, "
                           f"{X0 + 5} {Y0 + 5}, {X0 + 5} {Y0 + 30}, {X0} {Y0 + 30}, {X0} {Y0}))")
recintos, _ = geo.preparar(en_u)
px, py = geo.punto_interior(recintos[0])
interior = (recintos[0].geometria().contains(QgsGeometry.fromWkt(f"POINT({px} {py})"))
            and round(px, 2) == px and round(py, 2) == py)

# 8b. Capas del plugin (descarga, vista del GML): al editar, sup_calc se recalcula y los polígonos nuevos son «parcela»
from qgis.core import QgsVectorLayerUtils  # noqa: E402

_lectura = gl.ResultadoLectura()
_lectura.epsg = 25830
_lectura.elementos = [gl.ElementoGML(gl.PARCELA, 'X', 'ES.SDGC.CP', rect(X0, Y0, 10, 10), area_declarada=100)]
editable = gl.capa(_lectura, 'edicion')
editable.startEditing()
_f = next(editable.getFeatures())
_mitad = QgsGeometry(rect(X0, Y0, 5, 10))
_mitad.convertToMultiType()
editable.changeGeometry(_f.id(), _mitad)
_nueva = QgsVectorLayerUtils.createFeature(editable, rect(X0 + 20, Y0, 3, 3), {}, None)
editable.addFeature(_nueva)
_valores = sorted((g['sup_calc'], g['tipo']) for g in editable.getFeatures())
edicion = _valores == [(9, gl.PARCELA), (50, gl.PARCELA)] and editable.getFeature(_f.id())['sup_gml'] == 100
editable.rollBack()

# 9. Descargar el plugin con una tarea en marcha: la tarea se cancela y termina enseguida (AU-38)
def esperar_cancelacion(rc):
    fin = time.time() + 30
    while time.time() < fin:
        servicios_feedback = getattr(servicios._contexto, 'feedback', None)
        if servicios_feedback is not None and servicios_feedback.isCanceled():
            return None
        time.sleep(0.05)
    return 'no cancelada'


plugin = catastral_gml_tools.classFactory(qgis.utils.iface)
plugin.initGui()
plugin.toggle(True)
pestana = plugin.dockwidget.pestanaDescargar
tarea = pd.TareaCatastro("prueba: tarea larga", esperar_cancelacion, ('X',), {}, pestana, 'descargada')
pestana.tarea = tarea
QgsApplication.taskManager().addTask(tarea)
_inicio = time.time()
while tarea.status() != tarea.TaskStatus.Running and time.time() - _inicio < 5:
    QCoreApplication.processEvents()
    time.sleep(0.02)
plugin.unload()
_inicio = time.time()
while tarea.status() not in (tarea.TaskStatus.Complete, tarea.TaskStatus.Terminated) and time.time() - _inicio < 10:
    QCoreApplication.processEvents()
    time.sleep(0.02)
descarga_plugin = (tarea.status() in (tarea.TaskStatus.Complete, tarea.TaskStatus.Terminated)
                   and time.time() - _inicio < 10 and tarea.resultado is None and plugin.dockwidget is None)
QgsProject.instance().clear()

for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)

checks = {
    "DXF: varias líneas cerradas, patio, cierre a 5 mm y una abierta": dxf,
    "SRC que no encaja, líneas abiertas, capa de parcelas y capa de huellas": utilidades,
    "datos de rústica: subparcelas en lista o diccionario y JSON roto": rustica,
    "croquis con hueco y parcela de dos partes": croquis,
    "multiparcela: a 5 mm una zona; a 5 cm, dos": zonas,
    "comparación demasiado extensa (sin peticiones) y trozo que falla a mitad": comparacion,
    "referencias con Ñ: carácter de control": con_enye,
    "punto interior de una parcela en U": interior,
    "capas del plugin: superficie recalculada al editar y polígonos nuevos de tipo parcela": edicion,
    "descargar el plugin con una tarea en marcha: se cancela": descarga_plugin,
    "ninguna ventana emergente": not ventanas,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· robustez")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'dxf': (abiertas, [len(p) for p in partes], poligono.area() if poligono else None),
                        'rustica': (lista, diccionario, roto), 'svg': svg[:200],
                        'comparacion': (codigos(err_grande), len(peticiones), [str(i) for i in err_trozo]),
                        'enye': (control, refcat.comprobar(rc18 + control).mensaje),
                        'interior': (px, py), 'edicion': _valores, 'tarea': (tarea.status(), tarea.resultado)})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
