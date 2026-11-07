@echo off
setlocal EnableDelayedExpansion
title Video Downloader - Starting
color 0B
cls

echo.
echo   ============================================================
echo      VIDEO DOWNLOADER
echo      Starting up - this may take a minute the first time
echo   ============================================================
echo.

set "APPDIR=%~dp0"
set "APPFILE=%APPDIR%VideoDownloader.py"
set "PY="

if not exist "%APPFILE%" (
    echo   PROBLEM: VideoDownloader.py was not found.
    echo.
    echo   This launcher and VideoDownloader.py must sit in the
    echo   SAME folder. Looked in:
    echo     %APPDIR%
    echo.
    pause
    exit /b 1
)

:: ============================================================
::  STEP 1 - Find a working Python
:: ============================================================
echo   [1 of 4]  Looking for Python...

:: The 'py' launcher is the most reliable when it exists
py -3 -c "import sys" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PY=py -3"
    goto :found_python
)

:: Plain 'python'. On Windows this can be a Microsoft Store stub that
:: does nothing, so we test that it actually executes code rather than
:: trusting that the command exists.
python -c "import sys" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PY=python"
    goto :found_python
)

:: Common install locations, in case PATH was never set up
for %%V in (313 312 311 310 39 38) do (
    if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
        set "PY=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
        goto :found_python
    )
    if exist "C:\Python%%V\python.exe" (
        set "PY=C:\Python%%V\python.exe"
        goto :found_python
    )
)

:: ============================================================
::  STEP 1b - Not found: install it
:: ============================================================
echo           Python is not installed on this computer.
echo.
echo   ------------------------------------------------------------
echo     Python needs to be installed first. It is free, safe and
echo     made by the Python Software Foundation.
echo.
echo     This will download about 25 MB and take a few minutes.
echo   ------------------------------------------------------------
echo.
choice /C YN /M "   Install Python now"
if !ERRORLEVEL! equ 2 (
    echo.
    echo   Cancelled. Nothing was changed.
    echo   You can install Python yourself from https://python.org
    echo.
    pause
    exit /b 1
)

echo.
echo           Installing - please wait, do not close this window...
echo.

:: --- Try winget first (built into Windows 10 21H2+ and Windows 11) ---
set "INSTALLED=0"
winget --version >nul 2>&1
if !ERRORLEVEL! equ 0 (
    echo           Using Windows Package Manager...
    winget install --id Python.Python.3.12 --scope user --silent ^
          --accept-package-agreements --accept-source-agreements >nul 2>&1
    if !ERRORLEVEL! equ 0 set "INSTALLED=1"
)

:: --- Fall back to downloading the official installer ---
if "!INSTALLED!"=="0" (
    echo           Downloading the installer from python.org...
    set "PYSETUP=%TEMP%\python_setup.exe"
    set "PYURL=https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe"

    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "try { [Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -Uri '!PYURL!' -OutFile '!PYSETUP!' -UseBasicParsing } catch { exit 1 }" >nul 2>&1

    if not exist "!PYSETUP!" (
        echo.
        echo   PROBLEM: Could not download Python.
        echo.
        echo   Check the internet connection, then either run this
        echo   launcher again, or install Python by hand:
        echo.
        echo     1. Go to  https://python.org/downloads
        echo     2. Click the yellow Download button
        echo     3. IMPORTANT: tick "Add Python to PATH" on the
        echo        first screen of the installer
        echo     4. Click Install Now
        echo     5. Run this launcher again
        echo.
        pause
        exit /b 1
    )

    echo           Installing Python - this takes a few minutes...
    "!PYSETUP!" /passive InstallAllUsers=0 PrependPath=1 Include_pip=1 ^
                Include_launcher=1 Include_test=0 SimpleInstall=1
    del "!PYSETUP!" >nul 2>&1
)

