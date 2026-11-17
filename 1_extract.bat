@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Priconne Asset Extractor (Extract)

rem ======================================================================
rem  PRICONNE ASSET EXTRACTOR - EXTRACT
rem ======================================================================
rem  Extracts raw text / ADV scripts from .unity3d bundles located in input\
rem  Extracted text files are written into text\
rem
rem  Usage:
rem    Double-click to extract all bundles in input\
rem    1_extract.bat -r (Recursive folder extraction)
rem ======================================================================

echo [1/3] Extracting ADV scripts from input\ to text\...
echo.

for %%V in (3.13 3.12 3.14 3.11) do (
  py -%%V -c "import sys" >nul 2>&1 && (
    py -%%V priconne_tool.py extract %*
    goto :done
  )
)
python priconne_tool.py extract %*

:done
echo.
pause
