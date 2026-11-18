@echo off
setlocal

cd /d "%~dp0"
title Misora Editor: Unity3D Revision Tool ^& Story Editor

rem ── Debug mode: pass --debug to show console and log output ─────────────────
set "DEBUG_FLAG="
for %%A in (%*) do (
    if /i "%%~A"=="--debug" set "DEBUG_FLAG=1"
)

rem ── Launch: pythonw suppresses console window; py shows one (for debugging) ─
where py >nul 2>&1
if not errorlevel 1 (
    if defined DEBUG_FLAG (
        py -3.12 "%~dp0misora.py" %*
    ) else (
        start "" /b pythonw -3.12 "%~dp0misora.py" %*
    )
    goto :end
)

where python >nul 2>&1
if not errorlevel 1 (
    if defined DEBUG_FLAG (
        python "%~dp0misora.py" %*
    ) else (
        start "" /b pythonw "%~dp0misora.py" %*
    )
    goto :end
)

echo [ERROR] Python not found. Please install Python 3.11-3.14 from python.org.
pause

:end
endlocal