:: --- Pick up the PATH the installer just wrote ---
for /f "skip=2 tokens=2,*" %%a in ('reg query "HKCU\Environment" /v PATH 2^>nul') do (
    set "PATH=%%b;!PATH!"
)

:: --- Verify ---
py -3 -c "import sys" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PY=py -3"
    goto :found_python
)
python -c "import sys" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PY=python"
    goto :found_python
)
for %%V in (313 312 311 310) do (
    if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
        set "PY=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
        goto :found_python
    )
)

echo.
echo   Python was installed, but Windows has not picked it up yet.
echo.
echo     Please RESTART THE COMPUTER, then double-click this
echo     launcher again. This only happens once.
echo.
pause
exit /b 1

:found_python
for /f "tokens=*" %%v in ('!PY! --version 2^>^&1') do echo           Found %%v

:: ============================================================
::  STEP 2 - Download engine
:: ============================================================
echo.
echo   [2 of 4]  Checking the download engine...
!PY! -m pip install --upgrade pip --quiet >nul 2>&1
!PY! -m pip install --upgrade "yt-dlp[default]" --quiet >nul 2>&1
if !ERRORLEVEL! neq 0 (
    !PY! -m pip install --upgrade yt-dlp --quiet >nul 2>&1
)
for /f "tokens=*" %%v in ('!PY! -c "import yt_dlp;print(yt_dlp.version.__version__)" 2^>nul') do (
    echo           Engine version %%v
)

:: ============================================================
::  STEP 3 - Secure connections
:: ============================================================
echo.
echo   [3 of 4]  Checking secure connections...
!PY! -c "import truststore" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    !PY! -m pip install truststore --quiet >nul 2>&1
)
!PY! -c "import truststore" >nul 2>&1
if !ERRORLEVEL! equ 0 (echo           Ready) else (echo           Skipped - some sites may fail)

:: ============================================================
::  STEP 4 - Video helper (ffmpeg)
:: ============================================================
echo.
echo   [4 of 4]  Checking the helper module (FFmpeg)...
ffmpeg -version >nul 2>&1
if !ERRORLEVEL! equ 0 (
    echo           Found
) else (
    !PY! -c "import imageio_ffmpeg" >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo           Installing - please wait...
        winget --version >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            winget install --id Gyan.FFmpeg --scope user --silent ^
                  --accept-package-agreements --accept-source-agreements >nul 2>&1
        )
        ffmpeg -version >nul 2>&1
        if !ERRORLEVEL! neq 0 !PY! -m pip install imageio-ffmpeg --quiet >nul 2>&1
    )
    echo           Ready
)

:: ============================================================
::  Launch
:: ============================================================

:: Any flags given to this launcher (--selftest, --url ...) are passed
:: straight through, and those run in this console rather than detaching.
if not "%~1"=="" (
    echo.
    echo   ------------------------------------------------------------
    echo     Running: %*
    echo   ------------------------------------------------------------
    echo.
    !PY! "%APPFILE%" %*
    echo.
    pause
    exit /b 0
)

echo.
echo   ------------------------------------------------------------
echo     Everything is ready. Opening Video Downloader...
echo   ------------------------------------------------------------
echo.

:: pythonw runs without leaving a black console window behind
set "PYW="
if "!PY!"=="py -3" (
    set "PYW=pyw -3"
) else (
    for %%I in ("!PY!") do set "PYDIR=%%~dpI"
    if exist "!PYDIR!pythonw.exe" set "PYW=!PYDIR!pythonw.exe"
)

if defined PYW (
    start "" !PYW! "%APPFILE%"
    timeout /t 3 >nul
    exit /b 0
) else (
    !PY! "%APPFILE%"
    if !ERRORLEVEL! neq 0 (
        echo.
        echo   The program closed with an error. The message above
        echo   may explain why. For a full check, run:
        echo.
        echo       VideoDownloader.bat --selftest
        echo.
        pause
    )
)

endlocal
