"""
Lectura de una capa de huellas de construcciones para el GML de edificio (mejora 19): cada polígono es un edificio o
una piscina. Sirve una capa dibujada por el usuario, la capa «Construcciones» de la pestaña Descargar (campos tipo,
localId, plantas y naturaleza) o una capa de otro programa (shapefile, GeoPackage, DXF…): en una capa de líneas, como la
de un DXF, cada línea cerrada es una huella y las abiertas no se usan. En un DXF, la capa (campo «Layer») cuyo nombre
diga piscina marca las piscinas.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
from collections import Counter
from dataclasses import dataclass

from qgis.core import Qgis, QgsDefaultValue, QgsEditorWidgetSetup, QgsFeature, QgsGeometry, QgsVectorLayer

from . import geometria as geo
from . import gml_edificio as ge
from . import gml_lector as gl
from . import refcat
from .capa_parcelas import _texto, es_capa_poligonos

CAMPOS_ID = ('localId', 'localid', 'refcat', 'ref_catastral', 'referencia', 'nationalCadastralReference', 'rc')
CAMPOS_PLANTAS = ('plantas', 'numberOfFloorsAboveGround', 'n_plantas', 'num_plantas')
CAMPOS_CAPA = ('Layer', 'layer', 'capa', 'CAPA')  #Nombre de la capa de dibujo (DXF y DWG leídos por GDAL)
CIERRE = 0.01  #m: una línea cuyo final está a menos de 1 cm del principio se considera cerrada


@dataclass
class FilaConstruccion:
    fid: int
    tipo: str                   #ge.EDIFICIO o ge.PISCINA
    plantas: object             #Entero o None
    geometria: QgsGeometry      #En el SRC de la capa
    partes: int = 1
    referencia: str = ''        #Referencia de parcela deducida de la entidad (o '')
    estado: str = 'functional'  #conditionOfConstruction (campo «estado» de la capa, si lo tiene)


def _campo(capa, nombres):
    return next((n for n in nombres if capa.fields().indexOf(n) >= 0), '')


def es_capa_huellas(capa):
    """Capa de polígonos o de líneas (las líneas cerradas de un DXF también sirven de huella)."""
    return (capa is not None and capa.isValid() and hasattr(capa, 'geometryType')
            and capa.geometryType() in (Qgis.GeometryType.Polygon, Qgis.GeometryType.Line))


def _es_lineas(capa):
    return capa.geometryType() == Qgis.GeometryType.Line


def poligono_de_lineas(geometria):
    """
    Polígono con las líneas cerradas de una geometría de líneas (cada una, un recinto) o None si no hay ninguna.
    Devuelve (polígono o None, número de líneas abiertas).
    """
    if geometria is None or geometria.isNull() or geometria.isEmpty():
        return None, 0
    lineas = geometria.asMultiPolyline() if geometria.isMultipart() else [geometria.asPolyline()]
    anillos, abiertas = [], 0
    for linea in lineas:
        if len(linea) >= 4 and linea[0].distance(linea[-1]) <= CIERRE:
            anillos.append(list(linea[:-1]) + [linea[0]])
        else:
            abiertas += 1
    if not anillos:
        return None, abiertas
    poligonos = [QgsGeometry.fromPolygonXY([a]) for a in anillos]
    return (poligonos[0] if len(poligonos) == 1 else QgsGeometry.unaryUnion(poligonos)), abiertas


def src_incorrecto(capa):
    """
    Texto del problema si la capa no tiene SRC o si sus coordenadas no encajan con él (lo típico de un DXF en UTM que
    QGIS abre en un SRC geográfico); '' si está bien.
    """
    if capa is None:
        return ''
    crs = capa.crs()
    if not crs.isValid():
        return "La capa no tiene SRC: asígnelo en sus propiedades (pestaña Fuente)"
    extension = capa.extent()
    if crs.isGeographic() and not extension.isEmpty() and (abs(extension.xMaximum()) > 180 or abs(extension.yMaximum()) > 90):
        return (f"Las coordenadas de la capa no encajan con su SRC ({crs.authid()}): parecen UTM. Asigne el SRC correcto en "
                "sus propiedades (pestaña Fuente), p. ej. EPSG:25830")
    return ''


def es_capa_de_parcelas(capa):
    """
    True si la capa es de parcelas (p. ej. la «Parcela» o «Colindantes» de Descargar, o la vista de un GML de parcela):
    sus polígonos son parcelas, no huellas de construcciones.
    """
    if not es_capa_poligonos(capa) or capa.fields().indexOf('tipo') < 0:
        return False
    tipos = {_texto(f['tipo']) for f, _ in zip(capa.getFeatures(), range(50))}
    return bool(tipos) and tipos <= {gl.PARCELA}


def nueva_capa_huellas(crs, nombre="Huellas de construcciones", filas=(), crs_filas=None):
    """
    Capa temporal para dibujar las huellas: campos tipo (edificio o piscina, con lista desplegable) y plantas (sobre
    rasante) y estado del edificio (terminado, en construcción…). Cada polígono nuevo es un edificio terminado salvo que
    se elija otra cosa en el formulario. Con filas (FilaConstruccion en crs_filas), la capa empieza con una copia de esas
    construcciones, para retocarlas sin tocar la capa original (p. ej. la descargada del Catastro o un DXF).
    """
    capa = QgsVectorLayer(f"Polygon?crs={crs.authid()}&field=tipo:string(20)&field=plantas:integer&field=estado:string(20)",
                          nombre, 'memory')
    i_tipo = capa.fields().indexOf('tipo')
    capa.setEditorWidgetSetup(i_tipo, QgsEditorWidgetSetup('ValueMap', {'map': [{'Edificio': ge.EDIFICIO},
                                                                                {'Piscina': ge.PISCINA}]}))
    capa.setDefaultValueDefinition(i_tipo, QgsDefaultValue(f"'{ge.EDIFICIO}'"))
    capa.setFieldAlias(capa.fields().indexOf('plantas'), 'Plantas sobre rasante')
    i_estado = capa.fields().indexOf('estado')
    capa.setEditorWidgetSetup(i_estado, QgsEditorWidgetSetup('ValueMap', {'map': [{ge.NOMBRES_CORTOS[e]: e}
                                                                                  for e in ge.ESTADOS]}))
    capa.setDefaultValueDefinition(i_estado, QgsDefaultValue("'functional'"))
    capa.setFieldAlias(i_estado, 'Estado (edificios)')
    if filas:
        epsg = geo.epsg_de(crs)
        entidades = []
        for f in filas:
            entidad = QgsFeature(capa.fields())
            entidad.setGeometry(geo.transformar(f.geometria, crs_filas or crs, epsg) if epsg else f.geometria)
            entidad.setAttributes([f.tipo, f.plantas, f.estado if f.tipo == ge.EDIFICIO else None])
            entidades.append(entidad)
        capa.dataProvider().addFeatures(entidades)
    return capa


def campo_plantas(capa):
    """Campo de plantas con nombre habitual, o ''."""
    return _campo(capa, CAMPOS_PLANTAS) if es_capa_huellas(capa) else ''


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
    capa_dibujo = valores.get('capa', '').lower()
    return (valores.get('naturaleza', '') == 'openAirPool' or tipo in (gl.OTRA, ge.PISCINA)
            or '_pi.' in valores.get('id', '').lower() or '_piscina' in valores.get('id', '').lower()
            or 'piscin' in capa_dibujo or 'pool' in capa_dibujo)


def leer_capa(capa, solo_seleccion=False, campo_plantas_=''):
    """
    Filas de la tabla a partir de los polígonos de la capa (o de las líneas cerradas, en una capa de líneas). Las líneas
    abiertas no dan fila: lineas_abiertas() las cuenta.
    """
    if not es_capa_huellas(capa):
        return []
    nombres = capa.fields().names()
    campo_id = _campo(capa, CAMPOS_ID)
    campo_capa = _campo(capa, CAMPOS_CAPA)
    lineas = _es_lineas(capa)
    filas = []
    for entidad in (capa.getSelectedFeatures() if solo_seleccion else capa.getFeatures()):
        geometria = QgsGeometry(entidad.geometry())
        if lineas:
            geometria, _ = poligono_de_lineas(geometria)
            if geometria is None:
                continue
        valores = {'tipo': _texto(entidad['tipo']) if 'tipo' in nombres else '',
                   'naturaleza': _texto(entidad['naturaleza']) if 'naturaleza' in nombres else '',
                   'id': _texto(entidad[campo_id]) if campo_id else '',
                   'capa': _texto(entidad[campo_capa]) if campo_capa else ''}
        tipo = ge.PISCINA if es_piscina(valores) else ge.EDIFICIO
        plantas = _entero(entidad[campo_plantas_]) if campo_plantas_ and tipo == ge.EDIFICIO else None
        rc = refcat.limpiar(valores['id'])[:14]
        partes = 0 if geometria.isNull() else len(geometria.asGeometryCollection()) if geometria.isMultipart() else 1
        estado = _texto(entidad['estado']) if 'estado' in nombres else ''
        filas.append(FilaConstruccion(entidad.id(), tipo, plantas, geometria, partes,
                                      rc if refcat.es_rc_parcela(rc) else '',
                                      estado if estado in ge.ESTADOS else 'functional'))
    return filas


def lineas_abiertas(capa, solo_seleccion=False):
    """Número de líneas sin cerrar de una capa de líneas (no se pueden usar como huella)."""
    if not es_capa_huellas(capa) or not _es_lineas(capa):
        return 0
    return sum(poligono_de_lineas(e.geometry())[1]
               for e in (capa.getSelectedFeatures() if solo_seleccion else capa.getFeatures()))


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


def a_construcciones(filas, ids, tipos, plantas, estados, crs, epsg):
    """Construccion del GML (geometría transformada al EPSG del fichero) con lo que haya en la tabla (estado por fila)."""
    return [ge.Construccion(local_id, geo.transformar(f.geometria, crs, epsg), tipo, planta if tipo == ge.EDIFICIO else None,
                            estado)
            for f, local_id, tipo, planta, estado in zip(filas, ids, tipos, plantas, estados)]
