"""
Prueba de la pestaña Descargar con los servicios simulados (tests/simulador_catastro.py), sin internet:
comprobación de la referencia al escribirla, descarga en un grupo «Catastro <RC>» con estilo y la fuente en los
metadatos, sustitución del grupo al repetir, errores en la barra del panel y elección de la parcela con un clic en el
mapa (la herramienta anterior del mapa se devuelve).

Uso: tools\\probar.bat (o tools\\run_tests.py descargar_ui_test.py)
"""
import importlib.util
import os

import qgis.utils
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
integrada = dw.tabDescargarPendiente.isHidden() and pes.parent() is dw.tabDescargar
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
          and capas['colindantes'].labeling().settings().fieldName == 'label'
          and not capas['construcciones'].labelsEnabled() and capas['entorno'].labeling().settings().fieldName == 'label'
          and parcela.featureCount() == 1 and capas['colindantes'].featureCount() == 1 and capas['entorno'].featureCount() == 1
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

# 6. Mapa de fondo con el proyecto vacío: con conexión, Catastro y PNOA en un grupo al final y el proyecto en
# EPSG:25830; sin conexión, nada (ni grupo vacío). Nunca se duplica.
proyecto.removeMapLayers([c.id() for c in proyecto.mapLayers().values()])
raiz.removeAllChildren()
nuevas = fondo.asegurar(iface)
if nuevas:
    modo_fondo = "con conexión"
    fondo_ok = (len(nuevas) == 2 and raiz.children()[-1].name() == fondo.GRUPO
                and proyecto.crs().authid() == 'EPSG:25830'
                and any('Dirección General del Catastro' in c.metadata().rights()[0] for c in nuevas)
                and any('Instituto Geográfico Nacional' in c.metadata().rights()[0] for c in nuevas)
                and fondo.asegurar(iface) == [] and len(fondo.capas_fondo()) == 2
                and not raiz.findGroup(fondo.GRUPO).isExpanded()
                and not any(raiz.findLayer(c.id()).isExpanded() for c in nuevas))
else:
    modo_fondo = "sin conexión"
    fondo_ok = raiz.findGroup(fondo.GRUPO) is None and not fondo.capas_fondo()

pd.servicios.pedir = original
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
dw.deleteLater()

checks = {
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
    "clic sin parcela y cambio de herramienta": herramienta,
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
