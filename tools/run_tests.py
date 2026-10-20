r"""
Lanza las pruebas de tests/ cada una en un QGIS propio, SIN VENTANA: no toca el QGIS que tengas abierto,
las pruebas no se contaminan entre sí y, si una falla o se cierra, las demás siguen.

Uso (CMD, desde la carpeta del proyecto):
    "C:\Program Files\QGIS 3.40.13\bin\python-qgis-ltr.bat" tools\run_tests.py          (todas, QGIS 3.40)
    "C:\Program Files\QGIS 4.2.2\bin\python-qgis.bat" tools\run_tests.py                (todas, QGIS 4)
    ... tools\run_tests.py smoke_test.py                                                 (solo esa)

El resumen sale en pantalla y en tests/resultados_qgis<versión>.txt (p. ej. resultados_qgis3.40.txt). Usa la configuración de pruebas de QGIS, no la tuya
(favoritos, plantillas y configuraciones guardadas no se tocan). Lo que guardan las pruebas va a la organización
«CatastralGMLTools-Pruebas» (no a la de QGIS) y se borra al terminar: no quedan claves en el registro ni carpetas.

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
PRUEBAS = ['smoke_test.py', 'package_test.py', 'refcat_test.py', 'geometria_test.py', 'gml_parcela_test.py', 'parcela_ui_test.py', 'gml_lector_test.py', 'validar_ui_test.py', 'validador_test.py', 'esquemas_test.py', 'informe_test.py', 'servicios_test.py', 'descargar_ui_test.py', 'comparacion_test.py', 'alteraciones_test.py', 'unir_test.py', 'union_test.py', 'gml_edificio_test.py', 'edificio_ui_test.py', 'robustez_test.py', 'division_test.py', 'panel_test.py', 'conversor_test.py', 'superficies_test.py', 'ajuste_test.py', 'comparar_gml_test.py', 'comparar_casos_test.py', 'validar_casos_test.py', 'comparacion_casos_test.py', 'parcela_casos_test.py', 'division_casos_test.py', 'edificio_casos_test.py', 'descargar_casos_test.py', 'unir_casos_test.py', 'conversor_casos_test.py', 'superficies_casos_test.py', 'ajuste_casos_test.py', 'panel_casos_test.py', 'xml_roto_casos_test.py', 'coordenadas_casos_test.py']
ESPERA = 600  #Segundos máximos por prueba
ESPERA_TRAZA = 150  #Segundos tras los que una prueba colgada guarda su traza y se cierra
ESPERA_ARRANQUE = 60  #Segundos máximos para que arranque QGIS en el proceso de la prueba
ARRANCADO = '[QGIS arrancado]'
REINTENTOS_ARRANQUE = 2
MODULO = 'catastral_gml_tools'  #Nombre con el que QGIS carga el plugin
#Organización propia (no «QGIS»): lo que Qt guarda de las pruebas va a HKCU\Software\CatastralGMLTools-Pruebas y no se
#mezcla con QGIS ni con las pruebas de otros plugins (20/10/2026: 1115 claves QGIS-TEST-CGT-<pid> bajo
#HKCU\Software\QGIS dejaban QGIS 4.2 parado en initQgis() al arrancar cualquier prueba con la organización «QGIS»)
ORGANIZACION = 'CatastralGMLTools-Pruebas'
PREFIJO_APLICACION = 'QGIS-TEST-'
PREFIJO_ANTIGUO = 'QGIS-TEST-CGT-'  #Nombre que usaba este lanzador bajo la organización «QGIS» (hasta el 20/10/2026)


def arrancar_qgis():
    r"""
    Como qgis.testing.start_app, pero con una organización propia (ORGANIZACION) y un nombre de aplicación de este
    proceso. El nombre por proceso es necesario: QGIS guarda su caché, y el candado hstsstore.lock de la red, en
    LOCALAPPDATA\<organización>\<aplicación>\cache; con un nombre común, un proceso de prueba colgado retenía el
    candado y todos los QGIS siguientes se colgaban al arrancar hasta reiniciar Windows (QGIS 4.2, 15/10/2026). Lo que
    deja cada proceso (la carpeta de la caché y su clave del registro) se borra al terminar (borrar_cache); lo que dejara
    uno que se cortó, lo borra el proceso padre al acabar la batería (limpiar_restos).
    """
    import qgis.testing
    from qgis.core import QgsApplication
    from qgis.PyQt.QtCore import QCoreApplication, Qt
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    QCoreApplication.setOrganizationName(ORGANIZACION)
    QCoreApplication.setOrganizationDomain('catastralgmltools.invalid')
    QCoreApplication.setApplicationName(f'{PREFIJO_APLICACION}{os.getpid()}')
    os.environ['QGIS_CUSTOM_CONFIG_PATH'] = tempfile.mkdtemp('', 'QGIS-PythonTestConfigPath-')
    aplicacion = QgsApplication([os.fsencode(a) for a in sys.argv], True)
    aplicacion.initQgis()
    qgis.testing.QGISAPP = aplicacion  #start_app() (p. ej. desde qgis.testing.mocked) ya no crea otra
    return aplicacion


def borrar_cache():
    r"""
    Lo que deja este proceso: la carpeta de la caché de QGIS (con su nombre propio), la del perfil temporal y, en
    Windows, su clave del registro (HKCU\Software\<organización>\<aplicación>).
    """
    import shutil
    from qgis.PyQt.QtCore import QCoreApplication, QStandardPaths
    aplicacion = QCoreApplication.applicationName()
    cache = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
    while cache and os.path.basename(cache) != aplicacion and os.path.dirname(cache) != cache:
        cache = os.path.dirname(cache)  #Windows: …/<organización>/<aplicación>/cache; Linux: …/<organización>/<aplicación>
    for carpeta in (cache, os.environ.get('QGIS_CUSTOM_CONFIG_PATH', '')):
        if carpeta and (os.path.basename(carpeta) == aplicacion or 'QGIS-PythonTestConfigPath-' in carpeta):
            shutil.rmtree(carpeta, ignore_errors=True)
    borrar_clave(ORGANIZACION, aplicacion)


def borrar_clave(organizacion, aplicacion=None):
    r"""
    Borra HKCU\Software\<organización>\<aplicación> con todo lo que tenga dentro (o, sin aplicación, la de la
    organización entera). En Linux y macOS Qt guarda los ajustes en ficheros de la configuración temporal: nada que hacer.
    Devuelve las claves borradas.
    """
    if sys.platform != 'win32':
        return 0
    import winreg
    ruta = f'Software\\{organizacion}' + (f'\\{aplicacion}' if aplicacion else '')

    def borrar(padre, nombre):
        try:
            clave = winreg.OpenKey(padre, nombre, 0, winreg.KEY_ALL_ACCESS)
        except OSError:
            return 0
        n = 0
        with clave:
            while True:
                try:
                    hija = winreg.EnumKey(clave, 0)
                except OSError:
                    break
                n += borrar(clave, hija)
        try:
            winreg.DeleteKey(padre, nombre)
            return n + 1
        except OSError:
            return n
    return borrar(winreg.HKEY_CURRENT_USER, ruta)


def limpiar_restos():
    """
    Lo que dejaron los procesos de prueba que se cortaron antes de borrar_cache (tiempo agotado, cierre forzado), y las
    claves que dejaba este lanzador cuando usaba la organización «QGIS» (QGIS-TEST-CGT-<pid>). Solo toca lo de estas
    pruebas: nunca las claves ni las carpetas de QGIS ni las de otros plugins. Se llama al acabar la batería, con todos
    los procesos de prueba ya terminados. Devuelve el número de claves borradas.
    """
    import shutil
    borradas = 0
    if sys.platform == 'win32':
        import winreg
        try:  #Las de los procesos que no llegaron a borrar la suya (la de la organización, vacía, no cuenta)
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f'Software\\{ORGANIZACION}') as propia:
                restos = [winreg.EnumKey(propia, i) for i in range(winreg.QueryInfoKey(propia)[0])]
        except OSError:
            restos = []
        for nombre in restos:
            borradas += 1 if borrar_clave(ORGANIZACION, nombre) else 0
        borrar_clave(ORGANIZACION)
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Software\\QGIS') as qgis:
                antiguas = [winreg.EnumKey(qgis, i) for i in range(winreg.QueryInfoKey(qgis)[0])]
        except OSError:
            antiguas = []
        for nombre in antiguas:
            if nombre.startswith(PREFIJO_ANTIGUO):
                borradas += 1 if borrar_clave('QGIS', nombre) else 0
        base = os.environ.get('LOCALAPPDATA', '')
    else:
        base = os.path.join(os.path.expanduser('~'), '.cache')
    if base:
        shutil.rmtree(os.path.join(base, ORGANIZACION), ignore_errors=True)
        for carpeta in [os.path.join(base, 'QGIS', n) for n in (os.listdir(os.path.join(base, 'QGIS'))
                                                               if os.path.isdir(os.path.join(base, 'QGIS')) else [])]:
            if os.path.basename(carpeta).startswith(PREFIJO_ANTIGUO):
                shutil.rmtree(carpeta, ignore_errors=True)
    return borradas


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


def lanzar(prueba):
    """
    Ejecuta una prueba en su propio proceso y devuelve (salida, código). Si en ESPERA_ARRANQUE (+ margen) segundos no
    dice que QGIS ha arrancado, se corta para reintentarla, sin esperar a ESPERA: el 20/10/2026 un arranque colgado en
    QGIS 4.2 tuvo la batería parada 10 minutos; el proceso no llegaba a cerrarse del todo (como otros que Windows da por
    terminados y no desaparecen) y su salida no se cerraba. La salida se lee en un hilo aparte, que se abandona si el
    proceso no la cierra.
    """
    import threading
    hijo = subprocess.Popen([sys.executable, os.path.abspath(__file__), '--una', prueba], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
    lineas, arrancado, fin = [], threading.Event(), threading.Event()

    def leer():
        for linea in hijo.stdout:
            lineas.append(linea)
            if ARRANCADO in linea:
                arrancado.set()
        fin.set()
    threading.Thread(target=leer, daemon=True).start()
    codigo = None
    if not arrancado.wait(ESPERA_ARRANQUE + 20) and not fin.is_set():
        codigo = 'QGIS no arrancó a tiempo'
    elif not fin.wait(ESPERA):
        codigo = 'tiempo agotado'
    if codigo is not None:
        hijo.kill()
        fin.wait(10)  #Si ni así se cierra su salida, se sigue sin ella
    else:
        try:
            codigo = hijo.wait(30)
        except subprocess.TimeoutExpired:
            hijo.kill()
            codigo = 'no terminó de cerrarse'
    return ''.join(lineas), codigo


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
            salida, codigo = lanzar(prueba)
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
    borradas = limpiar_restos()
    if borradas:
        lineas.append(f"(Se han borrado {borradas} clave{'s' if borradas != 1 else ''} del registro que dejaron procesos de "
                      "prueba cortados)")
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
