"""
Utilidad «Parcela desde coordenadas» de la pestaña Utilidades (AU-57): elige el fichero de puntos de un levantamiento
(TXT o CSV), lo lee (core/coordenadas.py), dice qué parcelas salen y, con «Crear capa», las pone en una capa del
proyecto y pasa a la pestaña Parcela con ella, donde se eligen identificador, namespace y alteración y se crea el GML.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os
from html import escape

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsProject,
    QgsVectorLayer,
)
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..core import coordenadas as co
from ..core import geometria as geo
from ..core.incidencias import AVISO, ERROR

ICONO = '/mActionAddDelimitedTextLayer.svg'
EXTENSIONES = ('.txt', '.csv', '.dat', '.xyz', '.pts')
MAX_LINEAS = 8
HUSOS = ((25829, "EPSG:25829 · ETRS89 / UTM 29N (Galicia, oeste)"), (25830, "EPSG:25830 · ETRS89 / UTM 30N"),
         (25831, "EPSG:25831 · ETRS89 / UTM 31N (este y Baleares)"), (32628, "EPSG:32628 · WGS 84 / UTM 28N (Canarias)"))


class BloqueCoordenadas(QWidget):
    def __init__(self, pestana, parent=None):
        super().__init__(parent)
        self.pestana = pestana
        self.lectura = None
        self.capa_creada = None
        self.construir()
        self.fichero.fileChanged.connect(self.actualizar)
        self.huso.currentIndexChanged.connect(self.actualizar)
        self.crearBoton.clicked.connect(self.crear)
        self.actualizar()

    def construir(self):
        caja = QVBoxLayout(self)
        formulario = QFormLayout()
        self.fichero = QgsFileWidget(self)
        self.fichero.setStorageMode(QgsFileWidget.StorageMode.GetFile)
        self.fichero.setFilter("Puntos (*.txt *.csv *.dat *.xyz *.pts);;Todos (*.*)")
        self.fichero.setDialogTitle("Elegir el fichero de coordenadas del levantamiento")
        self.fichero.setToolTip("Una línea por punto: X Y, o nombre X Y (con Z o un código detrás, si los lleva). Varias "
                                "parcelas: separadas por una línea en blanco o por un título («Parcela 2»), o con una "
                                "primera columna con el identificador de la parcela de cada punto")
        formulario.addRow("Fichero", self.fichero)
        self.huso = QComboBox(self)
        for epsg, nombre in HUSOS:
            self.huso.addItem(nombre, epsg)
        self.huso.setToolTip("Sistema de referencia de las coordenadas del fichero (el del levantamiento)")
        proyecto = QgsProject.instance().crs().postgisSrid()
        self.huso.setCurrentIndex(max(self.huso.findData(proyecto if proyecto in dict(HUSOS) else 25830), 0))
        formulario.addRow("Sistema", self.huso)
        caja.addLayout(formulario)
        self.estado = QLabel(self)
        self.estado.setWordWrap(True)
        self.estado.setTextFormat(Qt.TextFormat.RichText)
        caja.addWidget(self.estado)
        botones = QHBoxLayout()
        botones.addStretch(1)
        self.crearBoton = QPushButton(QgsApplication.getThemeIcon(ICONO), "Crear capa", self)
        self.crearBoton.setToolTip("Pone las parcelas en una capa del proyecto y abre la pestaña Parcela con ella")
        botones.addWidget(self.crearBoton)
        caja.addLayout(botones)
        caja.addStretch(1)

    def epsg(self):
        return self.huso.currentData()

    def soltar(self, rutas):
        self.fichero.setFilePath(rutas[0])

    def leer(self):
        """Lee el fichero elegido. None si no hay; si no se puede abrir, una Lectura con el error."""
        ruta = self.fichero.filePath().strip()
        if not ruta:
            return None
        lectura = co.Lectura()
        try:
            with open(ruta, 'rb') as f:
                datos = f.read(20_000_000)
        except FileNotFoundError:
            lectura.incidencias.append(co.Incidencia(ERROR, 'FICHERO', f"No existe el fichero {os.path.basename(ruta)}"))
            return lectura
        except OSError as e:
            lectura.incidencias.append(co.Incidencia(ERROR, 'FICHERO', f"No se puede abrir {os.path.basename(ruta)}: "
                                                                        f"{e.strerror or e}"))
            return lectura
        if b'\x00' in datos[:4096] and not datos.startswith((b'\xff\xfe', b'\xfe\xff')):
            lectura.incidencias.append(co.Incidencia(ERROR, 'COORD-BINARIO', f"{os.path.basename(ruta)} no es un fichero de "
                                                                              "texto (TXT o CSV con las coordenadas)"))
            return lectura
        if datos.startswith((b'\xff\xfe', b'\xfe\xff')):
            texto = datos.decode('utf-16', 'replace')
        else:
            texto = co.decodificar(datos)
        lectura = co.leer(texto)
        crs = QgsCoordinateReferenceSystem(f'EPSG:{self.epsg()}')
        geometrias = [p.geometria for p in lectura.parcelas if p.geometria is not None]
        if geometrias:
            aviso = geo.aviso_huso(QgsGeometry.unaryUnion(geometrias), crs, self.epsg())
            if aviso is not None:
                lectura.incidencias.append(aviso)
        return lectura

    def actualizar(self, *args):
        self.lectura = self.leer()
        if self.lectura is None:
            self.estado.setText('')
            self.crearBoton.setEnabled(False)
            return
        lineas = [escape(co.resumen(self.lectura))]
        problemas = [i for i in self.lectura.incidencias + [i for p in self.lectura.parcelas for i in p.incidencias]
                     if i.nivel in (ERROR, AVISO)]
        for i in problemas[:MAX_LINEAS]:
            color = '#c92a2a' if i.nivel == ERROR else '#e67700'
            lineas.append(f"<span style='color:{color}'>{'✖' if i.nivel == ERROR else '⚠'} "
                          f"{escape(f'{i.elemento}: ' if i.elemento else '')}{escape(i.mensaje)}</span>")
        if len(problemas) > MAX_LINEAS:
            lineas.append(f"… y {len(problemas) - MAX_LINEAS} más")
        if self.lectura.saltadas:
            saltadas = ', '.join(map(str, self.lectura.saltadas[:10])) + ('…' if len(self.lectura.saltadas) > 10 else '')
            lineas.append(f"<span style='color:#495057'>Líneas sin coordenadas, saltadas: {saltadas}</span>")
        self.estado.setText("<small>" + "<br>".join(lineas) + "</small>")
        self.crearBoton.setEnabled(bool(self.validas()))

    def validas(self):
        """Parcelas que se pueden poner en la capa (con geometría y sin errores)."""
        if self.lectura is None or any(i.nivel == ERROR for i in self.lectura.incidencias):
            return []
        return [p for p in self.lectura.parcelas
                if p.geometria is not None and not any(i.nivel == ERROR for i in p.incidencias)]

    def crear(self, *args):
        """La capa con las parcelas, en el proyecto; la pestaña Parcela pasa a trabajar con ella."""
        dock = self.pestana.dock
        dock.messageBar.clearWidgets()
        self.actualizar()
        validas = self.validas()
        if not validas:
            dock.warn("No hay parcelas que crear: revise los avisos de la utilidad")
            return None
        ruta = self.fichero.filePath().strip()
        nombre = os.path.splitext(os.path.basename(ruta))[0]
        #Los campos en la dirección de la capa: vale igual en QGIS 3 y 4 (sin QVariant ni QMetaType)
        capa = QgsVectorLayer(f"Polygon?crs=EPSG:{self.epsg()}&field=localId:string(100)&field=puntos:integer", nombre,
                              'memory')
        proveedor = capa.dataProvider()
        entidades = []
        for parcela in validas:
            entidad = QgsFeature(capa.fields())
            entidad.setGeometry(QgsGeometry(parcela.geometria))
            entidad.setAttributes([parcela.identificador, len(parcela.puntos)])
            entidades.append(entidad)
        proveedor.addFeatures(entidades)
        capa.updateExtents()
        QgsProject.instance().addMapLayer(capa)
        self.capa_creada = capa
        descartadas = len(self.lectura.parcelas) - len(validas)
        dock.parcela_descargada(capa)  #La pestaña Parcela trabaja con ella (como con una parcela descargada)
        dock.tabWidget.setCurrentWidget(dock.tabParcela)
        avisos = [f"{i.elemento}: {i.mensaje}" if i.elemento else i.mensaje
                  for i in self.lectura.incidencias + [i for p in validas for i in p.incidencias] if i.nivel == AVISO]
        if descartadas:
            avisos.insert(0, f"{descartadas} parcela{'s' if descartadas > 1 else ''} del fichero no se "
                             f"{'han' if descartadas > 1 else 'ha'} podido formar (vea la utilidad)")
        dock.success(f"Capa «{nombre}»: {len(validas)} parcela{'s' if len(validas) != 1 else ''} desde coordenadas",
                     [], detalles=avisos,
                     notas=["Elija en la tabla el identificador y el namespace de cada una (y la alteración) y cree el GML",
                            "La capa es temporal: si quiere conservarla, guárdela desde el panel de Capas"])
        return capa
