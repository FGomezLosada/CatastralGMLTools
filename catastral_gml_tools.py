"""
Catastral GML Tools - Clase principal del plugin (menú, barra de herramientas y panel).

copyright : (C) 2026 by Francisco Gómez Losada
email     : pgomezlosada@gmail.com
license   : GNU GPL v2 or later
"""

from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .catastral_gml_tools_dockwidget import CatastralGMLToolsDockWidget
from .core.info import NOMBRE, ruta

MENU_NAME = "&Catastral GML Tools"


class CatastralGMLTools:
    """Implementación del plugin para QGIS."""

    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.toolbar = None
        self.dockwidget = None

    @staticmethod
    def tr(message):
        return QCoreApplication.translate("CatastralGMLTools", message)

    def initGui(self):  # noqa: N802 (nombre impuesto por QGIS)
        """Crea el botón en la barra de herramientas y la entrada en el menú Vectorial."""
        self.toolbar = self.iface.addToolBar(NOMBRE)
        self.toolbar.setObjectName("CatastralGMLTools")

        icon = QIcon(ruta("icon.svg"))  #Vectorial: se ve nítido a cualquier tamaño
        self.action = QAction(icon, self.tr(NOMBRE), self.iface.mainWindow())
        self.action.setObjectName("CatastralGMLToolsAction")
        self.action.setCheckable(True)  #El botón queda pulsado mientras el panel está visible
        self.action.triggered.connect(self.toggle)

        self.toolbar.addAction(self.action)
        self.iface.addPluginToVectorMenu(self.tr(MENU_NAME), self.action)

    def unload(self):
        """Elimina todo lo que el plugin ha añadido a QGIS (necesario para recargarlo)."""
        self.iface.removePluginVectorMenu(self.tr(MENU_NAME), self.action)
        self.iface.removeToolBarIcon(self.action)
        if self.dockwidget is not None:
            self.dockwidget.visibilityChanged.disconnect(self.on_visibility)
            self.dockwidget.cleanup()
            self.iface.removeDockWidget(self.dockwidget)
            self.dockwidget.deleteLater()
            self.dockwidget = None
        if self.toolbar is not None:
            self.toolbar.deleteLater()
            self.toolbar = None
        self.action = None

    def toggle(self, checked):
        """Muestra u oculta el panel desde el botón."""
        if checked:
            self.run()
        elif self.dockwidget is not None:
            self.dockwidget.hide()

    def run(self):
        """Muestra el panel. Se crea una sola vez y se reutiliza."""
        if self.dockwidget is None:
            self.dockwidget = CatastralGMLToolsDockWidget(self.iface)
            self.dockwidget.setWindowIcon(QIcon(ruta("icon.svg")))
            self.dockwidget.visibilityChanged.connect(self.on_visibility)
            self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dockwidget)
        self.dockwidget.show()
        self.dockwidget.raise_()

    def on_visibility(self, visible):
        """El botón de la barra refleja si el panel está a la vista (también al cerrarlo con la ×)."""
        if self.action is not None:
            self.action.setChecked(bool(visible))
