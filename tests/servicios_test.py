"""
Prueba de core/servicios.py: descarga de una parcela, sus colindantes y sus construcciones por referencia catastral,
y referencia catastral de un punto. Con los servicios simulados (tests/simulador_catastro.py) y, si hay internet,
una consulta real mínima (una parcela, sin guardar nada).

Uso: tools\\probar.bat (o tools\\run_tests.py servicios_test.py)
"""
import datetime
import importlib.util
import os

from qgis.core import Qgis

from catastral_gml_tools.core import servicios
from catastral_gml_tools.core.incidencias import codigos
from catastral_gml_tools.core.info import RAIZ

spec = importlib.util.spec_from_file_location('simulador_catastro', os.path.join(RAIZ, 'tests', 'simulador_catastro.py'))
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)

original = sim.instalar()

# 1. Direcciones de los servicios
urls = [servicios.url_parcela(sim.RC), servicios.url_colindantes(sim.RC, 25829), servicios.url_edificios(sim.RC),
        servicios.url_otras(sim.RC), servicios.url_rc_en_punto(-3.7085, 40.4207)]
direcciones = (all(u.startswith('https://ovc.catastro.meh.es/') for u in urls)
               and 'STOREDQUERIE_ID=GetParcel&refcat=1907401VK4810H&srsname=EPSG%3A%3A25830' in urls[0]
               and 'GetNeighbourParcel' in urls[1] and 'EPSG%3A%3A25829' in urls[1] and 'wfsBU.aspx' in urls[2]
               and 'GetOtherBuildingByParcel' in urls[3] and 'SRS=EPSG%3A4258&CoorX=-3.708500&CoorY=40.420700' in urls[4])

# 2. Descarga completa
ahora = datetime.datetime(2026, 10, 7, 9, 30)
d = servicios.descargar(sim.RC, ahora=ahora)
parcela = d.parcela.elementos[0] if d.parcela and d.parcela.elementos else None
completa = (d.correcta and d.epsg == 25830 and parcela is not None and parcela.local_id == sim.RC
            and parcela.area_declarada == 600 and len(sim.peticiones) == 4)
colindantes = (d.colindantes is not None
               and sorted(e.local_id for e in d.colindantes.elementos) == ['1907402VK4810H', sim.CAMINO]
               and [e.local_id for e in d.entorno.elementos] == ['1907403VK4810H']
               and 'typeNames=CP%3ACadastralParcel' in sim.peticiones[1] and 'bbox=421475.00%2C4070475.00%2C421545.00'
               in sim.peticiones[1] and not any('GetNeighbourParcel' in u for u in sim.peticiones))
construcciones = (d.construcciones is not None and len(d.construcciones.elementos) == 2
                  and d.construcciones.version == 'BU 2.0' and d.construcciones.epsg == 25830)
atribucion = d.atribucion() == "© Dirección General del Catastro · descargado el 07/10/2026 09:30"
resumen = [i.mensaje for i in d.incidencias if i.codigo == 'DESCARGA']
resumen_ok = resumen == [f"Parcela {sim.RC} · 600 m² · EPSG:25830 · 2 colindantes (1 de dominio público) · 1 en el entorno · 2 construcciones"]

# Dominio público: el camino se ve aparte y se avisa de que linda con él
camino = [e for e in d.colindantes.elementos if e.local_id == sim.CAMINO]
dominio = (camino and camino[0].tipo == 'dominio público'
           and [e.tipo for e in d.colindantes.elementos if e.local_id != sim.CAMINO] == ['parcela']
           and any(i.codigo == 'LINDA-DOMINIO-PUBLICO' and sim.CAMINO in i.mensaje and i.nivel == 'info'
                   for i in d.incidencias))

# 2b. Parcela demasiado grande para pedir su entorno: GetNeighbourParcel; «no hay colindantes» no es un error
grande = servicios.descargar(sim.RC_GRANDE, construcciones=False)
sin_colindantes = (grande.correcta and grande.colindantes is not None and not grande.colindantes.elementos
                   and grande.entorno is None and 'SIN-COLINDANTES' in codigos(grande.incidencias)
                   and not any(i.nivel != 'info' for i in grande.incidencias)
                   and 'GetNeighbourParcel' in sim.peticiones[-1])
# Rodeada de calles (sin colindantes) pero con parcelas cerca: entorno y nota informativa
isla = servicios.descargar('1907408VK4810H', construcciones=False)
sin_colindantes = (sin_colindantes and isla.correcta and not isla.colindantes.elementos and not isla.entorno.elementos
                   and [i.nivel for i in isla.incidencias if i.codigo == 'SIN-COLINDANTES'] == ['info'])

# 3. Referencia de inmueble (20 caracteres): se descarga la parcela (14)
sim.peticiones.clear()
d20 = servicios.descargar(sim.RC + '0001' + 'XX', colindantes=False, construcciones=False)
d18 = servicios.descargar(sim.RC + '0001', colindantes=False, construcciones=False)
inmueble = ('RC' in codigos(d20.incidencias) and d18.correcta and d18.rc == sim.RC and len(sim.peticiones) == 1
            and d18.colindantes is None and d18.construcciones is None)

