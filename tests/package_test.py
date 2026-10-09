"""
Prueba del empaquetado: tools/package.py genera un ZIP con una sola carpeta catastral_gml_tools/ y solo los
ficheros del plugin (sin pruebas, documentación de desarrollo, .git ni __pycache__). Sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py package_test.py)
"""
import configparser
import importlib.util
import os
import zipfile

from qgis.core import Qgis

import catastral_gml_tools.core.info as info

RAIZ = info.RAIZ
spec = importlib.util.spec_from_file_location('package', os.path.join(RAIZ, 'tools', 'package.py'))
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)

metadata = configparser.ConfigParser(interpolation=None)
metadata.read(os.path.join(RAIZ, 'metadata.txt'), encoding='utf-8')
version = metadata['general']['version'].strip()

package.main()
destino = os.path.join(RAIZ, 'dist', f"catastral_gml_tools-{version}.zip")
with zipfile.ZipFile(destino) as z:
    nombres = z.namelist()
    metadata_zip = z.read('catastral_gml_tools/metadata.txt').decode('utf-8')

carpetas = {n.split('/')[0] for n in nombres}
prohibidos = [n for n in nombres if '/tests/' in n or '/docs/' in n or '/tools/' in n or '__pycache__' in n
              or '/.git' in n or n.endswith(('.pyc', '.zip'))]
necesarios = ['__init__.py', 'catastral_gml_tools.py', 'catastral_gml_tools_dockwidget.py',
              'catastral_gml_tools_dockwidget_base.ui', 'metadata.txt', 'icon.png', 'icon.svg', 'LICENSE',
              'README.md', 'CREDITS.md', 'core/__init__.py', 'core/info.py', 'gui/__init__.py', 'gui/pestana_parcela.py', 'gui/pestana_validar.py', 'gui/estilos.py', 'core/gml_lector.py', 'core/validador.py', 'core/esquemas.py', 'core/informe.py', 'core/servicios.py', 'gui/pestana_descargar.py', 'gui/fondo.py', 'core/comparacion.py', 'help/index.html']

# Los espaciadores de los .ui deben llevar sizeHint: sin él, el uic de PyQt6 (QGIS 4) genera una llamada
# QSpacerItem inválida y el panel no se abre (error visto en QGIS 4.2.2)
import xml.etree.ElementTree as ET  # noqa: E402

espaciadores_sin_tamano = []
for nombre_ui in [n for n in os.listdir(RAIZ) if n.endswith('.ui')]:
    for spacer in ET.parse(os.path.join(RAIZ, nombre_ui)).iter('spacer'):
        if not any(p.get('name') == 'sizeHint' for p in spacer.findall('property')):
            espaciadores_sin_tamano.append(f"{nombre_ui}:{spacer.get('name')}")

checks = {
    "espaciadores de los .ui con sizeHint (compatibles con QGIS 4)": not espaciadores_sin_tamano,
    "ZIP con el nombre y la versión": os.path.isfile(destino),
    "una sola carpeta catastral_gml_tools/": carpetas == {'catastral_gml_tools'},
    "contiene todos los ficheros del plugin": all(f"catastral_gml_tools/{n}" in nombres for n in necesarios),
    "sin pruebas, documentación de desarrollo ni cachés": not prohibidos,
    "metadata.txt dentro del ZIP": f"version={version}" in metadata_zip,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· empaquetado")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'carpetas': carpetas, 'prohibidos': prohibidos, 'espaciadores': espaciadores_sin_tamano, 'faltan':
                        [n for n in necesarios if f"catastral_gml_tools/{n}" not in nombres]})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
