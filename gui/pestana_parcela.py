"""
Pestaña «Parcela»: crea el GML de parcela catastral (INSPIRE CP 4.0) a partir de una capa de polígonos.

Flujo: capa (y si se quiere solo la selección) → campos de identificador y de número de parcela → tabla con una fila por
parcela, donde se pueden cambiar identificador, namespace y número → fecha, SRC y fichero → Crear GML.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import contextlib
import os
import re

from qgis.core import Qgis, QgsApplication, QgsProject, QgsVectorLayer
from qgis.gui import QgsFieldComboBox, QgsFileWidget, QgsMapLayerComboBox
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QDate, Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import capa_parcelas as cp
from ..core import geometria as geo
from ..core import gml_parcela as gp
from ..core.incidencias import AVISO, ERROR

COL_N, COL_ID, COL_NS, COL_LABEL, COL_AREA, COL_ESTADO = range(6)
CABECERAS = ['Nº', 'Identificador (localId)', 'Namespace', 'Nº parcela', 'Sup. m²', 'Estado']
AUTOMATICO = 0  #Dato del combo de SRC para «automático»
#Máximo de parcelas que se cargan en la tabla. La Sede admite como mucho 30 parcelas resultantes por operación;
#con una capa grande (p. ej. un municipio entero) hay que seleccionar las parcelas: cargarla entera bloqueaba QGIS.
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
        self.labels_auto = []  #Por fila: True si el nº de parcela lo ha puesto el plugin (se recalcula al cambiar el id)
        self.ultimo_gml = ''
        self.capa_conectada = None
        self.destino_automatico = ''  #Último nombre de fichero propuesto (si el usuario no lo cambia, sigue a la capa)  #Capa cuya selección se sigue (para desconectarla al cambiar)
        self.construir()
        activa = self.dock.iface.activeLayer() if self.dock.iface is not None else None
        if cp.es_capa_poligonos(activa):
            self.capaCombo.setLayer(activa)  #Se empieza por la capa activa, no por la primera del proyecto
        self.conectar()
        self.cambiar_capa()  #La capa que el combo ya muestra al abrir el panel (sin esto no se proponen los campos)

    # ------------------------------------------------------------------ Interfaz

    def construir(self):
        principal = QVBoxLayout(self)
        principal.setContentsMargins(0, 0, 0, 0)
        formulario = QFormLayout()

        self.capaCombo = QgsMapLayerComboBox(self)
        self.capaCombo.setFilters(Qgis.LayerFilter.PolygonLayer)
        self.capaCombo.setToolTip("Capa de polígonos con las parcelas (cada polígono será una parcela del GML)")
        formulario.addRow("Capa", self.capaCombo)

        self.soloSeleccion = QCheckBox("Solo los elementos seleccionados", self)
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
        principal.addLayout(formulario)

        self.tabla = QTableWidget(0, len(CABECERAS), self)
        self.tabla.setHorizontalHeaderLabels(CABECERAS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.horizontalHeader().setSectionResizeMode(COL_ID, QHeaderView.ResizeMode.Stretch)
        self.tabla.setToolTip("Puede cambiar el identificador, el namespace y el número de parcela de cada fila.\n"
                              "SDGC: la parcela existe en el Catastro y se conserva su referencia (14 caracteres).\n"
                              "LOCAL: parcela nueva con un identificador propio (Seg_1, Div_1_1…).")
        principal.addWidget(self.tabla, 1)

        self.resumen = QLabel(self)
        self.resumen.setWordWrap(True)
        principal.addWidget(self.resumen)

        salida = QFormLayout()
        self.fecha = QDateEdit(QDate.currentDate(), self)
        self.fecha.setCalendarPopup(True)
        self.fecha.setDisplayFormat('dd/MM/yyyy')
        self.fecha.setToolTip("Fecha del GML (beginLifespanVersion)")
        salida.addRow("Fecha", self.fecha)

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
        botones.addStretch(1)
        botones.addWidget(self.crearBoton)
        principal.addLayout(botones)

    def conectar(self):
        """Señales conectadas a métodos (nunca a lambdas: cerraban QGIS 4)."""
        self.capaCombo.layerChanged.connect(self.cambiar_capa)
        self.soloSeleccion.toggled.connect(self.recargar)
        self.campoId.fieldChanged.connect(self.recargar)
        self.campoLabel.fieldChanged.connect(self.recargar)
        self.srcCombo.currentIndexChanged.connect(self.actualizar_superficies)
        self.tabla.itemSelectionChanged.connect(self.seleccionar_en_capa)
        self.tabla.itemChanged.connect(self.celda_cambiada)
        self.recargarBoton.clicked.connect(self.recargar)
        self.crearBoton.clicked.connect(self.crear_gml)

    # ------------------------------------------------------------------ Capa y tabla

    def capa(self):
        capa = self.capaCombo.currentLayer()
        return capa if cp.es_capa_poligonos(capa) else None

    def cambiar_capa(self, *args):
        capa = self.capa()
        self.seguir_seleccion(capa)
        #Sin señales mientras se rellenan los campos: si no, la tabla se recalculaba 3 o 4 veces seguidas
        for widget in (self.campoId, self.campoLabel, self.soloSeleccion):
            widget.blockSignals(True)
        self.campoId.setLayer(capa)
        self.campoLabel.setLayer(capa)
        if capa is not None:
            #Propone el campo de identificador si hay uno con nombre habitual
            for nombre in ('refcat', 'ref_catastral', 'referencia', 'nationalCadastralReference', 'localId', 'localid', 'rc'):
                if capa.fields().indexOf(nombre) >= 0:
                    self.campoId.setField(nombre)
                    break
            #En una capa grande con parcelas seleccionadas, se trabaja con la selección
            if capa.featureCount() > MAX_FILAS and capa.selectedFeatureCount() > 0:
                self.soloSeleccion.setChecked(True)
            self.proponer_fichero(capa)
        for widget in (self.campoId, self.campoLabel, self.soloSeleccion):
            widget.blockSignals(False)
        self.recargar()

    def proponer_fichero(self, capa):
        """
        Propone el fichero de salida con el nombre de la capa (sin espacios ni símbolos), en la carpeta que ya hubiera
        elegida o en la del proyecto. Si el usuario ha escrito su propio fichero, no se toca.
        """
        actual = self.destino.filePath().strip()
        if actual and actual != self.destino_automatico:
            return
        carpeta = os.path.dirname(actual) if actual else (QgsProject.instance().homePath() or os.path.expanduser('~'))
        nombre = re.sub(r'[^0-9A-Za-z_.-]+', '_', capa.name()).strip('._') or 'parcelas'
        self.destino_automatico = os.path.join(carpeta, f"{nombre}.gml")
        self.destino.setFilePath(self.destino_automatico)

    def seguir_seleccion(self, capa):
        """Con «Solo los elementos seleccionados», la tabla se actualiza al seleccionar parcelas en el mapa."""
        anterior = self.capa_conectada
        if anterior is not None and not sip.isdeleted(anterior):
            with contextlib.suppress(TypeError, RuntimeError):  #Ya desconectada
                anterior.selectionChanged.disconnect(self.seleccion_cambiada)
        self.capa_conectada = capa
        if capa is not None:
            capa.selectionChanged.connect(self.seleccion_cambiada)

    def seleccion_cambiada(self, *args):
        if not sip.isdeleted(self) and self.soloSeleccion.isChecked():
            self.recargar()

    def numero_parcelas(self, capa):
        return capa.selectedFeatureCount() if self.soloSeleccion.isChecked() else capa.featureCount()

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
        self.tabla.resizeColumnToContents(COL_N)
        self.actualizar_superficies()

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
        for i, fila in enumerate(self.filas):
            area = cp.area_m2(fila, capa.crs(), epsg) if capa is not None else None
            self.tabla.item(i, COL_AREA).setText('' if area is None else miles(area))
            total += area or 0
        if not self.filas:
            if capa is None:
                texto = "<i>Elija una capa de polígonos con las parcelas.</i>"
            elif self.demasiadas:
                texto = (f"<i>La capa tiene {miles(self.numero_parcelas(capa))} parcelas: seleccione en el mapa las que "
                         f"quiera incluir (máximo {MAX_FILAS}) y marque «Solo los elementos seleccionados».</i>")
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
        self.resumen.setText(texto)

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
        if item.column() == COL_LABEL:
            self.labels_auto[fila] = not item.text().strip()
            if self.labels_auto[fila]:
                self.actualizar_label(fila)
        elif item.column() == COL_ID:
            texto = item.text().strip()
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
        if not self.filas:
            if self.demasiadas:
                self.dock.warn(f"Demasiadas parcelas: seleccione en el mapa las que quiera incluir (máximo {MAX_FILAS}) "
                               "y marque «Solo los elementos seleccionados»")
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
        fecha = self.fecha.date().toPyDate()
        ok, incidencias = gp.escribir(ruta, cp.a_parcelas_gml(filas, capa.crs(), epsg), epsg, fecha)
        self.marcar_estados(incidencias)
        problemas = [str(i) for i in incidencias if i.nivel in (ERROR, AVISO)]
        if not ok:
            self.dock.notify("No se ha creado el GML: corrija estos errores\n\n" + "\n".join(f"- {p}" for p in problemas),
                             Qgis.MessageLevel.Critical, 0)
            return
        self.ultimo_gml = ruta
        resumen = f"GML creado: {os.path.basename(ruta)} · {len(filas)} parcelas · EPSG:{epsg}"
        self.dock.success(resumen, [("Abrir carpeta", self.abrir_carpeta), ("Cargar en el mapa", self.cargar_en_mapa)],
                          detalles=problemas)

    def abrir_carpeta(self, *args):
        if self.ultimo_gml:
            self.dock.open_path(os.path.dirname(self.ultimo_gml))

    def cargar_en_mapa(self, *args):
        """Carga el GML creado como capa (lo lee el driver GML de GDAL) para compararlo con el original."""
        if not self.ultimo_gml or not os.path.isfile(self.ultimo_gml):
            return None
        capa = QgsVectorLayer(self.ultimo_gml, os.path.splitext(os.path.basename(self.ultimo_gml))[0], 'ogr')
        if not capa.isValid():
            self.dock.warn("QGIS no ha podido abrir el GML creado")
            return None
        QgsProject.instance().addMapLayer(capa)
        return capa