# 4. Parcela en otro huso: se vuelve a pedir en el suyo y todo lo demás en ese huso
sim.peticiones.clear()
d29 = servicios.descargar(sim.RC_HUSO_29, construcciones=False)
huso = (d29.correcta and d29.epsg == 25829 and d29.parcela.epsg == 25829 and len(sim.peticiones) == 3
        and 'EPSG%3A%3A25830' in sim.peticiones[0] and all('EPSG%3A%3A25829' in u for u in sim.peticiones[1:])
        and abs(d29.parcela.elementos[0].geometria.area() - 600) < 5)
d_fijo = servicios.descargar(sim.RC_HUSO_29, colindantes=False, construcciones=False, epsg=25830)
huso_fijo = d_fijo.correcta and d_fijo.epsg == 25830

# 5. Errores: parcela inexistente, RC no válida, foral, sin red
no_existe = servicios.descargar('1907499VK4810H')
sim.peticiones.clear()
mal = servicios.descargar('1907401VK48')
foral = servicios.descargar('31001A00100001')
sin_peticiones = not sim.peticiones
sin_red = servicios.descargar(sim.RC_SIN_RED)
errores = (not no_existe.correcta and codigos(no_existe.incidencias) == ['WFS-EXCEPCION']
           and 'No se ha encontrado la parcela 1907499VK4810H' in no_existe.incidencias[0].mensaje
           and not mal.correcta and codigos(mal.incidencias) == ['RC']
           and not foral.correcta and codigos(foral.incidencias) == ['RC-FORAL'] and 'Navarra' in foral.incidencias[0].mensaje
           and sin_peticiones and codigos(sin_red.incidencias) == ['RED'] and 'not found' in sin_red.incidencias[0].mensaje)
excepcion = (servicios.excepcion_wfs(sim.EXCEPCION.format(rc='X', huso=25830).encode('latin-1'))
             == 'No se ha encontrado la parcela X para el huso 25830' and servicios.excepcion_wfs(b'<a/>') == '')

# 6. Referencia catastral de un punto
p = servicios.rc_en_punto(-3.7085, 40.4207)
p_vacio = servicios.rc_en_punto(3.0, 40.0)
punto = (p.rc == sim.RC and p.direccion.startswith('CL INVENTADA') and not p.incidencias
         and not p_vacio.rc and codigos(p_vacio.incidencias) == ['RCCOOR-SIN-PARCELA']
         and p_vacio.incidencias[0].mensaje.startswith('Para esas coordenadas no hay referencia disponible')
         and 'Navarra' in p_vacio.incidencias[0].mensaje)

# 7. Servicio real (si hay internet): una parcela, sin colindantes ni construcciones; no se guarda nada
servicios.pedir = original
real = servicios.descargar('9872023VH5797S', colindantes=False, construcciones=False)
if 'RED' in codigos(real.incidencias):
    modo = "sin conexión: no se ha probado el servicio real"
    real_ok = True
else:
    e = real.parcela.elementos[0] if real.parcela and real.parcela.elementos else None
    real_ok = (real.correcta and real.epsg == 25830 and e is not None and e.local_id == '9872023VH5797S'
               and (e.area_declarada or 0) > 0 and real.parcela.version == 'CP 4.0')
    modo = "con conexión: servicio real comprobado"

checks = {
    "direcciones https de los servicios (WFS CP, WFS BU y RCCOOR)": direcciones,
    "descarga la parcela con su superficie y el huso 30": completa,
    "colindantes (tocan la parcela) y entorno (a menos de 25 m), por geometría": colindantes,
    "dominio público (parcela 9000 de rústica): tipo propio y nota de que linda": dominio,
    "sin colindantes: nota informativa, no aviso (parcela grande: GetNeighbourParcel)": sin_colindantes,
    "edificios y otras construcciones juntos": construcciones,
    "cita de la fuente con la fecha de descarga": atribucion,
    "resumen de lo descargado": resumen_ok,
    "RC de inmueble: descarga su parcela; sin opciones, solo la parcela": inmueble,
    "parcela de otro huso: se vuelve a pedir en el suyo": huso,
    "con un EPSG indicado no se cambia de huso": huso_fijo,
    "errores: inexistente, RC no válida, foral (sin pedir nada) y sin red": errores,
    "lee el ExceptionReport del WFS": excepcion,
    "referencia catastral de un punto (y sin parcela, con aviso foral)": punto,
    f"servicio real ({modo})": real_ok,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· servicios del Catastro")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'incidencias': [str(i) for i in d.incidencias], 'peticiones': sim.peticiones,
                        'huso29': [str(i) for i in d29.incidencias], 'epsg29': d29.epsg,
                        'real': [str(i) for i in real.incidencias], 'punto': [str(i) for i in p_vacio.incidencias],
                        'resumen': resumen})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
