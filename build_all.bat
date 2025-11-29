@echo off
REM ============================================================
REM TrueFlow - Build All Variants
REM Builds: PyCharm Plugin + VS Code Extension
REM ============================================================

setlocal enabledelayedexpansion

echo.
echo ============================================================
echo TrueFlow - Building All Variants
echo ============================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "GRADLE_EXE=D:\gradle-8.10.1\bin\gradle.bat"
set "BUILD_SUCCESS=1"

REM ============================================================
REM 1. Build PyCharm Plugin (Kotlin/Gradle)
REM ============================================================
echo.
echo [1/2] Building PyCharm Plugin...
echo ------------------------------------------------------------

cd /d "%SCRIPT_DIR%"

if exist "%GRADLE_EXE%" (
    call "%GRADLE_EXE%" clean buildPlugin --no-daemon
) else (
    call gradlew.bat clean buildPlugin --no-daemon 2>nul || call gradle clean buildPlugin --no-daemon
)

if %ERRORLEVEL% neq 0 (
    echo [FAILED] PyCharm plugin build failed!
    set "BUILD_SUCCESS=0"
) else (
    echo [SUCCESS] PyCharm plugin built successfully!

    REM Find and display the built plugin
    for /f "delims=" %%i in ('dir /b /s "%SCRIPT_DIR%build\distributions\*.zip" 2^>nul') do (
        echo   Output: %%i
    )
)

REM ============================================================
REM 2. Build VS Code Extension (TypeScript/npm)
REM ============================================================
echo.
echo [2/2] Building VS Code Extension...
echo ------------------------------------------------------------

cd /d "%SCRIPT_DIR%vscode-extension"

if exist "package.json" (
    REM Install dependencies if node_modules doesn't exist
    if not exist "node_modules" (
        echo   Installing npm dependencies...
        call npm install
    )

    REM Compile TypeScript
    call npm run compile

    if %ERRORLEVEL% neq 0 (
        echo [FAILED] VS Code extension build failed!
        set "BUILD_SUCCESS=0"
    ) else (
        echo [SUCCESS] VS Code extension built successfully!
        echo   Output: %SCRIPT_DIR%vscode-extension\out\

        REM Package VSIX if vsce is available
        where vsce >nul 2>nul
        if %ERRORLEVEL% equ 0 (
            echo   Packaging VSIX...
            call vsce package
            for /f "delims=" %%i in ('dir /b "*.vsix" 2^>nul') do (
                echo   VSIX: %%i
            )
        ) else (
            echo   [INFO] Install vsce to package VSIX: npm install -g @vscode/vsce
        )
    )
) else (
    echo [SKIPPED] VS Code extension - package.json not found
)

REM ============================================================
REM Summary
REM ============================================================
echo.
echo ============================================================
echo Build Summary
echo ============================================================

cd /d "%SCRIPT_DIR%"

echo.
echo PyCharm Plugin:
if exist "build\distributions\*.zip" (
    for /f "delims=" %%i in ('dir /b "build\distributions\*.zip" 2^>nul') do (
        echo   [OK] build\distributions\%%i
    )
) else (
    echo   [MISSING] No plugin ZIP found
)

echo.
echo VS Code Extension:
if exist "vscode-extension\out\extension.js" (
    echo   [OK] vscode-extension\out\extension.js
) else (
    echo   [MISSING] Extension not compiled
)

echo.
if "%BUILD_SUCCESS%"=="1" (
    echo ============================================================
    echo All builds completed successfully!
    echo ============================================================
) else (
    echo ============================================================
    echo Some builds failed - check output above
    echo ============================================================
    exit /b 1
)

endlocal
