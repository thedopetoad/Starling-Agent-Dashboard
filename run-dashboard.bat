@echo off
rem ====================================================================
rem  Starling Agent Dashboard - double-click launcher (Windows)
rem  First run sets up a private virtual environment and installs the
rem  two dependencies (mcp, rich). After that it just opens the window.
rem ====================================================================
setlocal enableextensions
cd /d "%~dp0"

set "VENV=%~dp0.venv"
set "PYW=%VENV%\Scripts\pythonw.exe"
set "PY=%VENV%\Scripts\python.exe"
set "READY=%VENV%\.starling-deps"

rem -- fast path: already set up, just launch --------------------------
if exist "%PYW%" if exist "%READY%" goto launch

echo Setting up the Starling Dashboard (one time, ~30s)...
echo.

rem -- find a base Python ----------------------------------------------
set "BASEPY="
py -3 --version >nul 2>&1 && set "BASEPY=py -3"
if not defined BASEPY python --version >nul 2>&1 && set "BASEPY=python"
if not defined BASEPY (
  echo Python 3.10+ was not found on this PC.
  echo Install it from https://www.python.org/downloads/  ^(check "Add Python to PATH"^),
  echo then double-click this file again.
  start "" "https://www.python.org/downloads/"
  pause
  exit /b 1
)

rem -- create the venv if missing --------------------------------------
if not exist "%PY%" (
  echo Creating a private environment in .venv ...
  %BASEPY% -m venv "%VENV%"
  if errorlevel 1 (
    echo Failed to create the virtual environment.
    pause
    exit /b 1
  )
)

rem -- install dependencies --------------------------------------------
echo Installing dependencies ^(mcp, rich^)...
"%PY%" -m pip install --upgrade pip >nul 2>&1
"%PY%" -m pip install "mcp>=1.0" "rich>=13.0"
if errorlevel 1 (
  echo.
  echo Dependency install failed. Check your internet connection and try again.
  pause
  exit /b 1
)
> "%READY%" echo ok

:launch
rem Run as a windowed app ^(pythonw = no console^). PYTHONPATH makes the
rem local package importable without a pip install of the project itself.
set "PYTHONPATH=%~dp0"
start "" "%PYW%" -m starling_dashboard.gui
exit /b 0
