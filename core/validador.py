"""
Validador de GML antes de subirlo a la Sede Electrónica del Catastro.

Comprueba lo que se sabe que comprueba la Sede, según la documentación de la DGC y lo aprendido en pruebas reales
(ver docs/INVESTIGACION.md y docs/DESARROLLO.md). No sustituye a la validación de la Sede: hay reglas que la DGC
no publica, por eso el resultado siempre recuerda que hay que validar en la Sede.

Reglas (código de la incidencia entre corchetes):
  Fichero    [GML-*, XML-*]  bien formado, con parcelas o construcciones
             [CP-30]          esquema 3.0: la Sede solo admite el 4.0
             [XLINK]          la raíz debe declarar xmlns:xlink (lo exige la Sede aunque no se use)
             [SRC-*]          un único SRC, de los admitidos (25829, 25830, 25831, 32628)
             [N-PARCELAS]     más de 30 parcelas: la Sede no tramita automáticamente
  Identificadores
             [ID-*]           localId presente, sin caracteres no válidos y no repetido
             [NS-*]           namespace ES.SDGC.CP / ES.LOCAL.CP (ES.SDGC.BU / ES.LOCAL.BU en edificios);
                              con SDGC, el localId debe ser una referencia catastral de 14 caracteres
             [RC-FORAL]       referencia de Navarra o del País Vasco (catastros propios)
             [GMLID]          gml:id coherente con namespace y localId
  Geometría  [GEO-MULTIPARTE] un solo recinto por parcela
             [ANILLO-*]       anillos cerrados, con 4 vértices o más, count correcto, exterior horario y huecos
                              antihorarios
             [GEO-ALINEADOS]  cada anillo encierra superficie (no todos sus vértices alineados)
             [DECIMALES]      coordenadas con 2 decimales como máximo
             [GEO-INVALIDA]   sin autointersecciones
             [SUP-*]          superficie declarada presente y coincidente con la geometría (redondeo al m²)
             [REFPOINT]       punto de referencia dentro de la parcela
             [ESBELTEZ]       proporción largo/ancho mayor que 15: la Sede no tramita automáticamente
  Conjunto   [SOLAPE]         parcelas o construcciones que se superponen
             [HUECO]          huecos entre las parcelas aportadas

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import re
from collections import Counter
from dataclasses import dataclass, field

from qgis.core import QgsCoordinateReferenceSystem, QgsGeometry, QgsPointXY

from . import geometria as geo
from . import gml_lector as gl
from . import refcat
from .incidencias import AVISO, ERROR, Incidencia

NS_PARCELA = ('ES.SDGC.CP', 'ES.LOCAL.CP')
NS_EDIFICIO = ('ES.SDGC.BU', 'ES.LOCAL.BU')
ID_VALIDO = re.compile(r'^[A-Za-z0-9_.\-]+$')
MAX_PARCELAS = 30
MAX_ESBELTEZ = 15
MAX_DECIMALES = 2


@dataclass
class Informe:
    """Resultado de validar un GML."""
    ruta: str
    lectura: object                                  #gml_lector.ResultadoLectura
    incidencias: list = field(default_factory=list)  #Todas, incluidas las de lectura

    @property
    def errores(self):
        return [i for i in self.incidencias if i.nivel == ERROR]

    @property
    def avisos(self):
        return [i for i in self.incidencias if i.nivel == AVISO]

    def de(self, local_id):
        """Incidencias de un elemento (por su localId)."""
        return [i for i in self.incidencias if i.elemento == local_id]

    def estado(self, local_id):
        """'error', 'aviso' o 'correcta' para un elemento."""
        niveles = {i.nivel for i in self.de(local_id)}
        return ERROR if ERROR in niveles else AVISO if AVISO in niveles else 'correcta'


def validar(ruta, lectura=None):
    """Valida un GML (o una lectura ya hecha de él). Devuelve un Informe."""
    lectura = lectura or gl.leer(ruta)
    informe = Informe(ruta, lectura, [i for i in lectura.incidencias if i.codigo != 'GML-LEIDO'])
    if not lectura.elementos:
        return informe
    inc = informe.incidencias
    es_parcela = lectura.version.startswith('CP')

    #Fichero
    if es_parcela and not lectura.xlink_declarado:
        inc.append(Incidencia(ERROR, 'XLINK', "La raíz no declara xmlns:xlink: la Sede rechaza el fichero "
                                               "(«no cumple el esquema Inspire GML») aunque no se use"))
    if es_parcela and lectura.version == 'CP 4.0' and not lectura.raiz.endswith('}FeatureCollection'):
        inc.append(Incidencia(ERROR, 'RAIZ', "La raíz del fichero debe ser FeatureCollection"))
    if lectura.epsg is not None and lectura.epsg not in geo.SRC_ADMITIDOS:
        inc.append(Incidencia(ERROR, 'SRC-NO-ADMITIDO',
                              f"EPSG:{lectura.epsg} no lo admite la Sede: use 25829, 25830, 25831 o 32628"))
    if es_parcela and len(lectura.elementos) > MAX_PARCELAS:
        inc.append(Incidencia(AVISO, 'N-PARCELAS', f"{len(lectura.elementos)} parcelas: la Sede no tramita automáticamente "
                                                    f"más de {MAX_PARCELAS} parcelas resultantes o a unir"))

    #Identificadores repetidos
    repetidos = {k for k, n in Counter(e.local_id for e in lectura.elementos).items() if n > 1 and k}
    for local_id in sorted(repetidos):
        inc.append(Incidencia(ERROR, 'ID-REPETIDO', "Identificador repetido en el fichero", local_id))

    for elemento in lectura.elementos:
        inc += validar_elemento(elemento, es_parcela)

    inc += validar_conjunto(lectura.elementos, es_parcela)

    #Huso que no corresponde a la posición o a la provincia (AU-30)
    geometrias = [e.geometria for e in lectura.elementos if not e.geometria.isNull() and not e.geometria.isEmpty()]
    if geometrias and lectura.epsg in geo.SRC_ADMITIDOS:
        rusticas = [refcat.limpiar(e.local_id)[:14] for e in lectura.elementos
                    if refcat.tipo_parcela(refcat.limpiar(e.local_id)[:14]) == 'rústica']
        aviso = geo.aviso_huso(QgsGeometry.unaryUnion(geometrias), QgsCoordinateReferenceSystem(f'EPSG:{lectura.epsg}'),
                               lectura.epsg, rusticas[0][:2] if rusticas else '')
        if aviso is not None:
            inc.append(aviso)
    return informe


def validar_elemento(e, es_parcela):
    inc = []
    nombre = e.local_id or e.gml_id or '(sin identificador)'
    nss = NS_PARCELA if es_parcela else NS_EDIFICIO

    #Identificador y namespace
    if not e.local_id:
        inc.append(Incidencia(ERROR, 'ID-VACIO', "Falta el identificador (localId)", nombre))
    elif not ID_VALIDO.match(e.local_id):
        inc.append(Incidencia(ERROR, 'ID-CARACTERES', "El identificador tiene espacios, tildes u otros símbolos no válidos",
                              nombre))
    if e.namespace not in nss:
        inc.append(Incidencia(ERROR, 'NS-DESCONOCIDO', f"Namespace «{e.namespace}» no válido: debe ser {' o '.join(nss)}",
                              nombre))
    elif es_parcela and e.namespace == 'ES.SDGC.CP':
        if not refcat.es_rc_exacta(e.local_id):
            inc.append(Incidencia(ERROR, 'NS-SDGC-SIN-RC', "Con ES.SDGC.CP el identificador debe ser la referencia catastral "
                                                           "de 14 caracteres, en mayúsculas y sin separadores (si es una "
                                                           "parcela nueva, use ES.LOCAL.CP)", nombre))
        else:
            r = refcat.comprobar(e.local_id)
            if r.foral:
                inc.append(Incidencia(ERROR, 'RC-FORAL', r.mensaje, nombre))
    if e.gml_id and e.namespace and e.local_id and e.gml_id != f"{e.namespace}.{e.local_id}":
        inc.append(Incidencia(AVISO, 'GMLID', f"gml:id «{e.gml_id}» no coincide con «{e.namespace}.{e.local_id}»", nombre))

    if not es_parcela and e.tipo == gl.EDIFICIO and e.plantas is None:  #Obligatorio en el esquema de edificio de la DGC
        inc.append(Incidencia(ERROR, 'BU-SIN-PLANTAS', "Falta el número de plantas sobre rasante "
                                                       "(numberOfFloorsAboveGround): es obligatorio en el esquema de la DGC",
                              nombre))

    #Geometría
    if e.geometria.isNull() or e.geometria.isEmpty():
        return inc  #Ya avisado por el lector
    if es_parcela and e.recintos > 1:
        inc.append(Incidencia(ERROR, 'GEO-MULTIPARTE', f"La parcela tiene {e.recintos} recintos: la Sede solo admite uno "
                                                       "(una finca discontinua se aporta como varias parcelas)", nombre))
    for i, (anillo, rol) in enumerate(zip(e.anillos, e.roles or ['exterior'] * len(e.anillos)), start=1):
        que = 'exterior' if rol == 'exterior' else f'hueco {i - 1}'
        if len(anillo) < 2 or anillo[0] != anillo[-1]:
            inc.append(Incidencia(ERROR, 'ANILLO-ABIERTO', f"Anillo {que} sin cerrar: el último vértice debe ser igual al primero",
                                  nombre))
        if len(anillo) < geo.MINIMO_VERTICES:
            inc.append(Incidencia(ERROR, 'ANILLO-VERTICES', f"Anillo {que} con {len(anillo)} vértices: el mínimo es 4", nombre))
        count = e.counts[i - 1] if i - 1 < len(e.counts) else None
        if count is not None and count != len(anillo):
            inc.append(Incidencia(ERROR, 'ANILLO-COUNT', f"Anillo {que}: count={count} pero tiene {len(anillo)} vértices",
                                  nombre))
        if len(anillo) >= 4 and anillo[0] == anillo[-1] and geo.degenerado(anillo):
            inc.append(Incidencia(ERROR, 'GEO-ALINEADOS', f"Anillo {que} sin superficie: sus vértices están alineados o "
                                                          "repetidos (la Sede pide al menos 3 vértices no alineados más "
                                                          "el de cierre)", nombre))
        elif len(anillo) >= 4 and anillo[0] == anillo[-1]:
            horario = geo.es_horario(anillo)
            if rol == 'exterior' and not horario:
                inc.append(Incidencia(ERROR, 'ANILLO-SENTIDO', "El anillo exterior va en sentido antihorario: debe ir en "
                                                               "sentido horario", nombre))
            if rol == 'interior' and horario:
                inc.append(Incidencia(ERROR, 'ANILLO-SENTIDO', f"El {que} va en sentido horario: los huecos van en sentido "
                                                               "antihorario", nombre))
    if e.decimales > MAX_DECIMALES:
        inc.append(Incidencia(AVISO, 'DECIMALES', f"Coordenadas con {e.decimales} decimales: la Sede trabaja al centímetro "
                                                  "(2 decimales)", nombre))
    if not e.geometria.isGeosValid():
        errores = e.geometria.validateGeometry()
        detalle = f": {errores[0].what()}" if errores else ''
        inc.append(Incidencia(ERROR, 'GEO-INVALIDA', f"Geometría no válida (autointersección o anillos que se tocan){detalle}",
                              nombre))

    #Superficie, punto de referencia y esbeltez (parcelas)
    if es_parcela:
        calculada = geo.redondear_m2(e.geometria.area())
        if e.area_declarada is None:
            inc.append(Incidencia(ERROR, 'SUP-FALTA', "Falta la superficie (areaValue)", nombre))
        elif abs(e.area_declarada - calculada) >= 1:
            #La Sede ya no lo comprueba (documento de validación de la DGC, v2.1), pero conviene que coincida
            inc.append(Incidencia(AVISO, 'SUP-DISTINTA', f"Superficie declarada (areaValue) {e.area_declarada} m², pero la del "
                                                         f"dibujo es {calculada} m²: la Sede y el Registro toman la del "
                                                         "dibujo (proyección UTM, redondeada al m²). Corrija areaValue "
                                                         "para que el GML no diga dos cosas distintas", nombre))
        if e.punto_referencia is not None:
            punto = QgsGeometry.fromPointXY(QgsPointXY(*e.punto_referencia))
            if not e.geometria.contains(punto):
                inc.append(Incidencia(AVISO, 'REFPOINT', "El punto de referencia (referencePoint) está fuera de la parcela",
                                      nombre))
        caja = e.geometria.orientedMinimumBoundingBox()
        if caja and len(caja) >= 5 and min(caja[3], caja[4]) > 0:
            esbeltez = max(caja[3], caja[4]) / min(caja[3], caja[4])
            if esbeltez > MAX_ESBELTEZ:
                inc.append(Incidencia(AVISO, 'ESBELTEZ', f"Parcela muy alargada (proporción {esbeltez:.0f}:1): la Sede no tramita "
                                                         f"automáticamente parcelas con esbeltez mayor que {MAX_ESBELTEZ}",
                                      nombre))
    return inc


def validar_conjunto(elementos, es_parcela):
    """Solapes entre elementos y, en parcelas, huecos entre las aportadas."""
    inc = []
    validos = [e for e in elementos if not e.geometria.isNull() and not e.geometria.isEmpty()]
    for i, j, area, anchura in geo.solapes([e.geometria for e in validos]):
        inc.append(Incidencia(ERROR, 'SOLAPE', f"Se superpone con {validos[j].local_id} ({area:.2f} m², hasta "
                                               f"{anchura * 100:.0f} cm de ancho)", validos[i].local_id))
    if es_parcela and len(validos) > 1:
        hueco = geo.huecos([e.geometria for e in validos], sum(max(len(e.anillos) - 1, 0) for e in validos))
        if hueco > 0:
            inc.append(Incidencia(AVISO, 'HUECO', f"Hay huecos o franjas sin cubrir entre las parcelas aportadas "
                                                  f"({hueco:.2f} m²): el conjunto debe cubrir el contorno de las parcelas de "
                                                  "origen"))
    return inc


def resumen(informe):
    """Texto corto del resultado."""
    n_err, n_av = len(informe.errores), len(informe.avisos)
    if not informe.lectura.elementos:
        return "No se ha podido leer el fichero"
    if n_err == 0 and n_av == 0:
        return "Sin errores: listo para validarlo en la Sede"
    partes = []
    if n_err:
        partes.append(f"{n_err} error{'es' if n_err != 1 else ''}")
    if n_av:
        partes.append(f"{n_av} aviso{'s' if n_av != 1 else ''}")
    return ' y '.join(partes)

