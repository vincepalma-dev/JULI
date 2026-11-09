@echo off
title JULI Dashboard
echo.
echo   J.U.L.I.
echo   Jolly Universe of Little Intelligences
echo   ─────────────────────────────────────
echo.

:: Activate virtual environment and run
cd /d "%~dp0"
call .venv\Scripts\activate.bat

:: Open browser after a short delay (in background)
start "" cmd /c "timeout /t 4 /nobreak >nul & start http://localhost:3000"

:: Start both backend + frontend
python run.py

pause
