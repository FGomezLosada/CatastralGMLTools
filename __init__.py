"""
Catastral GML Tools - Plugin de QGIS
Crea, revisa y convierte ficheros GML de parcela y de edificio para la Sede Electrónica del Catastro.
Herramienta no oficial: el resultado debe validarse siempre en la Sede Electrónica del Catastro.

copyright : (C) 2026 by Francisco Gómez Losada
email     : pgomezlosada@gmail.com
license   : GNU GPL v2 or later
"""


def classFactory(iface):  # noqa: N802 (nombre impuesto por QGIS)
    """Punto de entrada que QGIS llama al cargar el plugin."""
    from .catastral_gml_tools import CatastralGMLTools

    return CatastralGMLTools(iface)
