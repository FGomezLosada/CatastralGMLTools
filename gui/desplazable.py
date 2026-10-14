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
from qgis.PyQt.QtCore import QEvent, QObject, Qt
from qgis.PyQt.QtWidgets import QAbstractScrollArea, QAbstractSpinBox, QApplication, QComboBox, QFrame, QScrollArea

ALTO_MINIMO_TABLA = 150  #px: unas cuatro filas de la tabla siempre a la vista


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


def envolver(widget, padre):
    """Zona desplazable (sin marco; las barras solo salen si el panel es más pequeño que su contenido)."""
    zona = QScrollArea(padre)
    zona.setWidgetResizable(True)
    zona.setFrameShape(QFrame.Shape.NoFrame)
    zona.setWidget(widget)
    return zona
