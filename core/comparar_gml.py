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
    QgsCsException,
    QgsGeometry,
    QgsPointXY,
)

from . import gml_lector as gl
from .geometria import epsg_recomendado, girar_ejes, orden_lat_lon
from .ficheros import escribir_texto
from .info import AVISO_LEGAL, NOMBRE, version

TOLERANCIA = 0.01       #m: la de la Sede por vértice
VERTICE_PROPIO = 0.10   #m: un vértice sin otro a menos de esto en el otro GML es añadido o quitado
PAREJA = 0.5            #Fracción de la superficie del menor que deben compartir dos recintos con distinto id
MAX_VERTICES_TABLA = 200
MAX_SOLAPES = 5
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
    giro: tuple = None         #(grados, escala, dx, dy) si el segundo es el primero girado o escalado
    solapes: list = field(default_factory=list)     #[(qué, '', con quién)] otros recintos del otro GML con suelo común

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
            return f"Desplazado {_distancia(math.hypot(dx, dy))} hacia {rumbo(dx, dy)}"
        if self.giro is not None:
            grados, escala, dx, dy = self.giro
            return (f"Girado ≈{_num(grados, 3)}° y escalado ≈{_num((escala - 1) * 1e6, 0)} ppm (y desplazado "
                    f"{_distancia(math.hypot(dx, dy))}): misma forma")
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
    vista_a: object = None     #Lecturas ya en el sistema de trabajo (para verlas en el mapa en su sitio, también si
    vista_b: object = None     #alguno venía en geográficas con el orden latitud-longitud)

    def iguales(self):
        return not self.errores and all(p.veredicto() == "Igual (±1 cm)" for p in self.parejas)


