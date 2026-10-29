r"""
Capturas de pantalla de la ayuda (help/img/*.png), hechas con el panel de verdad y los servicios del Catastro simulados
(tests/simulador_catastro.py: parcelas y construcciones SINTÉTICAS, sin datos reales ni personales). Se rehacen cuando
cambia el panel, para que la ayuda no se quede con capturas antiguas.

No es una prueba (no está en la lista de tools/run_tests.py). Uso, desde la carpeta del proyecto (CMD):
    tools\capturas.bat
que la lanza con QGIS 3.40 y la letra de Windows (QT_QPA_PLATFORM=windows; sin ventanas a la vista).

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import importlib.util
import os
import tempfile
import time

import qgis.utils
from qgis.core import QgsApplication, QgsMapRendererParallelJob, QgsMapSettings, QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import QEvent, QSize, Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QListWidget,
    QMessageBox,
    QScrollArea,
    QTableWidget,
)

qgis.utils.reloadPlugin('catastral_gml_tools')
import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import alteraciones as alt  # noqa: E402
from catastral_gml_tools.core.incidencias import INFO, Incidencia  # noqa: E402
from catastral_gml_tools.core.info import RAIZ  # noqa: E402

spec = importlib.util.spec_from_file_location('simulador_catastro', os.path.join(RAIZ, 'tests', 'simulador_catastro.py'))
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)
original = sim.instalar()

SALIDA = os.path.join(RAIZ, 'help', 'img')
os.makedirs(SALIDA, exist_ok=True)
ANCHO, ALTO = 540, 800  #Panel de un ancho habitual a la derecha de QGIS
hechas = []
ventanas = []
for _n in ('warning', 'information', 'critical', 'question'):
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))
#Nada se abre fuera (explorador, navegador)
dock_module.CatastralGMLToolsDockWidget.open_path = lambda self, ruta: None
dock_module.CatastralGMLToolsDockWidget.abrir_web = lambda self, url: None


def esperar():
    #Un momento con el bucle de eventos en marcha: la tabla coloca sus listas (namespace) con un temporizador; sin
    #esperar, una lista recién creada salía en la esquina de la tabla
    fin = time.monotonic() + 0.5
    while time.monotonic() < fin:
        QApplication.processEvents()
        time.sleep(0.02)
    for vista in dw.findChildren(QAbstractItemView):
        vista.doItemsLayout()
    for _ in range(4):
        QApplication.processEvents()
        #Los widgets sustituidos (p. ej. las listas de la tabla al recargarla) se borran con deleteLater: sin esto
        #salían en la captura encima de la tabla, cosa que en QGIS no pasa
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def alto_lista(vista):
    """Alto justo para ver sus filas (al menos dos), sin el hueco en blanco de debajo."""
    marco = 2 * vista.frameWidth()
    barra = vista.horizontalScrollBar().sizeHint().height() if vista.horizontalScrollBar().isVisible() else 0
    if isinstance(vista, QTableWidget):
        filas = sum(vista.rowHeight(r) for r in range(vista.rowCount()))
        minimo = 2 * vista.verticalHeader().defaultSectionSize()
        return vista.horizontalHeader().height() + max(filas, minimo) + marco + barra + 2
    vista.doItemsLayout()  #Con el texto partido en líneas al ancho de ahora
    filas = sum(vista.visualItemRect(vista.item(r)).height() + vista.spacing() for r in range(vista.count()))
    return max(filas, 3 * vista.fontMetrics().height() + 12) + marco + barra + 2


def compactar():
    """
    Tablas y listas al alto de su contenido y el panel al alto de lo que se ve (prueba a mano del 29/10/2026: en las
    capturas, las tablas estiradas dejaban grandes cuadros en blanco que no aportaban nada). Devuelve lo cambiado.
    """
    pagina = dw.tabWidget.currentWidget()
    cambiadas = []
    for vista in pagina.findChildren(QAbstractItemView):
        if isinstance(vista, (QTableWidget, QListWidget)) and vista.isVisibleTo(pagina):
            cambiadas.append((vista, vista.minimumHeight(), vista.maximumHeight()))
            vista.setFixedHeight(alto_lista(vista))
    esperar()
    zona = next((z for z in pagina.findChildren(QScrollArea) if z.widget() is not None and z.parent() is pagina), None)
    if zona is not None:
        necesario = pagina.height() - zona.viewport().height() + zona.widget().sizeHint().height()
    else:
        necesario = pagina.sizeHint().height()
    dw.resize(ANCHO, dw.height() - pagina.height() + necesario + 4)
    return cambiadas


def captura(nombre, widget=None):
    esperar()
    cambiadas = compactar() if widget is None else []
    esperar()
    imagen = (widget or dw.widget()).grab()  #A doble resolución (QT_SCALE_FACTOR=2 en tools\capturas.bat)
    imagen.save(os.path.join(SALIDA, nombre), 'PNG')
    hechas.append((nombre, imagen.width(), imagen.height()))
    for vista, minimo, maximo in cambiadas:
        vista.setMinimumHeight(minimo)
        vista.setMaximumHeight(maximo)
    dw.resize(ANCHO, ALTO)


def capas_visibles():
    raiz = QgsProject.instance().layerTreeRoot()
    return [c for c in raiz.layerOrder() if isinstance(c, QgsVectorLayer) and raiz.findLayer(c.id()) is not None
            and raiz.findLayer(c.id()).isVisible()]


def mapa(nombre, centro, factor=1.15, ancho=760, alto=440):
    """El mapa con las capas visibles (sin fondo ni selección), con la parcela y lo que tiene alrededor."""
    capas = capas_visibles()
    seleccion = {c.id(): c.selectedFeatureIds() for c in capas}
    for c in capas:  #Sin el amarillo de la selección (sin avisar al panel: la tabla sigue igual)
        c.blockSignals(True)
        c.removeSelection()
    ajustes = QgsMapSettings()
    ajustes.setLayers(capas)
    ajustes.setDestinationCrs(centro.crs())
    extension = centro.extent()
    for c in capas:
        if c.crs() == centro.crs() and c.extent().width() < 20 * max(centro.extent().width(), 1):
            extension.combineExtentWith(c.extent())
    extension.scale(factor)
    ajustes.setOutputSize(QSize(2 * ancho, 2 * alto))  #A doble resolución, como el panel: se ve nítido en la ayuda
    ajustes.setDevicePixelRatio(2)
    ajustes.setExtent(extension)
    ajustes.setBackgroundColor(QColor('white'))
    trabajo = QgsMapRendererParallelJob(ajustes)
    trabajo.start()
    trabajo.waitForFinished()
    trabajo.renderedImage().save(os.path.join(SALIDA, nombre), 'PNG')
    for c in capas:
        c.selectByIds(seleccion[c.id()])
        c.blockSignals(False)
    hechas.append((nombre, ancho, alto))


dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
dw.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
dw.resize(ANCHO, ALTO)
dw.show()

# 1. Descargar
dw.tabWidget.setCurrentWidget(dw.tabDescargar)
pes = dw.pestanaDescargar
pes.fondo.setChecked(False)  #Sin ortofoto (no se descarga nada de fuera)
pes.rc.setText(sim.RC)
pes.descargar(segundo_plano=False)
captura('descargar.png')
pt = dw.pestanaParcela
parcela = pt.capa()
mapa('mapa_descarga.png', parcela)

# 2. Parcela por pasos, con la parcela seleccionada
dw.messageBar.clearWidgets()
dw.tabWidget.setCurrentWidget(dw.tabParcela)
parcela.selectAll()
pt.capaCombo.setLayer(None)
pt.capaCombo.setLayer(parcela)  #Al elegirla con la parcela seleccionada se marca «Solo las seleccionadas»
captura('parcela.png')

# 3. Dividir: opciones abiertas con la vista previa
pt.dividirBoton.click()
pt.division.valores.setText('2')
captura('parcela_dividir.png')
pt.division.dividir()
pt.dividirBoton.click()  #Plegado
mapa('mapa_division.png', parcela)

# 4. Crear el GML
carpeta = tempfile.mkdtemp(prefix='cgt_ayuda_')
ruta = os.path.join(carpeta, f'Parcela_{sim.RC}.gml')
pt.destino.setFilePath(ruta)
pt.poner_alteracion(alt.SEGREGACION, False)
pt.crear_gml()
captura('parcela_creado.png')

# 5. Validar y comparar con el Catastro (el esquema XSD, como si la tarea lo hubiera aprobado: sin red)
dw.messageBar.clearWidgets()
dw.abrir_en_validar(ruta)
QgsApplication.taskManager().cancelAll()
esperar()
pv = dw.pestanaValidar
if pv.tarea is not None:
    pv.tarea = None
pv.esquema_comprobado([Incidencia(INFO, 'XSD-VALIDO', "Cumple el esquema XSD público de INSPIRE (la Sede comprueba "
                                                     "además otras reglas: vea los errores de arriba, si los hay)")])
pv.comparar_catastro(segundo_plano=False)
captura('validar.png')

# 6. Edificio y Utilidades
dw.messageBar.clearWidgets()
dw.tabWidget.setCurrentWidget(dw.tabEdificio)
captura('edificio.png')
dw.tabWidget.setCurrentWidget(dw.tabUtilidades)
captura('utilidades.png')

dw.cleanup()
dw.deleteLater()
servicios = sim.servicios
servicios.pedir = original
QgsProject.instance().removeAllMapLayers()
print("=" * 60)
print("Capturas de la ayuda en help/img:")
for nombre, ancho, alto in hechas:
    print(f"  OK     {nombre} ({ancho} × {alto} px)")
if ventanas:
    print("  FALLO  ventanas emergentes:", ventanas)
print("RESULTADO:", "TODO CORRECTO" if len(hechas) == 9 and not ventanas else "HAY FALLOS")
print("=" * 60)
