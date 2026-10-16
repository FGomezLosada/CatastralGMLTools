"""
Informe de comprobación en HTML (no oficial): un único fichero autocontenido (sin internet ni librerías externas) con el resultado,
la tabla de parcelas o construcciones, las incidencias, un croquis en SVG y la lista de coordenadas de cada recinto.
Sirve para guardarlo junto al GML o adjuntarlo a un expediente.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import datetime
import math
import os
from html import escape

from qgis.core import QgsPointXY

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


def croquis_svg(elementos, ancho=640, alto=420, margen=24, vertices=False):
    """
    Croquis de los recintos (SVG en línea), con el identificador en el punto interior de cada uno, la flecha del norte y
    una barra de escala. vertices: además, los vértices del contorno exterior numerados como en la tabla de coordenadas
    (por dentro del recinto; se omiten los números que se montarían sobre otro).
    """
    geometrias = [e for e in elementos if not e.geometria.isNull() and not e.geometria.isEmpty()]
    if not geometrias:
        return ''
    caja = geometrias[0].geometria.boundingBox()
    for e in geometrias[1:]:
        caja.combineExtentWith(e.geometria.boundingBox())
    w, h = max(caja.width(), 1e-6), max(caja.height(), 1e-6)
    escala = min((ancho - 2 * margen) / w, (alto - 2 * margen) / h)
    dx = (ancho - w * escala) / 2
    dy = (alto - h * escala) / 2

    def pantalla(x, y):
        return dx + (x - caja.xMinimum()) * escala, dy + (caja.yMaximum() - y) * escala

    def punto(x, y):
        px, py = pantalla(x, y)
        return f"{px:.1f},{py:.1f}"

    partes = [f'<svg viewBox="0 0 {ancho} {alto}" xmlns="http://www.w3.org/2000/svg" role="img" '
              f'aria-label="Croquis de los recintos" class="croquis">']
    numeros, ocupados = [], []  #Números ya puestos (de todos los recintos), para no montar uno sobre otro
    for i, e in enumerate(geometrias):
        color = PALETA_CROQUIS[i % len(PALETA_CROQUIS)]
        poligonos = e.geometria.asMultiPolygon() if e.geometria.isMultipart() else [e.geometria.asPolygon()]
        for poligono in poligonos:
            d = ' '.join('M ' + ' L '.join(punto(p.x(), p.y()) for p in anillo) + ' Z' for anillo in poligono)
            partes.append(f'<path d="{d}" fill="{color}" fill-opacity="0.15" stroke="{color}" stroke-width="2" '
                          'fill-rule="evenodd"/>')
        if vertices and poligonos and poligonos[0]:
            numeros += _numeros_vertices(e.geometria, poligonos[0][0], color, escala, pantalla, ocupados)
        interior = e.geometria.pointOnSurface()
        if interior.isNull():  #Anillo degenerado (2 vértices, todos alineados…): sin etiqueta, pero sin fallar (AU-08)
            continue
        centro = interior.asPoint()
        x, y = punto(centro.x(), centro.y()).split(',')
        partes.append(f'<text x="{x}" y="{y}" text-anchor="middle" class="etiqueta">{escape(e.local_id)}</text>')
    partes += numeros
    #Norte (arriba: las coordenadas UTM tienen el norte de la cuadrícula hacia arriba) y barra de escala
    partes.append(f'<g style="fill:var(--texto);stroke:none"><path d="M {ancho - 16},6 L {ancho - 21},20 L {ancho - 16},17 '
                  f'L {ancho - 11},20 Z"/><text x="{ancho - 16}" y="32" text-anchor="middle" font-size="11">N</text></g>')
    metros = _escala_redonda((ancho - 2 * margen) / 4 / escala)
    if metros:
        largo = metros * escala
        texto = f'{metros:g} m'.replace('.', ',')
        partes.append(f'<g style="fill:var(--texto);stroke:var(--texto)"><path d="M 8,{alto - 12} V {alto - 7} '
                      f'H {8 + largo:.1f} V {alto - 12}" fill="none" stroke-width="1.5"/>'
                      f'<text x="{12 + largo:.1f}" y="{alto - 6}" font-size="11" stroke="none">{texto}</text></g>')
    partes.append('</svg>')
    return ''.join(partes)


def _numeros_vertices(geometria, anillo, color, escala, pantalla, hecho, separacion=11):
    """Puntos y números de los vértices de un anillo exterior, desplazados hacia dentro por la bisectriz del ángulo."""
    puntos = list(anillo[:-1]) if len(anillo) > 1 and anillo[0] == anillo[-1] else list(anillo)
    n = len(puntos)
    partes = []
    desplazamiento = 9 / escala  #9 px en metros
    for k, p in enumerate(puntos):
        x, y = pantalla(p.x(), p.y())
        partes.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2" fill="{color}"/>')
        anterior, siguiente = puntos[k - 1], puntos[(k + 1) % n]
        u = [anterior.x() - p.x(), anterior.y() - p.y()]
        v = [siguiente.x() - p.x(), siguiente.y() - p.y()]
        lu, lv = math.hypot(*u) or 1, math.hypot(*v) or 1
        bx, by = u[0] / lu + v[0] / lv, u[1] / lu + v[1] / lv
        if math.hypot(bx, by) < 1e-6:  #Vértice en línea recta: perpendicular al lado
            bx, by = -v[1] / lv, v[0] / lv
        lb = math.hypot(bx, by)
        bx, by = bx / lb, by / lb
        if not geometria.contains(QgsPointXY(p.x() + bx * desplazamiento / 3, p.y() + by * desplazamiento / 3)):
            bx, by = -bx, -by
        tx, ty = pantalla(p.x() + bx * desplazamiento, p.y() + by * desplazamiento)
        if any(math.hypot(tx - hx, ty - hy) < separacion for hx, hy in hecho):
            continue
        hecho.append((tx, ty))
        partes.append(f'<text x="{tx:.1f}" y="{ty + 4:.1f}" text-anchor="middle" font-size="10" '
                      f'class="etiqueta" style="fill:{color}">{k + 1}</text>')
    return partes


def coordenadas_html(elemento):
    """Tabla de vértices de cada anillo, numerados, con 2 decimales."""
    filas = []
    for i, (anillo, rol) in enumerate(zip(elemento.anillos, elemento.roles or ['exterior'] * len(elemento.anillos))):
        nombre = 'Exterior' if rol == 'exterior' else f'Hueco {i}'
        vertices = anillo[:-1] if len(anillo) > 1 and anillo[0] == anillo[-1] else anillo
        filas.append(f'<tr class="anillo"><th colspan="3">{nombre} · {len(vertices)} vértices</th></tr>')
        filas += [f'<tr><td>{n}</td><td>{geo.formatear(x)}</td><td>{geo.formatear(y)}</td></tr>'
                  for n, (x, y) in enumerate(vertices, start=1)]
    return ('<table class="coord"><thead><tr><th>Nº</th><th>X</th><th>Y</th></tr></thead><tbody>'
            + ''.join(filas) + '</tbody></table>')


def html(informe, ahora=None, consulta=None):
    """
    Texto HTML del informe de comprobación. consulta: fecha y hora en que se compararon los datos con los de la Dirección
    General del Catastro (None si no se ha comparado).
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
  .croquis {{ width:100%; max-height:440px; background:var(--suave); border-radius:6px; }}
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

<h2>Coordenadas</h2>
<p class="meta">Coordenadas UTM en metros{f' (EPSG:{lectura.epsg})' if lectura.epsg else ''}, tal como están en el fichero.</p>
{detalle or '<p>Sin geometrías.</p>'}

<footer>Generado con {escape(NOMBRE)} {escape(version())} (herramienta no oficial, GPL-2.0-or-later) a partir del fichero
<code>{escape(informe.ruta)}</code>.</footer>
</body>
</html>
"""


def escribir(informe, ruta=None, consulta=None):
    """Escribe el informe HTML (por defecto junto al GML) y devuelve su ruta; lanza OSError si no se puede escribir."""
    ruta = ruta or ruta_por_defecto(informe.ruta)
    problema = escribir_texto(ruta, html(informe, consulta=consulta), 'utf-8')
    if problema is not None:
        raise OSError(problema.mensaje)
    return ruta
