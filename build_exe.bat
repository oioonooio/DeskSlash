@echo off
setlocal
cd /d "%~dp0"

echo [1/3] Cleaning previous build output...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [2/3] Building DesktopSlash.exe with PyInstaller...
python -m PyInstaller --noconfirm --clean DesktopSlash.spec
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

echo [3/3] Running the packaged self-test...
dist\DesktopSlash.exe --self-test
if errorlevel 1 (
    echo Packaged self-test failed. See dist\desktop_slash_self_test.txt
    exit /b 1
)

echo.
echo Build OK: dist\DesktopSlash.exe
echo Report:   dist\desktop_slash_self_test.txt
endlocal
