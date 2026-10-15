"""
Validación de un GML contra los esquemas XSD oficiales (INSPIRE CadastralParcels 4.0 + WFS 2.0, o BuildingExtended2D).

Lección aprendida (docs/DESARROLLO.md, E-10): libxml2 (lxml) no descarga por https ni sigue redirecciones, y si no
encuentra un esquema importado valida sin comprobar nada y dice «válido». Por eso:
  - los esquemas se descargan con la red de QGIS (respeta el proxy y sigue redirecciones) mediante un «resolver»;
  - se guardan en una caché del perfil de QGIS (la segunda vez no hace falta internet);
  - si falta cualquier esquema, el resultado es «no se ha podido comprobar», nunca «válido».

Hay que llamar a validar() fuera del hilo principal (en una QgsTask): la primera vez descarga unos 80 ficheros.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import contextlib
import hashlib
import os
import threading

from qgis.core import QgsApplication, QgsBlockingNetworkRequest
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from .incidencias import AVISO, ERROR, INFO, Incidencia

ESQUEMA_PARCELA = {
    'http://www.opengis.net/wfs/2.0': 'http://schemas.opengis.net/wfs/2.0/wfs.xsd',
    'http://inspire.ec.europa.eu/schemas/cp/4.0': 'http://inspire.ec.europa.eu/schemas/cp/4.0/CadastralParcels.xsd',
}
#Copia del esquema de edificio modificada por la DGC (ayuda del ICUC)
ESQUEMA_EDIFICIO = {
    'http://www.opengis.net/gml/3.2': 'http://schemas.opengis.net/gml/3.2.1/gml.xsd',
    'http://inspire.jrc.ec.europa.eu/schemas/bu-ext2d/2.0':
        'https://www.catastro.hacienda.gob.es/ws/esquemas/GML/inspire.ec.europa.eu/draft-schemas/bu-ext2d/2.0/'
        'BuildingExtended2D.xsd',
}
MAX_ERRORES = 15


#Cancelación de la descarga en curso (la tarea de Validar pone aquí su QgsFeedback). Antes la descarga de los ~80
#esquemas no se podía cortar: al cerrar QGIS o el plugin a mitad, el proceso podía quedarse esperando a la red
_contexto = threading.local()


def carpeta_cache():
    #CGT_ESQUEMAS: otra carpeta (las pruebas usan una común para no bajar los esquemas en cada una)
    ruta = os.environ.get('CGT_ESQUEMAS') or os.path.join(QgsApplication.qgisSettingsDirPath(), 'catastral_gml_tools',
                                                           'esquemas')
    os.makedirs(ruta, exist_ok=True)
    return ruta


def _fichero_cache(url):
    nombre = url.rstrip('/').rsplit('/', 1)[-1] or 'esquema.xsd'
    return os.path.join(carpeta_cache(), hashlib.sha1(url.encode('utf-8')).hexdigest()[:12] + '_' + nombre)


XS_SCHEMA = '{http://www.w3.org/2001/XMLSchema}schema'


def es_esquema(datos):
    """
    True si los bytes son un XSD de verdad (raíz xs:schema). Una página de error, la de un proxy o un portal cautivo,
    o un fichero cortado a medias no lo son: no se guardan en la caché ni se usan (AU-39).
    """
    if not datos or not datos.lstrip().startswith(b'<'):
        return False
    try:
        from lxml import etree
        raiz = etree.fromstring(datos, etree.XMLParser(resolve_entities=False, no_network=True))
    except Exception:  # noqa: BLE001  (sin lxml o XML roto: no es un esquema utilizable)
        return False
    return raiz.tag == XS_SCHEMA


def _guardar(cache, datos):
    """Escritura atómica: se escribe aparte y se renombra (dos validaciones a la vez o un cierre a medias no la dejan rota)."""
    temporal = f"{cache}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(temporal, 'wb') as f:
            f.write(datos)
        os.replace(temporal, cache)
    except OSError:
        with contextlib.suppress(OSError):
            os.remove(temporal)


def descargar(url):
    """Contenido de un esquema: de la caché o, si no está, de internet con la red de QGIS. b'' si no se puede."""
    cache = _fichero_cache(url)
    if os.path.isfile(cache) and os.path.getsize(cache) > 0:
        with open(cache, 'rb') as f:
            datos = f.read()
        if es_esquema(datos):
            return datos
        with contextlib.suppress(OSError):  #Caché estropeada (de una versión anterior del plugin): se vuelve a bajar
            os.remove(cache)
    feedback = getattr(_contexto, 'feedback', None)
    if feedback is not None and feedback.isCanceled():
        return b''
    peticion = QNetworkRequest(QUrl(url))
    peticion.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                          QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
    red = QgsBlockingNetworkRequest()
    if red.get(peticion, True, feedback) != QgsBlockingNetworkRequest.ErrorCode.NoError:
        return b''
    datos = bytes(red.reply().content())
    if not es_esquema(datos):
        return b''
    _guardar(cache, datos)
    return datos


def vaciar_cache():
    """Borra los esquemas guardados (se vuelven a descargar la próxima vez)."""
    carpeta = carpeta_cache()
    for nombre in os.listdir(carpeta):
        with contextlib.suppress(OSError):
            os.remove(os.path.join(carpeta, nombre))


def _resolver_clase(etree, faltan):
    class Resolver(etree.Resolver):
        """Todas las URL de los esquemas pasan por aquí: se sirven desde la caché o con la red de QGIS."""

        def resolve(self, url, pubid, context):
            if not url or not url.startswith(('http://', 'https://')):
                return None
            datos = descargar(url)
            if not datos:
                faltan.append(url)
                return self.resolve_string('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>', context)
            return self.resolve_string(datos, context, base_url=url)
    return Resolver


def envoltorio(esquemas):
    """XSD mínimo que importa los esquemas necesarios (para validar ficheros que mezclan espacios de nombres)."""
    importa = ''.join(f'<xs:import namespace="{ns}" schemaLocation="{url}"/>' for ns, url in esquemas.items())
    return ('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:catastral-gml-tools:envoltorio" '
            f'elementFormDefault="qualified">{importa}</xs:schema>').encode()


def validar(datos, version, feedback=None):
    """
    Valida los bytes de un GML. version: 'CP 4.0' o 'BU 2.0' (otra cosa no se valida).
    Devuelve una lista de Incidencia. Nunca dice «válido» si falta algún esquema. feedback: QgsFeedback para cortar la
    descarga de los esquemas (al cancelar, los que falten cuentan como no descargados).
    """
    _contexto.feedback = feedback
    try:
        return _validar(datos, version)
    finally:
        _contexto.feedback = None


def _validar(datos, version):
    try:
        from lxml import etree
    except ImportError:
        return [Incidencia(AVISO, 'XSD-SIN-LXML', "No se puede comprobar el esquema XSD: falta la librería lxml en este QGIS")]
    if version == 'CP 4.0':
        esquemas = ESQUEMA_PARCELA
    elif version == 'BU 2.0':
        esquemas = ESQUEMA_EDIFICIO
    else:
        return [Incidencia(AVISO, 'XSD-VERSION', f"No se comprueba el esquema de un GML {version or 'desconocido'}")]
    for intento in (1, 2):
        faltan = []
        parser = etree.XMLParser(no_network=True, resolve_entities=False)
        parser.resolvers.add(_resolver_clase(etree, faltan)())
        try:
            esquema = etree.XMLSchema(etree.fromstring(envoltorio(esquemas), parser, base_url='urn:envoltorio'))
            break
        except etree.XMLSchemaParseError as e:
            if faltan:
                return [_sin_comprobar(faltan)]
            if intento == 1:  #Algún esquema guardado no sirve: se vacía la caché y se prueba otra vez (AU-39)
                vaciar_cache()
                continue
            return [Incidencia(AVISO, 'XSD-ESQUEMA', f"No se han podido cargar los esquemas oficiales: {str(e)[:200]}")]
    if faltan:
        return [_sin_comprobar(faltan)]
    try:
        documento = etree.fromstring(datos, etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError as e:
        return [Incidencia(ERROR, 'XML-MAL-FORMADO', f"El fichero no es un XML bien formado: {e}")]
    if esquema.validate(documento):
        return [Incidencia(INFO, 'XSD-VALIDO', "Cumple el esquema XSD público de INSPIRE (la Sede comprueba además otras reglas: vea los errores de arriba, si los hay)")]
    errores = list(esquema.error_log)
    resultado = [Incidencia(ERROR, 'XSD', f"Línea {e.line}: {e.message}") for e in errores[:MAX_ERRORES]]
    if len(errores) > MAX_ERRORES:
        resultado.append(Incidencia(ERROR, 'XSD', f"… y {len(errores) - MAX_ERRORES} errores de esquema más"))
    return resultado


def _sin_comprobar(faltan):
    return Incidencia(AVISO, 'XSD-SIN-COMPROBAR',
                      f"No se ha podido comprobar el esquema XSD: no se han podido descargar {len(faltan)} esquemas oficiales "
                      f"(¿sin conexión?). Primero: {faltan[0]}")
