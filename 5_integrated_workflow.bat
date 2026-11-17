@echo off
chcp 65001 >nul
cd /d "%~dp0"

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
