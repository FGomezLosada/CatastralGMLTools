"""
Pestaña «Validar»: abre un GML de parcela o de edificio, lo comprueba como lo hará la Sede Electrónica del
Catastro (core/validador.py) y contra el esquema XSD oficial (core/esquemas.py, en segundo plano), muestra cada
parcela o construcción con su estado y la lista de incidencias, y lo carga en el mapa para revisarlo.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os

from qgis.core import Qgis, QgsApplication, QgsMimeDataUtils, QgsProject, QgsTask
from qgis.gui import QgsFileWidget
from qgis.PyQt import sip
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import comparacion as cmp
from ..core import esquemas
from ..core import geometria as geo
from ..core import gml_lector as gl
from ..core import informe as informe_html
from ..core import validador
from ..core.incidencias import AVISO, ERROR, INFO, Incidencia
from ..core.info import FUENTE_DGC
from . import estilos

CABECERAS = ['Tipo', 'Identificador (localId)', 'Namespace', 'Sup. GML m²', 'Sup. calculada m²', 'Estado']
COL_ESTADO = 5
ICONOS = {ERROR: '/mIconCritical.svg', AVISO: '/mIconWarning.svg', INFO: '/mIconInfo.svg'}
ICONOS_CODIGO = {'XSD-VALIDO': '/mIconSuccess.svg', 'CMP-CONTORNO-OK': '/mIconSuccess.svg', 'CMP-BU-DENTRO': '/mIconSuccess.svg'}  #Marca verde para lo que está bien
TEXTO_ESTADO = {ERROR: 'Con errores', AVISO: 'Con avisos', 'correcta': 'Correcta'}
PROPIEDAD_GML = 'catastral_gml_tools/gml'  #Propiedad de las capas que carga el plugin: ruta del GML del que salen
COMPARABLES = ('CP 4.0', 'BU 2.0')  #Parcela: operación y contorno; edificio: dentro de la parcela (ICUC)


def comparar(lectura):
    """Comparación con el Catastro según el tipo de GML."""
    return cmp.comparar_edificio(lectura) if lectura.version == 'BU 2.0' else cmp.comparar(lectura)


class PestanaValidar(QWidget):
    def __init__(self, dock, parent=None):
        super().__init__(parent)
        self.dock = dock
        self.resultado = None
        self.informe = None
        self.tarea = None  #Comprobación XSD en curso (se guarda la referencia para que Python no la borre)
        self.tarea_cmp = None  #Comparación con el Catastro en curso
        self.comparacion = None
        self.ruta = ''
        self.construir()
        self.setAcceptDrops(True)  #Se puede arrastrar un GML desde el Explorador de Windows a la pestaña
        self.fichero.lineEdit().setAcceptDrops(False)  #Que lo recoja la pestaña entera, también sobre la casilla del fichero
        self.fichero.fileChanged.connect(self.abrir)
        self.cargarBoton.clicked.connect(self.cargar_en_mapa)
        self.xsdBoton.clicked.connect(self.comprobar_esquema)
        self.cmpBoton.clicked.connect(self.comparar_catastro)
        self.informeBoton.clicked.connect(self.crear_informe)
        self.lista.itemSelectionChanged.connect(self.ir_a_elemento)

    def construir(self):
        principal = QVBoxLayout(self)
        principal.setContentsMargins(0, 0, 0, 0)
        fila = QHBoxLayout()
        fila.addWidget(QLabel("Fichero GML", self))
        self.fichero = QgsFileWidget(self)
        self.fichero.setStorageMode(QgsFileWidget.StorageMode.GetFile)
        self.fichero.setFilter("GML (*.gml *.xml)")
        self.fichero.setDialogTitle("Abrir un GML de parcela o de edificio")
        fila.addWidget(self.fichero, 1)
        principal.addLayout(fila)

        self.resumen = QLabel("<i>Elija o arrastre aquí un GML de parcela catastral (esquema 3.0 o 4.0) o de edificio.</i>",
                              self)
        self.resumen.setWordWrap(True)
        principal.addWidget(self.resumen)

        self.estado = QLabel(self)
        self.estado.setWordWrap(True)
        principal.addWidget(self.estado)

        divisor = QSplitter(Qt.Orientation.Vertical, self)
        self.tabla = QTableWidget(0, len(CABECERAS), divisor)
        self.tabla.setHorizontalHeaderLabels(CABECERAS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)  #Todas se pueden ensanchar arrastrando el borde
        cabecera.setStretchLastSection(True)
        cabecera.setMinimumSectionSize(40)
        self.lista = QListWidget(divisor)
        self.lista.setWordWrap(True)
        self.lista.setToolTip("Incidencias del GML. Al elegir una, se marca su parcela en la tabla")
        divisor.addWidget(self.tabla)
        divisor.addWidget(self.lista)
        principal.addWidget(divisor, 1)

        botones = QHBoxLayout()
        self.xsdBoton = QPushButton(QgsApplication.getThemeIcon('/mActionRefresh.svg'), "Comprobar esquema XSD", self)
        self.xsdBoton.setToolTip("Vuelve a comprobar el GML contra los esquemas XSD oficiales de INSPIRE.\n"
                                 "La primera vez se descargan de internet; después se usan los guardados")
        self.xsdBoton.setEnabled(False)
        botones.addWidget(self.xsdBoton)
        self.cmpBoton = QPushButton(QgsApplication.getThemeIcon('/mActionAddWfsLayer.svg'), "Comparar con el Catastro", self)
        self.cmpBoton.setToolTip("Descarga las parcelas catastrales vigentes bajo el GML y comprueba, como el informe de\n"
                                 "validación gráfica: parcelas afectadas (NPO), operación, contorno exterior (±1 cm),\n"
                                 "parcelas afectadas solo en parte, suelo sin parcela y referencias.\n"
                                 "En un GML de edificio, que cada construcción esté dentro de su parcela (como el ICUC).\n"
                                 "Necesita internet")
        self.cmpBoton.setEnabled(False)
        botones.addWidget(self.cmpBoton)
        botones.addStretch(1)
        principal.addLayout(botones)
        botones = QHBoxLayout()
        botones.addStretch(1)
        self.informeBoton = QPushButton(QgsApplication.getThemeIcon('/mActionNewReport.svg'), "Informe", self)
        self.informeBoton.setToolTip("Guarda junto al GML un informe de validación en HTML (resultado, incidencias, croquis y\n"
                                     "coordenadas) y lo abre en el navegador")
        self.informeBoton.setEnabled(False)
        botones.addWidget(self.informeBoton)
        self.cargarBoton = QPushButton(QgsApplication.getThemeIcon('/mActionAddLayer.svg'), "Cargar en el mapa", self)
        self.cargarBoton.setEnabled(False)
        botones.addWidget(self.cargarBoton)
        principal.addLayout(botones)

    # ------------------------------------------------------------------ Arrastrar y soltar

    @staticmethod
    def rutas_gml(mime):
        """
        Ficheros .gml o .xml que vienen en lo arrastrado:
          - desde el Explorador de Windows: rutas de ficheros;
          - desde el panel de Capas o el Navegador de QGIS: capas. De una capa cargada por el plugin se toma el GML del
            que salió (propiedad PROPIEDAD_GML); de una capa abierta desde un .gml, su fichero de origen.
        """
        if mime is None:
            return []
        rutas = []
        if mime.hasUrls():
            rutas += [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
        if QgsMimeDataUtils.isUriList(mime):
            for uri in QgsMimeDataUtils.decodeUriList(mime):
                capa = QgsProject.instance().mapLayer(uri.layerId) if uri.layerId else None
                if capa is not None and capa.customProperty(PROPIEDAD_GML):
                    rutas.append(capa.customProperty(PROPIEDAD_GML))
                else:
                    rutas.append((capa.source() if capa is not None else uri.uri).split('|')[0])
        vistas = []
        for ruta in rutas:
            if ruta and ruta.lower().endswith(('.gml', '.xml')) and os.path.isfile(ruta) and ruta not in vistas:
                vistas.append(ruta)
        return vistas

    def dragEnterEvent(self, event):  # noqa: N802 (nombre impuesto por Qt)
        if self.rutas_gml(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):  # noqa: N802 (nombre impuesto por Qt)
        self.dragEnterEvent(event)

    def dropEvent(self, event):  # noqa: N802 (nombre impuesto por Qt)
        rutas = self.rutas_gml(event.mimeData())
        if not rutas:
            event.ignore()
            return
        event.acceptProposedAction()
        self.soltar(rutas)

    def soltar(self, rutas):
        """Abre el GML soltado (si se sueltan varios, el primero, y se avisa)."""
        self.fichero.setFilePath(rutas[0])  #Lanza abrir() por la señal fileChanged
        if len(rutas) > 1:
            self.dock.notify(f"Se ha abierto {os.path.basename(rutas[0])}; la pestaña revisa un GML cada vez",
                             Qgis.MessageLevel.Info, 8)

    # ------------------------------------------------------------------ Abrir

    def limpiar(self):
        self.tabla.setRowCount(0)
        self.lista.clear()
        self.estado.clear()
        self.cargarBoton.setEnabled(False)
        self.xsdBoton.setEnabled(False)
        self.cmpBoton.setEnabled(False)
        self.informeBoton.setEnabled(False)
        self.comparacion = None
        self.resultado = None
        self.informe = None
        self.ultimo_informe = ''

    def abrir(self, *args, segundo_plano=True):
        """Lee y valida el GML elegido, rellena la tabla y la lista, y lanza la comprobación XSD en segundo plano."""
        self.dock.messageBar.clearWidgets()
        ruta = self.fichero.filePath().strip()
        self.limpiar()
        if not ruta:
            return None
        if not os.path.isfile(ruta):
            self.dock.warn(f"No existe el fichero: {ruta}")
            return None
        self.ruta = ruta
        self.resultado = gl.leer(ruta)
        self.informe = validador.validar(ruta, self.resultado)
        r = self.resultado
        self.tabla.setRowCount(len(r.elementos))
        for i, e in enumerate(r.elementos):
            calculada = None if e.geometria.isNull() else geo.redondear_m2(e.geometria.area())
            valores = [e.tipo.capitalize(), e.local_id, e.namespace,
                       '' if e.area_declarada is None else str(e.area_declarada), '' if calculada is None else str(calculada), '']
            for col, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                if col in (3, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tabla.setItem(i, col, item)
            if e.area_declarada is not None and calculada is not None and e.area_declarada != calculada:
                self.tabla.item(i, 3).setForeground(Qt.GlobalColor.red)
                self.tabla.item(i, 3).setToolTip("La superficie declarada no coincide con la de la geometría")
        self.tabla.resizeColumnsToContents()
        self.tabla.setColumnWidth(1, max(self.tabla.columnWidth(1), 130))
        informativas = [i.mensaje for i in r.incidencias if i.codigo == 'GML-LEIDO']
        self.resumen.setText(f"<b>{os.path.basename(ruta)}</b> · " + (informativas[0] if informativas else 'sin elementos'))
        self.mostrar_informe()
        self.cargarBoton.setEnabled(bool(r.elementos))
        self.informeBoton.setEnabled(bool(r.elementos))
        self.cmpBoton.setEnabled(r.version in COMPARABLES and bool(r.elementos) and self.tarea_cmp is None)
        if r.elementos and r.version in ('CP 4.0', 'BU 2.0'):
            self.comprobar_esquema(segundo_plano=segundo_plano)
        return self.informe

    def mostrar_informe(self):
        """Estado de cada fila, lista de incidencias y resumen (verde, naranja o rojo)."""
        informe = self.informe
        if informe is None:
            return
        for i, e in enumerate(informe.lectura.elementos):
            estado = informe.estado(e.local_id)
            item = self.tabla.item(i, COL_ESTADO)
            if item is None:
                continue
            item.setText(TEXTO_ESTADO[estado])
            item.setForeground(Qt.GlobalColor.red if estado == ERROR else Qt.GlobalColor.darkYellow if estado == AVISO
                               else Qt.GlobalColor.darkGreen)
            item.setToolTip("\n".join(i.mensaje for i in informe.de(e.local_id)))
        self.lista.clear()
        orden = {ERROR: 0, AVISO: 1, INFO: 2}
        for inc in sorted(informe.incidencias, key=lambda i: orden.get(i.nivel, 3)):
            if inc.codigo == 'GML-LEIDO':
                continue
            icono = ICONOS_CODIGO.get(inc.codigo) or ICONOS.get(inc.nivel, '/mIconInfo.svg')
            if inc.codigo == 'CMP-OPERACION' and inc.nivel == INFO:  #Operación admitida: también en verde
                icono = '/mIconSuccess.svg'
            item = QListWidgetItem(QgsApplication.getThemeIcon(icono), str(inc))
            item.setData(Qt.ItemDataRole.UserRole + 1, icono)
            item.setData(Qt.ItemDataRole.UserRole, inc.elemento)
            if inc.nivel == ERROR:
                item.setForeground(Qt.GlobalColor.red)
            self.lista.addItem(item)
        for tarea, texto in ((self.tarea, "Comprobando el esquema XSD oficial…"), (self.tarea_cmp, "Comparando con el Catastro…")):
            if tarea is not None:  #Tareas aún en marcha: se siguen viendo en la lista
                self.lista.addItem(QListWidgetItem(QgsApplication.getThemeIcon('/mIconLoading.gif'), texto))
        n_err, n_av = len(informe.errores), len(informe.avisos)
        color = '#c92a2a' if n_err else '#e67700' if n_av else '#2b8a3e'
        simbolo = '✖' if n_err else '⚠' if n_av else '✔'
        self.estado.setText(f"<span style='color:{color}'><b>{simbolo} {validador.resumen(informe)}</b></span>"
                            "<br><small>Herramienta no oficial: valide siempre el fichero en la Sede Electrónica del "
                            "Catastro.</small>")

    def ir_a_elemento(self):
        """Al elegir una incidencia de la lista, se selecciona su fila en la tabla."""
        items = self.lista.selectedItems()
        elemento = items[0].data(Qt.ItemDataRole.UserRole) if items else ''
        if not elemento:
            return
        for i in range(self.tabla.rowCount()):
            if self.tabla.item(i, 1).text() == elemento:
                self.tabla.selectRow(i)
                self.tabla.scrollToItem(self.tabla.item(i, 1))
                break

    # ------------------------------------------------------------------ Informe HTML

    def crear_informe(self, *args):
        """Guarda el informe de validación junto al GML y lo abre en el navegador."""
        if self.informe is None or not self.informe.lectura.elementos:
            return None
        try:
            ruta = informe_html.escribir(self.informe)
        except OSError as e:
            self.dock.warn(f"No se ha podido guardar el informe: {e}")
            return None
        self.ultimo_informe = ruta
        self.dock.success(f"Informe guardado: {os.path.basename(ruta)}",
                          [("Abrir informe", self.abrir_informe), ("Abrir carpeta", self.abrir_carpeta_informe)])
        self.abrir_informe()
        return ruta

    def abrir_informe(self, *args):
        if self.ultimo_informe:
            self.dock.open_path(self.ultimo_informe)

    def abrir_carpeta_informe(self, *args):
        if self.ultimo_informe:
            self.dock.open_path(os.path.dirname(self.ultimo_informe))

    # ------------------------------------------------------------------ Esquema XSD (segundo plano)

    def comprobar_esquema(self, *args, segundo_plano=True):
        """Comprueba el GML contra el esquema XSD oficial. En segundo plano no bloquea QGIS mientras se descargan."""
        if self.resultado is None or not self.resultado.datos:
            return
        self.informe.incidencias = [i for i in self.informe.incidencias if not i.codigo.startswith('XSD')]
        self.xsdBoton.setEnabled(False)
        self.lista.addItem(QListWidgetItem(QgsApplication.getThemeIcon('/mIconLoading.gif'),
                                           "Comprobando el esquema XSD oficial…"))
        if not segundo_plano:
            self.esquema_comprobado(esquemas.validar(self.resultado.datos, self.resultado.version))
            return
        self.tarea = TareaEsquema(self.resultado.datos, self.resultado.version, self)
        QgsApplication.taskManager().addTask(self.tarea)

    def esquema_comprobado(self, incidencias):
        """Llega del hilo de la tarea (ya en el hilo principal): añade el resultado XSD al informe."""
        if sip.isdeleted(self) or self.informe is None:
            return
        self.tarea = None  #Antes de mostrar_informe: si no, la lista seguiría diciendo «Comprobando…»
        self.informe.incidencias += incidencias
        self.mostrar_informe()
        self.xsdBoton.setEnabled(True)

    # ------------------------------------------------------------------ Comparación con el Catastro (segundo plano)

    def comparar_catastro(self, *args, segundo_plano=True):
        """Compara el GML con las parcelas catastrales vigentes (descarga del WFS de la DGC, en segundo plano)."""
        if self.resultado is None or self.resultado.version not in COMPARABLES or self.tarea_cmp is not None:
            return None
        self.informe.incidencias = [i for i in self.informe.incidencias if not i.codigo.startswith('CMP')]
        self.cmpBoton.setEnabled(False)
        self.lista.addItem(QListWidgetItem(QgsApplication.getThemeIcon('/mIconLoading.gif'),
                                           "Comparando con el Catastro…"))
        if not segundo_plano:
            return self.comparado(comparar(self.resultado))
        self.tarea_cmp = TareaComparacion(self.resultado, self)
        QgsApplication.taskManager().addTask(self.tarea_cmp)
        return None

    def comparado(self, comparacion):
        """Llega de la tarea: añade el resultado al informe y lleva al mapa las parcelas catastrales y las diferencias."""
        if sip.isdeleted(self):
            return None
        self.tarea_cmp = None
        if self.informe is None or comparacion is None:
            return None
        self.comparacion = comparacion
        self.informe.incidencias += comparacion.incidencias
        self.mostrar_informe()
        self.cmpBoton.setEnabled(True)
        if not comparacion.comparada:
            self.dock.warn("\n".join(i.mensaje for i in comparacion.incidencias) or "No se ha podido comparar con el Catastro")
            return comparacion
        cargar_comparacion(comparacion, self.ruta, self.dock.iface)
        errores = [i for i in comparacion.incidencias if i.nivel == ERROR]
        texto = comparacion.operacion if comparacion.edificio else \
            f"NPO {comparacion.npo} · NPP {comparacion.npp} → {comparacion.operacion}"
        if comparacion.edificio and not errores:
            errores = [i for i in comparacion.incidencias if i.nivel == AVISO]  #En parte fuera: se avisa en naranja
        if errores:
            n = len(errores)
            que = (f"{n} error{'es' if n != 1 else ''}" if errores[0].nivel == ERROR else f"{n} aviso{'s' if n != 1 else ''}")
            self.dock.warn(f"Comparación con el Catastro: {que} · {texto}\n"
                           + "\n".join(i.mensaje for i in errores))
        elif comparacion.edificio and not any(i.nivel == ERROR for i in self.informe.incidencias):
            rc = comparacion.origen[0].local_id if comparacion.origen else ''
            self.dock.success(f"{texto}. Listo para el ICUC: en la Sede Electrónica del Catastro, «Informe catastral de "
                              f"ubicación de las construcciones», indique la parcela {rc} y suba "
                              f"{os.path.basename(self.ruta)}", [("Abrir carpeta", self.abrir_carpeta_gml)])
        else:
            self.dock.success(f"Comparación con el Catastro: {texto}" + ("" if comparacion.edificio else ". Contorno coincidente"))
        return comparacion

    def abrir_carpeta_gml(self, *args):
        if self.ruta:
            self.dock.open_path(os.path.dirname(self.ruta))

    def cargar_en_mapa(self, *args):
        """Añade el GML al proyecto como capa de memoria con estilo y acerca el mapa a ella."""
        if not self.resultado or not self.resultado.elementos:
            return None
        return cargar(self.resultado, self.ruta, self.dock.iface)


class TareaComparacion(QgsTask):
    """Comparación con el Catastro en segundo plano (descarga las parcelas catastrales del WFS de la DGC)."""

    def __init__(self, resultado, pestana):
        super().__init__("Catastral GML Tools: comparando con el Catastro", QgsTask.Flag.CanCancel)
        self.resultado_lectura = resultado
        self.pestana = pestana
        self.comparacion = None

    def run(self):
        try:
            self.comparacion = comparar(self.resultado_lectura)
        except Exception as e:  #Nunca debe cerrar QGIS: se informa como incidencia
            self.comparacion = cmp.Comparacion(incidencias=[Incidencia(AVISO, 'CMP-FALLO',
                                                                       f"No se ha podido comparar con el Catastro: {e}")])
        return True

    def finished(self, resultado):
        if self.pestana is not None and not sip.isdeleted(self.pestana):
            self.pestana.comparado(self.comparacion)


class TareaEsquema(QgsTask):
    """Validación XSD en segundo plano: la primera vez descarga ~80 esquemas oficiales."""

    def __init__(self, datos, version, pestana):
        super().__init__("Catastral GML Tools: comprobando el esquema XSD", QgsTask.Flag.CanCancel)
        self.datos = datos
        self.version = version
        self.pestana = pestana
        self.incidencias = []

    def run(self):
        try:
            self.incidencias = esquemas.validar(self.datos, self.version)
        except Exception as e:  #Nunca debe cerrar QGIS: se informa como incidencia
            self.incidencias = [Incidencia(AVISO, 'XSD-FALLO', f"No se ha podido comprobar el esquema XSD: {e}")]
        return True

    def finished(self, resultado):
        if self.pestana is not None and not sip.isdeleted(self.pestana):
            self.pestana.esquema_comprobado(self.incidencias)


def cargar(resultado, ruta, iface=None):
    """Capa con estilo a partir de un resultado de lectura, añadida al proyecto (sin crear ficheros .gfs)."""
    nombre = os.path.splitext(os.path.basename(ruta))[0]
    capa = estilos.aplicar(gl.capa(resultado, f"{nombre} (vista del GML)"))
    capa.setCustomProperty(PROPIEDAD_GML, ruta)  #Para poder arrastrar la capa a la pestaña Validar
    #Es una capa temporal para ver el fichero: el GML válido para la Sede es el fichero, no hay que guardarla con QGIS
    #(«Guardar como» GML de QGIS escribe un GML genérico, no INSPIRE CadastralParcels 4.0)
    metadatos = capa.metadata()
    metadatos.setAbstract(f"Vista del fichero {ruta}. El GML para la Sede es ese fichero: no guarde esta capa con "
                          "«Guardar como» de QGIS (escribiría un GML genérico, no INSPIRE CadastralParcels 4.0).")
    capa.setMetadata(metadatos)
    QgsProject.instance().addMapLayer(capa)
    if iface is not None and hasattr(iface, 'mapCanvas'):
        try:
            lienzo = iface.mapCanvas()
            lienzo.setExtent(lienzo.mapSettings().layerExtentToOutputExtent(capa, capa.extent()).buffered(5))
            lienzo.refresh()
        except (AttributeError, TypeError):
            pass
    return capa


def cargar_comparacion(comparacion, ruta, iface=None):
    """
    Grupo «Comparación <fichero>» con las parcelas catastrales afectadas (gris, con su número) y, si las hay, las
    diferencias con el GML: exceso (suelo del GML fuera de ellas, rojo) y defecto (suelo de ellas que el GML deja
    fuera, azul). Si ya existía, se sustituye.
    """
    proyecto = QgsProject.instance()
    raiz = proyecto.layerTreeRoot()
    nombre = f"Comparación {os.path.splitext(os.path.basename(ruta))[0]}"
    viejo = raiz.findGroup(nombre)
    if viejo is not None:
        proyecto.removeMapLayers(viejo.findLayerIds())
        raiz.removeChildNode(viejo)
    grupo = raiz.insertGroup(0, nombre)
    capas = []
    exceso = "Fuera de la parcela catastral" if comparacion.edificio else "Exceso: fuera de las parcelas catastrales"
    for geometria, titulo, color in ((comparacion.exceso, exceso, '#e03131'),
                                     (comparacion.defecto, "Defecto: parcela catastral sin cubrir", '#1971c2')):
        if geometria is not None:
            capas.append(estilos.capa_diferencia(geometria, comparacion.epsg, titulo, color))
    origen = gl.ResultadoLectura(version='CP 4.0', epsg=comparacion.epsg, elementos=list(comparacion.origen))
    titulo = "Catastro vigente (parcela)" if comparacion.edificio else "Catastro vigente (parcelas afectadas)"
    catastro = estilos.aplicar(gl.capa(origen, titulo),
                               {gl.PARCELA: estilos.COLOR_COLINDANTES}, campo_etiqueta='label')
    metadatos = catastro.metadata()
    metadatos.setRights([f"© {FUENTE_DGC}"])
    catastro.setMetadata(metadatos)
    capas.append(catastro)
    for capa in capas:
        proyecto.addMapLayer(capa, False)
        grupo.addLayer(capa)
    return capas
