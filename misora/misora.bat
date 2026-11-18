@echo off
setlocal
cd /d "%~dp0"
title Misora Editor: Unity3D Revision Tool ^& Story Editor

rem ── Launch via py launcher (preferred) or python on PATH ───────────────────
rem Section 4-H: Use python.exe / py (NOT pythonw.exe) so Windows console is
rem visible for live diagnostic logs, and pause on error so failures are readable.

where py >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0misora.py" %*
    if errorlevel 1 (
        echo.
        echo [Misora] Process exited with error code %errorlevel%.
        pause
    )
    goto :end
)

where python >nul 2>&1
if not errorlevel 1 (
    python "%~dp0misora.py" %*
    if errorlevel 1 (
        echo.
        echo [Misora] Process exited with error code %errorlevel%.
        pause
    )
    goto :end
)

echo [ERROR] Python not found. Please install Python 3.11-3.14 from python.org.
pause

:end
endlocal
