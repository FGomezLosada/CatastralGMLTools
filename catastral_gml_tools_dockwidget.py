"""
Catastral GML Tools - Panel (dock) con la interfaz del plugin.

Aquí solo está la parte visual (pestañas, botones, avisos). La lógica de crear, leer y comprobar
ficheros GML está en la carpeta core/.

copyright : (C) 2026 by Francisco Gómez Losada
email     : pgomezlosada@gmail.com
license   : GNU GPL v2 or later
"""

import html
import os

from qgis.core import Qgis, QgsApplication
from qgis.gui import QgsMessageBar
from qgis.PyQt import QtWidgets, sip, uic
from qgis.PyQt.QtCore import QEvent, QObject, Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextBrowser, QToolButton, QVBoxLayout, QWidget

from .core.ficheros import misma_ruta
from .core.info import AVISO_LEGAL, FUENTE_DGC, NOMBRE, ruta, version
from .gui import desplazable
from .gui.pestana_descargar import PestanaDescargar
from .gui.pestana_edificio import PestanaEdificio
from .gui.pestana_parcela import PestanaParcela
from .gui.pestana_utilidades import PestanaUtilidades
from .gui.pestana_validar import PestanaValidar

FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'catastral_gml_tools_dockwidget_base.ui'))

#Icono nativo de QGIS para cada pestaña (nombre del objeto en el .ui → icono del tema)
ICONOS_PESTANAS = {
    'tabParcela': '/mActionAddPolygon.svg',
    'tabEdificio': '/mIconPolygonLayer.svg',
    'tabValidar': '/algorithms/mAlgorithmCheckGeometry.svg',
    'tabDescargar': '/mActionAddWfsLayer.svg',
    'tabUtilidades': '/mActionOptions.svg',
}
AYUDA = ruta('help', 'index.html')


MAX_AVISOS_MENSAJE = 3  #Avisos que se leen en el mensaje de resultado; el resto, al pasar el ratón
MAX_NOTAS_MENSAJE = 2   #Notas (p. ej. cambios del conversor): un mensaje alto se comía el panel (prueba del 15/10)
ALTO_MAXIMO_AVISO = 240  #px: un aviso de una línea larga crece hasta aquí (después, con su barra de desplazamiento)


class AjusteAltura(QObject):
    """
    El texto de un aviso simple de QgsMessageBar va en un cuadro de 45 px fijos: en un panel estrecho, un aviso largo
    quedaba cortado, con una barra de desplazamiento diminuta (prueba a mano del 26/10/2026, «La capa es de Gipuzkoa…»).
    Ajusta la altura al texto cada vez que cambia el ancho.
    """

    def eventFilter(self, objeto, evento):
        if evento.type() == QEvent.Type.Resize and isinstance(objeto, QTextBrowser):
            ajustar_altura(objeto)
        elif evento.type() == QEvent.Type.Resize and isinstance(objeto, QWidget) and objeto.layout() is not None:
            #La barra no tiene en cuenta que el texto y los botones se parten en varias líneas: «… la Sede propondrá:
            #subsanación de» se quedaba sin la última palabra (prueba a mano del 27/10/2026)
            alto = objeto.layout().totalHeightForWidth(objeto.width())
            if alto > 0 and objeto.minimumHeight() != alto:
                objeto.setMinimumHeight(alto)
        return False