def rumbo(dx, dy):
    nombres = ('E', 'NE', 'N', 'NO', 'O', 'SO', 'S', 'SE')
    return nombres[int(((math.degrees(math.atan2(dy, dx)) + 22.5) % 360) // 45)]


def _crs(epsg):
    return QgsCoordinateReferenceSystem(f'EPSG:{epsg}')


def _geografico(epsg):
    crs = _crs(epsg)
    return crs.isValid() and crs.isGeographic()


def _girar_ejes(geometria):
    return girar_ejes(geometria)


def _familia(elemento):
    """Parcelas con parcelas y construcciones con construcciones (un edificio no es la versión de una parcela)."""
    return 'parcela' if elemento.tipo == gl.PARCELA else 'construccion'


def _copias(lectura):
    salida = []
    for e in lectura.elementos:
        copia = gl.ElementoGML(**{**e.__dict__})
        copia.geometria = QgsGeometry(e.geometria)
        salida.append(copia)
    return salida


def _orden_lat_lon(elementos):
    """En geográficas: ¿el primer número es la latitud de España (26°-44,5°) y el segundo la longitud (−19°-5°)?"""
    return orden_lat_lon([e.geometria for e in elementos])


def src_de_trabajo(epsg_a, epsg_b, elementos_a, elementos_b):
    """
    Sistema en metros en el que se comparan: el del primero si es proyectado; si no, el del segundo; si los dos son
    geográficos (o no se sabe), el huso UTM de la zona (EPSG:25829/30/31 o 32628).
    """
    for epsg in (epsg_a, epsg_b):
        if epsg is not None and _crs(epsg).isValid() and not _geografico(epsg):
            return epsg
    for epsg, elementos in ((epsg_a, elementos_a), (epsg_b, elementos_b)):
        if epsg is not None and elementos:
            todos = QgsGeometry.collectGeometry([e.geometria for e in elementos])
            if _orden_lat_lon(elementos):
                todos = _girar_ejes(todos)
            recomendado = epsg_recomendado(todos, _crs(epsg))
            if recomendado:
                return recomendado
    return None


def al_src_de(elementos, epsg_origen, epsg_destino, cual='el segundo'):
    """
    Los elementos (copias) pasados de epsg_origen a epsg_destino, y las notas de lo hecho. En geográficas, el GML 3.2
    escribe latitud-longitud (orden EPSG); si el primer número parece la latitud de España, se cambian de orden.
    """
    notas = []
    if epsg_origen is None or epsg_destino is None or epsg_origen == epsg_destino or not elementos:
        return elementos, notas
    if _geografico(epsg_origen) and _orden_lat_lon(elementos):
        elementos = [_con_geometria(e, _girar_ejes(e.geometria)) for e in elementos]
        notas.append(f"{cual[0].upper()}{cual[1:]} está en coordenadas geográficas en el orden latitud, longitud; se han "
                     "leído así")
    transformacion = QgsCoordinateTransform(_crs(epsg_origen), _crs(epsg_destino), QgsCoordinateTransformContext())
    for e in elementos:
        try:
            e.geometria.transform(transformacion)
        except QgsCsException:
            e.geometria = QgsGeometry()
    notas.append(f"{cual[0].upper()}{cual[1:]} está en EPSG:{epsg_origen}: se ha pasado a EPSG:{epsg_destino} para "
                 "compararlos")
    return [e for e in elementos if not e.geometria.isEmpty()], notas


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
    geometria = elemento.geometria
    poligonos = geometria.asMultiPolygon() if geometria.isMultipart() else [geometria.asPolygon()]
    return _sin_cierre([anillo for poligono in poligonos for anillo in poligono])


def _cercano(p, geometria):
    """Vértice de geometria más cercano a p (y la distancia); con el índice de QGIS, rápido aunque tenga miles."""
    vertice, _, _, _, distancia2 = geometria.closestVertex(p)
    return QgsPointXY(vertice), math.sqrt(max(distancia2, 0.0))


def _valida(geometria):
    if geometria.isGeosValid():
        return geometria
    arreglada = geometria.makeValid()
    return arreglada if not arreglada.isEmpty() else geometria


def _area_fuera(a, b):
    try:
        return _valida(a).difference(_valida(b)).area()
    except Exception:  #GEOS con geometrías imposibles: mejor sin el dato que sin comparación
        return float('nan')


def _medir(pareja):
    a, b = pareja.a.geometria, pareja.b.geometria
    pareja.area_a, pareja.area_b = a.area(), b.area()
    pareja.hausdorff = a.hausdorffDistance(b)
    pareja.gana = _area_fuera(b, a)
    pareja.pierde = _area_fuera(a, b)
    pa, pb = _puntos(pareja.a), _puntos(pareja.b)
    if not pa or not pb:
        return
    #Cada vértice se busca en el otro GML después de quitar el desplazamiento de conjunto (prueba a mano del
    #19/10/2026: con un GML ajustado 44 cm, todos los vértices salían «añadidos y quitados» y no se veía que era un
    #desplazamiento). Primero con el de los centros; después, con la media de los vértices emparejados.
    centro_a, centro_b = a.boundingBox().center(), b.boundingBox().center()
    tx, ty = centro_b.x() - centro_a.x(), centro_b.y() - centro_a.y()
    parejas_v = []
    for _ in range(3):
        parejas_v = []
        for p in pa:
            q, residuo = _cercano(QgsPointXY(p.x() + tx, p.y() + ty), b)
            parejas_v.append((p, q, residuo))
        emparejados = [(p, q) for p, q, r in parejas_v if r <= VERTICE_PROPIO]
        if not emparejados:
            break
        tx = sum(q.x() - p.x() for p, q in emparejados) / len(emparejados)
        ty = sum(q.y() - p.y() for p, q in emparejados) / len(emparejados)
    #Si el desplazamiento de conjunto no empareja más que el emparejado directo (formas distintas), se usa el directo
    directos = [(p, *_cercano(p, b)) for p in pa]
    if sum(r <= VERTICE_PROPIO for _, _, r in directos) > sum(r <= VERTICE_PROPIO for _, _, r in parejas_v):
        parejas_v, tx, ty = directos, 0.0, 0.0
    pareja.vertices = [(n, p.x(), p.y(), math.hypot(q.x() - p.x(), q.y() - p.y()), q.x() - p.x(), q.y() - p.y())
                       for n, (p, q, _) in enumerate(parejas_v, start=1)]
    pareja.quitados = sum(1 for _, _, r in parejas_v if r > VERTICE_PROPIO)
    a_desplazada = QgsGeometry(a)
    a_desplazada.translate(tx, ty)
    pareja.anadidos = sum(1 for q in pb if _cercano(q, a_desplazada)[1] > VERTICE_PROPIO)
    #Desplazamiento uniforme: todos los vértices se mueven igual (dentro de ±1 cm)
    if len(pa) >= 3 and not pareja.anadidos and not pareja.quitados and pareja.hausdorff > TOLERANCIA:
        dispersion = max(math.hypot(v[4] - tx, v[5] - ty) for v in pareja.vertices)
        if math.hypot(tx, ty) > TOLERANCIA and dispersion <= TOLERANCIA:
            pareja.traslacion = (tx, ty)
        else:
            #¿Un giro o un cambio de escala de todo el recinto (un GML ajustado con semejanza, por ejemplo)?
            from .ajuste import SEMEJANZA, Par, calcular
            try:
                semejanza = calcular([Par(p.x(), p.y(), q.x(), q.y()) for p, q, _ in parejas_v], SEMEJANZA)
            except ValueError:
                semejanza = None
            if semejanza is not None and max(semejanza.residuos) <= TOLERANCIA:
                giro, escala, _, _ = semejanza.transformacion.descripcion()
                if abs(giro) > 1e-4 or abs(escala - 1) > 1e-6:
                    pareja.giro = (giro, escala, tx, ty)


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


def _comun(a, b):
    if not a.geometria.boundingBox().intersects(b.geometria.boundingBox()):
        return 0.0
    try:
        return _valida(a.geometria).intersection(_valida(b.geometria)).area()
    except Exception:
        return 0.0


def emparejar(elementos_a, elementos_b):
    """
    Por identificador (del mismo tipo: parcela o construcción) y, los que queden, por la superficie que comparten (más
    de la mitad del menor).
    """
    parejas, libres_b = [], list(elementos_b)
    sin_pareja = []
    for a in elementos_a:
        b = next((x for x in libres_b if x.local_id == a.local_id and _familia(x) == _familia(a)), None)
        if b is not None:
            libres_b.remove(b)
            parejas.append(Pareja(a, b, 'id'))
        else:
            sin_pareja.append(a)
    for a in sin_pareja:
        mejor, comun = None, 0.0
        for b in libres_b:
            if _familia(b) != _familia(a):
                continue
            area = _comun(a, b)
            if area > comun:
                mejor, comun = b, area
        if mejor is not None and comun >= PAREJA * min(a.geometria.area(), mejor.geometria.area()):
            libres_b.remove(mejor)
            parejas.append(Pareja(a, mejor, 'geometría'))
        else:
            parejas.append(Pareja(a, None))
    parejas += [Pareja(None, b) for b in libres_b]
    return parejas


def _solapes(pareja, elementos_a, elementos_b):
    """Con qué otros recintos del otro GML comparte suelo (una división, una segregación, una agrupación)."""
    textos = []
    for propio, otros, pareja_propia, cual in ((pareja.a, elementos_b, pareja.b, 'segundo'),
                                                (pareja.b, elementos_a, pareja.a, 'primero')):
        if propio is None:
            continue
        minimo = max(1.0, 0.01 * propio.geometria.area())
        nombres = [o.local_id for o in otros if o is not pareja_propia and _familia(o) == _familia(propio)
                   and _comun(propio, o) >= minimo]
        if nombres:
            texto = ', '.join(nombres[:MAX_SOLAPES]) + (f'… ({len(nombres)})' if len(nombres) > MAX_SOLAPES else '')
            textos.append((f'Comparte suelo con (del {cual})', '', texto))
    return textos


def _redondeo(decimales, epsg):
    """Error máximo (m) por redondear las coordenadas a esos decimales."""
    paso = 10 ** -decimales / 2
    return paso * GRADOS_A_METROS if epsg is not None and _geografico(epsg) else paso


def _leer(ruta):
    """Lectura del GML; si no es INSPIRE (un «Guardar como» de QGIS), como GML genérico. (lectura, nota o '')."""
    lectura = gl.leer(ruta)
    if lectura.elementos:
        return lectura, ''
    from .conversor import leer_generico
    datos = lectura.datos
    if not datos and os.path.isfile(ruta):  #Si no es XML válido, la lectura no guarda el contenido
        try:
            with open(ruta, 'rb') as f:
                datos = f.read()
        except OSError:
            datos = b''
    try:
        generica, _ = leer_generico(datos or b'')
    except Exception:
        generica = None
    if generica is not None and generica.elementos:
        return generica, f"{os.path.basename(ruta)} no es un GML de la Sede (INSPIRE): se ha leído como GML genérico"
    return lectura, ''


def _repetidos(elementos):
    vistos, repetidos = set(), []
    for e in elementos:
        clave = (_familia(e), e.local_id)
        if clave in vistos and e.local_id not in repetidos:
            repetidos.append(e.local_id)
        vistos.add(clave)
    return repetidos


def comparar(ruta_a, ruta_b, feedback=None):
    """
    Compara dos GML cualesquiera. feedback (QgsFeedback, opcional): avance y cancelación (en una QgsTask). Devuelve
    una Comparacion (con errores si no se ha podido comparar; vacía de parejas si se ha cancelado).
    """
    (lectura_a, nota_a), (lectura_b, nota_b) = _leer(ruta_a), _leer(ruta_b)
    notas = [n for n in (nota_a, nota_b) if n]
    errores = []
    for ruta, lectura in ((ruta_a, lectura_a), (ruta_b, lectura_b)):
        if not lectura.elementos:
            motivo = next((i.mensaje for i in lectura.incidencias), "no tiene parcelas ni construcciones")
            errores.append(f"{os.path.basename(ruta)}: {motivo}")
    if errores:
        return Comparacion(ruta_a, ruta_b, lectura_a, lectura_b, [], [], notas, errores)
    #Recintos cuya geometría no se ha podido leer: se dicen y no se comparan
    elementos = {}
    for cual, lectura in (('primero', lectura_a), ('segundo', lectura_b)):
        buenos = [e for e in _copias(lectura) if e.geometria is not None and not e.geometria.isNull()
                  and not e.geometria.isEmpty()]
        malos = [e.local_id or '(sin identificador)' for e in lectura.elementos
                 if e.geometria is None or e.geometria.isNull() or e.geometria.isEmpty()]
        if malos:
            notas.append(f"En el {cual}, sin geometría legible (no se comparan): {', '.join(malos[:MAX_SOLAPES])}")
        repetidos = _repetidos(buenos)
        if repetidos:
            notas.append(f"El {cual} repite identificadores: {', '.join(repetidos[:MAX_SOLAPES])}")
        elementos[cual] = buenos
    epsg_a, epsg_b = lectura_a.epsg, lectura_b.epsg
    if epsg_a is None and epsg_b is None:
        notas.append("Ninguno declara el sistema de referencia (srsName): se comparan las coordenadas tal cual")
    elif epsg_a is None or epsg_b is None:
        conocido = epsg_a or epsg_b
        notas.append(f"El {'primero' if epsg_a is None else 'segundo'} no declara el sistema de referencia (srsName): se "
                     f"supone EPSG:{conocido}, como el otro")
        epsg_a = epsg_b = conocido
    trabajo = src_de_trabajo(epsg_a, epsg_b, elementos['primero'], elementos['segundo']) or epsg_a
    elementos_a, notas_a = al_src_de(elementos['primero'], epsg_a, trabajo, 'el primero')
    elementos_b, notas_b = al_src_de(elementos['segundo'], epsg_b, trabajo, 'el segundo')
    notas += notas_a + notas_b
    dec_a = max((e.decimales for e in lectura_a.elementos), default=0)
    dec_b = max((e.decimales for e in lectura_b.elementos), default=0)
    generales = [("Esquema", lectura_a.version or 'desconocido', lectura_b.version or 'desconocido'),
                 ("Sistema de referencia", f"EPSG:{lectura_a.epsg}" if lectura_a.epsg else 'sin declarar',
                  f"EPSG:{lectura_b.epsg}" if lectura_b.epsg else 'sin declarar'),
                 ("Decimales de las coordenadas", str(dec_a), str(dec_b)),
                 ("Recintos", str(len(lectura_a.elementos)), str(len(lectura_b.elementos)))]
    familias_a = {_familia(e) for e in elementos_a}
    familias_b = {_familia(e) for e in elementos_b}
    if familias_a and familias_b and not familias_a & familias_b:
        notas.append("Uno es de parcelas y el otro de construcciones: solo se comparan recintos del mismo tipo, así que "
                     "no hay parejas")
    redondeo = {}
    for cual, decimales, epsg in (('primero', dec_a, epsg_a), ('segundo', dec_b, epsg_b)):
        redondeo[cual] = _redondeo(decimales, epsg)
        if redondeo[cual] > TOLERANCIA / 2:
            unidad = 'grados' if epsg is not None and _geografico(epsg) else 'm'
            notas.append(f"El {cual} tiene {decimales} decimales en {unidad}: solo por el redondeo, cada vértice puede "
                         f"moverse hasta {_num(redondeo[cual] * 100, 1)} cm")
    margen_redondeo = redondeo['primero'] + redondeo['segundo']
    parejas = emparejar(elementos_a, elementos_b)
    for n, p in enumerate(parejas):
        if feedback is not None:
            if feedback.isCanceled():
                return Comparacion(ruta_a, ruta_b, lectura_a, lectura_b, [], generales, notas, ["Cancelado"])
            feedback.setProgress(100.0 * n / max(len(parejas), 1))
        if p.a is not None and p.b is not None:
            p.datos = _datos(p.a, p.b)
            _medir(p)
            if (not p.iguales_geometria() and p.traslacion is None and p.giro is None and margen_redondeo > TOLERANCIA / 2
                    and p.hausdorff <= margen_redondeo * 1.5 + TOLERANCIA):
                p.datos.append(("Diferencia", "", f"compatible con el redondeo de las coordenadas "
                                                  f"(±{_num(margen_redondeo * 100, 1)} cm)"))
        p.solapes = _solapes(p, elementos_a, elementos_b)
    #¿Comparten suelo? Si ninguna pareja se toca, seguramente son fincas distintas o un srsName mal puesto
    if elementos_a and elementos_b:
        caja_a = QgsGeometry.collectGeometry([e.geometria for e in elementos_a]).boundingBox()
        caja_b = QgsGeometry.collectGeometry([e.geometria for e in elementos_b]).boundingBox()
        if not caja_a.intersects(caja_b):
            distancia = math.hypot(caja_a.center().x() - caja_b.center().x(), caja_a.center().y() - caja_b.center().y())
            notas.append(f"Los dos GML no se tocan (sus centros están a {_distancia(distancia)}): ¿son fincas distintas, o "
                         "alguno declara mal su sistema de referencia?")
    vistas = [gl.ResultadoLectura(version=lectura.version, epsg=trabajo, elementos=elementos)
              for lectura, elementos in ((lectura_a, elementos_a), (lectura_b, elementos_b))]
    return Comparacion(ruta_a, ruta_b, lectura_a, lectura_b, parejas, generales, notas, [], *vistas)


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
            partes += [f"{q[0].lower()}: {q[2]}" for q in p.solapes]
            lineas.append("; ".join(partes))
    return lineas + c.notas


def ruta_informe(ruta_a):
    base, _ = os.path.splitext(ruta_a)
    return f"{base}_comparacion.html"


def _num(valor, decimales=2):
    if valor != valor:  #NaN: no se ha podido calcular
        return '—'
    return f"{valor:,.{decimales}f}".replace(',', ' ').replace('.', ',')


def _distancia(metros):
    """En cm hasta 1 m; en m a partir de ahí."""
    return f"{_num(metros * 100, 1)} cm" if metros < 1 else f"{_num(metros)} m"


def _signo(valor):
    if abs(valor) < 0.005:
        return 'sin cambio'
    return ('+' if valor >= 0 else '−') + _num(abs(valor))


def _signo_cm(metros):
    return ('+' if metros > -0.0005 else '−') + _num(abs(metros) * 100, 1)  #Sin «−0,0»


class _Dibujo:
    """Elemento para el croquis con su color y trazo."""

    def __init__(self, elemento, color, discontinua=False, etiqueta=True):
        self.geometria = elemento.geometria
        self.local_id = elemento.local_id if etiqueta else ''
        self.color = color
        self.discontinua = discontinua


def html(c, ahora=None):
    from .informe import croquis_svg, leyenda
    ahora = ahora or datetime.datetime.now()
    nombre_a, nombre_b = os.path.basename(c.ruta_a), os.path.basename(c.ruta_b)
    cambia = " class='cambia'"
    filas_generales = ''.join(f"<tr{cambia if a != b else ''}><td>{escape(q)}</td><td>{escape(a)}</td>"
                              f"<td>{escape(b)}</td></tr>" for q, a, b in c.generales)
    filas = []
    secciones = []
    for p in c.parejas:
        solapes = ''.join(f"<br><small>{escape(q[0])}: {escape(q[2])}</small>" for q in p.solapes)
        filas.append(f"<tr><td class='id'>{escape(p.nombre)}</td><td>{escape(p.veredicto())}{solapes}</td>"
                     f"<td class='num'>{_num(p.area_a) if p.a is not None else ''}</td>"
                     f"<td class='num'>{_num(p.area_b) if p.b is not None else ''}</td>"
                     f"<td class='num'>{_num(p.hausdorff * 100, 1) if p.a is not None and p.b is not None else ''}</td></tr>")
        if p.a is None or p.b is None:
            continue
        datos = ''.join(f"<tr><td>{escape(n)}</td><td>{escape(a)}</td><td>{escape(b)}</td></tr>"
                        for n, a, b in p.datos + p.solapes)
        movidos = [v for v in p.vertices if v[3] > TOLERANCIA]
        tabla_v = ''.join(f"<tr><td>{n}</td><td class='num'>{x:.2f}</td><td class='num'>{y:.2f}</td>"
                          f"<td class='num'>{_num(d * 100, 1)}</td><td>{rumbo(dx, dy) if d > 1e-6 else ''}</td></tr>"
                          for n, x, y, d, dx, dy in movidos[:MAX_VERTICES_TABLA])
        croquis = (croquis_svg([_Dibujo(p.a, '#e8590c'), _Dibujo(p.b, '#1971c2', True, etiqueta=False)], alto=320)
                   + leyenda([(f"Primero: {nombre_a}", '#e8590c', 'relleno'),
                              (f"Segundo: {nombre_b}", '#1971c2', 'discontinua')]))
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
<p class="meta">Coordenadas UTM del primero; la separación de los contornos es la distancia de Hausdorff. Las diferencias
de centímetros no se aprecian en el croquis: están en las tablas.</p>
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
