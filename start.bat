@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PY=.venv\Scripts\python.exe"

echo ============================================
echo   Block Story Character Save Editor
echo ============================================
echo.

if not exist "%PY%" goto create_venv
"%PY%" -c "import streamlit" >nul 2>nul
if errorlevel 1 goto install
goto run

:create_venv
echo [1/3] Creating virtual environment ...
where py >nul 2>nul
if errorlevel 1 goto use_python
py -3 -m venv .venv
goto check_venv

:use_python
where python >nul 2>nul
if errorlevel 1 goto no_python
python -m venv .venv

:check_venv
if not exist "%PY%" goto no_python

:install
echo [2/3] Installing dependencies ...
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 goto install_failed

:run
echo [3/3] Starting http://localhost:8501
echo         Press Ctrl+C in this window to stop.
echo.
start "" http://localhost:8501
"%PY%" -m streamlit run app.py --server.headless true --server.port 8501
pause
exit /b 0

:install_failed
echo.
echo Dependency installation failed. Check your network, then run:
echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
pause
exit /b 1

:no_python
echo.
echo Python 3 was not found on PATH.
echo Install Python 3.12+ from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH", then run this file again.
pause
exit /b 1
