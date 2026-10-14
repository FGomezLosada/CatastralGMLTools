"""
Prueba de core/comparacion.py y del botón «Comparar con el Catastro» de la pestaña Validar, con el Catastro simulado
(tests/simulador_catastro.py): operación según NPO/NPP/namespace, contorno exterior, parcelas afectadas en parte,
suelo sin parcela, referencias que no existen o no son de las afectadas, dominio público, sin conexión y capas de la
comparación en el mapa. Sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py comparacion_test.py)
"""
import importlib.util
import os
import tempfile

import qgis.utils
from qgis.core import Qgis, QgsGeometry, QgsPointXY, QgsProject, QgsRectangle
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

qgis.utils.reloadPlugin('catastral_gml_tools')
import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import comparacion as cmp  # noqa: E402
from catastral_gml_tools.core import gml_edificio as ge  # noqa: E402
from catastral_gml_tools.core import gml_lector as gl  # noqa: E402
from catastral_gml_tools.core import gml_parcela as gp  # noqa: E402
from catastral_gml_tools.core import servicios  # noqa: E402
from catastral_gml_tools.core.incidencias import ERROR, codigos  # noqa: E402
from catastral_gml_tools.core.info import RAIZ  # noqa: E402

spec = importlib.util.spec_from_file_location('simulador_catastro', os.path.join(RAIZ, 'tests', 'simulador_catastro.py'))
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)
original = sim.instalar()

ventanas = []
_originales = {n: getattr(QMessageBox, n) for n in ('warning', 'information', 'critical', 'question')}
for _n in _originales:
    setattr(QMessageBox, _n, lambda *a, **k: ventanas.append(a))

X0, Y0, rect = sim.X0, sim.Y0, sim.rect
carpeta = tempfile.mkdtemp(prefix='cgt_cmp_')


def gml(nombre, parcelas):
    ruta = os.path.join(carpeta, nombre + '.gml')
    gp.escribir(ruta, [gp.ParcelaGML(i, gp.SDGC if gp_ns == 'S' else gp.LOCAL, g) for i, gp_ns, g in parcelas], 25830)
    return ruta


def comparar(nombre, parcelas):
    return cmp.comparar(gl.leer(gml(nombre, parcelas)))


def operacion_de(c):
    return c.operacion.split(' (')[0]


# 1. Segregación correcta: la parcela conserva su RC y sale una nueva; el contorno coincide
seg = comparar('segregacion', [(sim.RC, 'S', rect(X0, Y0, 20, 18)), ('Nueva_1', 'L', rect(X0, Y0 + 18, 20, 12))])
segregacion = (seg.comparada and seg.npo == 1 and seg.npp == 2 and operacion_de(seg) == 'Segregación'
               and 'CMP-CONTORNO-OK' in codigos(seg.incidencias) and not [i for i in seg.incidencias if i.nivel == ERROR]
               and seg.exceso is None and seg.defecto is None and [e.local_id for e in seg.origen] == [sim.RC])

# 2. División (todas LOCAL), agregación (una SDGC sobre dos parcelas) y agrupación (una LOCAL)
div = comparar('division', [('Div_1', 'L', rect(X0, Y0, 10, 30)), ('Div_2', 'L', rect(X0 + 10, Y0, 10, 30))])
agr = comparar('agregacion', [(sim.RC, 'S', rect(X0, Y0, 40, 30))])
agp = comparar('agrupacion', [('Agrupa_1', 'L', rect(X0, Y0, 40, 30))])
operaciones = (operacion_de(div) == 'División' and operacion_de(agr) == 'Agregación' and agr.npo == 2
               and operacion_de(agp) == 'Agrupación' and 'CMP-CONTORNO-OK' in codigos(agr.incidencias))

# 3. No permitida: de una parcela salen dos con referencia (y la segunda no es de las afectadas)
np_ = comparar('no_permitida', [(sim.RC, 'S', rect(X0, Y0, 20, 15)), ('1907402VK4810H', 'S', rect(X0, Y0 + 15, 20, 15))])
no_permitida = ('No permitida' in np_.operacion and 'CMP-RC-AJENA' in codigos(np_.incidencias)
                and [i.nivel for i in np_.incidencias if i.codigo == 'CMP-OPERACION'] == [ERROR])

