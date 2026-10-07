"""
Referencias catastrales: limpieza, formato y caracteres de control.

Estructura de la referencia catastral (RC) de la Dirección General del Catastro:
  - Parcela (14 caracteres)
      urbana:  7 dígitos de finca + 7 de hoja del plano (2 letras, 4 dígitos, 1 letra)   p. ej. 9872023VH5797S
      rústica: 2 de provincia + 3 de municipio + 1 letra de sector + 3 de polígono + 5 de parcela   p. ej. 29071A00700123
  - Inmueble (20 caracteres) = parcela (14) + 4 de cargo + 2 caracteres de control.
Los caracteres de control solo existen en la RC de 20 caracteres: una RC de 14 solo puede comprobarse por su formato.

Cálculo de los caracteres de control (método público de la DGC): para cada uno de los dos bloques
(caracteres 1-7 + cargo, y caracteres 8-14 + cargo) se suma cada carácter por su peso (13, 15, 12, 5, 4, 17, 9, 21, 3, 7, 1);
los dígitos valen su número y las letras su posición en el alfabeto español (A=1 … N=14, Ñ=15, O=16 … Z=27).
El resto de dividir la suma entre 23 indica la letra en la serie MQWERTYUIOPASDFGHJKLBZX.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import re
from dataclasses import dataclass

from .info import territorio_foral

PESOS = (13, 15, 12, 5, 4, 17, 9, 21, 3, 7, 1)
LETRAS_CONTROL = 'MQWERTYUIOPASDFGHJKLBZX'

URBANA = re.compile(r'^\d{7}[A-ZÑ]{2}\d{4}[A-ZÑ]$')
RUSTICA = re.compile(r'^\d{5}[A-ZÑ]\d{8}$')
ALFANUMERICO = re.compile(r'^[0-9A-ZÑ]+$')

#Niveles del resultado
CORRECTA = 'correcta'
AVISO = 'aviso'
ERROR = 'error'


@dataclass
class ResultadoRC:
    """Resultado de comprobar una referencia catastral."""
    rc: str                 #RC limpia (mayúsculas, sin espacios ni guiones)
    nivel: str              #CORRECTA, AVISO o ERROR
    mensaje: str            #Explicación para el usuario
    tipo: str = ''          #'urbana', 'rústica' o '' si no se reconoce
    parcela: str = ''       #Los 14 primeros caracteres (identifican la parcela)
    provincia: str = ''     #Código de provincia (solo en rústica)
    municipio: str = ''     #Código de municipio del Catastro (solo en rústica)
    foral: str = ''         #Territorio con catastro propio, si se deduce de la RC

    @property
    def valida(self):
        return self.nivel != ERROR


def limpiar(rc):
    """Mayúsculas y sin espacios, guiones ni puntos (como suele copiarse de un certificado)."""
    return re.sub(r'[\s\-.]', '', str(rc or '')).upper()


def _valor(caracter):
    if caracter.isdigit():
        return int(caracter)
    if caracter == 'Ñ':
        return 15
    posicion = ord(caracter) - ord('A') + 1  #A=1 … Z=26
    return posicion if caracter <= 'N' else posicion + 1  #Desde la O, uno más por la Ñ


def caracteres_control(rc18):
    """Los 2 caracteres de control de una RC a partir de sus 18 primeros caracteres."""
    rc18 = limpiar(rc18)[:18]
    if len(rc18) != 18 or not ALFANUMERICO.match(rc18):
        raise ValueError("Se necesitan los 18 primeros caracteres alfanuméricos de la referencia catastral")
    cargo = rc18[14:18]
    resultado = ''
    for bloque in (rc18[0:7] + cargo, rc18[7:14] + cargo):
        suma = sum(peso * _valor(c) for peso, c in zip(PESOS, bloque))
        resultado += LETRAS_CONTROL[suma % 23]
    return resultado


def tipo_parcela(rc14):
    """'urbana', 'rústica' o '' según el formato de los 14 caracteres de la parcela."""
    if URBANA.match(rc14):
        return 'urbana'
    if RUSTICA.match(rc14):
        return 'rústica'
    return ''


def comprobar(rc):
    """Comprueba una referencia catastral de 14, 18 o 20 caracteres y devuelve un ResultadoRC."""
    limpia = limpiar(rc)
    if not limpia:
        return ResultadoRC(limpia, ERROR, "La referencia catastral está vacía")
    if not ALFANUMERICO.match(limpia):
        return ResultadoRC(limpia, ERROR, "La referencia catastral solo puede tener letras y números")
    if len(limpia) not in (14, 18, 20):
        return ResultadoRC(limpia, ERROR, f"La referencia catastral debe tener 14, 18 o 20 caracteres (tiene {len(limpia)})")

    parcela = limpia[:14]
    tipo = tipo_parcela(parcela)
    datos = {'tipo': tipo, 'parcela': parcela}
    if tipo == 'rústica':
        datos.update(provincia=parcela[:2], municipio=parcela[2:5], foral=territorio_foral(parcela[:2]) or '')

    if len(limpia) == 20:
        esperado = caracteres_control(limpia)
        if limpia[18:] != esperado:
            return ResultadoRC(limpia, ERROR, f"Los caracteres de control no coinciden: deberían ser {esperado}", **datos)

    if not tipo:
        return ResultadoRC(limpia, AVISO, "El formato no corresponde a una parcela urbana ni rústica habitual: compruébela", **datos)
    if datos.get('foral'):
        return ResultadoRC(limpia, AVISO, f"Parcela de {datos['foral']}: tiene catastro propio, no el de la Dirección General del Catastro",
                           **datos)
    if len(limpia) == 14:
        return ResultadoRC(limpia, CORRECTA, f"Parcela {tipo} (14 caracteres: sin caracteres de control que comprobar)", **datos)
    if len(limpia) == 18:
        return ResultadoRC(limpia, CORRECTA, f"Inmueble de parcela {tipo}; faltan los 2 caracteres de control: "
                                             f"{caracteres_control(limpia)}", **datos)
    return ResultadoRC(limpia, CORRECTA, f"Inmueble de parcela {tipo} con caracteres de control correctos", **datos)


def es_rc_parcela(texto):
    """True si el texto es una RC de parcela de 14 caracteres con formato urbano o rústico (útil para localId SDGC)."""
    limpia = limpiar(texto)
    return len(limpia) == 14 and bool(tipo_parcela(limpia))


def es_dominio_publico(rc):
    """
    True si la RC es de un recinto de dominio público de rústica (caminos, carreteras, cauces, acequias…): en el
    Catastro de rústica llevan un número de parcela entre 9000 y 9999 dentro de su polígono. En urbana las calles no
    son parcelas (no tienen RC), así que no hay nada que detectar.
    """
    parcela = limpiar(rc)[:14]
    return tipo_parcela(parcela) == 'rústica' and 9000 <= int(parcela[9:14]) <= 9999
