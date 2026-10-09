"""
Pestaña «Edificio»: crea el GML de edificio (modelo simplificado de la DGC: edificios y piscinas) para el Informe
Catastral de Ubicación de las Construcciones (ICUC), a partir de una capa con las huellas.

Flujo: capa (dibujada o la «Construcciones» descargada) → referencia de la parcela → tabla con una fila por
construcción (tipo y plantas) → estado, fecha, SRC y fichero → Crear GML. Los identificadores se proponen según el
formato de la DGC (RC, RC_Edificio_N, RC_Piscina_N) y se pueden cambiar en la tabla.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import contextlib
import os
import re

from qgis.core import Qgis, QgsApplication, QgsProject
from qgis.gui import QgsFieldComboBox, QgsFileWidget, QgsMapLayerComboBox
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QDateTime, Qt, QTime
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import capa_edificios as ce
from ..core import capa_parcelas as cp
from ..core import gml_edificio as ge
from ..core import refcat
from ..core.incidencias import AVISO, ERROR
from .pestana_parcela import AUTOMATICO, MAX_FILAS, PROPIEDAD_TERRITORIO, miles

COL_N, COL_ID, COL_TIPO, COL_PLANTAS, COL_AREA, COL_ESTADO = range(6)
CABECERAS = ['Nº', 'Identificador (localId)', 'Tipo', 'Plantas', 'Sup. m²', 'Estado']
TIPOS = ((ge.EDIFICIO, 'Edificio'), (ge.PISCINA, 'Piscina'))


class PestanaEdificio(QWidget):
    """Contenido de la pestaña Edificio. dock es el panel, que muestra los avisos en su barra."""

    def __init__(self, dock, parent=None):
        super().__init__(parent)
        self.dock = dock
        self.filas = []
        self.demasiadas = False
        self.ultimo_gml = ''
        self.capa_conectada = None
        self.destino_automatico = ''
        self.referencia_automatica = ''  #Última referencia propuesta (si el usuario no la cambia, sigue a la capa)
        self.construir()
        self.capaCombo.setLayer(None)  #Se empieza sin capa: la de edificios casi nunca es la activa
        self.conectar()
        self.cambiar_capa()

    # ------------------------------------------------------------------ Interfaz

    def construir(self):
        principal = QVBoxLayout(self)
        principal.setContentsMargins(0, 0, 0, 0)
        formulario = QFormLayout()

        self.capaCombo = QgsMapLayerComboBox(self)
        self.capaCombo.setFilters(Qgis.LayerFilter.PolygonLayer)
        self.capaCombo.setAllowEmptyLayer(True)
        self.capaCombo.setToolTip("Capa de polígonos con la huella de cada construcción (edificio o piscina).\n"
                                  "Sirve la capa «Construcciones» de la pestaña Descargar")
        formulario.addRow("Capa", self.capaCombo)

        self.soloSeleccion = QCheckBox("Solo los elementos seleccionados", self)
        formulario.addRow("", self.soloSeleccion)

        self.referencia = QLineEdit(self)
        self.referencia.setPlaceholderText("Referencia catastral de la parcela (14 caracteres)")
        self.referencia.setToolTip("Referencia de la parcela donde están las construcciones: es la base de los "
                                   "identificadores (RC, RC_Edificio_1, RC_Piscina_1…).\nSi la parcela aún no existe en el "
                                   "Catastro, el identificador que tenga en la escritura")
        formulario.addRow("Parcela", self.referencia)

        self.campoPlantas = QgsFieldComboBox(self)
        self.campoPlantas.setAllowEmptyFieldName(True)
        self.campoPlantas.setToolTip("Campo con el número de plantas sobre rasante (opcional; se puede escribir en la tabla)")
        formulario.addRow("Campo de plantas", self.campoPlantas)
        principal.addLayout(formulario)

        self.tabla = QTableWidget(0, len(CABECERAS), self)
        self.tabla.setHorizontalHeaderLabels(CABECERAS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        cabecera.setStretchLastSection(True)
        cabecera.setMinimumSectionSize(40)
        self.tabla.setToolTip("Una fila por construcción. Puede cambiar el tipo, las plantas sobre rasante y el "
                              "identificador.\nUn edificio puede tener varias partes (toda su huella sobre rasante); "
                              "cada piscina, una sola")
        principal.addWidget(self.tabla, 1)

        self.resumen = QLabel(self)
        self.resumen.setWordWrap(True)
        principal.addWidget(self.resumen)

        salida = QFormLayout()
        self.estado = QComboBox(self)
        for estado in ge.ESTADOS:
            self.estado.addItem(ge.NOMBRES_ESTADO[estado], estado)
        self.estado.setToolTip("Estado de los edificios (conditionOfConstruction). Las piscinas no lo llevan")
        salida.addRow("Estado", self.estado)

        ahora = QDateTime.currentDateTime()
        ahora.setTime(QTime(ahora.time().hour(), ahora.time().minute()))
        self.fecha = QDateTimeEdit(ahora, self)
        self.fecha.setCalendarPopup(True)
        self.fecha.setDisplayFormat('dd/MM/yyyy HH:mm')
        self.fecha.setToolTip("Fecha y hora del GML (beginLifespanVersion)")
        salida.addRow("Fecha y hora", self.fecha)

        self.srcCombo = QComboBox(self)
        self.srcCombo.addItem("Automático (según la posición)", AUTOMATICO)
        for epsg, nombre in ((25829, 'ETRS89 / UTM 29N'), (25830, 'ETRS89 / UTM 30N'), (25831, 'ETRS89 / UTM 31N'),
                             (32628, 'WGS84 / UTM 28N (Canarias)')):
            self.srcCombo.addItem(f"EPSG:{epsg} · {nombre}", epsg)
        salida.addRow("SRC", self.srcCombo)

        self.destino = QgsFileWidget(self)
        self.destino.setStorageMode(QgsFileWidget.StorageMode.SaveFile)
        self.destino.setFilter("GML (*.gml)")
        self.destino.setDialogTitle("Guardar el GML de edificio")
        salida.addRow("Fichero", self.destino)
        principal.addLayout(salida)

        botones = QHBoxLayout()
        self.recargarBoton = QPushButton(QgsApplication.getThemeIcon('/mActionRefresh.svg'), "Recargar", self)
        self.recargarBoton.setToolTip("Vuelve a leer la capa (se pierden los cambios hechos en la tabla)")
        self.crearBoton = QPushButton(QgsApplication.getThemeIcon('/mActionFileSave.svg'), "Crear GML", self)
        botones.addWidget(self.recargarBoton)
        botones.addStretch(1)
        botones.addWidget(self.crearBoton)
        principal.addLayout(botones)

    def conectar(self):
        """Señales conectadas a métodos (nunca a lambdas: cerraban QGIS 4)."""
        self.capaCombo.layerChanged.connect(self.cambiar_capa)
        self.soloSeleccion.toggled.connect(self.recargar)
        self.campoPlantas.fieldChanged.connect(self.recargar)
        self.referencia.editingFinished.connect(self.proponer_ids)
        self.srcCombo.currentIndexChanged.connect(self.actualizar_superficies)
        self.tabla.itemSelectionChanged.connect(self.seleccionar_en_capa)
        self.recargarBoton.clicked.connect(self.recargar)
        self.crearBoton.clicked.connect(self.crear_gml)

    # ------------------------------------------------------------------ Capa y tabla

    def capa(self):
        capa = self.capaCombo.currentLayer()
        return capa if cp.es_capa_poligonos(capa) else None

    def usar_capa(self, capa):
        if cp.es_capa_poligonos(capa):
            self.soloSeleccion.setChecked(False)
            self.capaCombo.setLayer(capa)

    def cambiar_capa(self, *args):
        capa = self.capa()
        self.seguir_seleccion(capa)
        for widget in (self.campoPlantas, self.soloSeleccion):
            widget.blockSignals(True)
        self.campoPlantas.setLayer(capa)
        if capa is not None:
            self.campoPlantas.setField(ce.campo_plantas(capa))
            if capa.featureCount() > MAX_FILAS and capa.selectedFeatureCount() > 0:
                self.soloSeleccion.setChecked(True)
            self.proponer_fichero(capa)
        for widget in (self.campoPlantas, self.soloSeleccion):
            widget.blockSignals(False)
        self.recargar()

    def proponer_fichero(self, capa):
        actual = self.destino.filePath().strip()
        if actual and actual != self.destino_automatico:
            return
        carpeta = os.path.dirname(actual) if actual else (QgsProject.instance().homePath() or os.path.expanduser('~'))
        nombre = re.sub(r'[^0-9A-Za-z_.-]+', '_', capa.name()).strip('._') or 'edificio'
        self.destino_automatico = os.path.join(carpeta, f"{nombre}_edificio.gml")
        self.destino.setFilePath(self.destino_automatico)

    def seguir_seleccion(self, capa):
        anterior = self.capa_conectada
        if anterior is not None and not sip.isdeleted(anterior):
            with contextlib.suppress(TypeError, RuntimeError):
                anterior.selectionChanged.disconnect(self.seleccion_cambiada)
        self.capa_conectada = capa
        if capa is not None:
            capa.selectionChanged.connect(self.seleccion_cambiada)

    def seleccion_cambiada(self, *args):
        if not sip.isdeleted(self) and self.soloSeleccion.isChecked():
            self.recargar()

    def recargar(self, *args):
        capa = self.capa()
        n = 0 if capa is None else capa.selectedFeatureCount() if self.soloSeleccion.isChecked() else capa.featureCount()
        self.demasiadas = n > MAX_FILAS
        self.filas = [] if capa is None or self.demasiadas else ce.leer_capa(capa, self.soloSeleccion.isChecked(),
                                                                              self.campoPlantas.currentField())
        #La referencia se propone a partir de la capa (p. ej. la descargada), salvo que la haya escrito el usuario
        actual = self.referencia.text().strip()
        if not actual or actual == self.referencia_automatica:
            self.referencia_automatica = ce.referencia_propuesta(self.filas)
            self.referencia.setText(self.referencia_automatica)
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(len(self.filas))
        for i, fila in enumerate(self.filas):
            numero = QTableWidgetItem(str(i + 1))
            numero.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            numero.setData(Qt.ItemDataRole.UserRole, fila.fid)
            self.tabla.setItem(i, COL_N, numero)
            self.tabla.setItem(i, COL_ID, QTableWidgetItem(''))
            combo = QComboBox(self.tabla)  #Con padre: Python no lo borra
            for tipo, nombre in TIPOS:
                combo.addItem(nombre, tipo)
            combo.setCurrentIndex(0 if fila.tipo == ge.EDIFICIO else 1)
            combo.currentIndexChanged.connect(self.tipo_cambiado)
            self.tabla.setCellWidget(i, COL_TIPO, combo)
            self.tabla.setItem(i, COL_PLANTAS, QTableWidgetItem('' if fila.plantas is None else str(fila.plantas)))
            for col in (COL_AREA, COL_ESTADO):
                item = QTableWidgetItem('')
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.tabla.setItem(i, col, item)
            self.tabla.item(i, COL_AREA).setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabla.item(i, COL_ESTADO).setText('Sin geometría' if fila.partes == 0 else
                                                   f'{fila.partes} partes' if fila.partes > 1 else '')
        self.tabla.blockSignals(False)
        self.proponer_ids()
        self.tabla.resizeColumnsToContents()
        self.tabla.setColumnWidth(COL_ID, max(self.tabla.columnWidth(COL_ID), 160))
        self.actualizar_superficies()

    def tipo_fila(self, i):
        combo = self.tabla.cellWidget(i, COL_TIPO)
        return combo.currentData() if combo is not None else ge.EDIFICIO

    def tipo_cambiado(self, *args):
        """Al cambiar un tipo se vuelven a proponer los identificadores (cambia la numeración)."""
        self.proponer_ids()
        self.actualizar_superficies()

    def proponer_ids(self, *args):
        """Identificadores según el formato de la DGC a partir de la referencia de la parcela y de los tipos."""
        base = refcat.limpiar(self.referencia.text()) if refcat.es_rc_parcela(self.referencia.text()) \
            else re.sub(r'[^0-9A-Za-z_.-]+', '_', self.referencia.text().strip())
        ids = ge.identificadores(base, [self.tipo_fila(i) for i in range(len(self.filas))])
        self.tabla.blockSignals(True)
        for i, local_id in enumerate(ids):
            self.tabla.item(i, COL_ID).setText(local_id)
        self.tabla.blockSignals(False)

    def epsg_salida(self):
        elegido = self.srcCombo.currentData()
        if elegido != AUTOMATICO:
            return elegido
        capa = self.capa()
        return cp.epsg_para(self.filas, capa.crs()) if capa is not None else None

    def actualizar_superficies(self, *args):
        capa = self.capa()
        epsg = self.epsg_salida()
        total = 0
        for i, fila in enumerate(self.filas):
            area = ce.area_m2(fila, capa.crs(), epsg) if capa is not None else None
            self.tabla.item(i, COL_AREA).setText('' if area is None else miles(area))
            total += area or 0
        if not self.filas:
            if capa is None:
                texto = "<i>Elija la capa con la huella de las construcciones (p. ej. «Construcciones», de Descargar).</i>"
            elif self.demasiadas:
                texto = (f"<i>Demasiadas construcciones: seleccione en el mapa las de la parcela (máximo {MAX_FILAS}) y "
                         "marque «Solo los elementos seleccionados».</i>")
            else:
                texto = "<i>La capa no tiene polígonos (o no hay ninguno seleccionado).</i>"
            self.resumen.setText(texto)
            return
        edificios = sum(1 for i in range(len(self.filas)) if self.tipo_fila(i) == ge.EDIFICIO)
        piscinas = len(self.filas) - edificios
        texto = f"{edificios} edificio{'s' if edificios != 1 else ''}, {piscinas} piscina{'s' if piscinas != 1 else ''}"
        texto += f" · {miles(total)} m² de huella"
        if epsg:
            texto += f" · EPSG:{epsg}"
        if not self.referencia.text().strip():
            texto += "<br><span style='color:#e67700'>⚠ Indique la referencia de la parcela</span>"
        self.resumen.setText(texto)

    def seleccionar_en_capa(self):
        capa = self.capa()
        if capa is None:
            return
        fids = [self.tabla.item(i.row(), COL_N).data(Qt.ItemDataRole.UserRole)
                for i in self.tabla.selectionModel().selectedRows()]
        if fids and not self.soloSeleccion.isChecked():
            capa.selectByIds(fids)

    # ------------------------------------------------------------------ Crear el GML

    def plantas_fila(self, i):
        texto = self.tabla.item(i, COL_PLANTAS).text().strip()
        return int(texto) if texto.isdigit() else (texto or None)

    def marcar_estados(self, incidencias, ids):
        por_id = {}
        for inc in incidencias:
            if inc.elemento and inc.nivel in (ERROR, AVISO):
                por_id.setdefault(inc.elemento, inc)
        for i, local_id in enumerate(ids):
            inc = por_id.get(local_id)
            item = self.tabla.item(i, COL_ESTADO)
            item.setText(inc.mensaje if inc else 'Correcta')
            item.setToolTip(inc.mensaje if inc else '')
            item.setForeground(Qt.GlobalColor.red if inc and inc.nivel == ERROR else
                               Qt.GlobalColor.darkYellow if inc else Qt.GlobalColor.darkGreen)

    def crear_gml(self, *args):
        self.dock.messageBar.clearWidgets()
        capa = self.capa()
        if capa is None:
            self.dock.warn("Elija la capa con la huella de las construcciones")
            return None
        territorio = capa.customProperty(PROPIEDAD_TERRITORIO)
        if territorio:
            self.dock.warn(f"La capa es de {territorio}, que tiene catastro propio: el GML de edificio de la Dirección "
                           f"General del Catastro no sirve para sus trámites. Consulte al catastro de {territorio}.")
            return None
        if not self.filas:
            self.dock.warn("No hay construcciones: la capa está vacía, no hay elementos seleccionados o son demasiados")
            return None
        if not self.referencia.text().strip():
            self.dock.warn("Indique la referencia catastral de la parcela (o su identificador en la escritura)")
            return None
        ruta = self.destino.filePath().strip()
        if not ruta:
            self.dock.warn("Indique el fichero GML de salida")
            return None
        if not ruta.lower().endswith('.gml'):
            ruta += '.gml'
        if not os.path.isdir(os.path.dirname(os.path.abspath(ruta))):
            self.dock.warn(f"No existe la carpeta de destino: {os.path.dirname(ruta)}")
            return None
        epsg = self.epsg_salida()
        if epsg is None:
            self.dock.warn("No se ha podido determinar el SRC del GML: elíjalo en la lista")
            return None
        n = len(self.filas)
        ids = [self.tabla.item(i, COL_ID).text().strip() for i in range(n)]
        tipos = [self.tipo_fila(i) for i in range(n)]
        construcciones = ce.a_construcciones(self.filas, ids, tipos, [self.plantas_fila(i) for i in range(n)],
                                             self.estado.currentData(), capa.crs(), epsg)
        fecha = self.fecha.dateTime().toPyDateTime().replace(second=0, microsecond=0)
        ok, incidencias = ge.escribir(ruta, construcciones, epsg, fecha)
        self.marcar_estados(incidencias, ids)
        problemas = [str(i) for i in incidencias if i.nivel in (ERROR, AVISO)]
        if not ok:
            self.dock.notify("No se ha creado el GML: corrija estos errores\n\n" + "\n".join(f"- {p}" for p in problemas),
                             Qgis.MessageLevel.Critical, 0)
            return None
        self.ultimo_gml = ruta
        edificios = tipos.count(ge.EDIFICIO)
        piscinas = n - edificios
        self.dock.success(f"GML de edificio creado: {os.path.basename(ruta)} · {edificios} edificio"
                          f"{'s' if edificios != 1 else ''} y {piscinas} piscina{'s' if piscinas != 1 else ''} · "
                          f"EPSG:{epsg}", [("Abrir carpeta", self.abrir_carpeta), ("Validar", self.validar)],
                          detalles=problemas)
        return ruta

    def abrir_carpeta(self, *args):
        if self.ultimo_gml:
            self.dock.open_path(os.path.dirname(self.ultimo_gml))

    def validar(self, *args):
        """Abre el GML en la pestaña Validar (allí se comprueba también que está dentro de la parcela catastral)."""
        if self.ultimo_gml and hasattr(self.dock, 'pestanaValidar'):
            self.dock.tabWidget.setCurrentWidget(self.dock.tabValidar)
            self.dock.pestanaValidar.fichero.setFilePath(self.ultimo_gml)
