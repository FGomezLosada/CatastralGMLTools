"""
Escaneo de seguridad del ZIP del plugin, como el del repositorio oficial de QGIS (plugins.qgis.org, desde el
23/04/2026): Bandit y detect-secrets bloquean la publicación con hallazgos críticos; flake8 y el análisis de ficheros
son informativos (https://plugins.qgis.org/docs/security-scanning/tools). Auditoría AU-60.

Uso (con bandit, detect-secrets y flake8 instalados: pip install bandit detect-secrets flake8):
    python tools/escanear.py

Genera el ZIP con tools/package.py, lo descomprime en una carpeta temporal y pasa las tres herramientas sobre lo que
de verdad se publica. Termina con error si Bandit o detect-secrets encuentran algo, o si hay ficheros que no deben ir
(binarios, scripts .bat/.sh, ocultos salvo la configuración de flake8). Lo usa la Action de publicación.

copyright : (C) 2026 by Francisco Gómez Losada
license   : GNU GPL v2 or later
"""
import json
import os
import shutil
import subprocess  # nosec B404
import sys
import tempfile
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROHIBIDAS = ('.exe', '.dll', '.so', '.dylib', '.pyc', '.pyd', '.bat', '.cmd', '.sh', '.ps1', '.jar')
OCULTOS_ADMITIDOS = ('.flake8',)


def ejecutar(orden, carpeta):
    """Lanza una herramienta (lista de argumentos, sin shell) y devuelve (código, salida estándar, errores)."""
    if shutil.which(orden[0]) is None:
        sys.exit(f"Falta {orden[0]}: pip install bandit detect-secrets flake8")
    proceso = subprocess.run(orden, cwd=carpeta, capture_output=True, text=True)  # nosec B603
    return proceso.returncode, proceso.stdout, proceso.stderr


def main():
    subprocess.run([sys.executable, os.path.join(RAIZ, 'tools', 'package.py')], check=True)  # nosec B603
    zips = sorted(f for f in os.listdir(os.path.join(RAIZ, 'dist')) if f.endswith('.zip'))
    zip_ = os.path.join(RAIZ, 'dist', zips[-1])
    problemas = []
    with tempfile.TemporaryDirectory() as temporal:
        with zipfile.ZipFile(zip_) as z:
            z.extractall(temporal)
        plugin = os.path.join(temporal, 'catastral_gml_tools')
        #Ficheros que no deben ir en el ZIP
        for actual, _, nombres in os.walk(plugin):
            for nombre in nombres:
                relativa = os.path.relpath(os.path.join(actual, nombre), plugin)
                if nombre.lower().endswith(PROHIBIDAS):
                    problemas.append(f"Fichero que no debe publicarse: {relativa}")
                elif nombre.startswith('.') and nombre not in OCULTOS_ADMITIDOS:
                    problemas.append(f"Fichero oculto: {relativa}")
        codigo, salida, errores = ejecutar(['bandit', '-r', '.', '-q', '-f', 'json'], plugin)
        hallazgos = json.loads(salida[salida.index('{'):]).get('results', []) if '{' in salida else []
        for h in hallazgos:
            problemas.append(f"Bandit {h['test_id']} ({h['issue_severity']}): {h['filename']}:{h['line_number']} "
                             f"{h['issue_text']}")
        if codigo not in (0, 1) and not hallazgos:
            problemas.append(f"Bandit no ha podido terminar: {errores[-500:]}")
        codigo, salida, errores = ejecutar(['detect-secrets', 'scan', '.'], plugin)
        secretos = json.loads(salida).get('results', {}) if codigo == 0 else {}
        for fichero, lista in secretos.items():
            for s in lista:
                problemas.append(f"detect-secrets: {s['type']} en {fichero}:{s['line_number']}")
        if codigo != 0:
            problemas.append(f"detect-secrets no ha podido terminar: {errores[-500:]}")
        _, salida, _ = ejecutar(['flake8', '.'], plugin)  #Informativo, con el .flake8 del ZIP
        estilo = [linea for linea in salida.splitlines() if linea.strip()]
    print(f"ZIP escaneado: {zip_}")
    print(f"flake8 (informativo): {len(estilo)} avisos" + (''.join(f"\n  {e}" for e in estilo[:20]) if estilo else ''))
    if problemas:
        print("PROBLEMAS (bloquean la publicación):\n  " + "\n  ".join(problemas))
        sys.exit(1)
    print("Bandit y detect-secrets: sin hallazgos. Ficheros del ZIP: correctos.")


if __name__ == '__main__':
    main()
