"""
Prueba del conversor de GML de parcela 3.0 → 4.0 y de la reparación de un 4.0 (fase 9, AU-53): core/conversor.py, el
botón «Convertir a 4.0» / «Reparar» de Validar y el bloque de Utilidades. Ficheros sintéticos (coordenadas inventadas).
Sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py conversor_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import datetime
import os
import re
import shutil
import tempfile

import qgis.utils
from qgis.core import Qgis
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import conversor as cv  # noqa: E402
from catastral_gml_tools.core import gml_lector as gl  # noqa: E402
from catastral_gml_tools.core import validador as va  # noqa: E402
from catastral_gml_tools.core.incidencias import codigos  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))

carpeta = tempfile.mkdtemp(prefix='cgt_conversor_')
RC = '1907401VK4810H'
DATOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'gml')


def parcela_30(gml_id, local_id, ns, coords, area, count, fecha='2019-05-20T00:00:00'):
    inicio = (f'<cp:beginLifespanVersion>{fecha}</cp:beginLifespanVersion>' if fecha else
              '<cp:beginLifespanVersion xsi:nil="true" nilReason="other:unpopulated"></cp:beginLifespanVersion>')
    return (f'<gml:featureMember><cp:CadastralParcel gml:id="{gml_id}"><cp:areaValue uom="m2">{area}</cp:areaValue>{inicio}'
            f'<cp:geometry><gml:MultiSurface gml:id="MS_{local_id}" srsName="urn:ogc:def:crs:EPSG::25830"><gml:surfaceMember>'
            f'<gml:Surface gml:id="S_{local_id}" srsName="urn:ogc:def:crs:EPSG::25830"><gml:patches><gml:PolygonPatch>'
            f'<gml:exterior><gml:LinearRing><gml:posList srsDimension="2" count="{count}">{coords}</gml:posList>'
            '</gml:LinearRing></gml:exterior></gml:PolygonPatch></gml:patches></gml:Surface></gml:surfaceMember>'
            '</gml:MultiSurface></cp:geometry>'
            f'<cp:inspireId><base:Identifier><base:localId>{local_id}</base:localId><base:namespace>{ns}</base:namespace>'
            f'</base:Identifier></cp:inspireId><cp:label>{local_id[5:7] if ns == "ES.SDGC.CP" else local_id}</cp:label>'
            f'<cp:nationalCadastralReference>{local_id}</cp:nationalCadastralReference>'
            '<cp:validFrom xsi:nil="true" nilReason="other:unpopulated"></cp:validFrom>'
            '<cp:zoning xsi:nil="true" nilReason="other:unpopulated"></cp:zoning>'
            '</cp:CadastralParcel></gml:featureMember>')


def fichero_30(parcelas, xlink=False):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!-- SINTETICO de Catastral GML Tools: esquema 3.0, coordenadas inventadas -->\n'
            '<gml:FeatureCollection gml:id="ES.LOCAL.CP" xmlns:gml="http://www.opengis.net/gml/3.2" '
            + ('xmlns:xlink="http://www.w3.org/1999/xlink" ' if xlink else '')
            + 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns:cp="urn:x-inspire:specification:gmlas:CadastralParcels:3.0" '
            'xmlns:base="urn:x-inspire:specification:gmlas:BaseTypes:3.2" '
            'xsi:schemaLocation="urn:x-inspire:specification:gmlas:CadastralParcels:3.0 '
            'http://inspire.ec.europa.eu/schemas/cp/3.0/CadastralParcels.xsd">'
            '<gml:boundedBy><gml:Envelope srsName="urn:ogc:def:crs:EPSG::25830"><gml:lowerCorner>421500 4070500</gml:lowerCorner>'
            '<gml:upperCorner>421540 4070510</gml:upperCorner></gml:Envelope></gml:boundedBy>'
            + ''.join(parcelas) + '</gml:FeatureCollection>\n')


def leer_texto(ruta):
    if not os.path.isfile(ruta):
        return ''
    with open(ruta, encoding='utf-8') as f:
        return f.read()


def guardar(nombre, texto):
    ruta = os.path.join(carpeta, nombre)
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write(texto)
    return ruta


#3.0 «sucio»: anillo antihorario, count erróneo, superficie que no cuadra, 3 decimales, sin xmlns:xlink, con zoning
SUCIO = fichero_30([
    parcela_30(f'ES.SDGC.CP.{RC}', RC, 'ES.SDGC.CP',
               '421500.004 4070500.003 421520.002 4070500.001 421520.004 4070510.002 421500.001 4070510.004 421500.004 4070500.003',
               190, 4),
    parcela_30('ES.LOCAL.CP.Seg_1', 'Seg_1', 'ES.LOCAL.CP',
               '421520.002 4070500.001 421520.004 4070510.002 421540.000 4070510.000 421540.000 4070500.000 421520.002 4070500.001',
               200, 5),
])

# 1. 3.0 → 4.0: esquema, reparaciones, lo que se conserva y lo que se dice
ruta = guardar('sucio.gml', SUCIO)
antes = gl.leer(ruta)
destino = cv.destino_propuesto(ruta, antes.version)
ok, version, cambios, inc = cv.convertir(ruta, destino)
nueva = gl.leer(destino) if os.path.isfile(destino) else gl.ResultadoLectura()
informe = va.validar(destino) if os.path.isfile(destino) else None
texto = leer_texto(destino)
cambios_txt = ' | '.join(cambios)
desplazamiento = max((a.geometria.hausdorffDistance(b.geometria) for a, b in zip(antes.elementos, nueva.elementos)), default=9)
convertido = (ok and version == 'CP 3.0' and destino.endswith('sucio_v4.gml') and nueva.version == 'CP 4.0'
              and informe is not None and not informe.errores
              and [(e.local_id, e.namespace, e.label) for e in nueva.elementos]
              == [(RC, 'ES.SDGC.CP', '01'), ('Seg_1', 'ES.LOCAL.CP', 'Seg_1')]
              and [e.area_declarada for e in nueva.elementos] == [200, 200]
              and '2019-05-20T00:00:00' in texto and 'zoning' not in texto and 'validFrom' not in texto
              and 'boundedBy' not in texto and 'featureMember' not in texto and 'xmlns:xlink' in texto
              and desplazamiento < 0.006)
informado = ('Esquema 3.0 → 4.0' in cambios_txt and f'{RC}: superficie (areaValue) 190 → 200' in cambios_txt
             and '3 decimales redondeadas' in cambios_txt and 'Corregido:' in cambios_txt
             and re.search(r'Corregido:.*(horario|sentido)', cambios_txt, re.I) is not None
             and 'Fecha' not in cambios_txt and not [i for i in inc if i.nivel == 'ERROR'])

# 2. Sin fecha en el original: la que se indica; el fichero sin cambios que reportar
ruta_sin_fecha = guardar('sin_fecha.gml', fichero_30([parcela_30('ES.LOCAL.CP.P_1', 'P_1', 'ES.LOCAL.CP',
                                                                 '421500 4070500 421500 4070510 421520 4070510 421520 4070500 421500 4070500',
                                                                 200, 5, fecha='')], xlink=True))
ok2, _, cambios2, _ = cv.convertir(ruta_sin_fecha, cv.destino_propuesto(ruta_sin_fecha), datetime.datetime(2026, 10, 14, 9, 30))
sin_fecha = ok2 and any('14/10/2026 09:30' in c for c in cambios2) and '2026-10-14T09:30:00' in leer_texto(
    cv.destino_propuesto(ruta_sin_fecha).replace('_v4_2', '_v4'))

# 3. Reparar un 4.0 (sin xmlns:xlink y con la superficie mal): sale «_reparado» y sin errores
texto_40 = texto.replace(' xmlns:xlink="http://www.w3.org/1999/xlink"', '').replace('>200</cp:areaValue>', '>150</cp:areaValue>', 1)
ruta_40 = guardar('roto_40.gml', texto_40)
informe_roto = va.validar(ruta_40)
destino_40 = cv.destino_propuesto(ruta_40, 'CP 4.0')
ok3, version3, cambios3, inc3 = cv.convertir(ruta_40, destino_40)
reparado = (ok3 and version3 == 'CP 4.0' and destino_40.endswith('roto_40_reparado.gml')
            and {'XLINK', 'SUP-DISTINTA'} <= set(codigos(informe_roto.incidencias))
            and not va.validar(destino_40).errores and 'Esquema 3.0' not in ' '.join(cambios3)
            and any('150 → 200' in c for c in cambios3) and any('xlink' in c for c in cambios3))

# 4. Nunca sobrescribe: el original como salida es un error; la propuesta salta los nombres que ya existen
_, _, _, inc_mismo = cv.convertir(ruta, ruta)
no_pisa = (codigos(inc_mismo) == ['CONV-DESTINO'] and cv.destino_propuesto(ruta, 'CP 3.0').endswith('sucio_v4_2.gml')
           and leer_texto(ruta) == SUCIO)

# 5. Lo que no se convierte: edificio, XML mal formado, SDGC sin referencia catastral (no se inventa)
_, _, _, inc_bu = cv.convertir(os.path.join(DATOS, 'edificio_sintetico.gml'), os.path.join(carpeta, 'bu.gml'))
_, _, _, inc_mal = cv.convertir(os.path.join(DATOS, 'mal_formado.gml'), os.path.join(carpeta, 'mal.gml'))
ruta_rc = guardar('rc_mal.gml', SUCIO.replace(RC, '1907401-VK48'))  #SDGC con algo que no es una RC
ok_rc, _, _, inc_rc = cv.convertir(ruta_rc, os.path.join(carpeta, 'rc_mal_v4.gml'))
rechazos = (codigos(inc_bu) == ['CONV-NO-PARCELA'] and codigos(inc_mal) == ['XML-MAL-FORMADO']
            and not ok_rc and not os.path.exists(os.path.join(carpeta, 'rc_mal_v4.gml'))
            and any(i.codigo.startswith(('NS-', 'RC')) for i in inc_rc))

# 6. Validar: botón «Convertir a 4.0» con un 3.0; un clic crea la copia y la abre; con un 4.0 correcto no se ve
dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
pv = dw.pestanaValidar
ruta_ui = guardar('validar_30.gml', SUCIO)
pv.fichero.setFilePath(ruta_ui)
boton_30 = not pv.convertirBoton.isHidden() and pv.convertirBoton.text() == "Convertir a 4.0"
creado = pv.convertir()


def textos_barra():
    item = dw.messageBar.currentItem()
    return ' '.join([item.text()] + [e.text() for e in item.findChildren(QLabel)]) if item is not None else ''


validar_ui = (boton_30 and creado is not None and creado.endswith('validar_30_v4.gml')
              and os.path.normcase(pv.fichero.filePath()) == os.path.normcase(creado)
              and pv.resultado.version == 'CP 4.0' and pv.convertirBoton.isHidden()
              and 'Convertido a 4.0: validar_30_v4.gml' in textos_barra() and 'Esquema 3.0 → 4.0' in textos_barra())
pv.fichero.setFilePath(ruta_40)
validar_ui = validar_ui and not pv.convertirBoton.isHidden() and pv.convertirBoton.text() == "Reparar"

# 7. Utilidades: dice qué hará, propone la salida, convierte y un segundo clic no pisa lo creado
pu = dw.pestanaUtilidades
ruta_u = guardar('utilidades_30.gml', SUCIO)
pu.origenConv.setFilePath(ruta_u)
propuesta = pu.destinoConv.filePath()
estado = pu.estadoConv.text()
hecho = pu.convertir()
utilidades = ('Esquema 3.0' in estado and pu.convertirBoton.text() == "Convertir a 4.0" and propuesta.endswith('utilidades_30_v4.gml')
              and hecho == propuesta and os.path.isfile(hecho) and pu.destinoConv.filePath().endswith('utilidades_30_v4_2.gml')
              and dw.gml_pendiente == hecho)
pu.origenConv.setFilePath(os.path.join(DATOS, 'edificio_sintetico.gml'))
utilidades = utilidades and not pu.convertirBoton.isEnabled() and 'No es un GML de parcela' in pu.estadoConv.text()

for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
dw.deleteLater()
shutil.rmtree(carpeta, ignore_errors=True)

checks = {
    "3.0 → 4.0: esquema, anillos, superficies y decimales corregidos; ids, labels y fecha conservados": convertido,
    "dice qué ha cambiado (esquema, superficies, decimales, corregidos)": informado,
    "sin fecha en el original: la indicada, y se dice": sin_fecha,
    "reparar un 4.0 (xmlns:xlink y superficie): «_reparado» sin errores": reparado,
    "nunca sobrescribe el original ni lo ya creado": no_pisa,
    "no convierte edificios, XML mal formado ni SDGC sin referencia catastral (no inventa)": rechazos,
    "Validar: «Convertir a 4.0» con un clic y abre la copia; «Reparar» en un 4.0 con fallos": validar_ui,
    "Utilidades: estado, salida propuesta y sin pisar lo creado": utilidades,
    "ninguna ventana emergente": not ventanas,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· conversor 3.0 → 4.0 y reparación")
for nombre, ok_ in checks.items():
    print(("  OK   " if ok_ else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'ok': ok, 'cambios': cambios, 'inc': [str(i) for i in inc], 'nueva': [(e.local_id, e.namespace, e.label, e.area_declarada) for e in nueva.elementos],
                        'errores': [str(i) for i in informe.errores] if informe else None, 'desp': desplazamiento,
                        'cambios2': cambios2, 'cambios3': cambios3, 'inc3': [str(i) for i in inc3],
                        'roto': codigos(informe_roto.incidencias), 'mismo': codigos(inc_mismo),
                        'bu': codigos(inc_bu), 'mal': codigos(inc_mal), 'rc': [str(i) for i in inc_rc],
                        'barra': textos_barra(), 'estado': estado, 'propuesta': propuesta, 'hecho': hecho})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
