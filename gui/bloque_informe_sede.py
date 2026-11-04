"""
Utilidad «Leer informe de la Sede (IVG o ICUC)» de la pestaña Utilidades (AU-56, mejora 32; maqueta aprobada el
04/11/2026): abre el PDF del informe (o su XML), muestra el resultado, la operación, las parcelas presentadas con su
superficie y sus linderos y las parcelas catastrales afectadas; carga en el mapa lo presentado sobre lo afectado, guarda
el GML presentado tal como lo recibió la Sede y lo abre en Validar (core/informe_sede.py).

No lee ni muestra datos personales (los del técnico y del solicitante que trae el informe).

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os
from html import escape

from qgis.core import QgsApplication, QgsProject
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import gml_lector as gl
from ..core import informe_sede as isd
from . import desplazable

ICONO = '/mActionIdentify.svg'
GRUPO = 'catastral_gml_tools/informe_sede'  #Propiedad del grupo del informe en el mapa
ROJO = '#c92a2a'
VERDE = '#2b8a3e'
NOTA_PRIVACIDAD = ("Del informe no se leen ni se muestran los datos personales (NIF, nombre y contacto del técnico o del "
                   "solicitante).")


class BloqueInformeSede(QWidget):
    def __init__(self, pestana, parent=None):
        super().__init__(parent)
        self.pestana = pestana
        self.informe = None
        self.ruta = ''
        self.guardado = ''
        self.construir()
        self.fichero.fileChanged.connect(self.abrir)
        self.mapaBoton.clicked.connect(self.cargar_en_mapa)
        self.guardarBoton.clicked.connect(self.guardar)
        self.validarBoton.clicked.connect(self.abrir_en_validar)
        self.mostrar()

    def construir(self):
        caja = QVBoxLayout(self)
        fila = QHBoxLayout()
        fila.addWidget(QLabel("Informe", self))
        self.fichero = QgsFileWidget(self)
        self.fichero.setStorageMode(QgsFileWidget.StorageMode.GetFile)
        self.fichero.setFilter("Informe de la Sede (*.pdf *.xml)")
        self.fichero.setDialogTitle("Elegir el informe de la Sede (PDF del IVG o del ICUC)")
        self.fichero.setToolTip("El PDF que descarga de la Sede tras la validación gráfica (IVG) o el informe de ubicación "
                                "de las construcciones (ICUC). Lleva dentro el resultado y los GML")
        fila.addWidget(self.fichero, 1)
        caja.addLayout(fila)
        self.resultado = QLabel(self)
        self.resultado.setWordWrap(True)
        self.resultado.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        caja.addWidget(self.resultado)
        self.tituloTabla = QLabel(self)
        caja.addWidget(self.tituloTabla)
        self.tabla = QTableWidget(0, 4, self)
        self.tabla.setHorizontalHeaderLabels(["Identificador", "Namespace", "Sup. m²", "Linda con"])
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tabla.setMinimumHeight(70)
        desplazable.proteger(self.tabla)
        caja.addWidget(self.tabla, 1)
        self.afectadas = QLabel(self)
        self.afectadas.setWordWrap(True)
        self.afectadas.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        caja.addWidget(self.afectadas)
        nota = QLabel(f"<small style='color:#666'>{NOTA_PRIVACIDAD}</small>", self)
        nota.setWordWrap(True)
        caja.addWidget(nota)
        botones = desplazable.FilaFlexible()
        self.mapaBoton = QPushButton(QgsApplication.getThemeIcon('/mActionAddLayer.svg'), "Cargar en el mapa", self)
        self.mapaBoton.setToolTip("Lo presentado (naranja) sobre las parcelas catastrales afectadas (gris; en rojo las "
                                  "afectadas solo en parte)")
        self.guardarBoton = QPushButton(QgsApplication.getThemeIcon('/mActionFileSave.svg'), "Guardar el GML presentado",
                                        self)
        self.guardarBoton.setToolTip("El GML tal como lo recibió la Sede, junto al informe y con el CSV en el nombre")
        self.validarBoton = QPushButton(QgsApplication.getThemeIcon('/mActionFileOpen.svg'), "Abrir en Validar", self)
        self.validarBoton.setToolTip("Guarda el GML presentado (si no lo estaba) y lo compara en Validar con el Catastro de "
                                     "hoy")
        for boton in (self.mapaBoton, self.guardarBoton, self.validarBoton):
            botones.addWidget(boton)
        caja.addLayout(botones)

    # ------------------------------------------------------------------ Lectura

    def soltar(self, rutas):
        self.fichero.setFilePath(rutas[0])

    def abrir(self, *args):
        ruta = os.path.normpath(self.fichero.filePath().strip()) if self.fichero.filePath().strip() else ''
        self.ruta, self.guardado = ruta, ''
        self.informe = isd.leer(ruta) if ruta and os.path.isfile(ruta) else None
        self.mostrar()
        if self.informe is not None and self.informe.errores:
            self.pestana.dock.warn(self.informe.errores[0])
        return self.informe

    def mostrar(self):
        i = self.informe
        hay = i is not None and not i.errores
        for boton in (self.mapaBoton, self.guardarBoton, self.validarBoton):
            boton.setEnabled(hay)
        self.guardarBoton.setEnabled(hay and bool(i.gml_presentado))
        self.validarBoton.setEnabled(hay and bool(i.gml_presentado))
        self.mapaBoton.setEnabled(hay and bool(i.gml_presentado or i.gml_afectadas))
        self.tabla.setRowCount(0)
        if i is None:
            self.resultado.setText("<small>Elija el PDF del informe que da la Sede tras la validación gráfica (IVG) o el "
                                   "del informe de ubicación de las construcciones (ICUC). También puede arrastrarlo.</small>")
            self.tituloTabla.setText('')
            self.afectadas.setText('')
            self.tabla.setVisible(False)
            return
        if i.errores:
            self.resultado.setText(f"<small><span style='color:{ROJO}'>{escape(i.errores[0])}</span></small>")
            self.tituloTabla.setText('')
            self.afectadas.setText('')
            self.tabla.setVisible(False)
            return
        color = VERDE if i.positivo else ROJO
        marca = '✔' if i.positivo else '✖'
        detalles = [isd.NOMBRES.get(i.tipo, i.tipo)] + ([f"CSV {i.csv}"] if i.csv else []) + \
            ([f"emitido el {i.fecha}"] if i.fecha else []) + ([f"precisión {i.precision} m"] if i.precision else [])
        self.resultado.setText(f"<b style='color:{color}'>{marca} {escape(i.titulo())}</b><br>"
                               f"<small>{escape(' · '.join(detalles))}</small>")
        if i.tipo == isd.IVG:
            self.tituloTabla.setText("<b>Parcelas presentadas</b> <small>(las del GML que se subió)</small>")
            self.tabla.setVisible(True)
            self.llenar_tabla(i)
        else:
            presentado, _ = isd.lecturas(i)
            n = len(presentado.elementos) if presentado is not None else 0
            self.tituloTabla.setText(f"<b>GML de construcciones presentado</b> <small>· {escape(i.nombre_presentado)} · "
                                     f"{n} elemento{'s' if n != 1 else ''}</small>")
            self.tabla.setVisible(False)
        lineas = []
        if i.afectadas_total:
            lineas.append(f"{escape(', '.join(i.afectadas_total))} · en su totalidad")
        if i.afectadas_parcial:
            lineas.append(f"<span style='color:{ROJO}'>{escape(', '.join(i.afectadas_parcial))} · solo en parte: la Sede "
                          "no admite afectar en parte a una parcela (corrija el lindero común o inclúyala)</span>")
        titulo = "Parcela catastral" if i.tipo == isd.ICUC else "Parcelas catastrales afectadas"
        self.afectadas.setText(f"<b>{titulo}</b><br>" + "<br>".join(lineas) if lineas else '')

    def llenar_tabla(self, i):
        locales = {p.identificador for p in i.parcelas}
        self.tabla.setRowCount(len(i.parcelas))
        for fila, p in enumerate(i.parcelas):
            linda = [f"{x} (del GML)" if x in locales else x for x in p.linda_gml] + p.linda_catastro
            valores = [p.identificador, p.namespace, p.superficie, " · ".join(linda)]
            for columna, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                if columna == 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item.setToolTip(valor)
                self.tabla.setItem(fila, columna, item)
        self.tabla.resizeColumnsToContents()
        self.tabla.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

    # ------------------------------------------------------------------ Acciones

    def guardar(self, *args):
        """Guarda el GML presentado junto al informe. Devuelve la ruta o None."""
        dock = self.pestana.dock
        i = self.informe
        if i is None or not i.gml_presentado:
            return None
        ruta = isd.ruta_presentado(self.ruta, i)
        problema = isd.guardar_presentado(i, ruta)
        if problema is not None:
            dock.warn(f"No se ha guardado el GML presentado: {problema.mensaje}")
            return None
        self.guardado = ruta
        dock.success(f"GML presentado en el informe {i.csv}: {os.path.basename(ruta)}, junto al informe",
                     [("Abrir carpeta", self.abrir_carpeta), ("Abrir en Validar", self.abrir_en_validar)])
        return ruta

    def abrir_carpeta(self, *args):
        if self.guardado:
            self.pestana.dock.open_path(os.path.dirname(self.guardado))

    def abrir_en_validar(self, *args):
        ruta = self.guardado if self.guardado and os.path.isfile(self.guardado) else self.guardar()
        if ruta:
            self.pestana.dock.abrir_en_validar(ruta)
        return ruta

    def cargar_en_mapa(self, *args):
        """Grupo «Informe <CSV>»: lo presentado (naranja) encima de las parcelas catastrales afectadas (gris o rojo)."""
        from . import estilos
        i = self.informe
        if i is None or i.errores:
            return []
        presentado, afectadas = isd.lecturas(i)
        proyecto = QgsProject.instance()
        raiz = proyecto.layerTreeRoot()
        for grupo in [g for g in raiz.findGroups(True) if g.customProperty(GRUPO) == (i.csv or self.ruta)]:
            proyecto.removeMapLayers(grupo.findLayerIds())
            (grupo.parent() or raiz).removeChildNode(grupo)
        grupo = raiz.insertGroup(0, f"Informe de la Sede {i.csv} ({i.tipo})")
        grupo.setCustomProperty(GRUPO, i.csv or self.ruta)
        capas = []
        if presentado is not None and presentado.elementos:
            capas.append(estilos.aplicar(gl.capa(presentado, f"Presentado: {os.path.splitext(i.nombre_presentado)[0]}")))
        if afectadas is not None and afectadas.elementos:
            parciales = set(i.afectadas_parcial)
            for titulo, color, elementos in (
                    ("Afectadas solo en parte (a corregir)", ROJO,
                     [e for e in afectadas.elementos if e.local_id in parciales]),
                    ("Parcelas catastrales afectadas (las del informe)", estilos.COLOR_COLINDANTES,
                     [e for e in afectadas.elementos if e.local_id not in parciales])):
                if not elementos:
                    continue
                lectura = gl.ResultadoLectura(version=afectadas.version, epsg=afectadas.epsg, elementos=elementos)
                capa = estilos.aplicar(gl.capa(lectura, titulo), {gl.PARCELA: color}, campo_etiqueta='label')
                metadatos = capa.metadata()
                metadatos.setAbstract(f"Parcelas catastrales afectadas según el informe {i.csv} de la Sede (la "
                                      "geometría va dentro del propio informe)")
                capa.setMetadata(metadatos)
                capas.append(capa)
        for capa in capas:
            proyecto.addMapLayer(capa, False)
            grupo.addLayer(capa)
        iface = getattr(self.pestana.dock, 'iface', None)
        if capas and iface is not None and hasattr(iface, 'mapCanvas'):
            try:
                lienzo = iface.mapCanvas()
                lienzo.setExtent(lienzo.mapSettings().layerExtentToOutputExtent(capas[-1], capas[-1].extent()).buffered(5))
                lienzo.refresh()
            except (AttributeError, TypeError):
                pass
        return capas
