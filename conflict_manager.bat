@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
for %%V in (3.13 3.12 3.11 3.14) do (
    py -%%V -c "import sys" >nul 2>&1 && (
        py -%%V conflict_manager.py %*
        goto :done
    )
)
python conflict_manager.py %*
:done
echo.
pause