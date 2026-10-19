r"""
Lanza las pruebas de tests/ cada una en un QGIS propio, SIN VENTANA: no toca el QGIS que tengas abierto,
las pruebas no se contaminan entre sí y, si una falla o se cierra, las demás siguen.

Uso (CMD, desde la carpeta del proyecto):
    "C:\Program Files\QGIS 3.40.13\bin\python-qgis-ltr.bat" tools\run_tests.py          (todas, QGIS 3.40)
    "C:\Program Files\QGIS 4.2.2\bin\python-qgis.bat" tools\run_tests.py                (todas, QGIS 4)
    ... tools\run_tests.py smoke_test.py                                                 (solo esa)

El resumen sale en pantalla y en tests/resultados_qgis<versión>.txt (p. ej. resultados_qgis3.40.txt). Usa la configuración de pruebas de QGIS, no la tuya
(favoritos, plantillas y configuraciones guardadas no se tocan).

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import datetime
import importlib.util
import os
import subprocess
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRUEBAS = ['smoke_test.py', 'package_test.py', 'refcat_test.py', 'geometria_test.py', 'gml_parcela_test.py', 'parcela_ui_test.py', 'gml_lector_test.py', 'validar_ui_test.py', 'validador_test.py', 'esquemas_test.py', 'informe_test.py', 'servicios_test.py', 'descargar_ui_test.py', 'comparacion_test.py', 'alteraciones_test.py', 'unir_test.py', 'union_test.py', 'gml_edificio_test.py', 'edificio_ui_test.py', 'robustez_test.py', 'division_test.py', 'panel_test.py', 'conversor_test.py', 'superficies_test.py', 'ajuste_test.py', 'comparar_gml_test.py', 'comparar_casos_test.py', 'validar_casos_test.py']
ESPERA = 600  #Segundos máximos por prueba
ESPERA_TRAZA = 150  #Segundos tras los que una prueba colgada guarda su traza y se cierra
ESPERA_ARRANQUE = 60  #Segundos máximos para que arranque QGIS en el proceso de la prueba
ARRANCADO = '[QGIS arrancado]'
REINTENTOS_ARRANQUE = 2
MODULO = 'catastral_gml_tools'  #Nombre con el que QGIS carga el plugin


def arrancar_qgis():
    """
    Como qgis.testing.start_app, pero con un nombre de aplicación propio de este proceso: QGIS guarda su caché (y el
    candado hstsstore.lock de la red) en una carpeta con ese nombre. Con el nombre común «QGIS-TEST», un proceso de
    prueba que se quedaba colgado al salir retenía el candado y todos los QGIS siguientes se colgaban al arrancar hasta
    reiniciar Windows (QGIS 4.2, 15/10/2026). La carpeta se borra al terminar (borrar_cache).
    """
    import qgis.testing
    from qgis.core import QgsApplication
    from qgis.PyQt.QtCore import QCoreApplication, Qt
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    QCoreApplication.setOrganizationName('QGIS')
    QCoreApplication.setOrganizationDomain('qgis.org')
    QCoreApplication.setApplicationName(f'QGIS-TEST-CGT-{os.getpid()}')
    os.environ['QGIS_CUSTOM_CONFIG_PATH'] = tempfile.mkdtemp('', 'QGIS-PythonTestConfigPath-')
    aplicacion = QgsApplication([os.fsencode(a) for a in sys.argv], True)
    aplicacion.initQgis()
    qgis.testing.QGISAPP = aplicacion  #start_app() (p. ej. desde qgis.testing.mocked) ya no crea otra
    return aplicacion


def borrar_cache():
    """Carpetas de este proceso: la de la caché de QGIS (con su nombre propio) y la del perfil temporal."""
    import shutil
    from qgis.PyQt.QtCore import QStandardPaths
    cache = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
    while cache and not os.path.basename(cache).startswith('QGIS-TEST-CGT-') and os.path.dirname(cache) != cache:
        cache = os.path.dirname(cache)  #Windows: …/QGIS/QGIS-TEST-CGT-n/cache; Linux: …/QGIS/QGIS-TEST-CGT-n
    for carpeta in (cache, os.environ.get('QGIS_CUSTOM_CONFIG_PATH', '')):
        if carpeta and ('QGIS-TEST-CGT-' in carpeta or 'QGIS-PythonTestConfigPath-' in carpeta):
            shutil.rmtree(carpeta, ignore_errors=True)


def ejecutar_una(prueba):
    """Se ejecuta en el proceso hijo: arranca QGIS sin ventana, carga el plugin desde esta carpeta y lanza la prueba."""
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    #Esquemas XSD en una carpeta común a todas las pruebas: se descargan una vez, no en cada prueba (cada una arranca con
    #un perfil de QGIS nuevo y bajaba ~80 esquemas por internet)
    os.environ.setdefault('CGT_ESQUEMAS', os.path.join(tempfile.gettempdir(), 'catastral_gml_tools_esquemas'))
    #Si la prueba se cuelga, a los ESPERA_TRAZA segundos se guarda dónde estaba cada hilo y se cierra (en vez de esperar
    #a que el padre la corte sin saber por qué; cuelgue esporádico de conversor_test en QGIS 4.2, 15/10/2026)
    import faulthandler
    traza = open(os.path.join(RAIZ, 'tests', f'salida_traza_{os.path.splitext(os.path.basename(prueba))[0]}.txt'), 'w')  # noqa: SIM115 (abierto hasta el final)
    #QGIS 4.2 en Windows se queda a veces colgado al arrancar (initQgis, antes de cargar nada del plugin; 15/10/2026):
    #si el arranque pasa de ESPERA_ARRANQUE segundos, se cierra con ARRANQUE_COLGADO y el padre lo reintenta
    faulthandler.dump_traceback_later(ESPERA_ARRANQUE, exit=True, file=traza)
    arrancar_qgis()
    faulthandler.cancel_dump_traceback_later()
    print(ARRANCADO, flush=True)
    faulthandler.dump_traceback_later(ESPERA_TRAZA, exit=True, file=traza)
    from qgis.analysis import QgsNativeAlgorithms
    from qgis.core import QgsApplication
    for base in (QgsApplication.prefixPath(), QgsApplication.pkgDataPath()):  #Windows: prefixPath; Linux: pkgDataPath
        sys.path.append(os.path.join(base, 'python', 'plugins'))  #Ahí está Processing
    from processing.core.Processing import Processing
    Processing.initialize()  #Algoritmos de Processing (native:*, gdal:*)
    QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())
    import qgis.utils
    from qgis.testing.mocked import get_iface
    qgis.utils.iface = get_iface()  #Interfaz simulada con un lienzo de mapa real
    from qgis.core import QgsCoordinateReferenceSystem, QgsRectangle
    lienzo = qgis.utils.iface.mapCanvas()  #Como un QGIS recién abierto: mapa en EPSG:4326
    lienzo.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
    lienzo.setExtent(QgsRectangle(-3.95, 36.70, -3.80, 36.80))  #Nerja
    qgis.utils.reloadPlugin = lambda nombre: None  #Cada prueba ya parte de un QGIS recién abierto
    # El plugin se importa como «catastral_gml_tools» directamente desde la carpeta del proyecto
    spec = importlib.util.spec_from_file_location(MODULO, os.path.join(RAIZ, '__init__.py'),
                                                  submodule_search_locations=[RAIZ])
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[MODULO] = modulo
    spec.loader.exec_module(modulo)
    ruta = os.path.join(RAIZ, 'tests', prueba)
    with open(ruta, encoding='utf-8') as f:
        codigo = compile(f.read(), ruta, 'exec')
    exec(codigo, {'__name__': '__main__', '__file__': ruta})
    sys.stdout.flush()
    #Tareas en segundo plano que siguieran vivas (p. ej. la descarga de esquemas de Validar): se cancelan y se espera a
    #que acaben antes de salir; salir con peticiones de red a medias dejaba el proceso colgado en Windows (15/10/2026)
    from qgis.PyQt.QtCore import QCoreApplication
    gestor = QgsApplication.taskManager()
    gestor.cancelAll()
    limite = time.time() + 30
    while gestor.countActiveTasks() and time.time() < limite:
        QCoreApplication.processEvents()
        time.sleep(0.05)
    borrar_cache()
    os._exit(0)  #Salida inmediata: evita mensajes de cierre de QGIS que no aportan nada


def main(pruebas):
    from qgis.core import Qgis
    version = '.'.join(Qgis.version().split('.')[:2])
    resultados = os.path.join(RAIZ, 'tests', f'resultados_qgis{version}.txt')
    lineas = [f"Pruebas Catastral GML Tools · QGIS {Qgis.version()} · {datetime.datetime.now():%d/%m/%Y %H:%M}", ""]
    todo_bien = True
    for prueba in pruebas:
        desde = len(lineas)
        inicio = time.time()
        reintentos = 0
        while True:
            try:
                hijo = subprocess.run([sys.executable, os.path.abspath(__file__), '--una', prueba], capture_output=True,
                                      text=True, encoding='utf-8', errors='replace', timeout=ESPERA)
                salida, codigo = hijo.stdout + hijo.stderr, hijo.returncode
            except subprocess.TimeoutExpired:
                salida, codigo = '', 'tiempo agotado'
            if ARRANCADO in salida or reintentos >= REINTENTOS_ARRANQUE:
                break
            reintentos += 1  #QGIS no llegó a arrancar: no es un fallo de la prueba, se repite
        segundos = round(time.time() - inicio)
        resultado = [linea for linea in salida.splitlines() if 'RESULTADO:' in linea]
        fallos = [linea.strip() for linea in salida.splitlines() if 'FALLO' in linea and 'RESULTADO' not in linea]
        aviso = f" [QGIS no arrancó a la primera: {reintentos} reintento{'s' if reintentos != 1 else ''}]" if reintentos else ''
        if resultado and 'TODO CORRECTO' in resultado[-1]:
            lineas.append(f"  OK      {prueba} ({segundos} s){aviso}")
        else:
            todo_bien = False
            motivo = 'con fallos' if resultado else (f'se cerró sin terminar (código {codigo})' if ARRANCADO in salida
                                                     else 'QGIS no llegó a arrancar')
            lineas.append(f"  FALLO   {prueba} ({segundos} s): {motivo}")
            lineas += [f"            {f}" for f in fallos]
            if not resultado:
                lineas += [f"            | {linea}" for linea in salida.splitlines()[-25:]]
        print("\n".join(lineas[desde:]), flush=True)
    lineas += ["", "RESULTADO GLOBAL: " + ("TODO CORRECTO" if todo_bien else "HAY FALLOS")]
    with open(resultados, 'w', encoding='utf-8') as f:
        f.write("\n".join(lineas) + "\n")
    print("\n".join(lineas[-1:]))
    return 0 if todo_bien else 1


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--una':
        ejecutar_una(sys.argv[2])
    else:
        sys.exit(main([os.path.basename(a) for a in sys.argv[1:]] or PRUEBAS))
