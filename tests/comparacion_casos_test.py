"""
Batería de casos de «Comparar con el Catastro» (Validar; plan de pruebas, docs/PLAN_PRUEBAS.md): GML de parcela y de
edificio en situaciones que no son la segregación de manual. El Catastro está simulado (tests/simulador_catastro.py),
también caído, en mantenimiento o devolviendo algo inesperado. Ningún caso puede lanzar una excepción.

Uso: tools\\probar.bat (o tools\\run_tests.py comparacion_casos_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import importlib.util
import os
import re
import tempfile
import traceback

import qgis.utils
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsGeometry, QgsProject
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
import catastral_gml_tools.gui.pestana_validar as pv_module  # noqa: E402
from catastral_gml_tools.core import comparacion as cmp  # noqa: E402
from catastral_gml_tools.core import geometria as geo  # noqa: E402
from catastral_gml_tools.core import gml_edificio as ge  # noqa: E402
from catastral_gml_tools.core import gml_lector as gl  # noqa: E402
from catastral_gml_tools.core import gml_parcela as gp  # noqa: E402
from catastral_gml_tools.core import servicios  # noqa: E402
from catastral_gml_tools.core.incidencias import ERROR, INFO, Incidencia  # noqa: E402
from catastral_gml_tools.core.info import RAIZ  # noqa: E402

spec = importlib.util.spec_from_file_location('simulador_catastro', os.path.join(RAIZ, 'tests', 'simulador_catastro.py'))
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)
original = sim.instalar()
pv_module.esquemas.validar = lambda datos, version, feedback=None: [Incidencia(INFO, 'XSD-VALIDO', "Cumple el esquema")]

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))

carpeta = tempfile.mkdtemp(prefix='cgt_cmp_casos_')
X0, Y0, rect, RC = sim.X0, sim.Y0, sim.rect, sim.RC
resultados, detalles = {}, {}
PAGINA_MANTENIMIENTO = ('<HTML><HEAD><title>Sede Electrónica del Catastro</title></HEAD><BODY><td>&nbsp;INTERRUPCIÓN DEL '
                        'SERVICIO POR MOTIVOS DE MANTENIMIENTO</td><td>&nbsp;Tiempo estimado desde las 15.15H hasta las '
                        '19.00.H. Disculpe las molestias.</td></BODY></HTML>').encode()


def escribir(nombre, parcelas, epsg=25830):
    ruta = os.path.join(carpeta, nombre + '.gml')
    ok, inc = gp.escribir(ruta, parcelas, epsg)
    assert ok, (nombre, inc)
    return ruta


def guardar(nombre, texto):
    ruta = os.path.join(carpeta, nombre + '.gml')
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write(texto)
    return ruta


def leer_texto(ruta):
    with open(ruta, encoding='utf-8') as f:
        return f.read()


def comparar_ruta(ruta):
    return cmp.comparar(gl.leer(ruta))


def codigos(c):
    return {i.codigo for i in c.incidencias}


def caso(nombre, funcion):
    try:
        ok, detalle = funcion()
        resultados[nombre] = bool(ok)
        if not ok:
            detalles[nombre] = detalle
    except Exception:  # noqa: BLE001
        resultados[nombre] = False
        detalles[nombre] = traceback.format_exc()[-900:]


def resumen(c):
    return c.operacion, sorted(codigos(c)), [i.mensaje[:110] for i in c.incidencias if i.nivel == ERROR][:3]


SEG = [gp.ParcelaGML(RC, gp.SDGC, rect(X0, Y0, 20, 18), '01'), gp.ParcelaGML('Seg_1', gp.LOCAL, rect(X0, Y0 + 18, 20, 12))]


# 1. El mismo GML escrito de otra forma
def en_otro_huso():
    ruta = escribir('huso29', [gp.ParcelaGML(p.local_id, p.namespace, geo.transformar(
        p.geometria, QgsCoordinateReferenceSystem('EPSG:25830'), 25829), p.label) for p in SEG], 25829)
    c = comparar_ruta(ruta)
    return c.operacion.startswith("Segregación") and not any(i.nivel == ERROR for i in c.incidencias), resumen(c)


def tres_decimales():
    texto = leer_texto(escribir('seg', SEG))
    texto = re.sub(r'(\d+\.\d\d)(?=[ <])', lambda m: m.group(1) + '4', texto)  #+4 mm en cada coordenada
    c = comparar_ruta(guardar('seg_3dec', texto))
    return 'CMP-TRUNCADO' in codigos(c) and 'CMP-CONTORNO-OK' in codigos(c), resumen(c)


def esquema_30():
    c = comparar_ruta(os.path.join(RAIZ, 'tests', 'data', 'gml', 'parcela_cp30_sintetica.gml'))
    return not c.comparada and not c.incidencias, resumen(c)


def src_no_admitido():
    ruta = guardar('wgs84', leer_texto(escribir('seg', SEG)).replace('EPSG/0/25830', 'EPSG/0/4326'))
    c = comparar_ruta(ruta)
    return not c.comparada and 'CMP-SRC' in codigos(c), resumen(c)


caso("el GML en otro huso (25829): segregación, sin errores", en_otro_huso)
caso("3 decimales (4 mm de más): se trunca como la Sede y coincide", tres_decimales)
caso("esquema 3.0: no se compara (y no falla)", esquema_30)
caso("EPSG:4326: no se compara y se dice", src_no_admitido)


# 1b. Operaciones (tabla NPO/NPP/namespace del documento de validación de la DGC)
def operacion(nombre, parcelas, empieza, codigos_esperados=(), sin=()):
    def prueba():
        c = comparar_ruta(escribir(nombre, parcelas))
        ok = c.operacion.startswith(empieza) and all(x in codigos(c) for x in codigos_esperados)
        return ok and not any(x in codigos(c) for x in sin), resumen(c)
    return prueba


L, S = gp.LOCAL, gp.SDGC
R2, R3 = '1907402VK4810H', '1907403VK4810H'
caso("división (todas LOCAL)", operacion('division', [gp.ParcelaGML('Div_1', L, rect(X0, Y0, 20, 18)),
                                                      gp.ParcelaGML('Div_2', L, rect(X0, Y0 + 18, 20, 12))], "División"))
caso("agregación (una SDGC sobre dos)", operacion('agregacion', [gp.ParcelaGML(RC, S, rect(X0, Y0, 40, 30), '01')],
                                                  "Agregación"))
caso("agrupación (una LOCAL sobre dos)", operacion('agrupacion', [gp.ParcelaGML('Agrupa_1', L, rect(X0, Y0, 40, 30))],
                                                   "Agrupación"))
caso("subsanación (lindero común movido 1 m)", operacion('subsanacion', [gp.ParcelaGML(RC, S, rect(X0, Y0, 21, 30), '01'),
                                                                         gp.ParcelaGML(R2, S, rect(X0 + 21, Y0, 19, 30), '02')],
                                                         "Subsanación de discrepancias"))
caso("igual al Catastro: operación «ninguna»", operacion('igual', [gp.ParcelaGML(RC, S, rect(X0, Y0, 20, 30), '01')],
                                                         "ninguna", ['CMP-SIN-CAMBIOS']))
caso("no permitida: dos SDGC de una parcela", operacion('no_permitida', [gp.ParcelaGML(RC, S, rect(X0, Y0, 20, 18), '01'),
                                                                         gp.ParcelaGML(R2, S, rect(X0, Y0 + 18, 20, 12), '02')],
                                                        "No permitida"))
caso("desplazada 2 cm: afectada en parte", operacion('d2cm', [gp.ParcelaGML(RC, S, rect(X0 + 0.02, Y0, 20, 30), '01')],
                                                     "", ['CMP-PARCIAL']))
caso("desplazada 5 mm: dentro de la tolerancia", operacion('d5mm', [gp.ParcelaGML(RC, S, rect(X0 + 0.005, Y0, 20, 30), '01')],
                                                           "ninguna", ['CMP-SIN-CAMBIOS'], ['CMP-PARCIAL']))


def pico(nombre, salida):
    return QgsGeometry.fromWkt(f"POLYGON(({X0} {Y0}, {X0} {Y0 + 30}, {X0 + 20} {Y0 + 30}, {X0 + 20 + salida} {Y0 + 15}, "
                               f"{X0 + 20} {Y0}, {X0} {Y0}))")


caso("pico de 0,8 cm hacia la vecina: dentro de la tolerancia",
     operacion('pico1', [gp.ParcelaGML(RC, S, pico('p', 0.008), '01')], "ninguna", [], ['CMP-PARCIAL']))
caso("pico de 2 cm hacia la vecina: la afecta en parte",
     operacion('pico2', [gp.ParcelaGML(RC, S, pico('p', 0.02), '01')], "", ['CMP-PARCIAL']))
caso("calle ocupada por una parcela con RC: error", operacion('calle', [gp.ParcelaGML(R3, S, rect(X0 + 40, Y0, 25, 30), '03')],
                                                              "", ['CMP-SIN-PARCELA']))
caso("cesión de viario con una parcela LOCAL: aviso", operacion('cesion', [gp.ParcelaGML(R3, S, rect(X0 + 40, Y0, 20, 30), '03'),
                                                                           gp.ParcelaGML('Nueva_1', L, rect(X0 + 60, Y0, 5, 30))],
                                                                "", ['CMP-VIARIO'], ['CMP-SIN-PARCELA']))
caso("dominio público afectado: aviso", operacion('camino', [gp.ParcelaGML(RC, S, rect(X0, Y0 - 3, 20, 33), '01')],
                                                  "", ['CMP-DOMINIO-PUBLICO']))
caso("RC de otra parcela (ajena): error", operacion('ajena', [gp.ParcelaGML(R3, S, rect(X0, Y0, 20, 18), '03'),
                                                             gp.ParcelaGML('Seg_1', L, rect(X0, Y0 + 18, 20, 12))],
                                                    "", ['CMP-RC-AJENA']))
caso("en el mar (sin parcelas debajo): error", operacion('mar', [gp.ParcelaGML('Nueva_1', L, rect(X0, Y0 - 50000, 20, 30))],
                                                         "Sin parcelas", ['CMP-SIN-ORIGEN']))
caso("31 parcelas de una: aviso de más de 30", operacion('mas30', [gp.ParcelaGML(f'Div_{i}', L, rect(X0, Y0 + i * 30 / 31, 20, 30 / 31))
                                                                   for i in range(31)], "División", ['CMP-MAS-30']))
def navarra():
    #El escritor del plugin no deja poner una RC foral como SDGC: se cambia en el texto, como lo traería otro programa
    texto = leer_texto(escribir('base_nav', [gp.ParcelaGML(RC, S, rect(X0, Y0, 20, 30), '01')])).replace(RC, '31001A00100001')
    c = comparar_ruta(guardar('foral', texto))
    return not c.comparada and 'RC-FORAL' in codigos(c), resumen(c)


def hueco_rustico():
    """En rústica, el suelo sin parcela no es una calle: un hueco de la cartografía (guías de la Gerencia de Valencia)."""
    c = comparar_ruta(escribir('hueco_rustica', [gp.ParcelaGML(sim.RUSTICA_SOLA, gp.SDGC, rect(X0 + 300, Y0, 50, 51), '10')]))
    texto = ' '.join(i.mensaje for i in c.incidencias if i.codigo == 'CMP-SIN-PARCELA')
    return 'rústica, un hueco de la cartografía' in texto and 'vía pública' not in texto, resumen(c)


caso("rústica que ocupa un hueco de la cartografía: lo dice así, no «vía pública»", hueco_rustico)


caso("referencia de Navarra: no se compara y se dice", navarra)


def huso_equivocado():
    #Coordenadas del huso 30 declaradas en el 29: caen en otro sitio; no puede salir «coincide»
    texto = leer_texto(escribir('seg', SEG)).replace('EPSG/0/25830', 'EPSG/0/25829')
    c = comparar_ruta(guardar('huso_mal', texto))
    return 'CMP-CONTORNO-OK' not in codigos(c), resumen(c)


caso("coordenadas del huso 30 declaradas en el 29: no da por buena la comparación", huso_equivocado)


# 2. Cartografía y geometría
def desplazado_2m():
    c = comparar_ruta(escribir('desplazado', [gp.ParcelaGML(RC, gp.SDGC, rect(X0 + 2, Y0 + 1, 20, 30), '01')]))
    return 'CMP-PARCIAL' in codigos(c) and c.exceso is not None and c.defecto is not None, resumen(c)


def lejos_de_todo():
    c = comparar_ruta(escribir('lejos', [gp.ParcelaGML('Nueva_1', gp.LOCAL, rect(X0 + 3000, Y0 + 3000, 20, 30))]))
    return 'CMP-SIN-ORIGEN' in codigos(c), resumen(c)


def con_hueco():
    hueco = QgsGeometry.fromWkt(f"POLYGON(({X0} {Y0}, {X0} {Y0 + 30}, {X0 + 20} {Y0 + 30}, {X0 + 20} {Y0}, {X0} {Y0}),"
                                f"({X0 + 5} {Y0 + 5}, {X0 + 9} {Y0 + 5}, {X0 + 9} {Y0 + 9}, {X0 + 5} {Y0 + 9}, {X0 + 5} {Y0 + 5}))")
    c = comparar_ruta(escribir('hueco', [gp.ParcelaGML(RC, gp.SDGC, hueco, '01')]))
    return c.comparada and c.defecto is not None and abs(c.defecto.area() - 16) < 0.01, resumen(c)


def geometria_invalida():
    texto = leer_texto(escribir('base', [gp.ParcelaGML(RC, gp.SDGC, rect(X0, Y0, 20, 30), '01')]))
    m = re.search(r'(<gml:posList[^>]*>)([^<]*)(<)', texto)
    pajarita = f'{X0} {Y0} {X0 + 20} {Y0 + 30} {X0 + 20} {Y0} {X0} {Y0 + 30} {X0} {Y0}'
    c = comparar_ruta(guardar('pajarita', texto[:m.start(2)] + pajarita + texto[m.end(2):]))
    return 'CMP-GEO-INVALIDA' in codigos(c), resumen(c)


def parcela_grande():
    c = comparar_ruta(escribir('grande', [gp.ParcelaGML(sim.RC_GRANDE, gp.SDGC, rect(X0 + 5000, Y0, 1200, 1000), '07')]))
    return c.comparada and 'CMP-CONTORNO-OK' in codigos(c), resumen(c)


def demasiado_grande():
    c = comparar_ruta(escribir('enorme', [gp.ParcelaGML('Nueva_1', gp.LOCAL, rect(X0, Y0, 6000, 6000))]))
    return not c.comparada and any('demasiado extenso' in i.mensaje for i in c.incidencias), resumen(c)


def zonas_muy_separadas():
    ruta = escribir('zonas', SEG + [gp.ParcelaGML('Nueva_9', gp.LOCAL, rect(X0 + 5000, Y0, 20, 30))])
    sim.peticiones.clear()
    c = comparar_ruta(ruta)
    cajas = [p for p in sim.peticiones if 'bbox' in p.lower()]
    return 'CMP-ZONAS' in codigos(c) and len(cajas) <= 4, (resumen(c), len(cajas))


caso("cartografía desplazada 2 m: parcial, con exceso y defecto", desplazado_2m)
caso("parcela lejos de cualquier catastral: sin origen", lejos_de_todo)
caso("parcela con hueco: el hueco es suelo sin cubrir", con_hueco)
caso("geometría inválida (pajarita): compara una versión corregida y lo dice", geometria_invalida)
caso("parcela de 1,2 km: se pide en trozos y coincide", parcela_grande)
caso("parcelario de 6 × 6 km: no se compara y se dice", demasiado_grande)
caso("dos zonas a 5 km: se piden solo las zonas", zonas_muy_separadas)


# 3. El Catastro no responde como se espera
def con_respuesta(respuesta, nombre):
    servicios.pedir = respuesta
    try:
        c = comparar_ruta(escribir('seg', SEG))
    finally:
        servicios.pedir = sim.pedir
    return c, nombre


def sin_red():
    c, _ = con_respuesta(lambda url: (b'', 'Host ovc.catastro.meh.es not found (simulado)'), 'sin red')
    return not c.comparada and 'CMP-NO-COMPARADO' in codigos(c), resumen(c)


def mantenimiento():
    c, _ = con_respuesta(lambda url: (b'', servicios.mantenimiento(PAGINA_MANTENIMIENTO)) if 'ovc' in url else sim.pedir(url),
                         'mantenimiento')
    texto = ' '.join(i.mensaje for i in c.incidencias)
    return not c.comparada and 'mantenimiento' in texto.lower() and '19.00' in texto, resumen(c)


def respuesta_html():
    c, _ = con_respuesta(lambda url: (b'<html><body>Error 500</body></html>', ''), 'html')
    return not c.comparada and bool(c.incidencias), resumen(c)


def respuesta_vacia():
    c, _ = con_respuesta(lambda url: (b'', ''), 'vacía')
    return not c.comparada and bool(c.incidencias), resumen(c)


def excepcion_wfs():
    c, _ = con_respuesta(lambda url: (sim.EXCEPCION.format(rc=RC, huso=25830).encode('latin-1'), ''), 'excepción')
    return bool(c.incidencias), resumen(c)


def ficha_caida():
    sim.DNPRC_CAIDO = True
    try:
        c = comparar_ruta(escribir('seg', SEG))
    finally:
        sim.DNPRC_CAIDO = False
    return c.operacion.startswith("Segregación"), resumen(c)


def cancelado():
    #Con la tarea cancelada, la petición en curso devuelve CANCELADO (el simulador no mira el feedback: se simula)
    c, _ = con_respuesta(lambda url: (b'', servicios.CANCELADO), 'cancelado')
    return not c.comparada, resumen(c)


def red_cae_a_mitad():
    """Las parcelas llegan, pero al comprobar si existe una referencia ajena se cae la red: no debe decir «no existe»."""
    llamadas = []

    def pedir(url):
        llamadas.append(url)
        return sim.pedir(url) if 'bbox' in url.lower() or 'dnprc' in url.lower() else (b'', 'Connection reset (simulado)')
    c, _ = con_respuesta(pedir, 'a mitad')
    ruta = escribir('rc_ajena', [gp.ParcelaGML('1907499VK4810H', gp.SDGC, rect(X0, Y0, 20, 30), '01')])
    servicios.pedir = pedir
    try:
        c = comparar_ruta(ruta)
    finally:
        servicios.pedir = sim.pedir
    return 'CMP-RC-NO-EXISTE' not in codigos(c) and 'CMP-RC-SIN-COMPROBAR' in codigos(c), resumen(c)


caso("sin internet: no se compara y se dice", sin_red)
caso("Sede en mantenimiento: se dice con el horario", mantenimiento)
caso("respuesta HTML de error: no se compara, sin fallar", respuesta_html)
caso("respuesta vacía: no se compara, sin fallar", respuesta_vacia)
caso("respuesta de excepción del WFS: sin fallar", excepcion_wfs)
caso("la consulta de datos de parcela falla: se compara igual", ficha_caida)
caso("cancelado: no se compara, sin fallar", cancelado)
caso("la red se cae a mitad: no dice que una referencia no existe", red_cae_a_mitad)


# 4. Edificios (ICUC)
def edificio(nombre, construcciones):
    ruta = os.path.join(carpeta, nombre + '_bu.gml')
    ok, inc = ge.escribir(ruta, construcciones, 25830)
    assert ok, inc
    return cmp.comparar_edificio(gl.leer(ruta))


def bu_rc_inexistente():
    c = edificio('inexistente', [ge.Construccion('1907499VK4810H', rect(X0 + 2, Y0 + 2, 5, 5), plantas=1)])
    return 'CMP-RC-NO-EXISTE' in codigos(c), resumen(c)


def bu_lejos():
    c = edificio('lejos', [ge.Construccion(RC, rect(X0 + 400, Y0, 5, 5), plantas=1)])
    return any(i.nivel == ERROR for i in c.incidencias), resumen(c)


def bu_sin_red():
    servicios.pedir = lambda url: (b'', 'Host ovc.catastro.meh.es not found (simulado)')
    try:
        c = edificio('sinred', [ge.Construccion(RC, rect(X0 + 2, Y0 + 2, 5, 5), plantas=1)])
    finally:
        servicios.pedir = sim.pedir
    return bool(c.incidencias) and not any(i.codigo == 'CMP-BU-DENTRO' for i in c.incidencias), resumen(c)


def bu_dentro_y_fuera():
    c = edificio('mixto', [ge.Construccion(f'{RC}_Edificio_1', rect(X0 + 2, Y0 + 2, 5, 5), plantas=1),
                           ge.Construccion(f'{RC}_Edificio_2', rect(X0 + 18, Y0 + 2, 5, 5), plantas=2)])
    cods = [i.codigo for i in c.incidencias]
    return 'CMP-BU-FUERA' in cods and 'CMP-BU-DENTRO' not in cods and c.exceso is not None, resumen(c)


caso("edificio con una RC que no existe: error", bu_rc_inexistente)
caso("edificio a 400 m de su parcela: error", bu_lejos)
caso("edificio sin internet: no dice «dentro», sin fallar", bu_sin_red)
caso("dos construcciones, una dentro y otra en parte fuera", bu_dentro_y_fuera)


def bu_sin_rc():
    c = edificio('sin_rc', [ge.Construccion('Edificio_1', rect(X0 + 2, Y0 + 2, 5, 5), plantas=1)])
    return 'CMP-BU-SIN-RC' in codigos(c), resumen(c)


caso("edificio sin la RC en el identificador: no se compara y se dice", bu_sin_rc)


# 5. La pestaña: comparar, abrir otro fichero a mitad, cerrar el panel
def pestana():
    dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
    pv = dw.pestanaValidar
    pv.fichero.setFilePath(escribir('seg', SEG))
    pv.esquema_comprobado([])
    pv.comparar_catastro(segundo_plano=False)
    primera = pv.comparacion is not None and pv.comparacion.operacion.startswith("Segregación")
    #Abrir otro fichero mientras «llega» una comparación anterior: se descarta (no se mezclan resultados)
    vieja = pv.comparacion
    generacion = pv.generacion
    pv.fichero.setFilePath(escribir('desplazado', [gp.ParcelaGML(RC, gp.SDGC, rect(X0 + 2, Y0 + 1, 20, 30), '01')]))
    pv.comparado(vieja, generacion)
    descartada = pv.comparacion is not vieja
    #Con una comparación en curso, cerrar el plugin la cancela sin fallar
    pv.comparar_catastro()
    dw.cleanup()
    cerrada = pv.tarea_cmp is None or pv.tarea_cmp.feedback.isCanceled()
    barra = ' '.join(e.text() for item in dw.messageBar.items() for e in item.findChildren(QLabel))
    dw.deleteLater()
    QgsProject.instance().removeAllMapLayers()
    return primera and descartada and cerrada, (primera, descartada, cerrada, barra[:200])


caso("pestaña: comparar, descartar un resultado viejo y cerrar a mitad", pestana)

servicios.pedir = original
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
resultados["ninguna ventana emergente"] = not ventanas

print("=" * 60)
print("QGIS", Qgis.version(), "· comparar con el Catastro: batería de casos")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, d in detalles.items():
    print("Detalles", nombre, ":", d)
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
