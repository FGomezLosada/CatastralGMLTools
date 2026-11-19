"""
Catastro a una fecha: el parcelario de la Dirección General del Catastro tal como estaba en una fecha, como capa WMS.

El WMS de la DGC (ServidorWMS.aspx) admite el parámetro TIME=AAAA-MM-DD y devuelve la cartografía vigente en esa fecha,
con la fecha impresa en rojo en la imagen (comprobado el 19/11/2026 en QGIS 3.40 y 4.2: 2003, 2008, 2015 y 2022 dan
parcelarios distintos). Es solo imagen: la cartografía histórica no se puede descargar en vector. Sirve para ver si el
Catastro ha cambiado un lindero desde el levantamiento (petición del 19/11/2026, maqueta F aprobada).

Las capas van en el grupo «Catastro a una fecha», arriba del todo, sin repetir una fecha que ya esté.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import datetime

from qgis.core import QgsProject, QgsRasterLayer

from .info import FUENTE_DGC

URL = 'https://ovc.catastro.meh.es/Cartografia/WMS/ServidorWMS.aspx'
PROPIEDAD = 'catastral_gml_tools/catastro_fecha'  #Fecha (AAAA-MM-DD) de las capas creadas aquí
GRUPO = 'Catastro a una fecha'
PRIMERA = datetime.date(2002, 1, 1)  #Desde cuándo tiene sentido pedirla
ATAJOS = (2005, 2010, 2015, 2020)
#SRC en que se piden las imágenes: el del proyecto si el servicio lo ofrece; si no, EPSG:3857 (QGIS reproyecta)
SRC_WMS = ('EPSG:25829', 'EPSG:25830', 'EPSG:25831', 'EPSG:4258', 'EPSG:4326', 'EPSG:3857')


def texto_fecha(fecha):
    return fecha.strftime('%d/%m/%Y')


def nombre_capa(fecha):
    return f"Catastro a {texto_fecha(fecha)}"


def fecha_valida(fecha, hoy=None):
    """La fecha dentro de lo que tiene sentido pedir: entre PRIMERA y hoy."""
    hoy = hoy or datetime.date.today()
    return min(max(fecha, PRIMERA), hoy)


def uri(fecha, src='EPSG:25830'):
    """URI de la capa WMS con la fecha (QGIS 4 la guarda codificada, pero la fecha llega igual al servidor)."""
    src = src if src in SRC_WMS else 'EPSG:3857'
    return (f"contextualWMSLegend=0&crs={src}&dpiMode=7&featureCount=10&format=image/png&layers=Catastro&styles="
            f"&transparent=true&url={URL}?TIME={fecha.isoformat()}")


def capas(proyecto=None):
    proyecto = proyecto or QgsProject.instance()
    return [c for c in proyecto.mapLayers().values() if c.customProperty(PROPIEDAD)]


def capa_de(fecha, proyecto=None):
    """La capa de esa fecha si ya está en el proyecto."""
    return next((c for c in capas(proyecto) if c.customProperty(PROPIEDAD) == fecha.isoformat()), None)


def fijar_transparencia(porcentaje, proyecto=None):
    """Transparencia (0 a 100 %) de todas las capas de fechas: para ver debajo el Catastro actual o la ortofoto."""
    for capa in capas(proyecto):
        if capa.renderer() is not None:
            capa.renderer().setOpacity(1 - max(0, min(100, porcentaje)) / 100)
            capa.triggerRepaint()


def anadir(fecha, proyecto=None, transparencia=0):
    """
    Añade (o reutiliza) la capa del Catastro en esa fecha. Devuelve (capa, nueva, error): capa None si el servicio no
    responde; nueva False si ya estaba.
    """
    proyecto = proyecto or QgsProject.instance()
    fecha = fecha_valida(fecha)
    existente = capa_de(fecha, proyecto)
    if existente is not None:
        return existente, False, ''
    capa = QgsRasterLayer(uri(fecha, proyecto.crs().authid()), nombre_capa(fecha), 'wms')
    if not capa.isValid():
        return None, False, "El servicio WMS del Catastro no responde (sin conexión o en mantenimiento): pruebe más tarde"
    capa.setCustomProperty(PROPIEDAD, fecha.isoformat())
    metadatos = capa.metadata()
    metadatos.setRights([f"© {FUENTE_DGC}. Cartografía catastral vigente el {texto_fecha(fecha)} (servicio WMS)"])
    metadatos.setAbstract(f"Parcelario del Catastro tal como estaba el {texto_fecha(fecha)}. Solo imagen: no es la "
                          "cartografía vigente.")
    capa.setMetadata(metadatos)
    if capa.renderer() is not None:
        capa.renderer().setOpacity(1 - max(0, min(100, transparencia)) / 100)
    proyecto.addMapLayer(capa, False)
    raiz = proyecto.layerTreeRoot()
    grupo = raiz.findGroup(GRUPO)
    if grupo is None:
        grupo = raiz.insertGroup(0, GRUPO)  #Arriba del todo: encima del parcelario y del fondo
    grupo.insertLayer(0, capa).setExpanded(False)  #Leyenda plegada: la del WMS del Catastro es muy alta
    return capa, True, ''
