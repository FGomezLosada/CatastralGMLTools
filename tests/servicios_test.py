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
            and parcela.area_declarada == 600 and len(sim.peticiones) == 5
            and sum('Consulta_DNPRC' in u for u in sim.peticiones) == 1)
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
           and camino[0].descripcion == 'Camino · Vía de comunicación de dominio público'
           and [e.tipo for e in d.colindantes.elementos if e.local_id != sim.CAMINO] == ['parcela']
           and any(i.codigo == 'LINDA-DOMINIO-PUBLICO' and sim.CAMINO in i.mensaje and i.nivel == 'info'
                   for i in d.incidencias))

# Sin poder consultar los datos de la DGC: se aplica la numeración y se dice que no está confirmado
sim.DNPRC_CAIDO = True
d_caido = servicios.descargar(sim.RC, construcciones=False)
sim.DNPRC_CAIDO = False
camino_caido = [e for e in d_caido.colindantes.elementos if e.local_id == sim.CAMINO]
dominio = (dominio and d_caido.correcta and camino_caido and camino_caido[0].tipo == 'dominio público'
           and 'sin confirmar' in camino_caido[0].descripcion)
datos_ok = (servicios.es_dominio_publico_segun({'texto': 'Parcela 9700 (BIEN DE DOMIIO PUBLICO)', 'cultivos': []})
            and servicios.es_dominio_publico_segun({'texto': '', 'cultivos': [('HG', 'HIDROGRAFÍA NATURAL')]})
            and not servicios.es_dominio_publico_segun({'texto': 'SIERRA', 'cultivos': [('MT', 'MATORRAL')]})
            and not servicios.es_dominio_publico_segun(None))
dominio = dominio and datos_ok

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

# 6b. Navarra: servicio INSPIRE del Gobierno de Navarra (sin pasar por la DGC ni por Consulta_DNPRC)
sim.peticiones.clear()
nav = servicios.descargar('201-4-112', ahora=ahora)
nav_ok = (nav.correcta and nav.territorio == 'Navarra' and nav.rc == sim.NAVARRA and nav.epsg == 25830
          and [e.local_id for e in nav.colindantes.elementos] == ['201040113']
          and [e.local_id for e in nav.entorno.elementos] == ['201040114']
          and [e.local_id for e in nav.construcciones.elementos] == ['201040112A']
          and 'Gobierno de Navarra' in nav.atribucion() and 'NAVARRA' in codigos(nav.incidencias)
          and all('inspire.navarra.es' in u for u in sim.peticiones)
          and 'ResourceId' in sim.peticiones[0])
nav_no = servicios.descargar('201-4-999')
nav_punto = servicios.rc_en_punto(-1.644, 42.817)
nav_ok = (nav_ok and not nav_no.correcta and 'No se ha encontrado la parcela 999 del polígono 4 de 201' in str(nav_no.incidencias)
          and nav_punto.rc == sim.NAVARRA and 'polígono 4, parcela 112' in nav_punto.direccion and not nav_punto.incidencias)

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

#Plantas: el WFS de la DGC deja vacías las del edificio y las da en sus partes (BuildingPart); se toma la máxima
PARTES = ('<?xml version="1.0" encoding="ISO-8859-1"?><gml:FeatureCollection xmlns:gml="http://www.opengis.net/gml/3.2" '
          'xmlns:bu-ext2d="http://inspire.jrc.ec.europa.eu/schemas/bu-ext2d/2.0" xmlns:bu-core2d="http://inspire.jrc.ec.europa.eu/schemas/bu-core2d/2.0" '
          'xmlns:base="urn:x-inspire:specification:gmlas:BaseTypes:3.2">{}</gml:FeatureCollection>')
PARTE = ('<gml:featureMember><bu-ext2d:BuildingPart gml:id="ES.SDGC.BU.X_part{n}"><bu-core2d:inspireId><base:Identifier>'
         '<base:localId>X_part{n}</base:localId></base:Identifier></bu-core2d:inspireId><bu-ext2d:geometry><gml:Polygon '
         'srsName="urn:ogc:def:crs:EPSG::25830"><gml:exterior><gml:LinearRing><gml:posList>{c}</gml:posList></gml:LinearRing>'
         '</gml:exterior></gml:Polygon></bu-ext2d:geometry><bu-ext2d:numberOfFloorsAboveGround>{p}</bu-ext2d:numberOfFloorsAboveGround>'
         '</bu-ext2d:BuildingPart></gml:featureMember>')
X0, Y0 = 421500, 4070500
cuadro = lambda x, y, a: f"{x} {y} {x} {y + a} {x + a} {y + a} {x + a} {y} {x} {y}"  # noqa: E731
from catastral_gml_tools.core import gml_lector as gl  # noqa: E402
from qgis.core import QgsGeometry  # noqa: E402
partes = gl.leer_partes(PARTES.format(PARTE.format(n=1, c=cuadro(X0, Y0, 5), p=1) + PARTE.format(n=2, c=cuadro(X0 + 5, Y0, 5), p=2)
                                      + PARTE.format(n=3, c=cuadro(X0 + 50, Y0, 5), p=7)).encode('latin-1'))
edificio = gl.ElementoGML(gl.EDIFICIO, 'X', 'ES.SDGC.BU', QgsGeometry.fromWkt(f"POLYGON(({X0} {Y0}, {X0 + 10} {Y0}, {X0 + 10} {Y0 + 5}, {X0} {Y0 + 5}, {X0} {Y0}))"))
servicios.plantas_de_partes([edificio], partes)
plantas_partes = [p.plantas for p in partes] == [1, 2, 7] and edificio.plantas == 2 and 'GetBuildingPartByParcel' in servicios.url_partes(sim.RC)

checks = {
    "plantas del edificio: la máxima de sus partes (BuildingPart)": plantas_partes,
    "direcciones https de los servicios (WFS CP, WFS BU y RCCOOR)": direcciones,
    "descarga la parcela con su superficie y el huso 30": completa,
    "colindantes (tocan la parcela) y entorno (a menos de 25 m), por geometría": colindantes,
    "dominio público confirmado con la DGC (o por numeración si no responde), tipo propio y nota": dominio,
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
    "Navarra: parcela, colindantes, entorno y edificios del Gobierno de Navarra; clic en Navarra": nav_ok,
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
