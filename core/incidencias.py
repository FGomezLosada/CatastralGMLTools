"""
Incidencias: avisos y errores que devuelven las funciones de core/ (geometría, GML, validación).
Las funciones no muestran nada: devuelven la lista y el panel decide cómo enseñarla.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
from dataclasses import dataclass

INFO = 'info'
AVISO = 'aviso'
ERROR = 'error'


@dataclass
class Incidencia:
    nivel: str          #INFO, AVISO o ERROR
    codigo: str         #Identificador estable (para pruebas y para la ayuda), p. ej. 'GEO-ORIENTACION'
    mensaje: str        #Texto para el usuario
    elemento: str = ''  #A qué parcela o construcción se refiere (localId, nº de fila...)

    def __str__(self):
        prefijo = f"[{self.elemento}] " if self.elemento else ''
        return f"{prefijo}{self.mensaje}"


def hay_errores(incidencias):
    return any(i.nivel == ERROR for i in incidencias)


def codigos(incidencias):
    """Códigos de las incidencias (útil en las pruebas)."""
    return [i.codigo for i in incidencias]
