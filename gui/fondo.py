"""
Mapa de fondo para localizar parcelas cuando el proyecto está vacío: cartografía catastral (WMS de la Dirección
General del Catastro) sobre la ortofoto PNOA (WMS del Instituto Geográfico Nacional, CC BY 4.0). Son servicios
públicos que se añaden como capas WMS (QGIS las pide al servidor; no se descarga ni se guarda nada).

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
)

from ..core.info import FUENTE_DGC

PROPIEDAD_FONDO = 'catastral_gml_tools/fondo'
GRUPO = 'Fondo (Catastro e IGN)'
#SRC en que se piden las imágenes: el del proyecto si ambos servicios lo ofrecen; si no, EPSG:3857 (QGIS reproyecta)
SRC_WMS = ('EPSG:25829', 'EPSG:25830', 'EPSG:25831', 'EPSG:4258', 'EPSG:4326', 'EPSG:3857')
SRC_PROYECTO_VACIO = 'EPSG:25830'  #El habitual en el trabajo catastral (la mayor parte de España)
ESPANA = QgsRectangle(-9.6, 35.8, 4.6, 43.9)  #Península y Baleares, en EPSG:4258

CAPAS = (
    #(nombre, url, capa del servicio, formato, transparente, fuente)
    ("Catastro (WMS)", 'https://ovc.catastro.meh.es/Cartografia/WMS/ServidorWMS.aspx', 'Catastro', 'image/png', True,
     f"© {FUENTE_DGC}"),
    ("Ortofoto PNOA (IGN)", 'https://www.ign.es/wms-inspire/pnoa-ma', 'OI.OrthoimageCoverage', 'image/jpeg', False,
     "PNOA cedido por © Instituto Geográfico Nacional (CC BY 4.0)"),
)


def capas_fondo(proyecto=None):
    proyecto = proyecto or QgsProject.instance()
    return [c for c in proyecto.mapLayers().values() if c.customProperty(PROPIEDAD_FONDO)]


def uri(url, capa, formato, transparente, src):
    return (f"contextualWMSLegend=0&crs={src}&dpiMode=7&featureCount=10&format={formato}&layers={capa}&styles="
            + ("&transparent=true" if transparente else '') + f"&url={url}")


def asegurar(iface=None):
    """
    Añade el fondo al final de la lista de capas si aún no está. Si el proyecto estaba vacío, lo pone en EPSG:25830 y
    acerca el mapa a España. Devuelve las capas añadidas (lista vacía si ya estaban o si no hay conexión).
    """
    proyecto = QgsProject.instance()
    if capas_fondo(proyecto):
        return []
    vacio = not proyecto.mapLayers()
    if vacio:
        proyecto.setCrs(QgsCoordinateReferenceSystem(SRC_PROYECTO_VACIO))
    src = proyecto.crs().authid() if proyecto.crs().authid() in SRC_WMS else 'EPSG:3857'
    nuevas = []
    for nombre, url, capa_wms, formato, transparente, fuente in CAPAS:
        capa = QgsRasterLayer(uri(url, capa_wms, formato, transparente, src), nombre, 'wms')
        if not capa.isValid():  #Sin conexión o servicio caído: QGIS no admite capas no válidas
            continue
        capa.setCustomProperty(PROPIEDAD_FONDO, fuente)
        metadatos = capa.metadata()
        metadatos.setRights([fuente])
        capa.setMetadata(metadatos)
        nuevas.append(capa)
    if nuevas:
        grupo = proyecto.layerTreeRoot().addGroup(GRUPO)  #Al final: debajo de todo lo demás
        for capa in nuevas:
            proyecto.addMapLayer(capa, False)
            grupo.addLayer(capa).setExpanded(False)  #Leyenda plegada: la del WMS del Catastro es una imagen muy alta
        grupo.setExpanded(False)
    if vacio and iface is not None and hasattr(iface, 'mapCanvas'):
        lienzo = iface.mapCanvas()
        destino = lienzo.mapSettings().destinationCrs()
        if not destino.isValid():
            destino = proyecto.crs()
        transformacion = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:4258'), destino, proyecto)
        try:
            lienzo.setExtent(transformacion.transformBoundingBox(ESPANA))
            lienzo.refresh()
        except QgsCsException:  #Sin transformación posible: se deja el mapa como está
            pass
    return nuevas