# 4. Parcela colindante afectada en parte: error y defecto (lo que queda fuera del GML)
par = comparar('parcial', [(sim.RC, 'S', rect(X0, Y0, 25, 30))])
parcial = ('CMP-PARCIAL' in codigos(par.incidencias) and par.defecto is not None and abs(par.defecto.area() - 450) < 2
           and any('1907402VK4810H' in i.mensaje for i in par.incidencias if i.codigo == 'CMP-PARCIAL')
           and 'CMP-CONTORNO-OK' not in codigos(par.incidencias))

# 5. Suelo sin parcela (la «calle» entre 1907403 y 1907408): error y exceso
sin = comparar('sin_parcela', [('1907403VK4810H', 'S', rect(X0 + 40, Y0, 30, 30))])
sin_parcela = ('CMP-SIN-PARCELA' in codigos(sin.incidencias) and sin.exceso is not None
               and abs(sin.exceso.area() - 300) < 2)
#Con una parcela nueva (LOCAL) que cubre la calle: positivo condicionado, aviso (AU-21)
viario = comparar('viario', [('Nueva_1', 'L', rect(X0 + 40, Y0, 30, 30))])
sin_parcela = (sin_parcela and 'CMP-VIARIO' in codigos(viario.incidencias)
               and 'CMP-SIN-PARCELA' not in codigos(viario.incidencias) and 'negativo' not in str(sin.incidencias))

# 5b. Dos segregaciones separadas en un GML (multiparcela): la operación del conjunto y la de cada zona; cada zona se
#pide aparte (no el rectángulo de 5 km que las abarca)
sim.peticiones.clear()
dos_zonas = comparar('dos_zonas', [(sim.RC, 'S', rect(X0, Y0, 20, 18)), ('Nueva_1', 'L', rect(X0, Y0 + 18, 20, 12)),
                                   (sim.RC_GRANDE, 'S', rect(X0 + 5000, Y0, 600, 1000)),
                                   ('Nueva_2', 'L', rect(X0 + 5600, Y0, 600, 1000))])
_zonas = [i.mensaje for i in dos_zonas.incidencias if i.codigo == 'CMP-ZONAS']
_wfs = [u for u in sim.peticiones if 'storedquerie' not in u.lower() and 'bbox' in u.lower()]
zonas_ok = (len(_zonas) == 1 and 'zona 1: NPO 1 · NPP 2 → Segregación' in _zonas[0]
            and 'zona 2: NPO 1 · NPP 2 → Segregación' in _zonas[0] and dos_zonas.npo == 2 and dos_zonas.npp == 4
            and 'CMP-ZONAS' not in codigos(seg.incidencias) and len(_wfs) <= 6)

# 6. Referencia que no existe en el Catastro
noex = comparar('no_existe', [('1907499VK4810H', 'S', rect(X0, Y0, 20, 30))])
no_existe = 'CMP-RC-NO-EXISTE' in codigos(noex.incidencias)
#Sin parcelas de la DGC debajo: en Vitoria-Gasteiz avisa de que puede ser de un catastro foral; en el sur, no (AU-31)
vitoria = comparar('vitoria', [('Nueva_1', 'L', rect(526000, 4743500, 20, 30))])
vacio = comparar('vacio', [('Nueva_1', 'L', rect(X0 + 3000, Y0 + 3000, 20, 30))])
foral_posicion = ('CMP-SIN-ORIGEN' in codigos(vitoria.incidencias) and 'CMP-FORAL' in codigos(vitoria.incidencias)
                  and 'País Vasco' in str(vitoria.incidencias) and 'CMP-SIN-ORIGEN' in codigos(vacio.incidencias)
                  and 'CMP-FORAL' not in codigos(vacio.incidencias)
                  and cmp.servicios.zona_foral(QgsPointXY(610000, 4740000), 25830) == 'Navarra')

