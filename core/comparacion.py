"""
Comparación de un GML de parcela con la cartografía catastral vigente (mejora 14), como hará la Sede en el informe de
validación gráfica (IVG). Se descargan del WFS de la DGC las parcelas bajo el parcelario propuesto y se comprueba:

  - NPO (parcelas catastrales afectadas) y NPP (parcelas del GML), y la operación que corresponde según la tabla del
    documento de validación de la DGC (segregación, división, agregación, agrupación, subsanación o no permitida);
  - que el contorno exterior del GML coincida con el de las parcelas afectadas (±1 cm en vértices, FAQ de la DGC):
    ninguna parcela afectada solo en parte (con alguna parcial el IVG es negativo) ni suelo sin parcela ocupado
    (viales urbanos: IVG negativo);
  - que las referencias SDGC existan en el Catastro y sean de las parcelas afectadas;
  - avisos que no impiden el IVG pero sí la tramitación automática (urbana y rústica mezcladas, distinto polígono o
    manzana, más de 30 parcelas) y
    dominio público afectado (debe ir en el GML delimitando la parte afectada).

Fuentes en docs/INVESTIGACION.md §7.1. Es una ayuda: la comprobación que vale es la de la Sede.

Las peticiones son bloqueantes: llamar a comparar() desde una QgsTask.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import math
from dataclasses import dataclass, field

from qgis.core import QgsGeometry, QgsRectangle

from . import gml_lector as gl
from . import refcat, servicios
from .incidencias import AVISO, ERROR, INFO, Incidencia

TOLERANCIA = 0.01        #m: tolerancia en vértices de la Sede (±1 cm)
AREA_MINIMA = 0.05       #m²: diferencias menores (tras aplicar la tolerancia) se consideran ruido de redondeo
MARGEN = 2.0             #m alrededor del parcelario propuesto al pedir las parcelas catastrales
LADO_MAXIMO = 1000.0     #m: el WFS no admite rectángulos de más de ~1 km² («Area of extension out of limits»)
MAX_TROZOS = 25          #Como mucho, tantas peticiones por comparación (parcelarios de hasta ~5 × 5 km)
MAX_TRAMITACION = 30     #Más parcelas por operación: no se tramita de forma automática
EPSG_DGC = (25829, 25830, 25831, 32628)
DISTANCIA_ICUC = 100.0   #m: el ICUC no admite construcciones más lejos de la parcela


@dataclass
class Comparacion:
    npo: int = 0                                      #Parcelas catastrales afectadas
    npp: int = 0                                      #Parcelas del GML
    operacion: str = ''                               #Segregación, División… o '' si no se ha podido comparar
    origen: list = field(default_factory=list)        #ElementoGML de las parcelas catastrales afectadas
    exceso: object = None                             #QgsGeometry: suelo del GML fuera de las parcelas afectadas
    defecto: object = None                            #QgsGeometry: suelo de las parcelas afectadas que el GML deja fuera
    incidencias: list = field(default_factory=list)
    epsg: object = None
    edificio: bool = False                            #Comparación de un GML de edificio con su parcela (ICUC)

    @property
    def comparada(self):
        return bool(self.operacion)


def _trozos(caja):
    """Divide un rectángulo en rectángulos de LADO_MAXIMO como mucho (límite del WFS)."""
    nx = max(1, math.ceil(caja.width() / LADO_MAXIMO))
    ny = max(1, math.ceil(caja.height() / LADO_MAXIMO))
    ancho, alto = caja.width() / nx, caja.height() / ny
    return [QgsRectangle(caja.xMinimum() + i * ancho, caja.yMinimum() + j * alto,
                         caja.xMinimum() + (i + 1) * ancho, caja.yMinimum() + (j + 1) * alto)
            for i in range(nx) for j in range(ny)]


def parcelas_catastrales(caja, epsg):
    """Parcelas catastrales que tocan un rectángulo (en trozos si es grande). Devuelve (lista de ElementoGML, errores)."""
    trozos = _trozos(caja)
    if len(trozos) > MAX_TROZOS:
        return [], [Incidencia(AVISO, 'CMP-DEMASIADO-GRANDE', "El parcelario es demasiado extenso para compararlo con el "
                                                              "Catastro desde el plugin")]
    vistas = {}
    for trozo in trozos:
        resultado, errores = servicios.consultar_wfs(servicios.url_entorno(trozo, epsg), "las parcelas del Catastro")
        if errores or resultado is None:
            return [], errores or [Incidencia(AVISO, 'CMP-SIN-DATOS', "El Catastro no ha devuelto parcelas")]
        for e in resultado.elementos:
            if not e.geometria.isEmpty():
                vistas.setdefault(e.local_id, e)
    return list(vistas.values()), []


def operacion(npo, npp, propuestas, origen_ids):
    """
    Operación según la tabla NPO/NPP/namespace del documento de validación de la DGC (IVG_Operaciones, §4.2).
    Devuelve (texto, nivel): nivel ERROR si la combinación no está permitida.
    """
    sdgc = [e for e in propuestas if e.namespace == 'ES.SDGC.CP']
    if npo == 1 and npp > 1:
        if len(sdgc) == 1:
            return "Segregación (o subsanación)", INFO
        if not sdgc:
            return "División", INFO
        return "No permitida: de una parcela no pueden salir dos o más con referencia catastral (SDGC)", ERROR
    if npo > 1 and npp == 1:
        if sdgc:
            return "Agregación (o subsanación)", INFO
        return "Agrupación", INFO
    if npo == npp and npo > 0:
        if len(sdgc) == npp and {e.local_id for e in sdgc} == set(origen_ids):
            return "Subsanación de discrepancias", INFO
        return "Subsanación o reparcelación (no se tramita de forma automática)", AVISO
    return "Subsanación o reparcelación (no se tramita de forma automática)", AVISO


def comparar(lectura):
    """Compara un GML de parcela ya leído (gml_lector.ResultadoLectura) con el Catastro. Nunca lanza excepciones."""
    c = Comparacion(epsg=lectura.epsg)
    propuestas = [e for e in lectura.elementos if e.tipo == gl.PARCELA and not e.geometria.isEmpty()]
    if lectura.version != 'CP 4.0' or not propuestas:
        return c
    if lectura.epsg not in EPSG_DGC:
        c.incidencias.append(Incidencia(AVISO, 'CMP-SRC', "No se compara con el Catastro: el SRC no es uno de los de la Sede"))
        return c
    if any(i.codigo == 'RC-FORAL' for i in getattr(lectura, 'incidencias', [])):
        return c
    union = QgsGeometry.unaryUnion([e.geometria for e in propuestas])
    caja = union.boundingBox()
    caja.grow(MARGEN)
    catastrales, errores = parcelas_catastrales(caja, lectura.epsg)
    if errores:
        c.incidencias += [Incidencia(AVISO, 'CMP-NO-COMPARADO', f"No se ha podido comparar con el Catastro: {i.mensaje}")
                          for i in errores]
        return c

    #Parcelas afectadas: las que comparten superficie con el parcelario (no basta con tocarlo por un lindero)
    interior = union.buffer(-TOLERANCIA, 4)
    afectadas = [e for e in catastrales if e.geometria.intersects(interior)
                 and e.geometria.intersection(interior).area() > AREA_MINIMA]
    c.origen = afectadas
    c.npo, c.npp = len(afectadas), len(propuestas)
    if not afectadas:
        c.operacion = "Sin parcelas catastrales debajo"
        c.incidencias.append(Incidencia(ERROR, 'CMP-SIN-ORIGEN', "El parcelario no está sobre ninguna parcela catastral: "
                                                                 "compruebe la posición y el SRC"))
        return c

    union_origen = QgsGeometry.unaryUnion([e.geometria for e in afectadas])
    union_todas = QgsGeometry.unaryUnion([e.geometria for e in catastrales])
    holgura = union.buffer(TOLERANCIA, 4)
    #Afectadas solo en parte: la Sede da IVG negativo
    parciales = []
    for e in afectadas:
        fuera = e.geometria.difference(holgura)
        if not fuera.isEmpty() and fuera.area() > AREA_MINIMA:
            parciales.append((e, fuera.area()))
    for e, area in parciales:
        c.incidencias.append(Incidencia(
            ERROR, 'CMP-PARCIAL', f"La parcela catastral {e.local_id} queda afectada solo en parte ({area:.2f} m² fuera del "
                                  "GML): inclúyala entera, con la parte afectada y la no afectada, o ajuste el lindero",
            e.local_id))
    #Suelo sin parcela ocupado (calles en urbana)
    sin_parcela = union.difference(union_todas.buffer(TOLERANCIA, 4))
    if not sin_parcela.isEmpty() and sin_parcela.area() > AREA_MINIMA:
        c.incidencias.append(Incidencia(
            ERROR, 'CMP-SIN-PARCELA', f"El GML ocupa {sin_parcela.area():.2f} m² de suelo sin parcela catastral (en urbana, "
                                      "vía pública): la Sede dará informe negativo salvo cesión o incorporación del viario "
                                      "con una parcela propia (LOCAL)"))
    exceso = union.difference(union_origen.buffer(TOLERANCIA, 4))
    defecto = union_origen.difference(holgura)
    c.exceso = exceso if not exceso.isEmpty() and exceso.area() > AREA_MINIMA else None
    c.defecto = defecto if not defecto.isEmpty() and defecto.area() > AREA_MINIMA else None
    if not parciales and c.exceso is None and c.defecto is None:
        c.incidencias.append(Incidencia(INFO, 'CMP-CONTORNO-OK',
                                        "El contorno exterior coincide con el de "
                                        + ("la parcela catastral afectada" if c.npo == 1
                                           else f"las {c.npo} parcelas catastrales afectadas")
                                        + f" (±{TOLERANCIA * 100:.0f} cm)"))

    #Referencias catastrales del GML
    ids_origen = [e.local_id for e in afectadas]
    ids_todas = {e.local_id for e in catastrales}
    for e in propuestas:
        if e.namespace != 'ES.SDGC.CP':
            continue
        if e.local_id not in ids_todas and not _existe(e.local_id, lectura.epsg):
            c.incidencias.append(Incidencia(ERROR, 'CMP-RC-NO-EXISTE', f"La referencia {e.local_id} no existe en el Catastro",
                                            e.local_id))
        elif e.local_id not in ids_origen:
            c.incidencias.append(Incidencia(ERROR, 'CMP-RC-AJENA', f"La referencia {e.local_id} no es de ninguna de las "
                                                                   "parcelas catastrales afectadas", e.local_id))

    texto, nivel = operacion(c.npo, c.npp, propuestas, ids_origen)
    c.operacion = texto
    c.incidencias.append(Incidencia(nivel, 'CMP-OPERACION', f"NPO {c.npo} (parcelas catastrales afectadas) · NPP {c.npp} "
                                                            f"(parcelas del GML) → {texto}"))
    #No impiden el IVG, pero sí la tramitación automática
    tipos = {refcat.tipo_parcela(i) for i in ids_origen} - {''}
    if len(tipos) > 1:
        c.incidencias.append(Incidencia(AVISO, 'CMP-TIPOS', "Mezcla parcelas urbanas y rústicas: no se tramitará de forma "
                                                            "automática"))
    else:
        claves = {_clave_tramite(i) for i in ids_origen} - {''}
        if len(claves) > 1:
            c.incidencias.append(Incidencia(AVISO, 'CMP-TRAMITE', f"Parcelas de distinto polígono o manzana ({'; '.join(sorted(claves))}): "
                                                                  "no se tramitará de forma automática"))
    if max(c.npo, c.npp) > MAX_TRAMITACION:
        c.incidencias.append(Incidencia(AVISO, 'CMP-MAS-30', f"Más de {MAX_TRAMITACION} parcelas en la operación: no se "
                                                             "tramitará de forma automática"))
    publicas = [i for i in ids_origen if refcat.es_dominio_publico(i)]
    if publicas:
        c.incidencias.append(Incidencia(AVISO, 'CMP-DOMINIO-PUBLICO',
                                        f"Afecta a dominio público ({', '.join(publicas)}): debe ir en el GML delimitando la "
                                        "parte afectada, y la alteración requiere el pronunciamiento de su Administración "
                                        "titular"))
    return c


def comparar_edificio(lectura):
    """
    GML de edificio (mejora 20): sitúa cada construcción respecto a la parcela catastral vigente cuya referencia lleva su
    identificador (RC, RC_Edificio_N, RC_Piscina_N), como el ICUC: dentro (bien), en parte fuera (aviso: el informe lo
    reflejará) o a más de 100 m (error: el ICUC no la admite). Los solapes entre construcciones los ve el validador.
    Nunca lanza excepciones.
    """
    c = Comparacion(epsg=lectura.epsg, edificio=True)
    construcciones = [e for e in lectura.elementos if e.tipo != gl.PARCELA and not e.geometria.isEmpty()]
    if lectura.version != 'BU 2.0' or not construcciones:
        return c
    if lectura.epsg not in EPSG_DGC:
        c.incidencias.append(Incidencia(AVISO, 'CMP-SRC', "No se compara con el Catastro: el SRC no es uno de los de la Sede"))
        return c
    referencias = {refcat.limpiar(e.local_id)[:14] for e in construcciones}
    referencias = {r for r in referencias if refcat.es_rc_parcela(r)}
    if len(referencias) != 1:
        texto = ("los identificadores no empiezan por la referencia catastral de la parcela" if not referencias
                 else f"hay construcciones de varias parcelas ({', '.join(sorted(referencias))})")
        c.incidencias.append(Incidencia(AVISO, 'CMP-BU-SIN-RC', f"No se compara con el Catastro: {texto}. Si la parcela "
                                                                "aún no existe, el ICUC usa la del GML de parcela"))
        return c
    rc = referencias.pop()
    if refcat.comprobar(rc).foral:
        c.incidencias.append(Incidencia(AVISO, 'RC-FORAL', refcat.comprobar(rc).mensaje))
        return c
    resultado, errores = servicios.consultar_wfs(servicios.url_parcela(rc, lectura.epsg), f"la parcela {rc}")
    if errores:
        c.incidencias += [Incidencia(AVISO, 'CMP-NO-COMPARADO', f"No se ha podido comparar con el Catastro: {i.mensaje}")
                          for i in errores]
        return c
    parcelas = [e for e in (resultado.elementos if resultado else []) if not e.geometria.isEmpty()]
    if not parcelas:
        c.operacion = "Parcela no encontrada"
        c.incidencias.append(Incidencia(ERROR, 'CMP-RC-NO-EXISTE', f"La parcela {rc} no existe en el Catastro: el ICUC "
                                                                   "necesita una parcela catastral vigente"))
        return c
    c.origen = parcelas
    c.npo, c.npp = 1, len(construcciones)
    exacta = QgsGeometry.unaryUnion([e.geometria for e in parcelas])
    parcela = exacta.buffer(TOLERANCIA, 4)
    fuera = []
    for e in construcciones:
        distancia = e.geometria.distance(exacta)
        if distancia > DISTANCIA_ICUC:
            fuera.append(e.geometria)
            c.incidencias.append(Incidencia(ERROR, 'CMP-BU-LEJOS', f"La construcción está a {distancia:.0f} m de la parcela "
                                                                   f"{rc}: el ICUC no admite construcciones a más de "
                                                                   f"{DISTANCIA_ICUC:.0f} m. Compruebe la referencia y el SRC",
                                            e.local_id))
            continue
        resto = e.geometria.difference(parcela)
        if not resto.isEmpty() and resto.area() > AREA_MINIMA:
            fuera.append(resto)
            c.incidencias.append(Incidencia(AVISO, 'CMP-BU-FUERA', f"{resto.area():.2f} m² de la construcción quedan fuera de "
                                                                   f"la parcela catastral {rc}: el informe (ICUC) lo reflejará. "
                                                                   "Si el lindero no es correcto, tramite antes el GML de "
                                                                   "parcela", e.local_id))
    if fuera:
        c.exceso = QgsGeometry.unaryUnion(fuera)
        n = len(fuera)
        c.operacion = f"{n} construcci{'ones' if n != 1 else 'ón'} no {'están' if n != 1 else 'está'} entera dentro de la parcela {rc}"
    else:
        c.operacion = f"Construcciones dentro de la parcela {rc}"
        c.incidencias.append(Incidencia(INFO, 'CMP-BU-DENTRO', f"Todas las construcciones están dentro de la parcela "
                                                               f"catastral {rc} (±{TOLERANCIA * 100:.0f} cm)"))
    return c


def _clave_tramite(rc):
    """Polígono (rústica) o manzana (urbana) de una RC: si las afectadas son de varios, no hay tramitación automática."""
    tipo = refcat.tipo_parcela(rc)
    if tipo == 'rústica':
        return f"polígono {int(rc[6:9])} del municipio {rc[:5]}"
    if tipo == 'urbana':
        return f"manzana {rc[:5]}, hoja {rc[7:14]}"
    return ''


def _existe(rc, epsg):
    resultado, errores = servicios.consultar_wfs(servicios.url_parcela(rc, epsg), f"la parcela {rc}")
    return not errores and resultado is not None and bool(resultado.elementos)
