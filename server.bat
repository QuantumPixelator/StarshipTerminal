@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PY_EXE_DOTVENV=%SCRIPT_DIR%.venv\Scripts\python.exe"
set "PY_EXE_VENV=%SCRIPT_DIR%venv\Scripts\python.exe"
set "SERVER_MAIN=%SCRIPT_DIR%server\game_server_auth.py"

if exist "%PY_EXE_DOTVENV%" (
    "%PY_EXE_DOTVENV%" "%SERVER_MAIN%"
) else if exist "%PY_EXE_VENV%" (
    "%PY_EXE_VENV%" "%SERVER_MAIN%"
) else (
    echo [WARN] No local venv Python found in .venv or venv.
    echo [INFO] Falling back to py launcher...
    py "%SERVER_MAIN%"
)

if errorlevel 1 (
    echo.
    echo [ERROR] Server exited with an error.
    pause
)

endlocal