# 7. Dominio público afectado (el camino de 60 m, solo en parte): aviso y error de parcial
dp = comparar('dominio', [(sim.RC, 'S', rect(X0, Y0 - 6, 20, 36))])
dominio = ('CMP-DOMINIO-PUBLICO' in codigos(dp.incidencias) and sim.CAMINO in str(dp.incidencias)
           and 'CMP-PARCIAL' in codigos(dp.incidencias) and 'CMP-MUNICIPIOS' not in codigos(dp.incidencias))
#Las mismas parcelas, si la urbana fuera de otro municipio: la Sede no valida dos municipios en un GML (AU-26)
sim.MUNICIPIO_URBANA = 99
dos_mun = comparar('dos_municipios', [(sim.RC, 'S', rect(X0, Y0 - 6, 20, 36))])
sim.MUNICIPIO_URBANA = 71
dominio = dominio and 'CMP-MUNICIPIOS' in codigos(dos_mun.incidencias)

# 8. Sin conexión: no se compara y se dice
servicios.pedir = lambda url: (b'', 'Host not found (simulado)')
caido = comparar('caido', [(sim.RC, 'S', rect(X0, Y0, 20, 30))])
sim.instalar()
sin_red = not caido.comparada and codigos(caido.incidencias) == ['CMP-NO-COMPARADO']

# 9. Trozos de 1 km como mucho (límite del WFS) y tabla de operaciones
trozos = cmp._trozos(QgsRectangle(0, 0, 2500, 1200))
tabla = (len(trozos) == 6 and all(t.width() <= 1000 and t.height() <= 1000 for t in trozos)
         and cmp.operacion(2, 2, [gl.ElementoGML(gl.PARCELA, 'A', 'ES.SDGC.CP', None),
                                  gl.ElementoGML(gl.PARCELA, 'B', 'ES.SDGC.CP', None)], ['A', 'B'])[0]
         == 'Subsanación de discrepancias'
         and 'no se tramita' in cmp.operacion(2, 2, [gl.ElementoGML(gl.PARCELA, 'A', 'ES.LOCAL.CP', None)], ['A'])[0])

# 11. Tolerancia de 1 cm medida en distancia (AU-01) y parcelas sin cambios (AU-03)
def nueva(dx=0.0, entrante=False):
    """La parte norte de la segregación con el vértice NE desplazado dx hacia el este, o con un entrante de 4 cm × 1 m."""
    xs = X0 + 20 + dx
    if entrante:
        anillo = (f"{X0} {Y0 + 18}, {X0 + 20} {Y0 + 18}, {X0 + 20} {Y0 + 30}, {X0 + 10} {Y0 + 30}, {X0 + 10} {Y0 + 29.96}, "
                  f"{X0 + 9} {Y0 + 29.96}, {X0 + 9} {Y0 + 30}, {X0} {Y0 + 30}, {X0} {Y0 + 18}")
    else:
        anillo = f"{X0} {Y0 + 18}, {X0 + 20} {Y0 + 18}, {xs} {Y0 + 30}, {X0} {Y0 + 30}, {X0} {Y0 + 18}"
    return QgsGeometry.fromWkt(f"POLYGON(({anillo}))")


def seg_con(nombre, geometria):
    return comparar(nombre, [(sim.RC, 'S', rect(X0, Y0, 20, 18)), ('Nueva_1', 'L', geometria)])


medio = seg_con('medio_cm', nueva(0.005))
dos = seg_con('dos_cm', nueva(0.02))
entra = seg_con('entrante', nueva(entrante=True))
igual = comparar('igual', [(sim.RC, 'S', rect(X0, Y0, 20, 30))])
tolerancia = ('CMP-CONTORNO-OK' in codigos(medio.incidencias) and not [i for i in medio.incidencias if i.nivel == ERROR]
              and 'CMP-PARCIAL' in codigos(dos.incidencias) and 'CMP-CONTORNO-OK' not in codigos(dos.incidencias)
              and 'CMP-PARCIAL' in codigos(entra.incidencias) and 'CMP-CONTORNO-OK' not in codigos(entra.incidencias)
              and 'hasta 4.0 cm' in str(entra.incidencias) and 'hasta 2.0 cm' in str(dos.incidencias))
