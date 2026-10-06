"""
Catastral GML Tools - Panel (dock) con la interfaz del plugin.

Aquí solo está la parte visual (pestañas, botones, avisos). La lógica de crear, leer y comprobar
ficheros GML está en la carpeta core/.

copyright : (C) 2026 by Francisco Gómez Losada
email     : pgomezlosada@gmail.com
license   : GNU GPL v2 or later
"""

import os

from qgis.core import Qgis, QgsApplication
from qgis.gui import QgsMessageBar
from qgis.PyQt import QtWidgets, sip, uic
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QPushButton, QToolButton, QWidget

from .core.info import AVISO_LEGAL, FUENTE_DGC, NOMBRE, ruta, version
from .gui.pestana_parcela import PestanaParcela

FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'catastral_gml_tools_dockwidget_base.ui'))

#Icono nativo de QGIS para cada pestaña (nombre del objeto en el .ui → icono del tema)
ICONOS_PESTANAS = {
    'tabParcela': '/mActionAddPolygon.svg',
    'tabEdificio': '/mIconPolygonLayer.svg',
    'tabValidar': '/algorithms/mAlgorithmCheckGeometry.svg',
    'tabDescargar': '/mActionAddWfsLayer.svg',
    'tabDividir': '/mActionSplitFeatures.svg',
    'tabUtilidades': '/mActionOptions.svg',
}
AYUDA = ruta('help', 'index.html')


class CatastralGMLToolsDockWidget(QtWidgets.QDockWidget, FORM_CLASS):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setupUi(self)
        self.setWindowTitle(f"{NOMBRE} {version()}")
        self.setup_header()
        self.setup_tabs()
        self.setup_messages()
        self.setup_parcela()

    # ------------------------------------------------------------------ Cabecera: aviso legal y ayuda

    def setup_header(self):
        """Aviso de herramienta no oficial (siempre visible), botón de ayuda y cita de la fuente de los datos."""
        self.legalLabel.setText(f"<small>⚠ {AVISO_LEGAL}</small>")
        self.legalLabel.setToolTip(AVISO_LEGAL)
        self.helpButton = QToolButton(self.dockWidgetContents)  #Con padre: Python no lo borra
        self.helpButton.setObjectName('helpButton')
        self.helpButton.setIcon(QgsApplication.getThemeIcon('/mActionHelpContents.svg'))
        self.helpButton.setToolTip("Ayuda: abre la guía de uso de Catastral GML Tools")
        self.helpButton.setAutoRaise(True)
        self.helpButton.clicked.connect(self.open_help)
        self.headerLayout.addWidget(self.helpButton)
        self.sourceLabel.setText(f"<small>Datos catastrales descargados: © {FUENTE_DGC}</small>")

    def help_url(self):
        """Dirección de la ayuda local (funciona sin conexión)."""
        return QUrl.fromLocalFile(AYUDA)

    def open_help(self, *args):
        QDesktopServices.openUrl(self.help_url())

    # ------------------------------------------------------------------ Pestañas

    def setup_tabs(self):
        """Pone a cada pestaña su icono nativo de QGIS."""
        for i in range(self.tabWidget.count()):
            icono = ICONOS_PESTANAS.get(self.tabWidget.widget(i).objectName())
            if icono:
                self.tabWidget.setTabIcon(i, QgsApplication.getThemeIcon(icono))

    def setup_parcela(self):
        """Pestaña Parcela: sustituye el texto «Disponible en próximas versiones» por la herramienta."""
        self.tabParcelaPendiente.hide()
        self.pestanaParcela = PestanaParcela(self, self.tabParcela)
        #Justo debajo del texto de la pestaña y con «stretch»: ocupa todo el alto (el espaciador del .ui se queda sin sitio)
        self.tabParcelaLayout.insertWidget(1, self.pestanaParcela, 1)

    # ------------------------------------------------------------------ Avisos dentro del panel

    def setup_messages(self):
        """Barra de avisos del propio panel, debajo de las pestañas (siempre a la vista)."""
        self.messageBar = QgsMessageBar(self.dockWidgetContents)
        self.messageBar.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        self.mainLayout.insertWidget(self.mainLayout.indexOf(self.sourceLabel), self.messageBar)

    def notify(self, message, level=Qgis.MessageLevel.Info, duration=8):
        """
        Muestra un aviso en la barra del panel, sin ventanas que interrumpan. Si el texto tiene varias líneas, se ve la
        primera y el resto con el botón «Más». duration en segundos (0: se queda hasta cerrarlo con la ×).
        """
        if sip.isdeleted(self) or not hasattr(self, 'messageBar'):
            return
        primera, _, resto = message.strip().partition('\n')
        if resto.strip():
            self.messageBar.pushMessage('', primera, resto.strip(), level, duration)
        else:
            self.messageBar.pushMessage('', primera, level, duration)

    def warn(self, message):
        """Aviso al usuario en la barra del panel. Los avisos largos (con detalles) se quedan hasta cerrarlos."""
        self.notify(message, Qgis.MessageLevel.Warning, 0 if '\n' in message.strip() else 15)

    def success(self, message, buttons=(), detalles=()):
        """
        Resultado final en la barra del panel, con botones (texto, método) para abrir lo creado. Se queda hasta cerrarlo.
        Si hay avisos (detalles), el mensaje sale en naranja y los avisos se ven al pasar el ratón.
        """
        if sip.isdeleted(self):
            return None
        contenido = QWidget(self.messageBar)  #Con padre: si no, Python lo borraría al salir de aquí
        fila = QHBoxLayout(contenido)
        fila.setContentsMargins(0, 0, 0, 0)
        etiqueta = QLabel(message, contenido)
        etiqueta.setWordWrap(True)
        if detalles:
            etiqueta.setText(f"{message} · {len(detalles)} aviso{'s' if len(detalles) != 1 else ''}")
            etiqueta.setToolTip("\n".join(detalles))
        fila.addWidget(etiqueta, 1)
        for texto, metodo in buttons:
            boton = QPushButton(texto, contenido)
            boton.clicked.connect(metodo)
            fila.addWidget(boton)
        mensaje = self.messageBar.createMessage(contenido)
        nivel = Qgis.MessageLevel.Warning if detalles else Qgis.MessageLevel.Success
        self.messageBar.pushWidget(mensaje, nivel, 0)
        return mensaje

    def open_path(self, path):
        """Abre una carpeta o fichero con la aplicación del sistema."""
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
