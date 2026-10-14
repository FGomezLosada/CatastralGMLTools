"""
Bloque «Dividir la parcela seleccionada» de la pestaña Parcela (fase 10, AU-54; USABILIDAD U-09): divide la parcela
seleccionada en el mapa con linderos paralelos o perpendiculares a uno de sus lados (core/division.py), muestra antes el
resultado, la sustituye en la capa (Ctrl+Z lo deshace) y propone la operación (segregación o división) en el asistente.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsGeometry, QgsProject
from qgis.gui import QgsCollapsibleGroupBox, QgsRubberBand
from qgis.PyQt import sip
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton

from ..core import alteraciones as alt
from ..core import capa_parcelas as cp
from ..core import division as dv
from ..core import geometria as geo
from ..core.incidencias import AVISO, ERROR

OPERACIONES = ((alt.SEGREGACION, "Segregación (la mayor conserva la referencia)"),
               (alt.DIVISION, "División (todas son parcelas nuevas)"))


class BloqueDivision(QgsCollapsibleGroupBox):
    def __init__(self, pestana, parent=None):
        super().__init__("Dividir la parcela seleccionada", parent)
        self.pestana = pestana
        self.banda = None      #Lado elegido, marcado en el mapa
        self.piezas = []       #Resultado previsto (en el SRC de cálculo)
        self.construir()
        self.setCollapsed(True)
        self.modo.currentIndexChanged.connect(self.modo_cambiado)
        self.valores.textChanged.connect(self.previsualizar)
        self.direccion.currentIndexChanged.connect(self.previsualizar)
        self.lado.currentIndexChanged.connect(self.previsualizar)
        self.invertir.toggled.connect(self.previsualizar)
        self.dividirBoton.clicked.connect(self.dividir)
        self.collapsedStateChanged.connect(self.plegado)

    def construir(self):
        formulario = QFormLayout(self)
        self.modo = QComboBox(self)
        for modo in dv.MODOS:
            self.modo.addItem(dv.NOMBRES[modo], modo)
        formulario.addRow("Cómo", self.modo)
        self.valores = QLineEdit(self)
        self.valores.setPlaceholderText(f"p. ej. {dv.EJEMPLOS[dv.PARTES]}")
        self.valores.setToolTip("Partes: cuántas. Porcentajes, superficies, cuotas o franjas: los valores separados por "
                                "espacios. Si los porcentajes o las superficies no llegan al total, lo que falta es una "
                                "parcela más al final (como en el editor de la Sede)")
        formulario.addRow("Valores", self.valores)
        self.direccion = QComboBox(self)
        self.direccion.addItem("Linderos paralelos al lado", False)
        self.direccion.addItem("Linderos perpendiculares al lado", True)
        self.lado = QComboBox(self)
        self.lado.setToolTip("Lado de la parcela que marca la dirección de los linderos nuevos (se ve en rojo en el mapa)")
        fila = QHBoxLayout()
        fila.addWidget(self.direccion, 1)
        fila.addWidget(self.lado, 1)
        formulario.addRow("Dirección", fila)
        self.invertir = QCheckBox("Empezar por el lado opuesto", self)
        formulario.addRow("", self.invertir)
        self.operacion = QComboBox(self)
        for tipo, texto in OPERACIONES:
            self.operacion.addItem(texto, tipo)
        self.operacion.setToolTip("La que figurará en la escritura: la Sede no la deduce de las superficies")
        formulario.addRow("Operación", self.operacion)
        self.vista = QLabel(self)
        self.vista.setWordWrap(True)
        formulario.addRow(self.vista)
        self.dividirBoton = QPushButton("Dividir", self)
        self.dividirBoton.setEnabled(False)
        formulario.addRow("", self.dividirBoton)

    # ------------------------------------------------------------------ Parcela elegida

    def parcela(self):
        """(capa, entidad) de la única parcela seleccionada en la capa de la pestaña, o (capa, None)."""
        capa = self.pestana.capa()
        if capa is None or capa.selectedFeatureCount() != 1:
            return capa, None
        return capa, next(capa.getSelectedFeatures())

    def src_calculo(self, capa):
        """SRC en el que se divide: el de la capa si es proyectado; si es geográfico, el del GML (UTM)."""
        if capa.crs().isGeographic():
            epsg = self.pestana.epsg_salida()
            return QgsCoordinateReferenceSystem(f'EPSG:{epsg}') if epsg else None
        return capa.crs()

    def geometria_calculo(self):
        capa, entidad = self.parcela()
        if entidad is None:
            return capa, None, None
        crs = self.src_calculo(capa)
        if crs is None:
            return capa, None, None
        g = QgsGeometry(entidad.geometry())
        if crs != capa.crs():
            g = geo.transformar(g, capa.crs(), geo.epsg_de(crs))
        return capa, entidad, g

    def actualizar(self, *args):
        """Al cambiar la selección o la capa: lados de la parcela elegida y previsualización."""
        if sip.isdeleted(self):
            return
        _, _, g = self.geometria_calculo()
        anterior = self.lado.currentIndex()
        self.lado.blockSignals(True)
        self.lado.clear()
        if g is not None:
            for i, (_, _, largo, azimut) in enumerate(dv.lados(g), start=1):
                self.lado.addItem(f"Lado {i} · {largo:.2f} m · {azimut:.0f}°")
            if 0 <= anterior < self.lado.count():
                self.lado.setCurrentIndex(anterior)
        self.lado.blockSignals(False)
        self.previsualizar()

    def modo_cambiado(self, *args):
        self.valores.setPlaceholderText(f"p. ej. {dv.EJEMPLOS[self.modo.currentData()]}")
        self.previsualizar()

    # ------------------------------------------------------------------ Previsualización

    def calcular(self):
        """Piezas previstas y texto del resultado (o del motivo por el que no se puede dividir)."""
        capa, entidad, g = self.geometria_calculo()
        if capa is None:
            return [], "Elija una capa de parcelas."
        if entidad is None:
            return [], "Seleccione en el mapa una sola parcela."
        if g is None:
            return [], "La capa no tiene un SRC que permita medir: revíselo."
        try:
            valores = dv.leer_valores(self.valores.text())
        except ValueError:
            return [], "Escriba solo números separados por espacios."
        piezas, incidencias = dv.dividir(g, self.modo.currentData(), valores, self.lado.currentIndex(),
                                         self.direccion.currentData(), self.invertir.isChecked())
        errores = [i.mensaje for i in incidencias if i.nivel == ERROR]
        if errores or not piezas:
            return [], errores[0] if errores else "No se ha podido dividir."
        texto = f"{len(piezas)} parcelas: " + " · ".join(f"{p.area():.2f}" for p in piezas) + " m²"
        avisos = [i.mensaje for i in incidencias if i.nivel == AVISO]
        return piezas, texto + ''.join(f"<br><span style='color:#e67700'>⚠ {a}</span>" for a in avisos)

    def previsualizar(self, *args):
        if sip.isdeleted(self):
            return
        self.piezas, texto = self.calcular() if self.valores.text().strip() or self.parcela()[1] is None else ([], "")
        self.vista.setText(f"<small>{texto}</small>")
        self.dividirBoton.setEnabled(bool(self.piezas))
        self.marcar_lado()

    def marcar_lado(self, *args):
        """
        El lado elegido, en rojo en el mapa: solo con el bloque abierto, la pestaña Parcela a la vista y el panel abierto
        (al cambiar de pestaña o cerrar el panel, el dock vuelve a llamar aquí y la marca se quita).
        """
        lienzo = self.lienzo()
        if lienzo is None:
            return
        if self.banda is None:
            self.banda = QgsRubberBand(lienzo, Qgis.GeometryType.Line)
            self.banda.setColor(QColor(224, 49, 49))
            self.banda.setWidth(4)
        self.banda.reset(Qgis.GeometryType.Line)
        capa, entidad = self.parcela()
        dock = self.pestana.dock
        if (self.isCollapsed() or entidad is None or not self.isVisibleTo(dock)
                or getattr(dock, 'cerrado', False)):
            return
        todos = dv.lados(entidad.geometry())
        i = self.lado.currentIndex()
        if 0 <= i < len(todos):
            a, b = todos[i][0], todos[i][1]
            linea = QgsGeometry.fromPolylineXY([a, b])
            destino = lienzo.mapSettings().destinationCrs()
            if destino.isValid() and destino != capa.crs():
                linea.transform(QgsCoordinateTransform(capa.crs(), destino, QgsProject.instance()))
            self.banda.setToGeometry(linea, None)

    def lienzo(self):
        iface = getattr(self.pestana.dock, 'iface', None)
        return iface.mapCanvas() if iface is not None and hasattr(iface, 'mapCanvas') else None

    def plegado(self, *args):
        self.actualizar()

    def soltar(self):
        """Quita la marca del mapa (al cerrar el plugin)."""
        lienzo = self.lienzo()
        if self.banda is not None and lienzo is not None and not sip.isdeleted(self.banda):
            lienzo.scene().removeItem(self.banda)
        self.banda = None

    # ------------------------------------------------------------------ Dividir

    def dividir(self, *args):
        """Sustituye la parcela por las piezas en la capa y propone la operación elegida."""
        piezas, texto = self.calcular()
        capa, entidad = self.parcela()
        if not piezas or entidad is None:
            self.pestana.dock.warn(texto or "No se ha podido dividir")
            return None
        superficies = " · ".join(f"{p.area():.2f}" for p in piezas)  #En el SRC de cálculo (metros)
        crs = self.src_calculo(capa)
        if crs != capa.crs():  #Calculado en UTM: se vuelve al SRC de la capa
            vuelta = QgsCoordinateTransform(crs, capa.crs(), QgsProject.instance())
            piezas = [QgsGeometry(p) for p in piezas]
            for p in piezas:
                p.transform(vuelta)
        antes = self.pestana.estado_antes_de_editar()
        self.pestana.editando = True
        try:
            fids = cp.dividir_en_capa(capa, entidad.id(), piezas)
        finally:
            self.pestana.editando = False
        if not fids:
            self.pestana.dock.warn("La capa no permite editar sus parcelas")
            return None
        antes['ausentes'] = fids[1:]
        self.pestana.antes_union = antes  #Con Ctrl+Z la tabla y la alteración vuelven a como estaban
        capa.selectByIds(fids)
        self.pestana.recargar()
        self.pestana.poner_alteracion(self.operacion.currentData(), False)
        self.pestana.dock.success(f"Parcela dividida en {len(fids)}: {superficies} m² · propuesta: {alt.NOMBRES[self.operacion.currentData()]}. La capa queda en "
                                  "edición (Ctrl+Z deshace también la tabla; guarde la capa para conservarla)")
        self.valores.clear()
        return fids
