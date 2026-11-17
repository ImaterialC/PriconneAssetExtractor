@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem UnityPy needs Python 3.11-3.14 - pick one automatically via the py launcher.
rem Usage: priconne_tool.bat                      -> interactive menu
rem        priconne_tool.bat extract -r           -> run directly (extra args are passed through)
for %%V in (3.13 3.12 3.14 3.11) do (
  py -%%V -c "import sys" >nul 2>&1 && (
    py -%%V priconne_tool.py %*
    goto :done
  )
)
python priconne_tool.py %*
:done
echo.
pause
