@echo off
chcp 65001 >nul
cd /d "%~dp0"

for %%V in (3.13 3.12 3.14 3.11) do (
  py -%%V -c "import sys" >nul 2>&1 && (
    py -%%V browse_master_db.py %*
    goto :done
  )
)
python browse_master_db.py %*

:done
echo.
pause
