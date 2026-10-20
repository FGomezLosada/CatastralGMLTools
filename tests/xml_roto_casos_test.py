"""
Batería de XML rotos (plan de pruebas, docs/PLAN_PRUEBAS.md; prueba a mano del 20/10/2026): un GML de parcela y uno de
edificio se rompen de todas las formas posibles —se quita cada carácter, uno a uno; se mete un «<», «>», «&», «"» o
«/» en muchos sitios; se cortan por cualquier punto; se cambia la codificación— y el plugin no sabe qué se ha hecho.

Reglas de cada fichero roto:
  - leerlo y validarlo nunca lanza una excepción;
  - si no es XML: un mensaje en castellano (sin el texto del lector en inglés), con la línea y la columna, el texto de
    ese punto marcado con ▶, y sin afirmar qué se ha borrado (no se puede saber);
  - el punto señalado no está antes del cambio (hasta ahí el fichero era correcto);
  - si sigue siendo XML (p. ej. se ha quitado una cifra), Validar lo revisa sin fallar.

Uso: tools\\probar.bat (o tools\\run_tests.py xml_roto_casos_test.py)

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import os
import re
import tempfile
import time
import traceback

from qgis.core import Qgis, QgsGeometry

from catastral_gml_tools.core import gml_lector as gl  # noqa: E402
from catastral_gml_tools.core import gml_parcela as gp  # noqa: E402
from catastral_gml_tools.core import validador  # noqa: E402
from catastral_gml_tools.core.info import RAIZ  # noqa: E402

X0, Y0 = 421500.0, 4070500.0
carpeta = tempfile.mkdtemp(prefix='cgt xml roto ñ_')
resultados, detalles = {}, {}


def caso(nombre, funcion):
    try:
        ok, detalle = funcion()
        resultados[nombre] = bool(ok)
        if not ok:
            detalles[nombre] = detalle
    except Exception:  # noqa: BLE001
        resultados[nombre] = False
        detalles[nombre] = traceback.format_exc()[-900:]


#Texto del lector XML que no debe llegar al usuario, y suposiciones que el plugin no puede hacer
INGLES = re.compile(r'\b(tag|expected|found|line \d|column \d|attribute|document|not well|token|element|mismatch|'
                    r'premature|unbound|prefix \w+ on|Extra content|parsing)\b', re.IGNORECASE)
SUPOSICIONES = ('se ha borrado', 'ha borrado', 'falta el primer', '¿')


def rect(x, y, a, b):
    return QgsGeometry.fromWkt(f"POLYGON(({x} {y}, {x} {y + b}, {x + a} {y + b}, {x + a} {y}, {x} {y}))")


texto, _ = gp.construir([gp.ParcelaGML('1907401VK4810H', gp.SDGC, rect(X0, Y0, 20, 18), '01'),
                         gp.ParcelaGML('Seg_1', gp.LOCAL, rect(X0, Y0 + 18, 20, 12))], 25830)
PARCELA = texto.encode('utf-8')
with open(os.path.join(RAIZ, 'tests', 'data', 'gml', 'edificio_sintetico.gml'), 'rb') as _f:
    EDIFICIO = _f.read()  #ISO-8859-1, con acentos


def linea_de(datos, posicion):
    return datos[:posicion].count(b'\n') + 1


def revisar(datos, cambio, como):
    """Problemas de lo que dice el plugin de un fichero roto (lista vacía si todo bien)."""
    lectura = gl.leer_datos(datos)
    errores = [i for i in lectura.incidencias if i.nivel == 'error']
    xml = [i for i in errores if i.codigo == 'XML-MAL-FORMADO']
    if not xml:  #Sigue siendo XML: que Validar no falle con él
        ruta = os.path.join(carpeta, 'roto.gml')
        with open(ruta, 'wb') as f:
            f.write(datos)
        validador.validar(ruta, lectura)
        return []
    mensaje = xml[0].mensaje
    problemas = []
    if INGLES.search(mensaje.split('En ese punto:')[0]):
        problemas.append('inglés')
    if any(s in mensaje.split('En ese punto:')[0] for s in SUPOSICIONES):
        problemas.append('supone qué falta')
    if mensaje != "El fichero está vacío":
        m = re.search(r'\(línea (\d+), columna (\d+)\)', mensaje)
        if not m:
            problemas.append('sin línea ni columna')
        elif int(m.group(1)) < linea_de(datos, cambio):
            problemas.append(f'señala la línea {m.group(1)}, antes del cambio (línea {linea_de(datos, cambio)})')
        if '▶' not in mensaje:  #El texto de ese punto (o cómo termina, si está cortado)
            problemas.append('sin el texto del punto')
    return [f'{como}: {p} · {mensaje[:160]}' for p in problemas]


def bateria(nombre, datos, operaciones):
    def prueba():
        problemas, total = [], 0
        inicio = time.time()
        for posicion, roto, como in operaciones(datos):
            total += 1
            try:
                encontrados = revisar(roto, posicion, como)
            except Exception:  # noqa: BLE001
                encontrados = [f'{como}: excepción {traceback.format_exc()[-300:]}']
            problemas += encontrados
        return not problemas, (f'{len(problemas)} de {total} ({round(time.time() - inicio)} s)', problemas[:6])
    return prueba


def quitar_cada(datos):
    for i in range(len(datos)):
        yield i, datos[:i] + datos[i + 1:], f'sin el carácter {i} ({datos[i:i + 1]!r})'


def meter(datos):
    for i in range(0, len(datos), 5):
        for c in (b'<', b'>', b'&', b'"', b'/'):
            yield i, datos[:i] + c + datos[i:], f'{c.decode()} en {i}'


def cortar(datos):
    for i in range(1, len(datos), 17):
        yield i, datos[:i], f'cortado en {i}'


def codificacion(datos):
    for enc in (b'tf-8', b'utf8x', b'', b'latin-9', b'UTF-16'):
        roto = re.sub(rb'encoding="[^"]*"', b'encoding="' + enc + b'"', datos, count=1)
        yield 0, roto, f'encoding="{enc.decode()}"'
    yield 0, b'\xff\xfe' + datos, 'con marca UTF-16 delante'
    yield 0, datos.replace(b'</cp:label>', '</cp:label>é'.encode('latin-1'), 1), 'una é en latin-1 en un UTF-8'


caso("parcela: sin cada uno de sus caracteres", bateria('quitar', PARCELA, quitar_cada))
caso("parcela: «<», «>», «&», «\"» o «/» de más", bateria('meter', PARCELA, meter))
caso("parcela: cortada por cualquier sitio", bateria('cortar', PARCELA, cortar))
caso("parcela: codificación equivocada", bateria('codificacion', PARCELA, codificacion))
caso("edificio (ISO-8859-1): sin cada uno de sus caracteres", bateria('quitar', EDIFICIO, quitar_cada))
caso("edificio: cortado por cualquier sitio", bateria('cortar', EDIFICIO, cortar))


def ejemplos():
    """Lo que se lee en los casos de la prueba a mano: dice lo que encuentra y dónde, sin suponer."""
    sin_menor = gl.leer_datos(PARCELA[1:]).incidencias[0].mensaje
    etiqueta = gl.leer_datos(PARCELA.replace(b'<cp:label>', b'<cp:label', 1)).incidencias[0].mensaje
    cierre = gl.leer_datos(PARCELA.replace(b'</cp:label>', b'</cp:labe>', 1)).incidencias[0].mensaje
    ok = ('no empieza por una etiqueta XML' in sin_menor and 'cp:label' in etiqueta and '▶' in etiqueta
          and 'se cierra con </labe>' in cierre and ',' not in cierre.split('se cierra con')[1][:8])
    return ok, (sin_menor, etiqueta, cierre)


caso("los mensajes de la prueba a mano: qué encuentra y dónde", ejemplos)


def coordenada():
    """Sin una cifra o sin el punto en una coordenada, sigue siendo XML: Validar dice qué vértice ha quedado lejos."""
    ruta = os.path.join(carpeta, 'coordenada.gml')
    vistos = []
    for original, mal in ((b'421520.00', b'42152000'), (b'4070518.00', b'40705180'), (b'421520.00', b'42520.00')):
        with open(ruta, 'wb') as f:
            f.write(PARCELA.replace(original, mal, 1))
        informe = validador.validar(ruta)
        vistos.append([i.mensaje for i in informe.incidencias if i.codigo == 'GEO-VERTICE-LEJANO'])
    return all(v and 'compruebe que esa coordenada' in v[0] for v in vistos), vistos


caso("coordenada mal tecleada (sin una cifra o sin el punto): dice qué vértice", coordenada)

print("=" * 60)
print("QGIS", Qgis.version(), "· XML rotos: batería de casos")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, d in detalles.items():
    print("Detalles", nombre, ":", d)
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
