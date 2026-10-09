"""
Parcelas a partir de una capa de QGIS: lee los polígonos, propone identificador, namespace y label,
y los convierte en ParcelaGML en el SRC del fichero. Sin interfaz.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
from dataclasses import dataclass

from qgis.core import Qgis, QgsGeometry, QgsWkbTypes

from . import geometria as geo
from . import refcat
from .gml_parcela import LOCAL, SDGC, ParcelaGML, label_por_defecto


@dataclass
class FilaParcela:
    """Una parcela de la capa tal como se muestra en la tabla del panel (el usuario puede cambiar id, namespace y label)."""
    fid: int
    local_id: str
    namespace: str
    label: str
    geometria: QgsGeometry  #En el SRC de la capa
    partes: int = 1


def es_capa_poligonos(capa):
    return (capa is not None and capa.isValid() and hasattr(capa, 'geometryType')
            and capa.geometryType() == Qgis.GeometryType.Polygon)


def _texto(valor):
    """Valor de un campo como texto; los nulos de QGIS (NULL, QVariant nulo) como cadena vacía."""
    if valor is None:
        return ''
    if hasattr(valor, 'isNull') and valor.isNull():
        return ''
    texto = str(valor).strip()
    return '' if texto.upper() == 'NULL' else texto


def namespace_propuesto(local_id):
    """SDGC si el identificador es una referencia catastral de parcela; LOCAL en otro caso."""
    return SDGC if refcat.es_rc_parcela(local_id) else LOCAL


def leer_capa(capa, solo_seleccion=False, campo_id='', campo_label=''):
    """
    Filas de la tabla a partir de los polígonos de la capa.
    Identificador: el valor del campo elegido (limpio si es una RC) o, si está vacío, «Parcela_N».
    """
    filas = []
    if not es_capa_poligonos(capa):
        return filas
    entidades = capa.getSelectedFeatures() if solo_seleccion else capa.getFeatures()
    leidas = []
    for n, entidad in enumerate(entidades, start=1):
        geometria = QgsGeometry(entidad.geometry())
        valor = _texto(entidad[campo_id]) if campo_id else ''
        local_id = refcat.limpiar(valor) if refcat.es_rc_parcela(valor) else valor.replace(' ', '_')
        label = _texto(entidad[campo_label]) if campo_label else ''
        leidas.append([entidad.id(), local_id or f"Parcela_{n}", label, geometria])

    #Identificadores repetidos (lo normal tras dividir una parcela: todos los trozos copian su referencia).
    #Si es una referencia catastral, la conserva el trozo mayor y los demás se proponen como parcelas nuevas con un nombre
    #neutro (Nueva_1, Nueva_2…): no se presupone el tipo de alteración (segregación, división…), que decide el usuario
    #y, para la Sede, el número de parcelas y sus namespaces. Si no es una RC, se numeran id_2, id_3…
    grupos = {}
    for fila in leidas:
        grupos.setdefault(fila[1], []).append(fila)
    usados = {fila[1] for fila in leidas}
    nuevas = 0
    for local_id, grupo in grupos.items():
        if len(grupo) < 2:
            continue
        grupo.sort(key=lambda f: f[3].area() if not f[3].isNull() else 0, reverse=True)
        for k, fila in enumerate(grupo[1:], start=2):
            if refcat.es_rc_parcela(local_id):
                nuevas += 1
                nuevo = f"Nueva_{nuevas}"
            else:
                nuevo = f"{local_id}_{k}"
            while nuevo in usados:
                nuevo += '_b'
            usados.add(nuevo)
            fila[1] = nuevo

    for fid, local_id, label, geometria in leidas:
        namespace = namespace_propuesto(local_id)
        partes = 0 if geometria.isNull() else len(geometria.asGeometryCollection()) if geometria.isMultipart() else 1
        filas.append(FilaParcela(fid, local_id, namespace, label or label_por_defecto(local_id, namespace),
                                 geometria, partes))
    return filas


def epsg_para(filas, crs):
    """SRC recomendado para el fichero: el de la capa si lo admite la Sede; si no, el huso según la posición."""
    epsg = geo.epsg_de(crs)
    if epsg in geo.SRC_ADMITIDOS:
        return epsg
    geometrias = [f.geometria for f in filas if f.geometria is not None and not f.geometria.isNull()]
    if not geometrias:
        return None
    return geo.epsg_recomendado(QgsGeometry.unaryUnion(geometrias), crs)


def area_m2(fila, crs, epsg):
    """
    Superficie que tendrá la parcela en el GML (m² en el SRC del fichero), o None si no se puede calcular.
    Se calcula igual que en el GML: con las coordenadas ya redondeadas al centímetro (por eso puede diferir en 1 m²
    de la superficie de la geometría original).
    """
    if fila.geometria is None or fila.geometria.isNull() or epsg is None:
        return None
    recintos, _ = geo.preparar(geo.transformar(fila.geometria, crs, epsg))
    if not recintos:
        return None
    return sum(r.area_m2() for r in recintos)


def a_parcelas_gml(filas, crs, epsg):
    """ParcelaGML con la geometría transformada al EPSG del fichero."""
    return [ParcelaGML(f.local_id, f.namespace, geo.transformar(f.geometria, crs, epsg), f.label)
            for f in filas]


def unir_seleccionadas(capa, campo_id=''):
    """
    Une en una sola parcela los polígonos seleccionados de la capa (agregación o agrupación). Edita la capa dentro de
    un comando de edición (se puede deshacer con Ctrl+Z y no se guarda hasta que el usuario guarde la capa): la parcela
    mayor recibe la geometría unida y conserva sus atributos; las demás se borran.
    Devuelve (fid de la parcela resultante o None, tipo de alteración propuesto, incidencias).
    """
    from . import alteraciones as alt
    from .incidencias import ERROR, INFO, Incidencia

    if not es_capa_poligonos(capa):
        return None, '', [Incidencia(ERROR, 'UNION-CAPA', "Elija una capa de polígonos")]
    seleccion = list(capa.getSelectedFeatures())
    if len(seleccion) < 2:
        return None, '', [Incidencia(ERROR, 'UNION-POCAS', "Seleccione en el mapa dos parcelas o más")]
    geometrias = [QgsGeometry(f.geometry()) for f in seleccion]
    union = QgsGeometry.unaryUnion(geometrias)
    if union.isEmpty() or (union.isMultipart() and len(union.asGeometryCollection()) > 1):
        return None, '', [Incidencia(ERROR, 'UNION-NO-COLINDANTES', "Las parcelas seleccionadas no forman un solo recinto: "
                                                                    "para unirlas han de ser colindantes")]
    principal = max(seleccion, key=lambda f: f.geometry().area())
    if QgsWkbTypes.isMultiType(capa.wkbType()):  #Capa de multipolígonos: la geometría debe ser del mismo tipo
        union.convertToMultiType()
    if not capa.isEditable():
        capa.startEditing()
    capa.beginEditCommand("Unir parcelas (Catastral GML Tools)")
    ok = capa.changeGeometry(principal.id(), union)
    ok = capa.deleteFeatures([f.id() for f in seleccion if f.id() != principal.id()]) and ok
    if not ok:
        capa.destroyEditCommand()
        return None, '', [Incidencia(ERROR, 'UNION-EDICION', "La capa no permite editar sus parcelas")]
    capa.endEditCommand()
    capa.selectByIds([principal.id()])

    total = union.area()
    id_principal = _texto(principal[campo_id]) if campo_id else ''
    con_rc = refcat.es_rc_parcela(id_principal)
    proporcion = principal.geometry().area() / total if total else 0
    tipo = alt.AGREGACION if con_rc and proporcion >= 0.8 else alt.AGRUPACION
    incidencias = [Incidencia(INFO, 'UNION-HECHA', f"Unidas {len(seleccion)} parcelas en una de {round(total)} m²; la mayor "
                                                   f"({round(100 * proporcion)} % del total) conserva sus datos")]
    if con_rc and tipo == alt.AGRUPACION:
        incidencias.append(Incidencia(INFO, 'UNION-AGRUPACION', "La mayor no llega al 80 % del total: se propone agrupación "
                                                                "(parcela nueva). Si conserva su referencia, elija agregación"))
    return principal.id(), tipo, incidencias
