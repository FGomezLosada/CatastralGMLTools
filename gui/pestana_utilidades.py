"""
Pestaña «Utilidades»: «Unir GML» (multiparcela, core/unir.py): varios GML de parcela en uno solo; «Convertir a 4.0 o
reparar» (core/conversor.py): un GML de parcela del esquema 3.0 al 4.0, o un 4.0 con fallos que se arreglan al
reescribirlo; «Informe de superficies y coordenadas» (core/superficies.py): superficies, linderos y coordenadas de cada
parcela de un GML, en HTML; «Ajustar a la cartografía catastral» (core/ajuste.py, gui/bloque_ajuste.py); y «Comparar
dos GML» (core/comparar_gml.py, gui/bloque_comparar.py); «Parcela desde coordenadas» (core/coordenadas.py,
gui/bloque_coordenadas.py); e «Identidad gráfica con el Catastro» (core/identidad.py, gui/bloque_identidad.py).

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import contextlib
import datetime
import os

from qgis.core import Qgis, QgsApplication, QgsFeedback, QgsSettings, QgsTask
from qgis.gui import QgsFileWidget
from qgis.PyQt import sip
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QToolBox,
    QVBoxLayout,
    QWidget,
)

from ..core import comparacion as cmp
from ..core import conversor as cv
from ..core import geometria as geo
from ..core import gml_lector as gl
from ..core import servicios
from ..core import superficies as su
from ..core import unir as un
from ..core.incidencias import AVISO, ERROR, Incidencia
from . import desplazable
from .bloque_ajuste import BloqueAjuste
from .bloque_comparar import ICONO as ICONO_COMPARAR
from .bloque_comparar import BloqueComparar
from .bloque_coordenadas import EXTENSIONES as EXTENSIONES_COORDENADAS
from .bloque_coordenadas import ICONO as ICONO_COORDENADAS
from .bloque_coordenadas import BloqueCoordenadas
from .bloque_identidad import ICONO as ICONO_IDENTIDAD
from .bloque_identidad import BloqueIdentidad
from .pestana_validar import PestanaValidar


class PestanaUtilidades(QWidget):
    def __init__(self, dock, parent=None):
        super().__init__(parent)
        self.dock = dock
        self.ultimo = ''
        self.construir()
        self.anadirBoton.clicked.connect(self.elegir)
        self.quitarBoton.clicked.connect(self.quitar)
        self.unirBoton.clicked.connect(self.unir)
        self.origenConv.fileChanged.connect(self.origen_cambiado)
        self.convertirBoton.clicked.connect(self.convertir)
        self.origenSup.fileChanged.connect(self.origen_sup_cambiado)
        self.informeBoton.clicked.connect(self.crear_informe)
        self.lista.model().rowsInserted.connect(self.actualizar)
        self.lista.model().rowsRemoved.connect(self.actualizar)
        self.actualizar()

    def construir(self):
        """
        Cada utilidad es un apartado numerado de una lista desplegable (QToolBox): se ve la lista entera y solo se abre
        la que se usa (prueba a mano del 15/10: con todo a la vista y sus textos, la pestaña parecía una página web).
        Lo que explica cada utilidad está en su descripción emergente y en la ayuda.
        """
        principal = QVBoxLayout(self)
        principal.setContentsMargins(0, 0, 0, 0)
        self.utilidades = QToolBox(self)
        for numero, (widget, titulo, icono, ayuda) in enumerate((
                (self.pagina_unir(), "Unir GML (multiparcela)", '/mActionMergeFeatures.svg',
                 "Junta varios GML de parcela en uno solo para presentarlos a la vez en la Sede. Las parcelas repetidas "
                 "se incluyen una vez; si vienen en husos distintos, se pasan al del primer fichero."),
                (self.pagina_convertir(), "Convertir a 4.0 o reparar", '/mActionFileSaveAs.svg',
                 "La Sede solo admite el esquema 4.0. Crea una copia en 4.0 (o reparada, si ya lo era) con la estructura, "
                 "los anillos, los decimales y las superficies como los pide la Sede; el original no se toca. Dice qué ha "
                 "cambiado y qué queda por revisar."),
                (self.pagina_superficies(), "Informe de superficies y coordenadas", '/mActionNewReport.svg',
                 "Superficie (UTM y sobre el elipsoide), perímetro, linderos (con qué parcela linda cada lado y hacia "
                 "dónde) y coordenadas de cada parcela de un GML, en un informe HTML que se puede imprimir. Si se indica "
                 "la cabida inscrita, la compara con la del GML."),
                (self.pagina_ajuste(), "Ajustar a la cartografía catastral (desplazada o girada)",
                 '/mActionMoveFeature.svg',
                 "Si la cartografía catastral está desplazada o girada, calcula los parámetros de transformación con pares "
                 "de puntos (el mismo punto en el levantamiento y en el Catastro) y crea el GML ajustado a la cartografía "
                 "catastral y un fichero con los parámetros: la Sede pide los dos GML y los parámetros (Resolución de "
                 "29/03/2021); para el ICUC, los parámetros y el GML ajustado."),
                (self.pagina_comparar(), "Comparar dos GML", ICONO_COMPARAR,
                 "Dos GML de la misma finca o construcción, vengan de donde vengan (el presentado y el que devuelve otro "
                 "organismo, dos versiones, dos programas): diferencias de fichero, identificadores, superficies, "
                 "desplazamiento de cada vértice, vértices añadidos o quitados y si son iguales a efectos de la Sede (±1 cm)."),
                (self.pagina_coordenadas(), "Parcela desde coordenadas (levantamiento)", ICONO_COORDENADAS,
                 "Las parcelas de un fichero de puntos (TXT o CSV del levantamiento: X Y, o nombre X Y), en una capa que se "
                 "abre en la pestaña Parcela para crear el GML. Varias parcelas: separadas por una línea en blanco o un "
                 "título, o con una columna con el identificador de cada una."),
                (self.pagina_identidad(), "Identidad gráfica con el Catastro (simulación)", ICONO_IDENTIDAD,
                 "¿El GML del levantamiento y la parcela catastral cumplen el criterio de identidad gráfica (contorno dentro "
                 "de ±0,50 m en cartografía urbana o ±2,00 m en rústica, y no más del 5 % de diferencia de superficie)? "
                 "Simulación no oficial, como ayuda antes de ir al notario o al registro: el certificado válido es el de "
                 "la Sede."),
        ), start=1):
            indice = self.utilidades.addItem(widget, QgsApplication.getThemeIcon(icono), f"{numero}. {titulo}")
            self.utilidades.setItemToolTip(indice, ayuda)
        principal.addWidget(self.utilidades, 1)
        self.utilidades.currentChanged.connect(self.ajuste.mostrar_en_mapa)
        desplazable.soltar_en(self)  #Un GML soltado en cualquier punto (también sobre una casilla) va a la utilidad abierta

    def pagina_coordenadas(self):
        self.coordenadas = BloqueCoordenadas(self, self)
        return self.coordenadas

    def pagina_identidad(self):
        self.identidad = BloqueIdentidad(self, self)
        return self.identidad

    def pagina_comparar(self):
        self.comparador = BloqueComparar(self, self)
        return self.comparador

    def pagina_ajuste(self):
        self.ajuste = BloqueAjuste(self, self)
        return self.ajuste

    def pagina_unir(self):
        pagina = QWidget(self)
        caja = QVBoxLayout(pagina)
        self.lista = QListWidget(pagina)
        self.lista.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.lista.setToolTip("Ficheros GML que se van a unir (puede arrastrarlos aquí desde el Explorador o el panel de Capas)")
        self.lista.setAcceptDrops(False)
        caja.addWidget(self.lista, 1)
        fila = QHBoxLayout()
        self.anadirBoton = QPushButton(QgsApplication.getThemeIcon('/symbologyAdd.svg'), "Añadir…", pagina)
        self.quitarBoton = QPushButton(QgsApplication.getThemeIcon('/symbologyRemove.svg'), "Quitar", pagina)
        fila.addWidget(self.anadirBoton)
        fila.addWidget(self.quitarBoton)
        fila.addStretch(1)
        caja.addLayout(fila)
        formulario = QFormLayout()
        self.destino = QgsFileWidget(pagina)
        self.destino.setStorageMode(QgsFileWidget.StorageMode.SaveFile)
        self.destino.setFilter("GML (*.gml)")
        self.destino.setDialogTitle("Guardar el GML unido")
        formulario.addRow("Salida", self.destino)
        caja.addLayout(formulario)
        botones = QHBoxLayout()
        botones.addStretch(1)
        self.unirBoton = QPushButton(QgsApplication.getThemeIcon('/mActionMergeFeatures.svg'), "Unir GML", pagina)
        botones.addWidget(self.unirBoton)
        caja.addLayout(botones)
        return pagina

    def pagina_convertir(self):
        pagina = QWidget(self)
        caja = QVBoxLayout(pagina)
        formulario = QFormLayout()
        self.origenConv = QgsFileWidget(pagina)
        self.origenConv.setStorageMode(QgsFileWidget.StorageMode.GetFile)
        self.origenConv.setFilter("GML (*.gml *.xml)")
        self.origenConv.setDialogTitle("Elegir el GML de parcela que se va a convertir")
        formulario.addRow("GML", self.origenConv)
        self.destinoConv = QgsFileWidget(pagina)
        self.destinoConv.setStorageMode(QgsFileWidget.StorageMode.SaveFile)
        self.destinoConv.setFilter("GML (*.gml)")
        self.destinoConv.setDialogTitle("Guardar el GML convertido")
        formulario.addRow("Salida", self.destinoConv)
        caja.addLayout(formulario)
        self.estadoConv = QLabel(pagina)
        self.estadoConv.setWordWrap(True)
        caja.addWidget(self.estadoConv)
        botones = QHBoxLayout()
        botones.addStretch(1)
        self.convertirBoton = QPushButton(QgsApplication.getThemeIcon('/mActionFileSaveAs.svg'), "Convertir", pagina)
        self.convertirBoton.setEnabled(False)
        botones.addWidget(self.convertirBoton)
        caja.addLayout(botones)
        caja.addStretch(1)
        self.destino_conv_auto = ''
        return pagina

    def pagina_superficies(self):
        pagina = QWidget(self)
        caja = QVBoxLayout(pagina)
        formulario = QFormLayout()
        self.origenSup = QgsFileWidget(pagina)
        self.origenSup.setStorageMode(QgsFileWidget.StorageMode.GetFile)
        self.origenSup.setFilter("GML (*.gml)")
        self.origenSup.setDialogTitle("Elegir el GML de parcela")
        formulario.addRow("GML", self.origenSup)
        self.cabida = QLineEdit(pagina)
        self.cabida.setPlaceholderText("opcional, en m²")
        self.cabida.setToolTip("Cabida inscrita en el Registro (o la del título): se compara con la superficie total del GML")
        formulario.addRow("Cabida inscrita", self.cabida)
        self.autor = QLineEdit(QgsSettings().value(CLAVE_AUTOR, '', type=str), pagina)
        self.autor.setPlaceholderText("opcional: nombre, titulación, nº de colegiado")
        self.autor.setToolTip("Se escribe en la cabecera del informe y se recuerda para la próxima vez")
        formulario.addRow("Autor", self.autor)
        caja.addLayout(formulario)
        self.colindantes = QCheckBox("Linderos con el Catastro", pagina)
        self.colindantes.setToolTip("Consulta las parcelas catastrales de alrededor para decir con quién linda cada lado "
                                    "(datos públicos de la Dirección General del Catastro); sin internet, el informe sale "
                                    "con los linderos entre las parcelas del GML. Necesita internet")
        self.colindantes.setChecked(True)
        caja.addWidget(self.colindantes)
        self.ortofoto = QCheckBox("Ortofoto PNOA de fondo", pagina)
        self.ortofoto.setToolTip("El croquis general va sobre la ortofoto del Instituto Geográfico Nacional; los croquis de "
                                 "cada parcela, con los vértices numerados, van sin ella para que se lean bien impresos. "
                                 "Necesita internet")
        self.ortofoto.setChecked(True)
        caja.addWidget(self.ortofoto)
        self.estadoSup = QLabel(pagina)
        self.estadoSup.setWordWrap(True)
        caja.addWidget(self.estadoSup)
        botones = QHBoxLayout()
        botones.addStretch(1)
        self.informeBoton = QPushButton(QgsApplication.getThemeIcon('/mActionNewReport.svg'), "Crear informe", pagina)
        self.informeBoton.setEnabled(False)
        botones.addWidget(self.informeBoton)
        caja.addLayout(botones)
        caja.addStretch(1)
        self.tarea_sup = None
        self.ultimo_informe = ''
        return pagina

    # ------------------------------------------------------------------ Lista de ficheros

    def rutas(self):
        return [self.lista.item(i).text() for i in range(self.lista.count())]

    def agregar(self, rutas):
        """Añade ficheros GML a la lista (sin repetir). Propone el fichero de salida junto al primero."""
        actuales = self.rutas()
        for ruta in rutas:
            ruta = os.path.normpath(ruta) if ruta else ruta
            if ruta and ruta.lower().endswith('.gml') and os.path.isfile(ruta) and ruta not in actuales:
                self.lista.addItem(ruta)
                actuales.append(ruta)
        if actuales and not self.destino.filePath().strip():
            self.destino.setFilePath(os.path.join(os.path.dirname(actuales[0]), 'multiparcela.gml'))

    def elegir(self, *args):
        rutas, _ = QFileDialog.getOpenFileNames(self, "Elegir los GML que se van a unir", '', "GML (*.gml)")
        self.agregar(rutas)

    def quitar(self, *args):
        for item in self.lista.selectedItems():
            self.lista.takeItem(self.lista.row(item))

    def actualizar(self, *args):
        self.unirBoton.setEnabled(self.lista.count() >= 2)
        self.quitarBoton.setEnabled(self.lista.count() > 0)

    def dragEnterEvent(self, event):  # noqa: N802 (nombre impuesto por Qt)
        #Del Explorador de Windows (ficheros) o del panel de Capas y el Navegador de QGIS (capas: su GML de origen)
        if PestanaValidar.rutas_gml(event.mimeData(), self.extensiones()):
            event.setDropAction(Qt.DropAction.CopyAction)  #Nunca «mover» (quitaría la capa o el fichero de su origen)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):  # noqa: N802 (nombre impuesto por Qt)
        self.dragEnterEvent(event)

    def dropEvent(self, event):  # noqa: N802 (nombre impuesto por Qt)
        rutas = PestanaValidar.rutas_gml(event.mimeData(), self.extensiones())
        if not rutas:
            event.ignore()
            return
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self.soltar(rutas)

    def extensiones(self):
        """Lo que se puede soltar en la utilidad abierta: GML, o ficheros de puntos en «Parcela desde coordenadas»."""
        return EXTENSIONES_COORDENADAS if self.utilidades.currentIndex() == 5 else ('.gml', '.xml')

    def soltar(self, rutas):
        """El GML soltado va a la utilidad abierta: a la lista de «Unir», o como fichero de «Convertir» o del informe."""
        if self.utilidades.currentIndex() == 4:
            self.comparador.soltar(rutas)
            return
        if self.utilidades.currentIndex() == 5:
            self.coordenadas.soltar(rutas)
            return
        if self.utilidades.currentIndex() == 6:
            self.identidad.soltar(rutas)
            return
        casilla = {1: self.origenConv, 2: self.origenSup, 3: self.ajuste.origenAj}.get(self.utilidades.currentIndex())
        if casilla is None:
            self.agregar(rutas)
            return
        casilla.setFilePath(rutas[0])
        if len(rutas) > 1:
            self.dock.notify(f"Se ha tomado {os.path.basename(rutas[0])}: esta utilidad trabaja con un GML cada vez",
                             Qgis.MessageLevel.Info)

    # ------------------------------------------------------------------ Unir

    def unir(self, *args):
        self.dock.messageBar.clearWidgets()
        destino = self.destino.filePath().strip()
        if not destino:
            self.dock.warn("Indique el fichero de salida")
            return None
        if not destino.lower().endswith('.gml'):
            destino += '.gml'
        ahora = datetime.datetime.now().replace(second=0, microsecond=0)
        ok, n, incidencias = un.unir(self.rutas(), destino, ahora)
        problemas = [str(i) for i in incidencias if i.nivel in (ERROR, AVISO)]
        if not ok:
            self.dock.notify("No se han unido los GML:\n\n" + "\n".join(f"- {p}" for p in problemas if p),
                             Qgis.MessageLevel.Critical, 0)
            return None
        self.ultimo = destino
        self.dock.gml_creado(destino)
        self.dock.success(f"GML unido: {os.path.basename(destino)} · {n} parcelas de {self.lista.count()} ficheros",
                          [("Validar", self.validar), ("Abrir carpeta", self.abrir_carpeta)],
                          detalles=[str(i) for i in incidencias if i.nivel == AVISO])
        return destino

    # ------------------------------------------------------------------ Convertir a 4.0 o reparar

    def origen_cambiado(self, *args):
        """Dice qué se hará con el fichero elegido y propone la salida junto a él (sin pisar nada)."""
        ruta = self.origenConv.filePath().strip()
        version = gl.leer(ruta).version if ruta and os.path.isfile(ruta) else ''
        if ruta and not version.startswith(('CP', 'BU')) and os.path.isfile(ruta) and cv.generico(ruta):
            version = cv.GENERICO
        if version == cv.GENERICO:
            texto, boton = ("GML genérico, no INSPIRE (p. ej. «Guardar como» de QGIS): se convertirá al 4.0 con su "
                            "geometría y sus campos."), "Convertir a 4.0"
        elif version.startswith('BU'):
            texto, boton = (f"<span style='color:#c92a2a'>Es un GML de edificios ({version}): esta utilidad es para GML "
                            "de parcela.</span>"), "Convertir"
        elif version == 'CP 3.0':
            texto, boton = "Esquema 3.0 (obsoleto): se convertirá al 4.0.", "Convertir a 4.0"
        elif version == 'CP 4.0':
            texto, boton = "Ya es 4.0: se reescribirá corrigiendo lo que se pueda (estructura, anillos, superficies…).", "Reparar"
        elif ruta:
            texto, boton = ("<span style='color:#c92a2a'>No es un GML de parcela catastral que se pueda leer"
                            + (f" ({version})" if version else '') + ".</span>"), "Convertir"
        else:
            texto, boton = '', "Convertir"
        self.estadoConv.setText(f"<small>{texto}</small>" if texto else '')
        self.convertirBoton.setText(boton)
        self.convertirBoton.setEnabled(version in ('CP 3.0', 'CP 4.0', cv.GENERICO))
        actual = self.destinoConv.filePath().strip()
        if version in ('CP 3.0', 'CP 4.0', cv.GENERICO) and (not actual or actual == self.destino_conv_auto):
            self.destino_conv_auto = cv.destino_propuesto(ruta, version)
            self.destinoConv.setFilePath(self.destino_conv_auto)

    def convertir(self, *args):
        self.dock.messageBar.clearWidgets()
        ruta = self.origenConv.filePath().strip()
        destino = self.destinoConv.filePath().strip()
        if not destino:
            self.dock.warn("Indique el fichero de salida")
            return None
        if not destino.lower().endswith('.gml'):
            destino += '.gml'
        ok, version, cambios, incidencias = cv.convertir(ruta, destino)
        if not ok:
            self.dock.notify("No se ha podido convertir:\n\n" + "\n".join(f"- {i}" for i in incidencias),
                             Qgis.MessageLevel.Critical, 0)
            return None
        self.ultimo = destino
        self.dock.gml_creado(destino)
        accion = "Reparado" if version == 'CP 4.0' else "Convertido a 4.0"  #Corto: el mensaje no se come el panel
        self.dock.success(f"{accion}: {os.path.basename(destino)}",
                          [("Validar", self.validar), ("Abrir carpeta", self.abrir_carpeta)],
                          detalles=[str(i) for i in incidencias if i.nivel in (ERROR, AVISO)], notas=cambios + ["El original no se ha tocado"])
        self.destino_conv_auto = destino  #Se propone otro nombre libre: un segundo clic no pisa el que se acaba de crear
        self.origen_cambiado()
        return destino

    # ------------------------------------------------------------------ Informe de superficies y coordenadas

    def proponer_gml(self, ruta):
        """Un GML recién creado en el plugin se propone para el informe si aún no hay ninguno elegido."""
        if ruta and not self.origenSup.filePath().strip():
            self.origenSup.setFilePath(ruta)

    def origen_sup_cambiado(self, *args):
        ruta = self.origenSup.filePath().strip()
        lectura = gl.leer(ruta) if ruta and os.path.isfile(ruta) else None
        valido = (lectura is not None and lectura.version.startswith('CP') and bool(lectura.elementos)
                  and lectura.epsg in geo.SRC_ADMITIDOS and all(not e.geometria.isEmpty() for e in lectura.elementos))
        if not ruta:
            texto = ''
        elif valido:
            n = len(lectura.elementos)
            texto = f"{lectura.version} · {n} parcela{'s' if n != 1 else ''} · EPSG:{lectura.epsg}"
        else:
            texto = ("<span style='color:#c92a2a'>Elija un GML de parcela catastral legible y en un SRC de la Sede "
                     "(si es antiguo o de otro programa, conviértalo antes en «2.»).</span>")
        self.estadoSup.setText(f"<small>{texto}</small>" if texto else '')
        self.informeBoton.setEnabled(valido and self.tarea_sup is None)

    def cabida_inscrita(self):
        """La cabida escrita en m² (admite coma decimal y puntos de millar), None si está vacía; ValueError si no vale."""
        return su.leer_cabida(self.cabida.text())

    def crear_informe(self, *args, segundo_plano=True):
        """Lee el GML y, si se piden los linderos con el Catastro, consulta las colindantes en segundo plano."""
        self.dock.messageBar.clearWidgets()
        ruta = self.origenSup.filePath().strip()
        try:
            self.cabida_inscrita()
        except ValueError:
            self.dock.warn("La cabida inscrita debe ser un número de metros cuadrados (p. ej. 1250,5)")
            return None
        QgsSettings().setValue(CLAVE_AUTOR, self.autor.text().strip())
        lectura = gl.leer(ruta)
        errores = [i for i in lectura.incidencias if i.nivel == ERROR]
        if errores or not lectura.elementos:  #Borrado o cambiado después de elegirlo
            self.dock.warn(errores[0].mensaje if errores else "El GML no tiene parcelas")
            self.origen_sup_cambiado()
            return None
        colindantes, ortofoto = self.colindantes.isChecked(), self.ortofoto.isChecked()
        if not (colindantes or ortofoto):
            return self.informe_listo(ruta, lectura, None, [], b'')
        if not segundo_plano:
            return self.informe_listo(ruta, lectura, *consultar_red(lectura, colindantes, ortofoto))
        self.tarea_sup = TareaSuperficies(ruta, lectura, self, colindantes, ortofoto)
        self.informeBoton.setEnabled(False)
        self.informeBoton.setText("Consultando el Catastro…" if colindantes else "Descargando la ortofoto…")
        QgsApplication.taskManager().addTask(self.tarea_sup)
        return None

    def informe_listo(self, ruta, lectura, catastrales, errores, ortofoto=b''):
        """Escribe el informe junto al GML y lo ofrece para abrirlo."""
        self.tarea_sup = None
        self.informeBoton.setText("Crear informe")
        self.origen_sup_cambiado()
        fallo_catastro = [e for e in errores if e.codigo != 'SUP-ORTOFOTO']
        consulta = datetime.datetime.now() if catastrales is not None and not fallo_catastro else None
        vecinas = catastrales if consulta is not None else []
        lista = su.fichas(lectura, None if consulta is None else [(e.local_id, e.geometria) for e in vecinas])
        try:
            destino = su.escribir(lectura, ruta, lista, inscrita=self.cabida_inscrita(), autor=self.autor.text().strip(),
                                  consulta=consulta, vecinas=vecinas, ortofoto=ortofoto)
        except (OSError, ValueError) as e:
            self.dock.warn(f"No se ha podido escribir el informe: {e}")
            return None
        self.ultimo_informe = destino
        avisos = ([f"Sin linderos con el Catastro: {fallo_catastro[0].mensaje}"] if fallo_catastro else []) + [
            f"Sin ortofoto: {e.mensaje}" for e in errores if e.codigo == 'SUP-ORTOFOTO']
        self.dock.success(f"Informe de superficies: {os.path.basename(destino)}",
                          [("Abrir", self.abrir_informe), ("Abrir carpeta", self.abrir_carpeta_informe)], detalles=avisos)
        return destino

    def abrir_informe(self, *args):
        if self.ultimo_informe:
            self.dock.open_path(self.ultimo_informe)

    def abrir_carpeta_informe(self, *args):
        if self.ultimo_informe:
            self.dock.open_path(os.path.dirname(self.ultimo_informe))

    def cancelar_tareas(self):
        """Al cerrar o recargar el plugin: la consulta en curso se corta y el ajuste suelta el mapa."""
        self.ajuste.soltar()
        self.comparador.cancelar_tareas()
        self.identidad.cancelar_tareas()
        if self.tarea_sup is not None and not sip.isdeleted(self.tarea_sup):
            with contextlib.suppress(RuntimeError):
                self.tarea_sup.cancel()
        self.tarea_sup = None

    def validar(self, *args):
        """Abre el GML unido en la pestaña Validar (solapes, huecos y comparación con el Catastro)."""
        if self.ultimo:
            self.dock.abrir_en_validar(self.ultimo)

    def abrir_carpeta(self, *args):
        if self.ultimo:
            self.dock.open_path(os.path.dirname(self.ultimo))


CLAVE_AUTOR = 'catastral_gml_tools/autor_informe'


def consultar_colindantes(lectura):
    """Parcelas catastrales alrededor del GML (2 m de margen): (lista de ElementoGML, errores)."""
    caja = None
    for e in lectura.elementos:
        if caja is None:
            caja = e.geometria.boundingBox()
        else:
            caja.combineExtentWith(e.geometria.boundingBox())
    if caja is None:
        return [], []
    caja.grow(cmp.MARGEN)
    return cmp.parcelas_catastrales([caja], lectura.epsg)


ORTOFOTO_PX = 2  #La ortofoto se pide al doble de resolución que el croquis, para que se vea bien impresa


def consultar_red(lectura, colindantes=True, ortofoto=True):
    """
    Lo que el informe necesita de internet: (catastrales o None, errores, imagen de la ortofoto o b''). Un fallo de un
    servicio no impide lo demás; el de la ortofoto va como incidencia SUP-ORTOFOTO.
    """
    catastrales, errores, imagen = None, [], b''
    if colindantes:
        catastrales, errores = consultar_colindantes(lectura)
    if ortofoto:
        from ..core.informe import vista_croquis
        vista = vista_croquis([e for e in lectura.elementos if not e.geometria.isEmpty()])
        if vista is not None:
            imagen, error = servicios.ortofoto(vista, lectura.epsg, 640 * ORTOFOTO_PX, 420 * ORTOFOTO_PX)
            if error and error != servicios.CANCELADO:
                errores = list(errores) + [Incidencia(AVISO, 'SUP-ORTOFOTO', error)]
    return catastrales, errores, imagen


class TareaSuperficies(QgsTask):
    """Consulta de las parcelas catastrales colindantes y de la ortofoto en segundo plano (para el informe)."""

    def __init__(self, ruta, lectura, pestana, colindantes=True, ortofoto=True):
        super().__init__("Catastral GML Tools: informe de superficies", QgsTask.Flag.CanCancel)
        self.ruta, self.lectura, self.pestana = ruta, lectura, pestana
        self.colindantes, self.pedir_ortofoto = colindantes, ortofoto
        self.catastrales, self.errores, self.imagen = None, [], b''
        self.feedback = QgsFeedback()

    def cancel(self):
        self.feedback.cancel()
        super().cancel()

    def run(self):
        try:
            with servicios.en_tarea(self.feedback):
                self.catastrales, self.errores, self.imagen = consultar_red(self.lectura, self.colindantes,
                                                                           self.pedir_ortofoto)
        except Exception as e:  #Nunca debe cerrar QGIS: el informe se hace igual, sin lo que falte
            self.catastrales, self.errores, self.imagen = None, [Incidencia(AVISO, 'SUP-FALLO', str(e))], b''
        return not self.isCanceled()

    def finished(self, correcto):
        if self.pestana is None or sip.isdeleted(self.pestana):
            return
        if correcto:
            self.pestana.informe_listo(self.ruta, self.lectura, self.catastrales, self.errores, self.imagen)
        else:  #Cancelada: el botón vuelve a estar disponible
            self.pestana.tarea_sup = None
            self.pestana.informeBoton.setText("Crear informe")
            self.pestana.origen_sup_cambiado()
