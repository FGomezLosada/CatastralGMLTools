"""
Prueba de la pestaña Descargar con los servicios simulados (tests/simulador_catastro.py), sin internet:
comprobación de la referencia al escribirla, descarga en un grupo «Catastro <RC>» con estilo y la fuente en los
metadatos, sustitución del grupo al repetir, errores en la barra del panel y elección de la parcela con un clic en el
mapa (la herramienta anterior del mapa se devuelve).

Uso: tools\\probar.bat (o tools\\run_tests.py descargar_ui_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import importlib.util
import os

import qgis.utils
from qgis.PyQt import sip
from qgis.core import Qgis, QgsPointXY, QgsProject
from qgis.gui import QgsMapToolPan
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

qgis.utils.reloadPlugin('catastral_gml_tools')
import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core.info import RAIZ  # noqa: E402
from catastral_gml_tools.gui import fondo  # noqa: E402
from catastral_gml_tools.gui import pestana_descargar as pd  # noqa: E402

spec = importlib.util.spec_from_file_location('simulador_catastro', os.path.join(RAIZ, 'tests', 'simulador_catastro.py'))
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)
original = sim.instalar()

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))

iface = qgis.utils.iface
lienzo = iface.mapCanvas()
proyecto = QgsProject.instance()
raiz = proyecto.layerTreeRoot()
dw = dock_module.CatastralGMLToolsDockWidget(iface)
pes = dw.pestanaDescargar


def textos_barra():
    textos = []
    for item in dw.messageBar.items():
        textos.append(item.text())
        textos += [e.text() for e in item.findChildren(QLabel)]
    return ' | '.join(textos)


# 1. La pestaña sustituye al «Disponible en próximas versiones» y comprueba la referencia al escribirla
integrada = dw.tabDescargarPendiente.isHidden() and dw.tabDescargar.isAncestorOf(pes)
vacia = not pes.descargarBoton.isEnabled()
pes.rc.setText('1907401VK48')
corta = not pes.descargarBoton.isEnabled() and '14, 18 o 20' in pes.comprobacion.text()
pes.rc.setText('31001A00100001')
foral = not pes.descargarBoton.isEnabled() and 'Navarra' in pes.comprobacion.text()
pes.rc.setText('29071A00700123')
rustica = (pes.descargarBoton.isEnabled() and 'Parcela rústica de Málaga · municipio 071, polígono 7, parcela 123'
           in pes.comprobacion.text())
pes.rc.setText('9872023VH5797S0001')
inmueble = 'se descarga su parcela 9872023VH5797S (caracteres de control: WX)' in pes.comprobacion.text()
pes.rc.setText(' 1907401-VK4810H ')
valida = pes.descargarBoton.isEnabled() and 'Parcela urbana. Pulse Descargar' in pes.comprobacion.text()
comprobacion = integrada and vacia and corta and foral and rustica and inmueble and valida

# 2. Descarga: grupo, capas en orden, estilo y fuente (sin fondo: se prueba aparte, depende de la conexión)
sin_capa_parcela = dw.pestanaParcela.capa() is None  #La pestaña Parcela puede quedarse sin capa
pes.fondo.setChecked(False)
capas = pes.descargar(segundo_plano=False)
grupo = raiz.findGroup(f'Catastro {sim.RC}')
nombres = [n.name() for n in grupo.children()] if grupo else []
orden = nombres == ['Construcciones', f'Parcela {sim.RC}', 'Colindantes', 'Entorno'] and raiz.children()[0] is grupo
parcela = capas['parcela'] if capas else None
fuente = (parcela is not None and all('Dirección General del Catastro' in c.metadata().rights()[0]
                                      and 'descargado el' in c.customProperty(pd.PROPIEDAD_FUENTE) for c in capas.values())
          and 'no es cartografía oficial' in parcela.metadata().abstract())
estilo = (parcela is not None and parcela.renderer().type() == 'categorizedSymbol' and parcela.labelsEnabled()
          and '"label"' in capas['colindantes'].labeling().settings().fieldName
          and not capas['construcciones'].labelsEnabled() and '"label"' in capas['entorno'].labeling().settings().fieldName
          and parcela.featureCount() == 1 and capas['colindantes'].featureCount() == 2
          and len(capas['colindantes'].renderer().categories()) == 2 and capas['entorno'].featureCount() == 1
          and capas['construcciones'].featureCount() == 2 and parcela.crs().authid() == 'EPSG:25830')
barra = f'Descargada la parcela {sim.RC}' in textos_barra() and '600 m²' in pes.resumen.text()
# La pestaña Parcela pasa a trabajar con la parcela descargada (con su RC como SDGC)
pp = dw.pestanaParcela
entrega = (sin_capa_parcela and pp.capa() is parcela and len(pp.filas) == 1 and pp.filas[0].local_id == sim.RC
           and pp.filas[0].namespace == 'SDGC')
detalle_entrega = [sin_capa_parcela, pp.capa() is parcela, [(f.local_id, f.namespace) for f in pp.filas],
                   pp.campoId.currentField()]
pes.ir_a_parcela()
entrega = entrega and dw.tabWidget.currentWidget() is dw.tabParcela

# 3. Repetir la descarga sustituye el grupo (no se duplican capas); sin opciones, solo la parcela
n_capas = len(proyecto.mapLayers())
pes.colindantes.setChecked(False)
pes.construcciones.setChecked(False)
pes.descargar(segundo_plano=False)
grupos = [g for g in raiz.findGroups() if g.name() == f'Catastro {sim.RC}']
repetida = (len(grupos) == 1 and [n.name() for n in grupos[0].children()] == [f'Parcela {sim.RC}']
            and len(proyecto.mapLayers()) == n_capas - 3)
#Con la capa de la parcela en edición, volver a descargar no la borra: la nueva va en «Catastro <RC> (2)» (AU-10)
editada = proyecto.mapLayersByName(f'Parcela {sim.RC}')[0]
editada.startEditing()
pes.descargar(segundo_plano=False)
conserva = (raiz.findGroup(f'Catastro {sim.RC}') is not None and raiz.findGroup(f'Catastro {sim.RC} (2)') is not None
            and not sip.isdeleted(editada) and editada.isEditable())
editada.rollBack()
proyecto.removeMapLayers(raiz.findGroup(f'Catastro {sim.RC} (2)').findLayerIds())
raiz.removeChildNode(raiz.findGroup(f'Catastro {sim.RC} (2)'))
pes.colindantes.setChecked(True)
pes.construcciones.setChecked(True)

# 3b. Parcela rodeada de calles: sin colindantes es una nota (verde), no un aviso
pes.rc.setText('1907408VK4810H')
dw.messageBar.clearWidgets()
pes.descargar(segundo_plano=False)
isla = ('no tiene parcelas colindantes' in pes.resumen.text() and 'aviso' not in textos_barra()
        and dw.messageBar.currentItem().level() == Qgis.MessageLevel.Success)

# 4. Errores: parcela inexistente y sin red, en la barra del panel y sin grupo nuevo
n_grupos = len(raiz.findGroups())
pes.rc.setText('1907499VK4810H')
pes.descargar(segundo_plano=False)
inexistente = 'No se ha encontrado la parcela 1907499VK4810H' in textos_barra() and len(raiz.findGroups()) == n_grupos
pes.rc.setText(sim.RC_SIN_RED)
pes.descargar(segundo_plano=False)
sin_red = 'No se ha podido descargar' in textos_barra() and len(raiz.findGroups()) == n_grupos
errores = inexistente and sin_red and '✖' in pes.resumen.text() and pes.descargarBoton.isEnabled()

# 5. Elegir la parcela con un clic en el mapa (el mapa de las pruebas está en EPSG:4326)
pan = QgsMapToolPan(lienzo)
lienzo.setMapTool(pan)
pes.rc.clear()
pes.mapaBoton.setChecked(True)
activa = lienzo.mapTool() is pes.herramienta and pes.herramienta is not None
proyecto.removeMapLayers([c.id() for c in proyecto.mapLayers().values()])
raiz.removeAllChildren()
sim.peticiones.clear()
pes.punto_elegido(QgsPointXY(-3.7085, 40.4207), segundo_plano=False)
clic = (activa and pes.rc.text() == sim.RC and 'CoorX=-3.708500' in sim.peticiones[0]
        and raiz.findGroup(f'Catastro {sim.RC}') is not None and 'CL INVENTADA' in pes.rc.toolTip()
        and lienzo.mapTool() is pan and not pes.mapaBoton.isChecked())

# Clic donde no hay parcela: aviso con la nota foral y la casilla sin tocar
pes.mapaBoton.setChecked(True)
pes.punto_elegido(QgsPointXY(3.0, 40.0), segundo_plano=False)
sin_parcela = ('no hay referencia disponible' in textos_barra().lower()
               and 'Navarra' in textos_barra() and pes.rc.text() == sim.RC and lienzo.mapTool() is pan)

# Otra herramienta sustituye a la nuestra: el botón se desmarca; al cerrar el plugin se devuelve la anterior
pes.mapaBoton.setChecked(True)
lienzo.setMapTool(pan)
desmarcado = not pes.mapaBoton.isChecked()
pes.mapaBoton.setChecked(True)
dw.cleanup()
devuelta = lienzo.mapTool() is pan
herramienta = sin_parcela and desmarcado and devuelta
#Cerrar el panel con la × suelta «Elegir en el mapa» (B6)
pes.mapaBoton.setChecked(True)
dw.visibilidad_cambiada(False)
herramienta = herramienta and lienzo.mapTool() is pan and not pes.mapaBoton.isChecked()

# 5a. Robustez de las tareas (AU-38, AU-44): motivo real del fallo, cancelación y respuesta que no es del WFS
from qgis.core import QgsFeedback  # noqa: E402

dw.messageBar.clearWidgets()
_rota = pd.TareaCatastro("prueba", lambda rc: {}[rc], ('X',), {}, pes, 'descargada')  #Lanza KeyError
_rota.run()
_rota.finished(True)
motivo = 'No se ha podido descargar la parcela' in textos_barra() and "'X'" in textos_barra()
_cancelado = QgsFeedback()
_cancelado.cancel()
with pd.servicios.en_tarea(_cancelado):
    _datos, _error = original('https://ovc.catastro.meh.es/no-se-pide')
_lento = QgsFeedback()
with pd.servicios.en_tarea(_lento, tiempo_maximo=-1):
    _datos2, _error2 = original('https://ovc.catastro.meh.es/no-se-pide')
cancelable = _error == pd.servicios.CANCELADO and 'tarda demasiado' in _error2 and _datos == _datos2 == b''
pd.servicios.pedir = lambda url: (b'<html><body>Servicio en mantenimiento</body></html>', '')
_, _inc_html = pd.servicios.consultar_wfs(pd.servicios.url_parcela(sim.RC), 'la parcela')
pd.servicios.pedir = sim.pedir
mantenimiento = [i.codigo for i in _inc_html] == ['WFS-RESPUESTA'] and 'mantenimiento' in _inc_html[0].mensaje
tareas = motivo and cancelable and mantenimiento

# 5b. Navarra: se descarga del Gobierno de Navarra, no pasa a la pestaña Parcela y no deja crear el GML de la Sede
pp = dw.pestanaParcela
id_antes = pp.capa().id() if pp.capa() is not None else None
pes.rc.setText('201-4-112')
texto_nav = 'Parcela de Navarra' in pes.comprobacion.text() and pes.descargarBoton.isEnabled()
dw.messageBar.clearWidgets()
capas_nav = pes.descargar(segundo_plano=False) or {}
parcela_nav = capas_nav.get('parcela')
navarra_ui = (texto_nav and parcela_nav is not None and raiz.findGroup('Catastro 201040112') is not None
              and parcela_nav.customProperty('catastral_gml_tools/territorio') == 'Navarra'
              and 'Gobierno de Navarra' in parcela_nav.metadata().rights()[0]
              and 'Servicio proporcionado por el Gobierno de Navarra' in parcela_nav.metadata().abstract()
              and (pp.capa().id() if pp.capa() is not None else None) == id_antes
              and 'de Navarra' in textos_barra())
pp.capaCombo.setLayer(parcela_nav)
dw.messageBar.clearWidgets()
pp.crear_gml()
navarra_ui = navarra_ui and 'catastro propio' in textos_barra()

# 6. Mapa de fondo con el proyecto vacío: con conexión, Catastro (DGC y Navarra) y PNOA en un grupo al final y el proyecto en
# EPSG:25830; sin conexión, nada (ni grupo vacío). Nunca se duplica. Un servicio caído o en mantenimiento (el Catastro lo
# estuvo el 14/10/2026 de 15:15 a 19:00) no se añade, pero queda apuntado con su motivo
proyecto.removeMapLayers([c.id() for c in proyecto.mapLayers().values()])
raiz.removeAllChildren()
_orden = [c[0] for c in fondo.CAPAS]
_fuentes = {c[0]: c[5] for c in fondo.CAPAS}
nuevas = fondo.asegurar(iface)
_nombres = [c.name() for c in nuevas]
if nuevas:
    modo_fondo = "con conexión" if len(nuevas) == len(fondo.CAPAS) else f"con conexión, sin {len(fondo.CAPAS) - len(nuevas)} servicio(s)"
    fondo_ok = (raiz.children()[-1].name() == fondo.GRUPO
                and [n.name() for n in raiz.children()[-1].children()] == [n for n in _orden if n in _nombres]
                and proyecto.crs().authid() == 'EPSG:25830'
                and all(c.metadata().rights()[0] == _fuentes[c.name()] for c in nuevas)
                and fondo.asegurar(iface) == [] and len(fondo.capas_fondo()) == len(nuevas)
                and sorted(n for n, _ in fondo.caidos()) == sorted(n for n in _orden if n not in _nombres)
                and not raiz.findGroup(fondo.GRUPO).isExpanded()
                and not any(raiz.findLayer(c.id()).isExpanded() for c in nuevas))
    #Proyecto con el fondo de una versión anterior (sin Navarra): se añade solo la que falta, en su sitio
    if 'Catastro de Navarra (WMS)' in _nombres:
        proyecto.removeMapLayer([c for c in nuevas if 'Navarra' in c.name()][0].id())
        falta = fondo.asegurar(iface)
        fondo_ok = (fondo_ok and [c.name() for c in falta] == ['Catastro de Navarra (WMS)']
                    and [n.name() for n in raiz.findGroup(fondo.GRUPO).children()] == [n for n in _orden if n in _nombres])
else:
    modo_fondo = "sin conexión"
    fondo_ok = raiz.findGroup(fondo.GRUPO) is None and not fondo.capas_fondo()

# 6b. Servicio del fondo en mantenimiento: no se intenta (QGIS no se bloquea), la casilla sigue marcada y una línea fija
# dice qué capa falta, por qué y que se volverá a probar (si no, quien empieza buscaría la capa a mano); pasado el plazo
# o con «Reintentar ahora» se vuelve a probar
_estado = (dict(fondo.ESTADO), dict(fondo.MOTIVO), dict(fondo.PROBADO))
for _n in _orden:
    fondo.apuntar(_n, False, "está en mantenimiento («Tiempo estimado desde las 15.15H hasta las 19.00.H»)"
                  if _n == 'Catastro (WMS)' else "no responde (sin conexión o servicio caído)")
proyecto.removeMapLayers([c.id() for c in proyecto.mapLayers().values()])
raiz.removeAllChildren()
pes.fondo.setChecked(True)
dw.messageBar.clearWidgets()
caido = not fondo.pendientes() and [n for n, _ in fondo.caidos()] == _orden and fondo.asegurar(iface) == []
pes.fondo_comprobado()
_linea = pes.estadoFondo.text()
fondo_caido = (caido and pes.fondo.isChecked() and not pes.estadoFondo.isHidden() and '«Catastro (WMS)»' in _linea
               and 'mantenimiento' in _linea and '19.00' in _linea and 'Reintentar ahora' in _linea
               and 'no se ha añadido' in textos_barra())
fondo.PROBADO['Catastro (WMS)'] -= fondo.REINTENTO + 1  #Pasado el plazo, se vuelve a probar
fondo_caido = fondo_caido and fondo.pendientes() == ['Catastro (WMS)']
pes.fondo.setChecked(False)  #Sin la casilla no se pide nada y la línea se oculta
fondo_caido = fondo_caido and pes.estadoFondo.isHidden()
pes.reintentar_fondo()
fondo_caido = fondo_caido and 'Catastro (WMS)' not in fondo.ESTADO and pes.tarea_fondo is None
for _d, _v in zip((fondo.ESTADO, fondo.MOTIVO, fondo.PROBADO), _estado):
    _d.clear()
    _d.update(_v)
pes.fondo.setChecked(True)

pd.servicios.pedir = original
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
dw.deleteLater()

checks = {
    "volver a descargar no borra capas editadas": conserva,
    "comprueba y explica la referencia (corta, foral, rústica, inmueble y urbana)": comprobacion,
    "grupo «Catastro <RC>» con construcciones, parcela y colindantes": orden,
    "fuente y fecha en los metadatos de cada capa": fuente,
    "estilo, etiquetas y huso de las capas": estilo,
    "resultado en la barra del panel y resumen": barra,
    "la parcela descargada pasa a la pestaña Parcela (que puede quedar sin capa)": entrega,
    "repetir sustituye el grupo; sin opciones solo la parcela": repetida,
    "sin colindantes: nota en verde, no aviso": isla,
    "errores en la barra: parcela inexistente y sin red": errores,
    "clic en el mapa: consulta la RC, descarga y devuelve la herramienta": clic,
    "clic sin parcela, cambio de herramienta y panel cerrado": herramienta,
    "tareas: motivo del fallo, cancelación, tiempo máximo y servicio en mantenimiento": tareas,
    "mapa de fondo con un servicio en mantenimiento: no se intenta, se dice cuál y por qué, se reintenta": fondo_caido,
    "Navarra: descarga del Gobierno de Navarra y sin GML de la Sede": navarra_ui,
    f"mapa de fondo ({modo_fondo})": fondo_ok,
    "ninguna ventana emergente": not ventanas,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· pestaña Descargar")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'nombres': nombres, 'barra': textos_barra(), 'resumen': pes.resumen.text(),
                        'peticiones': sim.peticiones, 'rc': pes.rc.text(),
                        'comprobacion': [integrada, vacia, corta, foral, rustica, inmueble, valida, pes.comprobacion.text()], 'repetida': repetida, 'entrega': detalle_entrega,
                        'clic': [activa, lienzo.mapTool(), pes.mapaBoton.isChecked()],
                        'herramienta': [sin_parcela, desmarcado, devuelta]})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
