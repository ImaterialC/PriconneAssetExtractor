@echo off
setlocal
echo Registering .unity3d file association for Misora (Current User)...
set "MISORA_BAT=%~dp0misora.bat"
reg add "HKCU\Software\Classes\.unity3d" /ve /d "Misora.Unity3dBundle" /f >nul 2>&1
reg add "HKCU\Software\Classes\Misora.Unity3dBundle" /ve /d "Unity3D Story Bundle (Misora)" /f >nul 2>&1
reg add "HKCU\Software\Classes\Misora.Unity3dBundle\shell\open\command" /ve /d "\"%MISORA_BAT%\" \"%%1\"" /f >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Failed to write registry keys for current user.
) else (
    echo [SUCCESS] .unity3d files are now associated with Misora!
)
pause
