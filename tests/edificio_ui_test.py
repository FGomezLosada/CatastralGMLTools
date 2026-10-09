"""
Prueba de la pestaña Edificio (mejora 19) y de la comprobación del ICUC en Validar (mejora 20), con el Catastro
simulado: capa de construcciones como la de Descargar (referencia, tipos y plantas propuestos), identificadores según el
formato de la DGC, cambio de tipo, Crear GML, botón Validar, construcciones dentro, en parte fuera y lejos de la parcela, capa de
Navarra y falta de referencia. Sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py edificio_ui_test.py)
"""
import importlib.util
import os
import tempfile

import qgis.utils
from qgis.core import Qgis, QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

qgis.utils.reloadPlugin('catastral_gml_tools')
import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import comparacion as cmp  # noqa: E402
from catastral_gml_tools.core import gml_edificio as ge  # noqa: E402
from catastral_gml_tools.core import gml_lector as gl  # noqa: E402
from catastral_gml_tools.core import gml_parcela as gp  # noqa: E402
from catastral_gml_tools.core import servicios  # noqa: E402
from catastral_gml_tools.core.incidencias import ERROR, codigos  # noqa: E402
from catastral_gml_tools.core.info import RAIZ  # noqa: E402
from catastral_gml_tools.gui import pestana_edificio as pe_mod  # noqa: E402
from catastral_gml_tools.gui.pestana_parcela import PROPIEDAD_TERRITORIO  # noqa: E402

spec = importlib.util.spec_from_file_location('simulador_catastro', os.path.join(RAIZ, 'tests', 'simulador_catastro.py'))
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)
original = sim.instalar()

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))

X0, Y0, RC = sim.X0, sim.Y0, sim.RC
carpeta = tempfile.mkdtemp(prefix='cgt_edificio_')


def wkt(x, y, a, b):
    return f"POLYGON(({x} {y}, {x + a} {y}, {x + a} {y + b}, {x} {y + b}, {x} {y}))"


def barra(dw):
    item = dw.messageBar.currentItem()
    if item is None:
        return ''
    return ' '.join([item.text()] + [e.text() for e in item.findChildren(QLabel)])


#Capa como la «Construcciones» de Descargar: dos edificios y una piscina de la parcela sintética (20 × 30 m)
capa = QgsVectorLayer("Polygon?crs=EPSG:25830&field=tipo:string(30)&field=localId:string(40)&field=plantas:integer"
                      "&field=naturaleza:string(30)", "Construcciones", 'memory')
datos = [(wkt(X0 + 2, Y0 + 2, 8, 6), gl.EDIFICIO, RC, 2, ''),
         (wkt(X0 + 2, Y0 + 12, 6, 3), gl.OTRA, f'{RC}_PI.1', None, 'openAirPool'),
         (wkt(X0 + 12, Y0 + 2, 4, 4), gl.EDIFICIO, RC, 1, '')]
entidades = []
for geometria, tipo, local_id, plantas, naturaleza in datos:
    f = QgsFeature(capa.fields())
    f.setGeometry(QgsGeometry.fromWkt(geometria))
    f.setAttributes([tipo, local_id, plantas, naturaleza])
    entidades.append(f)
capa.dataProvider().addFeatures(entidades)
QgsProject.instance().addMapLayer(capa)

dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
pe = dw.pestanaEdificio
integrada = dw.tabEdificioPendiente.isHidden() and pe.parent() is dw.tabEdificio and pe.capa() is None

# 1. La capa descargada pasa a la pestaña: referencia, tipos, plantas e identificadores propuestos
dw.construcciones_descargadas(RC, capa)
ids = [pe.tabla.item(i, pe_mod.COL_ID).text() for i in range(pe.tabla.rowCount())]
tipos = [pe.tipo_fila(i) for i in range(pe.tabla.rowCount())]
plantas = [pe.tabla.item(i, pe_mod.COL_PLANTAS).text() for i in range(pe.tabla.rowCount())]
propuesta = (pe.capa() is capa and pe.referencia.text() == RC and pe.campoPlantas.currentField() == 'plantas'
             and tipos == [ge.EDIFICIO, ge.PISCINA, ge.EDIFICIO] and plantas == ['2', '', '1']
             and ids == [f'{RC}_Edificio_1', f'{RC}_Piscina_1', f'{RC}_Edificio_2']
             and pe.tabla.item(0, pe_mod.COL_AREA).text() == '48' and '2 edificios, 1 piscina' in pe.resumen.text()
             and pe.destino.filePath().endswith('Construcciones_edificio.gml'))

