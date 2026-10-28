"""
Estilos para las capas que crea el plugin: contorno sin relleno de color fuerte y etiqueta con el identificador,
para comparar el GML con la cartografía que haya debajo.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
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
           DOMINIO_PUBLICO: '#0c8599'}  #Verde azulado: caminos, cauces… (parcelas 9001-9999 de rústica)


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


ETIQUETA_NUEVA = '(nueva)'


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
    #Una parcela dibujada o salida de dividir no tiene identificador: se rotula «(nueva)» (su localId lo propone la
    #pestaña Parcela según la alteración; antes copiaba la referencia catastral y el mapa decía otra cosa que la tabla)
    ajustes.fieldName = f"coalesce(nullif(\"{campo_etiqueta}\", ''), '{ETIQUETA_NUEVA}')"
    ajustes.isExpression = True
    ajustes.setFormat(formato)
    capa.setLabeling(QgsVectorLayerSimpleLabeling(ajustes))
    capa.setLabelsEnabled(True)
    capa.triggerRepaint()
    return capa


def capa_zona(geometria, epsg, nombre, color, alfa=60, ancho=0.4, campos=None):
    """Capa de memoria con una zona de relleno liso semitransparente (el margen de identidad o lo que queda fuera).

    campos: {nombre: valor} para la tabla de atributos (float → double, int → integer, el resto texto), para que la capa
    se entienda sola si se guarda o se consulta con «Identificar objetos»."""
    campos = campos or {}
    tipos = ''.join(f"&field={n}:{'double' if isinstance(v, float) else 'integer' if isinstance(v, int) else 'string'}"
                    for n, v in campos.items())
    capa = QgsVectorLayer(f"MultiPolygon?crs=EPSG:{epsg or 25830}{tipos}", nombre, 'memory')
    entidad = QgsFeature(capa.fields())
    g = QgsGeometry(geometria)
    g.convertToMultiType()
    entidad.setGeometry(g)
    if campos:
        entidad.setAttributes(list(campos.values()))
    capa.dataProvider().addFeatures([entidad])
    capa.updateExtents()
    capa.setCrs(QgsCoordinateReferenceSystem(f'EPSG:{epsg or 25830}'))
    c = QColor(color)
    capa.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple({
        'color': f'{c.red()},{c.green()},{c.blue()},{alfa}', 'outline_color': color, 'outline_width': str(ancho),
        'outline_width_unit': 'MM'})))
    return capa


def capa_diferencia(geometria, epsg, nombre, color):
    """Capa de memoria con una diferencia de superficie (exceso o defecto), rayada y con su superficie en m²."""
    capa = QgsVectorLayer(f"MultiPolygon?crs=EPSG:{epsg or 25830}&field=superficie:double", nombre, 'memory')
    entidad = QgsFeature(capa.fields())
    g = QgsGeometry(geometria)
    g.convertToMultiType()
    entidad.setGeometry(g)
    entidad.setAttributes([round(g.area(), 2)])
    capa.dataProvider().addFeatures([entidad])
    capa.updateExtents()
    capa.setCrs(QgsCoordinateReferenceSystem(f'EPSG:{epsg or 25830}'))
    c = QColor(color)
    simbolo_relleno = QgsFillSymbol.createSimple({'color': f'{c.red()},{c.green()},{c.blue()},110', 'style': 'b_diagonal',
                                                  'outline_color': color, 'outline_width': '0.5',
                                                  'outline_width_unit': 'MM'})
    capa.setRenderer(QgsSingleSymbolRenderer(simbolo_relleno))
    return capa
