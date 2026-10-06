"""
Prueba rápida del esqueleto: el plugin se carga y se descarga sin errores, el panel se abre con sus pestañas,
iconos, aviso legal, ayuda y avisos dentro del panel. Sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py smoke_test.py)
"""
import configparser
import os

import qgis.utils
from qgis.core import Qgis
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

qgis.utils.reloadPlugin('catastral_gml_tools')
import catastral_gml_tools  # noqa: E402
import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import info  # noqa: E402

ventanas = []  #Si algo abriera una ventana de aviso, la prueba lo detectaría
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))

iface = qgis.utils.iface
RAIZ = os.path.dirname(dock_module.__file__)
metadata = configparser.ConfigParser(interpolation=None)
metadata.read(os.path.join(RAIZ, 'metadata.txt'), encoding='utf-8')
general = metadata['general']
with open(info.ruta('LICENSE'), encoding='utf-8') as f:
    licencia = f.read(400)


def _texto(barra):
    item = barra.currentItem()
    if item is None:
        return None
    etiquetas = [e.text() for e in item.findChildren(QLabel) if e.text()]
    return item.text() or (etiquetas[0] if etiquetas else '')


# 1. Carga del plugin como lo hace QGIS
plugin = catastral_gml_tools.classFactory(iface)
plugin.initGui()
accion_ok = plugin.action is not None and not plugin.action.icon().isNull() and plugin.action.isCheckable()

# 2. Abrir el panel desde el botón
plugin.action.setChecked(True)
plugin.toggle(True)
dw = plugin.dockwidget
nombres = [dw.tabWidget.widget(i).objectName() for i in range(dw.tabWidget.count())]
titulos = [dw.tabWidget.tabText(i) for i in range(dw.tabWidget.count())]
iconos = all(not dw.tabWidget.tabIcon(i).isNull() for i in range(dw.tabWidget.count()))
iconos_vacios = [dw.tabWidget.tabText(i) for i in range(dw.tabWidget.count()) if dw.tabWidget.tabIcon(i).isNull()]
titulo_ventana = dw.windowTitle()

# 3. Aviso legal, fuente y ayuda local
legal = 'no oficial' in dw.legalLabel.text() and 'Sede Electrónica del Catastro' in dw.legalLabel.text()
fuente = 'Dirección General del Catastro' in dw.sourceLabel.text()
ayuda = dw.help_url().isLocalFile() and os.path.isfile(dw.help_url().toLocalFile())
with open(info.ruta('help', 'index.html'), encoding='utf-8') as f:
    html = f.read()
ayuda_aviso = 'no oficial' in html and 'Navarra' in html and 'Dirección General del Catastro' in html
boton_ayuda = not dw.helpButton.icon().isNull() and dw.helpButton.parent() is dw.dockWidgetContents

# 4. Avisos dentro del panel, sin ventanas
dw.warn("Prueba de aviso")
aviso_corto = _texto(dw.messageBar) == "Prueba de aviso" and dw.messageBar.currentItem().level() == Qgis.MessageLevel.Warning
dw.warn("Primera línea\n\n- detalle 1\n- detalle 2")
aviso_largo = _texto(dw.messageBar) == "Primera línea" and dw.messageBar.currentItem().duration() == 0

# 5. Territorios forales
forales = (info.territorio_foral('31') == 'Navarra' and info.territorio_foral(1) == 'Álava/Araba'
           and info.territorio_foral('20') == 'Gipuzkoa' and info.territorio_foral('48') == 'Bizkaia'
           and info.territorio_foral('29') is None)

# 6. Ocultar con el botón y descargar el plugin
plugin.toggle(False)
oculto = not dw.isVisible()
plugin.unload()
descargado = plugin.dockwidget is None and plugin.action is None and plugin.toolbar is None

for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)

checks = {
    "metadata: supportsQt6, 3.34+, GPL y versión": general.get('supportsQt6') == 'True'
        and general.get('qgisMinimumVersion') == '3.34' and info.version() == general.get('version'),
    "LICENSE es la GPL v2": 'GNU GENERAL PUBLIC LICENSE' in licencia and 'Version 2' in licencia,
    "botón con icono propio": accion_ok,
    "seis pestañas en orden": titulos == ['Parcela', 'Edificio', 'Validar', 'Descargar', 'Dividir', 'Utilidades']
        and nombres[0] == 'tabParcela',
    "iconos nativos en todas las pestañas": iconos,
    "título con nombre y versión": titulo_ventana == f"Catastral GML Tools {general.get('version')}",
    "aviso legal visible": legal,
    "fuente de los datos citada": fuente,
    "ayuda local con aviso legal y territorios forales": ayuda and ayuda_aviso and boton_ayuda,
    "aviso corto en la barra del panel": aviso_corto,
    "aviso largo: primera línea y el resto con «Más»": aviso_largo,
    "ninguna ventana emergente": not ventanas,
    "territorios forales detectados": forales,
    "el botón oculta el panel": oculto,
    "descarga limpia del plugin": descargado,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· esqueleto del plugin")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'titulos': titulos, 'iconos_vacios': iconos_vacios, 'titulo': titulo_ventana, 'ventanas': ventanas})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
