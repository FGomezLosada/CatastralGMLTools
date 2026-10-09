"""
Prueba del asistente de alteraciones (mejora 15): core/alteraciones.py (propuesta de identificadores y namespaces,
comprobación de la tabla NPO/NPP/namespace y criterios orientativos de superficie) y su uso en la pestaña Parcela.
Sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py alteraciones_test.py)
"""
import os
import tempfile

import qgis.utils
from qgis.core import Qgis, QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
from qgis.PyQt.QtWidgets import QMessageBox

qgis.utils.reloadPlugin('catastral_gml_tools')
import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import alteraciones as alt  # noqa: E402
from catastral_gml_tools.core import gml_lector as gl  # noqa: E402
from catastral_gml_tools.core.incidencias import codigos  # noqa: E402
from catastral_gml_tools.gui import pestana_parcela as pp  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))

RC = '1907401VK4810H'
SDGC, LOCAL = 'SDGC', 'LOCAL'  #Valores de gml_parcela (el namespace completo es ES.SDGC.CP / ES.LOCAL.CP)

# 1. Propuestas (núcleo)
ids = [RC, 'Nueva_1', 'Mi_finca']
areas = [300, 100, 200]
seg = alt.proponer(alt.SEGREGACION, ids, areas)
div = alt.proponer(alt.DIVISION, ids, areas)
sub = alt.proponer(alt.SUBSANACION, [RC, '1907402VK4810H'], [10, 10])
agr = alt.proponer(alt.AGREGACION, [RC], [500])
agru = alt.proponer(alt.AGRUPACION, [RC], [500])
#La matriz es la mayor aunque no sea la primera fila, y lleva la RC aunque esa fila tuviera otro nombre
seg_mayor = alt.proponer(alt.SEGREGACION, ['Nueva_1', RC], [400, 100])
propuestas = (seg == [(RC, SDGC), ('Seg_1', LOCAL), ('Mi_finca', LOCAL)]
              and div == [('Div_1', LOCAL), ('Div_2', LOCAL), ('Mi_finca', LOCAL)]
              and sub == [(RC, SDGC), ('1907402VK4810H', SDGC)]
              and agr == [(RC, SDGC)] and agru == [('Agrupa_1', LOCAL)]
              and seg_mayor == [(RC, SDGC), ('Seg_1', LOCAL)]
              and alt.proponer(alt.SIN_INDICAR, ids, areas) == [(RC, SDGC), ('Nueva_1', LOCAL), ('Mi_finca', LOCAL)])

# 2. Comprobaciones
def cods(tipo, pares, superficies):
    return codigos(alt.comprobar(tipo, [p[0] for p in pares], [p[1] for p in pares], superficies))


comprobaciones = (cods(alt.SEGREGACION, seg, [500, 50, 50]) == []
                  and cods(alt.SEGREGACION, seg, [300, 100, 200]) == ['ALT-UMBRAL']   #Segrega el 50 %: solo nota
                  and cods(alt.SEGREGACION, div, areas) == ['ALT-SDGC', 'ALT-UMBRAL']
                  and cods(alt.DIVISION, div, [100, 100, 100]) == []
                  and cods(alt.DIVISION, div, [500, 50, 100]) == ['ALT-UMBRAL']
                  and cods(alt.DIVISION, seg, [100, 100, 100]) == ['ALT-SDGC']
                  and cods(alt.AGREGACION, agr, [500]) == [] and cods(alt.AGREGACION, seg, areas)[:1] == ['ALT-NPP']
                  and cods(alt.AGRUPACION, agru, [500]) == [] and cods(alt.AGRUPACION, agr, [500]) == ['ALT-SDGC']
                  and cods(alt.SUBSANACION, sub, [10, 10]) == []
                  and cods(alt.SUBSANACION, seg, areas) == ['ALT-SDGC']
                  and cods(alt.SEGREGACION, [(RC, SDGC)], [10]) == ['ALT-NPP']
                  and alt.comprobar(alt.SIN_INDICAR, ids, [SDGC, LOCAL, LOCAL], areas) == []
                  and all(i.nivel == 'info' for i in alt.comprobar(alt.SEGREGACION, [p[0] for p in seg],
                                                                   [p[1] for p in seg], [300, 100, 200])))
resumen = alt.resumen(alt.SEGREGACION, [RC, 'Seg_1'], [SDGC, LOCAL], [327, 286])
resumen_ok = resumen == f"Segregación · 2 parcelas (1 SDGC) · {RC} 327 m² (53 %) · Seg_1 286 m² (47 %)"

