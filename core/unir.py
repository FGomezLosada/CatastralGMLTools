"""
Multiparcela (mejora 16): une varios GML de parcela en uno solo, para presentar en la Sede varias parcelas a la vez
(p. ej. las resultantes de varias operaciones sobre parcelas colindantes, o ficheros hechos por separado).

Reglas:
  - solo GML de parcela catastral (CP 4.0 o el antiguo 3.0, que se reescribe en 4.0); los de edificio no se mezclan;
  - un único SRC: si los ficheros vienen en husos distintos, se transforman al del primero que admita la Sede (y se
    avisa); si ninguno lo admite (p. ej. EPSG:4326), al huso que les corresponde;
  - si las parcelas forman zonas separadas se avisa: la Sede trata el GML como una sola operación (no automática);
  - una parcela repetida en dos ficheros (mismo identificador y misma geometría, ±1 cm) se incluye una sola vez;
    dos parcelas nuevas (LOCAL) con el mismo nombre y distinta geometría: la segunda se renombra (Seg_1 → Seg_2);
    una referencia catastral (SDGC) con geometrías distintas es un error;
  - el fichero resultante se escribe con el escritor del plugin (xmlns:xlink, 2 decimales, superficie…) y se puede
    revisar después en la pestaña Validar (solapes y huecos entre parcelas, comparación con el Catastro).

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os

from qgis.core import QgsCoordinateReferenceSystem

from . import geometria as geo
from . import gml_lector as gl
from . import gml_parcela as gp
from .ficheros import comprobar_destino, misma_ruta
from .incidencias import AVISO, ERROR, INFO, Incidencia, hay_errores

NAMESPACES = {'ES.SDGC.CP': gp.SDGC, 'ES.LOCAL.CP': gp.LOCAL}
TOLERANCIA = 0.01  #m: dos geometrías a menos de 1 cm se consideran la misma parcela


def reunir(rutas):
    """
    Lee los GML y devuelve (parcelas ParcelaGML en el SRC común, epsg, incidencias). No escribe nada.
    """
    incidencias, parcelas, vistas = [], [], {}
    epsg = None
    lecturas = [(ruta, gl.leer(ruta)) for ruta in rutas]
    epsg = src_comun(lecturas)
    usados = {e.local_id for _, lectura in lecturas for e in lectura.elementos}  #Para no renombrar a uno que ya existe
    for ruta, lectura in lecturas:
        nombre = os.path.basename(ruta)
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
        transformar = lectura.epsg != epsg
        if transformar:
            incidencias.append(Incidencia(AVISO, 'UNIR-SRC', f"{nombre}: EPSG:{lectura.epsg} pasado a EPSG:{epsg} "
                                                             "(el GML solo puede tener un SRC)"))
        origen = QgsCoordinateReferenceSystem(f'EPSG:{lectura.epsg}')
        girar = latitud_primero(lectura)
        if girar:
            incidencias.append(Incidencia(INFO, 'UNIR-LAT-LON', f"{nombre}: coordenadas geográficas en el orden latitud, "
                                                                "longitud; se han leído así"))
        for e in lectura.elementos:
            geometria = geo.girar_ejes(e.geometria) if girar else e.geometria
            geometria = geo.transformar(geometria, origen, epsg) if transformar else geometria
            if geometria is None:
                incidencias.append(Incidencia(ERROR, 'UNIR-SRC-FALLO', f"{nombre}: {e.local_id} no se puede pasar a "
                                                                       f"EPSG:{epsg}", e.local_id))
                continue
            namespace = NAMESPACES.get(e.namespace)
            if namespace is None:
                namespace = gp.LOCAL
                incidencias.append(Incidencia(AVISO, 'UNIR-NAMESPACE', f"{nombre}: {e.local_id} tiene el namespace "
                                                                       f"«{e.namespace or 'vacío'}»: se escribe como "
                                                                       "parcela nueva (LOCAL)", e.local_id))
            local_id = e.local_id
            previa = vistas.get(local_id)
            if previa is not None:
                if previa.geometria.hausdorffDistance(geometria) <= TOLERANCIA:
                    incidencias.append(Incidencia(INFO, 'UNIR-REPETIDA', f"{local_id} está en varios ficheros: se "
                                                                         "incluye una vez", local_id))
                    continue
                if namespace == gp.SDGC or previa.namespace == gp.SDGC:
                    incidencias.append(Incidencia(ERROR, 'UNIR-ID-DISTINTO', f"{local_id} aparece en varios ficheros con "
                                                                             "geometrías distintas", local_id))
                    continue
                #Dos parcelas nuevas con el mismo nombre (p. ej. Seg_1 de dos segregaciones): se renombra la segunda (AU-41)
                local_id = nombre_libre(local_id, usados)
                usados.add(local_id)
                incidencias.append(Incidencia(INFO, 'UNIR-RENOMBRADA', f"{nombre}: {e.local_id} ya está en otro fichero con "
                                                                       f"otra geometría: se llama {local_id}", local_id))
            parcela = gp.ParcelaGML(local_id, namespace, geometria, e.label, e.referencia)
            vistas[local_id] = parcela
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


def latitud_primero(lectura):
    """¿Fichero en geográficas escrito en el orden latitud, longitud (EPSG:4326 en GML 3.2)?"""
    crs = QgsCoordinateReferenceSystem(f'EPSG:{lectura.epsg}')
    return crs.isValid() and crs.isGeographic() and geo.orden_lat_lon([e.geometria for e in lectura.elementos])


def src_comun(lecturas):
    """
    SRC del GML unido: el del primer fichero en un SRC que admita la Sede; si ninguno lo está (p. ej. todos en
    EPSG:4326), el huso que corresponde a su posición. Así nunca se pasa todo a grados por venir el primero en 4326.
    """
    validas = [lectura for _, lectura in lecturas if lectura.version.startswith('CP') and lectura.elementos
               and not hay_errores(lectura.incidencias)]
    for lectura in validas:
        if lectura.epsg in geo.SRC_ADMITIDOS:
            return lectura.epsg
    for lectura in validas:
        geometria = lectura.elementos[0].geometria
        recomendado = geo.epsg_recomendado(geo.girar_ejes(geometria) if latitud_primero(lectura) else geometria,
                                           QgsCoordinateReferenceSystem(f'EPSG:{lectura.epsg}'))
        if recomendado is not None:
            return recomendado
    return validas[0].epsg if validas else None


def nombre_libre(local_id, usados):
    """Identificador nuevo que no esté en usados: Seg_1 → Seg_2, Seg_3…; Parcela → Parcela_2…"""
    raiz, _, numero = local_id.rpartition('_')
    if not (raiz and numero.isdigit()):
        raiz, numero = local_id, '1'
    n = int(numero) + 1
    while f"{raiz}_{n}" in usados:
        n += 1
    return f"{raiz}_{n}"


def zonas_separadas(parcelas):
    """Número de grupos de parcelas que no se tocan entre sí (a más de 1 cm)."""
    return len(geo.zonas([p.geometria for p in parcelas], TOLERANCIA))


def unir(rutas, destino, fecha=None):
    """Une los GML en el fichero destino. Devuelve (escrito, número de parcelas, incidencias)."""
    if len(rutas) < 2:
        return False, 0, [Incidencia(ERROR, 'UNIR-POCOS', "Elija al menos dos ficheros GML")]
    if any(misma_ruta(r, destino) for r in rutas):
        return False, 0, [Incidencia(ERROR, 'UNIR-DESTINO', "El fichero de salida no puede ser uno de los que se unen")]
    problema = comprobar_destino(destino)  #Carpeta que no existe, ruta que es una carpeta… (AU-07)
    if problema is not None:
        return False, 0, [problema]
    parcelas, epsg, incidencias = reunir(rutas)
    if hay_errores(incidencias):
        return False, 0, incidencias
    ok, escritura = gp.escribir(destino, parcelas, epsg, fecha)
    return ok, len(parcelas) if ok else 0, incidencias + escritura
