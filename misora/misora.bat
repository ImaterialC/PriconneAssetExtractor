@echo off
setlocal
cd /d "%~dp0"
title Misora: Unity3D Revision Tool ^& Story Editor

where py >nul 2>&1
if not errorlevel 1 (
    py -3.12 misora.py %*
    goto :end
)

where python >nul 2>&1
if not errorlevel 1 (
    python misora.py %*
    goto :end
)

echo [ERROR] Python not found. Please install Python 3.11-3.14 from python.org.
pause

:end
endlocal
