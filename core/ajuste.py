"""
Ajuste por desplazamiento o giro de la cartografía catastral (fase 8e, AU-52).

Cuando la cartografía catastral está desplazada o girada respecto de la realidad, el levantamiento del técnico (en su
posición real) no casa con las parcelas del Catastro. La Resolución conjunta de la DGSJFP y la DGC de 29/03/2021
(BOE-A-2021-5949), apartado octavo, pide entonces dos GML: el del levantamiento, en coordenadas reales, y otro ajustado a
la cartografía catastral «procedente de aplicar los parámetros de transformación», junto con esos parámetros; primero se
ajusta el desplazamiento y después se aplica el criterio de identidad (apartado noveno). En el ICUC con toda la
cartografía de la zona desplazada (ayuda de la Sede «Posibles casos de desplazamientos en ICUC»): se marca que existe
desplazamiento, se escriben los parámetros, el ICUC se obtiene con el GML desplazado como la cartografía catastral y el
de las construcciones bien georreferenciadas se adjunta en «+ Documentación».

Los parámetros son los de la Sede, de coordenadas reales (X, Y) a catastrales (X', Y'):

    X' = AX·X + BX·Y + CX
    Y' = AY·X + BY·Y + CY

con AX = BY = 1 y BX = AY = 0 si solo hay traslación; CX y CY son positivos si la cartografía catastral está más al este
o al norte que la realidad. Se calculan por mínimos cuadrados con pares de puntos homólogos (el mismo punto del terreno
en el levantamiento y en la cartografía catastral):

  - traslación (CX, CY): 1 punto o más (la media de las diferencias);
  - semejanza (giro, escala y traslación; 4 parámetros): 2 puntos o más;
  - afín (6 parámetros): 3 puntos o más, no alineados.

Con más puntos de los mínimos, los residuos de cada punto y el error medio cuadrático dicen si el ajuste es bueno.

Sin interfaz: lo usa la utilidad «Ajustar a la cartografía catastral» de la pestaña Utilidades.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import datetime
import math
import os
import re
from dataclasses import dataclass

from qgis.core import QgsGeometry
from qgis.PyQt.QtGui import QTransform

from . import geometria as geo
from . import gml_lector as gl
from . import gml_parcela as gp
from .ficheros import comprobar_destino, escribir_texto, misma_ruta
from .incidencias import ERROR, Incidencia
from .info import AVISO_LEGAL, NOMBRE, version

TRASLACION, SEMEJANZA, AFIN, CONOCIDOS = 'traslacion', 'semejanza', 'afin', 'conocidos'
MINIMO_PUNTOS = {TRASLACION: 1, SEMEJANZA: 2, AFIN: 3, CONOCIDOS: 0}
NOMBRES = {TRASLACION: "Traslación (CX, CY)", SEMEJANZA: "Giro, escala y traslación (semejanza)",
           AFIN: "Afín (6 parámetros)", CONOCIDOS: "Parámetros conocidos"}
DECIMALES_A = 12  #AX, BX, AY, BY: con Y ≈ 4 000 000 m, 1e-12 son 4 µm
DECIMALES_C = 4   #CX, CY en metros
NAMESPACES = {'ES.SDGC.CP': gp.SDGC, 'ES.LOCAL.CP': gp.LOCAL}


@dataclass
class Transformacion:
    """Parámetros de la Sede: X' = ax·X + bx·Y + cx; Y' = ay·X + by·Y + cy (de real a catastral)."""
    ax: float = 1.0
    bx: float = 0.0
    cx: float = 0.0
    ay: float = 0.0
    by: float = 1.0
    cy: float = 0.0

    def aplicar(self, x, y):
        return self.ax * x + self.bx * y + self.cx, self.ay * x + self.by * y + self.cy

    def qtransform(self):
        #QTransform: x' = m11·x + m21·y + dx; y' = m12·x + m22·y + dy
        return QTransform(self.ax, self.ay, self.bx, self.by, self.cx, self.cy)

    def geometria(self, geometria):
        """Copia de la geometría transformada."""
        nueva = QgsGeometry(geometria)
        nueva.transform(self.qtransform())
        return nueva

    def determinante(self):
        return self.ax * self.by - self.bx * self.ay

    def inversa(self):
        d = self.determinante()
        if abs(d) < 1e-12:
            raise ValueError("la transformación no se puede invertir")
        ax, bx, ay, by = self.by / d, -self.bx / d, -self.ay / d, self.ax / d
        return Transformacion(ax, bx, -(ax * self.cx + bx * self.cy), ay, by, -(ay * self.cx + by * self.cy))

    def es_traslacion(self):
        return self.ax == 1 and self.by == 1 and self.bx == 0 and self.ay == 0

    def valores(self):
        return [self.ax, self.bx, self.cx, self.ay, self.by, self.cy]

    def textos(self):
        """Los seis parámetros como se escriben (AX, BX, CX, AY, BY, CY), con punto decimal."""
        return [f"{v:.{DECIMALES_C if i in (2, 5) else DECIMALES_A}f}" for i, v in enumerate(self.valores())]

    def descripcion(self):
        """Giro (grados, sentido antihorario), escala media y traslación en el centro: para que el técnico los valore."""
        escala_x, escala_y = math.hypot(self.ax, self.ay), math.hypot(self.bx, self.by)
        giro = math.degrees(math.atan2(self.ay, self.ax))
        return giro, (escala_x + escala_y) / 2, escala_x, escala_y


@dataclass
class Par:
    """Un punto homólogo: (x, y) real (levantamiento) y (xc, yc) en la cartografía catastral."""
    x: float
    y: float
    xc: float
    yc: float
    nombre: str = ''


@dataclass
class Ajuste:
    transformacion: Transformacion
    metodo: str
    residuos: list    #m por punto (distancia entre el punto transformado y el catastral)
    emc: float        #Error medio cuadrático (m); 0 si no hay redundancia
    redundancia: int  #Puntos de más sobre el mínimo (con 0, los residuos son nulos por construcción)


def _resolver(matriz, vector):
    """Sistema lineal pequeño (Gauss con pivote parcial). ValueError si es singular."""
    n = len(vector)
    a = [list(fila) + [vector[i]] for i, fila in enumerate(matriz)]
    escala = max((abs(v) for fila in matriz for v in fila), default=1.0) or 1.0
    for col in range(n):
        pivote = max(range(col, n), key=lambda f: abs(a[f][col]))
        if abs(a[pivote][col]) < 1e-10 * escala:
            raise ValueError("los puntos no determinan la transformación (¿están alineados o repetidos?)")
        a[col], a[pivote] = a[pivote], a[col]
        for f in range(col + 1, n):
            factor = a[f][col] / a[col][col]
            for c in range(col, n + 1):
                a[f][c] -= factor * a[col][c]
    solucion = [0.0] * n
    for f in range(n - 1, -1, -1):
        solucion[f] = (a[f][n] - sum(a[f][c] * solucion[c] for c in range(f + 1, n))) / a[f][f]
    return solucion


def _minimos_cuadrados(filas, valores):
    """Mínimos cuadrados por ecuaciones normales: filas · p ≈ valores."""
    n = len(filas[0])
    normal = [[sum(f[i] * f[j] for f in filas) for j in range(n)] for i in range(n)]
    termino = [sum(f[i] * v for f, v in zip(filas, valores)) for i in range(n)]
    return _resolver(normal, termino)


def calcular(pares, metodo):
    """
    Ajuste por mínimos cuadrados con los pares de puntos homólogos. Se trabaja con las coordenadas reducidas al centro de
    los puntos (con coordenadas UTM de millones de metros, las ecuaciones normales perderían precisión) y luego se pasa
    a los parámetros de la Sede. ValueError si faltan puntos o no determinan la transformación.
    """
    minimo = MINIMO_PUNTOS[metodo]
    if len(pares) < max(minimo, 1):
        raise ValueError(f"hacen falta al menos {minimo} punto{'s' if minimo != 1 else ''} para este ajuste")
    x0 = sum(p.x for p in pares) / len(pares)
    y0 = sum(p.y for p in pares) / len(pares)
    u = [(p.x - x0, p.y - y0) for p in pares]
    if metodo == TRASLACION:
        cx = sum(p.xc - p.x for p in pares) / len(pares)
        cy = sum(p.yc - p.y for p in pares) / len(pares)
        t = Transformacion(cx=cx, cy=cy)
    elif metodo == SEMEJANZA:
        #X' = a·u − b·v + tx ; Y' = b·u + a·v + ty
        filas, valores = [], []
        for (du, dv), p in zip(u, pares):
            filas += [[du, -dv, 1, 0], [dv, du, 0, 1]]
            valores += [p.xc, p.yc]
        a, b, tx, ty = _minimos_cuadrados(filas, valores)
        t = Transformacion(a, -b, tx - a * x0 + b * y0, b, a, ty - b * x0 - a * y0)
    elif metodo == AFIN:
        filas = [[du, dv, 1] for du, dv in u]
        ax, bx, tx = _minimos_cuadrados(filas, [p.xc for p in pares])
        ay, by, ty = _minimos_cuadrados(filas, [p.yc for p in pares])
        t = Transformacion(ax, bx, tx - ax * x0 - bx * y0, ay, by, ty - ay * x0 - by * y0)
    else:
        raise ValueError(f"método desconocido: {metodo}")
    return evaluar(t, pares, metodo)


def evaluar(t, pares, metodo=CONOCIDOS):
    """Residuos de cada par con la transformación t, error medio cuadrático y redundancia."""
    residuos = []
    for p in pares:
        x, y = t.aplicar(p.x, p.y)
        residuos.append(math.hypot(x - p.xc, y - p.yc))
    n_parametros = {TRASLACION: 2, SEMEJANZA: 4, AFIN: 6}.get(metodo, 0)
    redundancia = 2 * len(pares) - n_parametros if n_parametros else len(pares)
    emc = math.sqrt(sum(r * r for r in residuos) / len(residuos)) if residuos and redundancia > 0 else 0.0
    return Ajuste(t, metodo, residuos, emc, max(redundancia, 0))


ESCALA_ANOMALA = 500e-6  #Más de 0,5 m por km de diferencia de escala: no es un desplazamiento de la cartografía
GIRO_ANOMALO = 0.5       #Grados
REPARTO_MINIMO = 0.25    #Los puntos deben abarcar al menos esta fracción del tamaño del GML (y 5 m)


def avisos(ajuste, pares, tamano=0.0):
    """
    Lo que hace dudar del ajuste (prueba a mano del 19/10/2026: dos puntos a 33 cm daban un giro de 0,18° y una escala
    de +2841 ppm, y CX de 11 829 m): puntos muy juntos para calcular giro y escala, y giro o escala impropios de un
    desplazamiento de la cartografía. tamano: diagonal (m) del rectángulo que ocupa el GML.
    """
    textos = []
    t = ajuste.transformacion
    if ajuste.metodo in (SEMEJANZA, AFIN) and len(pares) >= 2:
        reparto = max(math.hypot(a.x - b.x, a.y - b.y) for i, a in enumerate(pares) for b in pares[i + 1:])
        necesario = max(5.0, REPARTO_MINIMO * tamano)
        if reparto < necesario:
            textos.append(f"Los puntos están muy juntos ({reparto:.2f} m entre los más alejados): el giro y la escala no "
                          f"son fiables. Tome puntos en extremos opuestos del levantamiento (al menos {necesario:.0f} m)")
    if not t.es_traslacion():
        giro, escala, _, _ = t.descripcion()
        if abs(escala - 1) > ESCALA_ANOMALA:
            textos.append(f"Escala anómala ({(escala - 1) * 1e6:+.0f} ppm, {abs(escala - 1) * 1000:.1f} m por km): "
                          "revise los puntos")
        if abs(giro) > GIRO_ANOMALO:
            textos.append(f"Giro anómalo ({giro:.2f}°): revise los puntos")
    return textos


# ------------------------------------------------------------------ Puntos desde un fichero

NUMERO = r'[-+]?\d+(?:[.,]\d+)?'


def leer_pares(texto):
    """
    Pares de puntos de un TXT o CSV: una línea por punto con X Y X' Y' (real y catastral), opcionalmente precedidas de
    un nombre o número. Separadores: espacios, tabuladores, punto y coma o coma (si la coma no es la decimal). Las
    líneas que no tienen cuatro números (cabeceras, comentarios) se saltan. Devuelve (pares, líneas saltadas).
    """
    pares, saltadas = [], []
    for n, linea in enumerate(texto.splitlines(), start=1):
        limpia = linea.strip()
        if not limpia or limpia.startswith('#'):
            continue
        if ';' in limpia or '\t' in limpia:
            campos = [c.strip() for c in re.split(r'[;\t]', limpia) if c.strip()]
        elif limpia.count(',') >= 3:  #Coma como separador (y punto decimal)
            campos = [c.strip() for c in limpia.split(',') if c.strip()]
        else:
            campos = limpia.split()
        numeros = [c for c in campos if re.fullmatch(NUMERO, c)]
        nombre = campos[0] if campos and not re.fullmatch(NUMERO, campos[0]) else ''
        if len(numeros) == 5 and not nombre:  #Número de punto delante
            nombre, numeros = numeros[0], numeros[1:]
        if len(numeros) != 4:
            saltadas.append(n)
            continue
        x, y, xc, yc = (float(v.replace(',', '.')) for v in numeros)
        pares.append(Par(x, y, xc, yc, nombre))
    return pares, saltadas


# ------------------------------------------------------------------ GML ajustado y parámetros

def ruta_ajustada(ruta_gml):
    """levantamiento.gml → levantamiento_ajustado.gml (junto al original)."""
    base, _ = os.path.splitext(ruta_gml)
    return f"{base}_ajustado.gml"


def ruta_parametros(ruta_destino):
    base, _ = os.path.splitext(ruta_destino)
    return f"{base}_parametros.txt"


def _coordenadas_texto(texto, t):
    """Transforma los pares de números de un posList o pos (2D) y los escribe con 2 decimales."""
    numeros = [float(v) for v in texto.split()]
    if len(numeros) % 2:
        raise ValueError("coordenadas incompletas")
    salida = []
    for i in range(0, len(numeros), 2):
        x, y = t.aplicar(numeros[i], numeros[i + 1])
        salida += [geo.formatear(x), geo.formatear(y)]
    return ' '.join(salida)


def transformar_texto(texto, t):
    """Aplica t a todas las coordenadas (gml:posList y gml:pos) de un GML, sin tocar nada más."""
    def cambiar(m):
        if re.search(r'srsDimension="3"', m.group(1)):
            raise ValueError("lleva coordenadas con Z (srsDimension 3); la DGC exige 2D: conviértalo antes")
        return m.group(1) + _coordenadas_texto(m.group(2), t) + m.group(3)
    texto = re.sub(r'(<gml:pos(?:List)?\b[^>]*>)([^<]*)(</gml:pos(?:List)?>)', cambiar, texto)
    #Se escribe en UTF-8: la declaración tiene que decirlo (los GML antiguos pueden venir en ISO-8859-1)
    return re.sub(r'(<\?xml[^>]*encoding=")[^"]*(")', r'\1utf-8\2', texto, count=1)


def escribir_ajustado(ruta, destino, t):
    """
    Escribe el GML ajustado a la cartografía catastral. Parcela (CP 4.0): se reescribe con el escritor del plugin, que
    recalcula la superficie (con giro o escala cambia algo) y conserva identificadores, número de parcela, referencia y
    fecha. Edificio: se transforman las coordenadas y lo demás queda igual. Devuelve (escrito, incidencias).
    """
    if misma_ruta(ruta, destino):
        return False, [Incidencia(ERROR, 'AJ-DESTINO', "El GML ajustado no puede sustituir al del levantamiento: "
                                                       "la Sede pide los dos")]
    problema = comprobar_destino(destino, (ruta,))
    if problema is not None:
        return False, [problema]
    lectura = gl.leer(ruta)
    errores = [i for i in lectura.incidencias if i.nivel == ERROR]
    if not lectura.elementos or lectura.epsg is None:
        return False, errores or [Incidencia(ERROR, 'AJ-LECTURA', "No se ha podido leer el GML")]
    if lectura.version == 'CP 4.0':
        from .conversor import fecha_original
        parcelas = [gp.ParcelaGML(e.local_id, NAMESPACES.get(e.namespace, gp.LOCAL), t.geometria(e.geometria), e.label,
                                  e.referencia) for e in lectura.elementos]
        ok, incidencias = gp.escribir(destino, parcelas, lectura.epsg, fecha=fecha_original(lectura.texto), origenes=(ruta,))
        return ok, incidencias
    if lectura.version.startswith('BU'):
        try:
            texto = transformar_texto(lectura.texto, t)
        except ValueError as e:
            return False, [Incidencia(ERROR, 'AJ-COORDENADAS', f"No se han podido transformar las coordenadas: {e}")]
        problema = escribir_texto(destino, texto, 'utf-8')
        return (False, [problema]) if problema is not None else (True, [])
    return False, [Incidencia(ERROR, 'AJ-VERSION', f"Solo GML de parcela 4.0 o de edificio (este es "
                                                   f"{lectura.version or 'de formato desconocido'}); conviértalo antes")]


def texto_parametros(ajuste, pares, ruta, destino, epsg, ahora=None, tamano=0.0):
    """Fichero de texto con los parámetros (para la Sede, el notario o el registro) y la comprobación con los puntos."""
    ahora = ahora or datetime.datetime.now()
    t = ajuste.transformacion
    nombres = ('AX', 'BX', 'CX', 'AY', 'BY', 'CY')
    giro, escala, _, _ = t.descripcion()
    lineas = [
        "PARÁMETROS DE TRANSFORMACIÓN: DE COORDENADAS DEL LEVANTAMIENTO A LA CARTOGRAFÍA CATASTRAL",
        f"Generado con {NOMBRE} {version()} el {ahora:%d/%m/%Y %H:%M}. {AVISO_LEGAL}",
        "",
        f"Levantamiento (coordenadas reales): {os.path.basename(ruta)}",
        f"Ajustado a la cartografía catastral: {os.path.basename(destino)}",
        f"Sistema de referencia: EPSG:{epsg}",
        f"Método: {NOMBRES.get(ajuste.metodo, ajuste.metodo)}",
        "",
        "X' = AX·X + BX·Y + CX",
        "Y' = AY·X + BY·Y + CY",
        "(X, Y: levantamiento; X', Y': cartografía catastral.",
        " CX y CY son positivos si la cartografía catastral está más al este o al norte que la realidad.)",
        "",
    ]
    lineas += [f"{n} = {v}" for n, v in zip(nombres, t.textos())]
    lineas += ["", f"Giro: {giro:.6f}° (antihorario) · escala: {escala:.8f} ({(escala - 1) * 1e6:+.1f} ppm)", ""]
    if pares:
        lineas.append(f"Puntos homólogos ({len(pares)}):")
        lineas.append("Nº;Nombre;X;Y;X';Y';Residuo (m)")
        for i, (p, r) in enumerate(zip(pares, ajuste.residuos), start=1):
            lineas.append(f"{i};{p.nombre};{p.x:.3f};{p.y:.3f};{p.xc:.3f};{p.yc:.3f};{r:.3f}")
        if ajuste.redundancia > 0:
            lineas.append(f"Error medio cuadrático: {ajuste.emc:.3f} m · residuo máximo: {max(ajuste.residuos):.3f} m")
        else:
            lineas.append("Sin puntos de más: los residuos son nulos por construcción y no comprueban el ajuste "
                          "(conviene añadir algún punto de control).")
    dudas = avisos(ajuste, pares, tamano)
    if dudas:
        lineas += ["", "AVISOS:"] + [f"- {d}" for d in dudas]
    lineas += ["", "Resolución conjunta DGSJFP-DGC de 29/03/2021 (BOE-A-2021-5949), apartado octavo: se aportan los dos "
               "GML (levantamiento y ajustado a la cartografía catastral) y estos parámetros. ICUC con la cartografía "
               "desplazada (ayuda de la Sede): se marca que existe desplazamiento, se escriben los parámetros, se sube el "
               "GML ajustado y el del levantamiento se adjunta en «+ Documentación»."]
    return '\n'.join(lineas) + '\n'


def escribir_parametros(ajuste, pares, ruta, destino, epsg, ahora=None, tamano=0.0):
    """Escribe el fichero de parámetros junto al GML ajustado; devuelve su ruta (OSError si no se puede)."""
    salida = ruta_parametros(destino)
    problema = escribir_texto(salida, texto_parametros(ajuste, pares, ruta, destino, epsg, ahora, tamano), 'utf-8')
    if problema is not None:
        raise OSError(problema.mensaje)
    return salida
