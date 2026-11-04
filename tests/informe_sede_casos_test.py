"""
Batería de «Leer informe de la Sede (IVG o ICUC)» (Utilidades «8.», AU-56). Informes SINTÉTICOS con la estructura de los
reales (documentada en docs/AUDITORIA.md, AU-56): XML con datos personales inventados en «datosAutor» y «solicitante»
(que no deben salir nunca: ni en el panel, ni en el mapa, ni en el objeto leído) y GML de parcelas inventadas en ZIP y
base64, dentro de un PDF mínimo como el de la Sede (flujo /EmbeddedFile comprimido). Sin internet.

Casos: IVG positivo de segregación; IVG negativo con una afectada solo en parte; ICUC; XML suelto; PDF sin XML; XML
con DOCTYPE; base64 roto; ZIP demasiado grande; GML presentado guardado sin pisar el original y abierto en Validar;
mapa; y en el panel.

Uso: tools\\probar.bat (o tools\\run_tests.py informe_sede_casos_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import base64
import io
import os
import tempfile
import traceback
import zipfile
import zlib

import qgis.utils
from qgis.core import Qgis, QgsGeometry, QgsPointXY, QgsProject
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

qgis.utils.reloadPlugin('catastral_gml_tools')
import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import gml_edificio as ge  # noqa: E402
from catastral_gml_tools.core import gml_parcela as gp  # noqa: E402
from catastral_gml_tools.core import informe_sede as isd  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))
dock_module.CatastralGMLToolsDockWidget.open_path = lambda self, ruta: None

X0, Y0 = 421500.0, 4070500.0
RC, VECINA, OTRA = '1907401VK4810H', '1907402VK4810H', '1907403VK4810H'
#Datos personales INVENTADOS: si alguno aparece en lo que muestra o guarda el plugin, es un fallo
PERSONALES = ('00000000T', 'Persona Ficticia', 'ficticia@example.invalid', '600000000', 'Solicitante Inventado',
              '11111111H')
carpeta = tempfile.mkdtemp(prefix='cgt informe sede ñ_')
resultados, detalles = {}, {}


def caso(nombre, funcion):
    try:
        ok, detalle = funcion()
        resultados[nombre] = bool(ok)
        if not ok:
            detalles[nombre] = detalle
    except Exception:  # noqa: BLE001
        resultados[nombre] = False
        detalles[nombre] = traceback.format_exc()[-900:]


def rect(x, y, a, b):
    return QgsGeometry.fromPolygonXY([[QgsPointXY(x, y), QgsPointXY(x, y + b), QgsPointXY(x + a, y + b),
                                       QgsPointXY(x + a, y), QgsPointXY(x, y)]])


def zip64(ficheros):
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, 'w', zipfile.ZIP_DEFLATED) as z:
        for nombre, contenido in ficheros.items():
            z.writestr(nombre, contenido)
    return base64.b64encode(memoria.getvalue()).decode('ascii')


def gml_parcelas(parcelas):
    texto, _ = gp.construir(parcelas, 25830)
    return texto.encode('utf-8')  #Como lo escribe el plugin (cabecera utf-8)


PRESENTADO = gml_parcelas([gp.ParcelaGML('Seg_1', gp.LOCAL, rect(X0, Y0, 12, 30)),
                           gp.ParcelaGML(RC, gp.SDGC, rect(X0 + 12, Y0, 18, 30))])
AFECTADA = gml_parcelas([gp.ParcelaGML(RC, gp.SDGC, rect(X0, Y0, 30, 30))])
AFECTADA_PARCIAL = gml_parcelas([gp.ParcelaGML(VECINA, gp.SDGC, rect(X0 + 30, Y0, 20, 30))])


def rc_xml(rc):
    return f"<rc><pc1>{rc[:7]}</pc1><pc2>{rc[7:]}</pc2></rc>"


AUTOR = ("<datosAutor><nif>00000000T</nif><nombre>Persona Ficticia</nombre><correo>ficticia@example.invalid</correo>"
         "<telefono>600000000</telefono></datosAutor>")


def ivg(positivo=True, operacion='3', parcial=False, base64_roto=False):
    afect_t = rc_xml(RC)
    afect_p = f"<parcelasAfectP>{rc_xml(VECINA)}</parcelasAfectP>" if parcial else ''
    geometria = zip64({f'{RC}.gml': AFECTADA, **({f'{VECINA}.gml': AFECTADA_PARCIAL} if parcial else {})})
    presentado = 'esto no es base64 %%%' if base64_roto else zip64({f'Parcela_{RC}.gml': PRESENTADO})
    return (f'<?xml version="1.0" encoding="iso-8859-1"?><informeGrafAlt xmlns="http://www.catastro.meh.es/">'
            f'<bentrada>{AUTOR}<datosGeo><lrc>{rc_xml(RC)}</lrc><parcelasGml>{presentado}</parcelasGml></datosGeo>'
            f'<tipoOperacion>{operacion}</tipoOperacion></bentrada>'
            f'<bresultado><resultado>{1 if positivo else 0}</resultado><csv>SINTETICO0000001</csv><parcelasResult>'
            f'<parcelaResult><identificador><idLocal>Seg_1</idLocal><namespace>ES.LOCAL.CP</namespace></identificador>'
            f'<superficie>360</superficie><linderosLocales><IdLocal>{RC}</IdLocal></linderosLocales>'
            f'<linderosCatastro>{rc_xml(OTRA)}</linderosCatastro></parcelaResult>'
            f'<parcelaResult><identificador><idLocal>{RC}</idLocal><namespace>ES.SDGC.CP</namespace></identificador>'
            f'<superficie>540</superficie><linderosLocales><IdLocal>Seg_1</IdLocal></linderosLocales>'
            f'<linderosCatastro>{rc_xml(VECINA)}</linderosCatastro></parcelaResult></parcelasResult>'
            f'<parcelasAfect><geometria>{geometria}</geometria><parcelasAfectT>{afect_t}</parcelasAfectT>{afect_p}'
            f'</parcelasAfect></bresultado></informeGrafAlt>').encode('iso-8859-1')


def icuc():
    edificio, _ = ge.construir([ge.Construccion('1', rect(X0 + 5, Y0 + 5, 10, 10), plantas=2)], 25830)
    return (f'<?xml version="1.0" encoding="iso-8859-1"?><informeICUC xmlns="http://www.catastro.meh.es/"><bentrada>'
            f'{AUTOR}<solicitante><nif>11111111H</nif><nombre>Solicitante Inventado</nombre></solicitante>'
            f'<espTrabajo><precision>0.800</precision><tipo>Otros</tipo></espTrabajo><despCarto/>'
            f'<datosGeo><lrc><pc1>{RC[:7]}</pc1><pc2>{RC[7:]}</pc2></lrc>'
            f'<construcGml>{zip64({"edificio.gml": edificio.encode("iso-8859-1")})}</construcGml></datosGeo></bentrada>'
            f'<bresultado><resultado>1</resultado><csv>SINTETICO0000002</csv>'
            f'<parcelaCatGml>{zip64({f"{RC}.gml": AFECTADA})}</parcelaCatGml></bresultado></informeICUC>'
            ).encode('iso-8859-1')


def pdf(xml, nombre):
    """PDF mínimo con el XML como fichero incrustado comprimido, como el de la Sede."""
    flujo = zlib.compress(xml)
    datos = (b'%PDF-1.7\n1 0 obj\n<</Type/Catalog>>\nendobj\n'
             b'2 0 obj\n<</Params<</Size ' + str(len(xml)).encode() + b'>>/Subtype/text#2fxml/Filter/FlateDecode/Length '
             + str(len(flujo)).encode() + b'/Type/EmbeddedFile>>stream\n' + flujo + b'\nendstream\nendobj\n'
             b'3 0 obj\n<</CreationDate(D:20261030101500+01\'00\')>>\nendobj\ntrailer\n<</Root 1 0 R>>\n%%EOF\n')
    ruta = os.path.join(carpeta, nombre)
    with open(ruta, 'wb') as f:
        f.write(datos)
    return ruta


def sin_personales(*textos):
    juntos = ' '.join(str(t) for t in textos)
    return [p for p in PERSONALES if p in juntos]


def ivg_positivo():
    i = isd.leer(pdf(ivg(), 'Informe_positivo.pdf'))
    ok = (i.tipo == isd.IVG and i.positivo and i.operacion == 'Segregación' and i.csv == 'SINTETICO0000001'
          and i.fecha == '30/10/2026' and i.referencias == [RC] and i.afectadas_total == [RC] and not i.afectadas_parcial
          and [p.identificador for p in i.parcelas] == ['Seg_1', RC] and i.parcelas[0].superficie == '360'
          and i.parcelas[0].linda_gml == [RC] and i.parcelas[1].linda_catastro == [VECINA]
          and i.gml_presentado == PRESENTADO and i.nombre_presentado == f'Parcela_{RC}.gml'
          and list(i.gml_afectadas) == [f'{RC}.gml'] and i.titulo() == 'Validación positiva · Segregación')
    fugas = sin_personales(repr(i))
    presentado, afectadas = isd.lecturas(i)
    lecturas = len(presentado.elementos) == 2 and len(afectadas.elementos) == 1
    return ok and lecturas and not fugas, (ok, lecturas, repr(i)[:300], fugas)


caso("IVG positivo (segregación): resultado, CSV, fecha, parcelas, linderos, afectadas y GML; sin datos personales",
     ivg_positivo)


def ivg_negativo():
    i = isd.leer(pdf(ivg(positivo=False, operacion='5', parcial=True), 'Informe_negativo.pdf'))
    ok = (not i.positivo and i.operacion == 'Subsanación de discrepancias' and i.afectadas_parcial == [VECINA]
          and i.titulo().startswith('Validación negativa') and len(i.gml_afectadas) == 2)
    return ok and not sin_personales(repr(i)), repr(i)[:300]


caso("IVG negativo: afectada solo en parte y operación «subsanación»", ivg_negativo)


def icuc_y_xml_suelto():
    i = isd.leer(pdf(icuc(), 'Informe_icuc.pdf'))
    ok = (i.tipo == isd.ICUC and i.positivo and i.precision == '0.800' and i.referencias == [RC]
          and i.titulo() == 'Ubicación correcta' and i.nombre_presentado == 'edificio.gml'
          and len(isd.lecturas(i)[0].elementos) == 1)
    ruta = os.path.join(carpeta, 'IVG_SINTETICO.xml')
    with open(ruta, 'wb') as f:
        f.write(ivg())
    suelto = isd.leer(ruta)
    return ok and suelto.csv == 'SINTETICO0000001' and not sin_personales(repr(i), repr(suelto)), repr(i)[:300]


caso("ICUC (sin los datos del técnico ni del solicitante) y XML suelto", icuc_y_xml_suelto)


def errores_claros():
    sin_xml = isd.leer(pdf(b'<?xml version="1.0"?><otra/>', 'otro.pdf'))
    ruta_dtd = os.path.join(carpeta, 'dtd.xml')
    with open(ruta_dtd, 'wb') as f:
        f.write(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><informeGrafAlt/>')
    dtd = isd.leer(ruta_dtd)
    roto = isd.leer(pdf(ivg(base64_roto=True), 'roto.pdf'))
    no_existe = isd.leer(os.path.join(carpeta, 'no_existe.pdf'))
    original = isd.MAX_DESCOMPRIMIDO
    isd.MAX_DESCOMPRIMIDO = 100  #Un ZIP o un flujo que crecería más: no se descomprime
    try:
        grande = isd.leer(pdf(ivg(), 'grande.pdf'))
    finally:
        isd.MAX_DESCOMPRIMIDO = original
    ok = (sin_xml.errores and 'no lleva el XML' in sin_xml.errores[0] and dtd.errores and no_existe.errores
          and not roto.errores and roto.gml_presentado == b'' and roto.csv == 'SINTETICO0000001'
          and grande.errores)
    return ok, (sin_xml.errores, dtd.errores, roto.errores, no_existe.errores, grande.errores)


caso("PDF sin el XML, XML con DOCTYPE, base64 roto, fichero que no existe y contenido demasiado grande: sin fallar",
     errores_claros)

dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
pu = dw.pestanaUtilidades
bloque = pu.informe_sede
pu.utilidades.setCurrentWidget(bloque)


def textos_panel():
    etiquetas = [e.text() for e in bloque.findChildren(QLabel)]
    celdas = [bloque.tabla.item(r, c).text() for r in range(bloque.tabla.rowCount()) for c in range(4)
              if bloque.tabla.item(r, c)]
    barra = [e.text() for item in dw.messageBar.items() for e in item.findChildren(QLabel)]
    return ' | '.join(etiquetas + celdas + barra)


def en_el_panel():
    ruta = pdf(ivg(), 'Informe_panel.pdf')
    pu.soltar([ruta])  #Arrastrado a la utilidad abierta
    texto = textos_panel()
    ok = ('Validación positiva · Segregación' in texto and 'CSV SINTETICO0000001' in texto and bloque.tabla.rowCount() == 2
          and f'{RC} (del GML)' in texto and 'en su totalidad' in texto and 'datos personales' in texto
          and bloque.mapaBoton.isEnabled() and bloque.validarBoton.isEnabled())
    #Cargar en el mapa: lo presentado y las afectadas, sin datos personales en las capas
    capas = bloque.cargar_en_mapa()
    atributos = ' '.join(str(a) for c in capas for f in c.getFeatures() for a in f.attributes())
    mapa = [c.name() for c in capas] == [f'Presentado: Parcela_{RC}', 'Parcelas catastrales afectadas (las del informe)']
    #Guardar el GML presentado: junto al informe, con el CSV, sin pisar el original, y abrirlo en Validar
    original = os.path.join(carpeta, f'Parcela_{RC}.gml')
    with open(original, 'wb') as f:
        f.write(b'original')
    guardado = bloque.abrir_en_validar()
    with open(original, 'rb') as f:
        intacto = f.read() == b'original'
    with open(guardado, 'rb') as f:
        igual = f.read() == PRESENTADO
    validar = (os.path.basename(guardado) == f'Parcela_{RC}_SINTETICO0000001.gml'
               and os.path.normpath(dw.pestanaValidar.fichero.filePath()) == os.path.normpath(guardado))
    fugas = sin_personales(texto, atributos, textos_panel())
    QgsProject.instance().removeAllMapLayers()
    return ok and mapa and intacto and igual and validar and not fugas, (ok, mapa, intacto, igual, validar, fugas,
                                                                         texto[:400])


caso("en el panel: resultado, tabla, cargar en el mapa, guardar el GML presentado (sin pisar el original) y abrirlo en "
     "Validar; ningún dato personal", en_el_panel)


def negativo_en_mapa():
    dw.tabWidget.setCurrentWidget(dw.tabUtilidades)
    bloque.fichero.setFilePath(pdf(ivg(positivo=False, parcial=True), 'Informe_negativo_panel.pdf'))
    texto = textos_panel()
    capas = bloque.cargar_en_mapa()
    nombres = [c.name() for c in capas]
    QgsProject.instance().removeAllMapLayers()
    ok = ('Validación negativa' in texto and 'solo en parte' in texto and VECINA in texto
          and 'Afectadas solo en parte (a corregir)' in nombres)
    return ok, (texto[:300], nombres)


caso("negativo en el panel y en el mapa: la afectada solo en parte, en rojo y aparte", negativo_en_mapa)


def error_en_el_panel():
    dw.messageBar.clearWidgets()
    bloque.fichero.setFilePath(pdf(b'<?xml version="1.0"?><otra/>', 'sin_informe.pdf'))
    texto = textos_panel()
    ok = 'no lleva el XML' in texto and not bloque.mapaBoton.isEnabled() and not bloque.guardarBoton.isEnabled()
    bloque.fichero.setFilePath(pdf(icuc(), 'Informe_icuc_panel.pdf'))
    texto = textos_panel()
    icuc_ok = ('Ubicación correcta' in texto and 'precisión 0.800 m' in texto and 'edificio.gml' in texto
               and not sin_personales(texto))
    return ok and icuc_ok, texto[:300]


caso("PDF sin informe (aviso, botones desactivados) e ICUC en el panel", error_en_el_panel)

dw.cleanup()
dw.deleteLater()
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
resultados["ninguna ventana emergente"] = not ventanas

print("=" * 60)
print("QGIS", Qgis.version(), "· Leer informe de la Sede: batería de casos")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, d in detalles.items():
    print("Detalles", nombre, ":", d)
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
