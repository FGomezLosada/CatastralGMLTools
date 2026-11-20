"""
Apartados numerados e índice de los informes HTML (superficies, comparación de dos GML y validación).

Petición del 20/11/2026 (propuesta C elegida): cada apartado (<h2>) lleva su número en una etiqueta del color del
informe, el título en mayúsculas y una línea gruesa debajo; al principio, un índice con enlaces a cada apartado. Se
aplica sobre el HTML ya generado, así los tres informes quedan iguales sin repetir el estilo en cada uno.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import re

MINIMO_INDICE = 3  #Con menos apartados el índice no aporta

ESTILO = """
  nav.indice { border:1px solid var(--linea); border-radius:8px; padding:10px 16px; background:var(--suave);
               margin:16px 0 8px; font-size:.93em; }
  nav.indice b { display:block; margin-bottom:4px; color:var(--acento); }
  nav.indice a { color:var(--acento); text-decoration:none; margin-right:18px; white-space:nowrap; }
  nav.indice a:hover { text-decoration:underline; }
  h2.apartado { border-bottom:3px solid var(--acento); padding-bottom:6px; margin-top:40px; text-transform:uppercase;
                letter-spacing:.6px; font-size:1.02em; }
  h2.apartado .num { color:#fff; background:var(--acento); padding:1px 8px; border-radius:4px; margin-right:10px; }
  @media print { h2.apartado { break-after:avoid; } }
"""

_H2 = re.compile(r'<h2>(.*?)</h2>', re.S)


def numerar(texto):
    """El HTML de un informe con sus <h2> numerados, el índice antes del primero y el estilo en su <style>."""
    titulos = [m.group(1) for m in _H2.finditer(texto)]
    if not titulos:
        return texto
    contador = iter(range(1, len(titulos) + 1))

    def apartado(m):
        n = next(contador)
        return f'<h2 id="apartado-{n}" class="apartado"><span class="num">{n}</span>{m.group(1)}</h2>'

    numerado = _H2.sub(apartado, texto)
    if len(titulos) >= MINIMO_INDICE:
        enlaces = ''.join(f'<a href="#apartado-{n}">{n}. {re.sub(r"<[^>]+>", "", t).strip()}</a>'
                          for n, t in enumerate(titulos, 1))
        indice = f'<nav class="indice"><b>Contenido</b>{enlaces}</nav>\n'
        posicion = numerado.find('<h2 id="apartado-1"')
        numerado = numerado[:posicion] + indice + numerado[posicion:]
    return numerado.replace('</style>', ESTILO + '</style>', 1)
