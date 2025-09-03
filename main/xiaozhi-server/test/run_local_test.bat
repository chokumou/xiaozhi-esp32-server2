
@echo off
setlocal enabledelayedexpansion
rem Usage: run_local_test.bat [TOKEN] [DEVICE_ID]
set "TOKEN=%~1"
if "%TOKEN%"=="" set "TOKEN=<YOUR_JWT>"
set "DEVICE_ID=%~2"
if "%DEVICE_ID%"=="" set "DEVICE_ID=test-device"

rem Resolve paths
set "SCRIPT_DIR=%~dp0"
set "SERVER_DIR=%SCRIPT_DIR%.."
set "TEST_DIR=%SCRIPT_DIR%"
set "LOG_DIR=%TEST_DIR%\test_logs"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo Starting uvicorn server in new window (title: NekotaServerWin)...
start "NekotaServerWin" cmd /k "cd /d "%SERVER_DIR%" && call .venv\Scripts\activate.bat && uvicorn railway_app:app --host 0.0.0.0 --port 8090 > "%LOG_DIR%\server.log" 2>&1"

rem give server a moment to start
timeout /t 2 /nobreak >nul

echo Running emulator (this window) and writing logs to %LOG_DIR%\emulator.log ...
pushd "%TEST_DIR%"
call "%SERVER_DIR%\.venv\Scripts\activate.bat"
python emulate_device_ws.py --url "ws://localhost:8090/ws?token=%TOKEN%&device_id=%DEVICE_ID%" --device-id %DEVICE_ID% --token "" >> "%LOG_DIR%\emulator.log" 2>&1
set "EMULATOR_EXIT_CODE=%ERRORLEVEL%"
popd

echo Emulator finished (exit code: %EMULATOR_EXIT_CODE%). Stopping server window...

rem Try to close the server window by window title
taskkill /F /FI "WINDOWTITLE eq NekotaServerWin" >nul 2>&1 || (
    echo Failed to kill by WINDOWTITLE, attempting to kill by image name (python)...
    taskkill /F /IM python.exe >nul 2>&1 || echo Could not kill python.exe
)

rem Show last 60 lines of server and emulator logs
echo ----- server.log (tail 60) -----
powershell -NoProfile -Command "Get-Content -Path '%LOG_DIR%\\server.log' -Tail 60 | ForEach-Object { $_ }"
echo ----- emulator.log (tail 60) -----
powershell -NoProfile -Command "Get-Content -Path '%LOG_DIR%\\emulator.log' -Tail 60 | ForEach-Object { $_ }"

echo Logs saved to %LOG_DIR%

endlocal


