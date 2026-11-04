"""
Lector del informe de la Sede Electrónica del Catastro (AU-56, mejora 32): el informe de validación gráfica (IVG) y el
informe catastral de ubicación de las construcciones (ICUC). El PDF que da la Sede lleva dentro un XML con el resultado
(raíz «informeGrafAlt» en el IVG e «informeICUC» en el ICUC) y, en base64, ZIP con el GML presentado y los GML de las
parcelas catastrales afectadas. Estructura documentada en docs/AUDITORIA.md (AU-56) con informes reales; códigos de la
operación según la ayuda del IVG de la DGC (1 agregación, 2 agrupación, 3 segregación, 4 división, 5 subsanación de
discrepancias, 6 reparcelación).

Datos personales: el XML trae los del técnico y del solicitante (NIF, nombre, contacto) en «datosAutor» y «solicitante».
Este módulo no los lee: solo toma los datos que nombra (resultado, CSV, operación, parcelas, superficies, linderos y
GML) y no guarda el XML. Tampoco se guardan en capas ni en memoria.

Sin dependencias: el XML va en un flujo /EmbeddedFile del PDF (anotación FileAttachment en el IVG, fichero incrustado en
el ICUC), que se busca y se descomprime con zlib.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import base64
import binascii
import io
import os
import re
import zipfile
import zlib
from dataclasses import dataclass, field

from . import gml_lector as gl
from .ficheros import comprobar_destino

IVG, ICUC = 'IVG', 'ICUC'
RAICES = {'informeGrafAlt': IVG, 'informeICUC': ICUC}
NOMBRES = {IVG: "Informe de validación gráfica (IVG)", ICUC: "Informe catastral de ubicación de las construcciones (ICUC)"}
OPERACIONES = {'1': "Agregación", '2': "Agrupación", '3': "Segregación", '4': "División",
               '5': "Subsanación de discrepancias", '6': "Reparcelación"}
PRIVADOS = ('datosAutor', 'solicitante')   #Nunca se leen
MAX_PDF = 100 * 1024 * 1024                #B: un informe de la Sede ocupa unos pocos MB
MAX_DESCOMPRIMIDO = 50 * 1024 * 1024       #B: lo más que se saca de un flujo o un ZIP (evita «bombas» de compresión)
FLUJO = re.compile(rb'(\d+)\s+(\d+)\s+obj\s*<<(.*?)>>\s*stream\r?\n', re.S)
FECHA_PDF = re.compile(rb'/(?:M|CreationDate)\s*\(D:(\d{4})(\d{2})(\d{2})')


@dataclass
class ParcelaInforme:
    identificador: str
    namespace: str = ''
    superficie: str = ''
    linda_gml: list = field(default_factory=list)       #Identificadores de otras parcelas del GML
    linda_catastro: list = field(default_factory=list)  #Referencias catastrales


@dataclass
class InformeSede:
    tipo: str = ''                     #IVG o ICUC
    csv: str = ''
    positivo: bool = False
    operacion: str = ''                #Solo IVG
    fecha: str = ''                    #dd/mm/aaaa (del PDF), si se sabe
    referencias: list = field(default_factory=list)       #Parcelas catastrales de la entrada (lrc)
    parcelas: list = field(default_factory=list)          #ParcelaInforme del resultado (IVG)
    afectadas_total: list = field(default_factory=list)   #RC afectadas en su totalidad
    afectadas_parcial: list = field(default_factory=list)  #RC afectadas solo en parte (informe negativo)
    precision: str = ''                #ICUC: precisión declarada (m)
    gml_presentado: bytes = b''
    nombre_presentado: str = ''
    gml_afectadas: dict = field(default_factory=dict)     #nombre del fichero → contenido (GML CP 4.0 de cada una)
    errores: list = field(default_factory=list)

    def titulo(self):
        estado = "Validación positiva" if self.positivo else "Validación negativa"
        if self.tipo == ICUC:
            estado = "Ubicación correcta" if self.positivo else "Ubicación no correcta"
        return f"{estado} · {self.operacion}" if self.operacion else estado


def _descomprimir(datos, limite=None):
    limite = MAX_DESCOMPRIMIDO if limite is None else limite
    d = zlib.decompressobj()
    salida = d.decompress(datos, limite + 1)
    if len(salida) > limite:
        raise ValueError("el contenido descomprimido es demasiado grande")
    return salida


def xml_del_pdf(datos):
    """El XML del informe que va dentro del PDF (bytes), o b'' si no lo lleva."""
    for m in FLUJO.finditer(datos):
        diccionario = m.group(3)
        if b'EmbeddedFile' not in diccionario:
            continue
        largo = re.search(rb'/Length\s+(\d+)(?!\s+\d+\s+R)', diccionario)
        fin = m.end() + int(largo.group(1)) if largo else datos.find(b'endstream', m.end())
        crudo = datos[m.end():fin]
        try:
            contenido = _descomprimir(crudo) if b'FlateDecode' in diccionario else crudo
        except (zlib.error, ValueError):
            continue
        cabecera = contenido[:400]
        if any(f'<{raiz}'.encode() in cabecera for raiz in RAICES):
            return contenido
    return b''


def fecha_del_pdf(datos):
    """Fecha de la firma (o, si no, de creación) del PDF, «dd/mm/aaaa», o ''."""
    m = FECHA_PDF.search(datos)
    return f"{m.group(3).decode()}/{m.group(2).decode()}/{m.group(1).decode()}" if m else ''


def _zip_base64(texto):
    """{nombre: contenido} de un ZIP en base64 (los GML del informe)."""
    try:
        crudo = base64.b64decode(''.join((texto or '').split()), validate=True)
        with zipfile.ZipFile(io.BytesIO(crudo)) as z:
            ficheros, total = {}, 0
            for info in z.infolist():
                if info.is_dir():
                    continue
                total += info.file_size
                if total > MAX_DESCOMPRIMIDO:
                    raise ValueError("el ZIP del informe es demasiado grande")
                ficheros[os.path.basename(info.filename)] = z.read(info)
            return ficheros
    except (binascii.Error, zipfile.BadZipFile, ValueError, OSError, RuntimeError):
        return {}


def _rc(elemento):
    """Referencia catastral de un elemento <rc> (pc1 + pc2) o de un <lrc> sin <rc> (ICUC)."""
    return (gl.texto_de(elemento, 'pc1') or '') + (gl.texto_de(elemento, 'pc2') or '')


def _hijo(elemento, *ruta):
    for nombre in ruta:
        if elemento is None:
            return None
        elemento = gl.hijo(elemento, nombre)
    return elemento


def _rcs(elemento):
    return [_rc(r) for r in gl.hijos(elemento, 'rc')] if elemento is not None else []


def interpretar(xml):
    """InformeSede a partir del XML del informe. Solo lee los elementos que nombra (nunca datosAutor ni solicitante)."""
    informe = InformeSede()
    try:
        raiz = gl.xml_fromstring(xml)
    except (gl.ET.ParseError, LookupError, ValueError) as e:
        informe.errores.append(f"El XML del informe no se puede leer: {gl.motivo_xml(e, xml)}")
        return informe
    informe.tipo = RAICES.get(gl.nombre_local(raiz.tag), '')
    if not informe.tipo:
        informe.errores.append("No es un informe de la Sede (IVG ni ICUC)")
        return informe
    entrada, resultado = gl.hijo(raiz, 'bentrada'), gl.hijo(raiz, 'bresultado')
    if resultado is None:
        informe.errores.append("El informe no trae el resultado")
        return informe
    informe.positivo = (gl.texto_de(resultado, 'resultado') or '').strip() == '1'
    informe.csv = (gl.texto_de(resultado, 'csv') or '').strip()
    lrc = _hijo(entrada, 'datosGeo', 'lrc')
    if informe.tipo == IVG:
        informe.referencias = _rcs(lrc)
        informe.operacion = OPERACIONES.get((gl.texto_de(entrada, 'tipoOperacion') or '').strip(), '')
        presentado = _zip_base64(gl.texto_de(_hijo(entrada, 'datosGeo'), 'parcelasGml'))
        for elemento in gl.hijos(gl.hijo(resultado, 'parcelasResult'), 'parcelaResult') \
                if gl.hijo(resultado, 'parcelasResult') is not None else []:
            ident = gl.hijo(elemento, 'identificador')
            informe.parcelas.append(ParcelaInforme(
                identificador=(gl.texto_de(ident, 'idLocal') or '').strip() if ident is not None else '',
                namespace=(gl.texto_de(ident, 'namespace') or '').strip() if ident is not None else '',
                superficie=(gl.texto_de(elemento, 'superficie') or '').strip(),
                linda_gml=[(e.text or '').strip() for e in gl.hijos(gl.hijo(elemento, 'linderosLocales'), 'IdLocal')]
                if gl.hijo(elemento, 'linderosLocales') is not None else [],
                linda_catastro=_rcs(gl.hijo(elemento, 'linderosCatastro'))))
        afect = gl.hijo(resultado, 'parcelasAfect')
        if afect is not None:
            informe.afectadas_total = _rcs(gl.hijo(afect, 'parcelasAfectT'))
            informe.afectadas_parcial = _rcs(gl.hijo(afect, 'parcelasAfectP'))
            informe.gml_afectadas = _zip_base64(gl.texto_de(afect, 'geometria'))
    else:
        informe.referencias = [_rc(lrc)] if lrc is not None and _rc(lrc) else []
        informe.precision = (gl.texto_de(_hijo(entrada, 'espTrabajo'), 'precision') or '').strip() \
            if _hijo(entrada, 'espTrabajo') is not None else ''
        presentado = _zip_base64(gl.texto_de(_hijo(entrada, 'datosGeo'), 'construcGml'))
        informe.gml_afectadas = _zip_base64(gl.texto_de(resultado, 'parcelaCatGml'))
        informe.afectadas_total = list(informe.referencias)
    if presentado:
        informe.nombre_presentado, informe.gml_presentado = next(iter(presentado.items()))
    return informe


def leer(ruta):
    """InformeSede de un PDF de la Sede (o de su XML suelto). Los problemas van en .errores; nunca lanza."""
    try:
        if os.path.getsize(ruta) > MAX_PDF:
            return InformeSede(errores=["El fichero es demasiado grande para ser un informe de la Sede"])
        with open(ruta, 'rb') as f:
            datos = f.read()
    except OSError as e:
        return InformeSede(errores=[f"No se puede leer el fichero: {e}"])
    if datos[:5] == b'%PDF-':
        xml = xml_del_pdf(datos)
        if not xml:
            return InformeSede(errores=["El PDF no lleva el XML del informe: ¿es el informe descargado de la Sede (IVG o "
                                        "ICUC)? Una copia impresa o escaneada no lo lleva"])
        informe = interpretar(xml)
        informe.fecha = fecha_del_pdf(datos)
        return informe
    return interpretar(datos)


def ruta_presentado(ruta_informe, informe):
    """Dónde guardar el GML presentado: junto al informe, con el CSV en el nombre (no pisa el GML original)."""
    base = os.path.splitext(informe.nombre_presentado or 'GML_presentado.gml')[0]
    limpio = ''.join(c if c.isalnum() or c in '-_' else '_' for c in base) or 'GML_presentado'
    return os.path.join(os.path.dirname(os.path.abspath(ruta_informe)), f"{limpio}_{informe.csv or 'informe'}.gml")


def guardar_presentado(informe, ruta):
    """Escribe el GML presentado tal cual venía en el informe. Devuelve None o la Incidencia del problema."""
    problema = comprobar_destino(ruta)
    if problema is not None:
        return problema
    try:
        with open(ruta, 'wb') as f:
            f.write(informe.gml_presentado)
    except OSError as e:
        from .incidencias import ERROR, Incidencia
        return Incidencia(ERROR, 'FICHERO', f"No se ha podido escribir {ruta}: {e}")
    return None


def lecturas(informe):
    """(presentado, afectadas): ResultadoLectura del GML presentado y de las parcelas catastrales afectadas juntas."""
    presentado = gl.leer_datos(informe.gml_presentado) if informe.gml_presentado else None
    afectadas = None
    for contenido in informe.gml_afectadas.values():
        r = gl.leer_datos(contenido)
        if afectadas is None:
            afectadas = r
        else:
            afectadas.elementos += r.elementos
    return presentado, afectadas
