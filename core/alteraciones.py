"""
Asistente de alteraciones (mejora 15): según el tipo de alteración que elige el usuario, propone el identificador y el
namespace de cada parcela del GML y comprueba que encajan con lo que espera la Sede.

Tabla NPO/NPP/namespace del documento de validación de la DGC (docs/INVESTIGACION.md §7.1):
  segregación  1 parcela → varias; la matriz conserva su referencia (1 SDGC), las segregadas son LOCAL
  división     1 parcela → varias; todas nuevas (0 SDGC)
  agregación   varias → 1; conserva la referencia de la parcela principal (SDGC)
  agrupación   varias → 1; parcela nueva (LOCAL)
  subsanación  las mismas parcelas, con sus referencias (todas SDGC)
Criterios orientativos del editor de la Sede (Reglamento Hipotecario), solo como nota: segregada menor del 20 % de la
matriz; en la división, cada resultante mayor que 1/5 de la original.

Sin interfaz: trabaja con listas de identificadores, namespaces y superficies.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import re

from . import refcat
from .gml_parcela import LOCAL, SDGC
from .incidencias import AVISO, INFO, Incidencia

SIN_INDICAR = ''
SEGREGACION = 'segregación'
DIVISION = 'división'
AGREGACION = 'agregación'
AGRUPACION = 'agrupación'
SUBSANACION = 'subsanación'
TIPOS = (SIN_INDICAR, SEGREGACION, DIVISION, AGREGACION, AGRUPACION, SUBSANACION)
NOMBRES = {SIN_INDICAR: "Sin indicar", SEGREGACION: "Segregación", DIVISION: "División", AGREGACION: "Agregación",
           AGRUPACION: "Agrupación", SUBSANACION: "Subsanación de discrepancias"}
AYUDA = {
    SIN_INDICAR: "El plugin no cambia identificadores ni namespaces: la Sede deducirá la operación",
    SEGREGACION: "De una parcela salen varias: la mayor conserva la referencia catastral (SDGC) y las demás son nuevas "
                 "(LOCAL, Seg_1, Seg_2…)",
    DIVISION: "Una parcela se divide en varias nuevas: todas LOCAL (Div_1, Div_2…), ninguna conserva la referencia",
    AGREGACION: "Varias parcelas se unen a una principal, que conserva su referencia catastral (SDGC)",
    AGRUPACION: "Varias parcelas forman una nueva (LOCAL, Agrupa_1)",
    SUBSANACION: "Corrección de linderos: las mismas parcelas, cada una con su referencia catastral (SDGC)",
}
PREFIJO = {SEGREGACION: 'Seg_', DIVISION: 'Div_', AGRUPACION: 'Agrupa_'}
#Nombres que pone el plugin (se pueden cambiar sin pisar los del usuario)
AUTOMATICO = re.compile(r'^(Nueva|Parcela|Seg|Div|Agrupa)_\d+$')
UMBRAL_SEGREGACION = 0.20  #Segregada menor del 20 % de la matriz (editor de la Sede)
UMBRAL_DIVISION = 0.20     #Cada resultante mayor que 1/5 de la original (editor de la Sede)


def es_automatico(local_id):
    return bool(AUTOMATICO.match(local_id or ''))


def _rc(ids):
    """Primera referencia catastral de parcela entre los identificadores (la de la parcela original), o ''."""
    return next((refcat.limpiar(i) for i in ids if refcat.es_rc_parcela(i)), '')


def _mayor(areas):
    validas = [(a or 0, i) for i, a in enumerate(areas)]
    return max(validas)[1] if validas else 0


def proponer(tipo, ids, areas, rc=''):
    """
    Identificadores y namespaces propuestos para el tipo de alteración: lista de (local_id, namespace) en el mismo orden.
    Los identificadores que ha escrito el usuario (que no son referencias ni nombres automáticos) se respetan.
    rc: referencia de la parcela original si se conoce (la tabla puede haberla perdido al pasar por una división).
    """
    ids = list(ids)
    if tipo == SIN_INDICAR or not ids:
        return [(i, SDGC if refcat.es_rc_parcela(i) else LOCAL) for i in ids]
    rc = _rc(ids) or (refcat.limpiar(rc) if refcat.es_rc_parcela(rc) else '')

    def nuevo(i, n):
        actual = ids[i]
        return actual if actual and not refcat.es_rc_parcela(actual) and not es_automatico(actual) else f"{PREFIJO[tipo]}{n}"

    if tipo == SEGREGACION:
        matriz = _mayor(areas)
        resultado, n = [], 0
        for i in range(len(ids)):
            if i == matriz and rc:
                resultado.append((rc, SDGC))
            else:
                n += 1
                resultado.append((nuevo(i, n), LOCAL))
        return resultado
    if tipo == DIVISION:
        return [(nuevo(i, i + 1), LOCAL) for i in range(len(ids))]
    if tipo == AGREGACION:
        return [(rc, SDGC) if rc else (ids[i], LOCAL) for i in range(len(ids))]
    if tipo == AGRUPACION:
        return [(nuevo(i, i + 1), LOCAL) for i in range(len(ids))]
    if tipo == SUBSANACION:
        return [(refcat.limpiar(i), SDGC) if refcat.es_rc_parcela(i) else (i, LOCAL) for i in ids]
    return [(i, SDGC if refcat.es_rc_parcela(i) else LOCAL) for i in ids]


def _pct(parte, total):
    return f"{100 * parte / total:.0f} %" if total else '?'


def comprobar(tipo, ids, namespaces, areas):
    """
    Avisos si la tabla no encaja con el tipo de alteración elegido y notas con los criterios orientativos de superficie.
    Las superficies son las de las parcelas resultantes (m², None si no se conocen).
    """
    inc = []
    n = len(ids)
    if tipo == SIN_INDICAR or not n:
        return inc
    sdgc = [i for i, ns in zip(ids, namespaces) if ns == SDGC]
    total = sum(a or 0 for a in areas)
    nombre = NOMBRES[tipo]
    if tipo in (SEGREGACION, DIVISION) and n < 2:
        inc.append(Incidencia(AVISO, 'ALT-NPP', f"{nombre}: el GML debe tener dos parcelas o más (tiene {n})"))
    if tipo in (AGREGACION, AGRUPACION) and n != 1:
        inc.append(Incidencia(AVISO, 'ALT-NPP', f"{nombre}: el resultado es una sola parcela (hay {n}); una primero los "
                                                "polígonos en la capa"))
    if tipo in (SEGREGACION, AGREGACION) and len(sdgc) != 1:
        inc.append(Incidencia(AVISO, 'ALT-SDGC', f"{nombre}: debe haber una parcela con la referencia catastral original "
                                                 f"(SDGC) y hay {len(sdgc)}"))
    if tipo in (DIVISION, AGRUPACION) and sdgc:
        inc.append(Incidencia(AVISO, 'ALT-SDGC', f"{nombre}: todas las parcelas son nuevas (LOCAL); {', '.join(sdgc)} "
                                                 "lleva SDGC"))
    if tipo == SUBSANACION and len(sdgc) != n:
        inc.append(Incidencia(AVISO, 'ALT-SDGC', f"{nombre}: todas las parcelas deben llevar su referencia catastral (SDGC); "
                                                 f"{n - len(sdgc)} no la llevan"))
    if not total:
        return inc
    if tipo == SEGREGACION and n >= 2:
        segregada = sum(a or 0 for a, ns in zip(areas, namespaces) if ns == LOCAL)
        if segregada >= UMBRAL_SEGREGACION * total:
            inc.append(Incidencia(INFO, 'ALT-UMBRAL', f"Se segrega el {_pct(segregada, total)} de la finca: según el criterio "
                                                      "orientativo del editor de la Sede (menos del 20 %) se parecería más "
                                                      "a una división. La Sede la valida igual por el número de parcelas y "
                                                      "sus namespaces"))
    if tipo == DIVISION and n >= 2:
        pequenas = [i for i, a in zip(ids, areas) if (a or 0) <= UMBRAL_DIVISION * total]
        if pequenas:
            inc.append(Incidencia(INFO, 'ALT-UMBRAL', f"{', '.join(pequenas)}: menos de 1/5 de la finca original; según el "
                                                      "criterio orientativo del editor de la Sede se parecería más a una "
                                                      "segregación"))
    return inc


def resumen(tipo, ids, namespaces, areas):
    """Una línea con la operación y el reparto de superficies (para el panel)."""
    if tipo == SIN_INDICAR or not ids:
        return ''
    total = sum(a or 0 for a in areas)
    partes = [f"{i} {round(a or 0)} m²" + (f" ({_pct(a or 0, total)})" if total and len(ids) > 1 else '')
              for i, a in zip(ids, areas)]
    sdgc = sum(1 for ns in namespaces if ns == SDGC)
    return f"{NOMBRES[tipo]} · {len(ids)} parcela{'s' if len(ids) != 1 else ''} ({sdgc} SDGC) · " + ' · '.join(partes)
