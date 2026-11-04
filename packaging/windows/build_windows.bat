@echo off
chcp 65001 > nul
echo ===================================================
echo   Compilazione ki-talii per Windows (PyInstaller)
echo ===================================================
echo.

cd /d "%~dp0..\.."

echo [1/2] Compilazione eseguibile ki-talii...
python -m PyInstaller --onedir --windowed --name "ki-talii" --collect-all customtkinter --noconfirm gui.py

if errorlevel 1 (
    echo.
    echo [ERRORE] Compilazione fallita!
    pause
    exit /b 1
)

echo.
echo [2/2] Compilazione completata con successo!
echo L'eseguibile e' disponibile in: dist\ki-talii\ki-talii.exe
echo.
echo Per creare l'installer .exe completo, apri packaging\windows\installer.iss con Inno Setup e compila.
echo.
pause
