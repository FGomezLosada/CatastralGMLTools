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

from ..core.gml_lector import DOMINIO_PUBLICO, EDIFICIO, OTRA, PARCELA

COLORES = {PARCELA: '#e8590c', EDIFICIO: '#c92a2a', OTRA: '#1971c2',  #Naranja, rojo y azul
           DOMINIO_PUBLICO: '#0c8599'}  #Verde azulado: caminos, cauces… (parcelas 9000 de rústica)


def simbolo(color):
    c = QColor(color)
    return QgsFillSymbol.createSimple({
        #Relleno casi transparente (15 %). En formato «R,G,B,A»: «#RRGGBBAA» lo lee Qt como #AARRGGBB (salía morado opaco)
        'color': f'{c.red()},{c.green()},{c.blue()},38',
        'outline_color': color,
        'outline_width': '0.6',
        'outline_width_unit': 'MM',
    })


COLOR_COLINDANTES = '#868e96'  #Gris: las colindantes son contexto, la parcela descargada va en naranja
COLOR_ENTORNO = '#adb5bd'      #Gris claro: parcelas cercanas que no tocan la parcela (al otro lado de la calle)


def aplicar(capa, colores=None, campo_etiqueta='localId'):
    """
    Simbología por tipo (solo los tipos que hay en la capa, para que la leyenda no muestre los demás) y etiqueta.
    colores cambia el color de algún tipo, p. ej. {PARCELA: COLOR_COLINDANTES}. campo_etiqueta=None: sin etiquetas.
    """
    presentes = {f['tipo'] for f in capa.getFeatures()}
    tabla = dict(COLORES, **(colores or {}))
    categorias = [QgsRendererCategory(tipo, simbolo(color), tipo.capitalize())
                  for tipo, color in tabla.items() if tipo in presentes]
    capa.setRenderer(QgsCategorizedSymbolRenderer('tipo', categorias))

    if not campo_etiqueta:
        capa.setLabelsEnabled(False)
        capa.triggerRepaint()
        return capa
    formato = QgsTextFormat()
    formato.setSize(9)
    formato.setColor(QColor('#212529'))
    fondo = QgsTextBufferSettings()
    fondo.setEnabled(True)
    fondo.setSize(1)
    fondo.setColor(QColor('#ffffff'))
    formato.setBuffer(fondo)
    ajustes = QgsPalLayerSettings()
    ajustes.fieldName = campo_etiqueta
    ajustes.setFormat(formato)
    capa.setLabeling(QgsVectorLayerSimpleLabeling(ajustes))
    capa.setLabelsEnabled(True)
    capa.triggerRepaint()
    return capa
