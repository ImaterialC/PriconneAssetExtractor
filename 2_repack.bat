@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem UnityPy needs Python 3.11-3.14 - pick one automatically via the py launcher
for %%V in (3.13 3.12 3.14 3.11) do (
  py -%%V -c "import sys" >nul 2>&1 && (
    py -%%V priconne_tool.py repack
    goto :done
  )
)
python priconne_tool.py repack
:done
pause
