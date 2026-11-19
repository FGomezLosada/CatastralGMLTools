"""
Pestaña Edificio: varios cuerpos de un mismo edificio (multirrecinto, petición del 19/11/2026).

Un edificio con cuerpos separados (dos volúmenes unidos por un porche, una nave con un anexo…) va en el GML como un
solo Building con un PolygonPatch por cuerpo; si se declaran como edificios distintos, la Sede da de alta varios y hay
que corregirlo con otro modelo 902. Se comprueba:

  - el aviso del resumen con dos o más edificios, y los botones «Mismo edificio» y «Separar» (activos solo cuando toca;
    las piscinas no se juntan);
  - «Mismo edificio» deja una fila con los dos cuerpos, el identificador sin «_Edificio_N», selecciona en el mapa todos
    los cuerpos y crea un GML con un solo edificio y dos recintos, sin errores en Validar y sin el aviso de varios
    edificios; la capa no cambia;
  - «Separar» vuelve a dos edificios y Validar da el aviso BU-VARIOS-EDIFICIOS;
  - «Editar una copia» con los cuerpos juntados crea una entidad con dos partes (capa MultiPolygon, admite «Añadir parte»);
  - con otra capa se empieza de cero; agrupar() con un cuerpo borrado no junta nada.

Uso: tools\\probar.bat edificio_multirrecinto_test.py

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os
import tempfile
import traceback

import qgis.utils
from qgis.core import Qgis, QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer, QgsWkbTypes
from qgis.PyQt.QtCore import QItemSelectionModel
from qgis.PyQt.QtWidgets import QMessageBox

import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import capa_edificios as ce  # noqa: E402
from catastral_gml_tools.core import gml_edificio as ge  # noqa: E402
from catastral_gml_tools.core import gml_lector as gl  # noqa: E402
from catastral_gml_tools.core import validador  # noqa: E402
from catastral_gml_tools.gui import pestana_edificio as pe_mod  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))
dock_module.CatastralGMLToolsDockWidget.open_path = lambda self, ruta: None

carpeta = tempfile.mkdtemp(prefix='cgt multirrecinto ñ_')
X0, Y0 = 421500.0, 4070500.0
RC = '1907401VK4810H'
proyecto = QgsProject.instance()
resultados, detalles = {}, {}


def rect(x, y, w, h):
    return f"POLYGON(({x} {y}, {x} {y + h}, {x + w} {y + h}, {x + w} {y}, {x} {y}))"


def capa(nombre):
    """Dos cuerpos separados 4 m (casa y anexo) y una piscina."""
    c = QgsVectorLayer("Polygon?crs=EPSG:25830&field=tipo:string(20)&field=plantas:integer", nombre, "memory")
    entidades = []
    for wkt, tipo, plantas in ((rect(X0 + 2, Y0 + 2, 10, 8), 'edificio', 2), (rect(X0 + 16, Y0 + 2, 5, 4), 'edificio', 1),
                               (rect(X0 + 4, Y0 + 14, 6, 3), 'piscina', None)):
        f = QgsFeature(c.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes([tipo, plantas])
        entidades.append(f)
    c.dataProvider().addFeatures(entidades)
    proyecto.addMapLayer(c)
    return c


def elegir(*filas):
    pe.tabla.clearSelection()
    modelo, sel = pe.tabla.model(), pe.tabla.selectionModel()
    for i in filas:
        sel.select(modelo.index(i, 0), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)


def comprobar(nombre, condicion, detalle=''):
    resultados[nombre] = bool(condicion)
    if not condicion and detalle:
        detalles[nombre] = detalle


def crear(nombre):
    ruta = os.path.join(carpeta, nombre)
    pe.destino.setFilePath(ruta)
    dw.messageBar.clearWidgets()
    pe.crear_gml()
    return ruta if os.path.isfile(ruta) else ''


dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
pe = dw.pestanaEdificio
try:
    c = capa('casa y anexo')
    pe.soloSeleccion.setChecked(False)
    pe.capaCombo.setLayer(c)
    pe.campoPlantas.setField('plantas')
    pe.referencia.setText(RC)
    pe.proponer_ids()
    comprobar("tres filas al empezar", len(pe.filas) == 3, len(pe.filas))
    comprobar("el resumen avisa de que la Sede dará de alta 2 edificios", 'Mismo edificio' in pe.resumen.text()
              and 'dará de alta 2 edificios' in pe.resumen.text(), pe.resumen.text())
    elegir(0)
    comprobar("con un solo edificio elegido, «Mismo edificio» desactivado", not pe.mismoBoton.isEnabled())
    elegir(0, 2)
    comprobar("con una piscina elegida, «Mismo edificio» desactivado", not pe.mismoBoton.isEnabled())
    elegir(0, 1)
    comprobar("con dos edificios elegidos, «Mismo edificio» activo y «Separar» no",
              pe.mismoBoton.isEnabled() and not pe.separarBoton.isEnabled())

    pe.mismo_edificio()
    comprobar("tras «Mismo edificio», dos filas (edificio y piscina)", len(pe.filas) == 2, len(pe.filas))
    fila = pe.filas[0]
    comprobar("la fila juntada tiene los dos cuerpos y sus dos entidades", fila.partes == 2 and len(fila.fids) == 2,
              (fila.partes, fila.fids))
    comprobar("la tabla lo dice («Un edificio, 2 cuerpos»)", pe.tabla.item(0, pe_mod.COL_ESTADO).text() == 'Un edificio, 2 cuerpos',
              pe.tabla.item(0, pe_mod.COL_ESTADO).text())
    ids = [pe.tabla.item(i, pe_mod.COL_ID).text() for i in range(2)]
    comprobar("identificadores: la referencia sola (un edificio) y RC_Piscina_1", ids == [RC, f'{RC}_Piscina_1'], ids)
    comprobar("plantas: las mayores de los cuerpos (2)", pe.tabla.item(0, pe_mod.COL_PLANTAS).text() == '2',
              pe.tabla.item(0, pe_mod.COL_PLANTAS).text())
    comprobar("sin el aviso de varios edificios", 'dará de alta' not in pe.resumen.text(), pe.resumen.text())
    comprobar("la capa no cambia (3 entidades)", c.featureCount() == 3 and not c.isModified())
    elegir(0)
    comprobar("al elegir el edificio juntado se seleccionan en el mapa sus dos cuerpos",
              sorted(c.selectedFeatureIds()) == sorted(fila.fids), c.selectedFeatureIds())
    comprobar("«Separar» activo con el edificio juntado elegido", pe.separarBoton.isEnabled())

    ruta = crear('juntado.gml')
    texto = open(ruta, encoding='iso-8859-1').read() if ruta else ''
    edificios = [e for e in gl.leer(ruta).elementos if e.tipo == gl.EDIFICIO] if ruta else []
    comprobar("GML creado con un solo edificio", ruta and len(edificios) == 1, len(edificios))
    comprobar("el edificio lleva dos recintos (PolygonPatch) y la piscina va aparte",
              texto.count('<gml:PolygonPatch>') == 2 and 'openAirPool' in texto, texto.count('<gml:PolygonPatch>'))
    informe = validador.validar(ruta) if ruta else None
    codigos = [i.codigo for i in informe.incidencias] if informe else []
    comprobar("Validar: sin errores y sin el aviso de varios edificios",
              informe and not informe.errores and 'BU-VARIOS-EDIFICIOS' not in codigos,
              [str(i) for i in informe.errores] if informe else 'sin informe')

    pe.separar()
    comprobar("«Separar» vuelve a tres filas", len(pe.filas) == 3, len(pe.filas))
    ids = [pe.tabla.item(i, pe_mod.COL_ID).text() for i in range(3)]
    comprobar("identificadores otra vez con _Edificio_1 y _Edificio_2", ids[:2] == [f'{RC}_Edificio_1', f'{RC}_Edificio_2'], ids)
    ruta = crear('separados.gml')
    informe = validador.validar(ruta) if ruta else None
    aviso = [i for i in informe.incidencias if i.codigo == 'BU-VARIOS-EDIFICIOS'] if informe else []
    comprobar("Validar con dos edificios: informa de que la Sede dará de alta 2 (BU-VARIOS-EDIFICIOS) sin error",
              informe and not informe.errores and len(aviso) == 1 and '902' in aviso[0].mensaje,
              [str(i) for i in informe.incidencias] if informe else 'sin informe')

    elegir(0, 1)
    pe.mismo_edificio()
    copia = pe.nueva_capa()
    partes = [len(f.geometry().asGeometryCollection()) for f in copia.getFeatures()]
    comprobar("«Editar una copia» con los cuerpos juntados: una entidad de dos partes y la piscina",
              sorted(partes) == [1, 2], partes)
    comprobar("la capa de huellas es MultiPolygon (admite «Añadir parte»)",
              QgsWkbTypes.isMultiType(copia.wkbType()), QgsWkbTypes.displayString(copia.wkbType()))
    comprobar("en la copia, sin grupos (ya es una entidad)", pe.capa() is copia and pe.grupos == [] and len(pe.filas) == 2,
              (pe.grupos, len(pe.filas)))
    copia.rollBack()

    pe.capaCombo.setLayer(c)
    comprobar("al volver a la capa original, empieza de cero (3 filas)", len(pe.filas) == 3, len(pe.filas))

    filas = ce.leer_capa(c)
    juntas = ce.agrupar(filas, [(filas[0].fid, 99999)])
    comprobar("agrupar() con un cuerpo que ya no existe no junta nada", len(juntas) == 3, len(juntas))
    juntas = ce.agrupar(filas, [(filas[1].fid, filas[0].fid)])
    comprobar("agrupar() deja el edificio juntado en el lugar del primero de la capa",
              len(juntas) == 2 and juntas[0].partes == 2 and juntas[1].tipo == ge.PISCINA, [(f.fid, f.partes) for f in juntas])
except Exception:  # noqa: BLE001
    resultados["sin excepciones"] = False
    detalles["excepción"] = traceback.format_exc()[-1500:]

dw.cleanup()
dw.deleteLater()
proyecto.removeAllMapLayers()
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
resultados["ninguna ventana emergente"] = not ventanas

print("=" * 60)
print("QGIS", Qgis.version(), "· Edificio: varios cuerpos de un mismo edificio (multirrecinto)")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, d in detalles.items():
    print("Detalles", nombre, ":", d)
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
