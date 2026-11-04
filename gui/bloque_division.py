"""
Bloque «Dividir parcela» de la pestaña Parcela (fase 10, AU-54; USABILIDAD U-01 y U-09): divide la parcela
seleccionada en el mapa con linderos paralelos o perpendiculares a uno de sus lados, o en abanico desde un vértice
(pivote; core/division.py), muestra antes el
resultado, la sustituye en la capa (Ctrl+Z lo deshace) y propone la operación (segregación o división) en el asistente.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsGeometry, QgsProject
from qgis.gui import QgsRubberBand
from qgis.PyQt import sip
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QCheckBox, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton

from ..core import alteraciones as alt
from ..core import capa_parcelas as cp
from ..core import division as dv
from ..core import geometria as geo
from ..core.incidencias import AVISO, ERROR
from ..core.validador import MAX_PARCELAS

PIVOTE = 'pivote'
TIP_LADO = "Lado de la parcela que marca la dirección de los linderos nuevos (se ve en rojo en el mapa)"
TIP_VERTICE = "Vértice del que salen los linderos nuevos (en rojo en el mapa, con sus dos lados)"
MAX_LISTA = 8  #Superficies que se listan en la vista previa; más, se resumen
OPERACIONES = ((alt.SEGREGACION, "Segregación (la mayor conserva la referencia)"),
               (alt.DIVISION, "División (todas son parcelas nuevas)"))


class BloqueDivision(QFrame):
    """
    Opciones de la división, debajo del botón «Dividir parcela» del paso 2 (Operación). Se abre y se pliega con ese botón
    (antes era una sección plegable suelta, lejos de «Unir parcelas»: USABILIDAD U-01). Una raya a la izquierda la une
    al botón sin meterla en otra caja («una ventana dentro de otra», prueba a mano del 27/10).
    """
    collapsedStateChanged = pyqtSignal(bool)  # noqa: N815 (mismo nombre que en QgsCollapsibleGroupBox)

    def __init__(self, pestana, parent=None):
        super().__init__(parent)
        self.pestana = pestana
        self._plegado = False
        self.setObjectName('bloqueDivision')
        self.setStyleSheet("QFrame#bloqueDivision { border: none; border-left: 3px solid #4dabf7; }")
        self.banda = None      #Lado elegido, marcado en el mapa
        self.piezas = []       #Resultado previsto (en el SRC de cálculo)
        self.construir()
        self.setCollapsed(True)
        self.modo.currentIndexChanged.connect(self.modo_cambiado)
        self.valores.textChanged.connect(self.previsualizar)
        self.direccion.currentIndexChanged.connect(self.direccion_cambiada)
        self.lado.currentIndexChanged.connect(self.previsualizar)
        self.invertir.toggled.connect(self.previsualizar)
        self.dividirBoton.clicked.connect(self.dividir)
        self.collapsedStateChanged.connect(self.plegado)

    def isCollapsed(self):  # noqa: N802 (como en QgsCollapsibleGroupBox)
        return self._plegado

    def setCollapsed(self, plegado):  # noqa: N802
        plegado = bool(plegado)
        cambia = plegado != self._plegado
        self._plegado = plegado
        self.setVisible(not plegado)
        if cambia:
            self.collapsedStateChanged.emit(plegado)

    def construir(self):
        formulario = QFormLayout(self)
        formulario.setContentsMargins(10, 2, 0, 4)
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
        self.ayuda = QLabel(self)  #Qué escribir en el modo elegido, siempre a la vista
        self.ayuda.setWordWrap(True)
        formulario.addRow("", self.ayuda)
        self.poner_ayuda()
        self.direccion = QComboBox(self)
        self.direccion.addItem("Linderos paralelos al lado", False)
        self.direccion.addItem("Linderos perpendiculares al lado", True)
        self.direccion.addItem("Linderos desde un vértice (pivote)", PIVOTE)
        self.direccion.setItemData(2, "Todos los linderos nuevos salen del mismo vértice, en abanico (p. ej. desde una "
                                      "esquina hacia el lado de enfrente)", Qt.ItemDataRole.ToolTipRole)
        self.lado = QComboBox(self)
        self.lado.setToolTip(TIP_LADO)
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
        pivote = self.es_pivote()
        self.lado.setToolTip(TIP_VERTICE if pivote else TIP_LADO)
        self.invertir.setText("Empezar por el otro lado del vértice" if pivote else "Empezar por el lado opuesto")
        if g is not None:
            todos = dv.lados(g)
            for i, (_, _, largo, azimut) in enumerate(todos, start=1):
                if pivote:  #El vértice i es el inicio del lado i: entre el lado anterior y ese
                    self.lado.addItem(f"Vértice {i} · entre los lados {(i - 2) % len(todos) + 1} y {i}")
                else:
                    self.lado.addItem(f"Lado {i} · {largo:.2f} m · {azimut:.0f}°")
            if 0 <= anterior < self.lado.count():
                self.lado.setCurrentIndex(anterior)
        self.lado.blockSignals(False)
        self.previsualizar()

    def es_pivote(self):
        return self.direccion.currentData() == PIVOTE

    def direccion_cambiada(self, *args):
        self.actualizar()  #Lados o vértices en la lista

    def poner_ayuda(self):
        modo = self.modo.currentData()
        self.valores.setPlaceholderText(f"p. ej. {dv.EJEMPLOS[modo]}")
        self.ayuda.setText(f"<small style='color:#666'>{dv.AYUDAS[modo]}</small>")

    def modo_cambiado(self, *args):
        self.poner_ayuda()
        self.previsualizar()

    # ------------------------------------------------------------------ Previsualización

    def calcular(self):
        """Piezas previstas y texto del resultado (o del motivo por el que no se puede dividir)."""
        capa, entidad, g = self.geometria_calculo()
        if capa is None:
            return [], "Elija una capa de parcelas."
        if entidad is None:
            n = capa.selectedFeatureCount()
            if n > 1:
                return [], f"Hay {n} parcelas seleccionadas en «{capa.name()}»: deje seleccionada solo la que quiera dividir."
            return [], f"Seleccione en el mapa una sola parcela de la capa «{capa.name()}»."
        if g is None:
            return [], "La capa no tiene un SRC que permita medir: revíselo."
        try:
            valores = dv.leer_valores(self.valores.text())
        except ValueError:
            return [], "Escriba solo números separados por espacios."
        pivote = self.es_pivote()
        piezas, incidencias = dv.dividir(g, self.modo.currentData(), valores, self.lado.currentIndex(),
                                         self.direccion.currentData() is True, self.invertir.isChecked(), pivote)
        errores = [i.mensaje for i in incidencias if i.nivel == ERROR]
        if errores or not piezas:
            return [], errores[0] if errores else "No se ha podido dividir."
        total = sum(p.area() for p in piezas) or 1
        areas = [p.area() for p in piezas]
        if len(piezas) > MAX_LISTA and max(areas) - min(areas) < 0.01:
            #Muchas iguales: una línea, no una lista de 40 superficies (prueba final del 30/10/2026)
            texto = f"{len(piezas)} parcelas de {areas[0]:.2f} m² ({100 * areas[0] / total:.1f} % cada una)"
        else:
            lista = [f"{a:.2f} m² ({100 * a / total:.0f} %)" for a in areas]
            if len(lista) > MAX_LISTA:
                lista = lista[:MAX_LISTA] + [f"… y {len(lista) - MAX_LISTA} más"]
            texto = f"{len(piezas)} parcelas: " + " · ".join(lista)
        avisos = [i.mensaje for i in incidencias if i.nivel == AVISO]
        if any(i.codigo == 'DIV-PARTES' for i in incidencias):
            #Prueba a mano del 04/11/2026: se podía dividir y luego el GML no se creaba. Se dice antes y, con pivote,
            #desde qué vértices sale bien
            avisos.append("Así no se podrá crear el GML: la Sede solo admite un recinto por parcela")
            if pivote:
                buenos = dv.vertices_sin_trozos(g, self.modo.currentData(), valores, self.invertir.isChecked())
                if buenos:
                    lista = ", ".join(str(v + 1) for v in buenos[:12]) + (" …" if len(buenos) > 12 else "")
                    avisos.append(f"Sin trozos desde los vértices {lista}")
                elif buenos == []:
                    avisos.append("Desde ningún vértice sale sin trozos con estos valores: pruebe con linderos "
                                  "paralelos o perpendiculares, o con otro sentido")
        if len(piezas) > MAX_PARCELAS:  #Lo que diría Validar después: mejor saberlo antes de dividir
            avisos.append(f"Más de {MAX_PARCELAS} parcelas resultantes: la Sede no tramita la operación de forma "
                          "automática. ¿Quería «Porcentajes» o «Superficies» en lugar de «Partes iguales»?"
                          if self.modo.currentData() == dv.PARTES else
                          f"Más de {MAX_PARCELAS} parcelas resultantes: la Sede no tramita la operación de forma automática")
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
            #Con pivote, el vértice con sus dos lados (el que llega y el que sale)
            puntos = [todos[i - 1][0], a, b] if self.es_pivote() else [a, b]
            linea = QgsGeometry.fromPolylineXY(puntos)
            destino = lienzo.mapSettings().destinationCrs()
            if destino.isValid() and destino != capa.crs():
                linea.transform(QgsCoordinateTransform(capa.crs(), destino, QgsProject.instance()))
            self.banda.setToGeometry(linea, None)

    def lienzo(self):
        iface = getattr(self.pestana.dock, 'iface', None)
        return iface.mapCanvas() if iface is not None and hasattr(iface, 'mapCanvas') else None

    def plegado(self, *args):
        self.updateGeometry()
        if not self.isCollapsed():
            self.pestana.activar_capa()  #La selección del mapa y Ctrl+Z van a la capa activa
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
        if self.operacion.currentData() == alt.SEGREGACION:
            #La parcela original (con su referencia catastral) se queda con la pieza mayor: es la que la conserva
            mayor = max(range(len(piezas)), key=lambda i: piezas[i].area())
            piezas = [piezas[mayor]] + piezas[:mayor] + piezas[mayor + 1:]
        antes = self.pestana.estado_antes_de_editar()
        self.pestana.editando = True
        try:
            fids = cp.dividir_en_capa(capa, entidad.id(), piezas, self.pestana.campoId.currentField())
        finally:
            self.pestana.editando = False
        if not fids:
            self.pestana.dock.warn("La capa no permite editar sus parcelas")
            return None
        antes['ausentes'] = fids[1:]
        self.pestana.antes_union = antes  #Con Ctrl+Z la tabla y la alteración vuelven a como estaban
        capa.selectByIds(fids)
        vista = ''
        if capa.featureCount() > len(fids) and not self.pestana.soloSeleccion.isChecked():
            #Como al unir (U-02): el GML lleva solo las parcelas de la operación, no el resto de la capa
            self.pestana.soloSeleccion.blockSignals(True)
            self.pestana.soloSeleccion.setChecked(True)
            self.pestana.soloSeleccion.blockSignals(False)
            vista = ". La tabla muestra solo las parcelas resultantes"
        self.pestana.recargar()
        self.pestana.poner_alteracion(self.operacion.currentData(), False)
        self.pestana.dock.success(f"Parcela dividida en {len(fids)}: {superficies} m² · propuesta: "
                                  f"{alt.NOMBRES[self.operacion.currentData()]}{vista}. Ctrl+Z lo deshace")
        self.valores.clear()
        return fids
