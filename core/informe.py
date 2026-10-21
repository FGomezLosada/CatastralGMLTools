"""
Informe de comprobación en HTML (no oficial): un único fichero autocontenido (sin internet ni librerías externas) con el resultado,
la tabla de parcelas o construcciones, las incidencias, un croquis en SVG y la lista de coordenadas de cada recinto.
Sirve para guardarlo junto al GML o adjuntarlo a un expediente.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import base64
import datetime
import math
import os
from html import escape

from qgis.core import QgsGeometry, QgsPointXY, QgsRectangle

from . import geometria as geo
from .ficheros import escribir_texto
from .incidencias import AVISO, ERROR, INFO
from .info import AVISO_LEGAL, FUENTE_DGC, NOMBRE, version
from .validador import resumen

COLORES = {ERROR: '#c92a2a', AVISO: '#e67700', 'correcta': '#2b8a3e'}
TEXTO_ESTADO = {ERROR: 'Con errores', AVISO: 'Con avisos', 'correcta': 'Correcta'}
NIVEL = {ERROR: 'Error', AVISO: 'Aviso', INFO: 'Información'}
PALETA_CROQUIS = ('#e8590c', '#1971c2', '#2b8a3e', '#9c36b5', '#c92a2a', '#0c8599', '#e67700', '#5c940d')


def ruta_por_defecto(ruta_gml):
    """Informe junto al GML: segregacion.gml → segregacion_informe.html."""
    base, _ = os.path.splitext(ruta_gml)
    return f"{base}_informe.html"


def _escala_redonda(maximo):
    """Longitud «redonda» (1, 2 o 5 × 10^n m) no mayor que maximo, para la barra de escala."""
    if maximo <= 0:
        return 0
    potencia = 10 ** math.floor(math.log10(maximo))
    return max(f * potencia for f in (1, 2, 5) if f * potencia <= maximo)


def _validas(elementos):
    return [e for e in elementos if e.geometria is not None and not e.geometria.isNull() and not e.geometria.isEmpty()]


def vista_croquis(elementos, ancho=640, alto=420, margen=24, foco=None, encuadre=None):
    """
    Rectángulo del terreno (QgsRectangle, en el SRC de las geometrías) que ocupa el croquis entero: sirve para pedir la
    ortofoto exactamente de ese encuadre. Con foco, el croquis se centra en ese recinto con un margen alrededor para ver
    sus colindantes. None si no hay geometrías.
    """
    if encuadre is not None:  #Una zona concreta (el detalle de un tramo), sin atenuar ningún recinto
        caja = QgsRectangle(encuadre)
    elif foco is not None:
        caja = QgsRectangle(foco.geometria.boundingBox())
        caja.grow(max(caja.width(), caja.height(), 1.0) * 0.12)
    else:
        validas = _validas(elementos)
        if not validas:
            return None
        caja = QgsRectangle(validas[0].geometria.boundingBox())
        for e in validas[1:]:
            caja.combineExtentWith(e.geometria.boundingBox())
    w, h = max(caja.width(), 1e-6), max(caja.height(), 1e-6)
    escala = min((ancho - 2 * margen) / w, (alto - 2 * margen) / h)
    cx, cy = caja.center().x(), caja.center().y()
    return QgsRectangle(cx - ancho / 2 / escala, cy - alto / 2 / escala, cx + ancho / 2 / escala, cy + alto / 2 / escala)


def croquis_svg(elementos, ancho=640, alto=420, margen=24, vertices=False, foco=None, vecinas=(), fondo=None,
                atribucion='', encuadre=None):
    """
    Croquis de los recintos (SVG en línea), con el identificador de cada uno, la flecha del norte y una barra de escala.
      - vertices: numera los vértices del contorno exterior (de foco, o de todos) como la tabla de coordenadas, por fuera
        del recinto; se omiten los números que se montarían sobre otro.
      - foco: el recinto en el que se centra el croquis (los demás del GML salen más tenues).
      - vecinas: parcelas de alrededor (las catastrales colindantes), en gris con su referencia.
      - fondo: imagen JPEG o PNG (bytes) del encuadre exacto de vista_croquis(), debajo de todo (la ortofoto), con
        atribucion al pie.
      - encuadre: rectángulo del terreno que se muestra (un detalle), sin atenuar ningún recinto.
    """
    validas = _validas(elementos)
    vista = vista_croquis(validas, ancho, alto, margen, foco, encuadre)
    if vista is None:
        return ''
    escala = ancho / vista.width()

    def pantalla(x, y):
        return (x - vista.xMinimum()) * escala, (vista.yMaximum() - y) * escala

    def punto(x, y):
        px, py = pantalla(x, y)
        return f"{px:.1f},{py:.1f}"

    def trazado(geometria):
        poligonos = geometria.asMultiPolygon() if geometria.isMultipart() else [geometria.asPolygon()]
        return ' '.join('M ' + ' L '.join(punto(p.x(), p.y()) for p in anillo) + ' Z'
                        for poligono in poligonos for anillo in poligono if anillo), poligonos

    def etiqueta(geometria, texto, clase='etiqueta', estilo=''):
        dentro = geometria.intersection(QgsGeometry.fromRect(vista)) if foco is not None or encuadre is not None else geometria
        interior = dentro.pointOnSurface() if not dentro.isEmpty() else QgsGeometry()
        if interior.isNull() or interior.isEmpty():  #Anillo degenerado o fuera del encuadre: sin etiqueta, sin fallar (AU-08)
            return ''
        x, y = punto(interior.asPoint().x(), interior.asPoint().y()).split(',')
        giro = _giro_etiqueta(dentro, texto, escala)
        rotar = f' transform="rotate({giro:.1f} {x} {y})"' if giro else ''
        return f'<text x="{x}" y="{y}" text-anchor="middle" class="{clase}"{estilo}{rotar}>{escape(texto)}</text>'

    partes = [f'<svg viewBox="0 0 {ancho} {alto}" xmlns="http://www.w3.org/2000/svg" role="img" '
              f'aria-label="Croquis de los recintos" class="croquis">']
    con_fondo = bool(fondo)
    if con_fondo:
        tipo = 'png' if fondo[:4] == b'\x89PNG' else 'jpeg'
        partes.append(f'<image x="0" y="0" width="{ancho}" height="{alto}" preserveAspectRatio="none" '
                      f'href="data:image/{tipo};base64,{base64.b64encode(fondo).decode("ascii")}"/>')
    textos = []
    for v in _validas(vecinas):
        if not v.geometria.boundingBox().intersects(vista):
            continue
        d, _ = trazado(v.geometria)
        partes.append(f'<path d="{d}" fill="none" stroke="#868e96" stroke-width="1" fill-rule="evenodd"/>')
        textos.append(etiqueta(v.geometria, v.local_id, 'etiqueta', ' style="fill:#868e96;font-size:10px"'))
    numeros, ocupados = [], []  #Números ya puestos, para no montar uno sobre otro
    for i, e in enumerate(validas):
        color = getattr(e, 'color', None) or PALETA_CROQUIS[i % len(PALETA_CROQUIS)]
        trazo = ' stroke-dasharray="7 4"' if getattr(e, 'discontinua', False) else ''
        tenue = foco is not None and e is not foco
        d, poligonos = trazado(e.geometria)
        relleno = 0 if con_fondo else 0.06 if tenue else 0.15
        if con_fondo:  #Sobre la ortofoto: un halo blanco bajo el borde para que se vea en cualquier fondo
            partes.append(f'<path d="{d}" fill="none" stroke="#ffffff" stroke-width="{2 if tenue else 4.5}" '
                          'stroke-opacity="0.85" fill-rule="evenodd"/>')
        if trazo:  #Superpuesto a otro (comparación): sin relleno, para que se vean los dos contornos
            relleno = 0
        partes.append(f'<path d="{d}" fill="{color}" fill-opacity="{relleno}" stroke="{color}" '
                      f'stroke-width="{1.2 if tenue else 2.5 if con_fondo else 2}" fill-rule="evenodd"{trazo}/>')
        if vertices and (foco is None or e is foco) and poligonos and poligonos[0]:
            #El exterior y los huecos, con la numeración seguida (como la tabla de coordenadas: 1-11, hueco 12-15)
            primero = 1
            for n, anillo in enumerate(poligonos[0]):
                #Un hueco pequeño en el croquis (un patio de 1,5 m): solo los puntos, los números se leen en la tabla
                lado = max(max(p.x() for p in anillo) - min(p.x() for p in anillo),
                           max(p.y() for p in anillo) - min(p.y() for p in anillo)) * escala
                numeros += _numeros_vertices(e.geometria, anillo, color, escala, pantalla, ocupados, primero=primero,
                                             numerar=n == 0 or lado >= HUECO_NUMERADO)
                primero += len(anillo) - 1 if len(anillo) > 1 and anillo[0] == anillo[-1] else len(anillo)
        if e.local_id:
            textos.append(etiqueta(e.geometria, e.local_id))
    partes += textos + numeros
    #Norte (arriba: las coordenadas UTM tienen el norte de la cuadrícula hacia arriba) y barra de escala
    partes.append(f'<path d="M {ancho - 16},6 L {ancho - 21},20 L {ancho - 16},17 L {ancho - 11},20 Z" '
                  'style="fill:var(--texto);stroke:var(--fondo);stroke-width:1"/>'
                  f'<text x="{ancho - 16}" y="32" text-anchor="middle" class="etiqueta" style="font-size:11px">N</text>')
    metros = _escala_redonda((ancho - 2 * margen) / 4 / escala)
    if metros:
        largo = metros * escala
        texto = f'{metros:g} m'.replace('.', ',')
        partes.append(f'<path d="M 8,{alto - 12} V {alto - 7} H {8 + largo:.1f} V {alto - 12}" '
                      'style="fill:none;stroke:var(--texto);stroke-width:1.5"/>'
                      f'<text x="{12 + largo:.1f}" y="{alto - 6}" class="etiqueta" style="font-size:11px">{texto}</text>')
    if con_fondo and atribucion:
        partes.append(f'<text x="{ancho - 6}" y="{alto - 6}" text-anchor="end" class="etiqueta" style="font-size:10px">'
                      f'{escape(atribucion)}</text>')
    partes.append('</svg>')
    return ''.join(partes)


def _giro_etiqueta(geometria, texto, escala, ancho_letra=7.0):
    """
    Grados (SVG, horario) para escribir el identificador a lo largo de un recinto estrecho en el que no cabe en
    horizontal (una franja segregada, por ejemplo); 0 si cabe o si tampoco cabe a lo largo.
    """
    caja = geometria.orientedMinimumBoundingBox()[0]
    anillo = caja.asPolygon()[0] if not caja.isNull() and caja.asPolygon() else []
    if len(anillo) < 3:
        return 0
    lados = [(anillo[1].x() - anillo[0].x(), anillo[1].y() - anillo[0].y()),
             (anillo[2].x() - anillo[1].x(), anillo[2].y() - anillo[1].y())]
    largo, corto = sorted(lados, key=lambda v: -math.hypot(*v))
    necesario = len(texto) * ancho_letra
    if math.hypot(*corto) * escala >= necesario or math.hypot(*largo) * escala < necesario:
        return 0
    grados = -math.degrees(math.atan2(largo[1], largo[0]))  #En pantalla la y crece hacia abajo
    if grados > 90:
        grados -= 180
    elif grados <= -90:
        grados += 180
    return 0 if abs(grados) < 3 else grados


HUECO_NUMERADO = 40  #px: un hueco más pequeño en el croquis lleva sus vértices sin número (no caben)


def _numeros_vertices(geometria, anillo, color, escala, pantalla, hecho, separacion=11, primero=1, numerar=True):
    """
    Puntos y números de los vértices de un anillo, por fuera del recinto (bisectriz del ángulo; en un hueco, dentro de
    él). primero: número del primer vértice (los huecos siguen la numeración del exterior).
    """
    puntos = list(anillo[:-1]) if len(anillo) > 1 and anillo[0] == anillo[-1] else list(anillo)
    n = len(puntos)
    partes = []
    desplazamiento = 10 / escala  #10 px en metros
    for k, p in enumerate(puntos):
        x, y = pantalla(p.x(), p.y())
        partes.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.2" fill="{color}" stroke="#ffffff" stroke-width="0.8"/>')
        anterior, siguiente = puntos[k - 1], puntos[(k + 1) % n]
        u = [anterior.x() - p.x(), anterior.y() - p.y()]
        v = [siguiente.x() - p.x(), siguiente.y() - p.y()]
        lu, lv = math.hypot(*u) or 1, math.hypot(*v) or 1
        bx, by = u[0] / lu + v[0] / lv, u[1] / lu + v[1] / lv
        if math.hypot(bx, by) < 1e-6:  #Vértice en línea recta: perpendicular al lado
            bx, by = -v[1] / lv, v[0] / lv
        lb = math.hypot(bx, by)
        bx, by = bx / lb, by / lb
        #La bisectriz apunta hacia dentro en un ángulo convexo: el número va al otro lado (por fuera)
        if geometria.contains(QgsPointXY(p.x() + bx * desplazamiento / 3, p.y() + by * desplazamiento / 3)):
            bx, by = -bx, -by
        tx, ty = pantalla(p.x() + bx * desplazamiento, p.y() + by * desplazamiento)
        if not numerar or any(math.hypot(tx - hx, ty - hy) < separacion for hx, hy in hecho):
            continue
        hecho.append((tx, ty))
        partes.append(f'<text x="{tx:.1f}" y="{ty + 4:.1f}" text-anchor="middle" class="etiqueta" '
                      f'style="fill:{color};font-size:10.5px;font-weight:600">{k + primero}</text>')
    return partes


def coordenadas_html(elemento):
    """Tabla de vértices de cada anillo, numerados, con 2 decimales."""
    filas, primero = [], 1
    for i, (anillo, rol) in enumerate(zip(elemento.anillos, elemento.roles or ['exterior'] * len(elemento.anillos))):
        nombre = 'Exterior' if rol == 'exterior' else f'Hueco {i}'
        vertices = anillo[:-1] if len(anillo) > 1 and anillo[0] == anillo[-1] else anillo
        filas.append(f'<tr class="anillo"><th colspan="3">{nombre} · {len(vertices)} vértices</th></tr>')
        filas += [f'<tr><td>{n}</td><td>{geo.formatear(x)}</td><td>{geo.formatear(y)}</td></tr>'
                  for n, (x, y) in enumerate(vertices, start=primero)]
        primero += len(vertices)  #Los huecos siguen la numeración: no hay dos vértices con el mismo número
    return ('<table class="coord"><thead><tr><th>Nº</th><th>X</th><th>Y</th></tr></thead><tbody>'
            + ''.join(filas) + '</tbody></table>')


def seccion_identidad(r):
    """
    Sección de la simulación de identidad gráfica (AU-58): veredicto, medidas y dos croquis, el general y otro ampliado en
    el tramo que más se separa (en el general, con parcelas de decenas de metros, unos centímetros no se ven). Margen en
    azul, parcela catastral en gris discontinuo, GML en naranja y lo que queda fuera del margen en rojo.
    """
    if r is None or r.referencia is None:
        return ''
    from types import SimpleNamespace

    from . import identidad as idg
    elementos = [SimpleNamespace(geometria=r.banda, local_id='', color='#4dabf7'),
                 SimpleNamespace(geometria=r.referencia, local_id=', '.join(r.catastrales), color='#495057',
                                 discontinua=True),
                 SimpleNamespace(geometria=r.rgga, local_id='', color='#e8590c')]
    if r.tramos:
        fuera = idg.exterior(r.rgga).difference(r.banda).buffer(max(0.04, r.margen * 0.12), 4)
        elementos.append(SimpleNamespace(geometria=fuera, local_id='', color='#c92a2a'))
    color = '#2b8a3e' if r.cumple else '#c92a2a'
    lineas = ''.join(f'<li>{escape(x)}</li>' for x in idg.resumen(r)[1:])
    partes = ['<h2>Identidad gráfica (simulación)</h2>',
              f'<div class="resultado" style="border-color:{color}"><b style="color:{color}">'
              f'{escape(idg.veredicto(r))}</b> · {escape(idg.resumen(r)[0])}</div>',
              f'<ul>{lineas}</ul>',
              '<p class="meta">Criterio del anexo II de la Resolución conjunta DGSJFP-DGC de 23/09/2020 (BOE-A-2020-12111): '
              'la línea exterior del GML dentro de ±0,50 m del perímetro catastral en cartografía urbana o ±2,00 m en '
              'rústica, y una diferencia de superficie de como mucho el 5 %. En azul, el margen; en gris, la parcela '
              'catastral; en naranja, el GML; en rojo, lo que queda fuera del margen. <b>Simulación no oficial</b>: el '
              'resultado válido es el de la Sede Electrónica del Catastro (Identidad de parcela).</p>',
              croquis_svg(elementos, alto=440)]
    if r.tramos:
        t = r.tramos[0]
        lado = max(8 * r.margen, 3 * t.distancia, 4.0)
        partes.append(f'<p class="meta">Detalle del tramo que más se separa ({idg._m(t.distancia)} m, cerca de X '
                      f'{t.x:.2f}, Y {t.y:.2f}):</p>')
        partes.append(croquis_svg(elementos, alto=360,
                                  encuadre=QgsRectangle(t.x - lado, t.y - lado, t.x + lado, t.y + lado)))
    return '\n'.join(partes) + '\n'


def html(informe, ahora=None, consulta=None, identidad=None):
    """
    Texto HTML del informe de comprobación. consulta: fecha y hora en que se compararon los datos con los de la Dirección
    General del Catastro (None si no se ha comparado). identidad: core.identidad.Resultado de la comparación, para la
    sección de la simulación de identidad gráfica.
    """
    ahora = ahora or datetime.datetime.now()
    lectura = informe.lectura
    n_err, n_av = len(informe.errores), len(informe.avisos)
    estado_global = ERROR if n_err else AVISO if n_av else 'correcta'
    simbolo = '✖' if n_err else '⚠' if n_av else '✔'
    nombre = os.path.basename(informe.ruta)

    filas = []
    for e in lectura.elementos:
        estado = informe.estado(e.local_id)
        calculada = '' if e.geometria.isNull() else geo.redondear_m2(e.geometria.area())
        vertices = sum(max(len(a) - 1, 0) for a in e.anillos)
        filas.append(
            f'<tr><td>{escape(e.tipo.capitalize())}</td><td class="id">{escape(e.local_id)}</td>'
            f'<td>{escape(e.namespace)}</td><td>{escape(e.label)}</td>'
            f'<td class="num">{"" if e.area_declarada is None else e.area_declarada}</td><td class="num">{calculada}</td>'
            f'<td class="num">{vertices}</td><td style="color:{COLORES[estado]}"><b>{TEXTO_ESTADO[estado]}</b></td></tr>')

    incidencias = []
    for nivel in (ERROR, AVISO, INFO):
        for inc in [i for i in informe.incidencias if i.nivel == nivel and i.codigo != 'GML-LEIDO']:
            donde = f'<b>{escape(inc.elemento)}</b>: ' if inc.elemento else ''
            incidencias.append(f'<li class="{nivel}"><span class="nivel">{NIVEL[nivel]}</span> {donde}{escape(inc.mensaje)} '
                               f'<code>{escape(inc.codigo)}</code></li>')

    detalle = ''.join(f'<details><summary>{escape(e.local_id)} · {escape(e.namespace)}</summary>{coordenadas_html(e)}</details>'
                      for e in lectura.elementos if e.anillos)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Informe de comprobación · {escape(nombre)}</title>
<style>
  :root {{ --fondo:#ffffff; --texto:#1d2327; --suave:#f1f3f5; --linea:#dee2e6; --acento:#1f6f78; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --fondo:#15191b; --texto:#e6eaeb; --suave:#1e2426; --linea:#343a40; }} }}
  body {{ font-family:"Segoe UI",Arial,sans-serif; max-width:980px; margin:0 auto; padding:16px; background:var(--fondo);
         color:var(--texto); line-height:1.45; }}
  h1 {{ color:var(--acento); margin:0 0 4px; font-size:1.5em; }}
  h2 {{ color:var(--acento); border-bottom:2px solid var(--suave); padding-bottom:4px; margin-top:28px; font-size:1.15em; }}
  .meta {{ opacity:.8; font-size:.92em; }}
  .resultado {{ border-left:6px solid {COLORES[estado_global]}; background:var(--suave); padding:10px 14px; margin:16px 0;
               font-size:1.1em; }}
  .resultado b {{ color:{COLORES[estado_global]}; }}
  .aviso-legal {{ font-size:.88em; opacity:.85; }}
  table {{ border-collapse:collapse; width:100%; font-size:.93em; }}
  th, td {{ border-bottom:1px solid var(--linea); padding:5px 8px; text-align:left; }}
  th {{ background:var(--suave); }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  td.id {{ font-family:Consolas,monospace; }}
  ul.inc {{ list-style:none; padding:0; }}
  ul.inc li {{ padding:6px 10px; border-left:4px solid var(--linea); margin-bottom:4px; background:var(--suave); }}
  ul.inc li.error {{ border-color:{COLORES[ERROR]}; }} ul.inc li.aviso {{ border-color:{COLORES[AVISO]}; }}
  .nivel {{ font-weight:bold; margin-right:4px; }} li.error .nivel {{ color:{COLORES[ERROR]}; }}
  li.aviso .nivel {{ color:{COLORES[AVISO]}; }}
  code {{ font-size:.82em; opacity:.7; }}
  .croquis {{ display:block; width:100%; max-width:760px; margin:0 auto; background:var(--suave); border-radius:6px; }}
  .etiqueta {{ font-size:12px; fill:var(--texto); paint-order:stroke; stroke:var(--fondo); stroke-width:3px; }}
  details {{ margin:6px 0; }} summary {{ cursor:pointer; font-weight:bold; }}
  table.coord {{ width:auto; min-width:320px; margin:6px 0 12px; }} tr.anillo th {{ background:none; font-style:italic; }}
  footer {{ margin-top:32px; font-size:.85em; opacity:.75; border-top:1px solid var(--linea); padding-top:8px; }}
  @media print {{ details {{ display:block; }} details > * {{ display:block; }} }}
</style>
</head>
<body>
<h1>Informe de comprobación de GML</h1>
<p class="aviso-legal"><b>No es un documento oficial</b> ni tiene código seguro de verificación (CSV): no sustituye al
informe de validación gráfica ni al ICUC de la Sede Electrónica del Catastro.</p>
<div class="meta">{escape(nombre)} · {escape(lectura.version or '?')} · {len(lectura.elementos)} elemento{'s' if len(lectura.elementos) != 1 else ''}
{f'· EPSG:{lectura.epsg}' if lectura.epsg else ''} · {ahora:%d/%m/%Y %H:%M}</div>
<div class="resultado"><b>{simbolo} {escape(resumen(informe))}</b></div>
<p class="aviso-legal">⚠ {escape(AVISO_LEGAL)} Este informe recoge las comprobaciones conocidas; la Sede puede aplicar otras.</p>
{f'<p class="meta">Comparación con los datos públicos de la {escape(FUENTE_DGC)} consultados el {consulta:%d/%m/%Y a las %H:%M}.</p>' if consulta else '<p class="meta">Sin comparar con los datos del Catastro.</p>'}

<h2>Parcelas y construcciones</h2>
<table>
<thead><tr><th>Tipo</th><th>Identificador</th><th>Namespace</th><th>Nº parcela</th><th>Sup. GML m²</th>
<th>Sup. calculada m²</th><th>Vértices</th><th>Estado</th></tr></thead>
<tbody>{''.join(filas)}</tbody>
</table>

<h2>Incidencias</h2>
{('<ul class="inc">' + ''.join(incidencias) + '</ul>') if incidencias else '<p>Ninguna.</p>'}

<h2>Croquis</h2>
{croquis_svg(lectura.elementos)}
{seccion_identidad(identidad)}
<h2>Coordenadas</h2>
<p class="meta">Coordenadas UTM en metros{f' (EPSG:{lectura.epsg})' if lectura.epsg else ''}, tal como están en el fichero.</p>
{detalle or '<p>Sin geometrías.</p>'}

<footer>Generado con {escape(NOMBRE)} {escape(version())} (herramienta no oficial, GPL-2.0-or-later) a partir del fichero
<code>{escape(informe.ruta)}</code>.</footer>
</body>
</html>
"""


def escribir(informe, ruta=None, consulta=None, identidad=None):
    """Escribe el informe HTML (por defecto junto al GML) y devuelve su ruta; lanza OSError si no se puede escribir."""
    ruta = ruta or ruta_por_defecto(informe.ruta)
    problema = escribir_texto(ruta, html(informe, consulta=consulta, identidad=identidad), 'utf-8')
    if problema is not None:
        raise OSError(problema.mensaje)
    return ruta
