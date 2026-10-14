"""
Pestaña «Utilidades». De momento, «Unir GML» (multiparcela, core/unir.py): varios GML de parcela en uno solo.
Las demás utilidades (conversor 3.0 → 4.0, informes de superficies y coordenadas) irán apareciendo aquí.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import datetime
import os

from qgis.core import Qgis, QgsApplication
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core import unir as un
from ..core.incidencias import AVISO, ERROR
from .pestana_validar import PestanaValidar


class PestanaUtilidades(QWidget):
    def __init__(self, dock, parent=None):
        super().__init__(parent)
        self.dock = dock
        self.ultimo = ''
        self.construir()
        self.anadirBoton.clicked.connect(self.elegir)
        self.quitarBoton.clicked.connect(self.quitar)
        self.unirBoton.clicked.connect(self.unir)
        self.lista.model().rowsInserted.connect(self.actualizar)
        self.lista.model().rowsRemoved.connect(self.actualizar)
        self.actualizar()

    def construir(self):
        principal = QVBoxLayout(self)
        principal.setContentsMargins(0, 0, 0, 0)
        grupo = QGroupBox("Unir GML (multiparcela)", self)
        caja = QVBoxLayout(grupo)
        ayuda = QLabel("Junta varios GML de parcela en uno solo para presentarlos a la vez en la Sede. Las parcelas "
                       "repetidas se incluyen una vez; si vienen en husos distintos, se pasan al del primer fichero.", grupo)
        ayuda.setWordWrap(True)
        caja.addWidget(ayuda)
        self.lista = QListWidget(grupo)
        self.lista.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.lista.setToolTip("Ficheros GML que se van a unir (puede arrastrarlos aquí desde el Explorador)")
        self.lista.setAcceptDrops(False)
        caja.addWidget(self.lista, 1)
        fila = QHBoxLayout()
        self.anadirBoton = QPushButton(QgsApplication.getThemeIcon('/symbologyAdd.svg'), "Añadir…", grupo)
        self.quitarBoton = QPushButton(QgsApplication.getThemeIcon('/symbologyRemove.svg'), "Quitar", grupo)
        fila.addWidget(self.anadirBoton)
        fila.addWidget(self.quitarBoton)
        fila.addStretch(1)
        caja.addLayout(fila)
        salida = QHBoxLayout()
        salida.addWidget(QLabel("Fichero de salida", grupo))
        self.destino = QgsFileWidget(grupo)
        self.destino.setStorageMode(QgsFileWidget.StorageMode.SaveFile)
        self.destino.setFilter("GML (*.gml)")
        self.destino.setDialogTitle("Guardar el GML unido")
        salida.addWidget(self.destino, 1)
        caja.addLayout(salida)
        botones = QHBoxLayout()
        botones.addStretch(1)
        self.unirBoton = QPushButton(QgsApplication.getThemeIcon('/mActionMergeFeatures.svg'), "Unir GML", grupo)
        botones.addWidget(self.unirBoton)
        caja.addLayout(botones)
        principal.addWidget(grupo, 1)
        pendiente = QLabel("<i>Conversor del esquema 3.0 al 4.0 e informes de superficies y coordenadas: en próximas "
                           "versiones.</i>", self)
        pendiente.setWordWrap(True)
        pendiente.setEnabled(False)
        principal.addWidget(pendiente)
        self.setAcceptDrops(True)

    # ------------------------------------------------------------------ Lista de ficheros

    def rutas(self):
        return [self.lista.item(i).text() for i in range(self.lista.count())]

    def agregar(self, rutas):
        """Añade ficheros GML a la lista (sin repetir). Propone el fichero de salida junto al primero."""
        actuales = self.rutas()
        for ruta in rutas:
            ruta = os.path.normpath(ruta) if ruta else ruta
            if ruta and ruta.lower().endswith('.gml') and os.path.isfile(ruta) and ruta not in actuales:
                self.lista.addItem(ruta)
                actuales.append(ruta)
        if actuales and not self.destino.filePath().strip():
            self.destino.setFilePath(os.path.join(os.path.dirname(actuales[0]), 'multiparcela.gml'))

    def elegir(self, *args):
        rutas, _ = QFileDialog.getOpenFileNames(self, "Elegir los GML que se van a unir", '', "GML (*.gml)")
        self.agregar(rutas)

    def quitar(self, *args):
        for item in self.lista.selectedItems():
            self.lista.takeItem(self.lista.row(item))

    def actualizar(self, *args):
        self.unirBoton.setEnabled(self.lista.count() >= 2)
        self.quitarBoton.setEnabled(self.lista.count() > 0)

    def dragEnterEvent(self, event):  # noqa: N802 (nombre impuesto por Qt)
        #Del Explorador de Windows (ficheros) o del panel de Capas y el Navegador de QGIS (capas: su GML de origen)
        if PestanaValidar.rutas_gml(event.mimeData()):
            event.setDropAction(Qt.DropAction.CopyAction)  #Nunca «mover» (quitaría la capa o el fichero de su origen)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):  # noqa: N802 (nombre impuesto por Qt)
        self.dragEnterEvent(event)

    def dropEvent(self, event):  # noqa: N802 (nombre impuesto por Qt)
        rutas = PestanaValidar.rutas_gml(event.mimeData())
        if not rutas:
            event.ignore()
            return
        self.agregar(rutas)
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    # ------------------------------------------------------------------ Unir

    def unir(self, *args):
        self.dock.messageBar.clearWidgets()
        destino = self.destino.filePath().strip()
        if not destino:
            self.dock.warn("Indique el fichero de salida")
            return None
        if not destino.lower().endswith('.gml'):
            destino += '.gml'
        ahora = datetime.datetime.now().replace(second=0, microsecond=0)
        ok, n, incidencias = un.unir(self.rutas(), destino, ahora)
        problemas = [str(i) for i in incidencias if i.nivel in (ERROR, AVISO)]
        if not ok:
            self.dock.notify("No se han unido los GML:\n\n" + "\n".join(f"- {p}" for p in problemas if p),
                             Qgis.MessageLevel.Critical, 0)
            return None
        self.ultimo = destino
        self.dock.gml_creado(destino)
        self.dock.success(f"GML unido: {os.path.basename(destino)} · {n} parcelas de {self.lista.count()} ficheros",
                          [("Validar", self.validar), ("Abrir carpeta", self.abrir_carpeta)],
                          detalles=[str(i) for i in incidencias if i.nivel == AVISO])
        return destino

    def validar(self, *args):
        """Abre el GML unido en la pestaña Validar (solapes, huecos y comparación con el Catastro)."""
        if self.ultimo:
            self.dock.abrir_en_validar(self.ultimo)

    def abrir_carpeta(self, *args):
        if self.ultimo:
            self.dock.open_path(os.path.dirname(self.ultimo))
