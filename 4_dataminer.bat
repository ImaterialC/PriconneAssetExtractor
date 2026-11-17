@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Priconne Universal Data Miner & master.db Explorer

rem ======================================================================
rem  PRICONNE UNIVERSAL JAPANESE GAME DATA MINER & master.db EXPLORER
rem ======================================================================
rem
rem  USAGE:
rem    Double-click or run without arguments to launch the Interactive Menu:
rem      4_dataminer.bat
rem
rem    Or run directly with CLI flags:
rem      Search Character by EN/Romaji : 4_dataminer.bat --db-unit Pecorine
rem      Search Character by JP name   : 4_dataminer.bat --db-unit ペコリーヌ
rem      Search Character by Unit ID   : 4_dataminer.bat --db-unit 105801
rem      Search Story / Episodes       : 4_dataminer.bat --db-story 1001
rem      Cross-Reference ID to Assets  : 4_dataminer.bat --cross-ref 105801
rem      List All Database Tables      : 4_dataminer.bat --list-tables
rem      Export Table to .sql          : 4_dataminer.bat --export-sql unit_data
rem      Check Remote DB Update        : 4_dataminer.bat --check-db-update
rem      Search Manifests (Offline)    : 4_dataminer.bat -s 9080155
rem      Download & Extract Assets     : 4_dataminer.bat -s 9080155 --download --extract
rem ======================================================================

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