# 2. Cambiar el tipo de la tercera fila a piscina: se renumeran los identificadores
pe.tabla.cellWidget(2, pe_mod.COL_TIPO).setCurrentIndex(1)
ids_tipo = [pe.tabla.item(i, pe_mod.COL_ID).text() for i in range(pe.tabla.rowCount())]
cambio_tipo = ids_tipo == [RC, f'{RC}_Piscina_1', f'{RC}_Piscina_2']
pe.tabla.cellWidget(2, pe_mod.COL_TIPO).setCurrentIndex(0)

# 3. Crear GML y abrirlo en Validar
salida = os.path.join(carpeta, 'edificio.gml')
pe.destino.setFilePath(salida)
pe.estado.setCurrentIndex(pe.estado.findData('underConstruction'))
creado = pe.crear_gml()
lectura = gl.leer(salida) if creado else None
contenido = lectura.datos.decode('iso-8859-1') if lectura else ''
texto_barra = barra(dw)
crear = (creado == salida and lectura.version == 'BU 2.0' and len(lectura.elementos) == 3
         and [e.plantas for e in lectura.elementos] == [2, None, 1]
         and 'underConstruction' in contenido
         and 'GML de edificio creado: edificio.gml · 2 edificios y 1 piscina · EPSG:25830' in texto_barra
         and pe.tabla.item(0, pe_mod.COL_ESTADO).text() == 'Correcta')
pe.validar()
pv = dw.pestanaValidar
abierto = dw.tabWidget.currentWidget() is dw.tabValidar and pv.fichero.filePath() == salida
pv.abrir(segundo_plano=False)
boton_cmp = pv.cmpBoton.isEnabled()

# 4. ICUC: todas dentro de la parcela
dentro = pv.comparar_catastro(segundo_plano=False)
icuc_dentro = (dentro is not None and dentro.edificio and codigos(dentro.incidencias) == ['CMP-BU-DENTRO']
               and 'Construcciones dentro de la parcela' in barra(dw)
               and QgsProject.instance().layerTreeRoot().findGroup('Comparación edificio') is not None)

# 5. Una construcción que sale de la parcela
fuera_ruta = os.path.join(carpeta, 'fuera.gml')
ge.escribir(fuera_ruta, [ge.Construccion(RC, QgsGeometry.fromWkt(wkt(X0 + 15, Y0 + 2, 10, 5)), plantas=1)], 25830)
fuera = cmp.comparar_edificio(gl.leer(fuera_ruta))
lejos_ruta = os.path.join(carpeta, 'lejos.gml')
ge.escribir(lejos_ruta, [ge.Construccion(RC, QgsGeometry.fromWkt(wkt(X0 + 300, Y0, 10, 5)), plantas=1)], 25830)
lejos = cmp.comparar_edificio(gl.leer(lejos_ruta))
sin_rc_ruta = os.path.join(carpeta, 'sin_rc.gml')
ge.escribir(sin_rc_ruta, [ge.Construccion('Edificio_1', QgsGeometry.fromWkt(wkt(X0 + 2, Y0 + 2, 5, 5)), plantas=1)], 25830)
sin_rc = cmp.comparar_edificio(gl.leer(sin_rc_ruta))
icuc_fuera = (codigos(fuera.incidencias) == ['CMP-BU-FUERA'] and fuera.incidencias[0].nivel == ERROR
              and abs(fuera.exceso.area() - 25) < 0.1 and codigos(lejos.incidencias) == ['CMP-BU-LEJOS']
              and lejos.incidencias[0].nivel == ERROR
              and codigos(sin_rc.incidencias) == ['CMP-BU-SIN-RC'] and not sin_rc.comparada)

# 6. Sin referencia y capa de Navarra: avisos y ningún fichero
pe.referencia.setText('')
pe.destino.setFilePath(os.path.join(carpeta, 'sin_referencia.gml'))
sin_referencia = pe.crear_gml() is None and 'referencia catastral de la parcela' in barra(dw)
pe.referencia.setText(RC)
capa.setCustomProperty(PROPIEDAD_TERRITORIO, 'Navarra')
navarra = pe.crear_gml() is None and 'catastro propio' in barra(dw)
capa.removeCustomProperty(PROPIEDAD_TERRITORIO)
ficheros = not os.path.exists(os.path.join(carpeta, 'sin_referencia.gml'))

