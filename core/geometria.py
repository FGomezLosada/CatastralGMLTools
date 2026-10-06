"""
Geometría para los GML del Catastro: preparar los recintos tal como los pide la Sede Electrónica.

Reglas (documentación de la DGC, ver docs/INVESTIGACION.md):
  - Coordenadas en metros con 2 decimales, separador decimal punto.
  - Anillos cerrados (último vértice = primero) y con al menos 4 vértices.
  - Anillo exterior en sentido horario; anillos interiores (huecos) en sentido antihorario.
  - Sin autointersecciones. Un solo recinto por parcela: una finca discontinua se aporta como varias parcelas.
  - Superficie: la cartesiana de la geometría, redondeada al m².
  - Punto de referencia (referencePoint): un punto interior del recinto.
  - Las curvas se sustituyen por vértices con una flecha menor de 2 cm.
  - SRC: EPSG 25829, 25830, 25831 (ETRS89 UTM 29/30/31) o 32628 (WGS84 UTM 28, Canarias).

Aquí no hay interfaz: las funciones reciben QgsGeometry y devuelven datos e incidencias.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import math
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from qgis.core import (
    Qgis,
    QgsAbstractGeometry,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsWkbTypes,
)

from .incidencias import AVISO, ERROR, INFO, Incidencia

DECIMALES = 2
FLECHA_MAXIMA = 0.015  #Metros. Menor que los 2 cm exigidos, con margen para el redondeo al centímetro
SRC_ADMITIDOS = (25829, 25830, 25831, 32628)
MINIMO_VERTICES = 4  #Incluido el de cierre

#Husos por provincia (código INE de 2 dígitos = código de provincia del Catastro).
#Fuente: tabla del documento «Preguntas y respuestas acerca de la coordinación Catastro-Registro» (DGC).
#Marcadas con * las que no aparecen en esa tabla y se deducen por su posición geográfica.
HUSOS_PROVINCIA = {
    '02': (25830,), '03': (25830, 25831), '04': (25830,), '05': (25830,), '06': (25829, 25830), '07': (25831,),
    '08': (25831,), '09': (25830,), '10': (25829, 25830), '11': (25829, 25830), '12': (25830, 25831), '13': (25830,),
    '14': (25830,), '15': (25829,), '16': (25830,), '17': (25831,),  # 17 Girona*
    '18': (25830,), '19': (25830,), '21': (25829,), '22': (25830, 25831), '23': (25830,), '24': (25829, 25830),
    '25': (25831,), '26': (25830,), '27': (25829,), '28': (25830,), '29': (25830,), '30': (25830,), '32': (25829,),
    '33': (25829, 25830), '34': (25830,), '35': (32628,),  # 35 Las Palmas*
    '36': (25829,), '37': (25829, 25830), '38': (32628,), '39': (25830,), '40': (25830,), '41': (25829, 25830),
    '42': (25830,), '43': (25831,), '44': (25830, 25831), '45': (25830,), '46': (25830,), '47': (25830,),
    '49': (25829, 25830), '50': (25830, 25831), '51': (25830,), '52': (25830,),  # 52 Melilla*
}


@dataclass
class Recinto:
    """Un recinto listo para el GML: anillo exterior (horario) y huecos (antihorarios), con 2 decimales y cerrados."""
    exterior: list
    interiores: list = field(default_factory=list)

    def anillos(self):
        return [self.exterior, *self.interiores]

    def area(self):
        """Superficie cartesiana en m² (sin redondear): exterior menos huecos."""
        return abs(area_firmada(self.exterior)) - sum(abs(area_firmada(a)) for a in self.interiores)

    def area_m2(self):
        """Superficie redondeada al m² (redondeo aritmético: 0,5 sube), como cp:areaValue."""
        return redondear_m2(self.area())

    def geometria(self):
        """El recinto como QgsGeometry (polígono)."""
        return QgsGeometry.fromPolygonXY([[QgsPointXY(x, y) for x, y in anillo] for anillo in self.anillos()])


# ------------------------------------------------------------------ Cálculos básicos

def redondear(valor, decimales=DECIMALES):
    """Redondeo aritmético (0,005 → 0,01), no el «del banquero» de round()."""
    paso = Decimal(1).scaleb(-decimales)
    return float(Decimal(repr(valor)).quantize(paso, rounding=ROUND_HALF_UP))


def redondear_m2(area):
    return int(Decimal(repr(area)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def area_firmada(anillo):
    """Área con signo (fórmula del área de Gauss): positiva si el anillo va en sentido antihorario."""
    total = 0.0
    for (x1, y1), (x2, y2) in zip(anillo, anillo[1:]):
        total += x1 * y2 - x2 * y1
    return total / 2.0


def es_horario(anillo):
    return area_firmada(anillo) < 0


def formatear(valor):
    """Coordenada con 2 decimales exactos, como se escribe en gml:posList."""
    return f"{redondear(valor):.{DECIMALES}f}"


# ------------------------------------------------------------------ Limpieza de anillos

def limpiar_anillo(puntos):
    """
    Redondea a 2 decimales, quita vértices repetidos seguidos y cierra el anillo.
    Devuelve (anillo, n_repetidos_quitados, se_ha_cerrado).
    """
    anillo = []
    repetidos = 0
    for p in puntos:
        punto = (redondear(p[0]), redondear(p[1]))
        if anillo and punto == anillo[-1]:
            repetidos += 1
            continue
        anillo.append(punto)
    cerrado = False
    if len(anillo) > 1 and anillo[0] == anillo[-1]:
        pass
    elif anillo:
        anillo.append(anillo[0])
        cerrado = True
    return anillo, repetidos, cerrado


def orientar(anillo, horario):
    """Devuelve el anillo en el sentido pedido (horario para el exterior, antihorario para los huecos)."""
    return anillo if es_horario(anillo) == horario else list(reversed(anillo))


# ------------------------------------------------------------------ Preparar una geometría

def tiene_curvas(geometria):
    return QgsWkbTypes.isCurvedType(geometria.wkbType())


def densificar(geometria, flecha=FLECHA_MAXIMA):
    """Sustituye arcos por segmentos con una flecha máxima en metros. Devuelve una QgsGeometry nueva."""
    if not tiene_curvas(geometria):
        return QgsGeometry(geometria)
    tipo = QgsAbstractGeometry.SegmentationToleranceType.MaximumDifference
    return QgsGeometry(geometria.constGet().segmentize(flecha, tipo))


def preparar(geometria, elemento=''):
    """
    Convierte una geometría de polígono en la lista de Recinto que irá al GML, con sus incidencias.
    Una geometría multiparte da varios recintos y una incidencia (cada parte debe ser una parcela distinta).
    Devuelve (recintos, incidencias).
    """
    incidencias = []
    if geometria is None or geometria.isNull() or geometria.isEmpty():
        return [], [Incidencia(ERROR, 'GEO-VACIA', "La geometría está vacía", elemento)]
    if QgsWkbTypes.geometryType(geometria.wkbType()) != Qgis.GeometryType.Polygon:
        return [], [Incidencia(ERROR, 'GEO-TIPO', "La geometría no es un polígono", elemento)]

    if tiene_curvas(geometria):
        geometria = densificar(geometria)
        incidencias.append(Incidencia(INFO, 'GEO-CURVAS', "Las curvas se han sustituido por vértices (flecha < 2 cm)",
                                      elemento))
    if QgsWkbTypes.hasZ(geometria.wkbType()) or QgsWkbTypes.hasM(geometria.wkbType()):
        geometria = QgsGeometry(geometria)
        geometria.get().dropZValue()
        geometria.get().dropMValue()
        incidencias.append(Incidencia(INFO, 'GEO-2D', "Se han quitado la Z y la M: el GML es 2D", elemento))

    poligonos = geometria.asMultiPolygon() if geometria.isMultipart() else [geometria.asPolygon()]
    poligonos = [p for p in poligonos if p]
    if len(poligonos) > 1:
        incidencias.append(Incidencia(ERROR, 'GEO-MULTIPARTE',
                                      f"La geometría tiene {len(poligonos)} partes: la Sede solo admite un recinto por parcela "
                                      "(una finca discontinua se aporta como varias parcelas)", elemento))

    recintos = []
    repetidos_total = cerrados_total = reorientados = 0
    for poligono in poligonos:
        anillos = []
        for i, puntos in enumerate(poligono):
            anillo, repetidos, cerrado = limpiar_anillo((p.x(), p.y()) for p in puntos)
            repetidos_total += repetidos
            cerrados_total += int(cerrado)
            if len(anillo) < MINIMO_VERTICES:
                incidencias.append(Incidencia(ERROR, 'GEO-POCOS-VERTICES',
                                              f"Un anillo tiene {len(anillo)} vértices: el mínimo es {MINIMO_VERTICES} "
                                              "(incluido el de cierre)", elemento))
                continue
            orientado = orientar(anillo, horario=(i == 0))
            reorientados += int(orientado is not anillo)
            anillos.append(orientado)
        if anillos:
            recintos.append(Recinto(anillos[0], anillos[1:]))

    if repetidos_total:
        incidencias.append(Incidencia(INFO, 'GEO-REPETIDOS', f"Se han quitado {repetidos_total} vértices repetidos", elemento))
    if cerrados_total:
        incidencias.append(Incidencia(INFO, 'GEO-CIERRE', "Se han cerrado los anillos abiertos", elemento))
    if reorientados:
        incidencias.append(Incidencia(INFO, 'GEO-ORIENTACION',
                                      "Se ha corregido el sentido de los anillos (exterior horario, huecos antihorario)",
                                      elemento))

    for recinto in recintos:
        geom = recinto.geometria()
        if not geom.isGeosValid():
            error = geom.validateGeometry()
            detalle = f": {error[0].what()}" if error else ''
            incidencias.append(Incidencia(ERROR, 'GEO-INVALIDA',
                                          f"La geometría no es válida (autointersección o anillos que se tocan){detalle}",
                                          elemento))
        if recinto.area_m2() <= 0:
            incidencias.append(Incidencia(ERROR, 'GEO-AREA', "La superficie es 0 m²", elemento))
    return recintos, incidencias


def punto_interior(recinto):
    """
    Punto interior del recinto con 2 decimales (para cp:referencePoint).
    Se prueba el centroide; si cae fuera (parcelas en L, con huecos...), un punto sobre la superficie y,
    por último, el polo de inaccesibilidad (el punto más alejado del borde).
    """
    geom = recinto.geometria()
    candidatos = [geom.centroid(), geom.pointOnSurface()]
    polo = geom.poleOfInaccessibility(0.01)
    if polo and polo[0] is not None:
        candidatos.append(polo[0])
    for candidato in candidatos:
        if candidato is None or candidato.isNull():
            continue
        p = candidato.asPoint()
        redondeado = (redondear(p.x()), redondear(p.y()))
        if geom.contains(QgsGeometry.fromPointXY(QgsPointXY(*redondeado))):
            return redondeado
    p = geom.pointOnSurface().asPoint()
    return redondear(p.x()), redondear(p.y())


# ------------------------------------------------------------------ Sistemas de referencia

def epsg_de(crs):
    """Código EPSG (entero) de un QgsCoordinateReferenceSystem, o None."""
    if crs is None or not crs.isValid():
        return None
    authid = crs.authid()
    if authid.upper().startswith('EPSG:'):
        try:
            return int(authid.split(':')[1])
        except ValueError:
            return None
    return None


def src_admitido(crs):
    return epsg_de(crs) in SRC_ADMITIDOS


def husos_provincia(codigo_provincia):
    """EPSG admitidos para una provincia (código de 2 dígitos). Tupla vacía si no se conoce o es foral."""
    return HUSOS_PROVINCIA.get(str(codigo_provincia).zfill(2), ())


def epsg_recomendado(geometria, crs):
    """
    EPSG en el que debería ir el GML según la posición de la geometría: huso UTM 29, 30 o 31 de ETRS89,
    o 32628 en Canarias. None si no se puede calcular.
    """
    if geometria is None or geometria.isEmpty() or crs is None or not crs.isValid():
        return None
    destino = QgsCoordinateReferenceSystem('EPSG:4258')
    centro = QgsGeometry(geometria.centroid())
    if crs != destino:
        centro.transform(QgsCoordinateTransform(crs, destino, QgsProject.instance()))
    p = centro.asPoint()
    lon, lat = p.x(), p.y()
    if 27.0 <= lat <= 29.6 and -18.5 <= lon <= -13.0:
        return 32628
    huso = int(math.floor((lon + 180) / 6)) + 1
    return {29: 25829, 30: 25830, 31: 25831}.get(huso)


def transformar(geometria, crs_origen, epsg_destino):
    """Copia de la geometría transformada al EPSG de destino."""
    destino = QgsCoordinateReferenceSystem(f'EPSG:{epsg_destino}')
    copia = QgsGeometry(geometria)
    if crs_origen != destino:
        copia.transform(QgsCoordinateTransform(crs_origen, destino, QgsProject.instance()))
    return copia


def comprobar_src(crs, geometria=None, codigo_provincia=''):
    """Incidencias sobre el SRC de la capa: si es admitido por la Sede y si encaja con la posición o la provincia."""
    incidencias = []
    epsg = epsg_de(crs)
    if epsg not in SRC_ADMITIDOS:
        nombre = crs.authid() if crs is not None and crs.isValid() else 'desconocido'
        recomendado = epsg_recomendado(geometria, crs) if geometria is not None else None
        sugerencia = f"; se transformará a EPSG:{recomendado}" if recomendado else ''
        incidencias.append(Incidencia(AVISO, 'SRC-NO-ADMITIDO',
                                      f"El SRC {nombre} no lo admite la Sede (25829, 25830, 25831 o 32628){sugerencia}"))
        return incidencias
    husos = husos_provincia(codigo_provincia) if codigo_provincia else ()
    if husos and epsg not in husos:
        incidencias.append(Incidencia(AVISO, 'SRC-PROVINCIA',
                                      f"EPSG:{epsg} no es el huso de la provincia {codigo_provincia} "
                                      f"({', '.join(map(str, husos))})"))
    elif geometria is not None:
        recomendado = epsg_recomendado(geometria, crs)
        if recomendado and recomendado != epsg and not (husos and epsg in husos):
            incidencias.append(Incidencia(AVISO, 'SRC-HUSO',
                                          f"La geometría cae en el huso de EPSG:{recomendado}, no en el de EPSG:{epsg}"))
    return incidencias