sin_cambios = ('CMP-SIN-CAMBIOS' in codigos(igual.incidencias) and 'CMP-SIN-CAMBIOS' not in codigos(seg.incidencias)
               and 'CMP-SIN-CAMBIOS' not in codigos(medio.incidencias))
#Edificio: 2 cm fuera de la parcela es fuera; 0,5 cm, dentro
ruta_bu = os.path.join(carpeta, 'bu.gml')
ge.escribir(ruta_bu, [ge.Construccion(sim.RC, rect(X0 + 15, Y0 + 5, 5.02, 4), plantas=1)], 25830)
bu_fuera = cmp.comparar_edificio(gl.leer(ruta_bu))
ge.escribir(ruta_bu, [ge.Construccion(sim.RC, rect(X0 + 15, Y0 + 5, 5.005, 4), plantas=1)], 25830)
bu_dentro = cmp.comparar_edificio(gl.leer(ruta_bu))
tolerancia_bu = codigos(bu_fuera.incidencias) == ['CMP-BU-FUERA'] and codigos(bu_dentro.incidencias) == ['CMP-BU-DENTRO']
#BICE y diseminado de urbana (Consulta_DNPRC): avisos de que no hay tramitación automática ni ICUC (AU-33)
sim.CLASES[sim.RC] = 'BI'
bice = comparar('bice', [(sim.RC, 'S', rect(X0, Y0, 20, 18)), ('Nueva_1', 'L', rect(X0, Y0 + 18, 20, 12))])
bu_bice = cmp.comparar_edificio(gl.leer(ruta_bu))
sim.CLASES[sim.RC] = 'DS'
disem = comparar('diseminado', [(sim.RC, 'S', rect(X0, Y0, 20, 18)), ('Nueva_1', 'L', rect(X0, Y0 + 18, 20, 12))])
sim.CLASES.clear()
sim.CLASES[sim.CAMINO] = 'DS'  #Rústica con una dirección «DS»: no es diseminado de urbana
rustica_ds = comparar('rustica_ds', [(sim.RC, 'S', rect(X0, Y0 - 6, 20, 36))])
sim.CLASES.clear()
especiales = ('CMP-BICE' in codigos(bice.incidencias) and 'CMP-DISEMINADO' not in codigos(bice.incidencias)
              and 'CMP-BU-BICE' in codigos(bu_bice.incidencias) and 'CMP-DISEMINADO' in codigos(disem.incidencias)
              and 'CMP-BICE' not in codigos(disem.incidencias) and 'CMP-BICE' not in codigos(seg.incidencias)
              and 'CMP-DISEMINADO' not in codigos(seg.incidencias) and 'CMP-DISEMINADO' not in codigos(dp.incidencias)
              and 'CMP-DISEMINADO' not in codigos(rustica_ds.incidencias) and 'CMP-DOMINIO-PUBLICO' in codigos(rustica_ds.incidencias))

# 10. Pestaña Validar: botón, lista, aviso en la barra y capas de la comparación
dw = dock_module.CatastralGMLToolsDockWidget(qgis.utils.iface)
pv = dw.pestanaValidar
desactivado = not pv.cmpBoton.isEnabled()
pv.fichero.setFilePath(os.path.join(carpeta, 'segregacion.gml'))
pv.esquema_comprobado([])
activo = pv.cmpBoton.isEnabled()
pv.comparar_catastro(segundo_plano=False)
lista = [pv.lista.item(i).text() for i in range(pv.lista.count())]
raiz = QgsProject.instance().layerTreeRoot()
grupo = raiz.findGroup('Comparación segregacion')
barra = ' | '.join(e.text() for item in dw.messageBar.items() for e in item.findChildren(QLabel))
interfaz = (desactivado and activo and any('NPO 1' in t and 'Segregación' in t for t in lista)
            and grupo is not None and [n.name() for n in grupo.children()] == ['Catastro vigente (parcelas afectadas)']
            and 'Segregación' in barra and pv.cmpBoton.isEnabled())
