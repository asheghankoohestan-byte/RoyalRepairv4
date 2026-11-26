@echo off
setlocal
cd /d "%~dp0"
title RoyalRepairShop - EXE Builder (FIXED)
color 0B

cls
echo =====================================================
echo   ROYAL REPAIR SHOP - WINDOWS EXE BUILDER (FIXED)
echo =====================================================
echo.
echo This window will remain open. Do not close it during build.
echo.

set "SCRIPT=RoyalRepairShop_DeviceReplacement.py"
set "PYEXE="

if not exist "%SCRIPT%" (
  echo [ERROR] Python source file was not found:
  echo "%CD%\%SCRIPT%"
  echo.
  echo Put this BAT file and the PY file in the SAME folder.
  goto :END_FAIL
)

where py.exe >nul 2>&1
if not errorlevel 1 (
  set "PYEXE=py -3"
) else (
  where python.exe >nul 2>&1
  if not errorlevel 1 set "PYEXE=python"
)

if not defined PYEXE (
  echo [ERROR] Python is not installed or not available in PATH.
  echo Install Python 3 for Windows and enable "Add Python to PATH".
  goto :END_FAIL
)

echo [1/4] Python version:
%PYEXE% --version
if errorlevel 1 goto :END_FAIL

echo.
echo [2/4] Installing / updating PyInstaller...
%PYEXE% -m pip install --upgrade pyinstaller
if errorlevel 1 goto :END_FAIL

echo.
echo [3/4] Removing old build files...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist RoyalRepairShop_DeviceReplacement.spec del /q RoyalRepairShop_DeviceReplacement.spec

echo.
echo [4/4] Building EXE. This may take several minutes...
%PYEXE% -m PyInstaller --noconfirm --clean --onefile --windowed --name RoyalRepairShop_DeviceReplacement "%SCRIPT%"
if errorlevel 1 goto :END_FAIL

if not exist "dist\RoyalRepairShop_DeviceReplacement.exe" (
  echo [ERROR] EXE was not created in the dist folder.
  goto :END_FAIL
)

echo.
echo =====================================================
echo [SUCCESS] EXE CREATED SUCCESSFULLY!
echo File: "%CD%\dist\RoyalRepairShop_DeviceReplacement.exe"
echo =====================================================
echo.
echo Press any key to close this window...
pause >nul
exit /b 0

:END_FAIL
echo.
echo =====================================================
echo [FAILED] BUILD DID NOT COMPLETE.
echo Please take a photo of the error text above and send it.
echo =====================================================
echo.
echo Press any key to close this window...
pause >nul
exit /b 1
