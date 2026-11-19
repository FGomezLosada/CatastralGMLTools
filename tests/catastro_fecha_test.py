"""
Catastro a una fecha (petición del 19/11/2026, maqueta F): capa WMS del Catastro con TIME=AAAA-MM-DD.

Se comprueba:
  - la URI lleva la fecha y el SRC (el del proyecto si el WMS lo ofrece; si no, EPSG:3857), y las fechas fuera de
    2002..hoy se ajustan;
  - en Descargar: los atajos de años, la transparencia (texto y opacidad de las capas) y «Añadir capa», que pone la capa
    arriba del todo en el grupo «Catastro a una fecha», con la fecha en el origen (QGIS 4 la guarda codificada) y sin
    repetir una fecha que ya está; en un proyecto vacío añade antes el mapa de fondo;
  - en Validar: «Ver cómo era antes» desactivado hasta comparar y al abrir otro fichero; al pulsarlo añade la capa de la
    fecha elegida en Descargar.
Necesita internet (WMS del Catastro).

Uso: tools\\probar.bat catastro_fecha_test.py

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import datetime
import traceback
from urllib.parse import unquote

import qgis.utils
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsProject
from qgis.PyQt.QtCore import QDate
from qgis.PyQt.QtWidgets import QMessageBox

import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import catastro_fecha as cf  # noqa: E402
from catastral_gml_tools.gui import fondo  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))

proyecto = QgsProject.instance()
resultados, detalles = {}, {}


def comprobar(nombre, condicion, detalle=''):
    resultados[nombre] = bool(condicion)
    if not condicion and detalle:
        detalles[nombre] = detalle


def mensajes(dw):
    return " | ".join(w.text() if hasattr(w, 'text') else '' for w in dw.messageBar.items())


dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
pes, pv = dw.pestanaDescargar, dw.pestanaValidar
try:
    d = datetime.date(2005, 6, 1)
    u = cf.uri(d, 'EPSG:25831')
    comprobar("URI con la fecha y el SRC del proyecto", u.endswith('ServidorWMS.aspx?TIME=2005-06-01') and 'crs=EPSG:25831' in u, u)
    comprobar("URI con un SRC que el WMS no ofrece: EPSG:3857", 'crs=EPSG:3857' in cf.uri(d, 'EPSG:2062'))
    comprobar("fechas ajustadas a 2002..hoy", cf.fecha_valida(datetime.date(1990, 1, 1)) == cf.PRIMERA
              and cf.fecha_valida(datetime.date(2100, 1, 1)) == datetime.date.today())
    comprobar("nombre de la capa", cf.nombre_capa(d) == "Catastro a 01/06/2005", cf.nombre_capa(d))

    #Proyecto vacío en EPSG:4326 (como uno nuevo de QGIS): «Añadir capa» pone antes el fondo y el proyecto en 25830
    proyecto.clear()
    proyecto.setCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
    comprobar("fecha propuesta: 01/01/2005", pes.fecha.date() == QDate(2005, 1, 1), pes.fecha.date().toString('dd/MM/yyyy'))
    pes.atajos[1].click()
    comprobar("el atajo 2010 pone 01/01/2010", pes.fecha.date() == QDate(2010, 1, 1), pes.fecha.date().toString('dd/MM/yyyy'))
    pes.transparencia.setValue(40)
    comprobar("la transparencia se escribe al lado (40 %)", pes.transparenciaTexto.text() == "40 %", pes.transparenciaTexto.text())
    dw.messageBar.clearWidgets()
    capa = pes.anadir_fecha()
    comprobar("«Añadir capa» crea la capa «Catastro a 01/01/2010» (WMS del Catastro)",
              capa is not None and capa.isValid() and capa.name() == "Catastro a 01/01/2010", mensajes(dw))
    if capa is not None:
        origen = unquote(capa.source())
        comprobar("la fecha va en el origen de la capa (decodificado en QGIS 4)", 'TIME=2010-01-01' in origen, origen[-120:])
        comprobar("con la transparencia elegida (opacidad 0,6)", abs(capa.renderer().opacity() - 0.6) < 1e-6,
                  capa.renderer().opacity())
        raiz = proyecto.layerTreeRoot()
        grupo = raiz.findGroup(cf.GRUPO)
        comprobar("en el grupo «Catastro a una fecha», arriba del todo", grupo is not None and raiz.children()[0] is grupo
                  and grupo.findLayer(capa.id()) is not None, [n.name() for n in raiz.children()])
        comprobar("en un proyecto vacío se añade también el mapa de fondo y el proyecto pasa a EPSG:25830",
                  bool(fondo.capas_fondo()) and proyecto.crs().authid() == 'EPSG:25830',
                  (len(fondo.capas_fondo()), proyecto.crs().authid()))
        comprobar("la barra lo dice (la fecha sale en rojo en el mapa)", 'sale en rojo' in mensajes(dw), mensajes(dw))
        otra = pes.anadir_fecha()
        comprobar("la misma fecha otra vez no se repite", otra is capa and len(cf.capas()) == 1 and 'ya estaba' in mensajes(dw),
                  (len(cf.capas()), mensajes(dw)))
        pes.transparencia.setValue(0)
        comprobar("al mover la transparencia cambia la de la capa (0 % → opaca)", abs(capa.renderer().opacity() - 1) < 1e-6,
                  capa.renderer().opacity())

    comprobar("Validar: «Ver cómo era antes» desactivado sin comparar", not pv.antesBoton.isEnabled())
    pv.antesBoton.setEnabled(True)
    pv.limpiar()
    comprobar("Validar: al abrir otro fichero se desactiva", not pv.antesBoton.isEnabled())
    pes.fecha.setDate(QDate(2015, 1, 1))
    antes = pv.ver_antes()
    comprobar("Validar: «Ver cómo era antes» añade el Catastro de la fecha de Descargar (01/01/2015)",
              antes is not None and antes.name() == "Catastro a 01/01/2015" and len(cf.capas()) == 2,
              [c.name() for c in cf.capas()])
    if antes is not None:
        grupo = proyecto.layerTreeRoot().findGroup(cf.GRUPO)
        comprobar("la última fecha añadida queda encima de las otras", grupo.children()[0].layerId() == antes.id(),
                  [n.name() for n in grupo.children()])
except Exception:  # noqa: BLE001
    resultados["sin excepciones"] = False
    detalles["excepción"] = traceback.format_exc()[-1500:]

dw.cleanup()
dw.deleteLater()
proyecto.clear()
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
resultados["ninguna ventana emergente"] = not ventanas

print("=" * 60)
print("QGIS", Qgis.version(), "· Catastro a una fecha (WMS con TIME)")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, d in detalles.items():
    print("Detalles", nombre, ":", d)
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
