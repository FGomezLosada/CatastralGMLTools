"""
Batería de casos del panel (plan de pruebas, docs/PLAN_PRUEBAS.md): abrir, cerrar, recargar y descargar el plugin con
tareas o herramientas de mapa en marcha; avisos con cualquier texto; pestañas y proyecto que cambian por debajo; y que
todo se entienda en un panel estrecho. Nunca una excepción ni una ventana. Sin internet (Catastro simulado).

Uso: tools\\probar.bat (o tools\\run_tests.py panel_casos_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import importlib.util
import os
import re
import tempfile
import traceback

import qgis.utils
from qgis.core import Qgis, QgsApplication, QgsProject
from qgis.gui import QgsMapToolPan
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFontMetrics, QTextDocument
from qgis.PyQt.QtWidgets import QAbstractButton, QApplication, QLabel, QMessageBox, QTextBrowser

import catastral_gml_tools  # noqa: E402
import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import gml_parcela as gp  # noqa: E402
from catastral_gml_tools.core.info import RAIZ  # noqa: E402

spec = importlib.util.spec_from_file_location('simulador_catastro', os.path.join(RAIZ, 'tests', 'simulador_catastro.py'))
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)
original = sim.instalar()

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))
dock_module.CatastralGMLToolsDockWidget.open_path = lambda self, ruta: None

iface = qgis.utils.iface
lienzo = iface.mapCanvas()
carpeta = tempfile.mkdtemp(prefix='cgt panel casos ñ_')
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


def gml(nombre):
    ruta = os.path.join(carpeta, nombre + '.gml')
    ok, inc = gp.escribir(ruta, [gp.ParcelaGML(sim.RC, gp.SDGC, sim.rect(sim.X0, sim.Y0, 20, 30), '01')], 25830)
    assert ok, inc
    return ruta


def visto(dw):
    """Lo que se lee en la barra de avisos (como se pinta, no el texto de origen)."""
    partes = []
    for item in dw.messageBar.items():
        partes += [w.toPlainText() for w in item.findChildren(QTextBrowser)]
        for e in item.findChildren(QLabel):  #Como se pinta: el texto enriquecido, pasado a texto
            if e.textFormat() == Qt.TextFormat.PlainText:
                partes.append(e.text())
            else:
                documento = QTextDocument()
                documento.setHtml(e.text())
                partes.append(documento.toPlainText())
    return ' '.join(partes)


def plugin_abierto():
    plugin = catastral_gml_tools.classFactory(iface)
    plugin.initGui()
    plugin.toggle(True)
    return plugin


# 1. Ciclo de vida
def sin_abrir():
    plugin = catastral_gml_tools.classFactory(iface)
    plugin.initGui()
    plugin.unload()
    plugin.unload()  #Dos veces (QGIS lo hace al recargar con errores): sin fallar
    return plugin.dockwidget is None, 'ok'


caso("cargar y descargar sin abrir el panel (y descargar dos veces)", sin_abrir)


def cerrar_con_x():
    plugin = plugin_abierto()
    dw = plugin.dockwidget
    dw.show()
    dw.hide()  #Como la × del panel
    desmarcado = not plugin.action.isChecked()
    plugin.toggle(True)
    reabierto = plugin.dockwidget is dw and dw.isVisible()
    plugin.unload()
    return desmarcado and reabierto, (desmarcado, reabierto)


caso("cerrar con la ×: el botón se desmarca y al reabrir es el mismo panel", cerrar_con_x)


def herramienta_descargar():
    pan = QgsMapToolPan(lienzo)
    lienzo.setMapTool(pan)
    plugin = plugin_abierto()
    dw = plugin.dockwidget
    dw.show()
    dw.pestanaDescargar.fondo.setChecked(False)
    dw.pestanaDescargar.mapaBoton.setChecked(True)
    activa = lienzo.mapTool() is dw.pestanaDescargar.herramienta
    dw.hide()
    devuelta = lienzo.mapTool() is pan and not dw.pestanaDescargar.mapaBoton.isChecked()
    plugin.unload()
    return activa and devuelta, (activa, devuelta, lienzo.mapTool())


caso("«Elegir en el mapa» activo y se cierra el panel: vuelve la herramienta de antes", herramienta_descargar)


def herramienta_ajuste():
    pan = QgsMapToolPan(lienzo)
    lienzo.setMapTool(pan)
    plugin = plugin_abierto()
    dw = plugin.dockwidget
    dw.show()
    bloque = dw.pestanaUtilidades.ajuste
    dw.tabWidget.setCurrentWidget(dw.tabUtilidades)
    dw.pestanaUtilidades.utilidades.setCurrentIndex(3)
    bloque.origenAj.setFilePath(gml('ajuste'))
    bloque.capturarBoton.setChecked(True)
    activa = lienzo.mapTool() is not pan
    plugin.unload()  #Descargar el plugin con la captura activa
    devuelta = lienzo.mapTool() is pan or lienzo.mapTool() is None
    return activa and devuelta, (activa, lienzo.mapTool())


caso("captura de pares activa y se descarga el plugin: el mapa queda libre", herramienta_ajuste)


def recargar_con_tarea():
    plugin = plugin_abierto()
    dw = plugin.dockwidget
    pes = dw.pestanaDescargar
    pes.fondo.setChecked(False)
    pes.rc.setText(sim.RC)
    pes.descargar()  #En segundo plano
    tarea = pes.tarea
    plugin.unload()  #«Plugin Reloader» a mitad de la descarga
    cancelada = tarea is None or tarea.feedback.isCanceled()
    otra = plugin_abierto()  #El plugin vuelto a cargar funciona
    nuevo = otra.dockwidget is not None and otra.dockwidget.tabWidget.count() == 5
    otra.unload()
    QgsApplication.taskManager().cancelAll()
    QgsProject.instance().removeAllMapLayers()
    QgsProject.instance().layerTreeRoot().removeAllChildren()
    return cancelada and nuevo, (cancelada, nuevo)


caso("recargar el plugin con una descarga en marcha: se cancela y el nuevo funciona", recargar_con_tarea)


# 2. Avisos con cualquier texto
dw = dock_module.CatastralGMLToolsDockWidget(iface)


def aviso(texto, debe_verse):
    def prueba():
        dw.messageBar.clearWidgets()
        dw.notify(texto)
        return debe_verse in visto(dw), visto(dw)
    return prueba


caso("aviso con «<ogr:2082108VF2628S…>»: se lee entero", aviso("Etiquetas (<ogr:2082108VF2628S…>) de QGIS",
                                                                "<ogr:2082108VF2628S…>"))
caso("aviso con «< 1 m²» y «&»: se lee tal cual", aviso("Restos de < 1 m² & astillas", "< 1 m² & astillas"))
caso("aviso con comillas: se leen tal cual", aviso('El campo "localId" y el \'label\'', '"localId" y el \'label\''))
caso("aviso con varias líneas y < >: se lee", aviso("Título\n- detalle con <b>negrita</b>", "<b>negrita</b>"))


def largo():
    dw.messageBar.clearWidgets()
    dw.warn("No se ha podido\n" + '\n'.join(f"- detalle {i}" for i in range(20)))
    texto = visto(dw)
    return 'detalle 0' in texto and 'más' in texto and 'detalle 19' not in texto, texto[-160:]


caso("aviso con 20 detalles: se ven los primeros y «… y N más»", largo)


def aviso_largo():
    """Un aviso de una línea larga en un panel estrecho se lee entero, sin barra de desplazamiento (26/10/2026)."""
    dw.messageBar.clearWidgets()
    dw.resize(360, 700)
    dw.show()
    dw.warn("La capa es de Gipuzkoa, que tiene catastro propio: el GML para la Sede Electrónica de la Dirección General "
            "del Catastro no sirve para sus trámites. Consulte al catastro de Gipuzkoa.")
    QgsApplication.processEvents()
    cajas = [c for i in dw.messageBar.items() for c in i.findChildren(QTextBrowser)]
    #Crece hasta que cabe el texto (o hasta el máximo: la letra de las pruebas sin ventana de Windows es mucho más ancha
    #que la real, y ahí un texto de tres líneas ocupa siete)
    tope = dock_module.ALTO_MAXIMO_AVISO
    entero = bool(cajas) and all(c.height() > 45 and (c.height() >= c.document().size().height() + 2 * c.frameWidth()
                                                      or c.height() == tope) for c in cajas)
    dw.messageBar.clearWidgets()
    return entero, [(c.height(), c.verticalScrollBar().isVisible(), c.document().size()) for c in cajas]


caso("aviso largo de una línea en un panel estrecho: la caja crece con el texto", aviso_largo)


def exito_largo():
    """El mensaje final con botones: el texto a todo lo ancho y entero, los botones debajo (27/10/2026)."""
    dw.messageBar.clearWidgets()
    dw.resize(360, 700)
    dw.show()
    mensaje = dw.success("GML creado: Parcela_29075A01100155.gml · 1 parcelas · EPSG:25830 · la Sede propondrá: subsanación "
                         "de discrepancias", [("Validar", dw.raise_), ("Abrir carpeta", dw.raise_),
                                             ("Cargar en el mapa", dw.raise_)])
    for _ in range(3):
        QgsApplication.processEvents()
    etiqueta = [e for e in mensaje.findChildren(QLabel) if 'GML creado' in e.text()][0]
    botones = [b for b in mensaje.findChildren(QAbstractButton) if b.text() == "Validar"]
    entero = etiqueta.height() >= etiqueta.heightForWidth(etiqueta.width()) > 0
    debajo = bool(botones) and botones[0].mapTo(mensaje, botones[0].rect().topLeft()).y() >= \
        etiqueta.mapTo(mensaje, etiqueta.rect().bottomLeft()).y()
    dw.messageBar.clearWidgets()
    return entero and debajo, (etiqueta.height(), etiqueta.heightForWidth(etiqueta.width()), etiqueta.width(), debajo)


caso("mensaje final largo con botones en un panel estrecho: texto entero y botones debajo", exito_largo)


def exito():
    dw.messageBar.clearWidgets()
    pulsado = []
    mensaje = dw.success("GML <creado> & listo", [("Abrir", lambda *a: pulsado.append(1))])
    boton = [b for b in mensaje.findChildren(QAbstractButton) if b.text() == "Abrir"]
    if boton:
        boton[0].click()
    return '<creado> & listo' in visto(dw) and pulsado == [1], (visto(dw), pulsado)


caso("mensaje final con < & y un botón que funciona", exito)


def arriba():
    """El aviso va encima de las pestañas: con el panel más alto que la pantalla, abajo no se veía (21/10/2026)."""
    dw.messageBar.clearWidgets()
    dw.tabWidget.setCurrentWidget(dw.tabParcela)
    dw.success("GML creado: prueba.gml")
    dw.mainLayout.activate()
    QgsApplication.processEvents()
    lugar = dw.mainLayout.indexOf(dw.messageBar), dw.mainLayout.indexOf(dw.tabWidget)
    return lugar[0] < lugar[1] and dw.messageBar.geometry().bottom() < dw.tabWidget.geometry().top() + 5, lugar


caso("el aviso final sale encima de las pestañas (siempre a la vista)", arriba)


# 3. Pestañas y proyecto que cambian por debajo
def orden():
    titulos = [dw.tabWidget.tabText(i).replace('&', '') for i in range(dw.tabWidget.count())]
    return titulos == ['Descargar', 'Parcela', 'Edificio', 'Validar', 'Utilidades'], titulos


caso("pestañas en el orden del trabajo", orden)


def pendiente_borrado():
    ruta = gml('pendiente')
    dw.gml_creado(ruta)
    os.remove(ruta)
    dw.messageBar.clearWidgets()
    dw.tabWidget.setCurrentWidget(dw.tabValidar)
    return 'No existe el fichero' in visto(dw) and dw.pestanaValidar.tabla.rowCount() == 0, visto(dw)


caso("el GML recién creado se borra antes de pasar a Validar: lo dice", pendiente_borrado)


def proyecto_nuevo():
    proyecto = QgsProject.instance()
    pes = dw.pestanaDescargar
    pes.fondo.setChecked(False)
    pes.rc.setText(sim.RC)
    pes.descargar(segundo_plano=False)  #Capas en Parcela y Edificio
    con_capa = dw.pestanaParcela.capa() is not None if hasattr(dw.pestanaParcela, 'capa') else True
    proyecto.clear()  #«Proyecto nuevo»
    for i in range(dw.tabWidget.count()):
        dw.tabWidget.setCurrentIndex(i)
    #Lo que use la capa ya borrada no puede fallar
    dw.pestanaParcela.division.marcar_lado()
    dw.pestanaUtilidades.ajuste.mostrar_en_mapa()
    return con_capa, 'ok'


caso("descargar y abrir un proyecto nuevo: se recorren las pestañas sin fallar", proyecto_nuevo)


def capas_quitadas():
    pes = dw.pestanaDescargar
    pes.descargar(segundo_plano=False)
    QgsProject.instance().removeAllMapLayers()
    for i in range(dw.tabWidget.count()):
        dw.tabWidget.setCurrentIndex(i)
    dw.pestanaParcela.division.marcar_lado()
    return True, 'ok'


caso("quitar todas las capas del proyecto con el panel abierto", capas_quitadas)


def mensaje_ancho():
    #Prueba a mano del 29/10/2026: el icono dejaba un hueco a su izquierda y el texto y los botones, apretados a la derecha
    dw.messageBar.clearWidgets()
    dw.resize(540, 700)
    mensaje = dw.success("GML creado: Parcela_1907401VK4810H.gml · 2 parcelas · EPSG:25830 · Segregación",
                         [("Validar", dw.messageBar.clearWidgets)])
    for _ in range(5):
        QApplication.processEvents()
    disposicion = mensaje.layout()
    widgets = [disposicion.itemAt(i).widget() for i in range(disposicion.count()) if disposicion.itemAt(i).widget()]
    icono = next((w for w in widgets if isinstance(w, QLabel) and w.pixmap() is not None and not w.pixmap().isNull()), None)
    contenido = next((w for w in widgets if w.layout() is not None), None)
    ok = (icono is not None and contenido is not None and icono.width() <= icono.pixmap().width() + 8
          and contenido.width() >= 0.75 * mensaje.width())
    dw.messageBar.clearWidgets()
    return ok, [(type(w).__name__, w.width()) for w in widgets] + [mensaje.width()]


caso("los mensajes finales usan todo el ancho: el icono no deja un hueco a su izquierda", mensaje_ancho)


def panel_bajo():
    #Prueba a mano del 30/10/2026: con «Opciones avanzadas» abiertas en Edificio y un mensaje arriba, el panel pedía más
    #alto que la ventana y se metía bajo la barra de Windows. Cada pestaña se desplaza: su alto mínimo es pequeño
    #En píxeles, no en líneas de letra: en Windows la letra es más baja y Validar (333 px) pasaba de 18 líneas sin que el
    #panel dejara de caber. 420 px dejan sitio, en una pantalla de 768 px, a QGIS, la cabecera y un mensaje
    limite = 420
    dw.pestanaEdificio.avanzadas.setCollapsed(False)
    dw.pestanaParcela.avanzadas.setCollapsed(False)
    QApplication.processEvents()
    altos = {dw.tabWidget.tabText(i): dw.tabWidget.widget(i).minimumSizeHint().height() for i in range(dw.tabWidget.count())}
    dw.pestanaEdificio.avanzadas.setCollapsed(True)
    dw.pestanaParcela.avanzadas.setCollapsed(True)
    return all(a <= limite for a in altos.values()), (limite, altos)


caso("cabe en una pantalla baja: ninguna pestaña pide más alto del que hay (se desplaza), también con opciones abiertas",
     panel_bajo)


# 4. Que se entienda en un panel estrecho
def botones():
    sin_texto = []
    for b in dw.findChildren(QAbstractButton):
        nombre = type(b).__name__
        if nombre in ('QTabBar', 'QgsFilterLineEdit') or b.objectName().startswith('qt_') or b.objectName() == 'collapseButton':
            continue
        if not b.text().replace('&', '').strip() and not b.toolTip().strip() and not b.icon().isNull():
            padre = b.parent()
            if padre is not None and type(padre).__name__ in ('QgsFileWidget', 'QgsMessageBarItem', 'QToolBox', 'QTabBar', 'QLineEdit',
                                                               'QgsFilterLineEdit', 'QgsCollapsibleGroupBox'):
                continue
            sin_texto.append((nombre, b.objectName(), type(padre).__name__ if padre else None))
    return not sin_texto, sin_texto[:8]


caso("todo botón con solo icono tiene una explicación al pasar el ratón", botones)


def estrecho():
    #Relativo a la letra: 42 «x» son unos 280 px con la de Windows (en el entorno de pruebas la letra es más ancha).
    #Prueba a mano del 20/10/2026: a unos 370 px, la pestaña Parcela sacaba una barra horizontal que tapaba el resumen
    limite = QFontMetrics(dw.font()).horizontalAdvance('x' * 42)
    anchos = {'límite': limite}
    paginas = [(dw.tabWidget.tabText(i), dw.tabWidget.widget(i)) for i in range(dw.tabWidget.count())]
    for nombre, pagina in paginas:
        anchos[nombre] = pagina.minimumSizeHint().width()
    for k in range(dw.pestanaUtilidades.utilidades.count()):
        anchos[f'Utilidades {k + 1}'] = dw.pestanaUtilidades.utilidades.widget(k).minimumSizeHint().width()
    return all(a <= limite for a in anchos.values()), anchos


caso("cabe en un panel estrecho (unos 280 px) en todas las pestañas y utilidades", estrecho)


def division_abierta():
    dw.pestanaParcela.division.setCollapsed(False)
    ancho = dw.pestanaParcela.minimumSizeHint().width()
    dw.pestanaParcela.division.setCollapsed(True)
    return ancho <= QFontMetrics(dw.font()).horizontalAdvance('x' * 42), ancho


caso("con «Dividir la parcela» desplegado también cabe", division_abierta)


def ayuda():
    ruta = dw.help_url().toLocalFile()
    with open(ruta, encoding='utf-8') as f:
        texto = f.read()
    anclas = set(re.findall(r'id="([^"]+)"', texto))
    enlaces = set(re.findall(r'href="#([^"]+)"', texto))
    rotos = sorted(enlaces - anclas)
    return os.path.isfile(ruta) and not rotos, rotos


caso("la ayuda local existe y sus enlaces internos llevan a su sitio", ayuda)

dw.cleanup()
dw.deleteLater()
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
resultados["ninguna ventana emergente"] = not ventanas

print("=" * 60)
print("QGIS", Qgis.version(), "· Panel: batería de casos")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, d in detalles.items():
    print("Detalles", nombre, ":", d)
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
