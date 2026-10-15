"""
Pestaña «Utilidades»: «Unir GML» (multiparcela, core/unir.py): varios GML de parcela en uno solo; y «Convertir a 4.0 o
reparar» (core/conversor.py): un GML de parcela del esquema 3.0 al 4.0, o un 4.0 con fallos que se arreglan al
reescribirlo.
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
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QToolBox,
    QVBoxLayout,
    QWidget,
)

from ..core import conversor as cv
from ..core import gml_lector as gl
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
        self.origenConv.fileChanged.connect(self.origen_cambiado)
        self.convertirBoton.clicked.connect(self.convertir)
        self.lista.model().rowsInserted.connect(self.actualizar)
        self.lista.model().rowsRemoved.connect(self.actualizar)
        self.actualizar()

    def construir(self):
        """
        Cada utilidad es un apartado numerado de una lista desplegable (QToolBox): se ve la lista entera y solo se abre
        la que se usa (prueba a mano del 15/10: con todo a la vista y sus textos, la pestaña parecía una página web).
        Lo que explica cada utilidad está en su descripción emergente y en la ayuda.
        """
        principal = QVBoxLayout(self)
        principal.setContentsMargins(0, 0, 0, 0)
        self.utilidades = QToolBox(self)
        for numero, (widget, titulo, icono, ayuda) in enumerate((
                (self.pagina_unir(), "Unir GML (multiparcela)", '/mActionMergeFeatures.svg',
                 "Junta varios GML de parcela en uno solo para presentarlos a la vez en la Sede. Las parcelas repetidas "
                 "se incluyen una vez; si vienen en husos distintos, se pasan al del primer fichero."),
                (self.pagina_convertir(), "Convertir a 4.0 o reparar", '/mActionFileSaveAs.svg',
                 "La Sede solo admite el esquema 4.0. Crea una copia en 4.0 (o reparada, si ya lo era) con la estructura, "
                 "los anillos, los decimales y las superficies como los pide la Sede; el original no se toca. Dice qué ha "
                 "cambiado y qué queda por revisar."),
                (QWidget(self), "Informe de superficies (próximamente)", '/mActionNewReport.svg',
                 "En una próxima versión"),
        ), start=1):
            indice = self.utilidades.addItem(widget, QgsApplication.getThemeIcon(icono), f"{numero}. {titulo}")
            self.utilidades.setItemToolTip(indice, ayuda)
        self.utilidades.setItemEnabled(2, False)
        principal.addWidget(self.utilidades, 1)
        self.setAcceptDrops(True)

    def pagina_unir(self):
        pagina = QWidget(self)
        caja = QVBoxLayout(pagina)
        self.lista = QListWidget(pagina)
        self.lista.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.lista.setToolTip("Ficheros GML que se van a unir (puede arrastrarlos aquí desde el Explorador o el panel de Capas)")
        self.lista.setAcceptDrops(False)
        caja.addWidget(self.lista, 1)
        fila = QHBoxLayout()
        self.anadirBoton = QPushButton(QgsApplication.getThemeIcon('/symbologyAdd.svg'), "Añadir…", pagina)
        self.quitarBoton = QPushButton(QgsApplication.getThemeIcon('/symbologyRemove.svg'), "Quitar", pagina)
        fila.addWidget(self.anadirBoton)
        fila.addWidget(self.quitarBoton)
        fila.addStretch(1)
        caja.addLayout(fila)
        formulario = QFormLayout()
        self.destino = QgsFileWidget(pagina)
        self.destino.setStorageMode(QgsFileWidget.StorageMode.SaveFile)
        self.destino.setFilter("GML (*.gml)")
        self.destino.setDialogTitle("Guardar el GML unido")
        formulario.addRow("Salida", self.destino)
        caja.addLayout(formulario)
        botones = QHBoxLayout()
        botones.addStretch(1)
        self.unirBoton = QPushButton(QgsApplication.getThemeIcon('/mActionMergeFeatures.svg'), "Unir GML", pagina)
        botones.addWidget(self.unirBoton)
        caja.addLayout(botones)
        return pagina

    def pagina_convertir(self):
        pagina = QWidget(self)
        caja = QVBoxLayout(pagina)
        formulario = QFormLayout()
        self.origenConv = QgsFileWidget(pagina)
        self.origenConv.setStorageMode(QgsFileWidget.StorageMode.GetFile)
        self.origenConv.setFilter("GML (*.gml *.xml)")
        self.origenConv.setDialogTitle("Elegir el GML de parcela que se va a convertir")
        formulario.addRow("GML", self.origenConv)
        self.destinoConv = QgsFileWidget(pagina)
        self.destinoConv.setStorageMode(QgsFileWidget.StorageMode.SaveFile)
        self.destinoConv.setFilter("GML (*.gml)")
        self.destinoConv.setDialogTitle("Guardar el GML convertido")
        formulario.addRow("Salida", self.destinoConv)
        caja.addLayout(formulario)
        self.estadoConv = QLabel(pagina)
        self.estadoConv.setWordWrap(True)
        caja.addWidget(self.estadoConv)
        botones = QHBoxLayout()
        botones.addStretch(1)
        self.convertirBoton = QPushButton(QgsApplication.getThemeIcon('/mActionFileSaveAs.svg'), "Convertir", pagina)
        self.convertirBoton.setEnabled(False)
        botones.addWidget(self.convertirBoton)
        caja.addLayout(botones)
        caja.addStretch(1)
        self.destino_conv_auto = ''
        return pagina

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
        if self.utilidades.currentIndex() == 1:  #«Convertir a 4.0 o reparar» abierta: el fichero que se suelta es el GML
            self.origenConv.setFilePath(rutas[0])
        else:
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

    # ------------------------------------------------------------------ Convertir a 4.0 o reparar

    def origen_cambiado(self, *args):
        """Dice qué se hará con el fichero elegido y propone la salida junto a él (sin pisar nada)."""
        ruta = self.origenConv.filePath().strip()
        version = gl.leer(ruta).version if ruta and os.path.isfile(ruta) else ''
        if version == 'CP 3.0':
            texto, boton = "Esquema 3.0 (obsoleto): se convertirá al 4.0.", "Convertir a 4.0"
        elif version == 'CP 4.0':
            texto, boton = "Ya es 4.0: se reescribirá corrigiendo lo que se pueda (estructura, anillos, superficies…).", "Reparar"
        elif ruta:
            texto, boton = ("<span style='color:#c92a2a'>No es un GML de parcela catastral que se pueda leer"
                            + (f" ({version})" if version else '') + ".</span>"), "Convertir"
        else:
            texto, boton = '', "Convertir"
        self.estadoConv.setText(f"<small>{texto}</small>" if texto else '')
        self.convertirBoton.setText(boton)
        self.convertirBoton.setEnabled(version in ('CP 3.0', 'CP 4.0'))
        actual = self.destinoConv.filePath().strip()
        if version in ('CP 3.0', 'CP 4.0') and (not actual or actual == self.destino_conv_auto):
            self.destino_conv_auto = cv.destino_propuesto(ruta, version)
            self.destinoConv.setFilePath(self.destino_conv_auto)

    def convertir(self, *args):
        self.dock.messageBar.clearWidgets()
        ruta = self.origenConv.filePath().strip()
        destino = self.destinoConv.filePath().strip()
        if not destino:
            self.dock.warn("Indique el fichero de salida")
            return None
        if not destino.lower().endswith('.gml'):
            destino += '.gml'
        ok, version, cambios, incidencias = cv.convertir(ruta, destino)
        if not ok:
            self.dock.notify("No se ha podido convertir:\n\n" + "\n".join(f"- {i}" for i in incidencias),
                             Qgis.MessageLevel.Critical, 0)
            return None
        self.ultimo = destino
        self.dock.gml_creado(destino)
        accion = "Convertido a 4.0" if version == 'CP 3.0' else "Reparado"  #Corto: el mensaje no se come el panel
        self.dock.success(f"{accion}: {os.path.basename(destino)}",
                          [("Validar", self.validar), ("Abrir carpeta", self.abrir_carpeta)],
                          detalles=[str(i) for i in incidencias if i.nivel in (ERROR, AVISO)], notas=cambios + ["El original no se ha tocado"])
        self.destino_conv_auto = destino  #Se propone otro nombre libre: un segundo clic no pisa el que se acaba de crear
        self.origen_cambiado()
        return destino

    def validar(self, *args):
        """Abre el GML unido en la pestaña Validar (solapes, huecos y comparación con el Catastro)."""
        if self.ultimo:
            self.dock.abrir_en_validar(self.ultimo)

    def abrir_carpeta(self, *args):
        if self.ultimo:
            self.dock.open_path(os.path.dirname(self.ultimo))
