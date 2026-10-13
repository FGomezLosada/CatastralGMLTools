"""
Escritura segura de ficheros (auditoría AU-07 y AU-09): comprobar el destino antes de escribir y convertir los errores
del sistema (carpeta que no existe, sin permiso, fichero abierto en otro programa…) en incidencias para el panel, en vez
de excepciones.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os

from .incidencias import ERROR, Incidencia


def misma_ruta(a, b):
    """True si a y b son el mismo fichero (Windows no distingue mayúsculas; se comparan rutas absolutas normalizadas)."""
    if not a or not b:
        return False
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def comprobar_destino(ruta, origenes=()):
    """Incidencia de error si no se puede escribir en ruta o si es uno de los ficheros de origen; None si vale."""
    if not ruta:
        return Incidencia(ERROR, 'FICHERO', "Indique el fichero de salida")
    if os.path.isdir(ruta):
        return Incidencia(ERROR, 'FICHERO', f"La ruta de salida es una carpeta: {ruta}")
    carpeta = os.path.dirname(os.path.abspath(ruta))
    if not os.path.isdir(carpeta):
        return Incidencia(ERROR, 'FICHERO', f"No existe la carpeta de destino: {carpeta}")
    for origen in origenes:
        if misma_ruta(ruta, origen):
            return Incidencia(ERROR, 'FICHERO-ORIGEN', f"El fichero de salida es el mismo del que salen los datos ({ruta}): "
                                                       "elija otro nombre para no sobrescribirlo")
    return None


def escribir_texto(ruta, texto, encoding='utf-8', errors='strict', origenes=()):
    """Escribe texto en ruta. Devuelve None si ha ido bien o la Incidencia del problema."""
    problema = comprobar_destino(ruta, origenes)
    if problema is not None:
        return problema
    try:
        with open(ruta, 'w', encoding=encoding, errors=errors, newline='\n') as f:
            f.write(texto)
    except OSError as e:
        return Incidencia(ERROR, 'FICHERO', f"No se ha podido escribir {os.path.basename(ruta)}: {e.strerror or e} "
                                            "(¿está abierto en otro programa o la carpeta es de solo lectura?)")
    return None