# 7. Descarga sin construcciones, capa de parcelas y dibujo de huellas
RC2 = '1907402VK4810H'
pe.referencia.setText('')
dw.construcciones_descargadas(RC2, None)
sin_construcciones = (pe.referencia.text() == RC2 and pe.capa() is None and 'no tiene construcciones' in pe.resumen.text())
ruta_parcela = os.path.join(carpeta, 'parcela.gml')
gp.escribir(ruta_parcela, [gp.ParcelaGML(RC2, gp.SDGC, QgsGeometry.fromWkt(wkt(X0 + 20, Y0, 20, 30)))], 25830)
parcela = gl.capa(gl.leer(ruta_parcela), f"Parcela {RC2}")
QgsProject.instance().addMapLayer(parcela)
pe.capaCombo.setLayer(parcela)
de_parcelas = (pe.de_parcelas and pe.tabla.rowCount() == 0 and 'es de parcelas' in pe.resumen.text()
               and pe.crear_gml() is None and 'es de parcelas' in barra(dw))
huellas = pe.nueva_capa()
nueva = (huellas.isEditable() and pe.capa() is huellas and huellas.name() == f"Huellas {RC2}"
         and huellas.crs().authid() == 'EPSG:25830' and pe.referencia.text() == RC2)
for geometria, tipo in ((wkt(X0 + 22, Y0 + 2, 5, 3), ge.PISCINA), (wkt(X0 + 30, Y0 + 5, 6, 8), ge.EDIFICIO)):
    f = QgsFeature(huellas.fields())
    f.setGeometry(QgsGeometry.fromWkt(geometria))
    f.setAttributes([tipo, None])
    huellas.addFeature(f)
dibujadas = ([pe.tipo_fila(i) for i in range(pe.tabla.rowCount())] == [ge.PISCINA, ge.EDIFICIO]
             and [pe.tabla.item(i, pe_mod.COL_ID).text() for i in range(pe.tabla.rowCount())] == [f'{RC2}_Piscina_1', RC2])
pe.destino.setFilePath(os.path.join(carpeta, 'huellas.gml'))
sin_plantas = (pe.crear_gml() is None and 'plantas' in pe.tabla.item(1, pe_mod.COL_ESTADO).text()
               and not os.path.exists(os.path.join(carpeta, 'huellas.gml')))
edificio = next(f for f in huellas.getFeatures() if f['tipo'] == ge.EDIFICIO)
huellas.changeAttributeValue(edificio.id(), huellas.fields().indexOf('plantas'), 2)
con_plantas = pe.tabla.item(1, pe_mod.COL_PLANTAS).text() == '2' and pe.crear_gml() == os.path.join(carpeta, 'huellas.gml')
huellas.rollBack()

servicios.pedir = original
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
dw.deleteLater()

checks = {
    "pestaña Edificio integrada (empieza sin capa)": integrada,
    "capa descargada: referencia, tipos, plantas e identificadores DGC": propuesta,
    "cambiar el tipo renumera los identificadores": cambio_tipo,
    "Crear GML: fichero, estado y resultado en la barra": crear,
    "botón Validar: abre el GML y permite comparar": abierto and boton_cmp,
    "ICUC: construcciones dentro de la parcela": icuc_dentro,
    "ICUC: en parte fuera y a más de 100 m (errores) y sin referencia": icuc_fuera,
    "sin referencia y capa de Navarra: aviso sin fichero": sin_referencia and navarra and ficheros,
    "descarga sin construcciones: referencia y explicación": sin_construcciones,
    "capa de parcelas: no se usa como huellas": de_parcelas,
    "Dibujar huellas: capa nueva en edición, tabla al dibujar": nueva and dibujadas,
    "plantas obligatorias (error) y GML al ponerlas": sin_plantas and con_plantas,
    "ninguna ventana emergente": not ventanas,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· pestaña Edificio e ICUC")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'ids': ids, 'tipos': tipos, 'plantas': plantas, 'ref': pe.referencia.text(),
                        'campo': pe.campoPlantas.currentField(), 'area': pe.tabla.item(0, pe_mod.COL_AREA).text(),
                        'resumen': pe.resumen.text(), 'destino': pe.destino.filePath(), 'ids_tipo': ids_tipo,
                        'creado': creado, 'barra': texto_barra,
                        'lectura': [(e.local_id, e.plantas) for e in lectura.elementos] if lectura else None,
                        'dentro': [str(i) for i in dentro.incidencias] if dentro else None,
                        'fuera': [str(i) for i in fuera.incidencias], 'res7': pe.resumen.text(), 'filas7': [(pe.tipo_fila(i), pe.tabla.item(i, pe_mod.COL_ID).text(), pe.tabla.item(i, pe_mod.COL_ESTADO).text()) for i in range(pe.tabla.rowCount())], 'n7': (nueva, huellas.name(), huellas.crs().authid()), 'lejos': [str(i) for i in lejos.incidencias], 'sin_rc': [str(i) for i in sin_rc.incidencias]})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
