"""
Multiparcela (mejora 16): une varios GML de parcela en uno solo, para presentar en la Sede varias parcelas a la vez
(p. ej. las resultantes de varias operaciones sobre parcelas colindantes, o ficheros hechos por separado).

Reglas:
  - solo GML de parcela catastral (CP 4.0 o el antiguo 3.0, que se reescribe en 4.0); los de edificio no se mezclan;
  - un único SRC: si los ficheros vienen en husos distintos, se transforman al del primero (y se avisa);
  - si las parcelas forman zonas separadas se avisa: la Sede trata el GML como una sola operación (no automática);
  - una parcela repetida en dos ficheros (mismo identificador y misma geometría, ±1 cm) se incluye una sola vez;
    el mismo identificador con geometrías distintas es un error;
  - el fichero resultante se escribe con el escritor del plugin (xmlns:xlink, 2 decimales, superficie…) y se puede
    revisar después en la pestaña Validar (solapes y huecos entre parcelas, comparación con el Catastro).

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os

from qgis.core import QgsCoordinateReferenceSystem, QgsGeometry

from . import geometria as geo
from . import gml_lector as gl
from . import gml_parcela as gp
from .incidencias import AVISO, ERROR, INFO, Incidencia, hay_errores

NAMESPACES = {'ES.SDGC.CP': gp.SDGC, 'ES.LOCAL.CP': gp.LOCAL}
TOLERANCIA = 0.01  #m: dos geometrías a menos de 1 cm se consideran la misma parcela


def reunir(rutas):
    """
    Lee los GML y devuelve (parcelas ParcelaGML en el SRC común, epsg, incidencias). No escribe nada.
    """
    incidencias, parcelas, vistas = [], [], {}
    epsg = None
    for ruta in rutas:
        nombre = os.path.basename(ruta)
        lectura = gl.leer(ruta)
        errores = [i for i in lectura.incidencias if i.nivel == ERROR]
        if errores:
            incidencias += [Incidencia(ERROR, i.codigo, f"{nombre}: {i.mensaje}") for i in errores]
            continue
        if not lectura.version.startswith('CP'):
            incidencias.append(Incidencia(ERROR, 'UNIR-NO-PARCELA', f"{nombre}: no es un GML de parcela catastral "
                                                                    f"({lectura.version or 'formato desconocido'})"))
            continue
        if lectura.version == 'CP 3.0':
            incidencias.append(Incidencia(INFO, 'UNIR-CP30', f"{nombre}: esquema 3.0, se reescribe en 4.0"))
        if epsg is None:
            epsg = lectura.epsg
        transformar = lectura.epsg != epsg
        if transformar:
            incidencias.append(Incidencia(AVISO, 'UNIR-SRC', f"{nombre}: EPSG:{lectura.epsg} pasado a EPSG:{epsg} "
                                                             "(el GML solo puede tener un SRC)"))
        origen = QgsCoordinateReferenceSystem(f'EPSG:{lectura.epsg}')
        for e in lectura.elementos:
            geometria = geo.transformar(e.geometria, origen, epsg) if transformar else e.geometria
            namespace = NAMESPACES.get(e.namespace, gp.LOCAL)
            previa = vistas.get(e.local_id)
            if previa is not None:
                if previa.geometria.hausdorffDistance(geometria) <= TOLERANCIA:
                    incidencias.append(Incidencia(INFO, 'UNIR-REPETIDA', f"{e.local_id} está en varios ficheros: se "
                                                                         "incluye una vez", e.local_id))
                else:
                    incidencias.append(Incidencia(ERROR, 'UNIR-ID-DISTINTO', f"{e.local_id} aparece en varios ficheros con "
                                                                             "geometrías distintas", e.local_id))
                continue
            parcela = gp.ParcelaGML(e.local_id, namespace, geometria, e.label, e.referencia)
            vistas[e.local_id] = parcela
            parcelas.append(parcela)
    if not parcelas and not hay_errores(incidencias):
        incidencias.append(Incidencia(ERROR, 'UNIR-VACIO', "No hay parcelas que unir"))
    zonas = zonas_separadas(parcelas)
    if zonas > 1:
        incidencias.append(Incidencia(AVISO, 'UNIR-SEPARADAS', f"Las parcelas forman {zonas} zonas separadas: la Sede trata "
                                                               "el GML como una sola operación (NPO y NPP del conjunto): puede "
                                                               "dar validación positiva, pero no propone la operación (hay "
                                                               "que elegirla a mano) ni la tramita de forma automática. Para "
                                                               "operaciones independientes, mejor un GML por finca"))
    return parcelas, epsg, incidencias


def zonas_separadas(parcelas):
    """Número de grupos de parcelas que no se tocan entre sí (a más de 1 cm)."""
    geometrias = [p.geometria.buffer(TOLERANCIA / 2, 2) for p in parcelas if not p.geometria.isEmpty()]
    if not geometrias:
        return 0
    union = QgsGeometry.unaryUnion(geometrias)
    return len(union.asGeometryCollection()) if union.isMultipart() else 1


def unir(rutas, destino, fecha=None):
    """Une los GML en el fichero destino. Devuelve (escrito, número de parcelas, incidencias)."""
    if len(rutas) < 2:
        return False, 0, [Incidencia(ERROR, 'UNIR-POCOS', "Elija al menos dos ficheros GML")]
    if any(os.path.abspath(r) == os.path.abspath(destino) for r in rutas):
        return False, 0, [Incidencia(ERROR, 'UNIR-DESTINO', "El fichero de salida no puede ser uno de los que se unen")]
    parcelas, epsg, incidencias = reunir(rutas)
    if hay_errores(incidencias):
        return False, 0, incidencias
    ok, escritura = gp.escribir(destino, parcelas, epsg, fecha)
    return ok, len(parcelas) if ok else 0, incidencias + escritura
