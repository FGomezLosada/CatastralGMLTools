"""
Gráficos SVG para los informes HTML (superficies, comparación de dos GML, identidad gráfica), sin librerías: el SVG va
dentro del HTML, se imprime bien y se ve igual en cualquier navegador y en QGIS 3 y 4. Cada marca lleva su <title>
(al pasar el ratón se lee el valor exacto). Los colores de las parcelas son los del croquis (la misma parcela, el mismo
color); los de estado (dentro / fuera de la tolerancia) van siempre con texto, nunca solo el color.

Petición del 19/11/2026: «gráficos en los informes, por si mejoran algo» (ideas, no código, de otro plugin GPL-3).

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
from html import escape

ANCHO = 720
TEXTO = 'currentColor'
SUAVE = '#868e96'
REJILLA = '#dee2e6'
BIEN = '#2b8a3e'
FUERA = '#c92a2a'
NEUTRO = '#1f6f78'
#Halo del color del fondo: la etiqueta se lee aunque pase por encima una barra o la línea
HALO = 'style="paint-order:stroke;stroke:var(--fondo,#fff);stroke-width:4px;stroke-linejoin:round"'


def _num(valor, decimales=2):
    #Como el panel: punto de miles y coma decimal (petición del 20/11/2026)
    return f"{valor:,.{decimales}f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def _svg(alto, contenido, titulo):
    return (f'<svg class="grafico" viewBox="0 0 {ANCHO} {alto}" role="img" aria-label="{escape(titulo)}" '
            f'xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI, Arial, sans-serif" font-size="13">'
            f'{contenido}</svg>')


def _paso(maximo, divisiones=5):
    """Paso «redondo» (1, 2 o 5 × 10^n) para unas 5 marcas del eje."""
    if maximo <= 0:
        return 1
    bruto = maximo / divisiones
    potencia = 1.0
    while potencia * 10 <= bruto:
        potencia *= 10
    while potencia > bruto:
        potencia /= 10
    for m in (1, 2, 5, 10):
        if m * potencia >= bruto:
            return m * potencia
    return 10 * potencia


def reparto(partes, total_texto='m²'):
    """
    Barra única con el reparto de la superficie entre las parcelas del GML (partes de un todo). partes: [(nombre, m²,
    color)]. Debajo, la leyenda con superficie y porcentaje de cada una. Con una sola parcela no aporta nada: ''.
    """
    partes = [p for p in partes if p[1] > 0]
    if len(partes) < 2:
        return ''
    total = sum(p[1] for p in partes)
    x0, ancho, y0, alto = 16, ANCHO - 32, 28, 34
    marcas, x = [], x0
    for nombre, area, color in partes:
        w = ancho * area / total
        porcentaje = 100 * area / total
        marcas.append(f'<rect x="{x:.1f}" y="{y0}" width="{max(w - 2, 0.5):.1f}" height="{alto}" rx="4" fill="{color}">'
                      f'<title>{escape(nombre)}: {_num(area)} {total_texto} ({_num(porcentaje, 1)} %)</title></rect>')
        if w > 54:  #Porcentaje dentro de la barra solo si cabe
            marcas.append(f'<text x="{x + w / 2:.1f}" y="{y0 + alto / 2 + 4:.1f}" text-anchor="middle" fill="#fff" '
                          f'font-weight="600">{_num(porcentaje, 1)} %</text>')
        x += w
    filas = (len(partes) + 1) // 2
    leyenda = []
    for i, (nombre, area, color) in enumerate(partes):
        cx = x0 + (i % 2) * (ancho / 2)
        cy = y0 + alto + 26 + (i // 2) * 22
        leyenda.append(f'<rect x="{cx:.1f}" y="{cy - 10}" width="12" height="12" rx="2" fill="{color}"/>'
                       f'<text x="{cx + 18:.1f}" y="{cy}" fill="{TEXTO}">{escape(nombre)} · {_num(area)} {total_texto} '
                       f'({_num(100 * area / total, 1)} %)</text>')
    titulo = f'<text x="{x0}" y="16" fill="{TEXTO}" font-weight="600">Reparto de {_num(total)} {total_texto} entre {len(partes)} parcelas</text>'
    return _svg(y0 + alto + 20 + filas * 22, titulo + ''.join(marcas) + ''.join(leyenda),
                f"Reparto de la superficie entre {len(partes)} parcelas")


def cabida(superficie, inscrita, umbrales=(5, 10)):
    """
    La superficie del GML frente a la cabida inscrita, con las bandas de ±5 % y ±10 % de la inscrita (de más clara a
    más oscura según se aleja). Se lee de un vistazo si está dentro de cada umbral.
    """
    if not inscrita or inscrita <= 0:
        return ''
    limite = max(max(umbrales) * 1.6, abs(superficie - inscrita) / inscrita * 100 * 1.25)
    lo, hi = inscrita * (1 - limite / 100), inscrita * (1 + limite / 100)
    x0, ancho = 16, ANCHO - 32

    def X(v):
        return x0 + (v - lo) / (hi - lo) * ancho

    y0, alto = 34, 30
    partes = [f'<rect x="{x0}" y="{y0}" width="{ancho}" height="{alto}" fill="{REJILLA}" opacity=".45"/>']
    for umbral, opacidad in zip(sorted(umbrales, reverse=True), (.55, .9)):
        a, b = X(inscrita * (1 - umbral / 100)), X(inscrita * (1 + umbral / 100))
        partes.append(f'<rect x="{a:.1f}" y="{y0}" width="{b - a:.1f}" height="{alto}" fill="{REJILLA}" opacity="{opacidad}">'
                      f'<title>±{umbral} % de la inscrita: {_num(inscrita * (1 - umbral / 100))} a '
                      f'{_num(inscrita * (1 + umbral / 100))} m²</title></rect>')
        for v, signo in ((inscrita * (1 - umbral / 100), '−'), (inscrita * (1 + umbral / 100), '+')):
            partes.append(f'<text x="{X(v):.1f}" y="{y0 + alto + 14}" text-anchor="middle" fill="{SUAVE}" '
                          f'font-size="11">{signo}{umbral} %</text>')
    xi = X(inscrita)
    partes.append(f'<line x1="{xi:.1f}" x2="{xi:.1f}" y1="{y0 - 4}" y2="{y0 + alto + 4}" stroke="{TEXTO}" stroke-width="2"/>'
                  f'<text x="{xi:.1f}" y="{y0 - 8}" text-anchor="middle" fill="{TEXTO}" font-size="11">Inscrita '
                  f'{_num(inscrita)} m²</text>')
    porcentaje = 100 * (superficie - inscrita) / inscrita
    dentro = abs(porcentaje) <= max(umbrales)
    color = BIEN if dentro else FUERA
    xs = X(superficie)
    partes.append(f'<circle cx="{xs:.1f}" cy="{y0 + alto / 2}" r="7" fill="{color}" stroke="#fff" stroke-width="2">'
                  f'<title>GML: {_num(superficie)} m² ({"+" if porcentaje >= 0 else "−"}{_num(abs(porcentaje), 2)} %)</title>'
                  f'</circle>')
    ancla = 'end' if xs > x0 + ancho * .75 else 'start'
    dx = -12 if ancla == 'end' else 12
    partes.append(f'<text x="{xs + dx:.1f}" y="{y0 + alto / 2 - 10:.1f}" text-anchor="{ancla}" fill="{TEXTO}" '
                  f'font-weight="600">GML {_num(superficie)} m² ({"+" if porcentaje >= 0 else "−"}'
                  f'{_num(abs(porcentaje), 2)} %)</text>')
    return _svg(y0 + alto + 24, ''.join(partes), "Superficie del GML frente a la cabida inscrita")


def barras_vertices(valores, tolerancia, unidad='cm', titulo='Desplazamiento de cada vértice', nombre_tolerancia=''):
    """
    Una barra por vértice (valores: [(etiqueta, valor)]) con la línea de la tolerancia: las que la pasan, en rojo y con
    su valor encima. Para la comparación de dos GML (±1 cm) o cualquier separación por vértice.
    """
    if not valores:
        return ''
    n = len(valores)
    maximo = max(max(v for _, v in valores), tolerancia * 1.5)
    paso = _paso(maximo)
    tope = paso * (int(maximo / paso) + 1)
    x0, y0, alto = 48, 30, 150
    ancho = ANCHO - x0 - 16
    hueco = ancho / n
    w = max(min(hueco * .7, 28), 1.5)

    def Y(v):
        return y0 + alto - v / tope * alto

    partes = [f'<text x="16" y="16" fill="{TEXTO}" font-weight="600">{escape(titulo)}</text>']
    v = 0.0
    while v <= tope + 1e-9:
        partes.append(f'<line x1="{x0}" x2="{x0 + ancho}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{REJILLA}"/>'
                      f'<text x="{x0 - 6}" y="{Y(v) + 4:.1f}" text-anchor="end" fill="{SUAVE}" font-size="11">'
                      f'{_num(v, 0 if paso >= 1 else 1)}</text>')
        v += paso
    fuera = 0
    for i, (etiqueta, valor) in enumerate(valores):
        x = x0 + i * hueco + (hueco - w) / 2
        pasa = valor > tolerancia
        fuera += pasa
        color = FUERA if pasa else NEUTRO
        partes.append(f'<rect x="{x:.1f}" y="{Y(valor):.1f}" width="{w:.1f}" height="{max(Y(0) - Y(valor), 0.5):.1f}" '
                      f'rx="{min(3, w / 3):.1f}" fill="{color}"><title>Vértice {escape(str(etiqueta))}: '
                      f'{_num(valor)} {unidad}{" (fuera de la tolerancia)" if pasa else ""}</title></rect>')
        if n <= 40:
            partes.append(f'<text x="{x + w / 2:.1f}" y="{y0 + alto + 14}" text-anchor="middle" fill="{SUAVE}" '
                          f'font-size="10">{escape(str(etiqueta))}</text>')
        if pasa and n <= 25:
            partes.append(f'<text x="{x + w / 2:.1f}" y="{Y(valor) - 4:.1f}" text-anchor="middle" fill="{TEXTO}" '
                          f'font-size="10">{_num(valor, 1)}</text>')
    yt = Y(tolerancia)
    partes.append(f'<line x1="{x0}" x2="{x0 + ancho}" y1="{yt:.1f}" y2="{yt:.1f}" stroke="{FUERA}" stroke-width="1.5" '
                  f'stroke-dasharray="6 4"/><text x="{x0 + 6}" y="{yt - 5:.1f}" fill="{FUERA}" {HALO} '
                  f'font-size="11">{escape(nombre_tolerancia or f"Tolerancia {_num(tolerancia, 0)} {unidad}")}</text>')
    resumen = (f"{fuera} de {n} vértices pasan la tolerancia" if fuera else f"Los {n} vértices, dentro de la tolerancia")
    partes.append(f'<text x="{x0}" y="{y0 + alto + 34}" fill="{FUERA if fuera else BIEN}" font-weight="600">'
                  f'{"✖" if fuera else "✔"} {resumen}</text>')
    return _svg(y0 + alto + 44, ''.join(partes), titulo)


def perfil(muestras, margen, longitud, titulo='Separación del contorno respecto al perímetro catastral'):
    """
    Separación del contorno del GML respecto al perímetro catastral a lo largo del contorno (muestras: [(distancia
    recorrida en m, separación en m)]), con la línea del margen de identidad (±0,50 m urbana, ±2,00 m rústica): lo que
    pasa del margen, en rojo. Dice dónde y cuánto se sale.
    """
    if not muestras or longitud <= 0:
        return ''
    maximo = max(max(s for _, s in muestras), margen * 1.4)
    paso = _paso(maximo, 4)
    tope = paso * (int(maximo / paso) + 1)
    x0, y0, alto = 48, 30, 140
    ancho = ANCHO - x0 - 16

    def X(d):
        return x0 + d / longitud * ancho

    def Y(s):
        return y0 + alto - s / tope * alto

    partes = [f'<text x="16" y="16" fill="{TEXTO}" font-weight="600">{escape(titulo)}</text>']
    v = 0.0
    while v <= tope + 1e-9:
        partes.append(f'<line x1="{x0}" x2="{x0 + ancho}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{REJILLA}"/>'
                      f'<text x="{x0 - 6}" y="{Y(v) + 4:.1f}" text-anchor="end" fill="{SUAVE}" font-size="11">'
                      f'{_num(v, 2 if paso < 0.1 else 1 if paso < 1 else 0)}</text>')
        v += paso
    puntos = ' '.join(f'{X(d):.1f},{Y(s):.1f}' for d, s in muestras)
    area = f'{X(muestras[0][0]):.1f},{Y(0):.1f} {puntos} {X(muestras[-1][0]):.1f},{Y(0):.1f}'
    partes.append(f'<polygon points="{area}" fill="{NEUTRO}" opacity=".15"/>')
    partes.append(f'<polyline points="{puntos}" fill="none" stroke="{NEUTRO}" stroke-width="2"/>')
    #Tramos fuera del margen, en rojo encima
    tramo = []
    for d, s in muestras + [(None, 0)]:
        if d is not None and s > margen:
            tramo.append((d, s))
        elif tramo:
            pts = ' '.join(f'{X(a):.1f},{Y(b):.1f}' for a, b in tramo)
            peor = max(tramo, key=lambda t: t[1])
            partes.append(f'<polyline points="{pts}" fill="none" stroke="{FUERA}" stroke-width="3">'
                          f'<title>Fuera del margen de {_num(tramo[0][0], 1)} a {_num(tramo[-1][0], 1)} m del contorno; '
                          f'hasta {_num(peor[1])} m</title></polyline>')
            partes.append(f'<text x="{X(peor[0]):.1f}" y="{Y(peor[1]) - 6:.1f}" text-anchor="middle" fill="{TEXTO}" '
                          f'font-size="11">{_num(peor[1])} m</text>')
            tramo = []
    ym = Y(margen)
    partes.append(f'<line x1="{x0}" x2="{x0 + ancho}" y1="{ym:.1f}" y2="{ym:.1f}" stroke="{FUERA}" stroke-width="1.5" '
                  f'stroke-dasharray="6 4"/><text x="{x0 + 6}" y="{ym - 5:.1f}" fill="{FUERA}" {HALO} '
                  f'font-size="11">Margen ±{_num(margen)} m</text>')
    for d in (0, longitud / 4, longitud / 2, 3 * longitud / 4, longitud):
        partes.append(f'<text x="{X(d):.1f}" y="{y0 + alto + 14}" text-anchor="middle" fill="{SUAVE}" font-size="11">'
                      f'{_num(d, 0)} m</text>')
    partes.append(f'<text x="{x0 + ancho / 2}" y="{y0 + alto + 30}" text-anchor="middle" fill="{SUAVE}" font-size="11">'
                  'recorrido a lo largo del contorno, desde el vértice 1</text>')
    return _svg(y0 + alto + 40, ''.join(partes), titulo)
