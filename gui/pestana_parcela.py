"""
Pestaña «Parcela»: crea el GML de parcela catastral (INSPIRE CP 4.0) a partir de una capa de polígonos.

Flujo: capa (y si se quiere solo la selección) → campos de identificador y de número de parcela → tabla con una fila por
parcela, donde se pueden cambiar identificador, namespace y número → fecha, SRC y fichero → Crear GML.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import contextlib
import html
import os
import re

from qgis.core import Qgis, QgsApplication, QgsProject
from qgis.gui import QgsFieldComboBox, QgsFileWidget, QgsMapLayerComboBox
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QDateTime, QTime, QTimer, Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import alteraciones as alt
from ..core import validador
from ..core import capa_parcelas as cp
from ..core import geometria as geo
from ..core import gml_lector as gl
from ..core import gml_parcela as gp
from ..core import refcat
from ..core.ficheros import misma_ruta
from ..core.incidencias import AVISO, ERROR, INFO
from . import desplazable
from .bloque_division import BloqueDivision
from .pestana_validar import cargar

COL_N, COL_ID, COL_NS, COL_LABEL, COL_AREA, COL_ESTADO = range(6)
CABECERAS = ['Nº', 'Identificador (localId)', 'Namespace', 'Nº parcela', 'Sup. m²', 'Estado']
AUTOMATICO = 0  #Dato del combo de SRC para «automático»
#Máximo de parcelas que se cargan en la tabla. La Sede admite como mucho 30 parcelas resultantes por operación;
#con una capa grande (p. ej. un municipio entero) hay que seleccionar las parcelas: cargarla entera bloqueaba QGIS.
PROPIEDAD_TERRITORIO = 'catastral_gml_tools/territorio'  #La pone la pestaña Descargar en las capas de Navarra
MAX_FILAS = 100


def miles(numero):
    """Entero con punto de miles, como se escribe en España: 12345 → 12.345."""
    return f"{numero:,}".replace(',', '.')


class PestanaParcela(QWidget):
    """Contenido de la pestaña Parcela. dock es el panel, que muestra los avisos en su barra."""

    def __init__(self, dock, parent=None):
        super().__init__(parent)
        self.dock = dock
        self.filas = []
        self.demasiadas = False
        self.areas = []  #Superficie de cada fila en el SRC del GML (la calcula actualizar_superficies)
        self.incidencias_alteracion = []
        self.filas_capa = []
        self.labels_auto = []  #Por fila: True si el nº de parcela lo ha puesto el plugin (se recalcula al cambiar el id)
        self.ultimo_gml = ''
        self.capa_conectada = None
        self.alteracion_auto = True   #El tipo de alteración lo propone el plugin (hasta que el usuario elige uno)
        self.manuales = {}            #fid → {columna: valor} que ha escrito el usuario en la tabla (se conservan al recargar)
        self.antes_union = None       #Estado de la tabla antes de «Unir seleccionadas» (para volver a él con Ctrl+Z)
        self.editando = False         #True mientras el plugin edita la capa (no se recarga por cada señal)
        self.matriz_fid = None        #Parcela elegida con «Es la matriz» (por su fid)
        self.destino_automatico = ''  #Último nombre de fichero propuesto (si el usuario no lo cambia, sigue a la capa)  #Capa cuya selección se sigue (para desconectarla al cambiar)
        self.construir()
        activa = self.dock.iface.activeLayer() if self.dock.iface is not None else None
        #Se empieza por la capa activa si es de polígonos; si no, sin capa (no la primera del proyecto)
        self.capaCombo.setLayer(activa if cp.es_capa_poligonos(activa) else None)
        self.conectar()
        self.cambiar_capa()  #La capa que el combo ya muestra al abrir el panel (sin esto no se proponen los campos)

    # ------------------------------------------------------------------ Interfaz

    def construir(self):
        principal = QVBoxLayout(self)
        principal.setContentsMargins(0, 0, 0, 0)
        formulario = QFormLayout()

        self.capaCombo = QgsMapLayerComboBox(self)
        self.capaCombo.setFilters(Qgis.LayerFilter.PolygonLayer)
        self.capaCombo.setAllowEmptyLayer(True)  #Se puede dejar sin capa
        self.capaCombo.setToolTip("Capa de polígonos con las parcelas (cada polígono será una parcela del GML)")
        formulario.addRow("Capa", self.capaCombo)

        self.soloSeleccion = QCheckBox("Solo los seleccionados", self)
        self.soloSeleccion.setToolTip("Solo los elementos seleccionados en el mapa (o en la tabla de atributos) de la capa")
        formulario.addRow("", self.soloSeleccion)

        self.campoId = QgsFieldComboBox(self)
        self.campoId.setAllowEmptyFieldName(True)
        self.campoId.setToolTip("Campo con la referencia catastral o el identificador de cada parcela.\n"
                                "Si se deja vacío, se numeran como Parcela_1, Parcela_2…")
        formulario.addRow("Identificador", self.campoId)

        self.campoLabel = QgsFieldComboBox(self)
        self.campoLabel.setAllowEmptyFieldName(True)
        self.campoLabel.setToolTip("Campo con el número de parcela que se ve en el plano (opcional).\n"
                                   "Si se deja vacío, se deduce de la referencia catastral")
        formulario.addRow("Nº de parcela", self.campoLabel)

        self.alteracion = QComboBox(self)
        for tipo in alt.TIPOS:
            self.alteracion.addItem(alt.NOMBRES[tipo], tipo)
            self.alteracion.setItemData(self.alteracion.count() - 1, alt.AYUDA[tipo], Qt.ItemDataRole.ToolTipRole)
        self.alteracion.setToolTip("Tipo de alteración: el plugin propone identificadores y namespaces y comprueba que "
                                   "encajan con lo que espera la Sede")
        fila_alteracion = QHBoxLayout()
        fila_alteracion.addWidget(self.alteracion, 1)
        self.matrizBoton = QPushButton("Es la matriz", self)
        self.matrizBoton.setToolTip("Segregación o agregación: la parcela elegida en la tabla es la que conserva la referencia "
                                    "catastral (por defecto, la mayor). La escritura puede designar como matriz el resto menor")
        self.matrizBoton.setEnabled(False)
        fila_alteracion.addWidget(self.matrizBoton)
        formulario.addRow("Alteración", fila_alteracion)
        principal.addLayout(formulario)
        self.division = BloqueDivision(self, self)  #Fase 10: dividir la parcela seleccionada (plegado)
        principal.addWidget(self.division)

        self.tabla = desplazable.TablaFlexible(0, len(CABECERAS), self)
        self.tabla.setHorizontalHeaderLabels(CABECERAS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)  #Todas se pueden ensanchar arrastrando el borde
        cabecera.setStretchLastSection(True)
        cabecera.setMinimumSectionSize(40)
        self.tabla.setToolTip("Puede cambiar el identificador, el namespace y el número de parcela de cada fila.\n"
                              "SDGC: la parcela existe en el Catastro y se conserva su referencia (14 caracteres).\n"
                              "LOCAL: parcela nueva con un identificador propio (Seg_1, Div_1_1…).")
        self.tabla.setMinimumHeight(desplazable.ALTO_MINIMO_TABLA)  #En pantallas bajas el panel se desplaza, no la aplasta
        principal.addWidget(self.tabla, 1)

        self.resumen = QLabel(self)
        self.resumen.setWordWrap(True)
        principal.addWidget(self.resumen)
        self.resumen.linkActivated.connect(self.enlace_resumen)
        self.alteracionInfo = QLabel(self)
        self.alteracionInfo.setWordWrap(True)
        self.alteracionInfo.linkActivated.connect(self.alternar_notas)
        self.notas_abiertas = False  #Las notas informativas de la operación, plegadas (se ven los avisos)
        self.alteracionInfo.hide()
        principal.addWidget(self.alteracionInfo)

        salida = QFormLayout()
        ahora = QDateTime.currentDateTime()
        ahora.setTime(QTime(ahora.time().hour(), ahora.time().minute()))  #Al minuto, sin segundos
        self.fecha = QDateTimeEdit(ahora, self)
        self.fecha.setCalendarPopup(True)
        self.fecha.setDisplayFormat('dd/MM/yyyy HH:mm')
        self.fecha.setToolTip("Fecha y hora del GML (beginLifespanVersion), en el formato AAAA-MM-DDThh:mm:ss")
        salida.addRow("Fecha y hora", self.fecha)

        self.srcCombo = QComboBox(self)
        self.srcCombo.addItem("Automático (según la posición)", AUTOMATICO)
        for epsg, nombre in ((25829, 'ETRS89 / UTM 29N'), (25830, 'ETRS89 / UTM 30N'), (25831, 'ETRS89 / UTM 31N'),
                             (32628, 'WGS84 / UTM 28N (Canarias)')):
            self.srcCombo.addItem(f"EPSG:{epsg} · {nombre}", epsg)
        self.srcCombo.setToolTip("SRC del GML. La Sede solo admite estos cuatro; la capa se transforma si hace falta")
        salida.addRow("SRC", self.srcCombo)

        self.destino = QgsFileWidget(self)
        self.destino.setStorageMode(QgsFileWidget.StorageMode.SaveFile)
        self.destino.setFilter("GML (*.gml)")
        self.destino.setDialogTitle("Guardar el GML de parcela")
        salida.addRow("Fichero", self.destino)
        principal.addLayout(salida)

        botones = QHBoxLayout()
        self.recargarBoton = QPushButton(QgsApplication.getThemeIcon('/mActionRefresh.svg'), "Recargar", self)
        self.recargarBoton.setToolTip("Vuelve a leer las parcelas de la capa (se pierden los cambios hechos en la tabla)")
        self.crearBoton = QPushButton(QgsApplication.getThemeIcon('/mActionFileSave.svg'), "Crear GML", self)
        self.crearBoton.setDefault(True)
        botones.addWidget(self.recargarBoton)
        self.unirBoton = QPushButton(QgsApplication.getThemeIcon('/mActionMergeFeatures.svg'), "Unir parcelas", self)
        self.unirBoton.setToolTip("Une en una sola parcela las parcelas seleccionadas en el mapa (agregación o agrupación).\n"
                                  "Para unir varios ficheros GML ya hechos en uno, use Utilidades › 1. Unir ficheros GML.\n"
                                  "La mayor conserva sus datos. La capa queda en edición: Ctrl+Z deshace la unión")
        self.unirBoton.setEnabled(False)
        botones.addWidget(self.unirBoton)
        botones.addStretch(1)
        botones.addWidget(self.crearBoton)
        principal.addLayout(botones)

    def conectar(self):
        """Señales conectadas a métodos (nunca a lambdas: cerraban QGIS 4)."""
        self.capaCombo.layerChanged.connect(self.cambiar_capa)
        #Al quitar del proyecto la capa elegida, el combo pasa solo a otra sin que siempre llegue layerChanged: los
        #campos se quedaban sin capa (o con los de la anterior). Se comprueba después de quitarla
        QgsProject.instance().layersRemoved.connect(self.capas_quitadas)
        self.soloSeleccion.toggled.connect(self.recargar)
        self.campoId.fieldChanged.connect(self.recargar)
        self.campoLabel.fieldChanged.connect(self.recargar)
        self.srcCombo.currentIndexChanged.connect(self.actualizar_superficies)
        self.alteracion.currentIndexChanged.connect(self.alteracion_cambiada)
        self.tabla.itemSelectionChanged.connect(self.seleccionar_en_capa)
        self.tabla.itemSelectionChanged.connect(self.actualizar_matriz)
        self.matrizBoton.clicked.connect(self.marcar_matriz)
        self.tabla.itemChanged.connect(self.celda_cambiada)
        self.recargarBoton.clicked.connect(self.recargar_desde_capa)
        self.unirBoton.clicked.connect(self.unir_seleccionadas)
        self.crearBoton.clicked.connect(self.crear_gml)

    # ------------------------------------------------------------------ Capa y tabla

    def usar_capa(self, capa):
        """Elige una capa desde fuera de la pestaña (p. ej. la parcela recién descargada)."""
        if cp.es_capa_poligonos(capa):
            self.soloSeleccion.setChecked(False)
            self.capaCombo.setLayer(capa)  #Lanza cambiar_capa por la señal layerChanged

    def capa(self):
        capa = self.capaCombo.currentLayer()
        return capa if cp.es_capa_poligonos(capa) else None

    def capas_quitadas(self, *args):
        if not sip.isdeleted(self):
            QTimer.singleShot(0, self.comprobar_capa)

    def comprobar_capa(self):
        """
        Si los campos no son de la capa que muestra el combo, se rehace todo como al elegirla. Si es porque la capa en
        uso se ha quitado del proyecto, se dice: el combo pasa solo a otra capa y, sin aviso, «Crear GML» haría el de esa
        (batería de casos, 19/10/2026).
        """
        if sip.isdeleted(self):
            return
        if self.campoId.layer() is not self.capa():
            anterior = getattr(self, 'nombre_capa', '')
            self.cambiar_capa()
            if anterior:
                actual = self.capa()
                self.dock.notify(f"La capa «{anterior}» se ha quitado del proyecto"
                                 + (f": ahora está elegida «{actual.name()}». Compruebe la tabla antes de crear el GML"
                                    if actual is not None else ""), Qgis.MessageLevel.Warning, 0)

    def cambiar_capa(self, *args):
        capa = self.capa()
        self.nombre_capa = capa.name() if capa is not None else ''
        self.manuales, self.antes_union, self.matriz_fid = {}, None, None  #Lo escrito y la unión eran de la otra capa
        self.seguir_seleccion(capa)
        self.actualizar_unir()
        self.division.actualizar()
        #Sin señales mientras se rellenan los campos: si no, la tabla se recalculaba 3 o 4 veces seguidas
        for widget in (self.campoId, self.campoLabel, self.soloSeleccion):
            widget.blockSignals(True)
        self.campoId.setLayer(capa)
        self.campoLabel.setLayer(capa)
        #En una capa grande con elementos seleccionados se trabaja con la selección; en otra capa, con todos (la casilla
        #no se queda marcada de la capa anterior: AU-46)
        self.soloSeleccion.setChecked(capa is not None and capa.featureCount() > MAX_FILAS
                                      and capa.selectedFeatureCount() > 0)
        if capa is not None:
            #Propone el campo de identificador si hay uno con nombre habitual
            for nombre in ('refcat', 'ref_catastral', 'referencia', 'nationalCadastralReference', 'localId', 'localid', 'rc'):
                if capa.fields().indexOf(nombre) >= 0:
                    self.campoId.setField(nombre)
                    break
            self.proponer_fichero(capa)
            if self.dock.tabWidget.currentWidget() is getattr(self.dock, 'tabParcela', None):
                self.activar_capa()
        for widget in (self.campoId, self.campoLabel, self.soloSeleccion):
            widget.blockSignals(False)
        self.recargar()

    def proponer_fichero(self, capa):
        """
        Propone el fichero de salida con el nombre de la capa (sin espacios ni símbolos), en la carpeta que ya hubiera
        elegida o en la del proyecto. Se llama al cambiar de capa: el nombre que haya escrito el usuario vale para su
        capa, no para la siguiente (si no, el GML de otra capa acababa en el fichero de la anterior; prueba del 14/10).
        """
        actual = self.destino.filePath().strip()
        carpeta = os.path.dirname(actual) if actual else (os.path.dirname(cp.fichero_de_capa(capa)) or QgsProject.instance().homePath()
                                                          or os.path.expanduser('~'))
        nombre = re.sub(r'[^0-9A-Za-z_.-]+', '_', capa.name()).strip('._') or 'parcelas'
        self.destino_automatico = os.path.join(carpeta, f"{nombre}.gml")
        if misma_ruta(self.destino_automatico, cp.fichero_de_capa(capa)):  #Nunca el fichero del que sale la capa (AU-09)
            self.destino_automatico = os.path.join(carpeta, f"{nombre}_nuevo.gml")
        self.destino.setFilePath(self.destino_automatico)

    def seguir_seleccion(self, capa):
        """Con «Solo los seleccionados», la tabla se actualiza al seleccionar parcelas en el mapa."""
        anterior = self.capa_conectada
        if anterior is not None and not sip.isdeleted(anterior):
            for senal, metodo in self.senales(anterior):
                with contextlib.suppress(TypeError, RuntimeError):  #Ya desconectada
                    senal.disconnect(metodo)
        self.capa_conectada = capa
        if capa is not None:
            for senal, metodo in self.senales(capa):
                senal.connect(metodo)

    def senales(self, capa):
        """Señales de la capa que sigue la tabla: selección y ediciones (dibujar, dividir, deshacer…)."""
        return [(capa.selectionChanged, self.seleccion_cambiada), (capa.featureAdded, self.capa_editada),
                (capa.featuresDeleted, self.capa_editada), (capa.geometryChanged, self.capa_editada),
                (capa.attributeValueChanged, self.capa_editada), (capa.afterRollBack, self.capa_editada)]

    def activar_capa(self):
        """
        Hace activa en el panel Capas la capa de la pestaña: la herramienta de selección del mapa y Ctrl+Z actúan sobre la
        capa activa. Al validar un GML, su vista pasa a ser la activa y, de vuelta en Parcela, seleccionar o deshacer no
        llegaba a la capa de trabajo (prueba a mano del 14/10).
        """
        capa, iface = self.capa(), self.dock.iface
        if capa is None or iface is None or not hasattr(iface, 'setActiveLayer'):
            return
        if iface.activeLayer() is not capa:
            iface.setActiveLayer(capa)

    def estado_antes_de_editar(self):
        """Lo que hay que devolver a la tabla si se deshace una edición del plugin (unir o dividir)."""
        return {'tipo': self.tipo_alteracion(), 'auto': self.alteracion_auto, 'solo': self.soloSeleccion.isChecked(),
                'presentes': [], 'ausentes': []}

    def capa_editada(self, *args):
        """
        Al editar la capa (dibujar, dividir, mover vértices, Ctrl+Z…) la tabla se recarga sola, conservando lo que haya
        escrito el usuario. Si se deshace «Unir seleccionadas», la tabla vuelve a como estaba antes de unir.
        """
        if sip.isdeleted(self) or self.editando:
            return
        capa = self.capa()
        if (self.antes_union is not None and capa is not None  #La unión o la división se han deshecho (Ctrl+Z)
                and all(capa.getFeature(fid).isValid() for fid in self.antes_union['presentes'])
                and not any(capa.getFeature(fid).isValid() for fid in self.antes_union['ausentes'])):
            estado, self.antes_union = self.antes_union, None
            self.soloSeleccion.blockSignals(True)
            self.soloSeleccion.setChecked(estado['solo'])
            self.soloSeleccion.blockSignals(False)
            self.poner_alteracion(estado['tipo'], estado['auto'])
        self.recargar()
        self.actualizar_unir()
        self.division.actualizar()

    def seleccion_cambiada(self, *args):
        if sip.isdeleted(self):
            return
        self.actualizar_unir()
        self.division.actualizar()  #Lados de la parcela seleccionada
        if self.soloSeleccion.isChecked():
            self.recargar()

    def actualizar_unir(self):
        capa = self.capa()
        self.unirBoton.setEnabled(capa is not None and capa.selectedFeatureCount() >= 2)

    def unir_seleccionadas(self, *args):
        """Une las parcelas seleccionadas en una y propone agregación o agrupación en el asistente."""
        self.dock.messageBar.clearWidgets()
        capa = self.capa()
        antes = self.estado_antes_de_editar()
        antes['presentes'] = list(capa.selectedFeatureIds()) if capa is not None else []  #Al deshacer, vuelven
        self.editando = True  #La unión cambia y borra entidades: se recarga una vez al final, no por cada señal
        try:
            fid, tipo, incidencias = cp.unir_seleccionadas(capa, self.campoId.currentField())
        finally:
            self.editando = False
        if fid is None:
            self.dock.warn("\n".join(i.mensaje for i in incidencias))
            return None
        self.antes_union = antes  #Con Ctrl+Z la tabla vuelve a este estado (capa_editada)
        if tipo:
            #Agregación o agrupación de parcelas catastrales: el GML lleva solo la parcela resultante (que queda
            #seleccionada), así que la tabla pasa a «Solo los seleccionados»
            self.soloSeleccion.blockSignals(True)
            self.soloSeleccion.setChecked(True)
            self.soloSeleccion.blockSignals(False)
            self.recargar()
            self.poner_alteracion(tipo, False)
            vista = (". La tabla muestra solo la parcela unida (desmarque «Solo los seleccionados» para ver "
                     "todas)")
            propuesta = f" · propuesta: {alt.NOMBRES[tipo]}"
        else:
            self.recargar()  #Retoque del dibujo: la tabla sigue con todas sus parcelas y la operación se vuelve a deducir
            vista, propuesta = '', ''
        self.actualizar_unir()
        notas = ''.join(f". {i.mensaje}" for i in incidencias[1:] if i.nivel == INFO)
        texto = (incidencias[0].mensaje + f"{propuesta}{notas}{vista}. La capa queda en edición (Ctrl+Z deshace también "
                 "la tabla; guarde la capa para conservarla)")
        avisos = [i.mensaje for i in incidencias if i.nivel == AVISO]
        if avisos:  #El dibujo no encaja: aviso en naranja, no en verde
            self.dock.notify(" ".join(avisos) + ". " + texto, Qgis.MessageLevel.Warning, 0)
        else:
            self.dock.success(texto)
        return fid

    def numero_parcelas(self, capa):
        return capa.selectedFeatureCount() if self.soloSeleccion.isChecked() else capa.featureCount()

    def recargar_desde_capa(self, *args):
        """Botón Recargar: la tabla vuelve a lo que dice la capa (se olvida lo escrito a mano)."""
        self.manuales = {}
        self.recargar()

    def poner_alteracion(self, tipo, automatica):
        """Elige el tipo de alteración desde el plugin (automatica: lo ha deducido él, y puede volver a deducirlo)."""
        self.alteracion.blockSignals(True)
        self.alteracion.setCurrentIndex(alt.TIPOS.index(tipo))
        self.alteracion.blockSignals(False)
        self.alteracion_auto = automatica
        self.actualizar_matriz()
        self.aplicar_alteracion()
        self.actualizar_superficies()

    def recargar(self, *args):
        capa = self.capa()
        self.demasiadas = capa is not None and self.numero_parcelas(capa) > MAX_FILAS
        if self.demasiadas:
            self.filas = []  #No se lee la capa entera: bloquearía QGIS
        else:
            self.filas = cp.leer_capa(capa, self.soloSeleccion.isChecked(), self.campoId.currentField(),
                                      self.campoLabel.currentField()) if capa is not None else []
        #Automático = el que propone el plugin (no viene del campo elegido o el campo estaba vacío)
        self.labels_auto = [f.label == gp.label_por_defecto(f.local_id, f.namespace) for f in self.filas]
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(len(self.filas))
        for i, fila in enumerate(self.filas):
            numero = QTableWidgetItem(str(i + 1))
            numero.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            numero.setData(Qt.ItemDataRole.UserRole, fila.fid)
            self.tabla.setItem(i, COL_N, numero)
            self.tabla.setItem(i, COL_ID, QTableWidgetItem(fila.local_id))
            combo = QComboBox(self.tabla)  #Con padre: Python no lo borra
            combo.addItems([gp.SDGC, gp.LOCAL])
            combo.setCurrentText(fila.namespace)
            combo.currentTextChanged.connect(self.namespace_cambiado)
            desplazable.proteger(combo)  #La rueda desplaza la tabla, no cambia el namespace
            self.tabla.setCellWidget(i, COL_NS, combo)
            self.tabla.setItem(i, COL_LABEL, QTableWidgetItem(fila.label))
            for col in (COL_AREA, COL_ESTADO):
                item = QTableWidgetItem('')
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.tabla.setItem(i, col, item)
            self.tabla.item(i, COL_AREA).setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            estado = 'Varias partes' if fila.partes > 1 else ('Sin geometría' if fila.partes == 0 else '')
            self.tabla.item(i, COL_ESTADO).setText(estado)
        self.tabla.blockSignals(False)
        self.ajustar_columnas()
        self.areas = []
        self.filas_capa = [f.local_id for f in self.filas]  #Identificadores tal como vienen de la capa
        #Fila matriz elegida por el usuario (None: la mayor); se sigue por su fid aunque cambie el orden de la tabla
        fids = [f.fid for f in self.filas]
        self.matriz = fids.index(self.matriz_fid) if getattr(self, 'matriz_fid', None) in fids else None
        self.aplicar_alteracion()  #Si hay un tipo de alteración elegido, se propone también para la capa nueva
        self.aplicar_manuales()
        self.actualizar_superficies()

    def aplicar_manuales(self):
        """Vuelve a poner en la tabla lo que el usuario había escrito a mano en cada parcela (por su fid)."""
        if not self.manuales:
            return
        self.tabla.blockSignals(True)
        for i, fila in enumerate(self.filas):
            valores = self.manuales.get(fila.fid, {})
            for columna in (COL_ID, COL_LABEL):
                if columna in valores:
                    self.tabla.item(i, columna).setText(valores[columna])
                    if columna == COL_LABEL:
                        self.labels_auto[i] = not valores[columna]
            combo = self.tabla.cellWidget(i, COL_NS)
            #El namespace elegido a mano o, si solo se escribió el identificador, el que le corresponde (SDGC si es RC)
            namespace = valores.get(COL_NS) or (cp.namespace_propuesto(valores[COL_ID]) if valores.get(COL_ID) else '')
            if namespace and combo is not None:
                combo.blockSignals(True)
                combo.setCurrentText(namespace)
                combo.blockSignals(False)
        self.tabla.blockSignals(False)
        for i in range(len(self.filas)):
            if COL_LABEL not in self.manuales.get(self.filas[i].fid, {}):
                self.actualizar_label(i)

    def ajustar_columnas(self):
        """Ancho de cada columna según su contenido (con un mínimo para el identificador); luego se puede cambiar a mano."""
        self.tabla.resizeColumnsToContents()
        self.tabla.setColumnWidth(COL_ID, max(self.tabla.columnWidth(COL_ID), 130))
        self.tabla.setColumnWidth(COL_NS, max(self.tabla.columnWidth(COL_NS), 90))

    def epsg_salida(self):
        capa = self.capa()
        elegido = self.srcCombo.currentData()
        if elegido != AUTOMATICO:
            return elegido
        return cp.epsg_para(self.filas, capa.crs()) if capa is not None else None

    def actualizar_superficies(self, *args):
        capa = self.capa()
        epsg = self.epsg_salida()
        total = 0
        self.areas = []
        for i, fila in enumerate(self.filas):
            area = cp.area_m2(fila, capa.crs(), epsg) if capa is not None else None
            self.areas.append(area)
            self.tabla.item(i, COL_AREA).setText('' if area is None else miles(area))
            total += area or 0
            self.marcar_namespace(i)
        self.mostrar_alteracion()
        if not self.filas:
            if capa is None:
                texto = "<i>Elija una capa de polígonos con las parcelas.</i>"
            elif self.demasiadas:
                texto = (f"<i>La capa tiene {miles(self.numero_parcelas(capa))} parcelas: seleccione en el mapa las que "
                         f"quiera incluir (máximo {MAX_FILAS}) y marque «Solo los seleccionados».</i>")
            else:
                texto = "<i>La capa no tiene polígonos (o no hay ninguno seleccionado).</i>"
            self.resumen.setText(texto)
            return
        sdgc = sum(1 for i in range(len(self.filas)) if self.namespace_fila(i) == gp.SDGC)
        n = len(self.filas)
        texto = f"{n} parcela{'s' if n != 1 else ''} ({sdgc} SDGC, {n - sdgc} LOCAL) · {miles(total)} m²"
        if epsg:
            origen = geo.epsg_de(capa.crs())
            texto += f" · EPSG:{epsg}" + ('' if origen == epsg else f" (se transforma desde {capa.crs().authid()})")
        problema = cp.src_incorrecto(capa)  #UTM en una capa marcada como geográfica, o sin SRC (AU-06)
        if problema:
            texto += f"<br><span style='color:#c92a2a'>✖ {problema}</span>"
        else:
            for aviso in cp.avisos_src(self.filas, capa.crs(), epsg, [f.local_id for f in self.filas]):  #AU-30, AU-32
                texto += f"<br><span style='color:#e67700'>⚠ {aviso.mensaje}</span>"
        if not sdgc and not any(refcat.es_rc_parcela(i) for i in self.filas_capa):
            otro = cp.campo_con_rc(capa, self.campoId.currentField())
            if otro:  #El identificador elegido no tiene referencias catastrales y otro campo sí
                elegido = self.campoId.currentField() or 'ninguno'
                texto += (f"<br><span style='color:#e67700'>⚠ El campo «{html.escape(otro)}» tiene referencias "
                          f"catastrales y el identificador elegido («{html.escape(elegido)}») no.</span> "
                          f"<a href='campo:{html.escape(otro)}'>Usar «{html.escape(otro)}»</a>")
        self.resumen.setText(texto)

    def enlace_resumen(self, enlace):
        """Enlace «Usar «campo»» del resumen: elige ese campo como identificador."""
        if enlace.startswith('campo:'):
            self.campoId.setField(enlace[len('campo:'):])

    # ------------------------------------------------------------------ Asistente de alteraciones

    def tipo_alteracion(self):
        return self.alteracion.currentData() or alt.SIN_INDICAR

    def actualizar_matriz(self, *args):
        filas = self.tabla.selectionModel().selectedRows() if self.tabla.selectionModel() else []
        self.matrizBoton.setEnabled(self.tipo_alteracion() in (alt.SEGREGACION, alt.AGREGACION) and len(filas) == 1)

    def marcar_matriz(self, *args):
        """La fila elegida conserva la referencia catastral (AU-24)."""
        filas = self.tabla.selectionModel().selectedRows()
        if len(filas) != 1:
            return
        self.matriz = filas[0].row()
        self.matriz_fid = self.filas[self.matriz].fid if self.matriz < len(self.filas) else None
        self.aplicar_alteracion()
        self.actualizar_superficies()

    def alteracion_cambiada(self, *args):
        """Al elegir el tipo de alteración se proponen identificadores y namespaces (respetando los del usuario)."""
        self.alteracion_auto = False  #Lo ha elegido el usuario: el plugin ya no lo cambia al recargar
        self.actualizar_matriz()
        self.aplicar_alteracion()
        self.actualizar_superficies()

    def aplicar_alteracion(self):
        tipo = self.tipo_alteracion()
        if tipo == alt.SIN_INDICAR or not self.filas:
            return
        ids = [self.tabla.item(i, COL_ID).text().strip() for i in range(len(self.filas))]
        areas = getattr(self, 'areas', []) or [None if f.geometria is None else f.geometria.area() for f in self.filas]
        if len(areas) != len(ids):
            areas = [None if f.geometria is None else f.geometria.area() for f in self.filas]
        self.tabla.blockSignals(True)
        #La referencia original se toma de la capa: la tabla puede haberla perdido (p. ej. tras elegir «División»)
        rc = next((i for i in self.filas_capa if refcat.es_rc_parcela(i)), '')
        for i, (local_id, namespace) in enumerate(alt.proponer(tipo, ids, areas, rc, getattr(self, 'matriz', None))):
            self.tabla.item(i, COL_ID).setText(local_id)
            combo = self.tabla.cellWidget(i, COL_NS)
            if combo is not None:
                combo.blockSignals(True)
                combo.setCurrentText(namespace)
                combo.blockSignals(False)
        self.tabla.blockSignals(False)
        for i in range(len(self.filas)):
            self.actualizar_label(i)

    def mostrar_alteracion(self):
        """Resumen de la operación elegida y avisos si la tabla no encaja con ella."""
        tipo = self.tipo_alteracion()
        n = len(self.filas)
        if not n:
            self.alteracionInfo.hide()
            self.incidencias_alteracion = []
            return
        if tipo == alt.SIN_INDICAR:  #Sin elegir: se dice qué operación deducirá la Sede de la tabla (NPO/NPP)
            self.incidencias_alteracion = []
            deducida = alt.deducir(self.filas_capa, [self.namespace_fila(i) for i in range(n)])
            if deducida:
                self.alteracionInfo.setText(f"<small>ℹ {deducida}</small>")
                self.alteracionInfo.setToolTip(alt.AYUDA[alt.SIN_INDICAR])
                self.alteracionInfo.show()
            else:
                self.alteracionInfo.hide()
            return
        ids = [self.tabla.item(i, COL_ID).text().strip() for i in range(n)]
        nss = [self.namespace_fila(i) for i in range(n)]
        areas = list(getattr(self, 'areas', [None] * n))
        self.incidencias_alteracion = alt.comprobar(tipo, ids, nss, areas)
        lineas = [f"<b>{alt.resumen(tipo, ids, nss, areas)}</b>"]
        #Los avisos (⚠) siempre a la vista; las notas informativas (ℹ), plegadas tras un enlace (con tantos textos, el
        #panel no cabía en una pantalla baja: prueba a mano del 14/10)
        notas = [i for i in self.incidencias_alteracion if i.nivel != AVISO]
        for inc in self.incidencias_alteracion:
            if inc.nivel == AVISO:
                lineas.append(f"<span style='color:#e67700'>⚠ {inc.mensaje}</span>")
        if not any(i.nivel == AVISO for i in self.incidencias_alteracion):
            lineas.insert(1, "<span style='color:#2b8a3e'>✔ Identificadores y namespaces de acuerdo con la operación</span>")
        if notas:
            n = len(notas)
            if self.notas_abiertas:
                lineas.append("<a href='notas'>ℹ Ocultar las notas ▾</a>")
                lineas += [f"<span style='color:#495057'>ℹ {inc.mensaje}</span>" for inc in notas]
            else:
                lineas.append(f"<a href='notas'>ℹ {n} nota{'s' if n != 1 else ''} sobre la operación ▸</a>")
        self.alteracionInfo.setText("<small>" + "<br>".join(lineas) + "</small>")
        self.alteracionInfo.setToolTip(alt.AYUDA[tipo])
        self.alteracionInfo.show()

    def alternar_notas(self, *args):
        """Enlace de las notas de la operación: las muestra u oculta."""
        self.notas_abiertas = not self.notas_abiertas
        self.mostrar_alteracion()

    def marcar_namespace(self, i):
        """Estado de la fila al momento si es SDGC sin referencia catastral (el GML no se crearía así)."""
        item = self.tabla.item(i, COL_ESTADO)
        if item is None:
            return
        local_id = self.tabla.item(i, COL_ID).text().strip()
        if self.namespace_fila(i) == gp.SDGC and not refcat.es_rc_exacta(local_id):
            item.setText("SDGC sin RC: use LOCAL")
            item.setForeground(Qt.GlobalColor.red)
            item.setToolTip("Con SDGC el identificador debe ser la referencia catastral de 14 caracteres; una parcela "
                            "nueva va como LOCAL")
        elif item.text() == "SDGC sin RC: use LOCAL":
            item.setText('')
            item.setToolTip('')

    def namespace_fila(self, i):
        combo = self.tabla.cellWidget(i, COL_NS)
        return combo.currentText() if combo is not None else gp.LOCAL

    def celda_cambiada(self, item):
        """
        Al cambiar el identificador se proponen de nuevo el namespace y, si no lo ha escrito el usuario, el nº de parcela.
        Si el usuario escribe el nº de parcela, se respeta.
        """
        fila = item.row()
        if not 0 <= fila < len(self.filas):
            return
        if item.column() in (COL_ID, COL_LABEL):  #Escrito por el usuario: se conserva al recargar la tabla
            self.manuales.setdefault(self.filas[fila].fid, {})[item.column()] = item.text().strip()
        if item.column() == COL_LABEL:
            self.labels_auto[fila] = not item.text().strip()
            if self.labels_auto[fila]:
                self.actualizar_label(fila)
        elif item.column() == COL_ID:
            texto = item.text().strip()
            rc = refcat.parcela_de(texto)
            if rc and rc != texto:  #RC escrita en minúsculas, con guiones o de inmueble: la de la parcela (AU-04, AU-05)
                self.tabla.blockSignals(True)
                item.setText(rc)
                self.tabla.blockSignals(False)
                texto = rc
            combo = self.tabla.cellWidget(fila, COL_NS)
            if combo is not None and texto:
                combo.blockSignals(True)
                combo.setCurrentText(cp.namespace_propuesto(texto))
                combo.blockSignals(False)
            self.actualizar_label(fila)
            self.actualizar_superficies()

    def namespace_cambiado(self, *args):
        """El combo que ha cambiado se busca por su fila (sin lambdas)."""
        combo = self.sender()
        for i in range(self.tabla.rowCount()):
            if self.tabla.cellWidget(i, COL_NS) is combo:
                if i < len(self.filas):
                    self.manuales.setdefault(self.filas[i].fid, {})[COL_NS] = combo.currentText()
                self.actualizar_label(i)
                break
        self.actualizar_superficies()

    def actualizar_label(self, fila):
        """Recalcula el nº de parcela de la fila si es el automático."""
        if not self.labels_auto[fila]:
            return
        local_id = self.tabla.item(fila, COL_ID).text().strip()
        item = self.tabla.item(fila, COL_LABEL)
        self.tabla.blockSignals(True)
        item.setText(gp.label_por_defecto(local_id, self.namespace_fila(fila)) if local_id else '')
        self.tabla.blockSignals(False)

    def filas_editadas(self):
        """Las filas con lo que el usuario haya cambiado en la tabla."""
        for i, fila in enumerate(self.filas):
            fila.local_id = self.tabla.item(i, COL_ID).text().strip()
            fila.namespace = self.namespace_fila(i)
            fila.label = self.tabla.item(i, COL_LABEL).text().strip()
        return self.filas

    def seleccionar_en_capa(self):
        """Al elegir filas de la tabla se seleccionan esas parcelas en la capa (para verlas en el mapa)."""
        capa = self.capa()
        if capa is None:
            return
        fids = [self.tabla.item(i.row(), COL_N).data(Qt.ItemDataRole.UserRole)
                for i in self.tabla.selectionModel().selectedRows()]
        if fids and not self.soloSeleccion.isChecked():  #Con «solo seleccionados» cambiar la selección vaciaría la tabla
            capa.selectByIds(fids)

    # ------------------------------------------------------------------ Crear el GML

    def marcar_estados(self, incidencias):
        """Pone en la columna Estado el primer problema de cada fila."""
        por_id = {}
        for inc in incidencias:
            if inc.elemento and inc.nivel in (ERROR, AVISO):
                por_id.setdefault(inc.elemento, inc)
        for i, fila in enumerate(self.filas):
            inc = por_id.get(fila.local_id) or por_id.get(f"fila {i + 1}")
            item = self.tabla.item(i, COL_ESTADO)
            item.setText(inc.mensaje if inc else 'Correcta')
            item.setToolTip(inc.mensaje if inc else '')
            item.setForeground(Qt.GlobalColor.red if inc and inc.nivel == ERROR else Qt.GlobalColor.darkGreen)

    def crear_gml(self, *args):
        self.dock.messageBar.clearWidgets()
        capa = self.capa()
        if capa is None:
            self.dock.warn("Elija una capa de polígonos")
            return
        if cp.src_incorrecto(capa):
            self.dock.warn(cp.src_incorrecto(capa))
            return
        territorio = capa.customProperty(PROPIEDAD_TERRITORIO)
        if territorio:  #Capa descargada de un catastro foral: el GML de la Sede de la DGC no sirve allí
            self.dock.warn(f"La capa es de {territorio}, que tiene catastro propio: el GML para la Sede Electrónica de la "
                           f"Dirección General del Catastro no sirve para sus trámites. Consulte al catastro de {territorio}.")
            return
        if not self.filas:
            if self.demasiadas:
                self.dock.warn(f"Demasiadas parcelas: seleccione en el mapa las que quiera incluir (máximo {MAX_FILAS}) "
                               "y marque «Solo los seleccionados»")
            else:
                self.dock.warn("No hay parcelas: la capa está vacía o no hay elementos seleccionados")
            return
        ruta = self.destino.filePath().strip()
        if not ruta:
            self.dock.warn("Indique el fichero GML de salida")
            return
        if not ruta.lower().endswith('.gml'):
            ruta += '.gml'
        if not os.path.isdir(os.path.dirname(os.path.abspath(ruta))):
            self.dock.warn(f"No existe la carpeta de destino: {os.path.dirname(ruta)}")
            return
        epsg = self.epsg_salida()
        if epsg is None:
            self.dock.warn("No se ha podido determinar el SRC del GML: elíjalo en la lista")
            return
        filas = self.filas_editadas()
        fecha = self.fecha.dateTime().toPyDateTime().replace(second=0, microsecond=0)
        ok, incidencias = gp.escribir(ruta, cp.a_parcelas_gml(filas, capa.crs(), epsg), epsg, fecha,
                                      origenes=[cp.fichero_de_capa(capa)])
        self.marcar_estados(incidencias)
        problemas = [str(i) for i in incidencias if i.nivel in (ERROR, AVISO)]
        problemas += [a.mensaje for a in cp.avisos_src(filas, capa.crs(), epsg, [f.local_id for f in filas])]
        if ok:  #Los avisos del asistente de alteraciones no impiden crear el GML, pero se recuerdan
            self.mostrar_alteracion()
            problemas += [i.mensaje for i in getattr(self, 'incidencias_alteracion', []) if i.nivel == AVISO]
            #Y los que vería Validar en el fichero (p. ej. más de 30 parcelas: la Sede no lo tramita sola; batería de
            #casos, 19/10/2026: se creaba sin decirlo)
            problemas += [i.mensaje for i in validador.validar(ruta).avisos
                          if not any(i.mensaje in p for p in problemas)]
        if not ok:
            errores = [str(i) for i in incidencias if i.nivel == ERROR]
            texto = (f"No se ha creado el GML: {errores[0]}" if len(errores) == 1 else
                     "No se ha creado el GML: corrija estos errores\n\n" + "\n".join(f"- {p}" for p in problemas))
            self.dock.notify(texto,
                             Qgis.MessageLevel.Critical, 0)
            return
        self.ultimo_gml = ruta
        resumen = f"GML creado: {os.path.basename(ruta)} · {len(filas)} parcelas · EPSG:{epsg}"
        if self.tipo_alteracion() != alt.SIN_INDICAR:
            resumen += f" · {alt.NOMBRES[self.tipo_alteracion()]}"
        else:  #Sin indicar: la que deducirá la Sede de la tabla
            deducida = alt.operacion_deducida(self.filas_capa, [f.namespace for f in filas])
            if deducida:
                resumen += f" · la Sede propondrá: {alt.NOMBRES[deducida].lower()}"
        self.dock.gml_creado(ruta)
        self.dock.success(resumen, [("Validar", self.validar), ("Abrir carpeta", self.abrir_carpeta),
                                    ("Cargar en el mapa", self.cargar_en_mapa)],
                          detalles=problemas)

    def validar(self, *args):
        """Abre el GML creado en la pestaña Validar (comprobaciones de la Sede y comparación con el Catastro)."""
        if self.ultimo_gml:
            self.dock.abrir_en_validar(self.ultimo_gml)

    def abrir_carpeta(self, *args):
        if self.ultimo_gml:
            self.dock.open_path(os.path.dirname(self.ultimo_gml))

    def cargar_en_mapa(self, *args):
        """
        Carga el GML creado en el mapa, leído con el lector del plugin (como lo leerá la Sede y sin crear el fichero .gfs
        que dejaba GDAL junto al GML), para compararlo con la capa original.
        """
        if not self.ultimo_gml or not os.path.isfile(self.ultimo_gml):
            return None
        resultado = gl.leer(self.ultimo_gml)
        if not resultado.elementos:
            self.dock.warn("No se ha podido leer el GML creado")
            return None
        return cargar(resultado, self.ultimo_gml, self.dock.iface)
