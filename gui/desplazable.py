"""
El panel en pantallas pequeñas (prueba a mano del 14/10/2026, segundo monitor): el contenido de cada pestaña va dentro de
una zona con barra de desplazamiento, para que nada quede cortado ni aplastado (la tabla de parcelas tenía una sola fila
a la vista y el bloque de división no se veía entero).

Y la rueda del ratón: al desplazar el panel con la rueda, si el puntero pasaba por una lista desplegable, la rueda le
cambiaba el valor sin que el usuario se diera cuenta (así acabó el identificador en el campo «pos» y la tabla mostraba
coordenadas en lugar de la referencia catastral). Ahora una lista o un campo numérico solo responde a la rueda si tiene
el foco (después de hacer clic en él); si no, la rueda desplaza el panel o la tabla.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt
from qgis.PyQt.QtWidgets import (
    QAbstractButton,
    QAbstractScrollArea,
    QAbstractSpinBox,
    QBoxLayout,
    QHBoxLayout,
    QLayout,
    QSizePolicy,
    QWidget,
    QApplication,
    QComboBox,
    QFormLayout,
    QFrame,
    QLineEdit,
    QScrollArea,
    QTableWidget,
)

ALTO_MINIMO_TABLA = 72  #px: la cabecera y dos filas a la vista; con más sitio, la tabla crece


class TablaFlexible(QTableWidget):
    """
    Tabla que pide poco alto (el mínimo) y crece con el sitio que haya. Una QTableWidget pide unos 190 px, y la zona
    desplazable de Parcela calcula su alto con lo que piden los elementos (no con su mínimo): aunque todo cabía, salía la
    barra de desplazamiento y la pestaña parecía una ventana dentro de otra (prueba a mano del 27/10/2026).
    """

    def sizeHint(self):  # noqa: N802 (nombre impuesto por Qt)
        hint = super().sizeHint()
        return QSize(hint.width(), max(self.minimumHeight(), ALTO_MINIMO_TABLA))


class FiltroRueda(QObject):
    """Sin foco, la rueda no cambia la lista o el número: se pasa a la zona desplazable que la contiene."""

    def eventFilter(self, objeto, evento):
        if evento.type() != QEvent.Type.Wheel or sip.isdeleted(objeto) or objeto.hasFocus():
            return False
        padre = objeto.parentWidget()
        while padre is not None and not isinstance(padre, QAbstractScrollArea):
            padre = padre.parentWidget()
        if padre is not None:
            QApplication.sendEvent(padre.viewport(), evento)
        return True  #La lista no cambia de valor


_FILTRO = None


def proteger(raiz):
    """Instala el filtro de la rueda en las listas desplegables y campos numéricos de raiz (y en raiz si lo es)."""
    global _FILTRO
    if _FILTRO is None:
        _FILTRO = FiltroRueda()
    widgets = [raiz] if isinstance(raiz, (QComboBox, QAbstractSpinBox)) else []
    widgets += raiz.findChildren(QComboBox) + raiz.findChildren(QAbstractSpinBox)
    for widget in widgets:
        if not widget.property('cgt_rueda'):
            widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  #Clic o tabulador para darle el foco; la rueda sola, no
            widget.installEventFilter(_FILTRO)
            widget.setProperty('cgt_rueda', True)
    return raiz


class FilaFlexible(QLayout):
    """
    Fila de botones o casillas que pasa a la línea siguiente cuando no cabe (como el texto), en lugar de obligar al panel
    a ser ancho (prueba a mano del 20/10/2026: con el panel estrecho salía una barra horizontal que tapaba el resumen).
    derecha: las líneas se alinean a la derecha (la fila original empezaba con un espacio elástico).
    """

    def __init__(self, padre=None, derecha=False, separacion=6):
        super().__init__(padre)
        self.elementos = []
        self.derecha = derecha
        self.separacion = separacion
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):  # noqa: N802 (nombre impuesto por Qt)
        self.elementos.append(item)

    def count(self):
        return len(self.elementos)

    def itemAt(self, indice):  # noqa: N802 (nombre impuesto por Qt)
        return self.elementos[indice] if 0 <= indice < len(self.elementos) else None

    def takeAt(self, indice):  # noqa: N802 (nombre impuesto por Qt)
        return self.elementos.pop(indice) if 0 <= indice < len(self.elementos) else None

    def expandingDirections(self):  # noqa: N802 (nombre impuesto por Qt)
        return Qt.Orientation(0)

    def hasHeightForWidth(self):  # noqa: N802 (nombre impuesto por Qt)
        return True

    def heightForWidth(self, ancho):  # noqa: N802 (nombre impuesto por Qt)
        return self._colocar(QRect(0, 0, ancho, 0), mover=False)

    def setGeometry(self, rect):  # noqa: N802 (nombre impuesto por Qt)
        super().setGeometry(rect)
        self._colocar(rect, mover=True)

    def sizeHint(self):  # noqa: N802 (nombre impuesto por Qt)
        visibles = [i for i in self.elementos if not i.isEmpty()]
        ancho = sum(i.sizeHint().width() for i in visibles) + self.separacion * max(len(visibles) - 1, 0)
        alto = max((i.sizeHint().height() for i in visibles), default=0)
        return QSize(ancho, alto)

    def minimumSize(self):  # noqa: N802 (nombre impuesto por Qt)
        #Lo justo para el elemento más ancho: el resto baja de línea
        visibles = [i for i in self.elementos if not i.isEmpty()]
        return QSize(max((i.minimumSize().width() for i in visibles), default=0),
                     max((i.minimumSize().height() for i in visibles), default=0))

    def _colocar(self, rect, mover):
        lineas, linea, ancho_linea = [], [], 0
        for item in (i for i in self.elementos if not i.isEmpty()):
            w = item.sizeHint().width()
            if linea and ancho_linea + self.separacion + w > rect.width():
                lineas.append((linea, ancho_linea))
                linea, ancho_linea = [], 0
            ancho_linea += (self.separacion if linea else 0) + w
            linea.append(item)
        if linea:
            lineas.append((linea, ancho_linea))
        y = rect.y()
        for elementos, ancho in lineas:
            alto = max(i.sizeHint().height() for i in elementos)
            x = rect.x() + (max(rect.width() - ancho, 0) if self.derecha else 0)
            for item in elementos:
                if mover:
                    item.setGeometry(QRect(QPoint(x, y), QSize(min(item.sizeHint().width(), rect.width()), alto)))
                x += item.sizeHint().width() + self.separacion
            y += alto + self.separacion
        return max(y - rect.y() - self.separacion, 0)


def _fila_de_botones(fila):
    """¿Es una fila (QHBoxLayout) solo de botones o casillas (y espacios), con al menos dos?"""
    if not isinstance(fila, QHBoxLayout) or isinstance(fila, FilaFlexible):
        return False
    widgets = [fila.itemAt(i).widget() for i in range(fila.count()) if fila.itemAt(i).widget() is not None]
    otros = [i for i in range(fila.count()) if fila.itemAt(i).widget() is None and fila.itemAt(i).spacerItem() is None]
    return len(widgets) >= 2 and not otros and all(isinstance(w, QAbstractButton) for w in widgets)


def flexibilizar(raiz):
    """Cambia las filas de solo botones o casillas por FilaFlexible (que baja de línea si no caben)."""
    for padre in raiz.findChildren(QBoxLayout):
        for indice in range(padre.count()):
            fila = padre.itemAt(indice).layout() if padre.itemAt(indice) is not None else None
            if fila is None or not _fila_de_botones(fila):
                continue
            primero = fila.itemAt(0)
            derecha = primero is not None and primero.spacerItem() is not None
            widgets = [fila.itemAt(i).widget() for i in range(fila.count()) if fila.itemAt(i).widget() is not None]
            dueno = padre.parentWidget() or raiz
            contenedor = QWidget(dueno)
            flexible = FilaFlexible(contenedor, derecha=derecha)
            for w in widgets:
                fila.removeWidget(w)
                flexible.addWidget(w)
            politica = contenedor.sizePolicy()
            politica.setHeightForWidth(True)
            politica.setVerticalPolicy(QSizePolicy.Policy.Minimum)
            contenedor.setSizePolicy(politica)
            padre.takeAt(indice)
            padre.insertWidget(indice, contenedor)
            fila.deleteLater()
    return raiz


def estrechar(raiz):
    """
    Que el panel quepa estrecho (batería del panel): las listas desplegables no fijan su ancho con la opción más larga (un
    nombre de capa o de campo largo lo ensanchaba); se muestran recortadas y al abrirlas la lista sale con su ancho. Y en
    los formularios, la etiqueta pasa encima del campo cuando no cabe al lado.
    """
    for combo in raiz.findChildren(QComboBox):
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(8)
        #QComboBox guarda el ancho mínimo ya calculado y no lo rehace al cambiar la política: un StyleChange lo borra
        QApplication.sendEvent(combo, QEvent(QEvent.Type.StyleChange))
        combo.updateGeometry()
    #En un panel estrecho, la etiqueta de cada campo pasa encima de él en lugar de empujar el ancho
    for formulario in raiz.findChildren(QFormLayout):
        formulario.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    #Y las filas de botones o casillas bajan de línea cuando no caben
    flexibilizar(raiz)
    for disposicion in raiz.findChildren(QLayout):  #Que no se quede el ancho mínimo calculado con lo de antes
        disposicion.invalidate()
    return raiz


def envolver(widget, padre):
    """Zona desplazable (sin marco; las barras solo salen si el panel es más pequeño que su contenido)."""
    zona = QScrollArea(padre)
    zona.setWidgetResizable(True)
    zona.setFrameShape(QFrame.Shape.NoFrame)
    zona.setWidget(widget)
    #Sin fondo propio: la zona pintaba el gris de la ventana sobre el blanco de la pestaña (en Windows) y Parcela se veía
    #como una caja gris dentro de la pestaña (prueba a mano del 27/10/2026)
    zona.viewport().setAutoFillBackground(False)
    widget.setAutoFillBackground(False)
    return zona


def soltar_en(pestana):
    """
    Que un GML arrastrado (desde el Explorador o desde el panel de Capas) lo recoja la pestaña aunque se suelte encima de
    una casilla: las casillas de texto y de fichero aceptan por su cuenta lo que se les suelta, se quedaban el fichero
    (solo su texto) o rechazaban la capa, y la pestaña no se enteraba (prueba a mano del 16/10/2026 en el informe de
    superficies; ya había pasado en Validar). Se llama al final de construir la pestaña, con todas sus casillas creadas.
    """
    pestana.setAcceptDrops(True)
    for casilla in pestana.findChildren(QLineEdit):
        casilla.setAcceptDrops(False)
    return pestana
