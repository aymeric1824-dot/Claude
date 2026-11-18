@echo off
REM Glissez le fichier Excel du client sur ce fichier.
cd /d "%~dp0"
if "%~1"=="" (
  echo Glissez le fichier Excel du client sur lancer.bat
  pause
  exit /b 1
)
echo === Etape 1 : verification du fichier (rien n est envoye) ===
python -m sophos_auto.deployer "%~1" --simulation
if errorlevel 1 (
  pause
  exit /b 1
)
echo.
set /p OK=Appliquer cette configuration sur le pare-feu ? (O/N) 
if /i not "%OK%"=="O" exit /b 0
python -m sophos_auto.deployer "%~1"
pause
