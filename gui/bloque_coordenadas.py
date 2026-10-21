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
    QgsPalLayerSettings,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
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
        self.capa_puntos_creada = None
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
        self.crearBoton = QPushButton(QgsApplication.getThemeIcon(ICONO), "Crear capas", self)
        self.crearBoton.setToolTip("Pone en el proyecto, en un grupo, las parcelas y todos los puntos del fichero (con el "
                                   "nombre, la Z y el código de cada uno), y abre la pestaña Parcela con las parcelas")
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
        #El huso, con las parcelas buenas: una con una coordenada mal escrita lo falsearía (prueba a mano del 20/10/2026)
        geometrias = [p.geometria for p in lectura.parcelas
                      if p.geometria is not None and not any(i.nivel == ERROR for i in p.incidencias)]
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
        self.crearBoton.setEnabled(self.con_puntos())
        self.crearBoton.setText("Crear capas" if self.validas() or not self.con_puntos() else "Ver los puntos en el mapa")

    def validas(self):
        """Parcelas que se pueden poner en la capa (con geometría y sin errores)."""
        if self.lectura is None or any(i.nivel == ERROR for i in self.lectura.incidencias):
            return []
        return [p for p in self.lectura.parcelas
                if p.geometria is not None and not any(i.nivel == ERROR for i in p.incidencias)]

    def con_puntos(self):
        """¿Hay puntos que se puedan poner en el mapa? (no si el fichero no se lee o las coordenadas son grados)"""
        return (self.lectura is not None and any(p.puntos for p in self.lectura.parcelas)
                and not any(i.nivel == ERROR for i in self.lectura.incidencias))

    def crear(self, *args):
        """
        Un grupo con dos capas: las parcelas (las que se han podido formar; la pestaña Parcela pasa a trabajar con ellas)
        y todos los puntos del fichero con sus datos (nombre del vértice, X, Y, Z, código, línea), para no perder nada de
        lo que trae el levantamiento (prueba a mano del 20/10/2026) y para ver dónde está lo que falla. Sin parcelas
        buenas, solo los puntos.
        """
        dock = self.pestana.dock
        dock.messageBar.clearWidgets()
        self.actualizar()
        if not self.con_puntos():
            dock.warn("No hay puntos que poner en el mapa: revise los avisos de la utilidad")
            return None
        validas = self.validas()
        ruta = self.fichero.filePath().strip()
        nombre = os.path.splitext(os.path.basename(ruta))[0]
        proyecto = QgsProject.instance()
        grupo = proyecto.layerTreeRoot().insertGroup(0, nombre)
        puntos = self.capa_puntos(f"{nombre} · puntos", validas)
        proyecto.addMapLayer(puntos, False)
        grupo.addLayer(puntos)
        capa = None
        if validas:
            capa = self.capa_parcelas(nombre, validas, os.path.basename(ruta))
            proyecto.addMapLayer(capa, False)
            grupo.addLayer(capa)
        self.capa_creada, self.capa_puntos_creada = capa, puntos
        n_puntos = sum(len(p.puntos) for p in self.lectura.parcelas)
        if capa is None:
            dock.warn(f"Ninguna parcela del fichero se ha podido formar: en el mapa están sus {n_puntos} puntos "
                      f"(capa «{puntos.name()}», con el nombre de cada vértice) para ver qué falla")
            return None
        descartadas = len(self.lectura.parcelas) - len(validas)
        dock.parcela_descargada(capa)  #La pestaña Parcela trabaja con ella (como con una parcela descargada)
        dock.tabWidget.setCurrentWidget(dock.tabParcela)
        avisos = [f"{i.elemento}: {i.mensaje}" if i.elemento else i.mensaje
                  for i in self.lectura.incidencias + [i for p in validas for i in p.incidencias] if i.nivel == AVISO]
        if descartadas:
            avisos.insert(0, f"{descartadas} parcela{'s' if descartadas > 1 else ''} del fichero no se "
                             f"{'han' if descartadas > 1 else 'ha'} podido formar (vea la utilidad; sus puntos están "
                             "en la capa de puntos)")
        dock.success(f"Capa «{nombre}»: {len(validas)} parcela{'s' if len(validas) != 1 else ''} desde coordenadas, y "
                     f"sus {n_puntos} puntos con sus datos", [], detalles=avisos,
                     notas=["Elija en la tabla el identificador y el namespace de cada una (y la alteración) y cree el GML",
                            "Las capas son temporales: si quiere conservarlas, guárdelas desde el panel de Capas"])
        return capa

    def capa_parcelas(self, nombre, validas, fichero):
        #Los campos en la dirección de la capa: vale igual en QGIS 3 y 4 (sin QVariant ni QMetaType)
        capa = QgsVectorLayer(f"Polygon?crs=EPSG:{self.epsg()}&field=localId:string(100)&field=puntos:integer"
                              "&field=vertices:string(254)&field=fichero:string(254)", nombre, 'memory')
        entidades = []
        for parcela in validas:
            entidad = QgsFeature(capa.fields())
            entidad.setGeometry(QgsGeometry(parcela.geometria))
            nombres = '-'.join(p.nombre for p in parcela.puntos if p.nombre)
            entidad.setAttributes([parcela.identificador, len(parcela.puntos),
                                   nombres if len(nombres) <= 254 else nombres[:253] + '…', fichero])
            entidades.append(entidad)
        capa.dataProvider().addFeatures(entidades)
        capa.updateExtents()
        return capa

    def capa_puntos(self, nombre, validas):
        """Todos los puntos del fichero, con lo que traía cada línea, y si su parcela se ha formado."""
        capa = QgsVectorLayer(f"Point?crs=EPSG:{self.epsg()}&field=parcela:string(100)&field=orden:integer"
                              "&field=nombre:string(100)&field=x:double&field=y:double&field=z:double"
                              "&field=codigo:string(254)&field=linea:integer&field=estado:string(30)", nombre, 'memory')
        buenas = {id(p) for p in validas}
        entidades = []
        for parcela in self.lectura.parcelas:
            estado = 'parcela formada' if id(parcela) in buenas else 'parcela no formada'
            for orden, punto in enumerate(parcela.puntos, start=1):
                entidad = QgsFeature(capa.fields())
                entidad.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(punto.x, punto.y)))
                entidad.setAttributes([parcela.identificador, orden, punto.nombre, punto.x, punto.y, punto.z,
                                       punto.codigo[:254], punto.linea, estado])
                entidades.append(entidad)
        capa.dataProvider().addFeatures(entidades)
        capa.updateExtents()
        etiquetas = QgsPalLayerSettings()
        etiquetas.fieldName = "if(length(\"nombre\") > 0, \"nombre\", to_string(\"orden\"))"  #Sin nombre, su orden
        etiquetas.isExpression = True
        formato = QgsTextFormat()  #Con halo blanco: se lee sobre el relleno de las parcelas y sobre la ortofoto
        halo = QgsTextBufferSettings()
        halo.setEnabled(True)
        halo.setSize(1.0)
        halo.setColor(QColor('white'))
        formato.setBuffer(halo)
        etiquetas.setFormat(formato)
        capa.setLabeling(QgsVectorLayerSimpleLabeling(etiquetas))
        capa.setLabelsEnabled(True)
        return capa
