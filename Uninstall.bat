@echo off
chcp 65001 >nul
title Uninstall YouMixer
cd /d "%~dp0"

echo Esto quita YouMixer de Windows: el enlace youmixer://, el acceso del menu Inicio y el entorno de Python (.venv).
echo La carpeta de YouMixer y su codigo no se tocan.
echo.
echo This removes YouMixer from Windows: the youmixer:// link, the Start menu shortcut and the Python environment (.venv).
echo The YouMixer folder and its code are left untouched.
echo.
choice /c SYN /n /m "Continuar / Continue? [S/Y/N] "
if errorlevel 3 exit /b 0

echo  - Apagando YouMixer / Turning YouMixer off...
powershell -NoProfile -NonInteractive -Command "try { Invoke-WebRequest -UseBasicParsing -Method Post -Uri http://localhost:8787/api/shutdown -Body '{}' -ContentType 'application/json' -TimeoutSec 3 | Out-Null; Start-Sleep 2 } catch {}"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" install.py uninstall
) else (
  reg delete "HKCU\Software\Classes\youmixer" /f >nul 2>nul
  del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\YouMixer.lnk" >nul 2>nul
)
rmdir /s /q ".venv" 2>nul
if exist ".venv" (
  echo  - No se pudo borrar .venv: puede que YouMixer siga abierto. Cierralo y vuelve a ejecutar esto.
  echo    Could not delete .venv: YouMixer may still be open. Close it and run this again.
) else (
  echo  - Entorno de Python borrado / Python environment removed.
)

echo.
if not exist "data" goto done
echo Tus datos (listas, historial, lo aprendido y copias de seguridad) estan en la carpeta data.
echo Your data (lists, history, what it learned and backups) is in the data folder.
choice /c SYN /n /m "Borrar tambien tus datos? / Delete your data too? No se puede deshacer / This cannot be undone. [S/Y/N] "
if errorlevel 3 (
  echo  - Tus datos se conservan. Si vuelves a instalar YouMixer, seguiran ahi.
  echo    Your data is kept. If you install YouMixer again, it will still be there.
  goto done
)
rmdir /s /q "data"
echo  - Datos borrados / Data deleted.

:done
echo.
echo YouMixer esta desinstalado. Los navegadores guardan una copia de la pagina; si quieres quitarla,
echo borra los datos del sitio localhost:8787 en la configuracion de cada navegador.
echo.
echo YouMixer is uninstalled. Browsers keep a copy of the page; to remove it,
echo clear the site data for localhost:8787 in each browser's settings.
pause
