"""
Utilidad «Puntos de apoyo para el editor de la Sede» (mejora 33; normativa ED-03): elige una capa del proyecto (puntos del
levantamiento, la parcela dibujada…), toma sus vértices (todos o los de los elementos seleccionados) y los guarda en el
TXT «x y» que carga el editor parcelario de la Sede, en el huso de la Sede (core/apoyo.py).

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os

from qgis.core import Qgis, QgsApplication, QgsGeometry, QgsProject
from qgis.gui import QgsFileWidget, QgsMapLayerComboBox
from qgis.PyQt.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..core import apoyo as ap
from ..core import geometria as geo
from .bloque_coordenadas import HUSOS

ICONO = '/mActionCapturePoint.svg'
AUTOMATICO = 0


class BloqueApoyo(QWidget):
    def __init__(self, pestana, parent=None):
        super().__init__(parent)
        self.pestana = pestana
        self.ultimo = ''
        self.destino_automatico = ''
        self.construir()
        self.capa.layerChanged.connect(self.capa_cambiada)
        self.soloSeleccion.toggled.connect(self.actualizar)
        self.huso.currentIndexChanged.connect(self.actualizar)
        self.crearBoton.clicked.connect(self.crear)
        self.capa_cambiada()

    def construir(self):
        caja = QVBoxLayout(self)
        formulario = QFormLayout()
        self.capa = QgsMapLayerComboBox(self)
        self.capa.setFilters(Qgis.LayerFilters(Qgis.LayerFilter.PointLayer | Qgis.LayerFilter.LineLayer
                                               | Qgis.LayerFilter.PolygonLayer))
        self.capa.setAllowEmptyLayer(True)
        self.capa.setLayer(None)
        self.capa.setToolTip("Capa con los puntos del levantamiento, o la parcela o las líneas cuyos vértices quiera tener "
                             "en el editor")
        formulario.addRow("Capa", self.capa)
        self.soloSeleccion = QCheckBox("Solo los elementos seleccionados", self)
        formulario.addRow("", self.soloSeleccion)
        self.huso = QComboBox(self)
        self.huso.addItem("Automático (según la posición)", AUTOMATICO)
        for epsg, nombre in HUSOS:
            self.huso.addItem(nombre, epsg)
        self.huso.setToolTip("El del GML de la parcela: el editor de la Sede trabaja en el huso de la parcela")
        formulario.addRow("SRC", self.huso)
        self.destino = QgsFileWidget(self)
        self.destino.setStorageMode(QgsFileWidget.StorageMode.SaveFile)
        self.destino.setFilter("Texto (*.txt)")
        self.destino.setDialogTitle("Guardar los puntos de apoyo")
        formulario.addRow("Fichero", self.destino)
        caja.addLayout(formulario)
        self.estado = QLabel(self)
        self.estado.setWordWrap(True)
        caja.addWidget(self.estado)
        botones = QHBoxLayout()
        botones.addStretch(1)
        self.crearBoton = QPushButton(QgsApplication.getThemeIcon('/mActionFileSave.svg'), "Crear TXT", self)
        botones.addWidget(self.crearBoton)
        caja.addLayout(botones)
        caja.addStretch(1)

    def capa_cambiada(self, *args):
        capa = self.capa.currentLayer()
        if capa is not None:
            actual = self.destino.filePath().strip()
            if not actual or actual == self.destino_automatico:
                carpeta = os.path.dirname(actual) if actual else (QgsProject.instance().homePath() or os.path.expanduser('~'))
                self.destino_automatico = ap.ruta_por_defecto(carpeta, capa.name())
                self.destino.setFilePath(self.destino_automatico)
            self.soloSeleccion.setChecked(capa.selectedFeatureCount() > 0)
        self.actualizar()

    def geometrias(self):
        """(geometrías en el SRC de destino, epsg) de la capa elegida, o ([], None)."""
        capa = self.capa.currentLayer()
        if capa is None:
            return [], None
        elementos = capa.getSelectedFeatures() if self.soloSeleccion.isChecked() else capa.getFeatures()
        originales = [f.geometry() for f in elementos if f.hasGeometry()]
        if not originales:
            return [], None
        epsg = self.huso.currentData()
        if epsg == AUTOMATICO:
            propio = geo.epsg_de(capa.crs())
            epsg = propio if propio in geo.SRC_ADMITIDOS else geo.epsg_recomendado(QgsGeometry.unaryUnion(originales),
                                                                                    capa.crs())
        if epsg is None:
            return [], None
        return [geo.transformar(g, capa.crs(), epsg) for g in originales], epsg

    def actualizar(self, *args):
        geometrias, epsg = self.geometrias()
        lista = ap.puntos(geometrias)
        if self.capa.currentLayer() is None:
            texto = "Elija la capa con los puntos o vértices."
        elif not lista:
            texto = "<span style='color:#c92a2a'>La capa no tiene vértices (o no hay elementos seleccionados).</span>"
        elif len(lista) > ap.MAX_PUNTOS:
            texto = (f"<span style='color:#c92a2a'>{len(lista)} puntos: demasiados para el editor (máximo "
                     f"{ap.MAX_PUNTOS}). Seleccione los que necesite.</span>")
        else:
            texto = f"{len(lista)} punto{'s' if len(lista) != 1 else ''} sin repetir · EPSG:{epsg}"
        self.estado.setText(f"<small>{texto}</small>")
        self.crearBoton.setEnabled(0 < len(lista) <= ap.MAX_PUNTOS)

    def crear(self, *args):
        dock = self.pestana.dock
        dock.messageBar.clearWidgets()
        geometrias, epsg = self.geometrias()
        lista = ap.puntos(geometrias)
        ruta = self.destino.filePath().strip()
        if not lista:
            dock.warn("No hay puntos que guardar")
            return None
        if not ruta:
            dock.warn("Indique el fichero TXT de salida")
            return None
        if not ruta.lower().endswith('.txt'):
            ruta += '.txt'
        try:
            ap.escribir(ruta, lista)
        except OSError as e:
            dock.warn(f"No se han guardado los puntos: {e}")
            return None
        self.ultimo = ruta
        dock.success(f"Puntos de apoyo: {os.path.basename(ruta)} · {len(lista)} puntos · EPSG:{epsg}. En el editor "
                     "parcelario de la Sede, cárguelos como puntos de apoyo (fichero TXT)",
                     [("Abrir carpeta", self.abrir_carpeta)])
        return ruta

    def abrir_carpeta(self, *args):
        if self.ultimo:
            self.pestana.dock.open_path(os.path.dirname(self.ultimo))
