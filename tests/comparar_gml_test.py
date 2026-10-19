"""
Prueba de «Comparar dos GML» (mejora 34): core/comparar_gml.py y la utilidad «5.» de Utilidades. Ficheros iguales,
desplazados, con un vértice movido o añadido, con identificadores cambiados, con recintos de más o de menos, en otro
sistema de referencia (geográficas en latitud-longitud con 6 decimales, como puede devolverlos otro organismo), errores,
informe HTML, y la interfaz (arrastrar los dos, mismo fichero dos veces, ver en el mapa).

Uso: tools\\probar.bat (o tools\\run_tests.py comparar_gml_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os
import re
import shutil
import tempfile

import qgis.utils
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
)
from qgis.PyQt.QtCore import QMimeData, QPointF, Qt, QUrl
from qgis.PyQt.QtGui import QDragEnterEvent, QDropEvent
from qgis.PyQt.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton

import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import ajuste as aj  # noqa: E402
from catastral_gml_tools.core import comparar_gml as cg  # noqa: E402
from catastral_gml_tools.core import gml_parcela as gp  # noqa: E402

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))

carpeta = tempfile.mkdtemp(prefix='cgt_comparar_')
X0, Y0 = 421500.0, 4070500.0


def rect(x, y, w, h):
    return QgsGeometry.fromWkt(f"POLYGON(({x} {y}, {x} {y + h}, {x + w} {y + h}, {x + w} {y}, {x} {y}))")


def gml(nombre, parcelas):
    ruta = os.path.join(carpeta, nombre)
    ok, inc = gp.escribir(ruta, parcelas, 25830)
    assert ok, inc
    return ruta


RC = '1907401VK4810H'
A = gml('a.gml', [gp.ParcelaGML(RC, gp.SDGC, rect(X0, Y0, 20, 30), '01'), gp.ParcelaGML('Seg_1', gp.LOCAL, rect(X0 + 20, Y0, 15, 30))])

# 1. Iguales (una copia)
copia = os.path.join(carpeta, 'copia.gml')
shutil.copy(A, copia)
c = cg.comparar(A, copia)
iguales = c.iguales() and len(c.parejas) == 2 and all(p.veredicto() == "Igual (±1 cm)" for p in c.parejas)

# 2. Desplazados 3 cm al este (todos los vértices igual)
desplazado = os.path.join(carpeta, 'desplazado.gml')
aj.escribir_ajustado(A, desplazado, aj.Transformacion(cx=0.03))
c = cg.comparar(A, desplazado)
p = c.parejas[0]
uniforme = (not c.iguales() and p.traslacion is not None and p.veredicto() == "Desplazado 3,0 cm hacia E"
            and 'ΔX +3,0 cm, ΔY +0,0 cm' in cg.html(c)
            and abs(p.hausdorff - 0.03) < 1e-6 and abs(p.maximo - 0.03) < 1e-6)

# 3. Un vértice movido 5 cm; 4. un vértice de más en un lado (misma geometría)
movido = gml('movido.gml', [gp.ParcelaGML(RC, gp.SDGC, QgsGeometry.fromWkt(
    f"POLYGON(({X0} {Y0}, {X0} {Y0 + 30}, {X0 + 19.95} {Y0 + 30}, {X0 + 20} {Y0}, {X0} {Y0}))"), '01'),
    gp.ParcelaGML('Seg_1', gp.LOCAL, rect(X0 + 20, Y0, 15, 30))])
c = cg.comparar(A, movido)
p = c.parejas[0]
un_vertice = (p.veredicto().startswith("Distinto: hasta 5,0 cm") and [v for v in p.vertices if v[3] > 0.01][0][3] > 0.049
              and p.traslacion is None and c.parejas[1].veredicto() == "Igual (±1 cm)")
con_vertice = gml('con_vertice.gml', [gp.ParcelaGML(RC, gp.SDGC, QgsGeometry.fromWkt(
    f"POLYGON(({X0} {Y0}, {X0} {Y0 + 15}, {X0} {Y0 + 30}, {X0 + 20} {Y0 + 30}, {X0 + 20} {Y0}, {X0} {Y0}))"), '01'),
    gp.ParcelaGML('Seg_1', gp.LOCAL, rect(X0 + 20, Y0, 15, 30))])
c = cg.comparar(A, con_vertice)
p = c.parejas[0]
vertice_mas = (p.veredicto() == "Misma geometría; cambian datos" and p.anadidos == 1 and p.quitados == 0
               and ('Nº de vértices', '4', '5') in p.datos)

# 5. Identificador cambiado (se empareja por la geometría); recinto solo en uno
renombrado = gml('renombrado.gml', [gp.ParcelaGML(RC, gp.SDGC, rect(X0, Y0, 20, 30), '01'),
                                    gp.ParcelaGML('Nueva_1', gp.LOCAL, rect(X0 + 20, Y0, 15, 30)),
                                    gp.ParcelaGML('Nueva_2', gp.LOCAL, rect(X0 + 35, Y0, 10, 30))])
c = cg.comparar(A, renombrado)
veredictos = {p.nombre: (p.veredicto(), p.por) for p in c.parejas}
renombre = (veredictos.get('Seg_1 ↔ Nueva_1') == ("Misma geometría; cambian datos", 'geometría')
            and veredictos.get('Nueva_2', ('',))[0] == "Solo en el segundo" and ('Recintos', '2', '3') in c.generales)
c_inverso = cg.comparar(renombrado, A)
renombre = renombre and any(p.veredicto() == "Solo en el primero" for p in c_inverso.parejas)

# 6. En geográficas (ETRS89, latitud-longitud) con 6 decimales: se pasa al SRC del primero y se explica el redondeo
transformacion = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:25830'), QgsCoordinateReferenceSystem('EPSG:4258'),
                                        QgsCoordinateTransformContext())


def a_geograficas(m):
    numeros = [float(v) for v in m.group(2).split()]
    salida = []
    for i in range(0, len(numeros), 2):
        q = transformacion.transform(QgsPointXY(numeros[i], numeros[i + 1]))
        salida += [f"{q.y():.6f}", f"{q.x():.6f}"]
    return m.group(1) + ' '.join(salida) + m.group(3)


with open(A, encoding='utf-8') as f:
    texto = f.read()
texto = re.sub(r'(<gml:pos(?:List)?\b[^>]*>)([^<]*)(</gml:pos(?:List)?>)', a_geograficas, texto)
geograficas = os.path.join(carpeta, 'geograficas.gml')
with open(geograficas, 'w', encoding='utf-8') as f:
    f.write(texto.replace('EPSG/0/25830', 'EPSG/0/4258'))
c = cg.comparar(A, geograficas)
notas = ' '.join(c.notas)
p = c.parejas[0]
geografico = (len(c.parejas) == 2 and p.a is not None and p.b is not None and ('Sistema de referencia', 'EPSG:25830', 'EPSG:4258') in c.generales
              and 'latitud, longitud' in notas and 'EPSG:4258' in notas and 'hasta 5,6 cm' in notas
              and p.hausdorff < 0.08 and abs(p.area_b - p.area_a) < 0.5
              and any(d[0] == 'Diferencia' and 'redondeo' in d[2] for d in p.datos))

# 7. Errores y resumen
c_error = cg.comparar(A, os.path.join(carpeta, 'no_existe.gml'))
errores = bool(c_error.errores) and not c_error.parejas and cg.resumen(c_error) == c_error.errores
c = cg.comparar(A, renombrado)
lineas = cg.resumen(c)
errores = (errores and lineas[0].startswith('Fichero: recintos 2 → 3') and any('Seg_1 ↔ Nueva_1' in x for x in lineas)
           and any(x == 'Iguales (±1 cm): 1' for x in lineas))

# 8. Informe HTML
informe = cg.escribir(cg.comparar(A, movido))
with open(informe, encoding='utf-8') as f:
    contenido = f.read()
html_ok = (os.path.normpath(informe) == os.path.normpath(cg.ruta_informe(A)) and 'Hay diferencias' in contenido and 'stroke-dasharray' in contenido
           and 'Vértices que se mueven más de 1 cm (1 de 4)' in contenido and 'Herramienta no oficial' in contenido)

# 9. Interfaz: Utilidades «5.»
dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
pu = dw.pestanaUtilidades
pu.utilidades.setCurrentIndex(4)
bc = pu.comparador


def textos_barra():
    textos = []
    for item in dw.messageBar.items():
        textos.append(item.text())
        textos += [e.text() for e in item.findChildren(QLabel)]
    return ' | '.join(textos)


#Arrastrar los dos a la vez sobre una casilla: primero y segundo
mime = QMimeData()
mime.setUrls([QUrl.fromLocalFile(A), QUrl.fromLocalFile(desplazado)])
acciones = Qt.DropAction.MoveAction | Qt.DropAction.CopyAction
casilla = bc.gmlB.lineEdit()
QApplication.sendEvent(casilla, QDragEnterEvent(casilla.rect().center(), acciones, mime, Qt.MouseButton.LeftButton,
                                                Qt.KeyboardModifier.NoModifier))
soltar = QDropEvent(QPointF(casilla.rect().center()), acciones, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
QApplication.sendEvent(casilla, soltar)
interfaz = (soltar.isAccepted() and os.path.normpath(bc.gmlA.filePath()) == os.path.normpath(A)
            and os.path.normpath(bc.gmlB.filePath()) == os.path.normpath(desplazado) and bc.compararBoton.isEnabled())
#El mismo fichero dos veces, no
bc.gmlB.setFilePath(A)
interfaz = interfaz and not bc.compararBoton.isEnabled() and 'mismo fichero' in bc.resultado.text()
#Uno solo soltado con el primero ya puesto: va al segundo
pu.soltar([desplazado])
interfaz = interfaz and os.path.normpath(bc.gmlB.filePath()) == os.path.normpath(desplazado)
hecho = bc.comparar()
botones = [b.text() for item in dw.messageBar.items() for b in item.findChildren(QPushButton)]
interfaz = (interfaz and os.path.normpath(hecho or '') == os.path.normpath(cg.ruta_informe(A)) and 'Desplazado 3,0 cm hacia E' in bc.resultado.text() and 'Hay diferencias' in bc.resultado.text()
            and 'Abrir informe' in botones and 'Ver en el mapa' in botones)
#Ver en el mapa: los dos, el segundo en azul discontinuo
capas = bc.ver_en_mapa()
categorias = capas[1].renderer().categories() if capas else []  #Se guarda la lista: el símbolo es de la categoría
simbolo = categorias[0].symbol().symbolLayer(0) if categorias else None
mapa = (capas is not None and len(QgsProject.instance().mapLayers()) == 2 and simbolo.strokeStyle() == Qt.PenStyle.DashLine
        and simbolo.fillColor().alpha() == 0 and capas[0].featureCount() == 2)
#Otra vez: se sustituye el grupo, no se acumulan capas
bc.ver_en_mapa()
grupos = [g for g in QgsProject.instance().layerTreeRoot().findGroups(True) if g.name().startswith('Comparación')]
mapa = mapa and len(QgsProject.instance().mapLayers()) == 2 and len(grupos) == 1
#Iguales: mensaje en verde
bc.gmlB.setFilePath(copia)
bc.comparar()
interfaz = interfaz and 'Son iguales a efectos de la Sede' in bc.resultado.text()
#Un fichero que no es un GML
malo = os.path.join(carpeta, 'malo.gml')
with open(malo, 'w', encoding='utf-8') as f:
    f.write('esto no es un GML')
bc.gmlB.setFilePath(malo)
interfaz = interfaz and bc.comparar() is None and 'No se han podido comparar' in textos_barra()

QgsProject.instance().removeAllMapLayers()
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
dw.deleteLater()

checks = {
    "dos copias: iguales (±1 cm)": iguales,
    "desplazamiento uniforme de 3 cm hacia el E": uniforme,
    "un vértice movido 5 cm; el resto iguales": un_vertice,
    "un vértice de más en un lado: misma geometría, cambian los vértices": vertice_mas,
    "identificador cambiado (emparejado por la geometría) y recintos de más o de menos": renombre,
    "en geográficas latitud-longitud con 6 decimales: SRC, orden de ejes y redondeo": geografico,
    "errores y resumen para el panel": errores,
    "informe HTML con croquis superpuesto y vértices movidos": html_ok,
    "interfaz: arrastrar los dos, mismo fichero, comparar, iguales y fichero malo": interfaz,
    "ver los dos en el mapa (el segundo, azul discontinuo)": mapa,
    "ninguna ventana emergente": not ventanas,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· comparar dos GML")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'veredictos': veredictos, 'notas': notas, 'geo': [(q.veredicto(), q.hausdorff, q.datos) for q in
                                                                         cg.comparar(A, geograficas).parejas],
                        'lineas': lineas, 'resultado': bc.resultado.text(), 'barra': textos_barra()})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
