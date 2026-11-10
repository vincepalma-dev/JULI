@echo off
title JULI
echo.
echo   J.U.L.I.
echo   Jolly Universe of Little Intelligences
echo   -------------------------------------
echo.

cd /d "%~dp0"

:: Serves the dashboard and the API on http://127.0.0.1:8000 (building the
:: dashboard first if needed) and opens it with a fresh session token.
.venv\Scripts\python -m juli serve

pause
