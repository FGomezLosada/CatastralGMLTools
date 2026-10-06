"""
Pestaña «Validar»: abre un GML de parcela o de edificio, muestra su contenido (identificadores, namespace,
superficie declarada y calculada) y lo carga en el mapa para revisarlo. Las comprobaciones previas a la Sede
se añaden en la mejora 10.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os

from qgis.core import Qgis, QgsApplication, QgsProject
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import geometria as geo
from ..core import gml_lector as gl
from ..core.incidencias import AVISO, ERROR
from . import estilos

CABECERAS = ['Tipo', 'Identificador (localId)', 'Namespace', 'Sup. GML m²', 'Sup. calculada m²']


class PestanaValidar(QWidget):
    def __init__(self, dock, parent=None):
        super().__init__(parent)
        self.dock = dock
        self.resultado = None
        self.ruta = ''
        self.construir()
        self.setAcceptDrops(True)  #Se puede arrastrar un GML desde el Explorador de Windows a la pestaña
        self.fichero.lineEdit().setAcceptDrops(False)  #Que lo recoja la pestaña entera, también sobre la casilla del fichero
        self.fichero.fileChanged.connect(self.abrir)
        self.cargarBoton.clicked.connect(self.cargar_en_mapa)

    def construir(self):
        principal = QVBoxLayout(self)
        principal.setContentsMargins(0, 0, 0, 0)
        fila = QHBoxLayout()
        fila.addWidget(QLabel("Fichero GML", self))
        self.fichero = QgsFileWidget(self)
        self.fichero.setStorageMode(QgsFileWidget.StorageMode.GetFile)
        self.fichero.setFilter("GML (*.gml *.xml)")
        self.fichero.setDialogTitle("Abrir un GML de parcela o de edificio")
        fila.addWidget(self.fichero, 1)
        principal.addLayout(fila)

        self.resumen = QLabel("<i>Elija o arrastre aquí un GML de parcela catastral (esquema 3.0 o 4.0) o de edificio.</i>",
                              self)
        self.resumen.setWordWrap(True)
        principal.addWidget(self.resumen)

        self.tabla = QTableWidget(0, len(CABECERAS), self)
        self.tabla.setHorizontalHeaderLabels(CABECERAS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        principal.addWidget(self.tabla, 1)

        botones = QHBoxLayout()
        botones.addStretch(1)
        self.cargarBoton = QPushButton(QgsApplication.getThemeIcon('/mActionAddLayer.svg'), "Cargar en el mapa", self)
        self.cargarBoton.setEnabled(False)
        botones.addWidget(self.cargarBoton)
        principal.addLayout(botones)

    # ------------------------------------------------------------------ Arrastrar y soltar

    @staticmethod
    def rutas_gml(mime):
        """Ficheros .gml o .xml locales que vienen en lo arrastrado."""
        if mime is None or not mime.hasUrls():
            return []
        return [u.toLocalFile() for u in mime.urls()
                if u.isLocalFile() and u.toLocalFile().lower().endswith(('.gml', '.xml'))]

    def dragEnterEvent(self, event):  # noqa: N802 (nombre impuesto por Qt)
        if self.rutas_gml(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):  # noqa: N802 (nombre impuesto por Qt)
        self.dragEnterEvent(event)

    def dropEvent(self, event):  # noqa: N802 (nombre impuesto por Qt)
        rutas = self.rutas_gml(event.mimeData())
        if not rutas:
            event.ignore()
            return
        event.acceptProposedAction()
        self.soltar(rutas)

    def soltar(self, rutas):
        """Abre el GML soltado (si se sueltan varios, el primero, y se avisa)."""
        self.fichero.setFilePath(rutas[0])  #Lanza abrir() por la señal fileChanged
        if len(rutas) > 1:
            self.dock.notify(f"Se ha abierto {os.path.basename(rutas[0])}; la pestaña revisa un GML cada vez",
                             Qgis.MessageLevel.Info, 8)

    # ------------------------------------------------------------------ Abrir

    def abrir(self, *args):
        """Lee el GML elegido y rellena la tabla."""
        self.dock.messageBar.clearWidgets()
        ruta = self.fichero.filePath().strip()
        self.tabla.setRowCount(0)
        self.cargarBoton.setEnabled(False)
        self.resultado = None
        if not ruta:
            return None
        if not os.path.isfile(ruta):
            self.dock.warn(f"No existe el fichero: {ruta}")
            return None
        self.ruta = ruta
        self.resultado = gl.leer(ruta)
        r = self.resultado
        self.tabla.setRowCount(len(r.elementos))
        for i, e in enumerate(r.elementos):
            calculada = None if e.geometria.isNull() else geo.redondear_m2(e.geometria.area())
            valores = [e.tipo.capitalize(), e.local_id, e.namespace,
                       '' if e.area_declarada is None else str(e.area_declarada), '' if calculada is None else str(calculada)]
            for col, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                if col >= 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tabla.setItem(i, col, item)
            if e.area_declarada is not None and calculada is not None and e.area_declarada != calculada:
                self.tabla.item(i, 3).setForeground(Qt.GlobalColor.red)
                self.tabla.item(i, 3).setToolTip("La superficie declarada no coincide con la de la geometría")
        self.tabla.resizeColumnToContents(0)
        informativas = [i.mensaje for i in r.incidencias if i.nivel not in (ERROR, AVISO)]
        self.resumen.setText(f"<b>{os.path.basename(ruta)}</b> · " + (informativas[0] if informativas else 'sin elementos'))
        problemas = [str(i) for i in r.incidencias if i.nivel in (ERROR, AVISO)]
        if problemas:
            nivel = Qgis.MessageLevel.Critical if any(i.nivel == ERROR for i in r.incidencias) else Qgis.MessageLevel.Warning
            self.dock.notify(f"{os.path.basename(ruta)}: {len(problemas)} problema{'s' if len(problemas) != 1 else ''}\n\n"
                             + "\n".join(f"- {p}" for p in problemas), nivel, 0)
        self.cargarBoton.setEnabled(bool(r.elementos))
        return r

    def cargar_en_mapa(self, *args):
        """Añade el GML al proyecto como capa de memoria con estilo y acerca el mapa a ella."""
        if not self.resultado or not self.resultado.elementos:
            return None
        return cargar(self.resultado, self.ruta, self.dock.iface)


def cargar(resultado, ruta, iface=None):
    """Capa con estilo a partir de un resultado de lectura, añadida al proyecto (sin crear ficheros .gfs)."""
    capa = estilos.aplicar(gl.capa(resultado, os.path.splitext(os.path.basename(ruta))[0]))
    QgsProject.instance().addMapLayer(capa)
    if iface is not None and hasattr(iface, 'mapCanvas'):
        try:
            lienzo = iface.mapCanvas()
            lienzo.setExtent(lienzo.mapSettings().layerExtentToOutputExtent(capa, capa.extent()).buffered(5))
            lienzo.refresh()
        except (AttributeError, TypeError):
            pass
    return capa
