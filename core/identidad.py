"""
Simulación del criterio de identidad gráfica (AU-58): ¿una representación gráfica alternativa (el GML de un
levantamiento) y la parcela catastral son «similares o equivalentes»? Solo como ayuda previa al notario, al registro o
al IVG: el informe válido es el de la Sede Electrónica del Catastro (Certificado de Identidad Gráfica).

Norma (Resolución conjunta DGSJFP-DGC de 23/09/2020, BOE-A-2020-12111, anexo II, «Margen de tolerancia gráfica»):
  1. La línea exterior que delimita el perímetro de la geometría de la RGGA debe estar dentro de la zona entre un borde
     exterior a +0,50 m y uno interior a –0,50 m del perímetro de la parcela catastral en cartografía urbana; ±2,00 m
     en cartografía rústica.
  2. Adicionalmente, la diferencia de superficie entre la RGGA y la cartografía catastral no excede del 5 % de la
     superficie catastral.
El margen depende de la cartografía (urbana o rústica) en que está la parcela catastral, «independientemente de la
naturaleza de la parcela» (ayuda de la Sede). Con giros o desplazamientos de la cartografía, primero se corrigen y
después se aplica el criterio (Resolución de 29/03/2021): aquí se puede aplicar una transformación (core/ajuste.py).
El certificado solo se emite con una parcela aportada frente a una catastral (1:1).

Sin interfaz (la usa la utilidad «7.» de Utilidades).

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
from dataclasses import dataclass, field

from qgis.core import QgsGeometry, QgsPointXY

from . import refcat
from .incidencias import AVISO, ERROR, Incidencia

MARGEN_URBANA = 0.50   #m
MARGEN_RUSTICA = 2.00  #m
DIFERENCIA_SUPERFICIE = 5.0  #% de la superficie catastral
SOLAPE_PROPIA = 0.5    #Una parcela catastral es la de la RGGA si esta cubre más de la mitad de ella
MINIMO_TRAMO = 0.01    #m: tramos fuera más cortos son ruido numérico
FUENTE = ("Resolución conjunta DGSJFP-DGC de 23/09/2020 (BOE-A-2020-12111), anexo II, «Margen de tolerancia gráfica»")


@dataclass
class Tramo:
    """Tramo de la línea exterior de la RGGA que queda fuera del margen."""
    longitud: float
    distancia: float       #m: lo más que se separa del perímetro catastral
    x: float               #Punto donde más se separa
    y: float


@dataclass
class Resultado:
    catastrales: list = field(default_factory=list)   #Referencias de las parcelas catastrales con las que se compara
    cartografia: str = ''      #'urbana' o 'rústica'
    margen: float = 0.0        #m
    area_rgga: float = 0.0
    area_catastral: float = 0.0
    dentro_margen: bool = False
    tramos: list = field(default_factory=list)        #Tramo fuera del margen
    separacion: float = 0.0    #m: lo más que se separa la línea de la RGGA del perímetro catastral
    banda: object = None       #QgsGeometry: la zona del margen (para verla)
    referencia: object = None  #QgsGeometry: la parcela (o parcelas) catastral
    rgga: object = None        #QgsGeometry: la RGGA (transformada, si se aplicó una transformación)
    recintos_rgga: int = 0
    desplazamiento: tuple = None  #(dx, dy) que la dejaría dentro del margen, si lo hay (pista)
    incidencias: list = field(default_factory=list)

    @property
    def diferencia(self):
        """Diferencia de superficie, en % de la catastral."""
        return 100.0 * abs(self.area_rgga - self.area_catastral) / self.area_catastral if self.area_catastral else 0.0

    @property
    def dentro_superficie(self):
        return self.area_catastral > 0 and self.diferencia <= DIFERENCIA_SUPERFICIE

    @property
    def uno_a_uno(self):
        return self.recintos_rgga == 1 and len(self.catastrales) == 1

    @property
    def cumple(self):
        return bool(self.catastrales) and self.dentro_margen and self.dentro_superficie


def margen_de(rc, forzado=None):
    """(margen en m, cartografía) para la parcela catastral rc: por el formato de su referencia, o el forzado."""
    if forzado in ('urbana', 'rústica'):
        return (MARGEN_URBANA if forzado == 'urbana' else MARGEN_RUSTICA), forzado
    tipo = refcat.tipo_parcela(refcat.limpiar(rc)[:14])
    return (MARGEN_RUSTICA, 'rústica') if tipo == 'rústica' else (MARGEN_URBANA, 'urbana')


def exterior(geometria):
    """Las líneas exteriores (sin los huecos) de una geometría poligonal, como una geometría de líneas."""
    poligonos = geometria.asMultiPolygon() if geometria.isMultipart() else [geometria.asPolygon()]
    lineas = [p[0] for p in poligonos if p]
    return QgsGeometry.fromMultiPolylineXY(lineas) if len(lineas) > 1 else QgsGeometry.fromPolylineXY(lineas[0])


def propias(rgga, catastrales):
    """Las parcelas catastrales [(rc, geometría)] que son las de la RGGA: las que esta cubre en más de la mitad."""
    elegidas = []
    for rc, geometria in catastrales:
        area = geometria.area()
        if area > 0 and rgga.intersection(geometria).area() > SOLAPE_PROPIA * area:
            elegidas.append((rc, geometria))
    return elegidas


def comprobar(rgga_partes, catastrales, forzado=None, transformacion=None):
    """
    rgga_partes: geometrías de los recintos del GML (en el SRC de las catastrales); catastrales: [(rc, geometría)]
    de alrededor; forzado: 'urbana' o 'rústica' para no deducir el margen; transformacion: core.ajuste.Transformacion
    que se aplica antes a la RGGA (cartografía desplazada o girada). Devuelve un Resultado.
    """
    resultado = Resultado(recintos_rgga=len(rgga_partes))
    partes = [transformacion.geometria(g) if transformacion is not None else QgsGeometry(g) for g in rgga_partes]
    rgga = QgsGeometry.unaryUnion(partes) if len(partes) > 1 else partes[0]
    resultado.rgga = rgga
    resultado.area_rgga = rgga.area()
    elegidas = propias(rgga, catastrales)
    if not elegidas:
        resultado.incidencias.append(Incidencia(ERROR, 'IDG-SIN-PARCELA', "El GML no se corresponde con ninguna parcela "
                                                                           "catastral (no cubre más de la mitad de "
                                                                           "ninguna): no se puede comparar"))
        return resultado
    resultado.catastrales = [rc for rc, _ in elegidas]
    referencia = QgsGeometry.unaryUnion([g for _, g in elegidas]) if len(elegidas) > 1 else QgsGeometry(elegidas[0][1])
    resultado.referencia = referencia
    resultado.area_catastral = referencia.area()
    margenes = {margen_de(rc, forzado) for rc in resultado.catastrales}
    resultado.margen, resultado.cartografia = min(margenes)  #Mezcla urbana y rústica: el más estricto
    if len(margenes) > 1:
        resultado.incidencias.append(Incidencia(AVISO, 'IDG-MEZCLA', "Las parcelas catastrales están en cartografía urbana "
                                                                      "y rústica: se aplica el margen más estricto "
                                                                      f"(±{resultado.margen:.2f} m)"))
    perimetro = exterior(referencia)
    resultado.banda = perimetro.buffer(resultado.margen, 8)
    medir(resultado, exterior(rgga), perimetro)
    if len(resultado.catastrales) > 1 or resultado.recintos_rgga > 1:
        resultado.incidencias.append(Incidencia(AVISO, 'IDG-NO-1A1', f"Son {resultado.recintos_rgga} recinto"
                                                                      f"{'s' if resultado.recintos_rgga != 1 else ''} "
                                                                      f"frente a {len(resultado.catastrales)} parcela"
                                                                      f"{'s' if len(resultado.catastrales) != 1 else ''} "
                                                                      "catastrales: la Sede compara, pero solo emite el "
                                                                      "certificado con una frente a una"))
    if not resultado.dentro_margen and transformacion is None:
        desplazamiento = desplazamiento_que_cumple(rgga, perimetro, resultado.margen)
        #Solo como pista si explica la separación (toda la RGGA movida): con un vértice mal, moverla algo también la
        #mete en el margen, pero el problema es ese vértice, no la cartografía
        if desplazamiento is not None and (desplazamiento[0] ** 2 + desplazamiento[1] ** 2) ** 0.5 >= 0.5 * resultado.separacion:
            resultado.desplazamiento = desplazamiento
    return resultado


def medir(resultado, linea, perimetro):
    """Tramos de la línea de la RGGA fuera de la banda, y lo más que se separa del perímetro catastral."""
    fuera = linea.difference(resultado.banda)
    resultado.separacion = _separacion(linea, perimetro)
    partes = fuera.asGeometryCollection() if not fuera.isEmpty() else []
    for parte in partes:
        if parte.length() < MINIMO_TRAMO:
            continue
        distancia, punto = 0.0, None
        for p in _muestras(parte):
            d = perimetro.distance(QgsGeometry.fromPointXY(p))
            if d > distancia:
                distancia, punto = d, p
        if punto is not None:
            resultado.tramos.append(Tramo(parte.length(), distancia, punto.x(), punto.y()))
    resultado.tramos.sort(key=lambda t: -t.distancia)
    resultado.dentro_margen = not resultado.tramos


def _muestras(linea, paso=0.05):
    """Vértices de la línea y puntos cada paso metros (para medir la separación máxima sin depender de los vértices)."""
    puntos = []
    densa = linea.densifyByDistance(paso) if linea.length() > paso else linea
    for parte in (densa.asMultiPolyline() if densa.isMultipart() else [densa.asPolyline()]):
        puntos += parte
    return puntos


def _separacion(linea, perimetro):
    """Lo más que se separa la línea del perímetro (distancia de Hausdorff dirigida, en m)."""
    return max((perimetro.distance(QgsGeometry.fromPointXY(p)) for p in _muestras(linea, 0.10)), default=0.0)


def desplazamiento_que_cumple(rgga, perimetro, margen, iteraciones=15):
    """
    Si la RGGA entra en el margen con solo desplazarla, ese desplazamiento (dx, dy); si no, None. Se busca moviendo los
    puntos de la línea hacia el punto más cercano del perímetro catastral (como un ajuste de puntos más próximos).
    """
    linea = exterior(rgga)
    puntos = _muestras(linea, 0.5)
    if not puntos:
        return None
    dx = dy = 0.0
    for _ in range(iteraciones):
        sx = sy = 0.0
        for p in puntos:
            movido = QgsPointXY(p.x() + dx, p.y() + dy)
            cercano = perimetro.nearestPoint(QgsGeometry.fromPointXY(movido)).asPoint()
            sx += cercano.x() - movido.x()
            sy += cercano.y() - movido.y()
        dx += sx / len(puntos)
        dy += sy / len(puntos)
    movida = QgsGeometry(linea)
    movida.translate(dx, dy)
    if movida.difference(perimetro.buffer(margen, 8)).length() < MINIMO_TRAMO:
        return dx, dy
    return None


# ------------------------------------------------------------------ Desde un fichero, resumen e informe

@dataclass
class Simulacion:
    ruta: str
    resultado: object = None   #Resultado, si se ha podido comprobar
    epsg: int = None
    errores: list = field(default_factory=list)  #Incidencia (lectura, red…)


def comprobar_gml(ruta, forzado=None, transformacion=None):
    """Lee el GML, pide al Catastro las parcelas de alrededor y comprueba el criterio. Nunca lanza excepciones."""
    from . import comparacion as cmp
    from . import geometria as geo
    from . import gml_lector as gl
    simulacion = Simulacion(ruta)
    lectura = gl.leer(ruta)
    errores = [i for i in lectura.incidencias if i.nivel == ERROR]
    if errores:
        simulacion.errores = errores
        return simulacion
    if not lectura.version.startswith('CP') or not lectura.elementos:
        simulacion.errores = [Incidencia(ERROR, 'IDG-NO-PARCELA', "Elija un GML de parcela catastral (el de edificios no "
                                                                   "sirve para la identidad gráfica)")]
        return simulacion
    epsg, geometrias, girado = geo.grados_a_utm([e.geometria for e in lectura.elementos], lectura.epsg)
    if epsg is None:
        simulacion.errores = [Incidencia(ERROR, 'IDG-SRC', girado)]
        return simulacion
    if epsg not in geo.SRC_ADMITIDOS:
        simulacion.errores = [Incidencia(ERROR, 'IDG-SRC', f"EPSG:{epsg} no es un sistema de la Sede: conviértalo antes en "
                                                            "«2. Convertir a 4.0 o reparar»")]
        return simulacion
    simulacion.epsg = epsg
    caja = QgsGeometry.collectGeometry(geometrias).boundingBox()
    caja.grow(max(MARGEN_RUSTICA * 2, cmp.MARGEN))
    catastrales, errores = cmp.parcelas_catastrales([caja], epsg)
    if errores:
        simulacion.errores = errores
        return simulacion
    simulacion.resultado = comprobar(geometrias, [(e.local_id, e.geometria) for e in catastrales], forzado, transformacion)
    if epsg != lectura.epsg:
        simulacion.resultado.incidencias.append(Incidencia(AVISO, 'IDG-GRADOS', f"El GML está en EPSG:{lectura.epsg} "
                                                                                 f"(grados): se ha comparado en EPSG:{epsg}"))
    return simulacion


def _m(valor, decimales=2):
    return f"{valor:,.{decimales}f}".replace(',', ' ').replace('.', ',')


def resumen(r):
    """Líneas para el panel y el informe."""
    if not r.catastrales:
        return [i.mensaje for i in r.incidencias]
    lineas = [f"Parcela catastral: {', '.join(r.catastrales)} · cartografía {r.cartografia} · margen ±{_m(r.margen)} m",
              f"1. Contorno: {'dentro del margen' if r.dentro_margen else 'fuera del margen'} (lo más que se separa del "
              f"catastral: {_m(r.separacion)} m)",
              f"2. Superficie: GML {_m(r.area_rgga)} m², catastral {_m(r.area_catastral)} m²: diferencia "
              f"{_m(r.diferencia)} % ({'no pasa' if r.dentro_superficie else 'pasa'} del {DIFERENCIA_SUPERFICIE:.0f} %)"]
    for t in r.tramos[:5]:
        lineas.append(f"Fuera del margen: {_m(t.longitud)} m de contorno, hasta {_m(t.distancia)} m del catastral "
                      f"(cerca de X {t.x:.2f}, Y {t.y:.2f})")
    if len(r.tramos) > 5:
        lineas.append(f"… y {len(r.tramos) - 5} tramos más")
    if r.desplazamiento is not None:
        dx, dy = r.desplazamiento
        lineas.append(f"Con un desplazamiento de {_m(dx)} m en X y {_m(dy)} m en Y entraría en el margen: si la "
                      "cartografía catastral está desplazada, la Sede pide aplicar primero el desplazamiento (utilidad "
                      "«4. Ajustar») y después el criterio")
    lineas += [i.mensaje for i in r.incidencias]
    return lineas


def veredicto(r):
    if not r.catastrales:
        return "No se puede comprobar"
    if r.cumple:
        return ("Cumpliría el criterio de identidad gráfica" + ("" if r.uno_a_uno else
                                                                 " (pero la Sede no emitiría el certificado: no es 1:1)"))
    return "No cumpliría el criterio de identidad gráfica"


def html(simulacion, ahora=None):
    """Informe HTML de la simulación, con un croquis: margen en azul, parcela catastral en gris, GML en naranja y lo que
    queda fuera del margen en rojo."""
    import datetime
    import os
    from html import escape
    from types import SimpleNamespace

    from .info import AVISO_LEGAL, FUENTE_DGC, NOMBRE, version
    from .informe import croquis_svg
    ahora = ahora or datetime.datetime.now()
    r = simulacion.resultado
    nombre = os.path.basename(simulacion.ruta)
    croquis = ''
    if r is not None and r.referencia is not None:
        elementos = [SimpleNamespace(geometria=r.banda, local_id='', color='#4dabf7'),
                     SimpleNamespace(geometria=r.referencia, local_id=', '.join(r.catastrales), color='#495057',
                                     discontinua=True),
                     SimpleNamespace(geometria=r.rgga, local_id='', color='#e8590c')]
        if r.tramos:
            fuera = exterior(r.rgga).difference(r.banda).buffer(max(r.margen / 8, 0.05), 4)
            elementos.append(SimpleNamespace(geometria=fuera, local_id='', color='#c92a2a'))
        croquis = croquis_svg(elementos, alto=440)
        if r.tramos:  #Detalle del tramo que más se separa: en el croquis general, con parcelas de decenas de metros, no se ve
            from qgis.core import QgsRectangle
            t = r.tramos[0]
            lado = max(8 * r.margen, 3 * t.distancia, 4.0)
            detalle = croquis_svg(elementos, alto=360, encuadre=QgsRectangle(t.x - lado, t.y - lado, t.x + lado, t.y + lado))
            croquis += (f'<p class="meta">Detalle del tramo que más se separa ({_m(t.distancia)} m, cerca de X {t.x:.2f}, '
                        f'Y {t.y:.2f}):</p>' + detalle)
    lineas = resumen(r) if r is not None else [i.mensaje for i in simulacion.errores]
    titulo = veredicto(r) if r is not None else "No se ha podido comprobar"
    color = '#2b8a3e' if r is not None and r.cumple else '#c92a2a'
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Identidad gráfica (simulación) · {escape(nombre)}</title>
<style>
  :root {{ --fondo:#ffffff; --texto:#1d2327; --suave:#f1f3f5; --linea:#dee2e6; --acento:#1f6f78; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --fondo:#15191b; --texto:#e6eaeb; --suave:#1e2426; --linea:#343a40; }} }}
  body {{ font-family:"Segoe UI",Arial,sans-serif; max-width:900px; margin:0 auto; padding:16px; background:var(--fondo);
         color:var(--texto); line-height:1.45; }}
  h1 {{ color:var(--acento); font-size:1.4em; margin:0 0 4px; }} h2 {{ font-size:1.15em; }}
  .meta {{ opacity:.8; font-size:.92em; }} .aviso-legal {{ font-size:.88em; opacity:.85; }}
  .croquis {{ display:block; width:100%; max-width:760px; margin:8px auto; background:var(--suave); border-radius:6px; }}
  .etiqueta {{ font-size:12px; fill:var(--texto); paint-order:stroke; stroke:var(--fondo); stroke-width:3px; }}
  footer {{ margin-top:28px; font-size:.85em; opacity:.75; border-top:1px solid var(--linea); padding-top:8px; }}
</style></head><body>
<h1>Identidad gráfica con la parcela catastral (simulación)</h1>
<p class="aviso-legal"><b>Simulación no oficial</b>: el informe válido es el Certificado de Identidad Gráfica de la Sede
Electrónica del Catastro. ⚠ {escape(AVISO_LEGAL)}</p>
<div class="meta">{escape(nombre)} · EPSG:{simulacion.epsg or '—'} · {ahora:%d/%m/%Y %H:%M}</div>
<h2 style="color:{color}">{escape(titulo)}</h2>
<ul>{''.join(f'<li>{escape(x)}</li>' for x in lineas)}</ul>
{croquis}
<p class="meta">En azul, el margen de tolerancia alrededor del perímetro catastral (gris discontinuo); en naranja, el GML;
en rojo, lo que queda fuera del margen. Criterio: {escape(FUENTE)}: el contorno exterior del GML dentro del margen
(±0,50 m en cartografía urbana, ±2,00 m en rústica) y la diferencia de superficie no mayor del 5 % de la catastral.
Parcelas catastrales: datos públicos de la {escape(FUENTE_DGC)} consultados el {ahora:%d/%m/%Y a las %H:%M}.</p>
<footer>Generado con {escape(NOMBRE)} {escape(version())} (herramienta no oficial, GPL-2.0-or-later) a partir de
<code>{escape(simulacion.ruta)}</code>.</footer>
</body></html>
"""


def ruta_informe(ruta_gml):
    import os
    base, _ = os.path.splitext(ruta_gml)
    return f"{base}_identidad.html"


def escribir(simulacion, ruta=None):
    from .ficheros import escribir_texto
    ruta = ruta or ruta_informe(simulacion.ruta)
    problema = escribir_texto(ruta, html(simulacion), 'utf-8')
    if problema is not None:
        raise OSError(problema.mensaje)
    return ruta
