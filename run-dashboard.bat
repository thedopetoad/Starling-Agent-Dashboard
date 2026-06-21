@echo off
rem ====================================================================
rem  Starling Agent Dashboard - web UI launcher (Windows)
rem  Stdlib only: no virtualenv, no pip install. Just needs Python 3.10+.
rem  Opens the dashboard in your browser. Close this window to stop it.
rem ====================================================================
setlocal enableextensions
cd /d "%~dp0"

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

set "PYTHONPATH=%~dp0"
echo Starting the Starling dashboard - a browser tab will open shortly.
echo Keep this window open while you use it; close it to stop the dashboard.
%BASEPY% -m starling_dashboard web