pv.fichero.setFilePath(os.path.join(carpeta, 'parcial.gml'))
pv.esquema_comprobado([])
dw.messageBar.clearWidgets()
pv.comparar_catastro(segundo_plano=False)
grupo = raiz.findGroup('Comparación parcial')
textos = ' | '.join(item.text() for item in dw.messageBar.items())
interfaz = (interfaz and grupo is not None
            and [n.name() for n in grupo.children()] == ['Defecto: parcela catastral sin cubrir',
                                                          'Catastro vigente (parcelas afectadas)']
            and 'error' in textos and '1 error' in pv.estado.text()
            and any(i.codigo == 'CMP-PARCIAL' for i in pv.informe.incidencias))

servicios.pedir = original
for _n, _f in _originales.items():
    setattr(QMessageBox, _n, _f)
dw.deleteLater()

tramite = (cmp._clave_tramite('9872023VH5797S') == 'manzana 98720, hoja VH5797S'
           and cmp._clave_tramite('29071A00700123') == 'polígono 7 del municipio 29071'
           and cmp._clave_tramite('9872023VH5797S') != cmp._clave_tramite('9872124VH5797S')
           and cmp._clave_tramite('Nueva_1') == '')
checks = {
    "tolerancia de 1 cm en distancia (0,5 cm bien; 2 cm y entrante de 4 cm, no)": tolerancia,
    "parcela igual a la catastral: error «sin cambios»": sin_cambios,
    "edificio 2 cm fuera de la parcela: fuera; 0,5 cm: dentro": tolerancia_bu,
    "BICE (parcela y edificio) y diseminado de urbana: avisos": especiales,
    "segregación: NPO 1, NPP 2, contorno coincidente y sin errores": segregacion,
    "división, agregación y agrupación según NPO/NPP/namespace": operaciones,
    "no permitida: dos SDGC de una parcela, y RC que no es de las afectadas": no_permitida,
    "colindante afectada en parte: error y superficie sin cubrir": parcial,
    "suelo sin parcela: error con SDGC; aviso (positivo condicionado) con parcela LOCAL": sin_parcela,
    "referencia que no existe en el Catastro": no_existe,
    "dos operaciones separadas en un GML: la de cada zona, pidiendo solo cada zona": zonas_ok,
    "sin parcelas de la DGC: pista de catastro foral por la posición": foral_posicion,
    "dominio público afectado: aviso; dos municipios: error": dominio,
    "sin conexión: no se compara y se avisa": sin_red,
    "rectángulos de 1 km como mucho y tabla de operaciones": tabla,
    "pestaña Validar: botón, lista, barra y capas de la comparación": interfaz,
    "polígono o manzana para la tramitación automática": tramite,
    "ninguna ventana emergente": not ventanas,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· comparación con el Catastro")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Tolerancia:", {n: [str(i) for i in c.incidencias] for n, c in (('medio', medio), ('dos', dos), ('entra', entra),
                                                                         ('igual', igual), ('bu_fuera', bu_fuera),
                                                                         ('bu_dentro', bu_dentro))})
    print("Detalles:", {n: [(c.operacion, c.npo, c.npp, [str(i) for i in c.incidencias],
                             c.exceso.area() if c.exceso else None, c.defecto.area() if c.defecto else None)]
                        for n, c in (('seg', seg), ('div', div), ('agr', agr), ('agp', agp), ('np', np_), ('par', par),
                                     ('sin', sin), ('noex', noex), ('dos_zonas', dos_zonas), ('vitoria', vitoria), ('bice', bice), ('disem', disem), ('bu_bice', bu_bice), ('vacio', vacio), ('dp', dp), ('caido', caido))},
          {'lista': lista, 'barra': barra, 'textos': textos, 'ui': [desactivado, activo, grupo is not None]})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
