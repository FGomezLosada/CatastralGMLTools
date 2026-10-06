"""
Datos generales del plugin: nombre, versión, textos legales y territorios.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import configparser
import os

NOMBRE = 'Catastral GML Tools'
CARPETA = 'catastral_gml_tools'  #Nombre de la carpeta del plugin dentro de QGIS
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#Aviso que se muestra en el panel, la ayuda y el README
AVISO_LEGAL = ("Herramienta no oficial. Valide siempre el resultado en la Sede Electrónica del Catastro "
               "antes de usarlo en cualquier trámite.")
#Cita de la fuente para todo dato descargado de los servicios de la DGC
FUENTE_DGC = "Dirección General del Catastro"

#Territorios con catastro propio (códigos de provincia del INE). El resto lo gestiona la DGC.
FORALES = {
    '31': 'Navarra',
    '01': 'Álava/Araba',
    '20': 'Gipuzkoa',
    '48': 'Bizkaia',
}


def version():
    """Versión leída de metadata.txt (una sola fuente de verdad)."""
    metadata = configparser.ConfigParser(interpolation=None)
    metadata.read(os.path.join(RAIZ, 'metadata.txt'), encoding='utf-8')
    try:
        return metadata['general']['version'].strip()
    except KeyError:
        return '?'


def ruta(*partes):
    """Ruta absoluta a un fichero del plugin."""
    return os.path.join(RAIZ, *partes)


def territorio_foral(codigo_provincia):
    """Nombre del territorio foral si el código de provincia (2 dígitos) pertenece a uno; si no, None."""
    return FORALES.get(str(codigo_provincia).zfill(2))
