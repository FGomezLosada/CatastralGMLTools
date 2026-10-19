"""
Utilidad «Comparar dos GML» de la pestaña Utilidades (mejora 34): elige dos GML, los compara (core/comparar_gml.py),
resume las diferencias en el panel y escribe un informe HTML junto al primero; «Ver en el mapa» carga los dos (el
segundo, con trazo azul discontinuo encima del primero).

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import contextlib
import os
from html import escape

from qgis.core import QgsApplication, QgsFeedback, QgsProject, QgsTask
from qgis.gui import QgsFileWidget
from qgis.PyQt import sip
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..core import comparar_gml as cg
from ..core import gml_lector as gl

MAX_LINEAS = 12
AZUL = QColor(25, 113, 194)
ICONO = '/algorithms/mAlgorithmSymmetricalDifference.svg'
GRUPO = 'catastral_gml_tools/comparacion_gml'  #Propiedad del grupo de la comparación en el mapa


class BloqueComparar(QWidget):
    def __init__(self, pestana, parent=None):
        super().__init__(parent)
        self.pestana = pestana
        self.comparacion = None
        self.informe = ''
        self.tarea = None
        self.construir()
        self.gmlA.fileChanged.connect(self.actualizar)
        self.gmlB.fileChanged.connect(self.actualizar)
        self.compararBoton.clicked.connect(self.comparar)
        self.actualizar()

    def construir(self):
        caja = QVBoxLayout(self)
        formulario = QFormLayout()
        self.gmlA = QgsFileWidget(self)
        self.gmlB = QgsFileWidget(self)
        for campo, titulo in ((self.gmlA, "Elegir el primer GML"), (self.gmlB, "Elegir el segundo GML")):
            campo.setStorageMode(QgsFileWidget.StorageMode.GetFile)
            campo.setFilter("GML (*.gml *.xml)")
            campo.setDialogTitle(titulo)
        formulario.addRow("Primero", self.gmlA)
        formulario.addRow("Segundo", self.gmlB)
        caja.addLayout(formulario)
        self.resultado = QLabel(self)
        self.resultado.setWordWrap(True)
        self.resultado.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        caja.addWidget(self.resultado)
        botones = QHBoxLayout()
        botones.addStretch(1)
        self.compararBoton = QPushButton(QgsApplication.getThemeIcon(ICONO), "Comparar", self)
        self.compararBoton.setToolTip("Compara los dos ficheros (da igual de dónde salgan) y escribe un informe junto al "
                                      "primero (…_comparacion.html)")
        botones.addWidget(self.compararBoton)
        caja.addLayout(botones)
        caja.addStretch(1)

    def rutas(self):
        """Las dos rutas normalizadas (en Windows, el selector puede devolverlas con «/»)."""
        return tuple(os.path.normpath(r) if r else '' for r in (self.gmlA.filePath().strip(), self.gmlB.filePath().strip()))

    def actualizar(self, *args):
        a, b = self.rutas()
        listos = bool(a and b and os.path.isfile(a) and os.path.isfile(b))
        self.compararBoton.setEnabled(listos)
        if not listos:
            self.resultado.setText("<small>Elija los dos GML que quiere comparar (también puede arrastrarlos: el primero "
                                   "que suelte va arriba)</small>" if not (a and b) else
                                   "<small><span style='color:#c92a2a'>No se encuentra alguno de los ficheros</span></small>")
        elif os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b)):
            self.compararBoton.setEnabled(False)
            self.resultado.setText("<small><span style='color:#c92a2a'>Es el mismo fichero dos veces</span></small>")
        else:
            self.resultado.clear()

    def soltar(self, rutas):
        """Dos ficheros: primero y segundo. Uno: al primero si está vacío; si no, al segundo."""
        if len(rutas) >= 2:
            self.gmlA.setFilePath(rutas[0])
            self.gmlB.setFilePath(rutas[1])
        elif not self.gmlA.filePath().strip():
            self.gmlA.setFilePath(rutas[0])
        else:
            self.gmlB.setFilePath(rutas[0])

    def comparar(self, *args, segundo_plano=True):
        """Compara los dos GML (en segundo plano: con ficheros de cientos de parcelas tarda) y muestra el resultado."""
        dock = self.pestana.dock
        dock.messageBar.clearWidgets()
        a, b = self.rutas()
        if not segundo_plano:
            return self.mostrar(cg.comparar(a, b))
        self.cancelar_tareas()
        self.tarea = TareaComparar(a, b, self)
        self.compararBoton.setEnabled(False)
        self.compararBoton.setText("Comparando…")
        QgsApplication.taskManager().addTask(self.tarea)
        return None

    def terminada(self, comparacion):
        self.tarea = None
        self.compararBoton.setText("Comparar")
        self.actualizar()
        if comparacion is not None:
            self.mostrar(comparacion)

    def cancelar_tareas(self):
        if self.tarea is not None and not sip.isdeleted(self.tarea):
            with contextlib.suppress(RuntimeError):
                self.tarea.cancel()
        self.tarea = None

    def mostrar(self, c):
        dock = self.pestana.dock
        self.comparacion = c
        lineas = cg.resumen(c)
        if c.errores:
            self.resultado.setText("<small><span style='color:#c92a2a'>" + "<br>".join(escape(x) for x in lineas)
                                   + "</span></small>")
            dock.warn("No se han podido comparar: " + c.errores[0])
            return None
        visibles = lineas[:MAX_LINEAS] + ([f"… y {len(lineas) - MAX_LINEAS} más (en el informe)"]
                                          if len(lineas) > MAX_LINEAS else [])
        cabecera = ("<b style='color:#2b8a3e'>Son iguales a efectos de la Sede (ningún vértice se separa más de 1 cm)</b>"
                    if c.iguales() else "<b style='color:#e67700'>Hay diferencias</b>")
        self.resultado.setText(f"<small>{cabecera}<br>" + "<br>".join(escape(x) for x in visibles) + "</small>")
        try:
            self.informe = cg.escribir(c)
        except OSError as e:
            self.informe = ''
            dock.warn(f"Comparados, pero no se ha podido escribir el informe: {e}")
            return None
        botones = [("Abrir informe", self.abrir_informe), ("Ver en el mapa", self.ver_en_mapa)]
        dock.success(f"Comparación: {os.path.basename(self.informe)}", botones)
        return self.informe

    def abrir_informe(self, *args):
        if self.informe:
            self.pestana.dock.open_path(self.informe)

    def ver_en_mapa(self, *args):
        """
        Los dos GML en el mapa, en un grupo «Comparación»: el segundo, en azul discontinuo y sin relleno, encima del
        primero. No se usa la carga de Validar: al cargar el segundo quitaba la vista del primero (es otro fichero).
        """
        from . import estilos
        from .pestana_validar import PROPIEDAD_GML, quitar_vistas_anteriores
        c = self.comparacion
        if c is None or c.errores:
            return None
        proyecto = QgsProject.instance()
        quitar_vistas_anteriores(c.ruta_a)  #Las vistas de otros GML (también una comparación anterior)
        raiz = proyecto.layerTreeRoot()
        for grupo in [g for g in raiz.findGroups(True) if g.customProperty(GRUPO)]:
            proyecto.removeMapLayers(grupo.findLayerIds())
            (grupo.parent() or raiz).removeChildNode(grupo)
        grupo = raiz.insertGroup(0, f"Comparación {os.path.basename(c.ruta_a)} · {os.path.basename(c.ruta_b)}")
        grupo.setCustomProperty(GRUPO, True)
        grupo.setCustomProperty(PROPIEDAD_GML, c.ruta_a)
        capas = []
        for lectura, ruta, nombre in ((c.vista_b or c.lectura_b, c.ruta_b, "segundo"),
                                      (c.vista_a or c.lectura_a, c.ruta_a, "primero")):
            capa = estilos.aplicar(gl.capa(lectura, f"{os.path.splitext(os.path.basename(ruta))[0]} ({nombre})"))
            capa.setCustomProperty(PROPIEDAD_GML, ruta)  #Se puede arrastrar a otra pestaña
            proyecto.addMapLayer(capa, False)
            grupo.addLayer(capa)
            capas.append(capa)
        segunda, primera = capas
        renderer = segunda.renderer()
        for i, categoria in enumerate(renderer.categories() if hasattr(renderer, 'categories') else []):
            simbolo = categoria.symbol().clone()
            capa_simbolo = simbolo.symbolLayer(0)
            if hasattr(capa_simbolo, 'setStrokeStyle'):
                capa_simbolo.setFillColor(QColor(0, 0, 0, 0))
                capa_simbolo.setStrokeColor(AZUL)
                capa_simbolo.setStrokeWidth(0.6)
                capa_simbolo.setStrokeStyle(Qt.PenStyle.DashLine)
            renderer.updateCategorySymbol(i, simbolo)
        segunda.triggerRepaint()
        iface = getattr(self.pestana.dock, 'iface', None)
        if iface is not None and hasattr(iface, 'mapCanvas'):
            lienzo = iface.mapCanvas()
            lienzo.setExtent(lienzo.mapSettings().layerExtentToOutputExtent(primera, primera.extent()).buffered(5))
            lienzo.refresh()
        return primera, segunda


class TareaComparar(QgsTask):
    """La comparación en segundo plano, cancelable (el gestor de tareas de QGIS muestra el avance)."""

    def __init__(self, ruta_a, ruta_b, bloque):
        super().__init__("Catastral GML Tools: comparar dos GML", QgsTask.Flag.CanCancel)
        self.ruta_a, self.ruta_b, self.bloque = ruta_a, ruta_b, bloque
        self.resultado = None
        self.feedback = QgsFeedback()
        self.feedback.progressChanged.connect(self.setProgress)

    def cancel(self):
        self.feedback.cancel()
        super().cancel()

    def run(self):
        try:
            self.resultado = cg.comparar(self.ruta_a, self.ruta_b, self.feedback)
        except Exception as e:  #Nunca debe cerrar QGIS
            self.resultado = cg.Comparacion(self.ruta_a, self.ruta_b, None, None, [], [], [], [f"Error inesperado: {e}"])
        return not self.isCanceled()

    def finished(self, correcto):
        if self.bloque is None or sip.isdeleted(self.bloque):
            return
        self.bloque.terminada(self.resultado if correcto else None)
