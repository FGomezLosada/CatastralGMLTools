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
from qgis.core import Qgis, QgsProject, QgsRectangle
from qgis.PyQt.QtWidgets import QLabel, QMessageBox

qgis.utils.reloadPlugin('catastral_gml_tools')
import catastral_gml_tools.catastral_gml_tools_dockwidget as dock_module  # noqa: E402
from catastral_gml_tools.core import comparacion as cmp  # noqa: E402
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

# 6. Referencia que no existe en el Catastro
noex = comparar('no_existe', [('1907499VK4810H', 'S', rect(X0, Y0, 20, 30))])
no_existe = 'CMP-RC-NO-EXISTE' in codigos(noex.incidencias)

# 7. Dominio público afectado (el camino de 60 m, solo en parte): aviso y error de parcial
dp = comparar('dominio', [(sim.RC, 'S', rect(X0, Y0 - 6, 20, 36))])
dominio = ('CMP-DOMINIO-PUBLICO' in codigos(dp.incidencias) and sim.CAMINO in str(dp.incidencias)
           and 'CMP-PARCIAL' in codigos(dp.incidencias))

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
    "segregación: NPO 1, NPP 2, contorno coincidente y sin errores": segregacion,
    "división, agregación y agrupación según NPO/NPP/namespace": operaciones,
    "no permitida: dos SDGC de una parcela, y RC que no es de las afectadas": no_permitida,
    "colindante afectada en parte: error y superficie sin cubrir": parcial,
    "suelo sin parcela (vía pública): error y superficie en exceso": sin_parcela,
    "referencia que no existe en el Catastro": no_existe,
    "dominio público afectado: aviso": dominio,
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
    print("Detalles:", {n: [(c.operacion, c.npo, c.npp, [str(i) for i in c.incidencias],
                             c.exceso.area() if c.exceso else None, c.defecto.area() if c.defecto else None)]
                        for n, c in (('seg', seg), ('div', div), ('agr', agr), ('agp', agp), ('np', np_), ('par', par),
                                     ('sin', sin), ('noex', noex), ('dp', dp), ('caido', caido))},
          {'lista': lista, 'barra': barra, 'textos': textos, 'ui': [desactivado, activo, grupo is not None]})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
