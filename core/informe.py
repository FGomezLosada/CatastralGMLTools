"""
Informe de validación en HTML: un único fichero autocontenido (sin internet ni librerías externas) con el resultado,
la tabla de parcelas o construcciones, las incidencias, un croquis en SVG y la lista de coordenadas de cada recinto.
Sirve para guardarlo junto al GML o adjuntarlo a un expediente.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import datetime
import os
from html import escape

from . import geometria as geo
from .incidencias import AVISO, ERROR, INFO
from .info import AVISO_LEGAL, NOMBRE, version
from .validador import resumen

COLORES = {ERROR: '#c92a2a', AVISO: '#e67700', 'correcta': '#2b8a3e'}
TEXTO_ESTADO = {ERROR: 'Con errores', AVISO: 'Con avisos', 'correcta': 'Correcta'}
NIVEL = {ERROR: 'Error', AVISO: 'Aviso', INFO: 'Información'}
PALETA_CROQUIS = ('#e8590c', '#1971c2', '#2b8a3e', '#9c36b5', '#c92a2a', '#0c8599', '#e67700', '#5c940d')


def ruta_por_defecto(ruta_gml):
    """Informe junto al GML: segregacion.gml → segregacion_informe.html."""
    base, _ = os.path.splitext(ruta_gml)
    return f"{base}_informe.html"


def croquis_svg(elementos, ancho=640, alto=420, margen=24):
    """Croquis de los recintos (SVG en línea), con el identificador en el punto interior de cada uno."""
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

    def punto(x, y):
        return f"{dx + (x - caja.xMinimum()) * escala:.1f},{dy + (caja.yMaximum() - y) * escala:.1f}"

    partes = [f'<svg viewBox="0 0 {ancho} {alto}" xmlns="http://www.w3.org/2000/svg" role="img" '
              f'aria-label="Croquis de los recintos" class="croquis">']
    for i, e in enumerate(geometrias):
        color = PALETA_CROQUIS[i % len(PALETA_CROQUIS)]
        poligonos = e.geometria.asMultiPolygon() if e.geometria.isMultipart() else [e.geometria.asPolygon()]
        for poligono in poligonos:
            d = ' '.join('M ' + ' L '.join(punto(p.x(), p.y()) for p in anillo) + ' Z' for anillo in poligono)
            partes.append(f'<path d="{d}" fill="{color}" fill-opacity="0.15" stroke="{color}" stroke-width="2" '
                          'fill-rule="evenodd"/>')
        centro = e.geometria.pointOnSurface().asPoint()
        x, y = punto(centro.x(), centro.y()).split(',')
        partes.append(f'<text x="{x}" y="{y}" text-anchor="middle" class="etiqueta">{escape(e.local_id)}</text>')
    partes.append('</svg>')
    return ''.join(partes)


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


def html(informe, ahora=None):
    """Texto HTML del informe de validación."""
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
<title>Informe de validación · {escape(nombre)}</title>
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
<h1>Informe de validación de GML</h1>
<div class="meta">{escape(nombre)} · {escape(lectura.version or '?')} · {len(lectura.elementos)} elemento{'s' if len(lectura.elementos) != 1 else ''}
{f'· EPSG:{lectura.epsg}' if lectura.epsg else ''} · {ahora:%d/%m/%Y %H:%M}</div>
<div class="resultado"><b>{simbolo} {escape(resumen(informe))}</b></div>
<p class="aviso-legal">⚠ {escape(AVISO_LEGAL)} Este informe recoge las comprobaciones conocidas; la Sede puede aplicar otras.</p>

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


def escribir(informe, ruta=None):
    """Escribe el informe HTML (por defecto junto al GML) y devuelve su ruta."""
    ruta = ruta or ruta_por_defecto(informe.ruta)
    with open(ruta, 'w', encoding='utf-8', newline='\n') as f:
        f.write(html(informe))
    return ruta
