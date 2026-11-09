@echo off
title JULI Dashboard
echo.
echo   J.U.L.I.
echo   Jolly Universe of Little Intelligences
echo   -------------------------------------
echo.

:: Activate virtual environment and run
cd /d "%~dp0"
call .venv\Scripts\activate.bat

:: Starts backend + dashboard and opens the browser with a session token
python run.py

pause
