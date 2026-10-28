"""
Batería de casos de la pestaña Descargar (plan de pruebas, docs/PLAN_PRUEBAS.md): referencias escritas de cualquier
forma, parcelas de otro huso, de catastros forales o que no existen, y el Catastro respondiendo mal (sin red, en
mantenimiento, con una página HTML, vacío, a medias, cancelado). La descarga nunca puede lanzar una excepción: o trae
la parcela o dice por qué no. El Catastro está simulado (tests/simulador_catastro.py).

Uso: tools\\probar.bat (o tools\\run_tests.py descargar_casos_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import importlib.util
import os
import traceback

import qgis.utils
from qgis.core import Qgis, QgsPointXY, QgsProject
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import servicios  # noqa: E402
from catastral_gml_tools.core.incidencias import ERROR  # noqa: E402
from catastral_gml_tools.core.info import RAIZ  # noqa: E402

spec = importlib.util.spec_from_file_location('simulador_catastro', os.path.join(RAIZ, 'tests', 'simulador_catastro.py'))
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)
original = sim.instalar()

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))

RC = sim.RC
resultados, detalles = {}, {}
PAGINA_MANTENIMIENTO = ('<HTML><BODY><td>&nbsp;INTERRUPCIÓN DEL SERVICIO POR MOTIVOS DE MANTENIMIENTO</td><td>&nbsp;Tiempo '
                        'estimado desde las 15.15H hasta las 19.00.H. Disculpe las molestias.</td></BODY></HTML>').encode()


def caso(nombre, funcion):
    try:
        ok, detalle = funcion()
        resultados[nombre] = bool(ok)
        if not ok:
            detalles[nombre] = detalle
    except Exception:  # noqa: BLE001
        resultados[nombre] = False
        detalles[nombre] = traceback.format_exc()[-900:]


def resumen(d):
    return (d.rc, d.epsg, d.correcta, len(d.colindantes.elementos) if d.colindantes else None,
            [(i.codigo, i.mensaje[:100]) for i in d.incidencias][:4])


def con(respuesta, rc=RC, **opciones):
    servicios.pedir = respuesta
    try:
        return servicios.descargar(rc, **opciones)
    finally:
        servicios.pedir = sim.pedir


def textos(d):
    return ' '.join(i.mensaje for i in d.incidencias)


# 1. La referencia escrita de cualquier forma
def escrita(rc, esperada):
    def prueba():
        d = servicios.descargar(rc)
        return d.correcta and d.rc == esperada, resumen(d)
    return prueba


caso("RC normal: parcela, colindantes y construcciones", escrita(RC, RC))
caso("en minúsculas, con espacios y guiones", escrita(' 1907401-vk4810h ', RC))
caso("de un inmueble (18 caracteres): baja su parcela", escrita('1907401VK4810H0001', RC))
caso("de un inmueble (20 caracteres): baja su parcela", escrita('1907401VK4810H0001WI', RC))
#Con los caracteres de control mal no se descarga: indican una errata en algún sitio de la referencia, también en la
#parte de la parcela, y se bajaría otra parcela sin avisar


def mala(rc, palabra):
    def prueba():
        d = servicios.descargar(rc)
        return (not d.correcta and any(i.nivel == ERROR for i in d.incidencias) and palabra.lower() in textos(d).lower()
                and 'huso' not in textos(d)), resumen(d)
    return prueba


caso("inmueble con los caracteres de control mal: no descarga y lo dice", mala('1907401VK4810H0001WX', 'control'))
caso("13 caracteres: lo dice", mala('1907401VK4810', 'caracteres'))
caso("texto cualquiera: lo dice", mala('hola mundo', ''))
caso("vacía: lo dice", mala('', ''))
caso("una RC que no existe: «no se ha encontrado», sin hablar del huso", mala('1907499VK4810H', 'no se ha encontrado'))


def huso_29():
    d = servicios.descargar(sim.RC_HUSO_29)
    return d.correcta and d.epsg == 25829, resumen(d)


def grande():
    d = servicios.descargar(sim.RC_GRANDE)
    return d.correcta, resumen(d)


def isla():
    d = servicios.descargar('1907408VK4810H')
    return d.correcta and not (d.colindantes and d.colindantes.elementos), resumen(d)


def navarra():
    d = servicios.descargar('201-4-112')
    return d.correcta and d.territorio == 'Navarra', resumen(d)


caso("parcela del huso 29: se pide en su huso", huso_29)
caso("parcela de 1,2 km: entorno sin pasarse del límite del servicio", grande)
caso("parcela rodeada de calles: sin colindantes, sin error", isla)
caso("Navarra con el formato 201-4-112: su catastro", navarra)


# País Vasco (AU-59): catastros de las diputaciones forales, solo para descargar y ver
def vasca(rc, territorio, local_id, colindantes):
    def prueba():
        d = servicios.descargar(rc)
        ids = [e.local_id for e in d.colindantes.elementos] if d.colindantes else []
        edificios = [e.local_id for e in d.construcciones.elementos] if d.construcciones else []
        ok = (d.correcta and d.territorio == territorio and d.rc == local_id and d.epsg == 25830
              and sorted(ids) == sorted(colindantes) and edificios == ['E1']  #Solo el edificio que cae dentro
              and any(i.codigo == 'FORAL-VASCO' and 'no sirve' in i.mensaje for i in d.incidencias)
              and 'Diputación Foral' in d.atribucion() and 'CC BY' in d.atribucion()
              and not any(i.nivel == ERROR for i in d.incidencias))  #Su gml:Polygon no es un error al solo ver
        return ok, (resumen(d), ids, edificios, d.atribucion())
    return prueba


caso("Bizkaia (48.020.1619.01003): su diputación, colindantes y el edificio de dentro",
     vasca(sim.BIZKAIA, 'Bizkaia', sim.BIZKAIA, ['48.020.1619.01004']))
caso("Gipuzkoa (069-8296630-1): cada parcela una vez (el servicio las repite con otro sufijo)",
     vasca(sim.GIPUZKOA, 'Gipuzkoa', sim.GIPUZKOA, ['069-8296631-1']))
caso("Álava con el namespace (ES.AFA.CP.59600922)", vasca('ES.AFA.CP.' + sim.ALAVA, 'Álava/Araba', sim.ALAVA, ['59600923']))


def vasca_no_existe():
    d = servicios.descargar('48.020.1619.09999')
    return not d.correcta and 'No se ha encontrado' in textos(d) and 'Diputación Foral' in textos(d), resumen(d)


def vasca_caida():
    sim.VASCO_CAIDO.add('Bizkaia')
    try:
        d = servicios.descargar(sim.BIZKAIA)
    finally:
        sim.VASCO_CAIDO.clear()
    return not d.correcta and 'No se ha podido descargar' in textos(d), resumen(d)


def formatos():
    """Lo vasco no se confunde con la DGC ni con Navarra, ni al revés («48.020.1619.01003» sin puntos parece rústica)."""
    vistos = {t: servicios.vasco(t) for t in ('48.020.1619.01003', ' 069-8296630-28223 ', 'es.bfa.cp.48.020.1619.01003',
                                               RC, '201-4-112', '201040112', '48020A01900003', '59600922')}
    esperado = {'48.020.1619.01003': ('Bizkaia', '48.020.1619.01003'),
                ' 069-8296630-28223 ': ('Gipuzkoa', '069-8296630-28223'),
                'es.bfa.cp.48.020.1619.01003': ('Bizkaia', '48.020.1619.01003'),
                RC: None, '201-4-112': None, '201040112': None, '48020A01900003': None, '59600922': None}
    return vistos == esperado, vistos


def clic_vasco():
    from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform
    transformacion = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:25830'),
                                            QgsCoordinateReferenceSystem('EPSG:4258'), QgsProject.instance())
    x, y = sim.VASCO_CENTROS['Bizkaia']
    dentro = transformacion.transform(QgsPointXY(x + 10, y + 15))
    calle = transformacion.transform(QgsPointXY(x - 10, y - 10))  #Fuera de las parcelas sintéticas
    r = servicios.rc_en_punto(dentro.x(), dentro.y())
    d = servicios.descargar(r.rc) if r.rc else None
    vacio = servicios.rc_en_punto(calle.x(), calle.y())
    texto = ' '.join(i.mensaje for i in vacio.incidencias)
    ok = (r.rc == 'ES.BFA.CP.' + sim.BIZKAIA and d is not None and d.correcta and not vacio.rc
          and 'Tampoco hay ninguna en el catastro foral' in texto and 'consulte su catastro foral' not in texto)
    return ok, (r.rc, r.direccion, d and resumen(d), texto)


caso("País Vasco: un identificador que no existe lo dice", vasca_no_existe)
caso("País Vasco: el servicio de la diputación no responde", vasca_caida)
caso("formatos: Bizkaia, Gipuzkoa y con namespace; la DGC y Navarra siguen siendo suyas", formatos)
caso("País Vasco: clic en el mapa (su diputación) y clic en la calle (lo dice sin mandar a otro sitio)", clic_vasco)


# 2. El Catastro responde mal
def sin_red():
    d = con(lambda url: (b'', 'Host ovc.catastro.meh.es not found (simulado)'))
    return not d.correcta and 'No se ha podido descargar' in textos(d), resumen(d)


def mantenimiento():
    d = con(lambda url: (b'', servicios.mantenimiento(PAGINA_MANTENIMIENTO)))
    return not d.correcta and '19.00' in textos(d), resumen(d)


def html():
    d = con(lambda url: (b'<html><body>Error 500</body></html>', ''))
    return not d.correcta and 'inesperada' in textos(d), resumen(d)


def vacia():
    d = con(lambda url: (b'', ''))
    return not d.correcta and bool(d.incidencias), resumen(d)


def construcciones_caidas():
    d = con(lambda url: (b'', 'Connection reset (simulado)') if 'wfsBU' in url else sim.pedir(url))
    return d.correcta and d.construcciones is None and 'edificios' in textos(d).lower(), resumen(d)


def colindantes_caidas():
    d = con(lambda url: (b'', 'Connection reset (simulado)') if 'bbox' in url.lower() or 'neighbour' in url.lower()
            else sim.pedir(url))
    return d.parcela is not None and bool(d.incidencias), resumen(d)


def ficha_caida():
    sim.DNPRC_CAIDO = True
    try:
        d = servicios.descargar(RC)
    finally:
        sim.DNPRC_CAIDO = False
    return d.correcta, resumen(d)


def cancelada():
    d = con(lambda url: (b'', servicios.CANCELADO))
    return not d.correcta, resumen(d)


def geometria_vacia():
    vacia_gml = (b'<?xml version="1.0" encoding="UTF-8"?><wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" '
                 b'numberMatched="0" numberReturned="0"/>')
    d = con(lambda url: (vacia_gml, '') if 'GetParcel' in url and 'Neighbour' not in url else sim.pedir(url))
    return not d.correcta and 'No se ha encontrado' in textos(d), resumen(d)


caso("sin internet: no se ha podido descargar", sin_red)
caso("Sede en mantenimiento: con el horario", mantenimiento)
caso("página HTML en lugar de datos: respuesta inesperada", html)
caso("respuesta vacía: lo dice", vacia)
caso("se caen solo las construcciones: parcela sí, aviso de edificios", construcciones_caidas)
caso("se caen solo las colindantes: parcela sí, con aviso", colindantes_caidas)
caso("se cae la consulta de datos: se descarga igual", ficha_caida)
caso("cancelada: no da una parcela a medias", cancelada)
caso("el servicio no devuelve la parcela: «no se ha encontrado»", geometria_vacia)


# 3. La pestaña
def pestana():
    dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
    pes = dw.pestanaDescargar
    pes.fondo.setChecked(False)
    proyecto = QgsProject.instance()
    raiz = proyecto.layerTreeRoot()
    #Enter con la casilla vacía o mal: no hace nada (el botón está desactivado), sin fallar
    pes.rc.setText('')
    vacia_ok = pes.descargar(segundo_plano=False) is None and not raiz.findGroups()
    pes.rc.setText('1907401VK48')
    mala_ok = not pes.descargarBoton.isEnabled() and pes.descargar(segundo_plano=False) is None
    #Descarga, el usuario borra el grupo a mano y vuelve a descargar
    pes.rc.setText(RC)
    pes.descargar(segundo_plano=False)
    grupo = raiz.findGroup(f'Catastro {RC}')
    proyecto.removeMapLayers(grupo.findLayerIds())
    raiz.removeChildNode(grupo)
    capas = pes.descargar(segundo_plano=False)
    otra_vez = capas is not None and raiz.findGroup(f'Catastro {RC}') is not None
    #Varias descargas: todas dentro de «Descargas del Catastro», la última arriba y abierta, las demás plegadas (U-06)
    from catastral_gml_tools.gui import pestana_descargar as pd
    pes.rc.setText(sim.NAVARRA)
    pes.descargar(segundo_plano=False)
    contenedor = raiz.findGroup(pd.GRUPO_DESCARGAS)
    hijos = contenedor.children() if contenedor else []
    juntas = (len([n for n in raiz.children() if n.name().startswith('Catastro ')]) == 0 and len(hijos) >= 2
              and hijos[0].name() == f'Catastro {sim.NAVARRA}' and hijos[0].isExpanded()
              and not any(h.isExpanded() for h in hijos[1:]))
    #País Vasco: se reconoce al escribir, se descarga solo para ver (sin pasar a Parcela) y Parcela no crea su GML
    pes.rc.setText(sim.BIZKAIA)
    reconocida = 'Bizkaia' in pes.comprobacion.text() and pes.descargarBoton.isEnabled()
    dw.messageBar.clearWidgets()
    vascas = pes.descargar(segundo_plano=False)
    barra_vasca = ' '.join(e.text() for i in dw.messageBar.items() for e in i.findChildren(QLabel))
    from catastral_gml_tools.gui.pestana_parcela import PROPIEDAD_TERRITORIO
    marcada = vascas is not None and vascas['parcela'].customProperty(PROPIEDAD_TERRITORIO) == 'Bizkaia'
    licencia = vascas is not None and 'creativecommons.org' in vascas['parcela'].metadata().abstract()
    dw.pestanaParcela.capaCombo.setLayer(vascas['parcela'] if vascas else None)
    dw.messageBar.clearWidgets()
    dw.pestanaParcela.crear_gml()
    sin_gml = 'catastro propio' in ' '.join([i.text() for i in dw.messageBar.items()]
                                            + [e.text() for i in dw.messageBar.items() for e in i.findChildren(QLabel)])
    vasco_ok = (reconocida and marcada and licencia and sin_gml and 'de Bizkaia' in barra_vasca
                and 'Ir a Parcela' not in barra_vasca)
    #Sin internet desde la pestaña: aviso en el panel y el botón vuelve a estar disponible
    servicios.pedir = lambda url: (b'', 'Host not found (simulado)')
    dw.messageBar.clearWidgets()
    pes.descargar(segundo_plano=False)
    servicios.pedir = sim.pedir
    barra = ' '.join([i.text() for i in dw.messageBar.items()] + [e.text() for i in dw.messageBar.items()
                                                                   for e in i.findChildren(QLabel)])
    sin_red_ok = 'No se ha podido descargar' in barra and pes.descargarBoton.isEnabled()
    #Clic en el mapa en el mar (sin referencia en ese punto): aviso, sin fallar
    dw.messageBar.clearWidgets()
    pes.punto_elegido(QgsPointXY(3.5, 39.0), segundo_plano=False)
    mar = bool(dw.messageBar.items())
    #Descarga en segundo plano y se cierra el plugin a mitad: se cancela sin fallar
    pes.descargar()
    tarea = pes.tarea
    dw.cleanup()
    cerrada = tarea is None or tarea.feedback.isCanceled() or pes.tarea is None
    dw.deleteLater()
    proyecto.removeAllMapLayers()
    raiz.removeAllChildren()
    ok = vacia_ok and mala_ok and otra_vez and sin_red_ok and mar and cerrada and vasco_ok and juntas
    return ok, (vacia_ok, mala_ok, otra_vez, sin_red_ok, mar, cerrada, vasco_ok, juntas, reconocida, marcada, licencia, sin_gml,
                barra_vasca[:200], barra[:200])


caso("pestaña: vacía, mal escrita, grupo borrado, descargas juntas, País Vasco solo para ver, sin red, clic en el mar y cerrar a mitad",
     pestana)

servicios.pedir = original
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
resultados["ninguna ventana emergente"] = not ventanas

print("=" * 60)
print("QGIS", Qgis.version(), "· Descargar: batería de casos")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, d in detalles.items():
    print("Detalles", nombre, ":", d)
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
