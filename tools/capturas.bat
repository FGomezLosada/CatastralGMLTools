@echo off
rem Rehace las capturas de la ayuda (help\img\*.png) con QGIS 3.40, la letra de Windows y datos sintéticos.
rem Uso: doble clic, o desde CMD en la carpeta del proyecto:  tools\capturas.bat
cd /d "%~dp0.."
set QT_QPA_PLATFORM=windows
rem A doble resolución: en la ayuda se ven nítidas (también en pantallas de alta densidad)
set QT_SCALE_FACTOR=2
call "C:\Program Files\QGIS 3.40.13\bin\python-qgis-ltr.bat" tools\run_tests.py --una capturas_ayuda.py
if not defined PB_SIN_PAUSA pause
