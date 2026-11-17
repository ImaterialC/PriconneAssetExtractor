@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Priconne ADV Translation Tool
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

set "PY="
for %%V in (3.13 3.12 3.11 3.14) do (
    if not defined PY ( py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V" )
)
if not defined PY ( python -c "import sys" >nul 2>&1 && set "PY=python" )
if not defined PY (
    echo [ERROR] Python not found. Install Python 3.13 from python.org.
    pause & exit /b 1
)

set "RAW=Raw"
set "WORK=Work"
set "TRANS=Trans"
set "OUT=Out"
set "FOUND=Found"
set "VERIFY=Verify"
set "PROJECT="
set "BUNDLES=..\input"
if exist "adv_paths.bat" call "adv_paths.bat"

if not "%~1"=="" ( set "CHOICE=%~1" & call :doit & pause & exit /b 0 )

:menu
cls
echo ========================================================
echo           PRICONNE ADV TRANSLATION TOOL
echo ========================================================
echo  Python : %PY%
echo  RAW    : %RAW%      skeleton scripts from priconne_tool
echo  WORK   : %WORK%     sheets you send to the AI
echo  TRANS  : %TRANS%    sheets the AI translated
echo  OUT    : %OUT%      translated scripts, feed to repack
echo  BUNDLES: %BUNDLES%  original .unity3d bundles for repack
echo  PROJECT: %PROJECT%
echo.
echo  1. RAW  --^> SHEET          build ordered translation sheets for AI
echo  2. XUAT --^> RAW            inject XUAT translations into RAW (single input)
echo  3. XUAT --^> RAW + REPACK   inject XUAT into RAW and repack into .unity3d!
echo  4. TRANS --^> RAW           inject manual TRANS sheets into RAW
echo  5. REPACK ONLY             repack OUT/*.txt into .unity3d bundles
echo  6. VERIFY ^& CONFLICTS      alignment, actors, conflicts
echo  7. FILL MISSING            search PROJECT, patch TRANS sheets
echo  8. FOLDERS                 change the paths above
echo  9. OPEN OUT                explorer
echo  0. Exit
echo.
set "CHOICE="
set /p "CHOICE=Choose: "
call :doit
goto menu

:doit
if "!CHOICE!"=="0" exit
if "!CHOICE!"=="1" goto run1
if "!CHOICE!"=="2" goto run2
if "!CHOICE!"=="3" goto run3
if "!CHOICE!"=="4" goto run4
if "!CHOICE!"=="5" goto run5
if "!CHOICE!"=="6" goto run6
if "!CHOICE!"=="7" goto run7
if "!CHOICE!"=="8" goto run8
if "!CHOICE!"=="9" goto run9
echo Invalid choice. & pause & exit /b 0

:run1
echo.
if not exist "%RAW%" ( echo [ERROR] RAW folder not found. Option 8. & pause & exit /b 0 )
%PY% raw2xuat.py "%RAW%" -o "%WORK%"
echo.
echo Send %WORK%\*.txt to the AI. Keep line order and count. Save into %TRANS%.
pause & exit /b 0

:run2
echo.
if not exist "%RAW%" ( echo [ERROR] RAW folder not found. Option 8. & pause & exit /b 0 )
if defined PROJECT (
    %PY% xuat2raw.py "%RAW%" -p "%PROJECT%" -o "%OUT%"
) else (
    %PY% xuat2raw.py "%RAW%" -o "%OUT%"
)
echo.
echo Translated scripts saved in "%OUT%".
pause & exit /b 0

:run3
echo.
if not exist "%RAW%" ( echo [ERROR] RAW folder not found. Option 8. & pause & exit /b 0 )
if defined PROJECT (
    %PY% xuat2raw.py "%RAW%" -p "%PROJECT%" -o "%OUT%" --bundles "%BUNDLES%" --repack
) else (
    %PY% xuat2raw.py "%RAW%" -o "%OUT%" --bundles "%BUNDLES%" --repack
)
echo.
echo XUAT injection and repacking complete.
pause & exit /b 0

:run4
echo.
if not exist "%TRANS%" ( echo [ERROR] TRANS folder not found. Option 8. & pause & exit /b 0 )
if defined PROJECT (
    %PY% xuat2raw.py "%RAW%" -t "%TRANS%" -p "%PROJECT%" -o "%OUT%"
) else (
    %PY% xuat2raw.py "%RAW%" -t "%TRANS%" -o "%OUT%"
)
echo.
pause & exit /b 0

:run5
echo.
if exist "..\priconne_tool.py" (
    %PY% ..\priconne_tool.py repack -t "%OUT%" -i "%BUNDLES%"
) else (
    %PY% priconne_tool.py repack -t "%OUT%" -i "%BUNDLES%"
)
pause & exit /b 0

:run6
echo.
%PY% advverify.py "%RAW%" -t "%TRANS%" -p "%PROJECT%" -o "%VERIFY%" --actors --conflicts
pause & exit /b 0

:run7
echo.
if not defined PROJECT ( echo [ERROR] Set PROJECT first. Option 8. & pause & exit /b 0 )
call :fill
pause & exit /b 0

:fill
%PY% advverify.py "%RAW%" -t "%TRANS%" -p "%PROJECT%" -o "%FOUND%" --fill --inplace
echo.
echo TRANS sheets updated. Details in "%FOUND%".
exit /b 0

:run8
echo.
call :ask RAW     "RAW    - skeleton .txt from priconne_tool Extract"
call :ask WORK    "WORK   - sheets for the AI"
call :ask TRANS   "TRANS  - translated sheets"
call :ask OUT     "OUT    - translated scripts for Repack"
call :ask BUNDLES "BUNDLES- original .unity3d folder for Repack"
call :ask PROJECT "PROJECT- whole XUAT dictionary folder"
call :savepaths
echo Saved. & pause & exit /b 0

:run9
if not exist "%OUT%" mkdir "%OUT%"
start "" explorer "%OUT%"
exit /b 0
echo ==================== HOW THIS TOOL WORKS ====================
echo.
echo  RAW      Skeleton scripts. Output of priconne_tool.bat Extract.
echo           They hold every command: animation, voice, timing, text.
echo           Set that tool's Extract name pattern to {id} so the file
echo           is called 9080155.txt, not 72093f93-9080155.txt.
echo.
echo  WORK     One sheet per RAW file, same name. Format:
echo             ## Actors      speaker names, first appearance order
echo             ## Scripts     one dialogue box per line, in story order
echo           Line breaks inside a box are written \n. No = signs.
echo.
echo  TRANS    The same sheets with English. SAME ORDER, SAME LINE COUNT.
echo           Line N of ## Scripts belongs to box N of the RAW file.
echo           Pairing is by FILE NAME: Raw\9080155.txt - Trans\9080155.txt
echo           If a name has no pair, text matching against the whole
echo           dictionary is used instead.
echo.
echo  OUT      Translated RAW scripts. Point priconne_tool's Text folder
echo           here and run Repack. Also contains:
echo             _SUMMARY.txt            totals
echo             _missing.txt            everything still untranslated
echo             9080155.report.txt      JP/EN side by side for proofreading
echo             9080155.missing.txt     that file's gaps only
echo.
echo  PROJECT  Your existing XUAT dictionary folder. Read only. Used to
echo           fill gaps and to reuse old translations. Never modified.
echo.
echo  FILL     Between the pause segments of one box the tool writes a
echo           single ASCII space. It cannot write nothing: length 0 ends
echo           a record in the binary format. Use --fill drop to delete
echo           the extra records instead, or --fill zwsp for U+200B.
echo.
pause & exit /b 0

:ask
set "TMPV="
set /p "TMPV=  %~2 [!%~1!]: "
if not defined TMPV exit /b 0
for /f "delims=" %%A in ("!TMPV!") do set "%~1=%%~A"
exit /b 0

:savepaths
> "adv_paths.bat" (
 echo set "RAW=!RAW!"
 echo set "WORK=!WORK!"
 echo set "TRANS=!TRANS!"
 echo set "OUT=!OUT!"
 echo set "FOUND=!FOUND!"
 echo set "VERIFY=!VERIFY!"
 echo set "PROJECT=!PROJECT!"
)
exit /b 0