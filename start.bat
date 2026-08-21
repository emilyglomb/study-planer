@echo off
REM Double-click to start StudyPlanner (backend + designed frontend, one server).
REM First run sets up the virtual environment and installs dependencies.

setlocal enabledelayedexpansion
cd /d "%~dp0"

REM --- find a working Python 3 ---
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo Python 3 was not found. Install it from https://www.python.org/downloads/
    echo Press any key to close.
    pause >nul
    exit /b 1
)
echo Using Python:
%PY% --version

REM --- create the virtual environment if missing ---
if not exist ".venv" (
    echo Creating virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo Could not create venv.
        pause >nul
        exit /b 1
    )
)

REM --- make sure the dependencies are actually installed (not just that .venv exists) ---
".venv\Scripts\python.exe" -c "import pandas, flask, flask_cors, plotly" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies ^(this can take a minute on the first run^)...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Dependency installation failed ^(see messages above^).
        pause >nul
        exit /b 1
    )
)

REM --- if port 5050 is already taken, kill whatever's holding it so we always
REM     start a fresh server with the current code (avoids stale zombie processes) ---
for /f %%p in ('powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort 5050 -State Listen -ErrorAction SilentlyContinue).OwningProcess" 2^>nul') do set "PORT_PID=%%p"
if defined PORT_PID (
    echo Port 5050 is already in use ^(process ID %PORT_PID%^), most likely an old StudyPlanner server.
    echo Stopping it so the latest code gets served...
    taskkill /PID %PORT_PID% /F /T >nul 2>&1
    timeout /t 1 >nul
)

REM --- start the server in its own visible window, so errors/crashes are visible ---
echo Starting server...
start "StudyPlanner Server" cmd /k ".venv\Scripts\python.exe frontend.py"

REM --- wait until the server actually answers, then open the browser ---
set "READY="
for /l %%i in (1,1,60) do (
    powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5050/home' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
    if not errorlevel 1 (
        set "READY=1"
        goto :ready
    )
    timeout /t 1 >nul
)
:ready

if defined READY (
    start "" "http://127.0.0.1:5050/home"
    echo.
    echo StudyPlanner is running at http://127.0.0.1:5050/home
    echo To stop the server, close the "StudyPlanner Server" window.
) else (
    echo.
    echo The server did not answer after 60 seconds.
    echo Check the separate "StudyPlanner Server" window that opened -
    echo any error or crash from Flask will be printed there.
    echo Common cause: port 5050 already in use, or a missing dependency.
)

echo.
echo Press any key to close.
pause >nul
