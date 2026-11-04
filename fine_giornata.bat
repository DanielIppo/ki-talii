@echo off
chcp 65001 > nul
title ki-talii: Sincronizzazione ActivityWatcher -> Kimai

cd /d "%~dp0"
python sync.py --sync

echo.
pause
