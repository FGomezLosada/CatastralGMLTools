"""
Batería de la pestaña Parcela por pasos (USABILIDAD U-01 y U-02, maqueta del 28/10/2026): 1. Parcelas → 2. Operación
(alteración, «Unir parcelas», «Dividir parcela») → 3. Revisar → 4. Crear, con el nº de parcela, la fecha y el SRC en
«Opciones avanzadas» plegadas; y que con parcelas seleccionadas se trabaje solo con ellas. Sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py parcela_pasos_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os
import tempfile
import traceback

import qgis.utils
from qgis.core import Qgis, QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

qgis.utils.reloadPlugin('catastral_gml_tools')
import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import alteraciones as alt  # noqa: E402
from catastral_gml_tools.gui import desplazable  # noqa: E402
from catastral_gml_tools.gui import pestana_parcela as pp  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))

X0, Y0 = 421500.0, 4070500.0
RCS = [f"1907{40 + i:02d}1VK4810{'ABCDEFG'[i]}" for i in range(7)]  #Inventadas (datos sintéticos)
carpeta = tempfile.mkdtemp(prefix='cgt pasos ñ_')
resultados, detalles = {}, {}


def caso(nombre, funcion):
    try:
        ok, detalle = funcion()
        resultados[nombre] = bool(ok)
        if not ok:
            detalles[nombre] = detalle
    except Exception:  # noqa: BLE001
        resultados[nombre] = False
        detalles[nombre] = traceback.format_exc()[-900:]


def rect(x, y, a, b):
    return f"POLYGON(({x} {y}, {x + a} {y}, {x + a} {y + b}, {x} {y + b}, {x} {y}))"


def capa_siete(nombre='Colindantes'):
    """Siete parcelas en fila (como la capa «Colindantes» de una descarga)."""
    capa = QgsVectorLayer("Polygon?crs=EPSG:25830&field=referencia:string(20)", nombre, "memory")
    entidades = []
    for i, rc in enumerate(RCS):
        f = QgsFeature(capa.fields())
        f.setGeometry(QgsGeometry.fromWkt(rect(X0 + 20 * i, Y0, 20, 30)))
        f.setAttributes([rc])
        entidades.append(f)
    capa.dataProvider().addFeatures(entidades)
    QgsProject.instance().addMapLayer(capa)
    return capa


dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
pt = dw.pestanaParcela
dw.tabWidget.setCurrentWidget(dw.tabParcela)


def textos_barra():
    item = dw.messageBar.currentItem()
    return ' '.join([item.text()] + [e.text() for e in item.findChildren(QLabel)]) if item is not None else ''


def pasos():
    titulos = [t.titulo.text() for t in pt.findChildren(desplazable.TituloPaso)]
    esperados = ['<b>1. Parcelas</b>', '<b>2. Operación</b>', '<b>3. Revisar</b>', '<b>4. Crear</b>']
    #En orden en la pestaña, y lo de cada paso debajo de su título
    disposicion = pt.layout()
    orden = [disposicion.indexOf(t) for t in pt.findChildren(desplazable.TituloPaso)]
    return titulos == esperados and orden == sorted(orden), (titulos, orden)


caso("cuatro pasos numerados en orden: Parcelas, Operación, Revisar, Crear", pasos)


def avanzadas():
    dentro = all(pt.avanzadas.isAncestorOf(w) for w in (pt.campoLabel, pt.fecha, pt.srcCombo))
    fuera = not any(pt.avanzadas.isAncestorOf(w) for w in (pt.capaCombo, pt.campoId, pt.alteracion, pt.destino))
    return pt.avanzadas.isCollapsed() and dentro and fuera, (pt.avanzadas.isCollapsed(), dentro, fuera)


caso("«Opciones avanzadas» plegadas, con el nº de parcela, la fecha y el SRC (y nada más)", avanzadas)


def seleccion_al_elegir():
    capa = capa_siete()
    capa.selectByIds([1, 2])
    pt.capaCombo.setLayer(capa)
    pt.campoId.setField('referencia')
    filas = pt.tabla.rowCount()
    estado = pt.paso1.estado.text()
    ok = pt.soloSeleccion.isChecked() and filas == 2 and '2 de 7 seleccionadas' in estado
    #Sin selección: todas, sin marcar
    capa.removeSelection()
    pt.capaCombo.setLayer(None)
    pt.capaCombo.setLayer(capa)
    ok = ok and not pt.soloSeleccion.isChecked() and pt.tabla.rowCount() == 7 and '7 parcelas' in pt.paso1.estado.text()
    #Selección hecha después, con la casilla sin marcar: lo dice en naranja (no cambia la tabla por su cuenta)
    capa.selectByIds([3])
    naranja = pt.paso1.estado.text()
    ok = ok and pt.tabla.rowCount() == 7 and '#e67700' in naranja and 'Solo las seleccionadas' in naranja
    QgsProject.instance().removeMapLayer(capa.id())
    return ok, (filas, estado, naranja)


caso("U-02: con parcelas seleccionadas al elegir la capa, solo ellas (2 de 7), y si no, todas; aviso si se "
     "selecciona después", seleccion_al_elegir)


def unir():
    capa = capa_siete('Unir')
    pt.capaCombo.setLayer(capa)
    pt.campoId.setField('referencia')
    sin = not pt.unirBoton.isEnabled() and pt.unirInfo.isHidden()
    capa.selectByIds([1, 2])
    con = pt.unirBoton.isEnabled() and not pt.unirInfo.isHidden() and 'las 2 seleccionadas' in pt.unirInfo.text()
    capa.startEditing()
    fid = pt.unir_seleccionadas()
    unida = (fid is not None and pt.tabla.rowCount() == 1 and pt.tipo_alteracion() in (alt.AGREGACION, alt.AGRUPACION)
             and not pt.unirBoton.isEnabled() and pt.unirInfo.isHidden())
    capa.rollBack()
    QgsProject.instance().removeMapLayer(capa.id())
    return sin and con and unida, (sin, con, unida, textos_barra()[:200])


caso("«Unir parcelas»: activo y explicado solo con 2 o más seleccionadas; une al momento y pasa a agregación", unir)


def dividir():
    cerrado = (pt.division.isCollapsed() and not pt.dividirBoton.isChecked() and pt.division.isHidden()
               and pt.dividirBoton.text() == pp.TEXTO_DIVIDIR[False])
    pt.dividirBoton.click()
    abierto = (not pt.division.isCollapsed() and pt.dividirBoton.isChecked() and not pt.division.isHidden()
               and pt.dividirBoton.text() == pp.TEXTO_DIVIDIR[True])
    #Justo debajo de los botones de la operación, antes de «3. Revisar»
    disposicion = pt.layout()
    revisar = [t for t in pt.findChildren(desplazable.TituloPaso) if 'Revisar' in t.titulo.text()][0]
    debajo = disposicion.indexOf(pt.division) < disposicion.indexOf(revisar)
    pt.dividirBoton.click()
    plegado = pt.division.isCollapsed() and pt.dividirBoton.text() == pp.TEXTO_DIVIDIR[False]
    #Si se abre desde fuera (como en las otras pruebas), el botón lo refleja
    pt.division.setCollapsed(False)
    sincronizado = pt.dividirBoton.isChecked() and pt.dividirBoton.text() == pp.TEXTO_DIVIDIR[True]
    pt.division.setCollapsed(True)
    sincronizado = sincronizado and not pt.dividirBoton.isChecked()
    return cerrado and abierto and debajo and plegado and sincronizado, (cerrado, abierto, debajo, plegado, sincronizado)


caso("«Dividir parcela ▸»: abre sus opciones justo debajo (▾) y las pliega; el botón sigue al bloque", dividir)


def dividir_y_crear():
    capa = capa_siete('Dividir')
    pt.capaCombo.setLayer(capa)
    pt.campoId.setField('referencia')
    capa.selectByIds([1])
    pt.dividirBoton.click()
    pt.division.valores.setText("2")
    fids = pt.division.dividir()
    #Como al unir: la tabla (y el GML) solo con las dos resultantes, no las 8 de la capa (U-02)
    ok = (fids is not None and len(fids) == 2 and pt.tabla.rowCount() == 2 and pt.soloSeleccion.isChecked()
          and 'solo las parcelas resultantes' in textos_barra())
    capa.undoStack().undo()  #Ctrl+Z: la casilla vuelve a como estaba
    ok = ok and not pt.soloSeleccion.isChecked() and pt.tabla.rowCount() == 7
    capa.undoStack().redo()
    capa.selectByIds(fids)
    pt.soloSeleccion.setChecked(True)
    ok = ok and pt.tabla.rowCount() == 2
    pt.dividirBoton.click()
    #Crear sin abrir las opciones avanzadas
    ruta = os.path.join(carpeta, 'dividida.gml')
    pt.destino.setFilePath(ruta)
    pt.crear_gml()
    creado = os.path.isfile(ruta) and 'GML creado: dividida.gml · 2 parcelas' in textos_barra()
    capa.rollBack()
    QgsProject.instance().removeMapLayer(capa.id())
    return ok and creado and pt.avanzadas.isCollapsed(), (ok, creado, pt.tabla.rowCount(), textos_barra()[:200])


caso("dividir una parcela de una capa de 7: la tabla y el GML solo con las 2 resultantes (Ctrl+Z lo deshace), sin "
     "abrir las opciones avanzadas", dividir_y_crear)


def src_sin_deducir():
    capa = capa_siete('SRC')
    pt.capaCombo.setLayer(capa)
    original = pt.epsg_salida
    pt.epsg_salida = lambda: None  #Como una capa fuera de España: no se deduce el huso
    try:
        pt.destino.setFilePath(os.path.join(carpeta, 'src.gml'))
        pt.crear_gml()
    finally:
        pt.epsg_salida = original
    abierto = not pt.avanzadas.isCollapsed() and 'Opciones avanzadas' in textos_barra()
    pt.avanzadas.setCollapsed(True)
    QgsProject.instance().removeMapLayer(capa.id())
    return abierto, textos_barra()[:200]


caso("si no se deduce el SRC, se abren las opciones avanzadas y el aviso dice dónde elegirlo", src_sin_deducir)


def sin_capa():
    pt.capaCombo.setLayer(None)
    return pt.paso1.estado.text() == '' and not pt.unirBoton.isEnabled(), pt.paso1.estado.text()


caso("sin capa: ni recuento ni «Unir parcelas»", sin_capa)

dw.cleanup()
dw.deleteLater()
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
resultados["ninguna ventana emergente"] = not ventanas

print("=" * 60)
print("QGIS", Qgis.version(), "· Parcela por pasos: batería de casos")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, d in detalles.items():
    print("Detalles", nombre, ":", d)
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
