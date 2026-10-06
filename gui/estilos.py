"""
Estilos para las capas que crea el plugin: contorno sin relleno de color fuerte y etiqueta con el identificador,
para comparar el GML con la cartografía que haya debajo.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsFillSymbol,
    QgsPalLayerSettings,
    QgsRendererCategory,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtGui import QColor

from ..core.gml_lector import EDIFICIO, OTRA, PARCELA

COLORES = {PARCELA: '#e8590c', EDIFICIO: '#c92a2a', OTRA: '#1971c2'}  #Naranja, rojo y azul


def simbolo(color):
    c = QColor(color)
    return QgsFillSymbol.createSimple({
        #Relleno casi transparente (15 %). En formato «R,G,B,A»: «#RRGGBBAA» lo lee Qt como #AARRGGBB (salía morado opaco)
        'color': f'{c.red()},{c.green()},{c.blue()},38',
        'outline_color': color,
        'outline_width': '0.6',
        'outline_width_unit': 'MM',
    })


def aplicar(capa):
    """Simbología por tipo (parcela, edificio, otra construcción) y etiqueta con el localId."""
    categorias = [QgsRendererCategory(tipo, simbolo(color), tipo.capitalize()) for tipo, color in COLORES.items()]
    capa.setRenderer(QgsCategorizedSymbolRenderer('tipo', categorias))

    formato = QgsTextFormat()
    formato.setSize(9)
    formato.setColor(QColor('#212529'))
    fondo = QgsTextBufferSettings()
    fondo.setEnabled(True)
    fondo.setSize(1)
    fondo.setColor(QColor('#ffffff'))
    formato.setBuffer(fondo)
    ajustes = QgsPalLayerSettings()
    ajustes.fieldName = 'localId'
    ajustes.setFormat(formato)
    capa.setLabeling(QgsVectorLayerSimpleLabeling(ajustes))
    capa.setLabelsEnabled(True)
    capa.triggerRepaint()
    return capa
