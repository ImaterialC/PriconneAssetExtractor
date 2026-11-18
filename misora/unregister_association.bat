@echo off
setlocal
echo Removing .unity3d file association for Misora (Current User)...
reg delete "HKCU\Software\Classes\.unity3d" /f >nul 2>&1
reg delete "HKCU\Software\Classes\Misora.Unity3dBundle" /f >nul 2>&1
echo [SUCCESS] .unity3d association removed for current user.
pause
