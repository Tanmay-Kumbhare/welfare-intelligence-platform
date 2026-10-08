@echo off
setlocal

:: Determine project root directory
set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

if exist "%ROOT_DIR%\backend" (
    set "PROJECT_DIR=%ROOT_DIR%"
) else if exist "%ROOT_DIR%\welfare-intelligence-platform\backend" (
    set "PROJECT_DIR=%ROOT_DIR%\welfare-intelligence-platform"
) else (
    echo [ERROR] Project directories not found.
    pause
    exit /b 1
)

set "BACKEND_DIR=%PROJECT_DIR%\backend"
set "FRONTEND_DIR=%PROJECT_DIR%\frontend"

echo ==============================================================================
echo                 Starting Welfare Intelligence Platform
echo ==============================================================================
echo.

:: 1. Start Backend using existing virtual environment and uvicorn
echo Starting Backend Server (FastAPI / Uvicorn on port 8000)...
if exist "%BACKEND_DIR%\venv\Scripts\activate.bat" (
    start "VidyaSetu - Backend" /D "%BACKEND_DIR%" cmd /k "call venv\Scripts\activate.bat && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
) else (
    start "VidyaSetu - Backend" /D "%BACKEND_DIR%" cmd /k "uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
)

:: 2. Start Frontend using existing npm run dev
echo Starting Frontend Server (Vite on port 5173)...
start "VidyaSetu - Frontend" /D "%FRONTEND_DIR%" cmd /k "npm run dev"

:: 3. Wait briefly and open default browser
echo.
echo Waiting for servers to initialize...
ping 127.0.0.1 -n 4 >nul

echo Opening http://localhost:5173 in default browser...
start http://localhost:5173

echo.
echo ==============================================================================
echo Application launched!
echo - Frontend UI: http://localhost:5173
echo - Backend API: http://localhost:8000
echo - API Docs:    http://localhost:8000/docs
echo.
echo Backend and frontend are running in separate terminal windows.
echo Use stop.bat to stop both services.
echo ==============================================================================
