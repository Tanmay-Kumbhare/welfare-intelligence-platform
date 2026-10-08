@echo off
setlocal enabledelayedexpansion

title VidyaSetu - Welfare Intelligence Platform Stopper
color 0C

echo ==============================================================================
echo                 VIDYASETU - WELFARE INTELLIGENCE PLATFORM
echo                           Stopping Services...
echo ==============================================================================
echo.

set "STOPPED=0"

:: 1. Stop processes on port 8000 (Backend API)
echo Checking for Backend on port 8000...
for /f "tokens=5" %%a in ('netstat -a -n -o ^| findstr /r ":8000\>"') do (
    set "PID=%%a"
    if "!PID!" neq "0" (
        echo  - Terminating process !PID! listening on port 8000...
        taskkill /F /PID !PID! >nul 2>&1
        set "STOPPED=1"
    )
)

:: 2. Stop processes on port 5173 (Frontend UI)
echo Checking for Frontend on port 5173...
for /f "tokens=5" %%a in ('netstat -a -n -o ^| findstr /r ":5173\>"') do (
    set "PID=%%a"
    if "!PID!" neq "0" (
        echo  - Terminating process !PID! listening on port 5173...
        taskkill /F /PID !PID! >nul 2>&1
        set "STOPPED=1"
    )
)

echo.
if "!STOPPED!"=="1" (
    echo [OK] Backend and Frontend services stopped successfully.
) else (
    echo [INFO] No running VidyaSetu services found on ports 8000 or 5173.
)

echo.
echo ==============================================================================
echo.
pause
