@echo off
cd /d "%~dp0"
echo Installation des composants necessaires...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Echec : verifiez que Python est installe avec l option "Add Python to PATH".
) else (
  echo.
  echo Installation terminee. Lancez assistant.bat
)
pause
