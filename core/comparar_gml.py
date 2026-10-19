"""
Comparar dos GML (mejora 34): dos versiones de la misma representación —la presentada y la que devuelve otro organismo,
la de antes y la de después de un retoque, la de dos programas— y lo que interesa al técnico que trabaja con el Catastro:

  - el fichero: esquema, sistema de referencia, decimales de las coordenadas y número de parcelas o construcciones;
  - qué recintos están en los dos (por identificador o, si cambia, por la superficie que comparten), cuáles solo en uno;
  - de cada pareja: identificador, namespace, número, referencia, superficie declarada y calculada; cuánto se separan los
    contornos (distancia de Hausdorff), el desplazamiento de cada vértice, vértices añadidos o quitados, el suelo que gana
    o pierde cada uno, y si la diferencia es un desplazamiento uniforme o un redondeo de coordenadas;
  - si a efectos de la Sede son iguales (±1 cm por vértice).

No importa de dónde salen los ficheros. Si están en distinto sistema de referencia, el segundo se pasa al del primero (con
coordenadas geográficas, también se tiene en cuenta el orden latitud-longitud). Sin interfaz: lo usa la utilidad
«Comparar dos GML» de la pestaña Utilidades.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import datetime
import math
import os
from dataclasses import dataclass, field
from html import escape

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsGeometry,
)

from . import gml_lector as gl
from .ficheros import escribir_texto
from .info import AVISO_LEGAL, NOMBRE, version

TOLERANCIA = 0.01       #m: la de la Sede por vértice
VERTICE_PROPIO = 0.10   #m: un vértice sin otro a menos de esto en el otro GML es añadido o quitado
PAREJA = 0.5            #Fracción de la superficie del menor que deben compartir dos recintos con distinto id
MAX_VERTICES_TABLA = 200
GRADOS_A_METROS = 111_320.0  #Un grado de latitud, en metros (aproximado: para estimar el redondeo)


@dataclass
class Pareja:
    a: object                  #ElementoGML del primero (o None si solo está en el segundo)
    b: object                  #ElementoGML del segundo (ya en el SRC del primero) o None
    por: str = 'id'            #Cómo se han emparejado: 'id' o 'geometría'
    datos: list = field(default_factory=list)       #[(campo, valor A, valor B)] que cambian
    area_a: float = 0.0
    area_b: float = 0.0
    hausdorff: float = 0.0     #Máxima separación entre los contornos (m)
    gana: float = 0.0          #Superficie del segundo fuera del primero (m²)
    pierde: float = 0.0        #Superficie del primero fuera del segundo (m²)
    vertices: list = field(default_factory=list)    #[(nº en A, x, y, distancia, dx, dy)] al vértice más cercano de B
    anadidos: int = 0          #Vértices de B sin otro de A cerca
    quitados: int = 0          #Vértices de A sin otro de B cerca
    traslacion: tuple = None   #(dx, dy) si los vértices se mueven todos igual

    @property
    def nombre(self):
        if self.a is not None and self.b is not None and self.a.local_id != self.b.local_id:
            return f"{self.a.local_id} ↔ {self.b.local_id}"
        return (self.a or self.b).local_id

    @property
    def maximo(self):
        return max((v[3] for v in self.vertices), default=0.0)

    def iguales_geometria(self):
        return self.a is not None and self.b is not None and self.hausdorff <= TOLERANCIA + 1e-9

    def veredicto(self):
        if self.a is None:
            return "Solo en el segundo"
        if self.b is None:
            return "Solo en el primero"
        if self.iguales_geometria():
            return "Igual (±1 cm)" if not self.datos else "Misma geometría; cambian datos"
        if self.traslacion is not None:
            dx, dy = self.traslacion
            return f"Desplazado {_num(math.hypot(dx, dy) * 100, 1)} cm hacia {rumbo(dx, dy)}"
        return f"Distinto: hasta {_num(self.hausdorff * 100, 1)} cm"


@dataclass
class Comparacion:
    ruta_a: str
    ruta_b: str
    lectura_a: object
    lectura_b: object
    parejas: list
    generales: list            #[(qué, primero, segundo)] del fichero
    notas: list                #Textos que explican la diferencia (redondeo, cambio de SRC…)
    errores: list              #No se ha podido comparar

    def iguales(self):
        return not self.errores and all(p.veredicto() == "Igual (±1 cm)" for p in self.parejas)


def rumbo(dx, dy):
    nombres = ('E', 'NE', 'N', 'NO', 'O', 'SO', 'S', 'SE')
    return nombres[int(((math.degrees(math.atan2(dy, dx)) + 22.5) % 360) // 45)]


def _geografico(epsg):
    crs = QgsCoordinateReferenceSystem(f'EPSG:{epsg}')
    return crs.isValid() and crs.isGeographic()


def _girar_ejes(geometria):
    nueva = QgsGeometry(geometria)
    nueva.get().swapXy()
    return nueva


def al_src_de(lectura, epsg_destino):
    """
    Copia de los elementos de lectura en el SRC epsg_destino (y la nota de lo hecho). En geográficas, el GML 3.2 escribe
    latitud-longitud (EPSG); si el primer número parece la latitud de España (27°-44°) se cambian de orden.
    """
    notas = []
    elementos = []
    origen = lectura.epsg
    for e in lectura.elementos:
        copia = gl.ElementoGML(**{**e.__dict__})
        copia.geometria = QgsGeometry(e.geometria)
        elementos.append(copia)
    if origen is None or origen == epsg_destino:
        return elementos, notas
    if _geografico(origen):
        centro = QgsGeometry.collectGeometry([e.geometria for e in elementos]).centroid().asPoint()
        if 26.0 <= centro.x() <= 44.5 and -19.0 <= centro.y() <= 5.0:
            elementos = [_con_geometria(e, _girar_ejes(e.geometria)) for e in elementos]
            notas.append("El segundo está en coordenadas geográficas en el orden latitud, longitud; se han leído así")
    transformacion = QgsCoordinateTransform(QgsCoordinateReferenceSystem(f'EPSG:{origen}'),
                                            QgsCoordinateReferenceSystem(f'EPSG:{epsg_destino}'),
                                            QgsCoordinateTransformContext())
    for e in elementos:
        e.geometria.transform(transformacion)
    notas.append(f"Están en sistemas de referencia distintos (EPSG:{origen} y EPSG:{epsg_destino}): el segundo se ha "
                 f"pasado al del primero para compararlos")
    return elementos, notas


def _con_geometria(e, geometria):
    e.geometria = geometria
    return e


def _sin_cierre(puntos):
    """Vértices de los anillos sin repetir el de cierre (el contador de vértices debe ser el de la tabla)."""
    salida = []
    for anillo in (puntos or []):
        salida += anillo[:-1] if len(anillo) > 1 and anillo[0] == anillo[-1] else anillo
    return salida


def _puntos(elemento):
    poligonos = elemento.geometria.asMultiPolygon() if elemento.geometria.isMultipart() else [elemento.geometria.asPolygon()]
    return _sin_cierre([anillo for poligono in poligonos for anillo in poligono])


def _cercano(p, puntos):
    mejor, d = None, float('inf')
    for q in puntos:
        distancia = math.hypot(q.x() - p.x(), q.y() - p.y())
        if distancia < d:
            mejor, d = q, distancia
    return mejor, d


def _medir(pareja):
    a, b = pareja.a.geometria, pareja.b.geometria
    pareja.area_a, pareja.area_b = a.area(), b.area()
    pareja.hausdorff = a.hausdorffDistance(b)
    pareja.gana = b.difference(a).area()
    pareja.pierde = a.difference(b).area()
    pa, pb = _puntos(pareja.a), _puntos(pareja.b)
    for n, p in enumerate(pa, start=1):
        q, d = _cercano(p, pb)
        pareja.vertices.append((n, p.x(), p.y(), d, q.x() - p.x(), q.y() - p.y()))
    pareja.quitados = sum(1 for v in pareja.vertices if v[3] > VERTICE_PROPIO)
    pareja.anadidos = sum(1 for q in pb if _cercano(q, pa)[1] > VERTICE_PROPIO)
    #Desplazamiento uniforme: todos los vértices homólogos se mueven igual (más de 1 cm y con poca dispersión)
    homologos = [v for v in pareja.vertices if v[3] <= VERTICE_PROPIO * 10]
    if len(homologos) >= 3 and not pareja.anadidos and not pareja.quitados:
        mx = sum(v[4] for v in homologos) / len(homologos)
        my = sum(v[5] for v in homologos) / len(homologos)
        dispersion = max(math.hypot(v[4] - mx, v[5] - my) for v in homologos)
        if math.hypot(mx, my) > TOLERANCIA and dispersion <= max(0.005, 0.2 * math.hypot(mx, my)):
            pareja.traslacion = (mx, my)


def _datos(a, b):
    cambios = []
    for campo, nombre in (('local_id', 'Identificador'), ('namespace', 'Namespace'), ('label', 'Nº de parcela'),
                          ('referencia', 'Referencia'), ('area_declarada', 'Superficie declarada (m²)'),
                          ('plantas', 'Plantas'), ('naturaleza', 'Tipo de construcción'), ('estado', 'Estado')):
        va, vb = getattr(a, campo, None), getattr(b, campo, None)
        if (va or None) != (vb or None):
            cambios.append((nombre, '' if va is None else str(va), '' if vb is None else str(vb)))
    if len(_puntos(a)) != len(_puntos(b)):
        cambios.append(('Nº de vértices', str(len(_puntos(a))), str(len(_puntos(b)))))
    return cambios


def emparejar(elementos_a, elementos_b):
    """Por identificador y, los que queden, por la superficie que comparten (más de la mitad del menor)."""
    parejas, libres_b = [], list(elementos_b)
    sin_pareja = []
    for a in elementos_a:
        b = next((x for x in libres_b if x.local_id == a.local_id), None)
        if b is not None:
            libres_b.remove(b)
            parejas.append(Pareja(a, b, 'id'))
        else:
            sin_pareja.append(a)
    for a in sin_pareja:
        mejor, comun = None, 0.0
        for b in libres_b:
            area = a.geometria.intersection(b.geometria).area()
            if area > comun:
                mejor, comun = b, area
        if mejor is not None and comun >= PAREJA * min(a.geometria.area(), mejor.geometria.area()):
            libres_b.remove(mejor)
            parejas.append(Pareja(a, mejor, 'geometría'))
        else:
            parejas.append(Pareja(a, None))
    parejas += [Pareja(None, b) for b in libres_b]
    return parejas


def _redondeo(decimales, epsg):
    """Error máximo (m) por redondear las coordenadas a esos decimales."""
    paso = 10 ** -decimales / 2
    return paso * GRADOS_A_METROS if _geografico(epsg) else paso


def comparar(ruta_a, ruta_b):
    lectura_a, lectura_b = gl.leer(ruta_a), gl.leer(ruta_b)
    errores = []
    for ruta, lectura in ((ruta_a, lectura_a), (ruta_b, lectura_b)):
        if not lectura.elementos:
            motivo = next((i.mensaje for i in lectura.incidencias), "no tiene parcelas ni construcciones")
            errores.append(f"{os.path.basename(ruta)}: {motivo}")
        elif lectura.epsg is None:
            errores.append(f"{os.path.basename(ruta)}: no se sabe en qué sistema de referencia está (srsName)")
    if errores:
        return Comparacion(ruta_a, ruta_b, lectura_a, lectura_b, [], [], [], errores)
    elementos_b, notas = al_src_de(lectura_b, lectura_a.epsg)
    dec_a = max((e.decimales for e in lectura_a.elementos), default=0)
    dec_b = max((e.decimales for e in lectura_b.elementos), default=0)
    generales = [("Esquema", lectura_a.version or 'desconocido', lectura_b.version or 'desconocido'),
                 ("Sistema de referencia", f"EPSG:{lectura_a.epsg}", f"EPSG:{lectura_b.epsg}"),
                 ("Decimales de las coordenadas", str(dec_a), str(dec_b)),
                 ("Recintos", str(len(lectura_a.elementos)), str(len(lectura_b.elementos)))]
    redondeo_b = _redondeo(dec_b, lectura_b.epsg)
    if redondeo_b > TOLERANCIA / 2:
        unidad = 'grados' if _geografico(lectura_b.epsg) else 'm'
        notas.append(f"El segundo tiene {dec_b} decimales en {unidad}: solo por el redondeo, cada vértice puede moverse "
                     f"hasta {_num(redondeo_b * 100, 1)} cm")
    parejas = emparejar(lectura_a.elementos, elementos_b)
    for p in parejas:
        if p.a is not None and p.b is not None:
            p.datos = _datos(p.a, p.b)
            _medir(p)
            if not p.iguales_geometria() and p.traslacion is None and p.hausdorff <= redondeo_b * 1.5 + TOLERANCIA:
                p.datos.append(("Diferencia", "", f"compatible con el redondeo de las coordenadas del segundo "
                                                  f"(±{_num(redondeo_b * 100, 1)} cm)"))
    return Comparacion(ruta_a, ruta_b, lectura_a, lectura_b, parejas, generales, notas, [])


# ------------------------------------------------------------------ Resumen e informe

def resumen(c):
    """Líneas cortas para el panel."""
    if c.errores:
        return c.errores
    lineas = []
    distintos = [g for g in c.generales if g[1] != g[2]]
    if distintos:
        lineas.append("Fichero: " + "; ".join(f"{q.lower()} {a} → {b}" for q, a, b in distintos))
    iguales = [p for p in c.parejas if p.veredicto() == "Igual (±1 cm)"]
    if iguales:
        lineas.append(f"Iguales (±1 cm): {len(iguales)}")
    for p in c.parejas:
        if p not in iguales:
            partes = [f"{p.nombre}: {p.veredicto()}"]
            if p.a is not None and p.b is not None:
                if abs(p.area_b - p.area_a) >= 0.005:
                    partes.append(f"superficie {_num(p.area_a)} → {_num(p.area_b)} m² ({_signo(p.area_b - p.area_a)})")
                if p.anadidos or p.quitados:
                    partes.append(f"vértices +{p.anadidos} −{p.quitados}")
                cambios = [d[0].lower() for d in p.datos if d[0] != 'Diferencia']
                if cambios:
                    partes.append("cambia " + ", ".join(cambios))
                if any(d[0] == 'Diferencia' for d in p.datos):
                    partes.append("compatible con el redondeo")
            lineas.append("; ".join(partes))
    return lineas + c.notas


def ruta_informe(ruta_a):
    base, _ = os.path.splitext(ruta_a)
    return f"{base}_comparacion.html"


def _num(valor, decimales=2):
    return f"{valor:,.{decimales}f}".replace(',', ' ').replace('.', ',')


def _signo(valor):
    if abs(valor) < 0.005:
        return 'sin cambio'
    return ('+' if valor >= 0 else '−') + _num(abs(valor))


def _signo_cm(metros):
    return ('+' if metros >= 0 else '−') + _num(abs(metros) * 100, 1)


class _Dibujo:
    """Elemento para el croquis con su color y trazo."""

    def __init__(self, elemento, color, discontinua=False, etiqueta=True):
        self.geometria = elemento.geometria
        self.local_id = elemento.local_id if etiqueta else ''
        self.color = color
        self.discontinua = discontinua


def html(c, ahora=None):
    from .informe import croquis_svg
    ahora = ahora or datetime.datetime.now()
    nombre_a, nombre_b = os.path.basename(c.ruta_a), os.path.basename(c.ruta_b)
    cambia = " class='cambia'"
    filas_generales = ''.join(f"<tr{cambia if a != b else ''}><td>{escape(q)}</td><td>{escape(a)}</td>"
                              f"<td>{escape(b)}</td></tr>" for q, a, b in c.generales)
    filas = []
    secciones = []
    for p in c.parejas:
        filas.append(f"<tr><td class='id'>{escape(p.nombre)}</td><td>{escape(p.veredicto())}</td>"
                     f"<td class='num'>{_num(p.area_a) if p.a is not None else ''}</td>"
                     f"<td class='num'>{_num(p.area_b) if p.b is not None else ''}</td>"
                     f"<td class='num'>{_num(p.hausdorff * 100, 1) if p.a is not None and p.b is not None else ''}</td></tr>")
        if p.a is None or p.b is None:
            continue
        datos = ''.join(f"<tr><td>{escape(n)}</td><td>{escape(a)}</td><td>{escape(b)}</td></tr>" for n, a, b in p.datos)
        movidos = [v for v in p.vertices if v[3] > TOLERANCIA]
        tabla_v = ''.join(f"<tr><td>{n}</td><td class='num'>{x:.2f}</td><td class='num'>{y:.2f}</td>"
                          f"<td class='num'>{_num(d * 100, 1)}</td><td>{rumbo(dx, dy) if d > 1e-6 else ''}</td></tr>"
                          for n, x, y, d, dx, dy in movidos[:MAX_VERTICES_TABLA])
        croquis = croquis_svg([_Dibujo(p.a, '#e8590c'), _Dibujo(p.b, '#1971c2', True, etiqueta=False)], alto=320)
        secciones.append(
            f"<section><h3>{escape(p.nombre)} <span class='meta'>· {escape(p.veredicto())}"
            f"{' · emparejados por la geometría' if p.por == 'geometría' else ''}</span></h3>"
            f"<p>Superficie {_num(p.area_a)} → {_num(p.area_b)} m² ({_signo(p.area_b - p.area_a)}) · el segundo gana "
            f"{_num(p.gana)} m² y pierde {_num(p.pierde)} m² · separación máxima de los contornos {_num(p.hausdorff * 100, 1)} cm"
            f" · vértices añadidos {p.anadidos}, quitados {p.quitados}</p>"
            + (f"<p>Todos los vértices se mueven igual: ΔX {_signo_cm(p.traslacion[0])} cm, ΔY {_signo_cm(p.traslacion[1])} "
               "cm (un desplazamiento, no un cambio de forma).</p>" if p.traslacion else '')
            + (f"<table><thead><tr><th>Dato</th><th>Primero</th><th>Segundo</th></tr></thead><tbody>{datos}</tbody></table>"
               if datos else '')
            + croquis
            + (f"<h4>Vértices que se mueven más de 1 cm ({len(movidos)} de {len(p.vertices)})</h4>"
               "<table class='coord'><thead><tr><th>Nº</th><th>X</th><th>Y</th><th>Al vértice más cercano (cm)</th>"
               f"<th>Hacia</th></tr></thead><tbody>{tabla_v}</tbody></table>" if movidos else
               "<p>Ningún vértice se mueve más de 1 cm.</p>")
            + "</section>")
    notas = ''.join(f"<li>{escape(n)}</li>" for n in c.notas)
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Comparación de GML · {escape(nombre_a)} y {escape(nombre_b)}</title>
<style>
  :root {{ --fondo:#ffffff; --texto:#1d2327; --suave:#f1f3f5; --linea:#dee2e6; --acento:#1f6f78; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --fondo:#15191b; --texto:#e6eaeb; --suave:#1e2426; --linea:#343a40; }} }}
  body {{ font-family:"Segoe UI",Arial,sans-serif; max-width:980px; margin:0 auto; padding:16px; background:var(--fondo);
         color:var(--texto); line-height:1.45; }}
  h1 {{ color:var(--acento); margin:0 0 4px; font-size:1.5em; }}
  h2 {{ color:var(--acento); border-bottom:2px solid var(--suave); padding-bottom:4px; margin-top:28px; font-size:1.15em; }}
  h3 {{ margin:24px 0 4px; }} h4 {{ margin:12px 0 4px; }}
  .meta {{ opacity:.8; font-size:.92em; font-weight:normal; }}
  table {{ border-collapse:collapse; width:100%; font-size:.93em; margin:6px 0; }}
  th, td {{ border-bottom:1px solid var(--linea); padding:5px 8px; text-align:left; }}
  th {{ background:var(--suave); }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  td.id {{ font-family:Consolas,monospace; }}
  tr.cambia td {{ font-weight:600; }}
  table.coord {{ width:auto; min-width:420px; }}
  .croquis {{ display:block; width:100%; max-width:760px; margin:8px auto; background:var(--suave); border-radius:6px; }}
  .etiqueta {{ font-size:12px; fill:var(--texto); paint-order:stroke; stroke:var(--fondo); stroke-width:3px; }}
  .leyenda span {{ display:inline-block; width:22px; height:0; border-top:3px solid; vertical-align:middle; margin:0 4px 0 12px; }}
  section {{ page-break-inside:avoid; }}
  footer {{ margin-top:32px; font-size:.85em; opacity:.75; border-top:1px solid var(--linea); padding-top:8px; }}
</style>
</head>
<body>
<h1>Comparación de dos GML</h1>
<p class="meta"><b>Primero:</b> {escape(nombre_a)} · <b>segundo:</b> {escape(nombre_b)} · {ahora:%d/%m/%Y %H:%M}</p>
<p class="meta">{escape(AVISO_LEGAL)} Iguales «a efectos de la Sede»: ningún vértice se separa más de 1 cm.</p>
<h2>Resultado</h2>
<p><b>{'Son iguales (±1 cm)' if c.iguales() else 'Hay diferencias'}</b></p>
{f'<ul>{notas}</ul>' if notas else ''}
<table><thead><tr><th></th><th>Primero</th><th>Segundo</th></tr></thead><tbody>{filas_generales}</tbody></table>
<table><thead><tr><th>Recinto</th><th>Resultado</th><th>Sup. primero m²</th><th>Sup. segundo m²</th>
<th>Separación máx. cm</th></tr></thead><tbody>{''.join(filas)}</tbody></table>
<h2>Detalle</h2>
<p class="leyenda meta"><span style="border-color:#e8590c"></span>primero <span style="border-color:#1971c2;border-top-style:dashed"></span>segundo
(coordenadas UTM del primero; la separación de los contornos es la distancia de Hausdorff). Las diferencias de
centímetros no se aprecian en el croquis: están en las tablas.</p>
{''.join(secciones) or '<p>No hay recintos en los dos ficheros.</p>'}
<footer>Generado con {escape(NOMBRE)} {escape(version())} (herramienta no oficial, GPL-2.0-or-later) a partir de
<code>{escape(c.ruta_a)}</code> y <code>{escape(c.ruta_b)}</code>.</footer>
</body>
</html>
"""


def escribir(c, ruta=None, ahora=None):
    ruta = ruta or ruta_informe(c.ruta_a)
    problema = escribir_texto(ruta, html(c, ahora), 'utf-8', origenes=(c.ruta_a, c.ruta_b))
    if problema is not None:
        raise OSError(problema.mensaje)
    return ruta

