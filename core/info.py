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
#Cita de los datos de Navarra (servicios INSPIRE del Gobierno de Navarra, licencia CC BY 4.0)
FUENTE_NAVARRA = "Gobierno de Navarra – Registro de la Riqueza Territorial (CC BY 4.0)"

#Territorios con catastro propio (códigos de provincia del INE). El resto lo gestiona la DGC.
FORALES = {
    '31': 'Navarra',
    '01': 'Álava/Araba',
    '20': 'Gipuzkoa',
    '48': 'Bizkaia',
}


#Nombres de las provincias por su código (INE = código de provincia del Catastro en la RC rústica)
PROVINCIAS = {
    '01': 'Álava/Araba', '02': 'Albacete', '03': 'Alicante/Alacant', '04': 'Almería', '05': 'Ávila', '06': 'Badajoz',
    '07': 'Illes Balears', '08': 'Barcelona', '09': 'Burgos', '10': 'Cáceres', '11': 'Cádiz', '12': 'Castellón/Castelló',
    '13': 'Ciudad Real', '14': 'Córdoba', '15': 'A Coruña', '16': 'Cuenca', '17': 'Girona', '18': 'Granada',
    '19': 'Guadalajara', '20': 'Gipuzkoa', '21': 'Huelva', '22': 'Huesca', '23': 'Jaén', '24': 'León', '25': 'Lleida',
    '26': 'La Rioja', '27': 'Lugo', '28': 'Madrid', '29': 'Málaga', '30': 'Murcia', '31': 'Navarra', '32': 'Ourense',
    '33': 'Asturias', '34': 'Palencia', '35': 'Las Palmas', '36': 'Pontevedra', '37': 'Salamanca',
    '38': 'Santa Cruz de Tenerife', '39': 'Cantabria', '40': 'Segovia', '41': 'Sevilla', '42': 'Soria', '43': 'Tarragona',
    '44': 'Teruel', '45': 'Toledo', '46': 'Valencia/València', '47': 'Valladolid', '48': 'Bizkaia', '49': 'Zamora',
    '50': 'Zaragoza', '51': 'Ceuta', '52': 'Melilla',
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


def provincia(codigo):
    """Nombre de la provincia por su código de 2 dígitos, o '' si no existe."""
    return PROVINCIAS.get(str(codigo).zfill(2), '')
