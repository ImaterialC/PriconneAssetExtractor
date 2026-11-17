@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Priconne master.db Browser & Explorer

set "PY="
for %%V in (3.13 3.12 3.11 3.14) do (
    if not defined PY ( py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V" )
)
if not defined PY ( python -c "import sys" >nul 2>&1 && set "PY=python" )
if not defined PY (
    echo [ERROR] Python not found. Install Python 3.11-3.14 from python.org.
    pause & exit /b 1
)

:menu
cls
echo ======================================================================
echo           PRICONNE master.db BROWSER & EXPLORER
echo ======================================================================
echo  master.db holds all official game metadata:
echo    - Characters / Units : ID (e.g. 105801), EN Name (Pecorine), JP Name (ペコリーヌ)
echo    - Stories / ADV      : Story ID (e.g. 1001001), JP Title, Subtitle
echo    - Cross-References   : Connects any character/story ID to actual .unity3d files
echo ======================================================================
echo.
echo  1. Search Character / Unit (by EN name, JP name, or Unit ID)
echo  2. Search Story Episodes   (by Story ID, Character name, or Subtitle)
echo  3. Cross-Reference ID      (find all asset files linked to an ID)
echo  4. List All Database Tables (view table names & row counts)
echo  5. Open master.db in SQLite GUI (DB Browser for SQLite)
echo  6. Launch Full Data Miner Menu (Manifests, Downloads & Extraction)
echo  0. Exit
echo.
set "CHOICE="
set /p "CHOICE=Choose an option [1-6, 0]: "

if "!CHOICE!"=="0" exit /b 0
if "!CHOICE!"=="1" goto search_unit
if "!CHOICE!"=="2" goto search_story
if "!CHOICE!"=="3" goto cross_ref
if "!CHOICE!"=="4" goto list_tables
if "!CHOICE!"=="5" goto open_gui
if "!CHOICE!"=="6" goto full_miner

echo [!] Invalid option.
timeout /t 2 >nul
goto menu

:search_unit
echo.
echo [Search Unit / Character]
echo Examples: Pecorine, Hiyori, ペコリーヌ, 105801
set "UNAME="
set /p "UNAME=Enter character name or ID: "
if defined UNAME (
    echo.
    %PY% -m NewDataMiner.cli --db-unit "!UNAME!"
)
echo.
pause
goto menu

:search_story
echo.
echo [Search Story Episodes]
echo Examples: 1001, ヒヨリ, 美食殿, 第1話
set "SNAME="
set /p "SNAME=Enter story ID or title keyword: "
if defined SNAME (
    echo.
    %PY% -m NewDataMiner.cli --db-story "!SNAME!"
)
echo.
pause
goto menu

:cross_ref
echo.
echo [Cross-Reference ID to Assets]
echo Examples: 105801 (Pecorine), 100101 (Hiyori), 1001001 (Story Ep 1)
set "REFID="
set /p "REFID=Enter Unit or Story ID: "
if defined REFID (
    echo.
    %PY% -m NewDataMiner.cli --cross-ref "!REFID!"
)
echo.
pause
goto menu

:list_tables
echo.
echo [Listing master.db Tables...]
%PY% -m NewDataMiner.cli --list-tables
echo.
pause
goto menu

:open_gui
echo.
set "DB_BROWSER="
if exist "C:\Program Files\DB Browser for SQLite\DB Browser for SQLite.exe" (
    set "DB_BROWSER=C:\Program Files\DB Browser for SQLite\DB Browser for SQLite.exe"
) else if exist "C:\Program Files (x86)\DB Browser for SQLite\DB Browser for SQLite.exe" (
    set "DB_BROWSER=C:\Program Files (x86)\DB Browser for SQLite\DB Browser for SQLite.exe"
) else (
    where sqlitebrowser >nul 2>&1 && set "DB_BROWSER=sqlitebrowser"
)

if defined DB_BROWSER (
    echo Launching DB Browser with master.db...
    start "" "!DB_BROWSER!" "%~dp0master.db"
) else (
    echo [!] DB Browser for SQLite is not installed.
    echo.
    echo To install it free:
    echo   Run command : winget install SQLiteBrowser.SQLiteBrowser
    echo   Or download : https://sqlitebrowser.org/dl/
    echo.
    echo Opening repository folder in Explorer instead...
    start "" explorer "%~dp0"
)
echo.
pause
goto menu

:full_miner
%PY% -m NewDataMiner.cli
goto menu
