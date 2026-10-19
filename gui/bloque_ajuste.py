"""
Utilidad «Ajustar a la cartografía catastral» (fase 8e, AU-52) de la pestaña Utilidades: con pares de puntos homólogos
(capturados en el mapa con atracción a los vértices, importados de un TXT/CSV o escritos a mano) calcula los parámetros
de transformación de la Sede y crea el GML ajustado a la cartografía catastral junto con un fichero de parámetros.
La lógica está en core/ajuste.py.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os
import re
from html import escape

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsPointLocator,
    QgsPointXY,
    QgsProject,
    QgsSnappingConfig,
    QgsSnappingUtils,
    QgsTolerance,
)
from qgis.gui import QgsFileWidget, QgsMapToolEmitPoint, QgsRubberBand, QgsSnapIndicator, QgsVertexMarker
from qgis.PyQt import sip
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
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

from ..core import ajuste as aj
from ..core import gml_lector as gl
from ..core.incidencias import ERROR

CABECERAS = ["X", "Y", "X′ catastral", "Y′ catastral", "Residuo (m)"]
COL_RESIDUO = 4
NOMBRES_PARAMETROS = ('AX', 'BX', 'CX', 'AY', 'BY', 'CY')
EMC_ALTO = 0.5  #m: con más error medio, se avisa de que algún punto puede estar mal
TOLERANCIA_PX = 12  #Atracción a los vértices, en píxeles
COLOR = QColor(201, 42, 42)
DECIMAL = re.compile(r'(\d)\.(\d)')


def coma(texto):
    """Los números de un texto con coma decimal (como se leen en el panel)."""
    return DECIMAL.sub(r'\1,\2', texto)


class HerramientaPares(QgsMapToolEmitPoint):
    """Clic en el mapa con atracción a los vértices de las capas visibles; Esc o clic derecho anulan el par en curso."""
    punto = pyqtSignal(QgsPointXY)
    anulado = pyqtSignal()

    def __init__(self, lienzo):
        super().__init__(lienzo)
        self.lienzo = lienzo
        self.indicador = QgsSnapIndicator(lienzo)
        self.atraccion = QgsSnappingUtils(self)
        configuracion = QgsSnappingConfig()
        configuracion.setEnabled(True)
        configuracion.setMode(Qgis.SnappingMode.AllLayers)
        configuracion.setTypeFlag(Qgis.SnappingType.Vertex)
        configuracion.setTolerance(TOLERANCIA_PX)
        configuracion.setUnits(QgsTolerance.UnitType.Pixels)
        self.atraccion.setConfig(configuracion)

    def ajustado(self, posicion):
        self.atraccion.setMapSettings(self.lienzo.mapSettings())
        return self.atraccion.snapToMap(posicion)

    def canvasMoveEvent(self, evento):  # noqa: N802 (nombre impuesto por QGIS)
        self.indicador.setMatch(self.ajustado(evento.pos()))

    def canvasReleaseEvent(self, evento):  # noqa: N802 (nombre impuesto por QGIS)
        if evento.button() == Qt.MouseButton.RightButton:
            self.anulado.emit()
            return
        if evento.button() != Qt.MouseButton.LeftButton:
            return
        encaje = self.ajustado(evento.pos())
        self.punto.emit(encaje.point() if encaje.isValid() else self.toMapCoordinates(evento.pos()))

    def keyPressEvent(self, evento):  # noqa: N802 (nombre impuesto por QGIS)
        if evento.key() == Qt.Key.Key_Escape:
            self.anulado.emit()
            evento.accept()
        else:
            evento.ignore()

    def deactivate(self):
        self.indicador.setMatch(QgsPointLocator.Match())  #Sin el círculo de atracción al soltar la herramienta
        super().deactivate()


class BloqueAjuste(QWidget):
    def __init__(self, pestana, parent=None):
        super().__init__(parent)
        self.pestana = pestana
        self.herramienta = None
        self.anterior = None
        self.pendiente = None    #Punto del levantamiento capturado, a la espera de su homólogo catastral
        self.banda = None        #Líneas de cada par en el mapa
        self.marca = None        #Punto pendiente en el mapa
        self.epsg = None
        self.version = ''
        self.tamano = 0.0        #Diagonal del rectángulo que ocupa el GML (m): para avisar de puntos muy juntos
        self.parametros_ruta = ''
        self.destino_auto = ''
        self.ajuste = None
        self.ultimo = ''
        self.calculando = False
        self.construir()
        self.origenAj.fileChanged.connect(self.origen_cambiado)
        self.metodo.currentIndexChanged.connect(self.metodo_cambiado)
        self.tabla.itemChanged.connect(self.recalcular)
        self.capturarBoton.toggled.connect(self.capturar)
        self.importarBoton.clicked.connect(self.importar)
        self.quitarParBoton.clicked.connect(self.quitar)
        self.crearAjBoton.clicked.connect(self.crear)
        for campo in self.parametros:
            campo.editingFinished.connect(self.recalcular)
        self.metodo_cambiado()

    def construir(self):
        caja = QVBoxLayout(self)
        formulario = QFormLayout()
        self.origenAj = QgsFileWidget(self)
        self.origenAj.setStorageMode(QgsFileWidget.StorageMode.GetFile)
        self.origenAj.setFilter("GML (*.gml)")
        self.origenAj.setDialogTitle("Elegir el GML del levantamiento (coordenadas reales)")
        self.origenAj.setToolTip("GML de parcela (4.0) o de edificio en su posición real, del levantamiento")
        formulario.addRow("Levantamiento", self.origenAj)
        self.metodo = QComboBox(self)
        for clave in (aj.TRASLACION, aj.SEMEJANZA, aj.AFIN, aj.CONOCIDOS):
            minimo = aj.MINIMO_PUNTOS[clave]
            texto = aj.NOMBRES[clave] + (f" · {minimo}+ puntos" if minimo else " (de la Sede u otro programa)")
            self.metodo.addItem(texto, clave)
        self.metodo.setToolTip("Traslación si la cartografía solo está corrida; semejanza si además está girada; afín si "
                               "hay deformación. Con puntos de más se comprueba el ajuste (residuos)")
        formulario.addRow("Ajuste", self.metodo)
        caja.addLayout(formulario)

        self.tabla = QTableWidget(0, len(CABECERAS), self)
        self.tabla.setHorizontalHeaderLabels(CABECERAS)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setToolTip("Pares de puntos homólogos: el mismo punto del terreno en el levantamiento (X, Y) y en la "
                              "cartografía catastral (X′, Y′), en el SRC del GML. Se pueden escribir o corregir aquí")
        self.tabla.setMinimumHeight(120)
        caja.addWidget(self.tabla, 1)
        fila = QHBoxLayout()
        self.capturarBoton = QPushButton(QgsApplication.getThemeIcon('/mActionCapturePoint.svg'), "Capturar en el mapa", self)
        self.capturarBoton.setCheckable(True)
        self.capturarBoton.setToolTip("Clic en un punto del levantamiento y después en el mismo punto de la cartografía "
                                      "catastral (se ajusta a los vértices). Esc o clic derecho anulan el par en curso")
        self.importarBoton = QPushButton(QgsApplication.getThemeIcon('/mActionFileOpen.svg'), "Importar…", self)
        self.importarBoton.setToolTip("TXT o CSV con una línea por punto: [nombre] X Y X′ Y′")
        self.quitarParBoton = QPushButton(QgsApplication.getThemeIcon('/symbologyRemove.svg'), "Quitar", self)
        for boton in (self.capturarBoton, self.importarBoton, self.quitarParBoton):
            fila.addWidget(boton)
        fila.addStretch(1)
        caja.addLayout(fila)
        #El paso de la captura, fijo en la utilidad mientras dura (en la barra se cortaba y se iba antes de leerlo)
        self.pasoCaptura = QLabel(self)
        self.pasoCaptura.setWordWrap(True)
        self.pasoCaptura.setVisible(False)
        caja.addWidget(self.pasoCaptura)

        rejilla = QGridLayout()
        self.parametros = []
        for i, nombre in enumerate(NOMBRES_PARAMETROS):
            campo = QLineEdit(self)
            campo.setToolTip(f"{nombre}: X′ = AX·X + BX·Y + CX; Y′ = AY·X + BY·Y + CY (de real a catastral)")
            rejilla.addWidget(QLabel(nombre, self), i // 3, 2 * (i % 3))
            rejilla.addWidget(campo, i // 3, 2 * (i % 3) + 1)
            self.parametros.append(campo)
        caja.addLayout(rejilla)
        self.resumenAj = QLabel(self)
        self.resumenAj.setWordWrap(True)
        caja.addWidget(self.resumenAj)
        salida = QFormLayout()
        self.destinoAj = QgsFileWidget(self)
        self.destinoAj.setStorageMode(QgsFileWidget.StorageMode.SaveFile)
        self.destinoAj.setFilter("GML (*.gml)")
        self.destinoAj.setDialogTitle("Guardar el GML ajustado a la cartografía catastral")
        salida.addRow("Ajustado", self.destinoAj)
        caja.addLayout(salida)
        botones = QHBoxLayout()
        botones.addStretch(1)
        self.crearAjBoton = QPushButton(QgsApplication.getThemeIcon('/mActionFileSave.svg'), "Crear GML ajustado", self)
        self.crearAjBoton.setToolTip("Escribe el GML ajustado a la cartografía catastral y, junto a él, los parámetros "
                                     "(…_parametros.txt). El GML del levantamiento no se toca: la Sede pide los dos")
        self.crearAjBoton.setEnabled(False)
        botones.addWidget(self.crearAjBoton)
        caja.addLayout(botones)

    # ------------------------------------------------------------------ Datos

    def origen_cambiado(self, *args):
        ruta = self.origenAj.filePath().strip()
        lectura = gl.leer(ruta) if ruta and os.path.isfile(ruta) else None
        valido = (lectura is not None and bool(lectura.elementos) and lectura.epsg is not None
                  and (lectura.version == 'CP 4.0' or lectura.version.startswith('BU'))
                  and not any(i.nivel == ERROR and i.codigo in ('XML-MAL-FORMADO', 'COORDENADAS') for i in lectura.incidencias))
        self.epsg = lectura.epsg if valido else None
        self.version = lectura.version if valido else ''
        self.tamano = 0.0
        if valido:
            caja = QgsGeometry.collectGeometry([e.geometria for e in lectura.elementos]).boundingBox()
            self.tamano = (caja.width() ** 2 + caja.height() ** 2) ** 0.5
        if valido:
            destino = self.destinoAj.filePath().strip()
            if not destino or destino == self.destino_auto:
                self.destino_auto = aj.ruta_ajustada(ruta)
                self.destinoAj.setFilePath(self.destino_auto)
        elif ruta:
            self.capturarBoton.setChecked(False)
        self.recalcular()

    def pares(self):
        """Pares completos de la tabla (las filas a medio escribir no cuentan) y filas con algún número mal."""
        pares, malas = [], []
        for fila in range(self.tabla.rowCount()):
            valores = []
            for col in range(4):
                item = self.tabla.item(fila, col)
                texto = item.text().strip().replace(',', '.') if item is not None else ''
                try:
                    valores.append(float(texto) if texto else None)
                except ValueError:
                    valores.append(None)
                    malas.append(fila + 1)
            if None not in valores:
                pares.append(aj.Par(*valores, nombre=str(fila + 1)))
        return pares, sorted(set(malas))

    def metodo_cambiado(self, *args):
        conocidos = self.metodo.currentData() == aj.CONOCIDOS
        for campo in self.parametros:
            campo.setReadOnly(not conocidos)
        if conocidos and not any(c.text().strip() for c in self.parametros):
            for campo, valor in zip(self.parametros, aj.Transformacion().textos()):
                campo.setText(valor)
        self.recalcular()

    def transformacion_escrita(self):
        valores = [float(c.text().strip().replace(',', '.')) for c in self.parametros]
        return aj.Transformacion(*valores)

    def recalcular(self, *args):
        """Calcula los parámetros con los puntos (o comprueba los escritos), los residuos y el resumen."""
        if self.calculando or sip.isdeleted(self):
            return
        self.calculando = True
        try:
            self._recalcular()
        finally:
            self.calculando = False
        self.mostrar_en_mapa()

    def _recalcular(self):
        metodo = self.metodo.currentData()
        pares, malas = self.pares()
        self.ajuste = None
        error = ''
        try:
            if metodo == aj.CONOCIDOS:
                self.ajuste = aj.evaluar(self.transformacion_escrita(), pares)
            elif pares:
                self.ajuste = aj.calcular(pares, metodo)
            else:
                error = f"Añada al menos {aj.MINIMO_PUNTOS[metodo]} par{'es' if aj.MINIMO_PUNTOS[metodo] != 1 else ''} de puntos"
        except ValueError as e:
            error = ("Los parámetros deben ser números" if metodo == aj.CONOCIDOS and 'float' in str(e)
                     else str(e)[:1].upper() + str(e)[1:])
        if self.ajuste is not None and metodo != aj.CONOCIDOS:
            for campo, valor in zip(self.parametros, self.ajuste.transformacion.textos()):
                campo.setText(valor)
        elif metodo != aj.CONOCIDOS:
            for campo in self.parametros:
                campo.clear()
        residuos = dict(zip([int(p.nombre) - 1 for p in pares], self.ajuste.residuos if self.ajuste else []))
        for fila in range(self.tabla.rowCount()):
            item = QTableWidgetItem(f"{residuos[fila]:.3f}".replace('.', ',') if fila in residuos else '')
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tabla.setItem(fila, COL_RESIDUO, item)
        self.resumenAj.setText(self.resumen(pares, malas, error))
        self.crearAjBoton.setEnabled(self.ajuste is not None and self.epsg is not None)

    def resumen(self, pares, malas, error):
        partes = []
        if self.origenAj.filePath().strip() and self.epsg is None:
            partes.append("<span style='color:#c92a2a'>Elija un GML de parcela 4.0 o de edificio legible (uno antiguo, "
                          "conviértalo antes en «2.»).</span>")
        elif self.epsg is not None:
            partes.append(f"{self.version} · EPSG:{self.epsg}")
        if malas:
            partes.append(f"<span style='color:#c92a2a'>Filas con números que no se entienden: "
                          f"{', '.join(map(str, malas))}</span>")
        if error:
            partes.append(f"<span style='color:#c92a2a'>{error}</span>")
        if self.ajuste is not None:
            t = self.ajuste.transformacion
            giro, escala, _, _ = t.descripcion()
            texto = f"{len(pares)} punto{'s' if len(pares) != 1 else ''}"
            if self.ajuste.redundancia > 0 and pares:
                maximo = max(self.ajuste.residuos)
                color = '#e67700' if self.ajuste.emc > EMC_ALTO else 'inherit'
                texto += (f" · <span style='color:{color}'>error medio {self.ajuste.emc:.3f} m · máximo {maximo:.3f} m "
                          f"(fila {self.ajuste.residuos.index(maximo) + 1})</span>")
                if self.ajuste.emc > EMC_ALTO:
                    texto += " · revise los puntos"
            elif pares:
                texto += " · sin puntos de control (los residuos son nulos por construcción; añada alguno más)"
            if not t.es_traslacion():
                texto += f" · giro {giro:.5f}° · escala {(escala - 1) * 1e6:+.1f} ppm"
            if pares:
                dx = sum(p.xc - p.x for p in pares) / len(pares)
                dy = sum(p.yc - p.y for p in pares) / len(pares)
                texto += f" · el Catastro está {abs(dx):.2f} m al {'E' if dx >= 0 else 'O'} y {abs(dy):.2f} m al " \
                         f"{'N' if dy >= 0 else 'S'}"
            partes.append(texto.replace('.', ','))
            partes += [f"<span style='color:#e67700'>⚠ {escape(coma(d))}</span>"
                       for d in aj.avisos(self.ajuste, pares, self.tamano)]
        return f"<small>{'<br>'.join(partes)}</small>" if partes else ''

    def anadir_par(self, par):
        self.calculando = True
        try:
            fila = self.tabla.rowCount()
            self.tabla.insertRow(fila)
            for col, valor in enumerate((par.x, par.y, par.xc, par.yc)):
                self.tabla.setItem(fila, col, QTableWidgetItem(f"{valor:.3f}"))
        finally:
            self.calculando = False

    def importar(self, *args):
        ruta, _ = QFileDialog.getOpenFileName(self, "Importar pares de puntos", os.path.dirname(self.origenAj.filePath()),
                                              "Puntos (*.txt *.csv);;Todos (*.*)")
        if ruta:
            self.importar_fichero(ruta)

    def importar_fichero(self, ruta):
        try:
            with open(ruta, encoding='utf-8-sig', errors='replace') as f:
                pares, saltadas = aj.leer_pares(f.read())
        except OSError as e:
            self.pestana.dock.warn(f"No se ha podido leer {os.path.basename(ruta)}: {e.strerror or e}")
            return 0
        for par in pares:
            self.anadir_par(par)
        self.recalcular()
        if not pares:
            self.pestana.dock.warn(f"{os.path.basename(ruta)} no tiene líneas con X Y X′ Y′")
        elif saltadas:
            self.pestana.dock.notify(f"Importados {len(pares)} pares; se han saltado las líneas "
                                     f"{', '.join(map(str, saltadas[:10]))}{'…' if len(saltadas) > 10 else ''} "
                                     "(sin cuatro números)", Qgis.MessageLevel.Info)
        return len(pares)

    def quitar(self, *args):
        filas = sorted({i.row() for i in self.tabla.selectedIndexes()}, reverse=True)
        if not filas and self.tabla.rowCount():
            filas = [self.tabla.rowCount() - 1]
        for fila in filas:
            self.tabla.removeRow(fila)
        self.recalcular()

    # ------------------------------------------------------------------ Crear

    def crear(self, *args):
        dock = self.pestana.dock
        dock.messageBar.clearWidgets()
        ruta = self.origenAj.filePath().strip()
        destino = self.destinoAj.filePath().strip()
        if self.ajuste is None or self.epsg is None:
            dock.warn("Elija el GML del levantamiento y calcule (o escriba) los parámetros")
            return None
        if not destino:
            dock.warn("Indique el fichero del GML ajustado")
            return None
        if not destino.lower().endswith('.gml'):
            destino += '.gml'
        ok, incidencias = aj.escribir_ajustado(ruta, destino, self.ajuste.transformacion)
        errores = [i for i in incidencias if i.nivel == ERROR]
        if not ok:
            dock.warn("No se ha creado el GML ajustado: " + (errores[0].mensaje if errores else "error desconocido"))
            return None
        try:
            parametros = aj.escribir_parametros(self.ajuste, self.pares()[0], ruta, destino, self.epsg, tamano=self.tamano)
        except OSError as e:
            dock.warn(f"El GML ajustado se ha creado, pero no los parámetros: {e}")
            return None
        self.ultimo = destino
        self.parametros_ruta = parametros
        notas = ["ICUC: marque que existe desplazamiento, escriba los parámetros, suba el GML ajustado y adjunte el del "
                 "levantamiento en «+ Documentación»"] \
            if self.version.startswith('BU') else ["Para la Sede o el notario: los dos GML y los parámetros "
                                                   "(Resolución de 29/03/2021, apartado octavo)"]
        dock.success(f"GML ajustado: {os.path.basename(destino)} · parámetros: {os.path.basename(parametros)}",
                     [("Validar", self.validar), ("Ver parámetros", self.abrir_parametros), ("Abrir carpeta", self.abrir_carpeta)],
                     notas=notas)
        return destino

    def validar(self, *args):
        """Abre el GML ajustado en Validar, donde se compara con el Catastro."""
        if self.ultimo:
            self.pestana.dock.abrir_en_validar(self.ultimo)

    def abrir_parametros(self, *args):
        if self.parametros_ruta:
            self.pestana.dock.open_path(self.parametros_ruta)

    def abrir_carpeta(self, *args):
        if self.ultimo:
            self.pestana.dock.open_path(os.path.dirname(self.ultimo))

    # ------------------------------------------------------------------ Mapa

    def lienzo(self):
        iface = getattr(self.pestana.dock, 'iface', None)
        return iface.mapCanvas() if iface is not None and hasattr(iface, 'mapCanvas') else None

    def capturar(self, activar):
        lienzo = self.lienzo()
        if lienzo is None:
            return
        if not activar:
            self.pendiente = None
            self.soltar_herramienta()
            self.mostrar_en_mapa()
            self.mostrar_paso()
            return
        if self.epsg is None:
            self.capturarBoton.blockSignals(True)
            self.capturarBoton.setChecked(False)
            self.capturarBoton.blockSignals(False)
            self.pestana.dock.warn("Elija antes el GML del levantamiento: los puntos se toman en su sistema de referencia")
            return
        if self.herramienta is None:
            self.herramienta = HerramientaPares(lienzo)
            self.herramienta.punto.connect(self.punto_capturado)
            self.herramienta.anulado.connect(self.anular_pendiente)
            self.herramienta.deactivated.connect(self.herramienta_desactivada)
        if lienzo.mapTool() is not self.herramienta:
            self.anterior = lienzo.mapTool()
        lienzo.setMapTool(self.herramienta)
        self.mostrar_paso()

    def mostrar_paso(self):
        """Qué clic toca ahora, a la vista mientras se captura."""
        if sip.isdeleted(self):
            return
        activa = self.capturarBoton.isChecked()
        self.pasoCaptura.setVisible(activa)
        if not activa:
            return
        if self.pendiente is None:
            texto = ("<b>1/2</b> · Clic en un punto del <b>levantamiento</b> (una esquina; el clic se ajusta a los "
                     "vértices). Tome los puntos en extremos opuestos")
        else:
            texto = "<b>2/2</b> · Clic en el <b>mismo punto en la cartografía catastral</b>"
        self.pasoCaptura.setText(f"<span style='color:#1971c2'>{texto}. Esc o clic derecho: anular el par.</span>")

    def a_gml(self, punto):
        """Del SRC del mapa al del GML."""
        lienzo = self.lienzo()
        origen = lienzo.mapSettings().destinationCrs()
        destino = QgsCoordinateReferenceSystem(f'EPSG:{self.epsg}')
        if origen == destino:
            return QgsPointXY(punto)
        return QgsCoordinateTransform(origen, destino, QgsProject.instance()).transform(punto)

    def punto_capturado(self, punto):
        if self.epsg is None:
            return
        punto = self.a_gml(punto)
        if self.pendiente is None:
            self.pendiente = punto
        else:
            self.anadir_par(aj.Par(self.pendiente.x(), self.pendiente.y(), punto.x(), punto.y()))
            self.pendiente = None
            self.recalcular()
        self.mostrar_en_mapa()
        self.mostrar_paso()

    def anular_pendiente(self):
        self.pendiente = None
        self.mostrar_en_mapa()
        self.mostrar_paso()

    def herramienta_desactivada(self):
        """Otra herramienta ha sustituido a la nuestra: se desmarca el botón y se olvida el punto a medias."""
        if sip.isdeleted(self):
            return
        self.pendiente = None
        self.capturarBoton.blockSignals(True)
        self.capturarBoton.setChecked(False)
        self.capturarBoton.blockSignals(False)
        self.mostrar_en_mapa()
        self.mostrar_paso()

    def soltar_herramienta(self):
        lienzo = self.lienzo()
        if lienzo is None or self.herramienta is None or sip.isdeleted(self.herramienta):
            return
        if lienzo.mapTool() is self.herramienta:
            if self.anterior is not None and not sip.isdeleted(self.anterior):
                lienzo.setMapTool(self.anterior)
            else:
                lienzo.unsetMapTool(self.herramienta)
        self.anterior = None

    def a_mapa(self, x, y):
        lienzo = self.lienzo()
        origen = QgsCoordinateReferenceSystem(f'EPSG:{self.epsg}')
        destino = lienzo.mapSettings().destinationCrs()
        if origen == destino:
            return QgsPointXY(x, y)
        return QgsCoordinateTransform(origen, destino, QgsProject.instance()).transform(QgsPointXY(x, y))

    def visible(self):
        dock = self.pestana.dock
        return (self.isVisibleTo(dock) and not getattr(dock, 'cerrado', False)
                and self.pestana.utilidades.currentWidget() is self)

    def mostrar_en_mapa(self, *args):
        """
        Cada par como una línea roja del punto del levantamiento al catastral, y el punto a medias marcado: solo con
        esta utilidad abierta y el panel a la vista (el dock vuelve a llamar aquí al cambiar de pestaña o cerrarlo).
        """
        lienzo = self.lienzo()
        if lienzo is None or sip.isdeleted(self):
            return
        if self.banda is None:
            self.banda = QgsRubberBand(lienzo, Qgis.GeometryType.Line)
            self.banda.setColor(COLOR)
            self.banda.setWidth(2)
        self.banda.reset(Qgis.GeometryType.Line)
        if self.marca is not None and not sip.isdeleted(self.marca):
            lienzo.scene().removeItem(self.marca)
        self.marca = None
        if not self.visible() or self.epsg is None:
            return
        for par in self.pares()[0]:
            linea = QgsGeometry.fromPolylineXY([self.a_mapa(par.x, par.y), self.a_mapa(par.xc, par.yc)])
            self.banda.addGeometry(linea, None, False)
        self.banda.updatePosition()
        if self.pendiente is not None:
            self.marca = QgsVertexMarker(lienzo)
            self.marca.setCenter(self.a_mapa(self.pendiente.x(), self.pendiente.y()))
            self.marca.setColor(COLOR)
            self.marca.setIconType(QgsVertexMarker.IconType.ICON_CROSS)
            self.marca.setIconSize(14)
            self.marca.setPenWidth(2)

    def soltar(self):
        """Al cerrar el plugin: devuelve la herramienta anterior y quita las marcas del mapa."""
        self.soltar_herramienta()
        lienzo = self.lienzo()
        for marca in (self.banda, self.marca):
            if marca is not None and lienzo is not None and not sip.isdeleted(marca):
                lienzo.scene().removeItem(marca)
        self.banda = self.marca = None
