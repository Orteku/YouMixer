@echo off
chcp 65001 >nul
title Install YouMixer
cd /d "%~dp0"
rem Con /auto (desde YouMixer.bat) no se para al final

echo Instalando YouMixer para este usuario de Windows, sin permisos de administrador...
echo Installing YouMixer for this Windows user, no administrator rights needed...
where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo No encuentro Python. Instalalo desde https://www.python.org/downloads/ y vuelve a abrir esto.
  echo Python not found. Install it from https://www.python.org/downloads/ and run this again.
  pause
  exit /b 1
)
echo  - Preparando Python / Setting up Python...
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" install.py install
if errorlevel 1 goto failed
copy /y requirements.txt ".venv\installed.ok" >nul

echo.
echo YouMixer esta instalado. Abrelo desde el menu Inicio o con YouMixer.bat.
echo YouMixer is installed. Open it from the Start menu or with YouMixer.bat.
if /i not "%~1"=="/auto" pause
exit /b 0

:failed
echo.
echo No se pudo instalar YouMixer. Revisa tu conexion y vuelve a intentarlo.
echo YouMixer could not be installed. Check your connection and try again.
pause
exit /b 1
