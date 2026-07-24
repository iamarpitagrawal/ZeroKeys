@echo off
title ZeroKeys Build Script
echo Building ZeroKeys.exe with PyInstaller...
pyinstaller --onefile --windowed --name ZeroKeys --collect-all faster_whisper --collect-all llama_cpp --collect-all customtkinter main.py
if %errorlevel% neq 0 (
    echo PyInstaller failed.
    pause
    exit /b %errorlevel%
)
echo.
echo Building NSIS installer...
python installer.py
if %errorlevel% neq 0 (
    echo Installer build failed.
    pause
    exit /b %errorlevel%
)
echo.
echo All done! Files in dist\:
dir dist\ /b
pause
