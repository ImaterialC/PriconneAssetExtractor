@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Priconne Universal Japanese Game Data Miner (New)
for %%V in (3.13 3.12 3.14 3.11) do (
  py -%%V -c "import sys" >nul 2>&1 && (
    py -%%V -m NewDataMiner.cli %*
    goto :done
  )
)
python -m NewDataMiner.cli %*
:done
echo.
pause
