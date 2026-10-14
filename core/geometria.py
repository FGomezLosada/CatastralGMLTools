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
    QgsCsException,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsSpatialIndex,
    QgsWkbTypes,
)

from .incidencias import AVISO, ERROR, INFO, Incidencia

DECIMALES = 2
FLECHA_MAXIMA = 0.015  #Metros. Menor que los 2 cm exigidos, con margen para el redondeo al centímetro
SRC_ADMITIDOS = (25829, 25830, 25831, 32628)
MINIMO_VERTICES = 4  #Incluido el de cierre

#Husos por provincia (código INE de 2 dígitos = código de provincia del Catastro).
#Fuente: tabla del documento «Preguntas y respuestas acerca de la coordinación Catastro-Registro» (DGC).
#Girona, Las Palmas y Melilla, confirmadas en el texto de la FAQ (auditoría, X-22).
HUSOS_PROVINCIA = {
    '02': (25830,), '03': (25830, 25831), '04': (25830,), '05': (25830,), '06': (25829, 25830), '07': (25831,),
    '08': (25831,), '09': (25830,), '10': (25829, 25830), '11': (25829, 25830), '12': (25830, 25831), '13': (25830,),
    '14': (25830,), '15': (25829,), '16': (25830,), '17': (25831,),
    '18': (25830,), '19': (25830,), '21': (25829,), '22': (25830, 25831), '23': (25830,), '24': (25829, 25830),
    '25': (25831,), '26': (25830,), '27': (25829,), '28': (25830,), '29': (25830,), '30': (25830,), '32': (25829,),
    '33': (25829, 25830), '34': (25830,), '35': (32628,),
    '36': (25829,), '37': (25829, 25830), '38': (32628,), '39': (25830,), '40': (25830,), '41': (25829, 25830),
    '42': (25830,), '43': (25831,), '44': (25830, 25831), '45': (25830,), '46': (25830,), '47': (25830,),
    '49': (25829, 25830), '50': (25830, 25831), '51': (25830,), '52': (25830,),
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


def degenerado(anillo):
    """
    True si el anillo (cerrado) no encierra superficie: menos de 3 vértices distintos o todos alineados. La Sede pide
    al menos 4 vértices (con el de cierre) que no estén alineados (asistente gráfico, casos de uso 4 y 5; AU-27).
    """
    distintos = set(map(tuple, anillo))
    if len(distintos) < 3:
        return True
    (x0, y0) = anillo[0]
    xf, yf = max(distintos, key=lambda p: (p[0] - x0) ** 2 + (p[1] - y0) ** 2)
    largo = math.hypot(xf - x0, yf - y0)
    #Alineados: ningún vértice se separa medio centímetro de la recta entre los dos más alejados (una «pajarita» no lo
    #está, aunque su área con signo sea 0: esa es una autointersección)
    return largo < 0.005 or max(abs((xf - x0) * (y - y0) - (yf - y0) * (x - x0)) / largo for x, y in distintos) < 0.005


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


def preparar(geometria, elemento='', area_entera=True):
    """
    Convierte una geometría de polígono en la lista de Recinto que irá al GML, con sus incidencias.
    Una geometría multiparte da varios recintos y una incidencia (cada parte debe ser una parcela distinta).
    Devuelve (recintos, incidencias).
    """
    incidencias = []
    if geometria is None:
        return [], [Incidencia(ERROR, 'GEO-SRC', "No se ha podido pasar al SRC del GML: las coordenadas no encajan con el "
                                                 "SRC de la capa (revíselo en sus propiedades, pestaña Fuente)", elemento)]
    if geometria.isNull() or geometria.isEmpty():
        return [], [Incidencia(ERROR, 'GEO-VACIA', "La geometría está vacía", elemento)]
    if not finita(geometria):
        return [], [Incidencia(ERROR, 'GEO-SRC', "Coordenadas no válidas (infinitas): revise el SRC de la capa", elemento)]
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
            if degenerado(anillo):
                incidencias.append(Incidencia(ERROR, 'GEO-ALINEADOS', "Un anillo no encierra superficie (sus vértices están "
                                                                      "alineados): la Sede no lo admite", elemento))
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
        #La parcela declara su superficie en m² enteros; el edificio no lleva superficie (basta con que no sea nula, AU-18)
        if (recinto.area_m2() if area_entera else recinto.area()) <= 0:
            incidencias.append(Incidencia(ERROR, 'GEO-AREA', "La superficie es 0 m²", elemento))
    return recintos, incidencias


SOLAPE_MINIMO = 0.01  #m: un solape más estrecho que 1 cm entra en la tolerancia de la Sede (±1 cm)


def solapes(geometrias):
    """
    Solapes entre geometrías (lista de QgsGeometry): [(i, j, superficie, anchura)]. Cuenta la anchura del solape
    (diámetro del mayor círculo que cabe en él), no solo su superficie: una franja de 3 cm × 1 m es un solape aunque
    mida 0,03 m² (auditoría AU-11, AU-40).
    """
    resultado = []
    validas = {i: v for i, v in ((i, poligonal(g)) for i, g in enumerate(geometrias)) if v is not None}
    #Índice espacial: solo se cruzan las que se tocan por la caja (con miles de parcelas no se prueban todas con todas)
    indice = QgsSpatialIndex()
    for i, g in validas.items():
        indice.addFeature(i, g.boundingBox())
    for i, a in validas.items():
        motor = None
        for j in sorted(indice.intersects(a.boundingBox())):
            if j <= i:
                continue
            b = validas[j]
            if motor is None:
                motor = QgsGeometry.createGeometryEngine(a.constGet())
                motor.prepareGeometry()
            if not motor.intersects(b.constGet()):
                continue
            comun = a.intersection(b)
            if comun.isEmpty() or comun.area() <= 1e-6:
                continue
            anchura = anchura_maxima(comun)
            if anchura > SOLAPE_MINIMO:
                resultado.append((i, j, comun.area(), anchura))
    return resultado


ALINEADO = 0.001      #m: un vértice a menos de 1 mm de la recta entre sus vecinos está «sobre el lindero» (no es esquina)
LINDERO_AVISO = 0.005  #m: aviso si, aun así, un vértice nuevo queda a más de 0,5 cm del lindero tras redondear


def _distancia_recta(p, a, b):
    """Distancia del punto p al segmento ab (tuplas x, y)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    largo2 = dx * dx + dy * dy
    if largo2 == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / largo2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _clave(x, y):
    return round(x, 6), round(y, 6)


def ajustar_a_lindero(geometrias):
    """
    Vértices que caen sobre un lindero recto del conjunto (p. ej. donde la línea de una división corta el contorno de la
    parcela): al redondear al centímetro podían quedar hasta 0,7 cm fuera del lindero. Se elige, de los cuatro puntos de
    la rejilla de 1 cm que lo rodean, el más cercano a la recta entre las esquinas (ya redondeadas) de ese lindero; todas
    las parcelas que comparten el vértice reciben el mismo punto (AU-61).
    Devuelve (geometrías ajustadas, distancia máxima en m de un vértice ajustado a su lindero).
    """
    validas = [g for g in geometrias if g is not None and not g.isNull() and not g.isEmpty()
               and QgsWkbTypes.geometryType(g.wkbType()) == Qgis.GeometryType.Polygon and not tiene_curvas(g)]
    if not validas:
        return list(geometrias), 0.0
    union = QgsGeometry.unaryUnion(validas)
    poligonos = union.asMultiPolygon() if union.isMultipart() else [union.asPolygon()]
    paso = 10 ** -DECIMALES
    cambios, peor = {}, 0.0
    for poligono in poligonos:
        for anillo in poligono:
            puntos = [(p.x(), p.y()) for p in anillo[:-1]]
            n = len(puntos)
            if n < 4:
                continue
            esquina = [_distancia_recta(puntos[i], puntos[i - 1], puntos[(i + 1) % n]) > ALINEADO for i in range(n)]
            if not any(esquina):
                continue
            for i in range(n):
                if esquina[i]:
                    continue
                a = next(puntos[(i - k) % n] for k in range(1, n) if esquina[(i - k) % n])
                b = next(puntos[(i + k) % n] for k in range(1, n) if esquina[(i + k) % n])
                a, b = (redondear(a[0]), redondear(a[1])), (redondear(b[0]), redondear(b[1]))
                x, y = puntos[i]
                x0, y0 = math.floor(x / paso) * paso, math.floor(y / paso) * paso
                candidatos = [(round(x0 + dx * paso, DECIMALES), round(y0 + dy * paso, DECIMALES))
                              for dx in (0, 1) for dy in (0, 1)]
                elegido = min(candidatos, key=lambda c: (_distancia_recta(c, a, b), math.hypot(c[0] - x, c[1] - y)))
                cambios[_clave(x, y)] = elegido
                peor = max(peor, _distancia_recta(elegido, a, b))
    if not cambios:
        return list(geometrias), 0.0

    def mover(punto):
        nuevo = cambios.get(_clave(punto.x(), punto.y()))
        return QgsPointXY(*nuevo) if nuevo else QgsPointXY(punto)

    resultado = []
    for g in geometrias:
        if g is None or not any(g is v for v in validas):
            resultado.append(g)
            continue
        multi = g.asMultiPolygon() if g.isMultipart() else [g.asPolygon()]
        partes = [[[mover(p) for p in anillo] for anillo in poligono] for poligono in multi if poligono]
        resultado.append(QgsGeometry.fromPolygonXY(partes[0]) if not g.isMultipart()
                         else QgsGeometry.fromMultiPolygonXY(partes))
    return resultado, peor


def zonas(geometrias, separacion=0.01):
    """
    Grupos de geometrías que se tocan (a menos de «separacion» m): lista de (unión de la zona, índices de sus
    geometrías). Un GML con varias zonas son varias operaciones en un fichero (p. ej. una multiparcela).
    """
    validas = [(i, g) for i, g in enumerate(geometrias) if g is not None and not g.isNull() and not g.isEmpty()]
    if not validas:
        return []
    union = QgsGeometry.unaryUnion([g.buffer(separacion / 2, 2) for _, g in validas])
    partes = union.asGeometryCollection() if union.isMultipart() else [union]
    return [(parte, [i for i, g in validas if g.intersects(parte)]) for parte in partes]


def truncar(geometria, decimales=DECIMALES):
    """
    Copia de un polígono o multipolígono con las coordenadas truncadas (no redondeadas) a 2 decimales, como hace la Sede
    con un GML que trae más (documento de validación v2.1; AU-29).
    """
    factor = 10 ** decimales

    def t(v):
        return math.trunc(v * factor) / factor

    multi = geometria.asMultiPolygon() if geometria.isMultipart() else [geometria.asPolygon()]
    partes = [[[QgsPointXY(t(p.x()), t(p.y())) for p in anillo] for anillo in poligono] for poligono in multi if poligono]
    if not partes:
        return QgsGeometry(geometria)
    return QgsGeometry.fromPolygonXY(partes[0]) if len(partes) == 1 else QgsGeometry.fromMultiPolygonXY(partes)


def poligonal(geometria):
    """
    La geometría válida y solo con sus partes de superficie (makeValid puede devolver colecciones con líneas o puntos),
    o None si no queda nada. Para operar sin excepciones con geometrías de ficheros ajenos.
    """
    if geometria is None or geometria.isNull() or geometria.isEmpty():
        return None
    g = geometria if geometria.isGeosValid() else geometria.makeValid()
    if g.isNull() or g.isEmpty():
        return None
    partes = [p for p in (g.asGeometryCollection() if g.isMultipart() or g.type() != Qgis.GeometryType.Polygon else [g])
              if QgsWkbTypes.geometryType(p.wkbType()) == Qgis.GeometryType.Polygon and p.area() > 0]
    if not partes:
        return None
    return partes[0] if len(partes) == 1 else QgsGeometry.unaryUnion(partes)


def anchura_maxima(geometria):
    """Diámetro del mayor círculo inscrito en una geometría poligonal (0 si no es de superficie)."""
    partes = geometria.asGeometryCollection() if geometria.isMultipart() else [geometria]
    mayor = 0.0
    for parte in partes:
        if QgsWkbTypes.geometryType(parte.wkbType()) != Qgis.GeometryType.Polygon or parte.area() <= 0:
            continue
        polo = parte.poleOfInaccessibility(0.001)
        if polo and polo[0] is not None:
            mayor = max(mayor, 2 * polo[1])
    return mayor


def huecos(geometrias, franja=0.5):
    """
    Superficie (m²) de los huecos entre parcelas contiguas: huecos cerrados (anillos interiores de la unión que no son
    patios de ninguna parcela) y franjas abiertas de menos de «franja» m de ancho que llegan al borde (AU-40).
    """
    validas = [v for v in (poligonal(g) for g in geometrias) if v is not None]
    if len(validas) < 2:
        return 0.0
    union = QgsGeometry.unaryUnion(validas)
    poligonos = union.asMultiPolygon() if union.isMultipart() else [union.asPolygon()]
    #Los patios propios de una parcela (que ninguna otra rellena) también son anillos interiores de la unión: se
    #reconocen por su geometría, no por cuántos hay (si no, un patio relleno y un hueco real se compensaban; AU-40)
    propios = [QgsGeometry.fromPolygonXY([anillo]) for g in validas
               for p in (g.asMultiPolygon() if g.isMultipart() else [g.asPolygon()]) for anillo in p[1:]]
    total = 0.0
    for p in poligonos:
        for anillo in p[1:]:
            hueco = QgsGeometry.fromPolygonXY([anillo])
            punto = hueco.pointOnSurface()
            if hueco.area() > 1e-4 and not any(abs(h.area() - hueco.area()) < 1e-3 and h.contains(punto) for h in propios):
                total += hueco.area()
    cierre = union.buffer(franja / 2, 8).buffer(-franja / 2, 8)  #Cierra las franjas estrechas abiertas al exterior
    abiertas = cierre.difference(union.buffer(0.001, 4))
    if not abiertas.isEmpty():
        cerrados_geom = [QgsGeometry.fromPolygonXY([anillo]) for p in poligonos for anillo in p[1:]]
        for g in cerrados_geom:  #Lo cerrado ya está contado
            abiertas = abiertas.difference(g)
        for pieza in (abiertas.asGeometryCollection() if abiertas.isMultipart() else [abiertas]):
            anchura = anchura_maxima(pieza)
            #Franja entre parcelas: alargada (no el redondeo de una esquina) y tocando al menos a dos de ellas
            if pieza.area() > 1e-3 and anchura > 0.001 and pieza.area() / anchura ** 2 > 8 \
                    and sum(1 for g in validas if g.distance(pieza) < 0.002) >= 2:
                total += pieza.area()
    return total


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


LIMITES_HUSO = {25829: (-12.0, -6.0), 25830: (-6.0, 0.0), 25831: (0.0, 6.0)}
MARGEN_HUSO = 1.5  #Grados fuera de su huso a partir de los que el SRC es claramente el de otra zona (AU-30)


def aviso_huso(geometria, crs, epsg, provincia=''):
    """
    Aviso si el GML va a ir en un huso que no corresponde a su posición o a su provincia (p. ej. una parcela de Galicia
    en EPSG:25830, o Baleares en 25830): la Sede lo rechazaría o la parcela quedaría desplazada. None si encaja.
    Con la provincia (de una RC de rústica) se usa la tabla de husos de la DGC; sin ella, solo se avisa cuando la
    posición queda claramente fuera del huso (más de 1,5° de su borde), para no confundir en provincias entre dos husos.
    """
    if geometria is None or geometria.isEmpty() or epsg not in SRC_ADMITIDOS or crs is None or not crs.isValid():
        return None
    husos = husos_provincia(provincia) if provincia else ()
    if husos:
        if epsg not in husos:
            return Incidencia(AVISO, 'SRC-PROVINCIA', f"EPSG:{epsg} no es el huso de la provincia {provincia} "
                                                      f"(EPSG:{', '.join(map(str, husos))})")
        return None
    destino = QgsCoordinateReferenceSystem('EPSG:4258')
    centro = QgsGeometry(geometria.centroid())
    try:
        if crs != destino:
            centro.transform(QgsCoordinateTransform(crs, destino, QgsProject.instance()))
    except QgsCsException:
        return None
    if not finita(centro):
        return None
    lon, lat = centro.asPoint().x(), centro.asPoint().y()
    canarias = 27.0 <= lat <= 29.6 and -18.5 <= lon <= -13.0
    if canarias != (epsg == 32628):
        recomendado = 32628 if canarias else epsg_recomendado(geometria, crs)
        return Incidencia(AVISO, 'SRC-HUSO', f"La geometría está en {'Canarias' if canarias else 'la Península o Baleares'}: "
                                             f"el GML debería ir en EPSG:{recomendado}, no en EPSG:{epsg}")
    if epsg in LIMITES_HUSO:
        oeste, este = LIMITES_HUSO[epsg]
        fuera = max(oeste - lon, lon - este, 0.0)
        if fuera > MARGEN_HUSO:
            return Incidencia(AVISO, 'SRC-HUSO', f"La geometría cae lejos del huso de EPSG:{epsg}: el GML debería ir en "
                                                 f"EPSG:{epsg_recomendado(geometria, crs)} (el huso de su provincia)")
    return None


ELIPSOIDES_ETRS89 = ('EPSG:7019', 'EPSG:7030')  #GRS80 (ETRS89, REGCAN95) y WGS84: entre ellos no hay desplazamiento


def aviso_datum(crs, epsg):
    """
    Aviso si la capa está en un datum antiguo (ED50, Madrid 1870…) y hay que transformarla al del GML: sin la rejilla
    oficial del IGN, QGIS usa una transformación aproximada que puede mover las coordenadas varios metros, mucho más que
    la tolerancia de la Sede (AU-32). None si no hace falta (ETRS89, REGCAN95 o WGS84: REGCAN95 y WGS84 en Canarias se
    tratan como el mismo, así que una capa en EPSG:4083 pasa a 32628 sin cambiar sus coordenadas).
    """
    if crs is None or not crs.isValid() or epsg_de(crs) == epsg or crs.ellipsoidAcronym() in ELIPSOIDES_ETRS89:
        return None
    return Incidencia(AVISO, 'SRC-DATUM', f"La capa está en {crs.authid()} ({crs.description()}), un datum distinto de "
                                          "ETRS89: la transformación puede desplazarla varios metros si QGIS no tiene la "
                                          "rejilla oficial del IGN. Mejor pase antes la capa a ETRS89 con la rejilla y "
                                          "compare el resultado con el Catastro")


def transformar(geometria, crs_origen, epsg_destino):
    """
    Copia de la geometría transformada al EPSG de destino, o None si no se puede transformar (coordenadas que no encajan
    con el SRC de la capa: p. ej. UTM en una capa marcada como EPSG:4326, AU-06). preparar(None) da el error GEO-SRC.
    """
    destino = QgsCoordinateReferenceSystem(f'EPSG:{epsg_destino}')
    copia = QgsGeometry(geometria)
    if crs_origen != destino and not copia.isNull():
        try:
            copia.transform(QgsCoordinateTransform(crs_origen, destino, QgsProject.instance()))
        except QgsCsException:
            return None
        if not finita(copia):
            return None
    return copia


def finita(geometria):
    """True si todas las coordenadas son números finitos (una transformación imposible da inf o nan)."""
    caja = geometria.boundingBox()
    return all(math.isfinite(v) for v in (caja.xMinimum(), caja.yMinimum(), caja.xMaximum(), caja.yMaximum()))


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
