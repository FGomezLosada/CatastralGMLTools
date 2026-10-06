"""
Parcelas a partir de una capa de QGIS: lee los polígonos, propone identificador, namespace y label,
y los convierte en ParcelaGML en el SRC del fichero. Sin interfaz.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
from dataclasses import dataclass

from qgis.core import Qgis, QgsGeometry

from . import geometria as geo
from . import refcat
from .gml_parcela import LOCAL, SDGC, ParcelaGML, label_por_defecto


@dataclass
class FilaParcela:
    """Una parcela de la capa tal como se muestra en la tabla del panel (el usuario puede cambiar id, namespace y label)."""
    fid: int
    local_id: str
    namespace: str
    label: str
    geometria: QgsGeometry  #En el SRC de la capa
    partes: int = 1


def es_capa_poligonos(capa):
    return (capa is not None and capa.isValid() and hasattr(capa, 'geometryType')
            and capa.geometryType() == Qgis.GeometryType.Polygon)


def _texto(valor):
    """Valor de un campo como texto; los nulos de QGIS (NULL, QVariant nulo) como cadena vacía."""
    if valor is None:
        return ''
    if hasattr(valor, 'isNull') and valor.isNull():
        return ''
    texto = str(valor).strip()
    return '' if texto.upper() == 'NULL' else texto


def namespace_propuesto(local_id):
    """SDGC si el identificador es una referencia catastral de parcela; LOCAL en otro caso."""
    return SDGC if refcat.es_rc_parcela(local_id) else LOCAL


def leer_capa(capa, solo_seleccion=False, campo_id='', campo_label=''):
    """
    Filas de la tabla a partir de los polígonos de la capa.
    Identificador: el valor del campo elegido (limpio si es una RC) o, si está vacío, «Parcela_N».
    """
    filas = []
    if not es_capa_poligonos(capa):
        return filas
    entidades = capa.getSelectedFeatures() if solo_seleccion else capa.getFeatures()
    usados = set()
    for n, entidad in enumerate(entidades, start=1):
        geometria = QgsGeometry(entidad.geometry())
        valor = _texto(entidad[campo_id]) if campo_id else ''
        local_id = refcat.limpiar(valor) if refcat.es_rc_parcela(valor) else valor.replace(' ', '_')
        if not local_id:
            local_id = f"Parcela_{n}"
        while local_id in usados:  #Evita repetidos al proponer (el usuario puede cambiarlos)
            local_id += '_b'
        usados.add(local_id)
        namespace = namespace_propuesto(local_id)
        label = _texto(entidad[campo_label]) if campo_label else ''
        partes = 0 if geometria.isNull() else len(geometria.asGeometryCollection()) if geometria.isMultipart() else 1
        filas.append(FilaParcela(entidad.id(), local_id, namespace, label or label_por_defecto(local_id, namespace),
                                 geometria, partes))
    return filas


def epsg_para(filas, crs):
    """SRC recomendado para el fichero: el de la capa si lo admite la Sede; si no, el huso según la posición."""
    epsg = geo.epsg_de(crs)
    if epsg in geo.SRC_ADMITIDOS:
        return epsg
    geometrias = [f.geometria for f in filas if f.geometria is not None and not f.geometria.isNull()]
    if not geometrias:
        return None
    return geo.epsg_recomendado(QgsGeometry.unaryUnion(geometrias), crs)


def area_m2(fila, crs, epsg):
    """
    Superficie que tendrá la parcela en el GML (m² en el SRC del fichero), o None si no se puede calcular.
    Se calcula igual que en el GML: con las coordenadas ya redondeadas al centímetro (por eso puede diferir en 1 m²
    de la superficie de la geometría original).
    """
    if fila.geometria is None or fila.geometria.isNull() or epsg is None:
        return None
    recintos, _ = geo.preparar(geo.transformar(fila.geometria, crs, epsg))
    if not recintos:
        return None
    return sum(r.area_m2() for r in recintos)


def a_parcelas_gml(filas, crs, epsg):
    """ParcelaGML con la geometría transformada al EPSG del fichero."""
    return [ParcelaGML(f.local_id, f.namespace, geo.transformar(f.geometria, crs, epsg), f.label)
            for f in filas]
