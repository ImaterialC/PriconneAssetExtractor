@echo off
setlocal
cd /d "%~dp0"
title Misora Editor: Unity3D Revision Tool ^& Story Editor

rem ── Find Python version with UnityPy installed (prefers Python 3.12/3.13) ──
for %%V in (3.12 3.13 3.11 3.14) do (
    py -%%V -c "import UnityPy" >nul 2>&1 && (
        py -%%V "%~dp0misora.py" %*
        if errorlevel 1 pause
        goto :end
    )
)

rem ── Fallback 1: try py -3.12 directly ────────────────────────────────────────
py -3.12 -c "import sys" >nul 2>&1 && (
    py -3.12 "%~dp0misora.py" %*
    if errorlevel 1 pause
    goto :end
)

rem ── Fallback 2: python on PATH if it has UnityPy ─────────────────────────────
python -c "import UnityPy" >nul 2>&1 && (
    python "%~dp0misora.py" %*
    if errorlevel 1 pause
    goto :end
)

rem ── Fallback 3: generic py -3 or python ──────────────────────────────────────
where py >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0misora.py" %*
    if errorlevel 1 pause
    goto :end
)

where python >nul 2>&1
if not errorlevel 1 (
    python "%~dp0misora.py" %*
    if errorlevel 1 pause
    goto :end
)

echo [ERROR] Python not found or UnityPy missing.
echo Please run: py -3.12 -m pip install -r requirements.txt
pause

:end
endlocal
