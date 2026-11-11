@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PY=.venv\Scripts\python.exe"

echo ============================================
echo   Block Story Character Save Editor
echo ============================================
echo.

if exist "%PY%" goto check_venv

set "PYBASE="
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul
if not errorlevel 1 set "PYBASE=py -3"
if defined PYBASE goto create_venv

:try_python
where python >nul 2>nul
if errorlevel 1 goto no_python
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul
if errorlevel 1 goto no_python
set "PYBASE=python"

:create_venv
if not defined PYBASE goto no_python
echo [1/2] Creating virtual environment .venv ...
%PYBASE% -m venv .venv
if not exist "%PY%" goto venv_failed

:check_venv
"%PY%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul
if errorlevel 1 goto old_venv

echo [2/2] Checking dependencies ...
"%PY%" bootstrap.py %*
if errorlevel 1 goto run_failed
exit /b 0

:run_failed
echo.
echo The editor could not start. Read the messages above, then retry with:
echo   .venv\Scripts\python.exe bootstrap.py
pause
exit /b 1

:old_venv
echo.
echo The existing .venv uses Python older than 3.12, or it is broken.
echo Delete the .venv folder and run this file again.
pause
exit /b 1

:venv_failed
echo.
echo Failed to create .venv. Check that Python 3.12+ is installed correctly.
pause
exit /b 1

:no_python
echo.
echo Python 3.12+ was not found.
echo Install it from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH", then run this file again.
pause
exit /b 1
