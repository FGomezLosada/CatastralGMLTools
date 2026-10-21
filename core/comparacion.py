"""
Comparación de un GML de parcela con la cartografía catastral vigente (mejora 14), como hará la Sede en el informe de
validación gráfica (IVG). Se descargan del WFS de la DGC las parcelas bajo el parcelario propuesto y se comprueba:

  - NPO (parcelas catastrales afectadas) y NPP (parcelas del GML), y la operación que corresponde según la tabla del
    documento de validación de la DGC (segregación, división, agregación, agrupación, subsanación o no permitida);
  - que el contorno exterior del GML coincida con el de las parcelas afectadas (±1 cm en vértices, FAQ de la DGC):
    ninguna parcela afectada solo en parte ni suelo sin parcela ocupado (viales urbanos). Desde el 12/03/2025 la Sede no
    certifica IVG negativos: con estos errores no emite el informe (muestra los errores y deja descargar el «GML
    parcial»; Tema 8 del curso, v2026). Ocupar viario con una parcela LOCAL (cesión o incorporación) da un positivo
    condicionado, sin tramitación automática (guía GML Catastro-Registro y Check4SEC; auditoría AU-20 y AU-21);
  - que las referencias SDGC existan en el Catastro y sean de las parcelas afectadas;
  - avisos que no impiden el IVG pero sí la tramitación automática (urbana y rústica mezcladas, distinto polígono o
    manzana, más de 30 parcelas) y
    dominio público afectado (debe ir en el GML delimitando la parte afectada).

Fuentes en docs/INVESTIGACION.md §7.1. Es una ayuda: la comprobación que vale es la de la Sede.

Las peticiones son bloqueantes: llamar a comparar() desde una QgsTask.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import datetime
import math
from dataclasses import dataclass, field, replace

from qgis.core import QgsGeometry, QgsPointXY, QgsRectangle

from . import geometria as geo
from . import gml_lector as gl
from . import refcat, servicios
from .incidencias import AVISO, ERROR, INFO, Incidencia

TOLERANCIA = 0.01        #m: tolerancia en vértices de la Sede (±1 cm)
RUIDO = 1e-6             #m²: por debajo, la diferencia es ruido numérico (la tolerancia se mide en distancia, AU-01)
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
    fecha: object = field(default_factory=datetime.datetime.now)  #Cuándo se consultaron los datos de la DGC
    identidad: object = None                          #core.identidad.Resultado (1 parcela frente a la suya), o None

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


def fuera_de(a, b):
    """
    Parte de la geometría a que está a más de 1 cm de b (None si no hay ninguna). La tolerancia se mide en distancia,
    no en superficie: un vértice movido 2 cm o una franja de 3 cm, por estrecha que sea, cuentan (auditoría AU-01).
    """
    resto = a.difference(b.buffer(TOLERANCIA, 8))
    return resto if not resto.isEmpty() and resto.area() > RUIDO else None


def diferencia(a, b):
    """a menos b, sin tolerancia (para dibujar en el mapa)."""
    resto = a.difference(b)
    return resto if not resto.isEmpty() else None


def desvio(resto, b):
    """
    Distancia máxima (m) de lo que queda fuera (resto) a b: cuánto se separa. El contorno de resto se densifica (el
    punto más lejano puede caer entre dos vértices, p. ej. en el fondo de un entrante).
    """
    if resto is None or resto.isEmpty():
        return 0.0
    paso = max(0.005, resto.length() / 4000)
    densa = resto.densifyByDistance(paso)  #Con referencia: el iterador de vértices no guarda la geometría (segfault)
    puntos = [QgsPointXY(v.x(), v.y()) for v in densa.vertices()]
    return max((b.distance(QgsGeometry.fromPointXY(p)) for p in puntos), default=0.0)


def parcelas_catastrales(cajas, epsg):
    """
    Parcelas catastrales que tocan uno o varios rectángulos (en trozos si son grandes). Con un GML de varias zonas
    separadas se pide cada zona, no el rectángulo que las abarca a todas (que podía ser de kilómetros: lento).
    Devuelve (lista de ElementoGML, errores).
    """
    cajas = [cajas] if isinstance(cajas, QgsRectangle) else list(cajas)
    trozos = [t for caja in cajas for t in _trozos(caja)]
    if len(trozos) > MAX_TROZOS:
        return [], [Incidencia(AVISO, 'CMP-DEMASIADO-GRANDE', "El parcelario es demasiado extenso para compararlo con el "
                                                              "Catastro desde el plugin")]
    vistas = {}
    for n, trozo in enumerate(trozos):
        servicios.progreso(n, len(trozos))
        resultado, errores = servicios.consultar_wfs(servicios.url_entorno(trozo, epsg), "las parcelas del Catastro")
        if errores or resultado is None:
            return [], errores or [Incidencia(AVISO, 'CMP-SIN-DATOS', "El Catastro no ha devuelto parcelas")]
        for e in resultado.elementos:
            if not e.geometria.isEmpty():
                vistas.setdefault(e.local_id, e)
    servicios.progreso(len(trozos), len(trozos))
    return list(vistas.values()), []


def operacion(npo, npp, propuestas, origen_ids):
    """
    Operación según la tabla NPO/NPP/namespace del documento de validación de la DGC (IVG_Operaciones, §4.2).
    Devuelve (texto, nivel): nivel ERROR si la combinación no está permitida.
    """
    sdgc = [e for e in propuestas if e.namespace == 'ES.SDGC.CP']
    if npo == 1 and npp > 1:
        if len(sdgc) == 1:
            return "Segregación (o subsanación, que no se tramita de forma automática)", INFO
        if not sdgc:
            return "División", INFO
        return "No permitida: de una parcela no pueden salir dos o más con referencia catastral (SDGC)", ERROR
    if npo > 1 and npp == 1:
        if sdgc:
            return "Agregación (o subsanación, que no se tramita de forma automática)", INFO
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
    forales = {refcat.comprobar(e.local_id).foral for e in propuestas if e.namespace == 'ES.SDGC.CP'} - {''}
    if forales:  #La RC dice que es de un territorio con catastro propio: el WFS de la DGC no tiene sus parcelas (AU-15)
        c.incidencias.append(Incidencia(AVISO, 'RC-FORAL', f"No se compara con el Catastro: parcelas de {', '.join(forales)}, "
                                                           "que tiene catastro propio (no el de la Dirección General del "
                                                           "Catastro)"))
        return c
    invalidas = [e.local_id for e in propuestas if not e.geometria.isGeosValid()]
    if invalidas:  #Batería de casos (19/10/2026): con una pajarita, GEOS fallaba por dentro y el resultado no era fiable
        c.incidencias.append(Incidencia(AVISO, 'CMP-GEO-INVALIDA', f"Geometría no válida ({', '.join(invalidas[:5])}): se "
                                                                   "compara una versión corregida y el resultado puede no "
                                                                   "ser exacto. Corrija la geometría (vea los errores de "
                                                                   "arriba)"))
        propuestas = [replace(e, geometria=e.geometria.makeValid()) if not e.geometria.isGeosValid() else e
                      for e in propuestas]
        propuestas = [e for e in propuestas if not e.geometria.isEmpty()]
        if not propuestas:
            return c
    if any(e.decimales > 2 for e in propuestas):  #La Sede trunca a 2 decimales: se compara lo que verá ella (AU-29)
        propuestas = [replace(e, geometria=geo.truncar(e.geometria)) for e in propuestas]
        c.incidencias.append(Incidencia(INFO, 'CMP-TRUNCADO', "El GML trae más de 2 decimales: se compara con las coordenadas "
                                                              "truncadas a 2, como hace la Sede"))
    union = QgsGeometry.unaryUnion([e.geometria for e in propuestas])
    grupos = geo.zonas([e.geometria for e in propuestas])
    cajas = []
    for parte, _ in grupos:
        caja = parte.boundingBox()
        caja.grow(MARGEN)
        cajas.append(caja)
    catastrales, errores = parcelas_catastrales(cajas, lectura.epsg)
    if errores:
        c.incidencias += [Incidencia(AVISO, 'CMP-NO-COMPARADO', f"No se ha podido comparar con el Catastro: {i.mensaje}")
                          for i in errores]
        return c

    #Parcelas afectadas: las que comparten superficie con el parcelario (no basta con tocarlo por un lindero)
    interior = union.buffer(-TOLERANCIA, 4)
    #(el interior está 1 cm hacia dentro: cualquier invasión de más de 1 cm cuenta, por estrecha que sea; AU-01)
    afectadas = [e for e in catastrales if e.geometria.intersects(interior)
                 and e.geometria.intersection(interior).area() > RUIDO]
    c.origen = afectadas
    c.npo, c.npp = len(afectadas), len(propuestas)
    if not afectadas:
        c.operacion = "Sin parcelas catastrales debajo"
        c.incidencias.append(Incidencia(ERROR, 'CMP-SIN-ORIGEN', "El parcelario no está sobre ninguna parcela catastral: "
                                                                 "compruebe la posición y el SRC"))
        zona = servicios.zona_foral(union.centroid().asPoint(), lectura.epsg)
        if zona:  #Sin parcelas de la DGC en una zona foral: lo más probable es que sea de su catastro propio (AU-31)
            c.incidencias.append(Incidencia(AVISO, 'CMP-FORAL', f"La posición parece de {zona}, que tiene catastro propio: "
                                                                "la Dirección General del Catastro no tiene sus parcelas. "
                                                                "Use la sede de su catastro foral"))
        return c

    union_origen = QgsGeometry.unaryUnion([e.geometria for e in afectadas])
    union_todas = QgsGeometry.unaryUnion([e.geometria for e in catastrales])
    #Afectadas solo en parte: la Sede no emite el informe
    parciales = []
    for e in afectadas:
        fuera = fuera_de(e.geometria, union)
        if fuera is not None:
            parciales.append((e, fuera.area(), desvio(fuera, union)))
    for e, area, distancia in parciales:
        ajuste = (f"; se separa hasta {distancia * 100:.1f} cm del GML (la Sede admite ±{TOLERANCIA * 100:.0f} cm): si no es "
                  "intencionado, ajuste esos vértices" if distancia < 1 else '')
        otras = [o.geometria for o in afectadas if o is not e]
        if not ajuste and otras:  #El GML apenas entra en ella (un vértice o un lindero desplazado unos cm)
            entra = desvio(e.geometria.intersection(union), QgsGeometry.unaryUnion(otras))
            if entra < 1:
                ajuste = (f"; el GML solo entra en ella hasta {entra * 100:.1f} cm (la Sede admite ±"
                          f"{TOLERANCIA * 100:.0f} cm): si no es intencionado, ajuste el lindero común")
        c.incidencias.append(Incidencia(
            ERROR, 'CMP-PARCIAL', f"La parcela catastral {e.local_id} queda afectada solo en parte ({area:.2f} m² fuera del "
                                  f"GML{ajuste}): inclúyala entera, con la parte afectada y la no afectada, o ajuste el "
                                  "lindero", e.local_id))
    #Suelo sin parcela ocupado (calles en urbana)
    sin_parcela = fuera_de(union, union_todas)
    if sin_parcela is not None:
        #¿Lo cubren solo parcelas nuevas (LOCAL)? Es la forma admitida de ceder o incorporar viario (AU-21)
        sdgc = [e.geometria for e in propuestas if e.namespace == 'ES.SDGC.CP']
        en_sdgc = fuera_de(sin_parcela, QgsGeometry.unaryUnion(sdgc).buffer(-TOLERANCIA, 4)) if sdgc else sin_parcela
        solo_local = not sdgc or (en_sdgc is not None and abs(en_sdgc.area() - sin_parcela.area()) < 0.01)
        if solo_local:
            c.incidencias.append(Incidencia(
                AVISO, 'CMP-VIARIO', f"El GML ocupa {sin_parcela.area():.2f} m² de suelo sin parcela catastral (en urbana, "
                                     "vía pública) con una parcela nueva (LOCAL): cesión o incorporación de viario. La Sede "
                                     "da un informe positivo condicionado, sin tramitación automática; necesita la "
                                     "conformidad de la Administración titular del viario"))
        else:
            c.incidencias.append(Incidencia(
                ERROR, 'CMP-SIN-PARCELA', f"El GML ocupa {sin_parcela.area():.2f} m² de suelo sin parcela catastral (en urbana, "
                                          "vía pública) dentro de una parcela con referencia (SDGC): la Sede no emitirá el "
                                          "informe. Para ceder o incorporar viario, delimítelo como una parcela propia "
                                          "(LOCAL)"))
    #Para el mapa, la diferencia entera (también el primer centímetro), no solo lo que pasa de la tolerancia: si no, la
    #zona dibujada no llegaba a la línea del GML y parecía otro descuadre (prueba a mano del 13/10/2026)
    c.exceso = diferencia(union, union_origen) if fuera_de(union, union_origen) is not None else None
    c.defecto = diferencia(union_origen, union) if fuera_de(union_origen, union) is not None else None
    if not parciales and c.exceso is None and c.defecto is None:
        c.incidencias.append(Incidencia(INFO, 'CMP-CONTORNO-OK',
                                        "El contorno exterior coincide con el de "
                                        + ("la parcela catastral afectada" if c.npo == 1
                                           else f"las {c.npo} parcelas catastrales afectadas")
                                        + f" (±{TOLERANCIA * 100:.0f} cm)"))

    #Un GML con parcelas de dos municipios no se valida (asistente Catastro-Registro, CdU_12; AU-26)
    #(una consulta de datos no protegidos por parcela afectada: municipio, BICE y diseminado)
    fichas = {e.local_id: servicios.ficha(e.local_id) for e in afectadas[:MAX_TRAMITACION]}
    municipios = {f['municipio'] for f in fichas.values() if f and f['municipio']}
    municipios |= {servicios.municipio_de(rc) for rc, f in fichas.items()
                   if not f and refcat.tipo_parcela(rc) == 'rústica'}  #Sin conexión, la rústica lo dice su RC
    if len(municipios) > 1:
        c.incidencias.append(Incidencia(ERROR, 'CMP-MUNICIPIOS', f"Las parcelas afectadas son de {len(municipios)} municipios: "
                                                                 "la Sede no valida un GML con parcelas de dos municipios "
                                                                 "(haga un GML por municipio)"))

    #Parcelas sin cambios: una parcela del GML idéntica (±1 cm) a una catastral no altera nada (AU-03; Check4SEC)
    iguales = []
    for p in propuestas:
        for e in afectadas:
            if fuera_de(p.geometria, e.geometria) is None and fuera_de(e.geometria, p.geometria) is None:
                iguales.append((p, e))
                break
    todo_igual = bool(iguales) and len(iguales) == len(propuestas)
    if todo_igual:  #Todo el GML es el Catastro vigente: «quítela del GML» no tenía sentido (prueba a mano del 15/10)
        c.incidencias.append(Incidencia(
            AVISO, 'CMP-SIN-CAMBIOS', f"El GML es igual al Catastro vigente (±{TOLERANCIA * 100:.0f} cm): no describe "
                                      "ninguna alteración. Si quiere acreditar la geometría catastral actual (ante el "
                                      "notario o el Registro), no hace falta un GML: sirve la certificación catastral "
                                      "descriptiva y gráfica. Si la finca real es distinta, dibuje su geometría real y cree "
                                      "el GML de nuevo"))
    else:
        for p, e in iguales:
            c.incidencias.append(Incidencia(
                ERROR, 'CMP-SIN-CAMBIOS', f"La parcela {p.local_id} es igual a la catastral {e.local_id} (±"
                                          f"{TOLERANCIA * 100:.0f} cm): no cambia nada. Quítela del GML (solo van las "
                                          "parcelas que se alteran)", p.local_id))

    #Referencias catastrales del GML
    ids_origen = [e.local_id for e in afectadas]
    ids_todas = {e.local_id for e in catastrales}
    for e in propuestas:
        if e.namespace != 'ES.SDGC.CP':
            continue
        existe = True if e.local_id in ids_todas else _existe(e.local_id, lectura.epsg)
        if existe is None:
            c.incidencias.append(Incidencia(AVISO, 'CMP-RC-SIN-COMPROBAR', f"No se ha podido comprobar si la referencia "
                                                                         f"{e.local_id} existe (sin conexión con el "
                                                                         "Catastro)", e.local_id))
        elif not existe:
            c.incidencias.append(Incidencia(ERROR, 'CMP-RC-NO-EXISTE', f"La referencia {e.local_id} no existe en el Catastro",
                                            e.local_id))
        elif e.local_id not in ids_origen:
            c.incidencias.append(Incidencia(ERROR, 'CMP-RC-AJENA', f"La referencia {e.local_id} no es de ninguna de las "
                                                                   "parcelas catastrales afectadas", e.local_id))

    texto, nivel = operacion(c.npo, c.npp, propuestas, ids_origen)
    if todo_igual:
        texto, nivel = "ninguna: el GML es igual al Catastro vigente", AVISO
    c.operacion = texto
    c.incidencias.append(Incidencia(nivel, 'CMP-OPERACION', f"NPO {c.npo} (parcelas catastrales afectadas) · NPP {c.npp} "
                                                            f"(parcelas del GML) → {texto}"))
    if c.npp == 1 and not todo_igual:
        #¿Cabe en el margen de identidad gráfica con la parcela catastral que es la suya (AU-58)? Un levantamiento a
        #30 cm del Catastro «afecta» a la vecina (NPO 2, ±1 cm), pero puede ser la misma finca a efectos de identidad
        from . import identidad
        try:
            simulada = identidad.comprobar([propuestas[0].geometria], [(e.local_id, e.geometria) for e in afectadas])
            mensaje = identidad.mensaje_validar(simulada) if simulada.uno_a_uno else None
            c.identidad = simulada if mensaje else None
        except Exception:  # noqa: BLE001 — es una ayuda: nunca impide la comparación
            mensaje = None
        if mensaje:
            c.incidencias.append(Incidencia(INFO, 'CMP-IDENTIDAD', mensaje))
    if len(grupos) > 1:  #Varias operaciones en un GML (p. ej. una multiparcela de dos segregaciones): se dice cada una
        partes = []
        for k, (parte, indices) in enumerate(grupos, start=1):
            de_zona = [propuestas[i] for i in indices]
            interior_zona = parte.buffer(-TOLERANCIA, 4)
            origen_zona = [e for e in afectadas if e.geometria.intersects(interior_zona)
                           and e.geometria.intersection(interior_zona).area() > RUIDO]
            texto_zona, _ = operacion(len(origen_zona), len(de_zona), de_zona, [e.local_id for e in origen_zona])
            partes.append(f"zona {k}: NPO {len(origen_zona)} · NPP {len(de_zona)} → {texto_zona.split(' (')[0]}")
        c.incidencias.append(Incidencia(AVISO, 'CMP-ZONAS', f"El GML tiene {len(grupos)} zonas separadas: la Sede lo trata "
                                                            "como una sola operación (la de arriba), puede dar validación "
                                                            "positiva pero no la tramita de forma automática. Por zonas: "
                                                            + "; ".join(partes) + ". Para tramitarlas, mejor un GML por "
                                                            "operación"))
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
    diseminado = [rc for rc, f in fichas.items() if f and f['diseminado']]
    if diseminado:  #Ayuda de la operativa del IVG: el diseminado de urbana no se tramita de forma automática (AU-33)
        c.incidencias.append(Incidencia(AVISO, 'CMP-DISEMINADO', f"Parcela de urbana en diseminado ({', '.join(diseminado)}): "
                                                                 "no se tramitará de forma automática"))
    bice = [rc for rc, f in fichas.items() if f and 'BI' in f['clases']]
    if bice:
        c.incidencias.append(Incidencia(AVISO, 'CMP-BICE', f"Afecta a un bien inmueble de características especiales (BICE: "
                                                           f"{', '.join(bice)}): no se tramitará de forma automática"))
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
    identificador (RC, RC_Edificio_N, RC_Piscina_N), como el ICUC (ayuda del ICUC y FAQ Catastro-Registro de la DGC):
    entera dentro (informe positivo), en parte fuera (informe negativo, con el exceso marcado) o a más de 100 m (no se
    emite informe). Los solapes entre construcciones (tampoco hay informe) los ve el validador.
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
        c.incidencias.append(Incidencia(AVISO, 'CMP-BU-SIN-RC', f"No se compara con el Catastro: {texto}. El ICUC solo "
                                                                "trabaja con parcelas catastrales vigentes (por su "
                                                                "referencia): si la parcela aún no existe, tramite antes "
                                                                "la alteración"))
        return c
    rc = referencias.pop()
    if refcat.comprobar(rc).foral:
        c.incidencias.append(Incidencia(AVISO, 'RC-FORAL', refcat.comprobar(rc).mensaje))
        return c
    resultado, errores = servicios.consultar_wfs(servicios.url_parcela(rc, lectura.epsg), f"la parcela {rc}")
    if errores and not _no_encontrada(errores):
        c.incidencias += [Incidencia(AVISO, 'CMP-NO-COMPARADO', f"No se ha podido comparar con el Catastro: {i.mensaje}")
                          for i in errores]
        return c
    parcelas = [e for e in (resultado.elementos if resultado and not errores else []) if not e.geometria.isEmpty()]
    if not parcelas:
        c.operacion = "Parcela no encontrada"
        c.incidencias.append(Incidencia(ERROR, 'CMP-RC-NO-EXISTE', f"La parcela {rc} no existe en el Catastro: el ICUC "
                                                                   "necesita una parcela catastral vigente"))
        return c
    c.origen = parcelas
    c.npo, c.npp = 1, len(construcciones)
    datos = servicios.ficha(rc)
    if datos and 'BI' in datos['clases']:  #Ayuda del ICUC: las parcelas BICE no tienen informe (AU-33)
        c.incidencias.append(Incidencia(AVISO, 'CMP-BU-BICE', f"La parcela {rc} es un bien inmueble de características "
                                                              "especiales (BICE): la Sede no emite el ICUC para ellas"))
    exacta = QgsGeometry.unaryUnion([e.geometria for e in parcelas])
    fuera = []
    for e in construcciones:
        distancia = e.geometria.distance(exacta)
        if distancia > DISTANCIA_ICUC:
            fuera.append(e.geometria)
            c.incidencias.append(Incidencia(ERROR, 'CMP-BU-LEJOS', f"La construcción está a {distancia:.0f} m de la parcela "
                                                                   f"{rc}: el ICUC no admite construcciones a más de "
                                                                   f"{DISTANCIA_ICUC:.0f} m y no emite el informe. Compruebe la "
                                                                   "referencia y el SRC",
                                            e.local_id))
            continue
        geometria = e.geometria if e.geometria.isGeosValid() else e.geometria.makeValid()  #Partes solapadas (AU-11)
        resto = fuera_de(geometria, exacta)
        if resto is not None:
            fuera.append(diferencia(geometria, exacta))
            c.incidencias.append(Incidencia(ERROR, 'CMP-BU-FUERA', f"La construcción sale de la parcela catastral {rc} "
                                                                   f"({_medida(resto.area(), desvio(resto, exacta))}): el "
                                                                   "ICUC exige que esté entera dentro, sin extralimitarla "
                                                                   f"(±{TOLERANCIA * 100:.0f} cm). Si el lindero no es "
                                                                   "correcto, tramite antes la alteración de la parcela; si "
                                                                   "la cartografía catastral está desplazada, vea la ayuda "
                                                                   "(el ICUC se pide con el GML desplazado como el Catastro)",
                                            e.local_id))
    if fuera:
        c.exceso = QgsGeometry.unaryUnion(fuera)
        n = len(fuera)
        c.operacion = f"{n} construcci{'ones' if n != 1 else 'ón'} no {'están' if n != 1 else 'está'} entera dentro de la parcela {rc}"
    else:
        c.operacion = f"Construcciones dentro de la parcela {rc}"
        c.incidencias.append(Incidencia(INFO, 'CMP-BU-DENTRO', f"Todas las construcciones están dentro de la parcela "
                                                               f"catastral {rc} (±{TOLERANCIA * 100:.0f} cm)"))
    return c


def _medida(area, distancia):
    """Texto de una diferencia: superficie si es apreciable y, siempre, cuánto se separa."""
    sup = f"{area:.2f} m², " if area >= 0.01 else ''
    return f"{sup}hasta {distancia * 100:.1f} cm"


def _clave_tramite(rc):
    """Polígono (rústica) o manzana (urbana) de una RC: si las afectadas son de varios, no hay tramitación automática."""
    tipo = refcat.tipo_parcela(rc)
    if tipo == 'rústica':
        return f"polígono {int(rc[6:9])} del municipio {rc[:5]}"
    if tipo == 'urbana':
        return f"manzana {rc[:5]}, hoja {rc[7:14]}"
    return ''


def _no_encontrada(errores):
    """El WFS contesta que esa parcela no existe (un ExceptionReport «No se ha encontrado la parcela…»), que no es un fallo
    de conexión (batería de casos, 19/10/2026: con una RC inexistente se decía «no se ha podido comparar»)."""
    return any(i.codigo == 'WFS-EXCEPCION' and 'no se ha encontrado' in i.mensaje.lower() for i in errores)


def _existe(rc, epsg):
    """True o False; None si no se ha podido saber (sin conexión: no se debe decir que no existe)."""
    resultado, errores = servicios.consultar_wfs(servicios.url_parcela(rc, epsg), f"la parcela {rc}")
    if errores:
        return False if _no_encontrada(errores) else None
    return resultado is not None and bool(resultado.elementos)