def ajustar_altura(caja):
    documento = caja.document()
    documento.setTextWidth(max(caja.viewport().width(), 50))
    alto = int(documento.size().height()) + 2 * caja.frameWidth() + 4
    caja.setFixedHeight(max(min(alto, ALTO_MAXIMO_AVISO), 24))



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
        self.setup_edificio()
        self.setup_validar()
        self.setup_descargar()
        self.setup_utilidades()
        self.quitar_espaciadores()
        desplazable.proteger(self.dockWidgetContents)  #La rueda desplaza el panel; no cambia listas sin foco
        desplazable.estrechar(self.dockWidgetContents)  #Un nombre largo en una lista no ensancha el panel
        self.visibilityChanged.connect(self.visibilidad_cambiada)
        self.gml_pendiente = ''
        self.tabWidget.currentChanged.connect(self.pestana_cambiada)

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

    def quitar_espaciadores(self):
        """
        Fuera los espaciadores del diseño (.ui): con el contenido de cada pestaña estirado, se repartían el alto con él y
        Parcela quedaba en una caja con un hueco vacío debajo, «una ventana dentro de otra» (prueba a mano del
        27/10/2026). Cada pestaña lleva su propio espacio elástico donde hace falta.
        """
        for layout in (self.tabDescargarLayout, self.tabParcelaLayout, self.tabEdificioLayout, self.tabValidarLayout,
                       self.tabUtilidadesLayout):
            for i in reversed(range(layout.count())):
                if layout.itemAt(i).spacerItem() is not None:
                    layout.takeAt(i)

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
        self.tabParcelaLayout.insertWidget(1, desplazable.envolver(self.pestanaParcela, self.tabParcela), 1)

    def setup_edificio(self):
        """Pestaña Edificio: GML de edificios y piscinas (ICUC) a partir de una capa con sus huellas."""
        self.tabEdificioPendiente.hide()
        self.pestanaEdificio = PestanaEdificio(self, self.tabEdificio)
        self.tabEdificioLayout.insertWidget(1, self.pestanaEdificio, 1)

    def setup_validar(self):
        """Pestaña Validar: abrir un GML, ver su contenido y cargarlo en el mapa."""
        self.tabValidarPendiente.hide()
        self.pestanaValidar = PestanaValidar(self, self.tabValidar)
        self.tabValidarLayout.insertWidget(1, self.pestanaValidar, 1)

    def gml_creado(self, ruta):
        """Un GML recién creado (Parcela, Edificio o Unir) es el que se abrirá al pasar a la pestaña Validar."""
        self.gml_pendiente = ruta
        if hasattr(self, 'pestanaUtilidades'):
            self.pestanaUtilidades.proponer_gml(ruta)  #Para el informe de superficies, si no hay otro elegido

    def abrir_en_validar(self, ruta):
        """Pasa a la pestaña Validar con ese GML abierto (si ya lo estaba, se vuelve a comprobar)."""
        if not hasattr(self, 'pestanaValidar'):
            return
        self.gml_pendiente = ''
        self.tabWidget.setCurrentWidget(self.tabValidar)
        if misma_ruta(self.pestanaValidar.fichero.filePath(), ruta):
            self.pestanaValidar.abrir()
        else:
            self.pestanaValidar.fichero.setFilePath(ruta)

    def pestana_cambiada(self, indice):
        """Al pasar a Validar con un GML recién creado, se abre ese y no queda a la vista el anterior."""
        if self.tabWidget.widget(indice) is getattr(self, 'tabValidar', None) and getattr(self, 'gml_pendiente', ''):
            self.abrir_en_validar(self.gml_pendiente)
        if hasattr(self, 'pestanaParcela'):
            if self.tabWidget.widget(indice) is getattr(self, 'tabParcela', None):
                self.pestanaParcela.activar_capa()  #Seleccionar en el mapa y Ctrl+Z, sobre la capa de trabajo
            self.pestanaParcela.division.marcar_lado()  #La marca del lado solo con la pestaña Parcela a la vista
        if hasattr(self, 'pestanaUtilidades'):
            self.pestanaUtilidades.ajuste.mostrar_en_mapa()  #Los pares de puntos, solo con el ajuste a la vista

    def setup_descargar(self):
        """Pestaña Descargar: una parcela por referencia catastral o con un clic en el mapa."""
        self.tabDescargarPendiente.hide()
        self.pestanaDescargar = PestanaDescargar(self, self.tabDescargar)
        self.tabDescargarLayout.insertWidget(1, self.pestanaDescargar, 1)

    def setup_utilidades(self):
        """Pestaña Utilidades: lista numerada (unir GML, convertir a 4.0…); se abre la que se usa."""
        self.tabUtilidadesPendiente.hide()
        self.pestanaUtilidades = PestanaUtilidades(self, self.tabUtilidades)
        self.tabUtilidadesInfo.hide()  #La lista numerada de utilidades ya dice lo que hay
        self.tabUtilidadesLayout.insertWidget(1, self.pestanaUtilidades, 1)

    def parcela_descargada(self, capa):
        """Tras descargar una parcela, la pestaña Parcela pasa a trabajar con ella."""
        if hasattr(self, 'pestanaParcela'):
            self.pestanaParcela.usar_capa(capa)

    def construcciones_descargadas(self, rc, capa=None):
        """Tras descargar una parcela, la pestaña Edificio toma su referencia y, si las hay, sus construcciones."""
        if hasattr(self, 'pestanaEdificio'):
            self.pestanaEdificio.descarga_hecha(rc, capa)

    def cleanup(self):
        """
        Al descargar el plugin: devuelve al mapa la herramienta que había antes de la nuestra y cancela las tareas en
        curso (si no, seguirían vivas con el código antiguo al recargarlo; AU-38).
        """
        if sip.isdeleted(self):
            return
        if hasattr(self, 'pestanaDescargar'):
            self.pestanaDescargar.soltar_herramienta()
        if hasattr(self, 'pestanaParcela'):
            self.pestanaParcela.division.soltar()  #La marca del lado en el mapa
        for nombre in ('pestanaDescargar', 'pestanaValidar', 'pestanaUtilidades'):
            pestana = getattr(self, nombre, None)
            if pestana is not None and hasattr(pestana, 'cancelar_tareas'):
                pestana.cancelar_tareas()

    def visibilidad_cambiada(self, visible):
        """Al cerrar el panel (también con la ×), «Elegir en el mapa» deja de estar activa (B6)."""
        if sip.isdeleted(self):
            return
        self.cerrado = not visible
        if not visible and hasattr(self, 'pestanaDescargar') and not sip.isdeleted(self.pestanaDescargar):
            self.pestanaDescargar.soltar_herramienta()
        if hasattr(self, 'pestanaParcela') and not sip.isdeleted(self.pestanaParcela):
            self.pestanaParcela.division.marcar_lado()  #Sin panel no queda la marca roja en el mapa
        if hasattr(self, 'pestanaUtilidades') and not sip.isdeleted(self.pestanaUtilidades):
            if not visible:
                self.pestanaUtilidades.ajuste.soltar_herramienta()
            self.pestanaUtilidades.ajuste.mostrar_en_mapa()

    # ------------------------------------------------------------------ Avisos dentro del panel

    def setup_messages(self):
        """
        Barra de avisos del propio panel, encima de las pestañas, como la de QGIS sobre el mapa. Antes iba debajo y, con
        el panel más alto que la pantalla (la barra de tareas de Windows encima), el «GML creado» no se veía (prueba a
        mano del 21/10/2026).
        """
        self.messageBar = QgsMessageBar(self.dockWidgetContents)
        self.messageBar.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        self.mainLayout.insertWidget(self.mainLayout.indexOf(self.tabWidget), self.messageBar)

    def notify(self, message, level=Qgis.MessageLevel.Info, duration=8):
        """
        Muestra un aviso en la barra del panel, sin ventanas que interrumpan. Si el texto tiene varias líneas, la primera
        es el título y las siguientes se leen debajo (como mucho MAX_AVISOS_MENSAJE; el resto, al pasar el ratón). Antes
        iban tras «Mostrar más», que abre una ventana de QGIS (prueba a mano del 15/10). duration en segundos (0: se queda
        hasta cerrarlo con la ×).
        """
        if sip.isdeleted(self) or not hasattr(self, 'messageBar'):
            return
        primera, _, resto = message.strip().partition('\n')
        lineas = [linea.strip().removeprefix('- ').strip() for linea in resto.splitlines() if linea.strip()]
        if not lineas:
            #La barra lo pinta como HTML: sin escapar, «(<ogr:2082108VF2628S…>)» salía «()» (batería del panel)
            self.messageBar.pushMessage('', html.escape(primera, quote=False), level, duration)
            item = self.messageBar.currentItem()
            if item is not None:
                filtro = AjusteAltura(item)  #Con padre: vive lo que el aviso
                for caja in item.findChildren(QTextBrowser):
                    caja.installEventFilter(filtro)
                    ajustar_altura(caja)
            return
        contenido = QWidget(self.messageBar)  #Con padre: si no, Python lo borraría al salir de aquí
        fila = QHBoxLayout(contenido)
        fila.setContentsMargins(0, 0, 0, 0)
        visibles = [html.escape(linea) for linea in lineas[:MAX_AVISOS_MENSAJE]]
        if len(lineas) > MAX_AVISOS_MENSAJE:
            visibles.append(f"… y {len(lineas) - MAX_AVISOS_MENSAJE} más (pase el ratón por el mensaje)")
        etiqueta = QLabel(contenido)
        etiqueta.setWordWrap(True)
        etiqueta.setTextFormat(Qt.TextFormat.RichText)
        etiqueta.setText(f"{html.escape(primera)}<br><small>" + "<br>".join(f"· {v}" for v in visibles) + "</small>")
        etiqueta.setToolTip(message.strip())
        contenido.installEventFilter(AjusteAltura(contenido))
        fila.addWidget(etiqueta, 1)
        self.messageBar.pushWidget(self.messageBar.createMessage(contenido), level, duration)

    def warn(self, message):
        """Aviso al usuario en la barra del panel. Los avisos largos (con detalles) se quedan hasta cerrarlos."""
        self.notify(message, Qgis.MessageLevel.Warning, 0 if '\n' in message.strip() else 15)

    def success(self, message, buttons=(), detalles=(), notas=()):
        """
        Resultado final en la barra del panel, con botones (texto, método) para abrir lo creado. Se queda hasta cerrarlo.
        Si hay avisos (detalles), el mensaje sale en naranja y los avisos se leen en él. notas: lo que se ha hecho
        (p. ej. los cambios del conversor), en gris bajo el mensaje; no cambian su color.
        """
        if sip.isdeleted(self):
            return None
        contenido = QWidget(self.messageBar)  #Con padre: si no, Python lo borraría al salir de aquí
        #El texto a todo lo ancho y los botones debajo: al lado, en un panel estrecho, el texto quedaba en una columna de
        #cinco líneas (prueba a mano del 27/10/2026)
        columna = QVBoxLayout(contenido)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(4)
        etiqueta = QLabel(message, contenido)
        etiqueta.setTextFormat(Qt.TextFormat.PlainText)  #Lo que venga en el mensaje (nombres, «<1 m²»…) se lee tal cual
        etiqueta.setWordWrap(True)
        if detalles or notas:  #Los avisos se leen en el propio mensaje (antes solo al pasar el ratón: no se encontraban)
            lineas = [f"⚠ {html.escape(d)}" for d in detalles[:MAX_AVISOS_MENSAJE]]
            if len(detalles) > MAX_AVISOS_MENSAJE:
                lineas.append(f"⚠ … y {len(detalles) - MAX_AVISOS_MENSAJE} más (pase el ratón por el mensaje)")
            lineas += [f"<span style='color:#495057'>· {html.escape(n)}</span>" for n in notas[:MAX_NOTAS_MENSAJE]]
            if len(notas) > MAX_NOTAS_MENSAJE:
                lineas.append(f"<span style='color:#495057'>· … y {len(notas) - MAX_NOTAS_MENSAJE} más (pase el ratón por "
                              "el mensaje)</span>")
            etiqueta.setTextFormat(Qt.TextFormat.RichText)
            etiqueta.setText(f"{html.escape(message)}<br><small>" + "<br>".join(lineas) + "</small>")
            etiqueta.setToolTip("\n".join(list(detalles) + list(notas)))
        contenido.installEventFilter(AjusteAltura(contenido))
        columna.addWidget(etiqueta)
        if buttons:
            fila = desplazable.FilaFlexible()  #Los botones pasan a otra línea si no caben
            for texto, metodo in buttons:
                boton = QPushButton(texto, contenido)
                boton.clicked.connect(metodo)
                fila.addWidget(boton)
            columna.addLayout(fila)
        mensaje = self.messageBar.createMessage(contenido)
        nivel = Qgis.MessageLevel.Warning if detalles else Qgis.MessageLevel.Success
        self.messageBar.pushWidget(mensaje, nivel, 0)
        return mensaje

    def abrir_web(self, url):
        """Abre una página en el navegador del sistema (p. ej. la Sede Electrónica del Catastro)."""
        QDesktopServices.openUrl(QUrl(url))

    def open_path(self, path):
        """Abre una carpeta o fichero con la aplicación del sistema."""
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
