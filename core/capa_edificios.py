"""
Lectura de una capa de huellas de construcciones para el GML de edificio (mejora 19): cada polígono es un edificio o
una piscina. Sirve tanto una capa dibujada por el usuario como la capa «Construcciones» de la pestaña Descargar
(campos tipo, localId, plantas y naturaleza).

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
from collections import Counter
from dataclasses import dataclass

from qgis.core import QgsGeometry

from . import geometria as geo
from . import gml_edificio as ge
from . import gml_lector as gl
from . import refcat
from .capa_parcelas import _texto, es_capa_poligonos

CAMPOS_ID = ('localId', 'localid', 'refcat', 'ref_catastral', 'referencia', 'nationalCadastralReference', 'rc')
CAMPOS_PLANTAS = ('plantas', 'numberOfFloorsAboveGround', 'n_plantas', 'num_plantas')


@dataclass
class FilaConstruccion:
    fid: int
    tipo: str                   #ge.EDIFICIO o ge.PISCINA
    plantas: object             #Entero o None
    geometria: QgsGeometry      #En el SRC de la capa
    partes: int = 1
    referencia: str = ''        #Referencia de parcela deducida de la entidad (o '')


def _campo(capa, nombres):
    return next((n for n in nombres if capa.fields().indexOf(n) >= 0), '')


def campo_plantas(capa):
    """Campo de plantas con nombre habitual, o ''."""
    return _campo(capa, CAMPOS_PLANTAS) if es_capa_poligonos(capa) else ''


def _entero(valor):
    texto = _texto(valor).strip()
    try:
        numero = int(float(texto.replace(',', '.')))
    except ValueError:
        return None
    return numero if numero > 0 else None


def es_piscina(valores):
    """Piscina según los campos de la descarga (tipo, naturaleza) o el identificador (_PI., _Piscina_)."""
    tipo = valores.get('tipo', '').lower()
    return (valores.get('naturaleza', '') == 'openAirPool' or tipo in (gl.OTRA, ge.PISCINA)
            or '_pi.' in valores.get('id', '').lower() or '_piscina' in valores.get('id', '').lower())


def leer_capa(capa, solo_seleccion=False, campo_plantas_=''):
    """Filas de la tabla a partir de los polígonos de la capa."""
    if not es_capa_poligonos(capa):
        return []
    nombres = capa.fields().names()
    campo_id = _campo(capa, CAMPOS_ID)
    filas = []
    for entidad in (capa.getSelectedFeatures() if solo_seleccion else capa.getFeatures()):
        geometria = QgsGeometry(entidad.geometry())
        valores = {'tipo': _texto(entidad['tipo']) if 'tipo' in nombres else '',
                   'naturaleza': _texto(entidad['naturaleza']) if 'naturaleza' in nombres else '',
                   'id': _texto(entidad[campo_id]) if campo_id else ''}
        tipo = ge.PISCINA if es_piscina(valores) else ge.EDIFICIO
        plantas = _entero(entidad[campo_plantas_]) if campo_plantas_ and tipo == ge.EDIFICIO else None
        rc = refcat.limpiar(valores['id'])[:14]
        partes = 0 if geometria.isNull() else len(geometria.asGeometryCollection()) if geometria.isMultipart() else 1
        filas.append(FilaConstruccion(entidad.id(), tipo, plantas, geometria, partes,
                                      rc if refcat.es_rc_parcela(rc) else ''))
    return filas


def referencia_propuesta(filas):
    """La referencia de parcela más repetida en las construcciones, o ''."""
    cuenta = Counter(f.referencia for f in filas if f.referencia)
    return cuenta.most_common(1)[0][0] if cuenta else ''


def area_m2(fila, crs, epsg):
    """Superficie de la huella en el GML (m², con las coordenadas redondeadas al centímetro), o None."""
    if fila.geometria is None or fila.geometria.isNull() or epsg is None:
        return None
    recintos, _ = geo.preparar(geo.transformar(fila.geometria, crs, epsg))
    return sum(r.area_m2() for r in recintos) if recintos else None


def a_construcciones(filas, ids, tipos, plantas, estado, crs, epsg):
    """Construccion del GML (geometría transformada al EPSG del fichero) con lo que haya en la tabla."""
    return [ge.Construccion(local_id, geo.transformar(f.geometria, crs, epsg), tipo, planta if tipo == ge.EDIFICIO else None,
                            estado)
            for f, local_id, tipo, planta in zip(filas, ids, tipos, plantas)]
