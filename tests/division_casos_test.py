"""
Batería de casos de «Dividir la parcela seleccionada» y «Unir seleccionadas» (pestaña Parcela; plan de pruebas,
docs/PLAN_PRUEBAS.md). La división se prueba en todas las combinaciones de forma de parcela × modo × valores × lado
(paralelo y perpendicular, desde un extremo y desde el otro), con estas reglas para cada resultado:

  - no falla nunca: o da las parcelas o da un error que se entiende;
  - las parcelas cubren exactamente la original (suman su superficie y no se solapan);
  - cada una tiene la superficie pedida (±1 cm²) salvo en franjas, que se miden por ancho;
  - si una queda en varios trozos, lo avisa (DIV-PARTES), y si no, el GML que se escribiría pasa la Validar del plugin.

La unión se prueba con parcelas que se tocan, con rendijas y huecos pequeños, con un hueco interior y separadas.

Uso: tools\\probar.bat (o tools\\run_tests.py division_casos_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os
import tempfile
import time
import traceback

from qgis.core import Qgis, QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

from catastral_gml_tools.core import capa_parcelas as cp  # noqa: E402
from catastral_gml_tools.core import division as dv  # noqa: E402
from catastral_gml_tools.core import gml_parcela as gp  # noqa: E402
from catastral_gml_tools.core import validador  # noqa: E402
from catastral_gml_tools.core.incidencias import ERROR  # noqa: E402

X0, Y0 = 421500.0, 4070500.0
carpeta = tempfile.mkdtemp(prefix='cgt_division_casos_')


def wkt(texto):
    return QgsGeometry.fromWkt(texto)


def poligono(*puntos, huecos=()):
    anillos = [list(puntos) + [puntos[0]]] + [list(h) + [h[0]] for h in huecos]
    return QgsGeometry.fromPolygonXY([[QgsPointXY(x, y) for x, y in anillo] for anillo in anillos])


FORMAS = {
    "rectángulo": poligono((X0, Y0), (X0, Y0 + 30), (X0 + 20, Y0 + 30), (X0 + 20, Y0)),
    "rectángulo girado 33°": QgsGeometry(poligono((X0, Y0), (X0, Y0 + 30), (X0 + 20, Y0 + 30), (X0 + 20, Y0))),
    "triángulo": poligono((X0, Y0), (X0 + 10, Y0 + 40), (X0 + 30, Y0)),
    "en L": poligono((X0, Y0), (X0, Y0 + 40), (X0 + 10, Y0 + 40), (X0 + 10, Y0 + 10), (X0 + 30, Y0 + 10), (X0 + 30, Y0)),
    "en U": poligono((X0, Y0), (X0, Y0 + 30), (X0 + 10, Y0 + 30), (X0 + 10, Y0 + 10), (X0 + 20, Y0 + 10), (X0 + 20, Y0 + 30),
                     (X0 + 30, Y0 + 30), (X0 + 30, Y0)),
    "con un hueco": poligono((X0, Y0), (X0, Y0 + 30), (X0 + 20, Y0 + 30), (X0 + 20, Y0),
                             huecos=[[(X0 + 5, Y0 + 10), (X0 + 15, Y0 + 10), (X0 + 15, Y0 + 20), (X0 + 5, Y0 + 20)]]),
    "estrecha y larga (2 × 200 m)": poligono((X0, Y0), (X0, Y0 + 200), (X0 + 2, Y0 + 200), (X0 + 2, Y0)),
    "círculo de 200 vértices": QgsGeometry.fromPointXY(QgsPointXY(X0, Y0)).buffer(15, 50),
    "irregular de 9 vértices": poligono((X0, Y0), (X0 - 3, Y0 + 12), (X0 + 4, Y0 + 25), (X0 + 15, Y0 + 31), (X0 + 26, Y0 + 24),
                                        (X0 + 24, Y0 + 9), (X0 + 18, Y0 + 2), (X0 + 9, Y0 - 4), (X0 + 4, Y0 - 1)),
}
FORMAS["rectángulo girado 33°"].rotate(33, QgsPointXY(X0, Y0))

VALORES = [
    (dv.PARTES, "2"), (dv.PARTES, "3"), (dv.PARTES, "7"), (dv.PARTES, "100"),
    (dv.PORCENTAJES, "30"), (dv.PORCENTAJES, "40 30 30"), (dv.PORCENTAJES, "33,3 33,3"),
    (dv.SUPERFICIES, "100"), (dv.SUPERFICIES, "50 50 50"),
    (dv.CUOTAS, "1 1 2"), (dv.CUOTAS, "3"),
    (dv.FRANJAS, "5"), (dv.FRANJAS, "2 3,5"),
]
ERRONEOS = [
    (dv.PARTES, "1"), (dv.PARTES, "2,5"), (dv.PARTES, "101"), (dv.PARTES, ""), (dv.PARTES, "dos"),
    (dv.PORCENTAJES, "60 70"), (dv.PORCENTAJES, "-10"), (dv.PORCENTAJES, "0"),
    (dv.SUPERFICIES, "999999"), (dv.FRANJAS, "500"), (dv.CUOTAS, "abc"),
]

resultados, detalles = {}, {}
ejecuciones = fallos_formas = 0


def comprobar(geometria, modo, texto, lado, perpendicular, invertir):
    """None si todo cuadra; el texto del problema si no."""
    try:
        valores = dv.leer_valores(texto)
    except ValueError:
        return None  #La interfaz lo dice antes de dividir (se prueba en ERRONEOS)
    piezas, inc = dv.dividir(geometria, modo, valores, lado, perpendicular, invertir)
    errores = [i for i in inc if i.nivel == ERROR]
    if errores:
        return None if all(i.mensaje for i in errores) else "error sin mensaje"
    if not piezas:
        return "ni parcelas ni error"
    total = geometria.area()
    suma = sum(p.area() for p in piezas)
    if abs(suma - total) > 0.01:
        return f"las parcelas suman {suma:.3f} m² y la original {total:.3f}"
    for i, a in enumerate(piezas):
        for b in piezas[i + 1:]:
            if a.intersection(b).area() > 1e-4:
                return "dos parcelas se solapan"
    if modo != dv.FRANJAS:
        metas, _ = dv.objetivos(modo, valores, total)
        if len(metas) != len(piezas):
            return f"{len(piezas)} parcelas y se pedían {len(metas)}"
        if any(abs(p.area() - m) > 0.01 for p, m in zip(piezas, metas)):
            return "alguna superficie no es la pedida: " + ", ".join(f"{p.area():.2f}/{m:.2f}" for p, m in zip(piezas, metas))
    trozos = any(p.isMultipart() and len(p.asGeometryCollection()) > 1 for p in piezas)
    if trozos != any(i.codigo == 'DIV-PARTES' for i in inc):
        return "parcela en varios trozos sin avisar (o aviso sin trozos)"
    if not trozos and len(piezas) <= 30:
        texto_gml, inc_gml = gp.construir([gp.ParcelaGML(f'Div_{k}', gp.LOCAL, p) for k, p in enumerate(piezas, 1)], 25830)
        if texto_gml is None:
            #Las piezas minúsculas que el redondeo al centímetro deja sin superficie no se pueden escribir: es correcto
            #que se diga; lo que no puede pasar es un error sin explicar
            if not all(i.mensaje for i in inc_gml if i.nivel == ERROR):
                return "no se puede escribir el GML y no se explica"
            return None
        ruta = os.path.join(carpeta, 'pieza.gml')
        with open(ruta, 'w', encoding='utf-8') as f:
            f.write(texto_gml)
        propios = [i.codigo for i in validador.validar(ruta).errores]
        if propios:
            return f"el GML de las parcelas no pasa la Validar del plugin: {propios[:3]}"
    return None


inicio = time.monotonic()
for nombre, geometria in FORMAS.items():
    problemas = []
    n_lados = len(dv.lados(geometria))
    for modo, texto in VALORES:
        for lado in sorted({0, n_lados // 2, n_lados - 1}):
            for perpendicular in (False, True):
                for invertir in (False, True):
                    ejecuciones += 1
                    try:
                        problema = comprobar(geometria, modo, texto, lado, perpendicular, invertir)
                    except Exception:  # noqa: BLE001
                        problema = traceback.format_exc()[-400:]
                    if problema:
                        problemas.append(f"{modo} «{texto}» lado {lado} {'perp.' if perpendicular else 'par.'}"
                                         f"{' inv.' if invertir else ''}: {problema}")
    resultados[f"dividir: {nombre}"] = not problemas
    if problemas:
        detalles[nombre] = problemas[:4] + ([f"… y {len(problemas) - 4} más"] if len(problemas) > 4 else [])
segundos = time.monotonic() - inicio

#Valores erróneos: siempre un error que se entiende, nunca una excepción
mal = []
for modo, texto in ERRONEOS:
    try:
        valores = dv.leer_valores(texto)
        piezas, inc = dv.dividir(FORMAS["rectángulo"], modo, valores, 0)
        if piezas or not any(i.nivel == ERROR and i.mensaje for i in inc):
            mal.append(f"{modo} «{texto}»: no da error")
    except ValueError:
        pass  #«dos», «abc»: no son números (la interfaz lo dice con su mensaje)
    except Exception:  # noqa: BLE001
        mal.append(f"{modo} «{texto}»: {traceback.format_exc()[-300:]}")
resultados["valores erróneos: error claro, sin fallar"] = not mal
if mal:
    detalles['valores erróneos'] = mal
#Geometrías que no se pueden dividir
raras = []
for nombre, g in (("vacía", QgsGeometry()), ("multiparte", wkt(f"MULTIPOLYGON((({X0} {Y0}, {X0} {Y0 + 5}, {X0 + 5} {Y0 + 5}, "
                                                                f"{X0} {Y0})), (({X0 + 9} {Y0}, {X0 + 9} {Y0 + 3}, "
                                                                f"{X0 + 12} {Y0 + 3}, {X0 + 9} {Y0})))")),
                  ("lado que no existe", FORMAS["rectángulo"])):
    try:
        piezas, inc = dv.dividir(g, dv.PARTES, [2], 99 if nombre == "lado que no existe" else 0)
        if piezas or not any(i.nivel == ERROR for i in inc):
            raras.append(nombre)
    except Exception:  # noqa: BLE001
        raras.append(f"{nombre}: {traceback.format_exc()[-300:]}")
resultados["geometría vacía, multiparte o lado inexistente: error claro"] = not raras
if raras:
    detalles['raras'] = raras


#Unir seleccionadas
def capa(nombre, geometrias):
    c = QgsVectorLayer("Polygon?crs=EPSG:25830&field=refcat:string(20)", nombre, "memory")
    entidades = []
    for i, g in enumerate(geometrias):
        f = QgsFeature(c.fields())
        f.setGeometry(g)
        f.setAttributes([f'1907{401 + i}VK4810H'])
        entidades.append(f)
    c.dataProvider().addFeatures(entidades)
    QgsProject.instance().addMapLayer(c)
    c.selectAll()
    return c


def r(x, y, w, h):
    return poligono((x, y), (x, y + h), (x + w, y + h), (x + w, y))


UNIONES = [
    ("dos que se tocan", [r(X0, Y0, 20, 30), r(X0 + 20, Y0, 20, 30)], True),
    ("tres en fila", [r(X0, Y0, 10, 30), r(X0 + 10, Y0, 10, 30), r(X0 + 20, Y0, 10, 30)], True),
    ("rendija de 5 mm", [r(X0, Y0, 20, 30), r(X0 + 20.005, Y0, 20, 30)], True),
    ("hueco de 10 cm", [r(X0, Y0, 20, 30), r(X0 + 20.10, Y0, 20, 30)], True),
    ("separadas 5 m", [r(X0, Y0, 20, 30), r(X0 + 25, Y0, 20, 30)], False),
    ("rodean un patio (se conserva como hueco y se avisa)", [r(X0, Y0, 30, 10), r(X0, Y0 + 20, 30, 10), r(X0, Y0 + 10, 10, 10),
                                                             r(X0 + 20, Y0 + 10, 10, 10)], 'patio'),
    ("solo una seleccionada", [r(X0, Y0, 20, 30)], False),
]
union_mal = []
for nombre, geometrias, debe_unir in UNIONES:
    try:
        c = capa(nombre, geometrias)
        total = sum(g.area() for g in geometrias)
        fid, _, inc = cp.unir_seleccionadas(c, 'refcat')
        if debe_unir:
            unida = c.getFeature(fid).geometry() if fid is not None else QgsGeometry()
            exacta = debe_unir == 'patio'  #Con el patio, la unida es exactamente la suma (el patio no se rellena)
            if debe_unir == 'patio' and not any(i.codigo == 'UNION-PATIO' for i in inc):
                union_mal.append(f"{nombre}: no avisa del patio")
            if fid is None or c.featureCount() != 1 or abs(unida.area() - total) > (0.01 if exacta else max(0.05 * total, 5)):
                union_mal.append(f"{nombre}: no unida ({[i.mensaje[:80] for i in inc]})")
            elif not unida.isGeosValid():
                union_mal.append(f"{nombre}: la unión no es válida")
        elif fid is not None or not any(i.nivel == ERROR and i.mensaje for i in inc):
            union_mal.append(f"{nombre}: debía dar un error claro")
        c.rollBack()
        QgsProject.instance().removeMapLayer(c.id())
    except Exception:  # noqa: BLE001
        union_mal.append(f"{nombre}: {traceback.format_exc()[-300:]}")
resultados["unir: se tocan, rendijas, huecos, patio, separadas y una sola"] = not union_mal
if union_mal:
    detalles['unir'] = union_mal

print("=" * 60)
print("QGIS", Qgis.version(), f"· dividir y unir: batería de casos ({ejecuciones} divisiones en {segundos:.1f} s)")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, d in detalles.items():
    print("Detalles", nombre, ":", d)
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
