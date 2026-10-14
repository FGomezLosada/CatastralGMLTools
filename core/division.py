"""
División de una parcela con linderos paralelos (o perpendiculares) a uno de sus lados, como la división automática del
editor parcelario de la Sede (auditoría ED-01, AU-54; mejoras 22 y 23):

  partes       n parcelas de la misma superficie (como mucho 100, el límite del editor)
  porcentajes  «40 30 30»; si suman menos de 100, la diferencia es una parcela más al final; si suman más, error
  superficies  «200 150» (m²); lo que sobre es una parcela más al final; si suman más que la parcela, error
  cuotas       proporciones: «10 10 20» es lo mismo que «1 1 2»
  franjas      anchos en metros medidos en perpendicular a los linderos: «5 5»; lo que sobra es una parcela más

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
MAX_PARTES = 100          #Límite del editor de la Sede
PRECISION_AREA = 1e-4     #m²: la bisección para a menos de 1 cm² de la superficie pedida
RESTO_MINIMO = 0.5        #m²: un resto menor no da otra parcela (se suma a la última)


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


def dividir(geometria, modo, valores, lado=0, perpendicular=False, invertir=False):
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
    incidencias = []
    for i, pieza in enumerate(piezas, start=1):
        if pieza.isMultipart() and len(pieza.asGeometryCollection()) > 1:
            incidencias.append(Incidencia(AVISO, 'DIV-PARTES', f"La parcela {i} queda en {len(pieza.asGeometryCollection())} "
                                                               "trozos (la forma de la parcela no permite un lindero "
                                                               "recto en esa dirección): pruebe con otro lado"))
    return piezas, incidencias
