"""
Puntos de apoyo para el editor parcelario de la Sede Electrónica del Catastro (mejora 33): los vértices de una capa (de
puntos, líneas o polígonos) en un TXT con «x y» por línea, como los carga el editor (punto decimal, solo cifras, sin
cabecera), en el huso UTM que admite la Sede y con 2 decimales, sin repetir puntos.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os

from . import geometria as geo
from .ficheros import escribir_texto

MAX_PUNTOS = 10000  #Más no tiene sentido como apoyo para dibujar a mano (y el fichero lo cargaría con dificultad)


def puntos(geometrias):
    """Vértices de las geometrías (ya en el SRC de destino), redondeados al cm y sin repetir, en su orden."""
    vistos, salida = set(), []
    for g in geometrias:
        if g is None or g.isNull() or g.isEmpty():
            continue
        for v in g.vertices():
            p = (geo.redondear(v.x()), geo.redondear(v.y()))
            if p not in vistos:
                vistos.add(p)
                salida.append(p)
    return salida


def texto(lista):
    """Una línea «x y» por punto, con 2 decimales y punto decimal."""
    return ''.join(f"{geo.formatear(x)} {geo.formatear(y)}\n" for x, y in lista)


def ruta_por_defecto(carpeta, nombre_capa):
    limpio = ''.join(c if c.isalnum() or c in '-_' else '_' for c in nombre_capa).strip('_') or 'puntos'
    return os.path.join(carpeta, f"{limpio}_puntos_apoyo.txt")


def escribir(ruta, lista):
    """Escribe el TXT; lanza OSError si no se puede."""
    problema = escribir_texto(ruta, texto(lista), 'ascii')
    if problema is not None:
        raise OSError(problema.mensaje)
    return ruta
