"""
Parcelas a partir de una capa de QGIS: lee los polígonos, propone identificador, namespace y label,
y los convierte en ParcelaGML en el SRC del fichero. Sin interfaz.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
from dataclasses import dataclass

from qgis.analysis import QgsGeometrySnapper
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


def src_incorrecto(capa):
    """
    Texto del problema si la capa no tiene SRC o si sus coordenadas no encajan con él (lo típico de un DXF en UTM que
    QGIS abre en un SRC geográfico); '' si está bien.
    """
    if capa is None:
        return ''
    crs = capa.crs()
    if not crs.isValid():
        return "La capa no tiene SRC: asígnelo en sus propiedades (pestaña Fuente)"
    extension = capa.extent()
    if crs.isGeographic() and not extension.isEmpty() and (abs(extension.xMaximum()) > 180 or abs(extension.yMaximum()) > 90):
        return (f"Las coordenadas de la capa no encajan con su SRC ({crs.authid()}): parecen UTM. Asigne el SRC correcto en "
                "sus propiedades (pestaña Fuente), p. ej. EPSG:25830")
    return ''


def aviso_huso(filas, crs, epsg, referencias=()):
    """Aviso de huso (geometria.aviso_huso) para las filas de una capa; la provincia sale de una RC de rústica si la hay."""
    geometrias = [f.geometria for f in filas if f.geometria is not None and not f.geometria.isNull()]
    if not geometrias or epsg is None:
        return None
    rusticas = [r for r in (refcat.parcela_de(x) for x in referencias) if refcat.tipo_parcela(r) == 'rústica']
    return geo.aviso_huso(QgsGeometry.unaryUnion(geometrias), crs, epsg, rusticas[0][:2] if rusticas else '')


def avisos_src(filas, crs, epsg, referencias=()):
    """Avisos del SRC de una capa que se va a pasar a un GML: datum antiguo (AU-32) y huso que no encaja (AU-30)."""
    avisos = [geo.aviso_datum(crs, epsg) if epsg else None, aviso_huso(filas, crs, epsg, referencias)]
    return [a for a in avisos if a is not None]


def fichero_de_capa(capa):
    """Ruta del fichero del que sale la capa ('' si es de memoria o de un servicio). Sirve para no sobrescribirlo (AU-09)."""
    if capa is None or capa.providerType() not in ('ogr', 'delimitedtext'):
        return ''
    return capa.source().split('|')[0]


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
        #Una RC (también en minúsculas, con guiones o de inmueble de 18/20) se normaliza a la de la parcela (AU-04, AU-05)
        local_id = refcat.parcela_de(valor) or valor.replace(' ', '_')
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


CIERRE_UNION = 0.01  #m: rendijas de digitalización entre parcelas que se cierran al unirlas


def _partes(geometria):
    return len(geometria.asGeometryCollection()) if geometria.isMultipart() else (0 if geometria.isEmpty() else 1)


def _rendijas(geometria):
    """True si la geometría tiene huecos interiores de menos de 1 cm de ancho (restos de digitalización)."""
    poligonos = geometria.asMultiPolygon() if geometria.isMultipart() else [geometria.asPolygon()]
    return any(geo.anchura_maxima(QgsGeometry.fromPolygonXY([anillo])) < CIERRE_UNION for p in poligonos for anillo in p[1:])


def _sin_rendijas(geometria):
    """Copia sin los huecos interiores de menos de 1 cm de ancho (los patios de verdad se conservan)."""
    poligonos = geometria.asMultiPolygon() if geometria.isMultipart() else [geometria.asPolygon()]
    limpios = [[p[0]] + [a for a in p[1:] if geo.anchura_maxima(QgsGeometry.fromPolygonXY([a])) >= CIERRE_UNION]
               for p in poligonos if p]
    if not limpios:
        return QgsGeometry()
    return QgsGeometry.fromPolygonXY(limpios[0]) if len(limpios) == 1 else QgsGeometry.fromMultiPolygonXY(limpios)


def unir_seleccionadas(capa, campo_id=''):
    """
    Une en una sola parcela los polígonos seleccionados de la capa (agregación o agrupación). Edita la capa dentro de
    un comando de edición (se puede deshacer con Ctrl+Z y no se guarda hasta que el usuario guarde la capa): la parcela
    mayor recibe la geometría unida y conserva sus atributos; las demás se borran.
    Devuelve (fid de la parcela resultante o None, tipo de alteración propuesto, incidencias).
    """
    from . import alteraciones as alt
    from .incidencias import AVISO, ERROR, INFO, Incidencia

    if not es_capa_poligonos(capa):
        return None, '', [Incidencia(ERROR, 'UNION-CAPA', "Elija una capa de polígonos")]
    seleccion = list(capa.getSelectedFeatures())
    if len(seleccion) < 2:
        return None, '', [Incidencia(ERROR, 'UNION-POCAS', "Seleccione en el mapa dos parcelas o más")]
    geometrias = [QgsGeometry(f.geometry()) for f in seleccion]
    original = QgsGeometry.unaryUnion(geometrias)
    #1. Rendijas de digitalización de menos de 1 cm: los vértices de cada parcela se ajustan a las demás (como el
    #autoensamblado de QGIS; AU-42). Siempre: también deja rendijas abiertas al borde, no solo huecos cerrados
    ajustadas = [QgsGeometrySnapper.snapGeometry(g, CIERRE_UNION, [h for k, h in enumerate(geometrias) if k != i])
                 for i, g in enumerate(geometrias)]
    union = _sin_rendijas(QgsGeometry.unaryUnion(ajustadas))
    if union.isEmpty() or _partes(union) > 1:  #El ajuste no basta para que se toquen: se prueba sin él
        union, ajustadas = original, geometrias
    rendijas = abs(union.area() - original.area()) if union is not original else 0.0
    #2. Huecos y cuñas de hasta 20 cm entre ellas (el dibujo no encaja): al unirlas desaparece el lindero común, así que
    #se rellenan y se avisa (si no, la parcela unida quedaba con un hueco o una grieta y su GML no era válido)
    union, rellenado = geo.rellenar_huecos(ajustadas) if len(ajustadas) > 1 else (union, 0.0)
    union = _sin_rendijas(union)
    if union.isEmpty() or _partes(union) > 1:
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
    #Solo es una agregación o agrupación si se unen parcelas catastrales distintas (dos referencias o más). Unir un
    #trozo dibujado (sin referencia, o con la misma que copió al dividir) es retocar el dibujo: no cambia la operación
    #(prueba a mano del 14/10/2026: unir el trozo de una segregación con una franja de vial proponía «Agrupación»)
    referencias = {refcat.parcela_de(_texto(f[campo_id])) for f in seleccion} - {''} if campo_id else set()
    if len(referencias) >= 2:
        tipo = alt.AGREGACION if con_rc and proporcion >= 0.8 else alt.AGRUPACION
    else:
        tipo = alt.SIN_INDICAR
    incidencias = [Incidencia(INFO, 'UNION-HECHA', f"Unidas {len(seleccion)} parcelas en una de {round(total)} m²; la mayor "
                                                   f"({round(100 * proporcion)} % del total) conserva sus datos")]
    if rellenado < 0.005:  #Rellenos de menos de 50 cm²: son rendijas de dibujo, no merecen un aviso
        rendijas, rellenado = rendijas + rellenado, 0.0
    if rendijas > 1e-6:
        incidencias.append(Incidencia(INFO, 'UNION-RENDIJAS', f"Se han cerrado rendijas de digitalización entre las parcelas "
                                                              f"({rendijas:.4f} m²)"))
    if rellenado:
        incidencias.append(Incidencia(AVISO, 'UNION-RELLENO', f"Las parcelas no encajaban: se han rellenado {rellenado:.2f} m² "
                                                              "de huecos o cuñas entre ellas. Compruebe en el mapa que la "
                                                              "parcela unida es la que quiere"))
    if not union.isGeosValid():
        incidencias.append(Incidencia(AVISO, 'UNION-INVALIDA', "La parcela unida no es una geometría válida (el dibujo tiene "
                                                               "huecos o picos de más de 20 cm entre las parcelas): revísela "
                                                               "antes de crear el GML"))
    if not tipo:
        incidencias.append(Incidencia(INFO, 'UNION-DIBUJO', "No son parcelas catastrales distintas: es un retoque del dibujo y "
                                                            "no cambia la operación"))
    elif con_rc and tipo == alt.AGRUPACION:
        incidencias.append(Incidencia(INFO, 'UNION-AGRUPACION', "La mayor no llega al 80 % del total: se propone agrupación "
                                                                "(parcela nueva). Si conserva su referencia, elija agregación"))
    elif tipo == alt.AGREGACION and proporcion < alt.UMBRAL_AGREGACION:
        incidencias.append(Incidencia(INFO, 'UNION-UMBRAL', "La mayor llega al 80 % de la guía del IVG, pero no al quíntuplo "
                                                            "de lo agregado del Reglamento Hipotecario (≈ 83 %): manda la "
                                                            "escritura"))
    return principal.id(), tipo, incidencias


def dividir_en_capa(capa, fid, piezas):
    """
    Sustituye la parcela fid por las piezas de una división (geometrías en el SRC de la capa), dentro de un comando de
    edición (Ctrl+Z lo deshace): la primera pieza se queda en la parcela original y las demás son parcelas nuevas con sus
    mismos datos (como «Dividir objetos» de QGIS), salvo la superficie, que se recalcula. Devuelve los fid en orden, o []
    si la capa no deja editar.
    """
    from qgis.core import QgsVectorLayerUtils

    original = capa.getFeature(fid)
    if not original.isValid() or not piezas:
        return []
    multi = QgsWkbTypes.isMultiType(capa.wkbType())
    geometrias = []
    for pieza in piezas:
        g = QgsGeometry(pieza)
        if multi:
            g.convertToMultiType()
        geometrias.append(g)
    sin_copiar = {capa.fields().indexOf(n) for n in ('sup_gml', 'sup_calc')} - {-1}  #Se recalculan o no valen ya
    atributos = {i: v for i, v in enumerate(original.attributes()) if i not in sin_copiar}
    if not capa.isEditable():
        capa.startEditing()
    capa.beginEditCommand("Dividir parcela (Catastral GML Tools)")
    ok = capa.changeGeometry(fid, geometrias[0])
    fids = [fid]
    for g in geometrias[1:]:
        nueva = QgsVectorLayerUtils.createFeature(capa, g, atributos)
        ok = capa.addFeature(nueva) and ok
        fids.append(nueva.id())
    if not ok:
        capa.destroyEditCommand()
        return []
    capa.endEditCommand()
    return fids
