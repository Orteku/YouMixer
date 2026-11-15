@echo off
chcp 65001 >nul
title YouMixer
cd /d "%~dp0"

rem La primera vez instala; despues solo arranca
if not exist ".venv\installed.ok" goto install
fc /b requirements.txt ".venv\installed.ok" >nul 2>nul || goto install
goto run

:install
call Install.bat /auto || exit /b 1

:run

rem Arranca sin ventana; se apaga con el boton Apagar de la pagina. Los errores quedan en data\youmixer.log
start "" ".venv\Scripts\pythonw.exe" server.py
exit /b