# 3. Pestaña Parcela: una parcela partida en dos (los dos trozos con la misma RC, como tras «Dividir objetos»)
X0, Y0 = 421500.0, 4070500.0
capa = QgsVectorLayer("Polygon?crs=EPSG:25830&field=refcat:string(20)", 'partida', 'memory')
entidades = []
for wkt in (f"POLYGON(({X0} {Y0}, {X0 + 20} {Y0}, {X0 + 20} {Y0 + 30}, {X0} {Y0 + 30}, {X0} {Y0}))",
            f"POLYGON(({X0 + 20} {Y0}, {X0 + 30} {Y0}, {X0 + 30} {Y0 + 30}, {X0 + 20} {Y0 + 30}, {X0 + 20} {Y0}))"):
    f = QgsFeature(capa.fields())
    f.setGeometry(QgsGeometry.fromWkt(wkt))
    f.setAttributes([RC])
    entidades.append(f)
capa.dataProvider().addFeatures(entidades)
QgsProject.instance().addMapLayer(capa)

dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
pt = dw.pestanaParcela
pt.capaCombo.setLayer(capa)


def tabla():
    return [(pt.tabla.item(i, pp.COL_ID).text(), pt.namespace_fila(i), pt.tabla.item(i, pp.COL_LABEL).text())
            for i in range(pt.tabla.rowCount())]


sin_info = pt.alteracionInfo.isHidden() and pt.alteracion.currentData() == alt.SIN_INDICAR
antes = tabla()
pt.alteracion.setCurrentIndex(alt.TIPOS.index(alt.SEGREGACION))
tras_seg = tabla()
texto_seg = pt.alteracionInfo.text()
pt.alteracion.setCurrentIndex(alt.TIPOS.index(alt.DIVISION))
tras_div = tabla()
texto_div = pt.alteracionInfo.text()
#Un nombre escrito por el usuario se respeta al cambiar de operación
pt.tabla.item(1, pp.COL_ID).setText('Finca_B')
pt.alteracion.setCurrentIndex(alt.TIPOS.index(alt.SEGREGACION))
tras_usuario = tabla()

ns_sdgc = 'SDGC'
interfaz = (sin_info and antes[0][0] == RC and antes[1][0] == 'Nueva_1'
            and [(t[0], t[1]) for t in tras_seg] == [(RC, ns_sdgc), ('Seg_1', 'LOCAL')]
            and 'Segregación · 2 parcelas (1 SDGC)' in texto_seg and '✔' in texto_seg
            and 'Se segrega el 33 %' in texto_seg and not pt.alteracionInfo.isHidden()
            and [(t[0], t[1]) for t in tras_div] == [('Div_1', 'LOCAL'), ('Div_2', 'LOCAL')]
            and 'División · 2 parcelas (0 SDGC)' in texto_div
            and [(t[0], t[1]) for t in tras_usuario] == [(RC, ns_sdgc), ('Finca_B', 'LOCAL')]
            and tras_seg[1][2] == 'Seg_1')

# Cambiar a mano un namespace que no encaja: aviso en naranja
pt.tabla.cellWidget(1, pp.COL_NS).setCurrentText(ns_sdgc)
aviso_manual = '⚠' in pt.alteracionInfo.text() and 'hay 2' in pt.alteracionInfo.text()
pt.tabla.cellWidget(1, pp.COL_NS).setCurrentText('LOCAL')

# 4. Crear el GML: identificadores del asistente y operación en el resultado
carpeta = tempfile.mkdtemp(prefix='cgt_alt_')
ruta = os.path.join(carpeta, 'segregacion.gml')
pt.destino.setFilePath(ruta)
pt.crear_gml()
lectura = gl.leer(ruta) if os.path.isfile(ruta) else None
gml = (lectura is not None and [(e.local_id, e.namespace) for e in lectura.elementos]
       == [(RC, 'ES.SDGC.CP'), ('Finca_B', 'ES.LOCAL.CP')]
       and dw.messageBar.currentItem() is not None
       and dw.messageBar.currentItem().level() == Qgis.MessageLevel.Success)
mensajes = ' '.join(e.text() for e in dw.messageBar.currentItem().findChildren(dock_module.QLabel)) \
    if dw.messageBar.currentItem() else ''
gml = gml and '· Segregación' in mensajes

for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
dw.deleteLater()

checks = {
    "propuestas de identificador y namespace por operación": propuestas,
    "comprobación NPP/namespace y notas de superficie": comprobaciones,
    "resumen con superficies y porcentajes": resumen_ok,
    "pestaña Parcela: el desplegable cambia la tabla y respeta los nombres del usuario": interfaz,
    "namespace cambiado a mano que no encaja: aviso": aviso_manual,
    "el GML sale con los identificadores del asistente y la operación en el resultado": gml,
    "ninguna ventana emergente": not ventanas,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· asistente de alteraciones")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'seg': seg, 'div': div, 'resumen': resumen, 'antes': antes, 'tras_seg': tras_seg,
                        'tras_div': tras_div, 'tras_usuario': tras_usuario, 'texto_seg': texto_seg, 'mensajes': mensajes,
                        'gml': [(e.local_id, e.namespace) for e in lectura.elementos] if lectura else None})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
