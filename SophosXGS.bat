@echo off
rem ===========================================================================
rem  SophosXGS : double-cliquez sur ce fichier pour ouvrir l'outil (la fenetre).
rem  Au premier lancement, les composants necessaires sont installes tout seuls.
rem ===========================================================================
cd /d "%~dp0"
set "PY=python"
where python >nul 2>nul || set "PY=py"
where %PY% >nul 2>nul || goto pas_de_python
%PY% -c "import requests, xmltodict, openpyxl, pykeepass, tkinter" >nul 2>nul && goto lancer
echo.
echo   Premier lancement : installation des composants necessaires.
echo   Cela prend une minute, ne fermez pas cette fenetre...
echo.
%PY% -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto echec
:lancer
set "PYW=pythonw"
if /i "%PY%"=="py" set "PYW=pyw"
start "" %PYW% lanceur.py
exit /b 0

:pas_de_python
echo.
echo   Python n'est pas installe sur ce PC.
echo   1. Installez-le depuis https://www.python.org/downloads/
echo   2. Pendant l'installation, cochez la case "Add Python to PATH".
echo   3. Double-cliquez a nouveau sur SophosXGS.bat
echo.
pause
exit /b 1

:echec
echo.
echo   L'installation des composants a echoue. Verifiez la connexion Internet,
echo   puis double-cliquez a nouveau sur SophosXGS.bat
echo.
pause
exit /b 1
