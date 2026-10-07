"""
Pestaña «Descargar»: descarga una parcela concreta por su referencia catastral (o eligiéndola en el mapa), con sus
colindantes y sus construcciones, de los servicios públicos de la Dirección General del Catastro (core/servicios.py).
Las capas se añaden en un grupo «Catastro <RC>» con la fuente y la fecha en sus metadatos.

No es una herramienta de descarga masiva: una parcela cada vez.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    QgsTask,
)
from qgis.gui import QgsMapToolEmitPoint
from qgis.PyQt import sip
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core import gml_lector as gl
from ..core import refcat, servicios
from ..core.incidencias import AVISO, ERROR, INFO
from ..core.info import FUENTE_DGC, FUENTE_NAVARRA, provincia
from . import estilos, fondo

PROPIEDAD_FUENTE = 'catastral_gml_tools/fuente'  #Cita de la fuente guardada en cada capa descargada
PROPIEDAD_TERRITORIO = 'catastral_gml_tools/territorio'  #'Navarra' en las capas de Navarra (el GML de la DGC no sirve)
COLORES_NIVEL = {refcat.CORRECTA: '#2b8a3e', refcat.AVISO: '#e67700', refcat.ERROR: '#c92a2a'}


class PestanaDescargar(QWidget):
    def __init__(self, dock, parent=None):
        super().__init__(parent)
        self.dock = dock
        self.tarea = None          #Tarea en curso (referencia guardada para que Python no la borre)
        self.herramienta = None    #Herramienta de mapa para elegir la parcela con un clic
        self.anterior = None       #Herramienta de mapa que había antes, para devolverla
        self.capas = {}            #Capas de la última descarga
        self.descarga = None
        self.construir()
        self.rc.textChanged.connect(self.rc_cambiada)
        self.rc.returnPressed.connect(self.descargar)
        self.descargarBoton.clicked.connect(self.descargar)
        self.mapaBoton.toggled.connect(self.elegir_en_mapa)
        self.rc_cambiada(self.rc.text())

    def construir(self):
        principal = QVBoxLayout(self)
        principal.setContentsMargins(0, 0, 0, 0)
        ayuda = QLabel("Escriba la referencia catastral (en Navarra: municipio-polígono-parcela) y pulse <b>Descargar</b>. "
                       "Si no la conoce, pulse <b>Elegir en el mapa</b> y haga clic sobre la parcela.", self)
        ayuda.setWordWrap(True)
        principal.addWidget(ayuda)

        fila = QHBoxLayout()
        self.rc = QLineEdit(self)
        self.rc.setPlaceholderText("p. ej. 9872023VH5797S o, en Navarra, 201-7-184")
        self.rc.setClearButtonEnabled(True)
        self.rc.setToolTip("Referencia de la parcela (14 caracteres), urbana o rústica, o de un inmueble (18 o 20: se\n"
                           "descarga su parcela). En Navarra: municipio, polígono y parcela (201-7-184) o sus 9 dígitos")
        fila.addWidget(self.rc, 1)
        self.descargarBoton = QPushButton(QgsApplication.getThemeIcon('/mActionAddWfsLayer.svg'), "Descargar", self)
        self.descargarBoton.setDefault(True)
        fila.addWidget(self.descargarBoton)
        principal.addLayout(fila)

        self.comprobacion = QLabel(self)
        self.comprobacion.setWordWrap(True)
        principal.addWidget(self.comprobacion)

        opciones = QHBoxLayout()
        self.colindantes = QCheckBox("Colindantes", self)
        self.colindantes.setChecked(True)
        self.colindantes.setToolTip("Descargar también las parcelas colindantes")
        self.construcciones = QCheckBox("Construcciones", self)
        self.construcciones.setChecked(True)
        self.construcciones.setToolTip("Edificios y otras construcciones (piscinas, etc.) de la parcela")
        self.fondo = QCheckBox("Mapa de fondo", self)
        self.fondo.setChecked(True)
        self.fondo.setToolTip("Si aún no está, añade al final de la lista de capas la cartografía del Catastro y la "
                              "ortofoto PNOA (servicios WMS públicos de la DGC y del IGN)")
        for casilla in (self.colindantes, self.construcciones, self.fondo):
            opciones.addWidget(casilla)
        opciones.addStretch(1)
        principal.addLayout(opciones)

        fila_mapa = QHBoxLayout()
        self.mapaBoton = QToolButton(self)
        self.mapaBoton.setIcon(QgsApplication.getThemeIcon('/mActionIdentify.svg'))
        self.mapaBoton.setText("Elegir en el mapa")
        self.mapaBoton.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.mapaBoton.setCheckable(True)
        self.mapaBoton.setToolTip("Haga clic en el mapa sobre una parcela: se busca su referencia y se descarga.\n"
                                  "Si el proyecto está vacío, se añade el mapa de fondo y se muestra España")
        fila_mapa.addWidget(self.mapaBoton)
        fila_mapa.addStretch(1)
        principal.addLayout(fila_mapa)

        self.resumen = QLabel(self)
        self.resumen.setWordWrap(True)
        principal.addWidget(self.resumen)
        nota = QLabel(f"<small>Datos públicos de la {FUENTE_DGC} (servicios INSPIRE), sin titulares ni valores; en Navarra, "
                      f"del {FUENTE_NAVARRA.replace('Gobierno de Navarra – ', '')}. Se descarga una parcela cada vez, en el "
                      "huso UTM que le corresponde. El País Vasco (Álava/Araba, Gipuzkoa y Bizkaia) tiene catastros propios "
                      "que no están en estos servicios.</small>", self)
        nota.setWordWrap(True)
        principal.addWidget(nota)
        principal.addStretch(1)

    # ------------------------------------------------------------------ Referencia

    @staticmethod
    def explicar(r):
        """Texto para el usuario sobre una referencia comprobada (refcat.ResultadoRC): qué es y qué se va a descargar."""
        if not r.valida or r.foral or not r.tipo:
            return r.mensaje
        if r.tipo == 'rústica':
            p = r.parcela
            nombre = provincia(r.provincia)
            texto = (f"Parcela rústica de {nombre or 'provincia ' + r.provincia} · municipio {p[2:5]}, polígono "
                     f"{int(p[6:9])}, parcela {int(p[9:14])}")
        else:
            texto = "Parcela urbana"
        if len(r.rc) > 14:
            texto += f" · inmueble {r.rc[14:18]}: se descarga su parcela {r.parcela}"
            if len(r.rc) == 18:
                texto += f" (caracteres de control: {refcat.caracteres_control(r.rc)})"
        return texto + ". Pulse Descargar."

    def rc_cambiada(self, texto):
        """Comprueba la referencia mientras se escribe y solo deja descargar si es válida y no foral."""
        if not texto.strip():
            self.comprobacion.setText("<small><i>Referencia de 14 caracteres (urbana o rústica), o de 18 o 20 de un "
                                      "inmueble.</i></small>")
            self.descargarBoton.setEnabled(False)
            return
        r = refcat.comprobar(texto)
        navarra = refcat.navarra(texto) if not r.valida else ''
        if navarra:
            municipio, poligono, numero = refcat.navarra_partes(navarra)
            self.comprobacion.setText(f"<small><span style='color:{COLORES_NIVEL[refcat.CORRECTA]}'>✔ Parcela de Navarra: "
                                      f"municipio {municipio:03d}, polígono {poligono}, parcela {numero}. Se descarga del "
                                      "Registro de la Riqueza Territorial (Gobierno de Navarra). Pulse Descargar.</span></small>")
            self.descargarBoton.setEnabled(self.tarea is None)
            return
        nivel = refcat.ERROR if r.foral else r.nivel
        simbolo = {refcat.CORRECTA: '✔', refcat.AVISO: '⚠', refcat.ERROR: '✖'}[nivel]
        self.comprobacion.setText(f"<small><span style='color:{COLORES_NIVEL[nivel]}'>{simbolo} {self.explicar(r)}"
                                  "</span></small>")
        self.descargarBoton.setEnabled(r.valida and not r.foral and self.tarea is None)

    # ------------------------------------------------------------------ Descarga

    def descargar(self, *args, segundo_plano=True):
        """Descarga la parcela escrita (en segundo plano: QGIS no se queda esperando al servicio)."""
        if self.tarea is not None or not self.descargarBoton.isEnabled():
            return None
        self.dock.messageBar.clearWidgets()
        rc = self.rc.text()
        opciones = {'colindantes': self.colindantes.isChecked(), 'construcciones': self.construcciones.isChecked()}
        self.resumen.setText(f"<i>Descargando {refcat.comprobar(rc).parcela or refcat.navarra(rc)}…</i>")
        if not segundo_plano:
            return self.descargada(servicios.descargar(rc, **opciones))
        self.descargarBoton.setEnabled(False)
        self.tarea = TareaCatastro("Catastral GML Tools: descargando la parcela", servicios.descargar, (rc,), opciones,
                                   self, 'descargada')
        QgsApplication.taskManager().addTask(self.tarea)
        return None

    def descargada(self, descarga):
        """Llega de la tarea (en el hilo principal): añade las capas o explica por qué no se ha podido."""
        if sip.isdeleted(self):
            return None
        self.tarea = None
        self.rc_cambiada(self.rc.text())
        self.descarga = descarga
        if descarga is None or not descarga.correcta:
            errores = [i.mensaje for i in (descarga.incidencias if descarga else []) if i.nivel == ERROR]
            self.resumen.setText("<span style='color:#c92a2a'>✖ No se ha descargado la parcela</span>")
            self.dock.warn("\n".join(errores) or "No se ha podido descargar la parcela")
            return None
        if self.fondo.isChecked():
            fondo.asegurar(self.dock.iface)  #Antes que la parcela: si el proyecto está vacío, fija su SRC
        self.capas = cargar_descarga(descarga, self.dock.iface)
        if self.dock.iface is not None and hasattr(self.dock.iface, 'setActiveLayer'):
            self.dock.iface.setActiveLayer(self.capas['parcela'])
        navarra = descarga.territorio == 'Navarra'
        if not navarra:  #El GML de la Sede de la DGC no sirve en Navarra: no se pasa a la pestaña Parcela
            self.dock.parcela_descargada(self.capas['parcela'])  #La pestaña Parcela pasa a trabajar con ella
        info = [i.mensaje for i in descarga.incidencias if i.codigo == 'DESCARGA']
        avisos = [i.mensaje for i in descarga.incidencias if i.nivel == AVISO]
        notas = [i.mensaje for i in descarga.incidencias if i.nivel == INFO and i.codigo != 'DESCARGA']
        self.resumen.setText(f"<span style='color:#2b8a3e'>✔ {info[0] if info else descarga.rc}</span><br>"
                             + ''.join(f"<small>ℹ {n}</small><br>" for n in notas)
                             + f"<small>{descarga.atribucion()}</small>")
        if navarra:
            self.dock.success(f"Descargada la parcela {descarga.rc} de Navarra", [("Acercar", self.acercar)],
                              detalles=avisos)
        else:
            self.dock.success(f"Descargada la parcela {descarga.rc}: ya está elegida en la pestaña Parcela",
                              [("Acercar", self.acercar), ("Ir a Parcela", self.ir_a_parcela)], detalles=avisos)
        self.acercar()
        return self.capas

    def ir_a_parcela(self, *args):
        self.dock.tabWidget.setCurrentWidget(self.dock.tabParcela)

    def acercar(self, *args):
        capa = self.capas.get('parcela')
        if capa is not None and not sip.isdeleted(capa):
            acercar_a(capa, self.dock.iface)

    # ------------------------------------------------------------------ Elegir en el mapa

    def lienzo(self):
        iface = self.dock.iface
        return iface.mapCanvas() if iface is not None and hasattr(iface, 'mapCanvas') else None

    def elegir_en_mapa(self, activar):
        """Activa una herramienta de mapa: al hacer clic se consulta qué parcela hay ahí y se descarga."""
        lienzo = self.lienzo()
        if lienzo is None:
            return
        if activar:
            if self.herramienta is None:
                self.herramienta = QgsMapToolEmitPoint(lienzo)
                self.herramienta.canvasClicked.connect(self.punto_elegido)
                self.herramienta.deactivated.connect(self.herramienta_desactivada)
            if lienzo.mapTool() is not self.herramienta:
                self.anterior = lienzo.mapTool()
            nuevo_fondo = fondo.asegurar(self.dock.iface) if self.fondo.isChecked() else []
            lienzo.setMapTool(self.herramienta)
            self.dock.notify("Acérquese a la zona (rueda del ratón) y haga clic sobre la parcela que quiere descargar"
                             if nuevo_fondo else "Haga clic en el mapa sobre la parcela que quiere descargar",
                             Qgis.MessageLevel.Info, 10)
        else:
            self.soltar_herramienta()

    def soltar_herramienta(self):
        """Devuelve al mapa la herramienta que había antes."""
        lienzo = self.lienzo()
        if lienzo is None or self.herramienta is None or sip.isdeleted(self.herramienta):
            return
        if lienzo.mapTool() is self.herramienta:
            if self.anterior is not None and not sip.isdeleted(self.anterior):
                lienzo.setMapTool(self.anterior)
            else:
                lienzo.unsetMapTool(self.herramienta)
        self.anterior = None

    def herramienta_desactivada(self):
        """Otra herramienta ha sustituido a la nuestra: se desmarca el botón sin volver a tocar el mapa."""
        if sip.isdeleted(self):
            return
        self.mapaBoton.blockSignals(True)
        self.mapaBoton.setChecked(False)
        self.mapaBoton.blockSignals(False)

    def punto_elegido(self, punto, boton=None, segundo_plano=True):
        """Clic en el mapa: se pasa el punto a ETRS89 y se pregunta al Catastro qué parcela hay."""
        lienzo = self.lienzo()
        origen = lienzo.mapSettings().destinationCrs() if lienzo is not None else QgsCoordinateReferenceSystem('EPSG:4326')
        destino = QgsCoordinateReferenceSystem(f'EPSG:{servicios.EPSG_PUNTO}')
        if origen != destino:
            punto = QgsCoordinateTransform(origen, destino, QgsProject.instance()).transform(punto)
        self.soltar_herramienta()
        self.herramienta_desactivada()
        if self.tarea is not None:
            return None
        self.resumen.setText("<i>Consultando la parcela del punto…</i>")
        if not segundo_plano:
            return self.rc_encontrada(servicios.rc_en_punto(punto.x(), punto.y()), segundo_plano=False)
        self.tarea = TareaCatastro("Catastral GML Tools: consultando la parcela del punto", servicios.rc_en_punto,
                                   (punto.x(), punto.y()), {}, self, 'rc_encontrada')
        QgsApplication.taskManager().addTask(self.tarea)
        return None

    def rc_encontrada(self, resultado, segundo_plano=True):
        """Llega la referencia del punto: se escribe en la casilla y se descarga la parcela."""
        if sip.isdeleted(self):
            return None
        self.tarea = None
        if resultado is None or not resultado.rc or any(i.nivel == ERROR for i in resultado.incidencias):
            self.resumen.clear()
            self.dock.warn("\n".join(i.mensaje for i in (resultado.incidencias if resultado else []))
                           or "No se ha encontrado ninguna parcela en ese punto")
            self.rc_cambiada(self.rc.text())
            return None
        self.rc.setText(resultado.rc)
        self.rc_cambiada(resultado.rc)  #Por si ya estaba escrita la misma (entonces no hay señal textChanged)
        if resultado.direccion:
            self.rc.setToolTip(resultado.direccion)
        return self.descargar(segundo_plano=segundo_plano)


class TareaCatastro(QgsTask):
    """Consulta a los servicios del Catastro en segundo plano. Al terminar llama al método indicado de la pestaña."""

    def __init__(self, descripcion, funcion, argumentos, opciones, pestana, metodo):
        super().__init__(descripcion, QgsTask.Flag.CanCancel)
        self.funcion = funcion
        self.argumentos = argumentos
        self.opciones = opciones
        self.pestana = pestana
        self.metodo = metodo
        self.resultado = None

    def run(self):
        try:
            self.resultado = self.funcion(*self.argumentos, **self.opciones)
        except Exception:  #Nunca debe cerrar QGIS: el resultado vacío se explica en el panel
            self.resultado = None
        return True

    def finished(self, correcto):
        if self.pestana is not None and not sip.isdeleted(self.pestana):
            getattr(self.pestana, self.metodo)(self.resultado)


# ------------------------------------------------------------------ Capas

def _con_fuente(capa, descarga, que):
    """Cita de la fuente y fecha en los metadatos de la capa (se ven en Propiedades > Metadatos)."""
    origen = (f"del servicio INSPIRE del {FUENTE_NAVARRA}" if descarga.territorio == 'Navarra'
              else f"de los servicios INSPIRE de la {FUENTE_DGC}")
    metadatos = capa.metadata()
    metadatos.setTitle(capa.name())
    metadatos.setAbstract(f"{que.capitalize()} de la parcela {descarga.rc} descargada {origen}. Copia para trabajo: no es "
                          "cartografía oficial. Descargada con Catastral GML Tools (herramienta no oficial)."
                          + (" Servicio proporcionado por el Gobierno de Navarra." if descarga.territorio == 'Navarra' else ''))
    metadatos.setRights([descarga.atribucion()])
    capa.setMetadata(metadatos)
    capa.setCustomProperty(PROPIEDAD_FUENTE, descarga.atribucion())
    if descarga.territorio:
        capa.setCustomProperty(PROPIEDAD_TERRITORIO, descarga.territorio)
    return capa


def cargar_descarga(descarga, iface=None):
    """
    Añade la descarga al proyecto en un grupo «Catastro <RC>» (si ya existía, lo sustituye): construcciones, parcela
    y colindantes, con estilo y la fuente en los metadatos. Devuelve {'parcela': capa, 'colindantes': …, …}.
    """
    proyecto = QgsProject.instance()
    raiz = proyecto.layerTreeRoot()
    nombre = f"Catastro {descarga.rc}"
    viejo = raiz.findGroup(nombre)
    if viejo is not None:
        proyecto.removeMapLayers(viejo.findLayerIds())
        raiz.removeChildNode(viejo)
    grupo = raiz.insertGroup(0, nombre)
    capas = {}
    if descarga.construcciones is not None and descarga.construcciones.elementos:
        #Sin etiquetas: llevan la misma referencia que la parcela y tapaban su etiqueta
        capas['construcciones'] = estilos.aplicar(gl.capa(descarga.construcciones, "Construcciones"), campo_etiqueta=None)
        _con_fuente(capas['construcciones'], descarga, "construcciones")
    capas['parcela'] = _con_fuente(estilos.aplicar(gl.capa(descarga.parcela, f"Parcela {descarga.rc}")), descarga, "parcela")
    if descarga.colindantes is not None and descarga.colindantes.elementos:
        capas['colindantes'] = estilos.aplicar(gl.capa(descarga.colindantes, "Colindantes"),
                                               {gl.PARCELA: estilos.COLOR_COLINDANTES}, campo_etiqueta='label')
        _con_fuente(capas['colindantes'], descarga, "parcelas colindantes")
    if descarga.entorno is not None and descarga.entorno.elementos:
        capas['entorno'] = estilos.aplicar(gl.capa(descarga.entorno, "Entorno"), {gl.PARCELA: estilos.COLOR_ENTORNO},
                                           campo_etiqueta='label')
        _con_fuente(capas['entorno'], descarga, f"parcelas a menos de {servicios.MARGEN_ENTORNO:.0f} m (no colindantes)")
    for capa in capas.values():  #En este orden: construcciones encima y entorno debajo
        proyecto.addMapLayer(capa, False)
        grupo.addLayer(capa)
    return capas


def acercar_a(capa, iface=None):
    if iface is None or not hasattr(iface, 'mapCanvas'):
        return
    try:
        lienzo = iface.mapCanvas()
        extension = lienzo.mapSettings().layerExtentToOutputExtent(capa, capa.extent())
        extension.scale(1.6)
        lienzo.setExtent(extension)
        lienzo.refresh()
    except (AttributeError, TypeError):
        pass
