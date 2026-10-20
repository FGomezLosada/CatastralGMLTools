"""
Parcela desde coordenadas (AU-57): lee el fichero de puntos de un levantamiento (TXT o CSV) y forma con ellos las
parcelas, que luego van a la pestaña Parcela como una capa (allí se eligen identificador, namespace y alteración, se
valida y se crea el GML).

Formatos que se leen (los habituales de las libretas y programas de topografía):
  - una línea por punto: X Y, o nombre/número X Y, con Z o un código detrás (se ignoran);
  - separados por espacios, tabuladores, punto y coma o comas; coma decimal (también con punto de millares si va
    separado por punto y coma o tabulador: «421.500,25;4.070.500,10»);
  - cabeceras, comentarios (#, //, ;) y líneas sin coordenadas se saltan y se dice cuáles;
  - varias parcelas: separadas por líneas en blanco, por una línea de título («Parcela 2», «P2:»…), o con una primera
    columna con el identificador de la parcela de cada punto (las filas de la misma parcela, seguidas).

Lo que no se puede deducir se dice y no se inventa: coordenadas que parecen grados, el orden Y X (se corrige, avisando,
solo cuando no hay duda), un contorno que se cruza (los puntos no van en orden), menos de 3 puntos distintos.
La orientación y el cierre del anillo no hacen falta en el fichero: los pone el escritor del GML.

Sin interfaz (la usa la utilidad «6.» de Utilidades).

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import math
import re
from dataclasses import dataclass, field

from qgis.core import QgsGeometry, QgsPointXY

from . import geometria as geo
from .incidencias import AVISO, ERROR, INFO, Incidencia

NUMERO = re.compile(r'^[-+]?(\d+([.,]\d+)?|\d{1,3}(\.\d{3})+(,\d+)?|\d{1,3}(,\d{3})+(\.\d+)?)$')
COMENTARIO = ('#', '//', '!', '*')
TITULO = re.compile(r'^\s*(parcela|finca|recinto|p|pol[ií]gono|lote)\b[\s._:-]*([\w.-]+)?\s*:?\s*$', re.IGNORECASE)
#Coordenadas UTM de España en metros (ETRS89 / REGCAN95): X entre ~150 000 y ~850 000; Y entre ~3 000 000 y ~4 900 000
X_UTM = (100000.0, 900000.0)
Y_UTM = (3000000.0, 4950000.0)
MAX_PUNTOS = 5000  #Por parcela: más es otra cosa (una nube de puntos)


@dataclass
class Punto:
    x: float
    y: float
    nombre: str = ''
    linea: int = 0


@dataclass
class ParcelaPuntos:
    identificador: str
    puntos: list = field(default_factory=list)
    geometria: object = None                         #QgsGeometry, si se ha podido formar
    incidencias: list = field(default_factory=list)


@dataclass
class Lectura:
    parcelas: list = field(default_factory=list)
    saltadas: list = field(default_factory=list)     #Números de línea que no son puntos
    incidencias: list = field(default_factory=list)  #Del fichero entero (codificación, orden Y X, grados…)


def decodificar(datos):
    """Texto del fichero: UTF-8 (con o sin BOM), o ISO-8859-1 / Windows-1252 (Excel y libretas antiguas)."""
    for codificacion in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            return datos.decode(codificacion)
        except UnicodeDecodeError:
            continue
    return datos.decode('latin-1', 'replace')


def numero(texto):
    """Número de un campo: «421500.25», «421500,25», «421.500,25», «421,500.25». None si no lo es."""
    texto = texto.strip()
    if not NUMERO.match(texto):
        return None
    if ',' in texto and '.' in texto:
        decimal = ',' if texto.rfind(',') > texto.rfind('.') else '.'
        texto = texto.replace('.' if decimal == ',' else ',', '').replace(decimal, '.')
    elif ',' in texto:
        texto = texto.replace(',', '.') if texto.count(',') == 1 else texto.replace(',', '')
    elif texto.count('.') > 1:
        texto = texto.replace('.', '')  #Puntos de millares
    try:
        return float(texto)
    except ValueError:
        return None


def campos(linea):
    """Los campos de una línea, con el separador que tenga (punto y coma, tabulador, coma o espacios)."""
    if ';' in linea:
        return [c.strip() for c in linea.split(';')]
    if '\t' in linea:
        return [c.strip() for c in linea.split('\t')]
    if linea.count(',') >= 2 and not re.search(r'\d,\d+\s+\d', linea):  #Comas como separador (no coma decimal + espacios)
        return [c.strip() for c in linea.split(',')]
    return linea.split()


def interpretar(partes):
    """
    (nombre, x, y) de los campos de una línea, o None si no tiene dos coordenadas. Las coordenadas son los dos primeros
    números de metros (de 1000 o más); lo que va delante es el nombre o número del punto, y lo de detrás (Z, código), se
    ignora. Si no hay números de metros (grados), los dos primeros números, o los dos siguientes a un número de punto.
    """
    valores = [numero(p) for p in partes]
    indices = [k for k, v in enumerate(valores) if v is not None]
    if len(indices) < 2:
        return None
    grandes = [k for k in indices if abs(valores[k]) >= 1000]
    if len(grandes) >= 2:
        i, j = grandes[0], grandes[1]
    elif len(indices) >= 3 and float(valores[indices[0]]).is_integer():
        i, j = indices[1], indices[2]  #Número de punto delante
    else:
        i, j = indices[0], indices[1]
    delante = [p for p in partes[:i] if p.strip()]
    return (delante[0] if delante else ''), valores[i], valores[j]


def leer(texto, columna_parcela=None):
    """
    Lee los puntos de un levantamiento. columna_parcela: True si la primera columna es el identificador de la parcela
    de cada punto; None para deducirlo (si hay varios valores que se repiten en filas seguidas y no son números de
    punto). Devuelve una Lectura.
    """
    resultado = Lectura()
    filas = []  #(línea, primer campo, x, y) o None para un separador (línea en blanco o título)
    titulos = {}
    for n, linea in enumerate(texto.splitlines(), start=1):
        limpia = linea.strip().strip('﻿')
        if not limpia:
            filas.append(None)
            continue
        if limpia.startswith(COMENTARIO):
            continue
        titulo = TITULO.match(limpia)
        if titulo and not any(numero(p) is not None and abs(numero(p)) >= 1000 for p in campos(limpia)):
            filas.append(None)
            titulos[len(filas)] = (titulo.group(2) or '').strip()
            continue
        punto = interpretar(campos(limpia))
        if punto is None:
            resultado.saltadas.append(n)
            continue
        filas.append((n, punto[0], punto[1], punto[2]))
    puntos = [f for f in filas if f is not None]
    if not puntos:
        resultado.incidencias.append(Incidencia(ERROR, 'COORD-SIN-PUNTOS', "El fichero no tiene líneas con coordenadas "
                                                                            "(X Y, o nombre X Y)"))
        return resultado

    #¿La primera columna dice a qué parcela va cada punto? (p. ej. «P1;421500;4070500»): pocos valores distintos, que se
    #repiten en filas seguidas; no si son números de punto (todos distintos)
    nombres = [f[1] for f in puntos]
    if columna_parcela is None:
        distintos = len(set(nombres))
        columna_parcela = bool(nombres[0]) and 1 < distintos < len(nombres) and distintos <= len(nombres) // 3 \
            and all(nombres.count(v) >= 3 for v in set(nombres))
    grupos = []  #[(nombre, [filas])]
    if columna_parcela:
        for f in puntos:
            if not grupos or grupos[-1][0] != f[1]:
                grupos.append((f[1], []))
            grupos[-1][1].append(f)
    else:
        pendiente, actual = '', None  #Nombre que da un título a la parcela siguiente
        for k, f in enumerate(filas, start=1):
            if f is None:
                actual = None
                if k in titulos:
                    pendiente = titulos[k] or ''
                continue
            if actual is None:
                actual = []
                grupos.append((pendiente, actual))
                pendiente = ''
            actual.append(f)
    usados = set()
    for k, (nombre, filas_grupo) in enumerate(grupos, start=1):
        identificador = re.sub(r'[^\w.-]', '_', str(nombre)) if nombre else f'Parcela_{k}'
        while identificador in usados:
            identificador = f'{identificador}_{k}'
        usados.add(identificador)
        resultado.parcelas.append(ParcelaPuntos(identificador, [Punto(x, y, nombre_p if not columna_parcela else '', n)
                                                                for n, nombre_p, x, y in filas_grupo]))
    _revisar_conjunto(resultado)
    if not any(i.codigo == 'COORD-GRADOS' for i in resultado.incidencias):  #En grados no se forma nada: no son metros
        for parcela in resultado.parcelas:
            formar(parcela)
    return resultado


def _revisar_conjunto(resultado):
    """Grados, orden Y X y coordenadas que no son de España: se mira el conjunto, no punto a punto."""
    todos = [p for parcela in resultado.parcelas for p in parcela.puntos]
    if all(abs(p.x) <= 180 and abs(p.y) <= 90 for p in todos):
        resultado.incidencias.append(Incidencia(ERROR, 'COORD-GRADOS', "Las coordenadas parecen grados (latitud y "
                                                                        "longitud): la Sede pide UTM en metros. Páselas a "
                                                                        "UTM (ETRS89) antes, o cree la capa en QGIS"))
        return
    en_x = sum(X_UTM[0] <= p.x <= X_UTM[1] and Y_UTM[0] <= p.y <= Y_UTM[1] for p in todos)
    al_reves = sum(X_UTM[0] <= p.y <= X_UTM[1] and Y_UTM[0] <= p.x <= Y_UTM[1] for p in todos)
    if al_reves == len(todos) and en_x == 0:
        for p in todos:
            p.x, p.y = p.y, p.x
        resultado.incidencias.append(Incidencia(AVISO, 'COORD-YX', "Las coordenadas venían en el orden Y X (la Y, de "
                                                                    "millones, primero): se han leído como X Y"))
    elif en_x < len(todos):
        #Puntos que no son coordenadas UTM de España: una coordenada mal escrita (una cifra o el punto de menos). La
        #parcela que los tiene no se forma (sería una astilla de kilómetros) y se dice la línea
        for parcela in resultado.parcelas:
            fuera = [p for p in parcela.puntos if not (X_UTM[0] <= p.x <= X_UTM[1] and Y_UTM[0] <= p.y <= Y_UTM[1])]
            if fuera:
                lineas = ', '.join(str(p.linea) for p in fuera[:5]) + ('…' if len(fuera) > 5 else '')
                ejemplo = fuera[0]
                parcela.incidencias.append(Incidencia(
                    ERROR, 'COORD-FUERA', f"{'Las líneas' if len(fuera) > 1 else 'La línea'} {lineas} no "
                                          f"{'tienen' if len(fuera) > 1 else 'tiene'} coordenadas UTM de España (p. ej. "
                                          f"{geo.formatear(ejemplo.x)} {geo.formatear(ejemplo.y)}): compruebe que están "
                                          "bien escritas", parcela.identificador))


def formar(parcela):
    """La geometría de la parcela con sus puntos en orden; incidencias si no se puede o hace dudar."""
    puntos = [QgsPointXY(p.x, p.y) for p in parcela.puntos]
    #Cierre y puntos repetidos seguidos (también la repetición del primero al final, que es lo normal en una libreta)
    limpios = []
    for p in puntos:
        if not limpios or p != limpios[-1]:
            limpios.append(p)
    if len(limpios) > 1 and limpios[0] == limpios[-1]:
        limpios.pop()
    repetidos = len(puntos) - len(limpios) - (1 if len(puntos) > 1 and puntos[0] == puntos[-1] else 0)
    if repetidos > 0:
        parcela.incidencias.append(Incidencia(INFO, 'COORD-REPETIDOS', f"Se {'han' if repetidos > 1 else 'ha'} quitado "
                                                                        f"{repetidos} punto{'s' if repetidos > 1 else ''} "
                                                                        "repetido seguido", parcela.identificador))
    if len(limpios) > MAX_PUNTOS:
        parcela.incidencias.append(Incidencia(ERROR, 'COORD-MUCHOS', f"{len(limpios)} puntos: más de {MAX_PUNTOS} no es "
                                                                      "el contorno de una parcela (¿es una nube de "
                                                                      "puntos o faltan separaciones entre parcelas?)",
                                              parcela.identificador))
        return
    if len({(p.x(), p.y()) for p in limpios}) < 3:
        parcela.incidencias.append(Incidencia(ERROR, 'COORD-POCOS', f"Solo {len(limpios)} punto"
                                                                     f"{'s' if len(limpios) != 1 else ''} distinto"
                                                                     f"{'s' if len(limpios) != 1 else ''}: hacen falta "
                                                                     "al menos 3 para cerrar una parcela",
                                              parcela.identificador))
        return
    geometria = QgsGeometry.fromPolygonXY([limpios + [limpios[0]]])
    if geo.degenerado([(p.x(), p.y()) for p in limpios + [limpios[0]]]):
        parcela.incidencias.append(Incidencia(ERROR, 'COORD-ALINEADOS', "Los puntos están alineados: no encierran "
                                                                         "superficie", parcela.identificador))
        return
    if not geometria.isGeosValid():
        motivo = geo.motivo_invalida(geometria)
        parcela.incidencias.append(Incidencia(ERROR, 'COORD-CRUZA', "El contorno se cruza consigo mismo" + (
            motivo.replace(': el contorno se corta a sí mismo', '') if motivo else '') + ": los puntos tienen que ir "
            "en el orden del contorno (uno detrás de otro, sin saltar al otro lado)", parcela.identificador))
        parcela.geometria = geometria  #Para verla en el mapa
        return
    lejano = geo.vertice_lejano([[(p.x(), p.y()) for p in limpios + [limpios[0]]]])
    if lejano is not None and not any(i.codigo == 'COORD-FUERA' for i in parcela.incidencias):  #Ya dicho, con su línea
        n, x, y, metros = lejano
        linea = parcela.puntos[n - 1].linea if n - 1 < len(parcela.puntos) else 0
        parcela.incidencias.append(Incidencia(AVISO, 'COORD-LEJANO', f"El punto de la línea {linea} ({geo.formatear(x)} "
                                                                      f"{geo.formatear(y)}) está a "
                                                                      f"{metros / 1000:.1f} km de los demás".replace('.', ',')
                                                                      + ": compruebe que está bien escrito",
                                              parcela.identificador))
    parcela.geometria = geometria


def resumen(lectura):
    """Texto corto para la utilidad: cuántas parcelas, puntos y superficies, o el primer problema."""
    if not lectura.parcelas:
        return lectura.incidencias[0].mensaje if lectura.incidencias else "Sin puntos"
    partes = []
    for p in lectura.parcelas[:6]:
        if p.geometria is not None and not any(i.nivel == ERROR for i in p.incidencias):
            partes.append(f"{p.identificador}: {len(p.puntos)} puntos, {geo.redondear_m2(p.geometria.area())} m²")
        else:
            partes.append(f"{p.identificador}: {len(p.puntos)} puntos, sin parcela")
    if len(lectura.parcelas) > 6:
        partes.append(f"… y {len(lectura.parcelas) - 6} más")
    return " · ".join(partes)


def errores(lectura):
    return [i for i in lectura.incidencias + [i for p in lectura.parcelas for i in p.incidencias] if i.nivel == ERROR]


def distancia(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)
