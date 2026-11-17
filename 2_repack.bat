@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Priconne Asset Extractor (Repack)

rem ======================================================================
rem  PRICONNE ASSET EXTRACTOR - REPACK
rem ======================================================================
rem  Repacks translated text files from text\ back into original .unity3d
rem  bundles from input\, creating modified bundles in output\
rem
rem  Usage:
rem    Double-click to repack all modified scripts from text\ into output\
rem ======================================================================

echo [2/3] Repacking translated text\ scripts back into .unity3d bundles...
echo.

for %%V in (3.13 3.12 3.14 3.11) do (
  py -%%V -c "import sys" >nul 2>&1 && (
    py -%%V priconne_tool.py repack %*
    goto :done
  )
)
python priconne_tool.py repack %*

:done
echo.
pause
