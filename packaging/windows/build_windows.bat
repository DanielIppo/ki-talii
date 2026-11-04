@echo off
chcp 65001 > nul
echo =========================================================
echo   Compilazione Completa ki-talii: Eseguibile + Installer
echo =========================================================
echo.

cd /d "%~dp0..\.."

echo [1/2] Compilazione eseguibile con PyInstaller...
python -m PyInstaller --onedir --windowed --name "ki-talii" --collect-all customtkinter --noconfirm gui.py

if errorlevel 1 (
    echo.
    echo [ERRORE] Compilazione PyInstaller fallita!
    pause
    exit /b 1
)

echo.
echo [2/2] Creazione Windows Setup Installer con Inno Setup...

set "ISCC_PATH="
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
)

if defined ISCC_PATH (
    "%ISCC_PATH%" "packaging\windows\installer.iss"
    echo.
    echo =========================================================
    echo   INSTALLER CREATO CON SUCCESSO!
    echo   File: packaging\windows\Output\ki-talii-setup-x64.exe
    echo =========================================================
) else (
    echo [AVVISO] Inno Setup (ISCC.exe) non trovato nel percorso standard.
    echo Puoi compilare a mano packaging\windows\installer.iss con Inno Setup.
)

echo.
pause
