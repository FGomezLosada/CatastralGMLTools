"""
Utilidad «Identidad gráfica con el Catastro (simulación)» de la pestaña Utilidades (AU-58): elige el GML de un
levantamiento, pide al Catastro las parcelas de alrededor (en segundo plano) y simula el criterio de identidad gráfica
del anexo II de la Resolución de 2020 (core/identidad.py): resultado en el panel, informe HTML con croquis y, en el mapa,
el margen, la parcela catastral, el GML y lo que queda fuera.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import contextlib
import os
from html import escape

from qgis.core import QgsApplication, QgsFeature, QgsProject, QgsTask, QgsVectorLayer
from qgis.gui import QgsFileWidget
from qgis.PyQt import sip
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..core import identidad as idg

ICONO = '/algorithms/mAlgorithmBuffer.svg'
GRUPO = 'catastral_gml_tools/identidad'  #Propiedad del grupo de la simulación en el mapa
MAX_LINEAS = 10


class BloqueIdentidad(QWidget):
    def __init__(self, pestana, parent=None):
        super().__init__(parent)
        self.pestana = pestana
        self.simulacion = None
        self.informe = ''
        self.tarea = None
        self.construir()
        self.fichero.fileChanged.connect(self.actualizar)
        self.comprobarBoton.clicked.connect(self.comprobar)
        self.actualizar()

    def construir(self):
        caja = QVBoxLayout(self)
        formulario = QFormLayout()
        self.fichero = QgsFileWidget(self)
        self.fichero.setStorageMode(QgsFileWidget.StorageMode.GetFile)
        self.fichero.setFilter("GML (*.gml *.xml)")
        self.fichero.setDialogTitle("Elegir el GML del levantamiento (representación gráfica alternativa)")
        formulario.addRow("GML", self.fichero)
        self.margen = QComboBox(self)
        self.margen.addItem("Según la cartografía catastral", None)
        self.margen.addItem("Urbana: ±0,50 m", 'urbana')
        self.margen.addItem("Rústica: ±2,00 m", 'rústica')
        self.margen.setToolTip("El margen depende de la cartografía (urbana o rústica) en que está la parcela catastral, "
                               "no de su naturaleza: se deduce de su referencia; elija uno si sabe que es el otro")
        formulario.addRow("Margen", self.margen)
        caja.addLayout(formulario)
        self.resultado = QLabel(self)
        self.resultado.setWordWrap(True)
        self.resultado.setTextFormat(Qt.TextFormat.RichText)
        self.resultado.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        caja.addWidget(self.resultado)
        botones = QHBoxLayout()
        botones.addStretch(1)
        self.comprobarBoton = QPushButton(QgsApplication.getThemeIcon(ICONO), "Comprobar", self)
        self.comprobarBoton.setToolTip("Pide al Catastro las parcelas de alrededor y comprueba los dos criterios del margen "
                                       "de tolerancia (necesita internet). Simulación no oficial")
        botones.addWidget(self.comprobarBoton)
        caja.addLayout(botones)
        caja.addStretch(1)

    def ruta(self):
        return os.path.normpath(self.fichero.filePath().strip()) if self.fichero.filePath().strip() else ''

    def soltar(self, rutas):
        self.fichero.setFilePath(rutas[0])

    def actualizar(self, *args):
        self.comprobarBoton.setEnabled(bool(self.ruta()) and os.path.isfile(self.ruta()) and self.tarea is None)

    def comprobar(self, *args, segundo_plano=True):
        dock = self.pestana.dock
        dock.messageBar.clearWidgets()
        forzado = self.margen.currentData()
        if not segundo_plano:
            return self.mostrar(idg.comprobar_gml(self.ruta(), forzado))
        self.cancelar_tareas()
        self.tarea = TareaIdentidad(self.ruta(), forzado, self)
        self.comprobarBoton.setEnabled(False)
        self.comprobarBoton.setText("Consultando el Catastro…")
        QgsApplication.taskManager().addTask(self.tarea)
        return None

    def terminada(self, simulacion):
        self.tarea = None
        self.comprobarBoton.setText("Comprobar")
        self.actualizar()
        if simulacion is not None:
            self.mostrar(simulacion)

    def cancelar_tareas(self):
        if self.tarea is not None and not sip.isdeleted(self.tarea):
            with contextlib.suppress(RuntimeError):
                self.tarea.cancel()
        self.tarea = None

    def mostrar(self, simulacion):
        dock = self.pestana.dock
        self.simulacion = simulacion
        r = simulacion.resultado
        if r is None:
            mensaje = simulacion.errores[0].mensaje if simulacion.errores else "No se ha podido comprobar"
            self.resultado.setText(f"<small><span style='color:#c92a2a'>{escape(mensaje)}</span></small>")
            dock.warn(f"No se ha podido comprobar la identidad gráfica: {mensaje}")
            return None
        color = '#2b8a3e' if r.cumple else '#c92a2a'
        lineas = idg.resumen(r)
        visibles = lineas[:MAX_LINEAS] + ([f"… y {len(lineas) - MAX_LINEAS} más (en el informe)"]
                                          if len(lineas) > MAX_LINEAS else [])
        self.resultado.setText(f"<small><b style='color:{color}'>{escape(idg.veredicto(r))}</b> (simulación)<br>"
                               + "<br>".join(escape(x) for x in visibles) + "</small>")
        try:
            self.informe = idg.escribir(simulacion)
        except OSError as e:
            self.informe = ''
            dock.warn(f"Comprobado, pero no se ha podido escribir el informe: {e}")
            return None
        botones = [("Abrir informe", self.abrir_informe), ("Ver en el mapa", self.ver_en_mapa)]
        notas = ["Simulación no oficial: el certificado válido es el de la Sede (Identidad de parcela)"]
        if r.cumple:
            dock.success(f"{idg.veredicto(r)}: {os.path.basename(self.informe)}", botones, notas=notas)
        else:
            dock.success(f"{idg.veredicto(r)}: {os.path.basename(self.informe)}", botones,
                         detalles=[x for x in lineas if x.startswith(('Fuera', '2.', 'Con un'))][:4], notas=notas)
        return self.informe

    def abrir_informe(self, *args):
        if self.informe:
            self.pestana.dock.open_path(self.informe)

    def ver_en_mapa(self, *args):
        """Un grupo con el margen (azul), la parcela catastral (gris), el GML (naranja) y lo que queda fuera (rojo)."""
        s = self.simulacion
        if s is None or s.resultado is None or s.resultado.referencia is None:
            return None
        r = s.resultado
        proyecto = QgsProject.instance()
        raiz = proyecto.layerTreeRoot()
        for grupo in [g for g in raiz.findGroups(True) if g.customProperty(GRUPO)]:
            proyecto.removeMapLayers(grupo.findLayerIds())
            (grupo.parent() or raiz).removeChildNode(grupo)
        grupo = raiz.insertGroup(0, f"Identidad gráfica · {os.path.basename(s.ruta)}")
        grupo.setCustomProperty(GRUPO, True)
        capas = []
        if r.tramos:
            capas.append(self._capa("LineString", "Fuera del margen", [idg.exterior(r.rgga).difference(r.banda)],
                                    '#c92a2a', 0.9))
        capas.append(self._capa("Polygon", "GML", [r.rgga], '#e8590c', 0.6, relleno=False))
        capas.append(self._capa("Polygon", f"Catastral {', '.join(r.catastrales)}", [r.referencia], '#495057', 0.4,
                                relleno=False))
        capas.append(self._capa("Polygon", f"Margen ±{r.margen:.2f} m".replace('.', ','), [r.banda], '#4dabf7', 0.2))
        for capa in capas:
            proyecto.addMapLayer(capa, False)
            grupo.addLayer(capa)
        return capas

    def _capa(self, tipo, nombre, geometrias, color, ancho, relleno=True):
        capa = QgsVectorLayer(f"{tipo}?crs=EPSG:{self.simulacion.epsg}", nombre, 'memory')
        entidades = []
        for g in geometrias:
            entidad = QgsFeature()
            entidad.setGeometry(g)
            entidades.append(entidad)
        capa.dataProvider().addFeatures(entidades)
        capa.updateExtents()
        simbolo = capa.renderer().symbol()
        simbolo.setColor(QColor(color))
        capa_simbolo = simbolo.symbolLayer(0)
        if tipo == "Polygon":
            capa_simbolo.setStrokeColor(QColor(color))
            capa_simbolo.setStrokeWidth(ancho)
            if not relleno:
                capa_simbolo.setBrushStyle(Qt.BrushStyle.NoBrush)
            else:
                transparente = QColor(color)
                transparente.setAlpha(90)
                capa_simbolo.setFillColor(transparente)
        else:
            capa_simbolo.setWidth(ancho)
        return capa


class TareaIdentidad(QgsTask):
    """La consulta al Catastro y la comprobación, en segundo plano (cancelable)."""

    def __init__(self, ruta, forzado, bloque):
        super().__init__("Catastral GML Tools: identidad gráfica", QgsTask.Flag.CanCancel)
        self.ruta, self.forzado, self.bloque = ruta, forzado, bloque
        self.resultado = None

    def run(self):
        try:
            self.resultado = idg.comprobar_gml(self.ruta, self.forzado)
        except Exception as e:  #Nunca debe cerrar QGIS
            self.resultado = idg.Simulacion(self.ruta, errores=[idg.Incidencia(idg.ERROR, 'IDG-ERROR',
                                                                               f"Error inesperado: {e}")])
        return not self.isCanceled()

    def finished(self, correcto):
        if self.bloque is None or sip.isdeleted(self.bloque):
            return
        self.bloque.terminada(self.resultado if correcto else None)
