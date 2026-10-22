"""
Prueba del informe de superficies y coordenadas (fase 11, AU-55): core/superficies.py y el apartado «3.» de Utilidades.
Linderos lado a lado con las parcelas del GML, las catastrales colindantes (simuladas) y el suelo sin parcela, rumbos,
superficies UTM y sobre el elipsoide, comparación con la cabida inscrita (umbrales de la Ley Hipotecaria), HTML y la
interfaz (también sin internet y al cancelar). Sin internet: los servicios del Catastro están simulados.

Uso: tools\\probar.bat (o tools\\run_tests.py superficies_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import datetime
import importlib.util
import os
import tempfile

import qgis.utils
from qgis.core import Qgis, QgsGeometry, QgsSettings
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import gml_lector as gl  # noqa: E402
from catastral_gml_tools.core import gml_parcela as gp  # noqa: E402
from catastral_gml_tools.core import servicios  # noqa: E402
from catastral_gml_tools.core import superficies as su  # noqa: E402
from catastral_gml_tools.core.info import RAIZ  # noqa: E402
from catastral_gml_tools.gui import pestana_utilidades as pu_module  # noqa: E402

spec = importlib.util.spec_from_file_location('simulador_catastro', os.path.join(RAIZ, 'tests', 'simulador_catastro.py'))
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)
original = sim.instalar()

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))

carpeta = tempfile.mkdtemp(prefix='cgt_superficies_')
X0, Y0 = sim.X0, sim.Y0
SIN = su.SIN_PARCELA

#Segregación de la parcela sintética (20 × 30): la matriz al sur (20 × 18) y la nueva al norte (20 × 12). En el Catastro
#simulado, al este linda 1907402 y al sur el camino 29071A00709001; al norte y al oeste no hay parcela
ruta = os.path.join(carpeta, 'segregacion.gml')
gp.escribir(ruta, [gp.ParcelaGML(sim.RC, gp.SDGC, sim.rect(X0, Y0, 20, 18)),
                   gp.ParcelaGML('Seg_1', gp.LOCAL, sim.rect(X0, Y0 + 18, 20, 12))], 25830)
lectura = gl.leer(ruta)
catastrales, errores = pu_module.consultar_colindantes(lectura)
lista = su.fichas(lectura, [(e.local_id, e.geometria) for e in catastrales])


def resumen(ficha):
    return [(li.rumbo, li.con, li.tipo, round(li.longitud, 2)) for li in ficha.linderos]


# 1. Linderos lado a lado: la matriz (origen) no cuenta como colindante; corregir esquinas de unos centímetros
linderos_ok = (not errores and resumen(lista[0]) == [('N', 'Seg_1', 'gml', 20.0), ('E', '1907402VK4810H', 'catastral', 18.0),
                                                       ('S', sim.CAMINO, 'catastral', 20.0), ('O', SIN, 'sin parcela', 18.0)]
               and resumen(lista[1]) == [('N', SIN, 'sin parcela', 20.0), ('E', '1907402VK4810H', 'catastral', 12.0),
                                         ('S', sim.RC, 'gml', 20.0), ('O', SIN, 'sin parcela', 12.0)])
#Sin consultar el Catastro: solo los linderos entre parcelas del GML (el resto no se asigna)
solo_gml = su.fichas(lectura, None)
sin_catastro = (resumen(solo_gml[0]) == [('N', 'Seg_1', 'gml', 20.0)] and resumen(solo_gml[1]) == [('S', sim.RC, 'gml', 20.0)])
#El rumbo no depende del sentido del anillo (horario como el GML, o antihorario)
antihorario = QgsGeometry.fromWkt(f"POLYGON(({X0} {Y0}, {X0 + 20} {Y0}, {X0 + 20} {Y0 + 10}, {X0} {Y0 + 10}, {X0} {Y0}))")
horario = QgsGeometry.fromWkt(f"POLYGON(({X0} {Y0}, {X0} {Y0 + 10}, {X0 + 20} {Y0 + 10}, {X0 + 20} {Y0}, {X0} {Y0}))")
rumbos = ([li.rumbo for li in su.linderos(antihorario, [], [])] == ['N', 'E', 'S', 'O']
          and [li.rumbo for li in su.linderos(horario, [], [])] == ['N', 'E', 'S', 'O']
          and all(li.con == SIN for li in su.linderos(horario, [], [])))

#Un lado corto (8 cm) en la esquina que linda con la catastral del oeste (prueba a mano del 16/10/2026): va con ella y
#los linderos suman el perímetro; sin consultar el Catastro, los centímetros sueltos no se asignan
esquina = QgsGeometry.fromWkt(f"POLYGON(({X0} {Y0 + 0.08}, {X0} {Y0 + 10}, {X0 + 10} {Y0 + 10}, {X0 + 10} {Y0}, "
                              f"{X0 + 0.03} {Y0}, {X0} {Y0 + 0.08}))")
oeste = QgsGeometry.fromWkt(f"POLYGON(({X0 - 5} {Y0}, {X0 - 5} {Y0 + 10}, {X0} {Y0 + 10}, {X0} {Y0}, {X0 - 5} {Y0}))")
_esq = su.linderos(esquina, [], [('OESTE', oeste)])
_esq_gml = su.linderos(esquina, [('OESTE', oeste)], None)
esquinas = (abs(sum(li.longitud for li in _esq) - esquina.constGet().perimeter()) < 1e-6
            and [li.con for li in _esq if li.rumbo == 'O'] == ['OESTE']
            and abs(next(li.longitud for li in _esq if li.con == 'OESTE') - (9.92 + 0.0854)) < 1e-3
            and abs(sum(li.longitud for li in _esq_gml) - (9.92 + 0.0854)) < 1e-3)
#Croquis del informe: vértices numerados, norte y barra de escala
_svg = su.html(lectura, ruta, lista, consulta=datetime.datetime(2026, 10, 16, 12, 0))
croquis = _svg.count('<circle') == 8 and '>N</text>' in _svg and ' m</text>' in _svg and 'Total (perímetro)' in _svg

# 2. Superficies: UTM (la del GML), sobre el elipsoide algo mayor (factor de escala de la UTM), perímetro y vértices
superficies = (abs(lista[0].area_utm - 360) < 1e-6 and abs(lista[1].area_utm - 240) < 1e-6
               and 360 < lista[0].area_elipsoide < 360.5 and abs(lista[0].perimetro - 76) < 1e-6
               and [len(p) for _, p in lista[0].anillos] == [4])

# 3. Cabida inscrita: umbrales de la Ley Hipotecaria (5 % art. 201.3.b; 10 % arts. 9.b y 201.3.a)
_3 = su.comparar_cabida(600, 620)
_7 = su.comparar_cabida(600, 645)
_12 = su.comparar_cabida(600, 682)
cabida = (su.comparar_cabida(600, None) is None and len(_3[2]) == 2 and len(_7[2]) == 1 and '10 %' in _7[2][0]
          and _12[2] == [] and round(_3[1], 2) == 3.23 and _3[0] == -20)

# 4. HTML: aviso de no oficial, fuente y fecha de la consulta, autor, cabida, coordenadas con su lado
_html = su.html(lectura, ruta, lista, inscrita=620, autor='Técnico <prueba>', ahora=datetime.datetime(2026, 10, 15, 10, 0),
                consulta=datetime.datetime(2026, 10, 15, 9, 59))
documento = ('No es un documento oficial' in _html and 'Dirección General del Catastro' in _html
             and '15/10/2026 a las 09:59' in _html and 'Técnico &lt;prueba&gt;' in _html
             and '600,00 m²' in _html and '3,23 %' in _html and 'art. 201.3.b' in _html
             and 'Lado hasta el siguiente' in _html and '20,00' in _html and 'Seg_1' in _html
             and SIN in _html and _html.count('<section>') == 2)
documento = documento and 'Sin consultar el Catastro' in su.html(lectura, ruta, solo_gml)

# 5. Utilidades: propuesta del GML creado, informe con las colindantes, cabida errónea, autor recordado, sin internet
dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
pu = dw.pestanaUtilidades
QgsSettings().remove(pu_module.CLAVE_AUTOR)
dw.gml_creado(ruta)
propuesto = pu.origenSup.filePath() == ruta and pu.informeBoton.isEnabled() and '2 parcelas' in pu.estadoSup.text()


def textos_barra():
    item = dw.messageBar.currentItem()
    return ' '.join([item.text()] + [e.text() for e in item.findChildren(QLabel)]) if item is not None else ''


pu.cabida.setText('abc')
mal = pu.crear_informe(segundo_plano=False) is None and 'cabida inscrita' in textos_barra()
pu.cabida.setText('620,5')
pu.autor.setText('F. G. L.')
hecho = pu.crear_informe(segundo_plano=False)
with open(hecho or os.devnull, encoding='utf-8') as f:
    contenido = f.read()
interfaz = (mal and hecho == su.ruta_por_defecto(ruta) and 'Informe de superficies' in textos_barra()
            and '1907402VK4810H' in contenido and '620,50 m²' in contenido and 'F. G. L.' in contenido
            and QgsSettings().value(pu_module.CLAVE_AUTOR, '') == 'F. G. L.')
#Croquis general sobre la ortofoto (con su atribución) y uno por parcela, sin ortofoto, con las catastrales en gris
croquis_ui = (contenido.count('<svg') == 3 and contenido.count('class="leyenda"') == 3
              and 'Parcelas catastrales de alrededor' in contenido and contenido.count('<image') == 1 and 'data:image/jpeg;base64,' in contenido
              and 'PNOA cedido por © Instituto Geográfico Nacional' in contenido and 'stroke="#868e96"' in contenido
              and any('ign.es/wms-inspire/pnoa-ma' in u and 'CRS=EPSG:25830' in u for u in sim.peticiones))
#La ortofoto no responde: el informe sale igual, sin ella, y se dice
sim.ORTOFOTO_CAIDA = True
dw.messageBar.clearWidgets()
with open(pu.crear_informe(segundo_plano=False) or os.devnull, encoding='utf-8') as f:
    sin_orto = f.read()
croquis_ui = croquis_ui and '<image' not in sin_orto and 'Sin ortofoto' in textos_barra() and '1907402VK4810H' in sin_orto
sim.ORTOFOTO_CAIDA = False
#Sin las casillas de internet: ni consulta ni ortofoto
pu.colindantes.setChecked(False)
pu.ortofoto.setChecked(False)
antes = len(sim.peticiones)
with open(pu.crear_informe(segundo_plano=False) or os.devnull, encoding='utf-8') as f:
    sin_casillas = f.read()
croquis_ui = croquis_ui and len(sim.peticiones) == antes and '<image' not in sin_casillas
pu.colindantes.setChecked(True)
pu.ortofoto.setChecked(True)

# 6. Arrastrar y soltar de verdad: el evento llega a la casilla sobre la que se suelta (como en QGIS) y debe acabar en la
#utilidad abierta, desde el Explorador (fichero) o desde el panel de Capas (capa cargada por el plugin)
from qgis.core import QgsMimeDataUtils, QgsProject  # noqa: E402
from qgis.PyQt.QtCore import QMimeData, QPointF, Qt, QUrl  # noqa: E402
from qgis.PyQt.QtGui import QDragEnterEvent, QDropEvent  # noqa: E402
from qgis.PyQt.QtWidgets import QApplication, QLineEdit  # noqa: E402

from catastral_gml_tools.gui import pestana_validar as pv_mod  # noqa: E402

capa = pv_mod.cargar(lectura, ruta)
otro = os.path.join(carpeta, 'otro.gml')
gp.escribir(otro, [gp.ParcelaGML('Otra', gp.LOCAL, sim.rect(X0, Y0, 10, 10))], 25830)


def soltar_en(casilla, mime):
    """Arrastra hasta la casilla y suelta; True si alguien aceptó (Qt pasa el evento al padre que acepta soltar)."""
    acciones = Qt.DropAction.MoveAction | Qt.DropAction.CopyAction
    entrar = QDragEnterEvent(casilla.rect().center(), acciones, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(casilla, entrar)
    soltar = QDropEvent(QPointF(casilla.rect().center()), acciones, mime, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(casilla, soltar)
    return entrar.isAccepted() and soltar.isAccepted() and soltar.dropAction() == Qt.DropAction.CopyAction


def fichero(r):
    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(r)])
    return m


pu.utilidades.setCurrentIndex(2)
pu.origenSup.setFilePath('')
arrastre = (soltar_en(pu.origenSup.lineEdit(), fichero(otro)) and os.path.normpath(pu.origenSup.filePath()) == otro
            and soltar_en(pu.cabida, QgsMimeDataUtils.encodeUriList([QgsMimeDataUtils.Uri(capa)]))
            and os.path.normpath(pu.origenSup.filePath()) == os.path.normpath(ruta) and pu.cabida.text() == '620,5'
            and QgsProject.instance().mapLayer(capa.id()) is not None)
pu.utilidades.setCurrentIndex(1)
arrastre = arrastre and soltar_en(pu.destinoConv.lineEdit(), fichero(otro)) and os.path.normpath(pu.origenConv.filePath()) == otro
pu.utilidades.setCurrentIndex(0)
arrastre = arrastre and soltar_en(pu.destino.lineEdit(), fichero(otro)) and os.path.normpath(otro) in pu.rutas()
pv = dw.pestanaValidar
arrastre = arrastre and soltar_en(pv.fichero.lineEdit(), fichero(otro)) and os.path.normpath(pv.fichero.filePath()) == otro
#Ninguna casilla de las pestañas que admiten soltar se queda con lo soltado
arrastre = arrastre and all(not c.acceptDrops() for t in (pu, pv) for c in t.findChildren(QLineEdit))
QgsProject.instance().removeMapLayer(capa.id())
pu.utilidades.setCurrentIndex(2)
pu.origenSup.setFilePath(ruta)
#Sin internet: el informe se hace igual, sin las colindantes, y se dice
servicios.pedir = lambda url: (b'', 'Host ovc.catastro.meh.es not found (simulado)')
dw.messageBar.clearWidgets()
hecho_sin = pu.crear_informe(segundo_plano=False)
with open(hecho_sin or os.devnull, encoding='utf-8') as f:
    contenido_sin = f.read()
sin_red = (hecho_sin is not None and 'Sin linderos con el Catastro' in textos_barra() and 'Sin ortofoto' in textos_barra()
           and 'Sin consultar el Catastro' in contenido_sin)
servicios.pedir = sim.pedir
#Cancelar la consulta: el botón vuelve a estar disponible
tarea = pu_module.TareaSuperficies(ruta, lectura, pu)
pu.tarea_sup = tarea
pu.informeBoton.setEnabled(False)
tarea.cancel()
tarea.finished(False)
cancelar = pu.tarea_sup is None and pu.informeBoton.isEnabled() and pu.informeBoton.text() == "Crear informe"
#Un GML de edificios no vale
pu.origenSup.setFilePath(os.path.join(RAIZ, 'tests', 'data', 'gml', 'edificio_sintetico.gml'))
no_parcela = not pu.informeBoton.isEnabled() and 'GML de parcela' in pu.estadoSup.text()

QgsSettings().remove(pu_module.CLAVE_AUTOR)
servicios.pedir = original
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
dw.deleteLater()

checks = {
    "linderos lado a lado: GML, catastrales colindantes (no la de origen) y suelo sin parcela": linderos_ok,
    "sin consultar el Catastro: solo los linderos entre parcelas del GML": sin_catastro,
    "rumbos N, E, S, O con el anillo en cualquier sentido": rumbos,
    "lado corto de esquina: con la colindante, y los linderos suman el perímetro": esquinas,
    "croquis con vértices numerados, norte y escala; total de linderos": croquis,
    "superficie UTM, sobre el elipsoide, perímetro y vértices": superficies,
    "cabida inscrita: diferencia y umbrales del 5 % y el 10 % de la Ley Hipotecaria": cabida,
    "HTML: no oficial, fuente y fecha de la consulta, autor, cabida, coordenadas y lados": documento,
    "Utilidades: GML propuesto, informe con colindantes, cabida errónea y autor recordado": propuesto and interfaz,
    "croquis general sobre la ortofoto PNOA y uno por parcela; sin ortofoto o sin casillas, igual": croquis_ui,
    "arrastrar a cualquier casilla (fichero o capa) va a la utilidad abierta, también en Validar": arrastre,
    "sin internet: informe igual, sin colindantes ni ortofoto y avisando": sin_red,
    "cancelar la consulta deja el botón disponible; un GML de edificios no vale": cancelar and no_parcela,
    "ninguna ventana emergente": not ventanas,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· informe de superficies y coordenadas")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'l0': resumen(lista[0]), 'l1': resumen(lista[1]), 'g0': resumen(solo_gml[0]), 'g1': resumen(solo_gml[1]), 'esq': _esq, 'esq_gml': _esq_gml,
                        'sup': [(f.area_utm, f.area_elipsoide, f.perimetro) for f in lista], 'c3': _3, 'c7': _7,
                        'barra': textos_barra(), 'hecho': hecho, 'estado': pu.estadoSup.text(), 'errores': errores})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
