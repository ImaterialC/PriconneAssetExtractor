@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Priconne End-to-End Integrated Workflow

rem ======================================================================
rem  PRICONNE END-TO-END INTEGRATED WORKFLOW (P5)
rem ======================================================================
rem  Fully automated translation pipeline:
rem    1. Scans translation project directory (XUAT)
rem    2. Cross-references target entities with master.db
rem    3. Auto-downloads missing official bundles from Cygames CDN
rem    4. Extracts, injects English translations, and repacks
rem    5. Deploys redirected bundles into BepInEx RedirectedResources
rem
rem  Usage:
rem    5_integrated_workflow.bat
rem    5_integrated_workflow.bat --project "C:\PriconneRe-TL\src\BepInEx\Translation\en\Text"
rem ======================================================================

echo ======================================================================
echo    Princess Connect! Re:Dive - End-to-End Integrated Workflow (P5)
echo    Database Discovery -> Targeted Mining -> XUAT Repack -> Redirection
echo ======================================================================
echo.

for %%V in (3.13 3.12 3.14 3.11) do (
  py -%%V -c "import sys" >nul 2>&1 && (
    py -%%V priconne_tool.py workflow %*
    goto :done
  )
)
python priconne_tool.py workflow %*

:done
echo.
pause
