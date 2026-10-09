"""
Servicios públicos de la Dirección General del Catastro que usa el plugin:
  - WFS INSPIRE de parcelas (wfsCP.aspx): una parcela (GetParcel) y las de su entorno (GetFeature con un rectángulo
    un poco mayor que la parcela), de las que se separan las colindantes por geometría. GetNeighbourParcel no es
    fiable (docs/DESARROLLO.md, E-14): solo se usa si la parcela es demasiado grande para pedir su entorno;
  - WFS INSPIRE de edificios (wfsBU.aspx): edificios (GetBuildingByParcel) y otras construcciones (GetOtherBuildingByParcel);
  - Consulta_RCCOOR (JSON): referencia catastral de la parcela que hay en un punto;
  - Consulta_DNPRC (JSON): datos no protegidos de una parcela de rústica (paraje y clase de cultivo), para confirmar
    si es de dominio público (docs/DESARROLLO.md, E-15).

Solo datos públicos (geometría, referencia, superficie, dirección): nunca titulares ni valores. Se descarga una
parcela concreta cada vez, no zonas enteras. Todo lo descargado se cita como «Dirección General del Catastro» con la
fecha de descarga.

Las peticiones son bloqueantes: hay que llamar a descargar() y rc_en_punto() desde una QgsTask (fuera del hilo de la
interfaz). Para las pruebas basta con sustituir pedir() por una función que devuelva respuestas de ejemplo.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import datetime
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.parse import quote, urlencode

from qgis.core import (
    QgsBlockingNetworkRequest,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
)
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from . import geometria as geo
from . import gml_lector as gl
from . import refcat
from .incidencias import AVISO, ERROR, INFO, Incidencia, hay_errores
from .info import FUENTE_DGC, FUENTE_NAVARRA

WFS_CP = 'https://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx'
WFS_BU = 'https://ovc.catastro.meh.es/INSPIRE/wfsBU.aspx'
RCCOOR = 'https://ovc.catastro.meh.es/OVCServWeb/OVCWcfCallejero/COVCCoordenadas.svc/json/Consulta_RCCOOR'
EPSG_INICIAL = 25830  #Se pide primero en el huso 30 y, si la parcela cae en otro huso, se vuelve a pedir en el suyo
MARGEN_ENTORNO = 25.0           #m alrededor de la parcela en los que se buscan las parcelas del entorno
TOLERANCIA_COLINDANTE = 0.20    #m: a menos de esta distancia se considera colindante (calles de por medio: no)
AREA_MAXIMA_ENTORNO = 1_000_000  #m²: el WFS no admite rectángulos mayores («Area of extension out of limits»)
SIN_COLINDANTES = 'No se han encontrado parcelas colindantes'  #Texto del ExceptionReport cuando no hay ninguna
#Navarra (Registro de la Riqueza Territorial): servicios INSPIRE del Gobierno de Navarra, CC BY 4.0, todo en el huso 30
WFS_NAVARRA_CP = 'https://inspire.navarra.es/services/CP/wfs'
WFS_NAVARRA_BU = 'https://inspire.navarra.es/services/BU/wfs'
EPSG_NAVARRA = 25830
CAJA_NAVARRA = (-2.55, 41.88, -0.70, 43.35)  #lon/lat aproximados: solo para no preguntar a Navarra por puntos de fuera
AVISO_NAVARRA = ("Parcela de Navarra (Registro de la Riqueza Territorial). El GML de la Sede Electrónica de la DGC no sirve "
                 "en Navarra: sus alteraciones se tramitan ante la Hacienda Foral de Navarra")
DNPRC = 'https://ovc.catastro.meh.es/OVCServWeb/OVCWcfCallejero/COVCCallejero.svc/json/Consulta_DNPRC'
#Usos de las parcelas de dominio público de rústica (9001-9999) según la DGC: VT y HG comprobados además en
#Consulta_DNPRC el 07/10/2026. OT («otros») no se usa como prueba por sí solo: cuenta la numeración
CULTIVOS_DOMINIO_PUBLICO = {'VT': 'vías de comunicación', 'HG': 'hidrografía natural', 'HC': 'hidrografía construida',
                            'FF': 'ferrocarril'}
MAX_CONSULTAS_DNPRC = 60  #Como mucho, tantas consultas de datos por descarga (una por parcela de rústica)
EPSG_PUNTO = 4258     #Las coordenadas del clic se envían en ETRS89 geográficas (lon, lat): vale para toda España
AVISO_FORAL = ("Si está en Navarra o en el País Vasco, consulte su catastro foral: no lo gestiona la Dirección General "
               "del Catastro")


# ------------------------------------------------------------------ Direcciones de los servicios

def _wfs(base, consulta, rc, epsg):
    return base + '?' + urlencode({'service': 'wfs', 'version': '2.0.0', 'request': 'GetFeature',
                                   'STOREDQUERIE_ID': consulta, 'refcat': rc, 'srsname': f'EPSG::{epsg}'})


def url_parcela(rc, epsg=EPSG_INICIAL):
    return _wfs(WFS_CP, 'GetParcel', rc, epsg)


def url_colindantes(rc, epsg=EPSG_INICIAL):
    return _wfs(WFS_CP, 'GetNeighbourParcel', rc, epsg)


def url_entorno(rectangulo, epsg=EPSG_INICIAL):
    """Parcelas que tocan un rectángulo (QgsRectangle en el EPSG indicado)."""
    caja = ','.join(f'{v:.2f}' for v in (rectangulo.xMinimum(), rectangulo.yMinimum(), rectangulo.xMaximum(),
                                          rectangulo.yMaximum()))
    return WFS_CP + '?' + urlencode({'service': 'wfs', 'version': '2.0.0', 'request': 'GetFeature',
                                     'typeNames': 'CP:CadastralParcel', 'srsName': f'EPSG::{epsg}', 'bbox': caja})


def url_edificios(rc, epsg=EPSG_INICIAL):
    return _wfs(WFS_BU, 'GetBuildingByParcel', rc, epsg)


def url_partes(rc, epsg=EPSG_INICIAL):
    """Partes de los edificios (BuildingPart): traen las plantas sobre rasante, que el edificio deja vacías."""
    return _wfs(WFS_BU, 'GetBuildingPartByParcel', rc, epsg)


def url_otras(rc, epsg=EPSG_INICIAL):
    return _wfs(WFS_BU, 'GetOtherBuildingByParcel', rc, epsg)


def url_datos(rc):
    return DNPRC + '?' + urlencode({'RefCat': rc})


def _wfs_navarra(base, tipo, **parametros):
    consulta = {'service': 'WFS', 'version': '2.0.0', 'request': 'GetFeature', 'typeNames': tipo,
                'srsName': f'EPSG:{EPSG_NAVARRA}'}
    consulta.update(parametros)
    return base + '?' + urlencode(consulta, quote_via=quote)


def url_navarra_parcela(ref9):
    """Parcela de Navarra por su identificador INSPIRE (ES.RRTN.CP.<9 dígitos>), con un filtro FES ResourceId."""
    filtro = f'<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0"><fes:ResourceId rid="ES.RRTN.CP.{ref9}"/></fes:Filter>'
    return _wfs_navarra(WFS_NAVARRA_CP, 'CP:CadastralParcel', FILTER=filtro)


def _caja(rectangulo):
    return ','.join(f'{v:.2f}' for v in (rectangulo.xMinimum(), rectangulo.yMinimum(), rectangulo.xMaximum(),
                                          rectangulo.yMaximum())) + f',urn:ogc:def:crs:EPSG::{EPSG_NAVARRA}'


def url_navarra_entorno(rectangulo):
    return _wfs_navarra(WFS_NAVARRA_CP, 'CP:CadastralParcel', bbox=_caja(rectangulo))


def url_navarra_edificios(rectangulo):
    return _wfs_navarra(WFS_NAVARRA_BU, 'BU:Building', bbox=_caja(rectangulo))


def url_rc_en_punto(x, y, epsg=EPSG_PUNTO):
    return RCCOOR + '?' + urlencode({'SRS': f'EPSG:{epsg}', 'CoorX': f'{x:.6f}' if epsg == 4258 else f'{x:.2f}',
                                     'CoorY': f'{y:.6f}' if epsg == 4258 else f'{y:.2f}'})


# ------------------------------------------------------------------ Peticiones

def pedir(url):
    """Descarga una dirección con la red de QGIS (respeta el proxy). Devuelve (contenido, texto de error o '')."""
    peticion = QNetworkRequest(QUrl(url))
    peticion.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                          QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
    red = QgsBlockingNetworkRequest()
    if red.get(peticion, True) != QgsBlockingNetworkRequest.ErrorCode.NoError:
        return b'', red.errorMessage() or 'error de red'
    return bytes(red.reply().content()), ''


def excepcion_wfs(datos):
    """Texto de un ExceptionReport del WFS (p. ej. «No se ha encontrado la parcela…»), o '' si no lo es."""
    if b'ExceptionReport' not in datos[:600]:
        return ''
    try:
        raiz = ET.fromstring(datos)
    except ET.ParseError:
        return 'respuesta de error del servicio'
    textos = [(e.text or '').strip() for e in raiz.iter() if gl.nombre_local(e.tag) == 'ExceptionText']
    return ' '.join(t for t in textos if t) or 'respuesta de error del servicio'


def consultar_wfs(url, que):
    """
    Pide una consulta WFS y la lee con el lector del plugin. Devuelve (ResultadoLectura o None, incidencias).
    Una colección vacía (p. ej. una parcela sin otras construcciones) no es un error.
    """
    datos, error = pedir(url)
    if error:
        return None, [Incidencia(ERROR, 'RED', f"No se ha podido descargar {que}: {error}")]
    texto_error = excepcion_wfs(datos)
    if texto_error:
        return None, [Incidencia(ERROR, 'WFS-EXCEPCION', f"{que[0].upper()}{que[1:]}: {texto_error}")]
    resultado = gl.leer_datos(datos)
    if any(i.codigo == 'XML-MAL-FORMADO' for i in resultado.incidencias):
        return None, [Incidencia(ERROR, 'WFS-RESPUESTA', f"El servicio no ha devuelto un GML válido para {que}")]
    resultado.incidencias = [i for i in resultado.incidencias if i.codigo not in ('GML-SIN-ELEMENTOS', 'GML-LEIDO')]
    return resultado, [i for i in resultado.incidencias if i.nivel == ERROR]


# ------------------------------------------------------------------ Descarga de una parcela

@dataclass
class Descarga:
    rc: str = ''                       #Referencia de la parcela (14 caracteres)
    epsg: object = None                #SRC en el que se ha descargado (el huso de la parcela)
    parcela: object = None             #ResultadoLectura con la parcela
    colindantes: object = None         #ResultadoLectura con las colindantes (sin la propia parcela)
    entorno: object = None             #ResultadoLectura con las demás parcelas a menos de MARGEN_ENTORNO m
    construcciones: object = None      #ResultadoLectura con edificios y otras construcciones juntos
    incidencias: list = field(default_factory=list)
    fecha: object = None               #datetime de la descarga
    territorio: str = ''               #'' (Dirección General del Catastro) o 'Navarra'

    @property
    def correcta(self):
        return self.parcela is not None and bool(self.parcela.elementos) and not hay_errores(self.incidencias)

    def atribucion(self):
        """Cita de la fuente de los datos con la fecha de descarga."""
        fecha = f" · descargado el {self.fecha:%d/%m/%Y %H:%M}" if self.fecha else ''
        return f"© {FUENTE_NAVARRA if self.territorio == 'Navarra' else FUENTE_DGC}{fecha}"


def descargar(rc, colindantes=True, construcciones=True, epsg=None, ahora=None):
    """
    Descarga una parcela por su referencia catastral y, si se pide, sus colindantes y sus construcciones, en el huso
    UTM que le corresponde (o en el EPSG indicado). Nunca lanza excepciones: los problemas van en descarga.incidencias.
    """
    descarga = Descarga(fecha=ahora or datetime.datetime.now())
    comprobada = refcat.comprobar(rc)
    descarga.rc = comprobada.parcela or comprobada.rc
    if not comprobada.valida and refcat.navarra(rc):
        return _descargar_navarra(descarga, refcat.navarra(rc), colindantes, construcciones)
    if not comprobada.valida:
        descarga.incidencias.append(Incidencia(ERROR, 'RC', comprobada.mensaje))
        return descarga
    if comprobada.foral:
        descarga.incidencias.append(Incidencia(ERROR, 'RC-FORAL', f"{comprobada.mensaje}. Los servicios de la DGC no "
                                                                  "tienen sus parcelas"))
        return descarga

    pedido = epsg or EPSG_INICIAL
    parcela, errores = consultar_wfs(url_parcela(descarga.rc, pedido), f"la parcela {descarga.rc}")
    if errores or parcela is None or not parcela.elementos:
        descarga.incidencias += errores or [Incidencia(ERROR, 'WFS-VACIO', f"No se ha encontrado la parcela {descarga.rc}")]
        return descarga
    if epsg is None:  #Huso de la parcela según su posición; si no es el 30, se vuelve a pedir en el suyo
        propio = geo.epsg_recomendado(parcela.elementos[0].geometria, QgsCoordinateReferenceSystem(f'EPSG:{pedido}'))
        if propio and propio != pedido:
            otra, errores = consultar_wfs(url_parcela(descarga.rc, propio), f"la parcela {descarga.rc}")
            if otra is not None and otra.elementos and not errores:
                parcela, pedido = otra, propio
    descarga.parcela, descarga.epsg = parcela, pedido

    if colindantes:
        _vecinas(descarga, parcela.elementos[0].geometria, pedido)
    if construcciones:
        edificios, errores = consultar_wfs(url_edificios(descarga.rc, pedido), "los edificios")
        if edificios is not None and any(e.plantas is None for e in edificios.elementos if e.tipo == gl.EDIFICIO):
            datos, error = pedir(url_partes(descarga.rc, pedido))
            plantas_de_partes(edificios.elementos, [] if error else gl.leer_partes(datos))
        otras, errores_otras = consultar_wfs(url_otras(descarga.rc, pedido), "las otras construcciones")
        descarga.incidencias += [Incidencia(AVISO, i.codigo, i.mensaje) for i in errores + errores_otras]
        juntas = edificios or otras
        if juntas is not None:
            juntas.elementos = (edificios.elementos if edificios else []) + (otras.elementos if otras else [])
            juntas.version = 'BU 2.0'
            juntas.epsg = juntas.epsg or pedido
            descarga.construcciones = juntas

    _resumen(descarga, colindantes, construcciones)
    return descarga


def plantas_de_partes(edificios, partes):
    """
    El WFS de la DGC deja vacías las plantas del edificio (numberOfFloorsAboveGround nil) y las da en sus partes
    (GetBuildingPartByParcel, una por volumen: «RC_part1»…). Para el GML de edificio vale la máxima: se pone en cada
    edificio sin plantas la máxima de las partes que caen dentro de él (comprobado con 2082107VF2628S el 09/10/2026).
    """
    for edificio in edificios:
        if edificio.tipo != gl.EDIFICIO or edificio.plantas is not None or edificio.geometria.isEmpty():
            continue
        dentro = [p.plantas for p in partes if p.plantas is not None and not p.geometria.isEmpty()
                  and edificio.geometria.intersection(p.geometria).area() > 0.5 * min(p.geometria.area(), 1.0)]
        if dentro:
            edificio.plantas = max(dentro)


def _resumen(descarga, colindantes, construcciones):
    e = descarga.parcela.elementos[0]
    pedido = descarga.epsg
    n_col = len(descarga.colindantes.elementos) if descarga.colindantes else 0
    n_pub = len([e for e in descarga.colindantes.elementos if e.tipo == gl.DOMINIO_PUBLICO]) if descarga.colindantes else 0
    n_con = len(descarga.construcciones.elementos) if descarga.construcciones else 0
    descarga.incidencias.append(Incidencia(
        INFO, 'DESCARGA', f"Parcela {descarga.rc} · {e.area_declarada if e.area_declarada is not None else '?'} m² · "
                          f"EPSG:{pedido}" + (f" · {n_col} colindante{'s' if n_col != 1 else ''}"
                                             + (f" ({n_pub} de dominio público)" if n_pub else '') if colindantes else '')
                          + (f" · {len(descarga.entorno.elementos)} en el entorno" if descarga.entorno else '')
                          + (f" · {n_con} construcci{'ones' if n_con != 1 else 'ón'}" if construcciones else '')))


def _descargar_navarra(descarga, ref9, colindantes, construcciones):
    """
    Parcela de Navarra del servicio INSPIRE del Gobierno de Navarra (Registro de la Riqueza Territorial): la parcela por
    su referencia, el entorno por rectángulo (colindantes por geometría, como en la DGC) y sus edificios (los del
    rectángulo de la parcela cuyo identificador empieza por su referencia). Siempre en EPSG:25830.
    """
    municipio, poligono, numero = refcat.navarra_partes(ref9)
    descarga.rc, descarga.territorio, descarga.epsg = ref9, 'Navarra', EPSG_NAVARRA
    que = f"la parcela {numero} del polígono {poligono} de {municipio:03d} (Navarra)"
    parcela, errores = consultar_wfs(url_navarra_parcela(ref9), que)
    if errores or parcela is None or not parcela.elementos:
        descarga.incidencias += errores or [Incidencia(ERROR, 'WFS-VACIO', f"No se ha encontrado {que} en el Registro de "
                                                                          "la Riqueza Territorial")]
        return descarga
    descarga.parcela = parcela
    geometria = parcela.elementos[0].geometria
    if colindantes:
        caja = geometria.boundingBox()
        caja.grow(MARGEN_ENTORNO)
        todas, errores = consultar_wfs(url_navarra_entorno(caja), "las parcelas del entorno")
        descarga.incidencias += [Incidencia(AVISO, i.codigo, i.mensaje) for i in errores]
        if todas is not None and not errores:
            _separar(descarga, todas, geometria)
    if construcciones:
        edificios, errores = consultar_wfs(url_navarra_edificios(geometria.boundingBox()), "los edificios")
        descarga.incidencias += [Incidencia(AVISO, i.codigo, i.mensaje) for i in errores]
        if edificios is not None:
            edificios.elementos = [e for e in edificios.elementos if e.local_id.startswith(ref9)]
            edificios.epsg = edificios.epsg or EPSG_NAVARRA
            descarga.construcciones = edificios
    descarga.incidencias.append(Incidencia(INFO, 'NAVARRA', AVISO_NAVARRA))
    _resumen(descarga, colindantes, construcciones)
    return descarga


def _vecinas(descarga, geometria, epsg):
    """
    Colindantes (a menos de TOLERANCIA_COLINDANTE m) y parcelas del entorno (a menos de MARGEN_ENTORNO m), pidiendo al
    WFS las parcelas de un rectángulo algo mayor que la parcela. Si la parcela es tan grande que el rectángulo pasa del
    límite del servicio, se usa GetNeighbourParcel (solo colindantes).
    """
    caja = geometria.boundingBox()
    caja.grow(MARGEN_ENTORNO)
    if caja.area() <= AREA_MAXIMA_ENTORNO:
        todas, errores = consultar_wfs(url_entorno(caja, epsg), "las parcelas del entorno")
        if todas is not None and not errores:
            _separar(descarga, todas, geometria)
            _marcar_dominio_publico(descarga)
            return
    vecinas, errores = consultar_wfs(url_colindantes(descarga.rc, epsg), "las parcelas colindantes")
    if errores and all(SIN_COLINDANTES in i.mensaje for i in errores):
        descarga.colindantes = gl.ResultadoLectura(version='CP 4.0', epsg=epsg)
        descarga.incidencias.append(Incidencia(INFO, 'SIN-COLINDANTES', _texto_sin_colindantes([])))
        return
    descarga.incidencias += [Incidencia(AVISO, i.codigo, i.mensaje) for i in errores]
    if vecinas is not None:
        #El servicio a veces incluye la propia parcela entre las colindantes
        vecinas.elementos = [e for e in vecinas.elementos if e.local_id != descarga.rc]
        descarga.colindantes = vecinas
        _marcar_dominio_publico(descarga)


def datos_rustica(rc):
    """
    Datos no protegidos de una parcela de rústica (Consulta_DNPRC): {'paraje', 'cultivos': [(código, descripción)],
    'texto'}. None si no se puede consultar o la respuesta no es la esperada. Nunca titulares ni valores.
    """
    datos, error = pedir(url_datos(rc))
    if error:
        return None
    try:
        bico = json.loads(datos.decode('utf-8', 'replace'))['consulta_dnprcResult']['bico']
        bi = bico['bi']
        lugar = bi.get('dt', {}).get('locs', {}).get('lors', {}).get('lorus', {})
        subparcelas = bico.get('lspr') or []
        if isinstance(subparcelas, dict):
            subparcelas = [subparcelas]
        cultivos = [(str(sp.get('dspr', {}).get('ccc', '')), str(sp.get('dspr', {}).get('dcc', '')))
                    for sp in subparcelas if isinstance(sp, dict)]
        return {'paraje': str(lugar.get('npa', '')).strip(), 'cultivos': cultivos, 'texto': str(bi.get('ldt', ''))}
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def _sin_tildes(texto):
    return texto.upper().translate(str.maketrans('ÁÉÍÓÚ', 'AEIOU'))


def es_dominio_publico_segun(datos):
    """True si los datos de Consulta_DNPRC indican dominio público (clase de cultivo o texto de la DGC)."""
    if not datos:
        return False
    textos = _sin_tildes(datos['texto'] + ' ' + ' '.join(d for _, d in datos['cultivos']))
    return (any(c in CULTIVOS_DOMINIO_PUBLICO for c, _ in datos['cultivos'])
            or 'DOMINIO PUBLICO' in textos or 'DOMIIO PUBLICO' in textos)  #La DGC lo escribe a veces así


def _descripcion(datos):
    partes = [datos['paraje'].capitalize()] if datos['paraje'] else []
    partes += [d.capitalize() for _, d in datos['cultivos'][:2] if d]
    return ' · '.join(partes)


def _marcar_dominio_publico(descarga):
    """
    Parcelas de dominio público entre las colindantes y el entorno: se consulta a la DGC (Consulta_DNPRC) cada colindante
    de rústica y cada parcela del entorno con número 9001-9999. Es de dominio público si la DGC lo dice (clase VT o HG,
    o «dominio público» en su descripción) o, si no se puede consultar, si su número está entre 9001 y 9999 (se indica
    «sin confirmar»). Cambian de tipo para verse aparte, llevan la descripción de la DGC y se avisa si lindan.
    """
    colindantes = descarga.colindantes.elementos if descarga.colindantes else []
    entorno = descarga.entorno.elementos if descarga.entorno else []
    candidatas = [e for e in colindantes if refcat.tipo_parcela(e.local_id[:14]) == 'rústica']
    candidatas += [e for e in entorno if refcat.es_dominio_publico(e.local_id)]
    for e in candidatas[:MAX_CONSULTAS_DNPRC]:
        datos = datos_rustica(e.local_id)
        if datos:
            e.descripcion = _descripcion(datos)
            publica = es_dominio_publico_segun(datos) or refcat.es_dominio_publico(e.local_id)
        else:
            publica = refcat.es_dominio_publico(e.local_id)
            if publica:
                e.descripcion = "Parcela 9001-9999 de rústica (sin confirmar: no se ha podido consultar el Catastro)"
        if publica:
            e.tipo = gl.DOMINIO_PUBLICO
    publicas = [e.local_id + (f" ({e.descripcion.split(' · ')[0].lower()})" if e.descripcion else '')
                for e in colindantes if e.tipo == gl.DOMINIO_PUBLICO]
    if publicas:
        descarga.incidencias.append(Incidencia(
            INFO, 'LINDA-DOMINIO-PUBLICO',
            f"Linda con dominio público: {', '.join(publicas[:4])}"
            + (f" y {len(publicas) - 4} más" if len(publicas) > 4 else '') + ". Ese lindero no se puede "
            "mover sin contar con su deslinde y su Administración titular"))


def _separar(descarga, todas, geometria):
    """Parte las parcelas de un rectángulo en colindantes (tocan la parcela) y entorno (a menos de MARGEN_ENTORNO m)."""
    otras = [e for e in todas.elementos if e.local_id != descarga.rc and not e.geometria.isEmpty()]
    distancias = [(e, e.geometria.distance(geometria)) for e in otras]
    cerca = [e for e, d in distancias if d <= TOLERANCIA_COLINDANTE]
    lejos = [e for e, d in distancias if TOLERANCIA_COLINDANTE < d <= MARGEN_ENTORNO]
    descarga.colindantes = _copia(todas, cerca)
    descarga.entorno = _copia(todas, lejos)
    if not cerca:
        descarga.incidencias.append(Incidencia(INFO, 'SIN-COLINDANTES', _texto_sin_colindantes(lejos)))


def _copia(resultado, elementos):
    return gl.ResultadoLectura(version=resultado.version, epsg=resultado.epsg, elementos=list(elementos))


def _texto_sin_colindantes(cercanas):
    texto = "La parcela no tiene parcelas colindantes en el Catastro: la rodean calles u otro suelo sin parcela"
    if cercanas:
        texto += f" (se añaden las {len(cercanas)} parcelas a menos de {MARGEN_ENTORNO:.0f} m como entorno)"
    return texto


# ------------------------------------------------------------------ Referencia catastral en un punto

@dataclass
class ParcelaEnPunto:
    rc: str = ''
    direccion: str = ''
    incidencias: list = field(default_factory=list)


def rc_en_punto(x, y, epsg=EPSG_PUNTO):
    """Referencia catastral (14 caracteres) y dirección de la parcela que hay en un punto (Consulta_RCCOOR)."""
    resultado = ParcelaEnPunto()
    datos, error = pedir(url_rc_en_punto(x, y, epsg))
    if error:
        resultado.incidencias.append(Incidencia(ERROR, 'RED', f"No se ha podido consultar el Catastro: {error}"))
        return resultado
    try:
        respuesta = json.loads(datos.decode('utf-8', 'replace'))['Consulta_RCCOORResult']
    except (ValueError, KeyError, TypeError):
        resultado.incidencias.append(Incidencia(ERROR, 'RCCOOR-RESPUESTA', "Respuesta no esperada del Catastro"))
        return resultado
    errores = respuesta.get('lerr') or []
    if errores and epsg == EPSG_PUNTO and _en_navarra(x, y):
        ref9 = _navarra_en_punto(x, y)
        if ref9:  #Navarra no está en los servicios de la DGC: se pregunta al del Gobierno de Navarra
            resultado.rc = ref9
            municipio, poligono, numero = refcat.navarra_partes(ref9)
            resultado.direccion = f"Navarra · municipio {municipio:03d}, polígono {poligono}, parcela {numero}"
            return resultado
    if errores:
        texto = '; '.join(str(e.get('des', '')).strip().capitalize() for e in errores if isinstance(e, dict))
        resultado.incidencias.append(Incidencia(ERROR, 'RCCOOR-SIN-PARCELA',
                                                f"{texto or 'No hay parcela en ese punto'}. {AVISO_FORAL}"))
        return resultado
    coordenadas = (respuesta.get('coordenadas') or {}).get('coord') or []
    if isinstance(coordenadas, dict):
        coordenadas = [coordenadas]
    if not coordenadas:
        resultado.incidencias.append(Incidencia(ERROR, 'RCCOOR-SIN-PARCELA', f"No hay parcela en ese punto. {AVISO_FORAL}"))
        return resultado
    primera = coordenadas[0]
    pc = primera.get('pc') or {}
    resultado.rc = f"{pc.get('pc1', '')}{pc.get('pc2', '')}".strip()
    resultado.direccion = str(primera.get('ldt', '')).strip()
    if refcat.navarra(resultado.rc):  #En Navarra, Consulta_RCCOOR devuelve su referencia de 9 dígitos
        municipio, poligono, numero = refcat.navarra_partes(resultado.rc)
        resultado.direccion = (resultado.direccion or
                               f"Navarra · municipio {municipio:03d}, polígono {poligono}, parcela {numero}")
        return resultado
    if len(resultado.rc) != 14:
        resultado.incidencias.append(Incidencia(ERROR, 'RCCOOR-RESPUESTA', "El Catastro no ha devuelto una referencia válida"))
    return resultado


def _en_navarra(lon, lat):
    return CAJA_NAVARRA[0] <= lon <= CAJA_NAVARRA[2] and CAJA_NAVARRA[1] <= lat <= CAJA_NAVARRA[3]


def _navarra_en_punto(lon, lat):
    """Referencia de Navarra (9 dígitos) de la parcela que contiene un punto en ETRS89 geográficas, o ''."""
    transformacion = QgsCoordinateTransform(QgsCoordinateReferenceSystem(f'EPSG:{EPSG_PUNTO}'),
                                            QgsCoordinateReferenceSystem(f'EPSG:{EPSG_NAVARRA}'), QgsProject.instance())
    p = transformacion.transform(QgsPointXY(lon, lat))
    todas, errores = consultar_wfs(url_navarra_entorno(QgsRectangle(p.x() - 0.5, p.y() - 0.5, p.x() + 0.5, p.y() + 0.5)),
                                   "la parcela del punto (Navarra)")
    if errores or todas is None:
        return ''
    punto = QgsGeometry.fromPointXY(p)
    dentro = [e for e in todas.elementos if e.geometria.contains(punto)] or todas.elementos
    return dentro[0].local_id if dentro and refcat.navarra(dentro[0].local_id) else ''
