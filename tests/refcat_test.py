"""
Prueba de core/refcat.py: limpieza, formato urbano/rústico, caracteres de control y territorios forales. Sin internet.

Las RC de 20 caracteres "correctas" son referencias publicadas como ejemplo o consultadas una vez en los servicios
libres del Catastro (solo el identificador, sin ningún otro dato) para comprobar el cálculo con casos reales.

Uso: tools\\probar.bat (o tools\\run_tests.py refcat_test.py)
"""
from qgis.core import Qgis

from catastral_gml_tools.core import refcat

reales = ['9872023VH5797S0001WX', '2749704YJ0624N0001DI', '29053A001000090000IR', '29075A013000080000EG',
          '29075A013000080001RH']
r_espacios = refcat.comprobar(' 9872023 vh5797s-0001 wx ')
r_mal = refcat.comprobar('9872023VH5797S0001WQ')
r_14u = refcat.comprobar('1907401VK4810H')
r_14r = refcat.comprobar('29053A00100009')
r_18 = refcat.comprobar('9872023VH5797S0001')
r_corta = refcat.comprobar('1907401VK4810')
r_simbolo = refcat.comprobar('1907401VK4810H#')
r_vacia = refcat.comprobar(None)
r_rara = refcat.comprobar('ABCDEFGHIJKLMN')
r_navarra = refcat.comprobar('31201A00100001')
r_bizkaia = refcat.comprobar('48020A00100001')

dominio = (refcat.es_dominio_publico('29075A90009700') and refcat.es_dominio_publico('29071A007 09001')
           and not refcat.es_dominio_publico('29071A00700123') and not refcat.es_dominio_publico('9872023VH5797S')
           and not refcat.es_dominio_publico('29071A00708999') and not refcat.es_dominio_publico('29071A00709000')
           and refcat.es_dominio_publico('03099A04809010') and not refcat.es_dominio_publico(''))
navarra = (refcat.navarra('201-4-112') == '201040112' and refcat.navarra('201040112') == '201040112'
           and refcat.navarra('201/04/0112') == '201040112' and refcat.navarra('73 2 577') == '073020577'
           and refcat.navarra('0-1-1') == '' and refcat.navarra('9872023VH5797S') == '' and refcat.navarra('') == ''
           and refcat.navarra_partes('201040112') == (201, 4, 112))
checks = {
    "Navarra: municipio-polígono-parcela y sus 9 dígitos": navarra,
    "dominio público de rústica (parcelas 9001-9999; la 9000 no)": dominio,
    "las RC reales tienen los caracteres de control correctos": all(refcat.comprobar(rc).nivel == refcat.CORRECTA for rc in reales),
    "limpia espacios, guiones y minúsculas": r_espacios.rc == '9872023VH5797S0001WX' and r_espacios.valida,
    "detecta caracteres de control erróneos y dice los buenos": r_mal.nivel == refcat.ERROR and 'WX' in r_mal.mensaje,
    "parcela urbana de 14": r_14u.nivel == refcat.CORRECTA and r_14u.tipo == 'urbana' and r_14u.parcela == '1907401VK4810H',
    "parcela rústica de 14 con provincia y municipio": r_14r.tipo == 'rústica' and r_14r.provincia == '29'
        and r_14r.municipio == '053',
    "RC de 18: calcula los caracteres que faltan": r_18.valida and 'WX' in r_18.mensaje,
    "longitud incorrecta": r_corta.nivel == refcat.ERROR and '13' in r_corta.mensaje,
    "caracteres no válidos": r_simbolo.nivel == refcat.ERROR,
    "vacía": r_vacia.nivel == refcat.ERROR,
    "formato no habitual: aviso, no error": r_rara.nivel == refcat.AVISO and r_rara.valida,
    "Navarra y País Vasco: aviso de catastro propio": r_navarra.nivel == refcat.AVISO and r_navarra.foral == 'Navarra'
        and r_bizkaia.foral == 'Bizkaia',
    "es_rc_parcela solo para 14 caracteres con formato": refcat.es_rc_parcela('1907401VK4810H')
        and not refcat.es_rc_parcela('Seg_1') and not refcat.es_rc_parcela('9872023VH5797S0001WX'),
}

print("=" * 60)
print("QGIS", Qgis.version(), "· referencias catastrales")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
