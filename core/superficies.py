"""
Informe de superficies y coordenadas de un GML de parcela (fase 11, AU-55): un HTML autocontenido para acompañar la
descripción de las fincas (escritura, expediente, encargo) con, por cada parcela:

  - superficie en proyección UTM (la del GML y la del Catastro) y sobre el elipsoide GRS80 (la del terreno sin relieve);
  - perímetro, vértices numerados con sus coordenadas y la longitud de cada lado;
  - linderos: con qué linda cada tramo del contorno (otras parcelas del GML, parcelas catastrales colindantes o suelo
    sin parcela, como la vía pública) y hacia dónde (N, NE, E…), con su longitud.

Si se indica la cabida inscrita (o la del título), se compara con la superficie total del GML y se recuerdan los
umbrales de la Ley Hipotecaria (texto consolidado, BOE-A-1946-2453): art. 9.b, correspondencia si las diferencias de
cabida no exceden del 10 % de la inscrita; art. 201.3.a, sin expediente hasta el 10 % con certificación catastral
descriptiva y gráfica de plena coincidencia; art. 201.3.b, rectificación hasta el 5 %. El informe no lo decide: lo
valora el registrador.

No es un documento oficial (pie del informe). Sin interfaz: la consulta de las colindantes la hace quien llama (en una
QgsTask) con comparacion.parcelas_catastrales.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import datetime
import math
import os
import re
from dataclasses import dataclass, field
from html import escape

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext,
    QgsDistanceArea,
    QgsGeometry,
    QgsPointXY,
)

from . import geometria as geo
from .ficheros import escribir_texto
from .info import AVISO_LEGAL, FUENTE_DGC, NOMBRE, version
from .servicios import ATRIBUCION_PNOA

TOCA = 0.05            #m: un tramo del contorno linda con otra parcela si está a menos de 5 cm de ella
MINIMO_LINDERO = 0.10  #m: tramos más cortos no son un lindero propio: van con el de al lado (esquinas, redondeos)
SOLAPE = 1.0           #m²: una catastral que se solapa más con la parcela no es colindante (es la de origen)
RUMBOS = ('N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO')
SIN_PARCELA = "Suelo sin parcela catastral (vía pública u otro dominio)"
HUECO = "Hueco {n} de la parcela (patio u otro suelo que no es de ella)"
UMBRALES = ((5.0, "art. 201.3.b: rectificación de superficie sin expediente si la diferencia no excede del 5 %"),
            (10.0, "art. 9.b: correspondencia de la representación gráfica si las diferencias de cabida no exceden del "
                   "10 %; art. 201.3.a: sin expediente hasta el 10 % con certificación catastral descriptiva y gráfica "
                   "de plena coincidencia"))


@dataclass
class Lindero:
    con: str          #Identificador de la parcela colindante, o SIN_PARCELA
    tipo: str         #'gml', 'catastral' o 'sin parcela'
    longitud: float   #m de contorno compartido
    rumbo: str        #N, NE, E…: hacia donde da el lado (normal exterior)


@dataclass
class Ficha:
    local_id: str
    namespace: str
    label: str
    area_utm: float
    area_elipsoide: float
    perimetro: float
    anillos: list = field(default_factory=list)   #[(rol, [(x, y), …])] sin repetir el primer vértice al final
    linderos: list = field(default_factory=list)


def ruta_por_defecto(ruta_gml):
    base, _ = os.path.splitext(ruta_gml)
    return f"{base}_superficies.html"


def _anillos(geometria):
    poligono = geometria.asMultiPolygon()[0] if geometria.isMultipart() else geometria.asPolygon()
    resultado = []
    for i, anillo in enumerate(poligono):
        puntos = [(p.x(), p.y()) for p in anillo]
        if len(puntos) > 1 and puntos[0] == puntos[-1]:
            puntos = puntos[:-1]
        resultado.append(('Exterior' if i == 0 else f'Hueco {i}', puntos))
    return resultado


def rumbo_normal(a, b, horario):
    """Rumbo hacia fuera de la parcela del lado a→b (normal exterior), según el sentido del anillo."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    nx, ny = (-dy, dx) if horario else (dy, -dx)  #Horario: el exterior queda a la izquierda del avance
    azimut = math.degrees(math.atan2(nx, ny)) % 360
    return RUMBOS[int((azimut + 22.5) // 45) % 8]


def linderos(parcela, otras, catastrales):
    """
    Linderos de una parcela (QgsGeometry), lado a lado del contorno exterior y de los huecos: cada tramo se asigna a la primera que lo
    toque (a menos de TOCA) de las otras parcelas del GML [(id, geometría)] y de las catastrales colindantes
    [(rc, geometría)] (las que se solapan con la parcela son las de origen y no cuentan); lo que no toca a ninguna es
    suelo sin parcela. Si catastrales es None (sin consultar el Catastro), ese resto no se asigna. Los restos de menos
    de MINIMO_LINDERO (esquinas, redondeos) van con el tramo de al lado, para que los linderos sumen el perímetro (prueba a
    mano del 16/10/2026: se perdían 8 cm de un lado corto). El rumbo de cada tramo es la normal exterior de su lado (el
    lado norte de un rectángulo linda «al N»; el de un hueco, hacia el hueco). Se suman por colindante y rumbo.
    """
    poligono = parcela.asMultiPolygon()[0] if parcela.isMultipart() else parcela.asPolygon()
    candidatos = [(i, g.buffer(TOCA, 4), 'gml') for i, g in otras]
    for rc, g in catastrales or []:
        if g.intersection(parcela).area() <= SOLAPE:
            candidatos.append((rc, g.buffer(TOCA, 4), 'catastral'))
    suma = {}

    def sumar(clave, longitud):
        suma[clave] = suma.get(clave, 0.0) + longitud

    #El contorno exterior y el de cada hueco (patio): el perímetro de la parcela incluye los huecos, y los linderos deben
    #sumarlo. En un hueco la parcela queda fuera del anillo: el lado da hacia dentro de él (hacia el patio)
    for n, anillo in enumerate(poligono):
        puntos = [(p.x(), p.y()) for p in anillo]
        doble_area = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(puntos, puntos[1:]))
        horario = (doble_area < 0) if n == 0 else (doble_area >= 0)
        if n == 0:
            _linderos_anillo(puntos, horario, candidatos, catastrales is not None, sumar)
        else:  #Lo que no es otra parcela es el propio hueco: se sabe aunque no se consulte el Catastro
            _linderos_anillo(puntos, horario, candidatos, True, sumar, (HUECO.format(n=n), 'hueco'))
    orden = {r: n for n, r in enumerate(RUMBOS)}
    resultado = [Lindero(ident, tipo, longitud, hacia) for (ident, tipo, hacia), longitud in suma.items()]
    return sorted(resultado, key=lambda li: (orden[li.rumbo], -li.longitud))


def _linderos_anillo(puntos, horario, candidatos, consultado, sumar, sin=(SIN_PARCELA, 'sin parcela')):
    """
    Linderos de un anillo, lado a lado (ver linderos): sumar(clave, longitud) con clave (colindante, tipo, rumbo). sin: a
    quién va lo que no toca a ninguna parcela (el suelo sin parcela, o el propio hueco en un anillo interior).
    """
    ultima = None      #Clave del último tramo asignado (los restos de centímetros van con él)
    pendiente = 0.0    #Restos antes del primer tramo asignado: van con el último (el anillo es cerrado)
    for a, b in zip(puntos, puntos[1:]):
        lado = QgsGeometry.fromPolylineXY([QgsPointXY(*a), QgsPointXY(*b)])
        largo = lado.length()
        if largo < 1e-9:
            continue
        hacia = rumbo_normal(a, b, horario)
        libre = lado
        mayor = None  #(longitud, clave) del tramo más largo de este lado
        #Primero la colindante que más comparte este lado: la esquina de otra (a menos de TOCA) no le quita centímetros
        tocan = sorted(((lado.intersection(zona).length(), ident, zona, tipo) for ident, zona, tipo in candidatos),
                       key=lambda t: -t[0])
        for compartido, ident, zona, tipo in tocan:
            if libre.isEmpty() or libre.length() < 1e-6:
                break
            #Tocar solo la esquina (unos centímetros) no es lindar; pero un lado corto entero con una parcela, sí
            if compartido < MINIMO_LINDERO and (mayor is not None or compartido < largo / 2):
                break
            tramo = libre.intersection(zona)
            if tramo.isEmpty() or tramo.length() < 1e-6:
                continue
            clave = (ident, tipo, hacia)
            sumar(clave, tramo.length())
            if mayor is None or tramo.length() > mayor[0]:
                mayor = (tramo.length(), clave)
            libre = libre.difference(zona)
        resto = 0.0 if libre.isEmpty() else libre.length()
        if resto >= MINIMO_LINDERO:
            if consultado:
                mayor = (resto, (*sin, hacia))
                sumar(mayor[1], resto)
            else:
                ultima = None  #Sin consultar el Catastro, el resto no se asigna (ni sus centímetros)
                continue
        elif resto > 1e-6 and consultado:
            #Centímetros sueltos (esquinas, redondeos): con el tramo de al lado, para que los linderos sumen el perímetro
            destino = mayor[1] if mayor is not None else ultima
            if destino is None:
                pendiente += resto
            else:
                sumar(destino, resto)
        if mayor is not None:
            ultima = mayor[1]
    if pendiente and ultima is not None:
        sumar(ultima, pendiente)


def fichas(lectura, catastrales=None):
    """Una Ficha por parcela del GML (lectura de gml_lector). catastrales: [(rc, geometría)] en el SRC del GML, o None."""
    medidor = QgsDistanceArea()
    medidor.setSourceCrs(QgsCoordinateReferenceSystem(f'EPSG:{lectura.epsg}'), QgsCoordinateTransformContext())
    medidor.setEllipsoid('GRS80')
    parcelas = [e for e in lectura.elementos if not e.geometria.isNull() and not e.geometria.isEmpty()]
    resultado = []
    for e in parcelas:
        otras = [(o.local_id, o.geometria) for o in parcelas if o is not e]
        resultado.append(Ficha(e.local_id, e.namespace, e.label, e.geometria.area(), medidor.measureArea(e.geometria),
                               e.geometria.constGet().perimeter(), _anillos(e.geometria),
                               linderos(e.geometria, otras, catastrales)))
    return resultado


def _num(valor, decimales=2):
    return f"{valor:,.{decimales}f}".replace(',', ' ').replace('.', ',')


def _coordenadas(ficha):
    filas, primero = [], 1
    for rol, puntos in ficha.anillos:
        filas.append(f'<tr class="anillo"><th colspan="4">{rol} · {len(puntos)} vértices</th></tr>')
        for k, (x, y) in enumerate(puntos):
            n = primero + k  #Los huecos siguen la numeración del exterior, como en el croquis
            sx, sy = puntos[(k + 1) % len(puntos)]
            filas.append(f'<tr><td>{n}</td><td class="num">{geo.formatear(x)}</td><td class="num">{geo.formatear(y)}</td>'
                         f'<td class="num">{_num(math.hypot(sx - x, sy - y))}</td></tr>')
        primero += len(puntos)
    return ('<table class="coord"><thead><tr><th>Nº</th><th>X</th><th>Y</th><th>Lado hasta el siguiente (m)</th></tr></thead>'
            '<tbody>' + ''.join(filas) + '</tbody></table>')


def _linderos(ficha, consultado):
    if not ficha.linderos:
        return ('<p>Sin linderos calculados' + ('' if consultado else ' (no se ha consultado el Catastro)') + '.</p>')
    filas = [f'<tr><td>{li.rumbo}</td><td class="id">{escape(li.con)}</td>'
             f'<td>{"del GML" if li.tipo == "gml" else "catastral" if li.tipo == "catastral" else ""}</td>'
             f'<td class="num">{_num(li.longitud)}</td></tr>' for li in ficha.linderos]
    pie = ''
    if consultado:  #Con el Catastro, todo el contorno está asignado: la suma es el perímetro (comprobación a la vista)
        pie = (f'<tfoot><tr><td colspan="3">Total (perímetro)</td>'
               f'<td class="num">{_num(sum(li.longitud for li in ficha.linderos))}</td></tr></tfoot>')
    return ('<table><thead><tr><th>Hacia</th><th>Linda con</th><th></th><th>Longitud (m)</th></tr></thead><tbody>'
            + ''.join(filas) + '</tbody>' + pie + '</table>')


def leer_cabida(texto):
    """
    Cabida escrita por el usuario, en m²: None si está vacía; ValueError si no es un número positivo. Admite «1250,5»,
    «1250.5», «1.250» y «1 250,5» (millares a la española), «1,250.5» y la unidad («620,5 m²»). Con un solo punto seguido
    de tres cifras («1.250») es un millar, como se escribe en las escrituras, no 1,25 m².
    """
    limpio = re.sub(r'\s|m²|m2', '', (texto or '').strip(), flags=re.IGNORECASE)
    if not limpio:
        return None
    if not re.fullmatch(r'[\d.,]+', limpio):
        raise ValueError(texto)
    comas, puntos = limpio.count(','), limpio.count('.')
    if comas and puntos:
        decimal = ',' if limpio.rfind(',') > limpio.rfind('.') else '.'
        millar = '.' if decimal == ',' else ','
        if limpio.count(decimal) > 1:
            raise ValueError(texto)
        limpio = limpio.replace(millar, '').replace(decimal, '.')
    elif comas:
        if comas > 1:
            raise ValueError(texto)
        limpio = limpio.replace(',', '.')
    elif puntos and re.fullmatch(r'\d{1,3}(\.\d{3})+', limpio):
        limpio = limpio.replace('.', '')
    elif puntos > 1:
        raise ValueError(texto)
    valor = float(limpio)
    if valor <= 0:
        raise ValueError(texto)
    return valor


def comparar_cabida(total, inscrita):
    """(diferencia en m², en % de la inscrita, umbrales que cumple) o None si no hay cabida inscrita."""
    if not inscrita or inscrita <= 0:
        return None
    diferencia = total - inscrita
    porcentaje = 100.0 * abs(diferencia) / inscrita
    return diferencia, porcentaje, [texto for limite, texto in UMBRALES if porcentaje <= limite]


def _leyenda_parcela(parcelas, foco, vecinas):
    """Leyenda del croquis de una parcela: ella (su color), las demás del GML (tenues) y las catastrales de alrededor."""
    from .informe import PALETA_CROQUIS, leyenda
    indice = next(i for i, e in enumerate(parcelas) if e is foco)
    color = getattr(foco, 'color', None) or PALETA_CROQUIS[indice % len(PALETA_CROQUIS)]
    entradas = [(f"Parcela {foco.local_id}, con sus vértices numerados como en la tabla de coordenadas", color, 'relleno')]
    if len(parcelas) > 1:
        entradas.append(("Otras parcelas del GML (más claras, cada una con su color)", '#868e96', 'tenue'))
    if vecinas:
        entradas.append(("Parcelas catastrales de alrededor, con su referencia", '#868e96', 'gris'))
    return leyenda(entradas)


def html(lectura, ruta_gml, lista, inscrita=None, autor='', ahora=None, consulta=None, vecinas=(), ortofoto=b''):
    """
    Texto HTML del informe. consulta: fecha de la consulta de las colindantes al Catastro (None si no se consultó);
    vecinas: esas parcelas catastrales (ElementoGML), que se dibujan en gris en el croquis de cada parcela; ortofoto:
    imagen del encuadre del croquis general (vista_croquis), que va debajo de las parcelas.
    """
    ahora = ahora or datetime.datetime.now()
    from .informe import croquis_svg, leyenda_recintos  #Mismo croquis que el informe de comprobación
    parcelas = [e for e in lectura.elementos if not e.geometria.isNull() and not e.geometria.isEmpty()]
    #Las catastrales de origen (las que ocupa el GML) no se dibujan: taparían el contorno nuevo
    vecinas = [v for v in vecinas if all(v.geometria.intersection(p.geometria).area() <= SOLAPE for p in parcelas)]
    nombre = os.path.basename(ruta_gml)
    total_utm = sum(f.area_utm for f in lista)
    total_elipsoide = sum(f.area_elipsoide for f in lista)
    filas = ''.join(f'<tr><td class="id">{escape(f.local_id)}</td><td>{escape(f.namespace)}</td><td>{escape(f.label)}</td>'
                    f'<td class="num">{_num(f.area_utm)}</td><td class="num">{_num(f.area_elipsoide)}</td>'
                    f'<td class="num">{_num(f.perimetro)}</td></tr>' for f in lista)
    cabida = comparar_cabida(total_utm, inscrita)
    if cabida is None:
        bloque_cabida = ''
    else:
        diferencia, porcentaje, cumple = cabida
        bloque_cabida = (
            '<h2>Comparación con la cabida inscrita</h2>'
            f'<p>Cabida inscrita o de título: <b>{_num(inscrita)} m²</b> · superficie del GML: <b>{_num(total_utm)} m²</b> · '
            f'diferencia: <b>{"+" if diferencia >= 0 else "−"}{_num(abs(diferencia))} m² ({_num(porcentaje)} %)</b>.</p>'
            + ('<ul>' + ''.join(f'<li>Dentro del umbral del {escape(t)}.</li>' for t in cumple) + '</ul>' if cumple
               else '<p>Supera el 10 % de la cabida inscrita.</p>')
            + '<p class="meta">Umbrales de la Ley Hipotecaria (texto consolidado, BOE-A-1946-2453). Es una referencia: '
              'la valoración corresponde al registrador.</p>')
    detalle = ''.join(
        f'<section><h3>{escape(f.local_id)} <span class="meta">· {escape(f.namespace)} · nº {escape(f.label or "—")}</span></h3>'
        f'<p>Superficie UTM <b>{_num(f.area_utm)} m²</b> · elipsoide {_num(f.area_elipsoide)} m² · perímetro '
        f'{_num(f.perimetro)} m</p>'
        f'{croquis_svg(parcelas, alto=360, vertices=True, foco=p, vecinas=vecinas)}'
        f'{_leyenda_parcela(parcelas, p, vecinas)}'
        f'<h4>Linderos</h4>{_linderos(f, consulta is not None)}'
        f'<h4>Coordenadas</h4>{_coordenadas(f)}</section>' for f, p in zip(lista, parcelas))
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Superficies y coordenadas · {escape(nombre)}</title>
<style>
  :root {{ --fondo:#ffffff; --texto:#1d2327; --suave:#f1f3f5; --linea:#dee2e6; --acento:#1f6f78; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --fondo:#15191b; --texto:#e6eaeb; --suave:#1e2426; --linea:#343a40; }} }}
  body {{ font-family:"Segoe UI",Arial,sans-serif; max-width:980px; margin:0 auto; padding:16px; background:var(--fondo);
         color:var(--texto); line-height:1.45; }}
  h1 {{ color:var(--acento); margin:0 0 4px; font-size:1.5em; }}
  h2 {{ color:var(--acento); border-bottom:2px solid var(--suave); padding-bottom:4px; margin-top:28px; font-size:1.15em; }}
  h3 {{ margin:24px 0 4px; }} h4 {{ margin:12px 0 4px; }}
  .meta {{ opacity:.8; font-size:.92em; font-weight:normal; }}
  .aviso-legal {{ font-size:.88em; opacity:.85; }}
  table {{ border-collapse:collapse; width:100%; font-size:.93em; }}
  th, td {{ border-bottom:1px solid var(--linea); padding:5px 8px; text-align:left; }}
  th {{ background:var(--suave); }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  td.id {{ font-family:Consolas,monospace; }}
  table.coord {{ width:auto; min-width:420px; }} tr.anillo th {{ background:none; font-style:italic; }}
  tfoot td {{ font-weight:bold; }}
  .croquis {{ display:block; width:100%; max-width:760px; margin:8px auto; background:var(--suave); border-radius:6px; }}
  .etiqueta {{ font-size:12px; fill:var(--texto); paint-order:stroke; stroke:var(--fondo); stroke-width:3px; }}
  section {{ page-break-inside:avoid; }}
  footer {{ margin-top:32px; font-size:.85em; opacity:.75; border-top:1px solid var(--linea); padding-top:8px; }}
</style>
</head>
<body>
<h1>Superficies y coordenadas</h1>
<p class="aviso-legal"><b>No es un documento oficial</b> ni tiene código seguro de verificación (CSV). ⚠ {escape(AVISO_LEGAL)}</p>
<div class="meta">{escape(nombre)} · {len(lista)} parcela{'s' if len(lista) != 1 else ''} · EPSG:{lectura.epsg} ·
{ahora:%d/%m/%Y %H:%M}{f' · {escape(autor)}' if autor else ''}</div>

<h2>Resumen</h2>
<table>
<thead><tr><th>Identificador</th><th>Namespace</th><th>Nº parcela</th><th>Sup. UTM m²</th><th>Sup. elipsoide m²</th>
<th>Perímetro m</th></tr></thead>
<tbody>{filas}</tbody>
<tfoot><tr><td colspan="3">Total</td><td class="num">{_num(total_utm)}</td><td class="num">{_num(total_elipsoide)}</td><td></td></tr></tfoot>
</table>
<p class="meta">La superficie UTM es la de la proyección del GML y la que usa el Catastro (la del fichero, redondeada al
m²). La del elipsoide GRS80 es la del terreno sin relieve; en terreno inclinado la superficie real es mayor que ambas.</p>
{bloque_cabida}
<h2>Croquis</h2>
{croquis_svg(parcelas, fondo=ortofoto, atribucion=ATRIBUCION_PNOA)}
{leyenda_recintos(parcelas)}
<p class="meta">{'Sobre la ortofoto PNOA del Instituto Geográfico Nacional (CC BY 4.0, scne.es), que puede no coincidir al centímetro con la cartografía catastral. ' if ortofoto else ''}Cada parcela tiene abajo su croquis con los vértices numerados y, en gris, las parcelas catastrales de alrededor.</p>

<h2>Parcelas</h2>
<p class="meta">{f'Linderos con las parcelas catastrales según los datos públicos de la {escape(FUENTE_DGC)} consultados el {consulta:%d/%m/%Y a las %H:%M}; ' if consulta else 'Sin consultar el Catastro: solo los linderos entre parcelas del GML; '}«hacia»: el
rumbo al que da cada lado (el lado norte de una parcela linda «al N»). Coordenadas UTM en metros (EPSG:{lectura.epsg});
los números de los vértices son los del croquis de cada parcela (en él se omiten los de vértices muy juntos).</p>
{detalle}

<footer>Generado con {escape(NOMBRE)} {escape(version())} (herramienta no oficial, GPL-2.0-or-later) a partir del fichero
<code>{escape(ruta_gml)}</code>.</footer>
</body>
</html>
"""


def escribir(lectura, ruta_gml, lista, ruta=None, inscrita=None, autor='', consulta=None, vecinas=(), ortofoto=b''):
    """Escribe el informe (por defecto junto al GML) y devuelve su ruta; lanza OSError si no se puede escribir."""
    ruta = ruta or ruta_por_defecto(ruta_gml)
    problema = escribir_texto(ruta, html(lectura, ruta_gml, lista, inscrita, autor, consulta=consulta, vecinas=vecinas,
                                       ortofoto=ortofoto), 'utf-8')
    if problema is not None:
        raise OSError(problema.mensaje)
    return ruta
