@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Priconne XUAT Direct Repacker

rem ======================================================================
rem  PRICONNE XUAT DIRECT REPACKER
rem ======================================================================
rem  Directly merges external XUAT translations into raw ADV scripts
rem  and repacks them into game-ready .unity3d bundles in output\
rem
rem  Usage:
rem    3_xuat_repack.bat
rem    3_xuat_repack.bat --project "C:\PriconneRe-TL\src\BepInEx\Translation\en\Text"
rem ======================================================================

echo [3/3] Running XUAT direct injection and repacking...
echo.

for %%V in (3.13 3.12 3.14 3.11) do (
  py -%%V -c "import sys" >nul 2>&1 && (
    py -%%V priconne_tool.py xuat-repack %*
    goto :done
  )
)
python priconne_tool.py xuat-repack %*

:done
echo.
pause
