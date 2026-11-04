"""
División de una parcela con linderos paralelos (o perpendiculares) a uno de sus lados, como la división automática del
editor parcelario de la Sede (auditoría ED-01, AU-54; mejoras 22 y 23):

  partes       n parcelas de la misma superficie (como mucho 100, el límite del editor)
  porcentajes  «40 30 30»; si suman menos de 100, la diferencia es una parcela más al final; si suman más, error
  superficies  «200 150» (m²); lo que sobre es una parcela más al final; si suman más que la parcela, error
  cuotas       proporciones: «10 10 20» es lo mismo que «1 1 2»
  franjas      anchos en metros medidos en perpendicular a los linderos: «5 5»; lo que sobra es una parcela más

Con pivote (mejora 23), los linderos salen todos de un vértice de la parcela, en abanico, girando desde uno de los lados
que llegan a él: «40» deja un 40 % junto a ese lado y el resto al otro (sin franjas: no tienen sentido en abanico).

Las parcelas salen en orden desde el lado elegido (o desde el opuesto). Cada lindero nuevo se busca por bisección hasta
que la superficie quede a menos de 1 cm² de la pedida. La división no redondea: las coordenadas van al centímetro al
escribir el GML (y los vértices sobre el contorno se ajustan a él, AU-61).

Sin interfaz.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import math
import re

from qgis.core import QgsGeometry, QgsPointXY

from .incidencias import AVISO, ERROR, Incidencia

PARTES = 'partes'
PORCENTAJES = 'porcentajes'
SUPERFICIES = 'superficies'
CUOTAS = 'cuotas'
FRANJAS = 'franjas'
MODOS = (PARTES, PORCENTAJES, SUPERFICIES, CUOTAS, FRANJAS)
NOMBRES = {PARTES: "Partes iguales", PORCENTAJES: "Porcentajes (%)", SUPERFICIES: "Superficies (m²)",
           CUOTAS: "Cuotas (proporciones)", FRANJAS: "Franjas de ancho fijo (m)"}
EJEMPLOS = {PARTES: "3", PORCENTAJES: "40 30 30", SUPERFICIES: "200 150", CUOTAS: "1 1 2", FRANJAS: "5 5"}
#Qué escribir en cada modo (se ve siempre debajo de «Valores»: prueba a mano del 14/10, no se adivinaba que se pueden
#poner uno o varios porcentajes)
AYUDAS = {PARTES: "Cuántas parcelas de la misma superficie (de 2 a 100). Ej.: «3».",
          PORCENTAJES: "Uno o varios % separados por espacios, sin pasar de 100 en total. Lo que falte hasta 100 es "
                       "otra parcela: «30» da 30 % + 70 %; «40 30 30», tres parcelas.",
          SUPERFICIES: "Uno o varios m² separados por espacios. Lo que sobre es otra parcela: «200» da 200 m² + el "
                       "resto; «200 150», tres parcelas.",
          CUOTAS: "Proporciones separadas por espacios: «1 1 2» da 25 % + 25 % + 50 %.",
          FRANJAS: "Anchos en metros, medidos desde el lado elegido y separados por espacios. Lo que sobre es otra "
                   "parcela: «5 5» da dos franjas de 5 m + el resto."}
MAX_PARTES = 100          #Límite del editor de la Sede
PRECISION_AREA = 1e-4     #m²: la bisección para a menos de 1 cm² de la superficie pedida
RESTO_MINIMO = 0.5        #m²: un resto menor no da otra parcela (se suma a la última)
#m²: un trozo suelto menor pasa a la parcela vecina con la que linda (prueba a mano del 04/11/2026: los vértices casi
#alineados de un lindero real dejaban astillas de mm²)
ASTILLA = 0.05


def lados(geometria):
    """Lados del contorno exterior: lista de (QgsPointXY inicio, QgsPointXY fin, longitud en m, azimut en grados)."""
    poligono = geometria.asMultiPolygon()[0] if geometria.isMultipart() else geometria.asPolygon()
    if not poligono:
        return []
    anillo = poligono[0]
    resultado = []
    for a, b in zip(anillo, anillo[1:]):
        largo = math.hypot(b.x() - a.x(), b.y() - a.y())
        if largo > 1e-6:
            azimut = math.degrees(math.atan2(b.x() - a.x(), b.y() - a.y())) % 360
            resultado.append((QgsPointXY(a), QgsPointXY(b), largo, azimut))
    return resultado


def leer_valores(texto):
    """Números de «40 30 30», «40;30;30» o «12,5 7,5» (coma decimal); ValueError si hay algo que no es un número."""
    trozos = [t for t in re.split(r'[\s;]+', (texto or '').strip()) if t]
    if len(trozos) == 1 and trozos[0].count(',') > 1:  #«40,30,30»: comas como separador
        trozos = trozos[0].split(',')
    return [float(t.replace(',', '.')) for t in trozos]


def objetivos(modo, valores, total):
    """
    Superficies (m²) de cada parcela resultante, en orden, según el modo. Devuelve (lista, incidencias); con un error,
    lista vacía.
    """
    error = []
    if not valores:
        return [], [Incidencia(ERROR, 'DIV-VALORES', f"Escriba los valores (p. ej. «{EJEMPLOS[modo]}»)")]
    if any(v <= 0 for v in valores):
        return [], [Incidencia(ERROR, 'DIV-VALORES', "Los valores deben ser mayores que cero")]
    if modo == PARTES:
        n = valores[0]
        if len(valores) != 1 or n != int(n) or n < 2:
            error = [Incidencia(ERROR, 'DIV-VALORES', "Indique cuántas partes: un número entero de 2 o más")]
        elif n > MAX_PARTES:
            error = [Incidencia(ERROR, 'DIV-MAXIMO', f"Como mucho {MAX_PARTES} partes (límite del editor de la Sede)")]
        return ([], error) if error else ([total / int(n)] * int(n), [])
    if modo == CUOTAS:
        suma = sum(valores)
        return [total * v / suma for v in valores], []
    if modo == PORCENTAJES:
        suma = sum(valores)
        if suma > 100 + 1e-9:
            return [], [Incidencia(ERROR, 'DIV-SUMA', f"Los porcentajes suman {suma:g} %: no pueden pasar de 100")]
        areas = [total * v / 100 for v in valores]
    elif modo == SUPERFICIES:
        suma = sum(valores)
        if suma > total + RESTO_MINIMO:
            return [], [Incidencia(ERROR, 'DIV-SUMA', f"Las superficies suman {suma:.2f} m² y la parcela tiene {total:.2f} m²")]
        areas = list(valores)
    else:
        return [], [Incidencia(ERROR, 'DIV-MODO', f"Modo de división desconocido: {modo}")]
    resto = total - sum(areas)
    if resto > RESTO_MINIMO:
        areas.append(resto)  #Regla del editor: lo que falta es una parcela más al final
    elif areas:
        areas[-1] += resto
    return areas, []


def _semiplano(origen, direccion, normal, t, alcance):
    """Polígono enorme con los puntos p tales que (p - origen)·normal ≤ t (el lado «de antes» del lindero t)."""
    cx, cy = origen.x() + normal[0] * t, origen.y() + normal[1] * t
    dx, dy = direccion[0] * alcance, direccion[1] * alcance
    nx, ny = normal[0] * alcance, normal[1] * alcance
    puntos = [QgsPointXY(cx - dx, cy - dy), QgsPointXY(cx + dx, cy + dy), QgsPointXY(cx + dx - nx, cy + dy - ny),
              QgsPointXY(cx - dx - nx, cy - dy - ny)]
    return QgsGeometry.fromPolygonXY([puntos + [puntos[0]]])


def _absorber_astillas(piezas):
    """
    Los trozos sueltos minúsculos (menos de ASTILLA m²) que deja un lindero al pasar rozando un entrante de pocos
    centímetros pasan a la parcela con la que lindan más (las superficies cambian menos de lo que redondea la Sede); los
    de superficie nula se quitan. Los trozos grandes se quedan: se avisa de ellos (DIV-PARTES).
    """
    piezas = [QgsGeometry(p) for p in piezas]
    for i, pieza in enumerate(piezas):
        partes = [q for q in pieza.asGeometryCollection() if q.area() > 1e-8] if pieza.isMultipart() else [pieza]
        if len(partes) <= 1:
            piezas[i] = partes[0] if partes else pieza
            continue
        partes.sort(key=lambda q: -q.area())
        quedan = [partes[0]]
        for trozo in partes[1:]:
            vecina, mejor = None, 1e-6
            if trozo.area() < ASTILLA:
                for j, otra in enumerate(piezas):
                    if j != i:
                        comun = trozo.intersection(otra).length()
                        if comun > mejor:
                            vecina, mejor = j, comun
            if vecina is None:
                quedan.append(trozo)
            else:
                piezas[vecina] = QgsGeometry.unaryUnion([piezas[vecina], trozo])
        piezas[i] = quedan[0] if len(quedan) == 1 else QgsGeometry.collectGeometry(quedan)
    return piezas


VERTICES_JUNTOS = 0.02    #m: dos vértices a menos de esto (tras redondear al cm, el mismo o un lado de 1 cm) se unen


def _unir_vertices_cercanos(piezas, original):
    """
    Los vértices a menos de VERTICES_JUNTOS se convierten en uno (el de la parcela original, si lo hay), igual en todas
    las piezas para que los linderos comunes sigan casando: un lindero que acaba a milímetros de un vértice dejaba un
    lado de 5 mm o 1 cm (prueba a mano del 04/11/2026). Si alguna pieza no quedara válida o cambiara de superficie más
    de ASTILLA, se dejan todas como estaban.
    """
    fijos = [QgsPointXY(v.x(), v.y()) for v in original.vertices()]
    representantes = list(fijos)

    exactos = {(round(v.x(), 9), round(v.y(), 9)): v for v in fijos}

    def representante(punto):
        if (round(punto.x(), 9), round(punto.y(), 9)) in exactos:  #Los de la original no se mueven nunca
            return exactos[(round(punto.x(), 9), round(punto.y(), 9))]
        for r in representantes:
            if abs(r.x() - punto.x()) < VERTICES_JUNTOS and abs(r.y() - punto.y()) < VERTICES_JUNTOS \
                    and math.hypot(r.x() - punto.x(), r.y() - punto.y()) < VERTICES_JUNTOS:
                return r
        representantes.append(QgsPointXY(punto))
        return representantes[-1]

    def anillo(puntos):
        nuevo = []
        for punto in puntos:
            r = representante(punto)
            if not nuevo or nuevo[-1] != r:
                nuevo.append(r)
        if len(nuevo) > 1 and nuevo[0] != nuevo[-1]:
            nuevo.append(nuevo[0])
        return nuevo

    resultado = []
    for pieza in piezas:
        poligonos = pieza.asMultiPolygon() if pieza.isMultipart() else [pieza.asPolygon()]
        nuevos = [[anillo(a) for a in poligono] for poligono in poligonos if poligono]
        nuevos = [p for p in ([a for a in p if len(a) >= 4] for p in nuevos) if p]
        if not nuevos:
            return piezas
        geometria = QgsGeometry.fromMultiPolygonXY(nuevos) if len(nuevos) > 1 else QgsGeometry.fromPolygonXY(nuevos[0])
        if not geometria.isGeosValid() or abs(geometria.area() - pieza.area()) >= ASTILLA:
            return piezas  #Todas o ninguna: si no, los linderos comunes dejarían de casar
        resultado.append(geometria)
    if abs(sum(g.area() for g in resultado) - original.area()) > 0.01:
        return piezas
    return resultado


def _cuna(pivote, angulo_inicio, barrido, alcance):
    """Cuña desde el pivote: del ángulo de inicio (radianes) girando «barrido» (con signo), con radio «alcance»."""
    pasos = max(2, int(abs(barrido) / (math.pi / 12)) + 2)
    puntos = [QgsPointXY(pivote)]
    for k in range(pasos + 1):
        ang = angulo_inicio + barrido * k / pasos
        puntos.append(QgsPointXY(pivote.x() + alcance * math.cos(ang), pivote.y() + alcance * math.sin(ang)))
    puntos.append(QgsPointXY(pivote))
    return QgsGeometry.fromPolygonXY([puntos])


def dividir_pivote(geometria, metas, vertice, invertir=False):
    """
    Linderos en abanico desde un vértice: las parcelas, en orden desde el lado que sale del vértice (o desde el que llega,
    con invertir). metas: superficies en m². Devuelve (piezas, incidencias).
    """
    anillo = [a for a, _, _, _ in lados(geometria)]  #Sin vértices repetidos: el índice es el mismo que en lados()
    n = len(anillo)
    p, siguiente, anterior = anillo[vertice % n], anillo[(vertice + 1) % n], anillo[(vertice - 1) % n]
    a_sig = math.atan2(siguiente.y() - p.y(), siguiente.x() - p.x())
    a_ant = math.atan2(anterior.y() - p.y(), anterior.x() - p.x())
    barrido = (a_ant - a_sig) % (2 * math.pi)  #Giro antihorario de un lado al otro
    caja = geometria.boundingBox()
    alcance = 10 * max(caja.width(), caja.height(), 1.0)
    medio = a_sig + barrido / 2
    prueba = QgsGeometry.fromPointXY(QgsPointXY(p.x() + 0.01 * math.cos(medio), p.y() + 0.01 * math.sin(medio)))
    if not geometria.contains(prueba):  #El interior está girando hacia el otro lado
        barrido = barrido - 2 * math.pi
    inicio = a_sig
    if invertir:
        inicio, barrido = a_ant, -barrido

    def area_hasta(giro):
        return geometria.intersection(_cuna(p, inicio, giro, alcance)).area()

    giros, acumulada = [], 0.0
    for meta in metas[:-1]:
        acumulada += meta
        b_bajo, b_alto = (giros[-1] if giros else 0.0), barrido
        for _ in range(200):
            mitad = (b_bajo + b_alto) / 2
            diferencia = area_hasta(mitad) - acumulada
            if abs(diferencia) < PRECISION_AREA:
                break
            #El área crece con el giro, sea cual sea su signo
            b_bajo, b_alto = (mitad, b_alto) if diferencia < 0 else (b_bajo, mitad)
        giros.append(mitad)
    piezas, desde, resto = [], 0.0, QgsGeometry(geometria)
    for giro, meta in zip(giros, metas):
        cuna = _cuna(p, inicio + desde, giro - desde, alcance)
        pieza = resto.intersection(cuna)
        if abs(pieza.area() - meta) > PRECISION_AREA * 10:
            return [], [Incidencia(ERROR, 'DIV-PIVOTE-ALCANCE', f"Desde el vértice {vertice + 1} no se llega a la "
                                                                f"superficie pedida para la parcela {len(piezas) + 1} "
                                                                "(parte de la parcela no se ve desde él): pruebe con otro "
                                                                "vértice")]
        piezas.append(pieza)
        resto = resto.difference(cuna)
        desde = giro
    #La última: todo lo que queda, también lo que no se ve desde el vértice (en una U, el otro brazo)
    piezas.append(resto)
    piezas = _unir_vertices_cercanos(_absorber_astillas(piezas), geometria)
    incidencias = []
    for i, pieza in enumerate(piezas, start=1):
        if pieza.isMultipart() and len(pieza.asGeometryCollection()) > 1:
            incidencias.append(Incidencia(AVISO, 'DIV-PARTES', f"La parcela {i} queda en {len(pieza.asGeometryCollection())} "
                                                               "trozos (desde ese vértice no se ve toda la parcela): "
                                                               "pruebe con otro vértice"))
    return piezas, incidencias


def dividir(geometria, modo, valores, lado=0, perpendicular=False, invertir=False, pivote=False):
    """
    Divide la geometría (polígono, en un SRC proyectado) en parcelas con linderos paralelos al lado indicado (índice en
    lados(); con perpendicular=True, perpendiculares a él). Devuelve (lista de QgsGeometry en orden, incidencias).
    """
    if geometria is None or geometria.isNull() or geometria.isEmpty():
        return [], [Incidencia(ERROR, 'DIV-GEOMETRIA', "Elija una parcela con geometría")]
    if geometria.isMultipart() and len(geometria.asGeometryCollection()) > 1:
        return [], [Incidencia(ERROR, 'DIV-MULTIPARTE', "La parcela tiene varias partes: divida cada una por separado")]
    todos = lados(geometria)
    if not 0 <= lado < len(todos):
        return [], [Incidencia(ERROR, 'DIV-LADO', "Elija un lado de la parcela")]
    total = geometria.area()
    if pivote:  #lado es el índice del vértice (el inicio de ese lado)
        if modo == FRANJAS:
            return [], [Incidencia(ERROR, 'DIV-PIVOTE', "Con pivote no hay franjas de ancho fijo: elija superficies, "
                                                        "porcentajes, partes o cuotas")]
        metas, inc = objetivos(modo, valores, total)
        if not metas:
            return [], inc
        return dividir_pivote(geometria, metas, lado, invertir)
    if modo == FRANJAS:
        if not valores or any(v <= 0 for v in valores):
            return [], [Incidencia(ERROR, 'DIV-VALORES', f"Escriba los anchos en metros (p. ej. «{EJEMPLOS[FRANJAS]}»)")]
        metas = None
    else:
        metas, inc = objetivos(modo, valores, total)
        if not metas:
            return [], inc
    a, b, largo, _ = todos[lado]
    ux, uy = (b.x() - a.x()) / largo, (b.y() - a.y()) / largo
    direccion, normal = ((ux, uy), (-uy, ux)) if not perpendicular else ((-uy, ux), (ux, uy))
    #Recorrido de la normal sobre la parcela: los linderos se buscan entre tmin y tmax
    proyecciones = [(v.x() - a.x()) * normal[0] + (v.y() - a.y()) * normal[1] for v in geometria.vertices()]
    tmin, tmax = min(proyecciones), max(proyecciones)
    if invertir:  #Desde el otro extremo: se invierte la normal
        normal = (-normal[0], -normal[1])
        tmin, tmax = -tmax, -tmin
    caja = geometria.boundingBox()
    alcance = 10 * max(caja.width(), caja.height(), 1.0)

    def area_hasta(t):
        return geometria.intersection(_semiplano(a, direccion, normal, t, alcance)).area()

    cortes = []
    if metas is None:  #Franjas: cada lindero a una distancia fija del anterior
        t = tmin
        for ancho in valores:
            t += ancho
            if t >= tmax - 1e-6:
                return [], [Incidencia(ERROR, 'DIV-SUMA', f"Las franjas suman {sum(valores):g} m y la parcela mide "
                                                          f"{tmax - tmin:.2f} m en esa dirección")]
            cortes.append(t)
    else:
        acumulada = 0.0
        for meta in metas[:-1]:
            acumulada += meta
            bajo, alto = (cortes[-1] if cortes else tmin), tmax
            for _ in range(200):
                medio = (bajo + alto) / 2
                diferencia = area_hasta(medio) - acumulada
                if abs(diferencia) < PRECISION_AREA:
                    break
                bajo, alto = (medio, alto) if diferencia < 0 else (bajo, medio)
            cortes.append(medio)
    piezas, resto = [], QgsGeometry(geometria)
    for t in cortes:
        semiplano = _semiplano(a, direccion, normal, t, alcance)
        piezas.append(resto.intersection(semiplano))
        resto = resto.difference(semiplano)
    piezas.append(resto)
    piezas = _unir_vertices_cercanos(_absorber_astillas(piezas), geometria)
    incidencias = []
    for i, pieza in enumerate(piezas, start=1):
        if pieza.isMultipart() and len(pieza.asGeometryCollection()) > 1:
            incidencias.append(Incidencia(AVISO, 'DIV-PARTES', f"La parcela {i} queda en {len(pieza.asGeometryCollection())} "
                                                               "trozos (la forma de la parcela no permite un lindero "
                                                               "recto en esa dirección): pruebe con otro lado"))
    return piezas, incidencias


MAX_VERTICES_SUGERENCIA = 60  #Con más vértices no se prueban todos (sería lento al escribir los valores)
MAX_PRUEBAS_SUGERENCIA = 400  #Vértices × parcelas: más, y la vista previa tardaría


def vertices_sin_trozos(geometria, modo, valores, invertir=False):
    """
    Índices de los vértices desde los que el pivote da todas las parcelas de una pieza (para sugerirlos cuando el
    elegido deja alguna en varios trozos). None si la parcela tiene demasiados vértices para probarlos todos.
    """
    todos = lados(geometria)
    metas, _ = objetivos(modo, valores, geometria.area()) if modo != FRANJAS else ([], [])
    if not metas or len(todos) > MAX_VERTICES_SUGERENCIA or len(todos) * len(metas) > MAX_PRUEBAS_SUGERENCIA:
        return None
    buenos = []
    for v in range(len(todos)):
        piezas, inc = dividir(geometria, modo, valores, v, False, invertir, True)
        if piezas and not any(i.nivel == ERROR or i.codigo == 'DIV-PARTES' for i in inc):
            buenos.append(v)
    return buenos
