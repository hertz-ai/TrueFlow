@echo off
REM ============================================================
REM TrueFlow - Build All Variants
REM Builds: PyCharm Plugin + VS Code Extension + Python Deps
REM Usage: build_all.bat [--test] [--skip-python]
REM ============================================================

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "GRADLE_EXE=D:\gradle-8.10.1\bin\gradle.bat"
set "BUILD_SUCCESS=1"
set "RUN_TESTS=0"
set "SKIP_PYTHON=0"

REM Parse arguments
:parse_args
if "%~1"=="" goto :done_args
if /i "%~1"=="--test" set "RUN_TESTS=1"
if /i "%~1"=="--skip-python" set "SKIP_PYTHON=1"
shift
goto :parse_args
:done_args

echo.
echo ============================================================
echo TrueFlow - Building All Variants
echo ============================================================
echo.

REM Activate virtual environment if it exists
if exist "%SCRIPT_DIR%.venv\Scripts\activate.bat" (
    call "%SCRIPT_DIR%.venv\Scripts\activate.bat"
    echo [OK] Activated .venv
) else if exist "%SCRIPT_DIR%venv\Scripts\activate.bat" (
    call "%SCRIPT_DIR%venv\Scripts\activate.bat"
    echo [OK] Activated venv
)

REM ============================================================
REM 0. Install Python Dependencies (if not skipped)
REM ============================================================
if "%SKIP_PYTHON%"=="0" (
    echo.
    echo [0/3] Installing Python Dependencies...
    echo ------------------------------------------------------------

    cd /d "%SCRIPT_DIR%"

    REM Install manim visualizer dependencies
    if exist "manim_visualizer\requirements.txt" (
        pip install -r manim_visualizer\requirements.txt -q 2>nul
        if %ERRORLEVEL% equ 0 (
            echo   [OK] Manim dependencies installed
        ) else (
            echo   [WARN] Some manim dependencies may have failed
        )
    )

    REM Install test dependencies
    if exist "manim_visualizer\requirements-test.txt" (
        pip install -r manim_visualizer\requirements-test.txt -q 2>nul
        if %ERRORLEVEL% equ 0 (
            echo   [OK] Test dependencies installed
        ) else (
            echo   [WARN] Some test dependencies may have failed
        )
    )
) else (
    echo.
    echo [0/3] Skipping Python dependencies (--skip-python)
)

REM ============================================================
REM 1. Build PyCharm Plugin (Kotlin/Gradle)
REM ============================================================
echo.
echo [1/3] Building PyCharm Plugin...
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
echo [2/3] Building VS Code Extension...
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
REM 3. Run Tests (if --test flag provided)
REM ============================================================
if "%RUN_TESTS%"=="1" (
    echo.
    echo [3/3] Running Tests...
    echo ------------------------------------------------------------

    cd /d "%SCRIPT_DIR%"

    REM Set PYTHONPATH
    set "PYTHONPATH=%SCRIPT_DIR%src\main\resources\runtime_injector;%SCRIPT_DIR%src\main\resources;%SCRIPT_DIR%;%SCRIPT_DIR%manim_visualizer"

    REM Run quick tests
    python -m pytest tests/test_runtime_instrumentor_unit.py tests/test_error_handling.py -v --tb=short -q
    if %ERRORLEVEL% neq 0 (
        echo [WARN] Some tests failed
    ) else (
        echo [OK] Core tests passed
    )

    cd /d "%SCRIPT_DIR%manim_visualizer"
    python -m pytest tests/test_frame_bounds_validation.py tests/test_animation_pacing.py -v --tb=short -q
    if %ERRORLEVEL% neq 0 (
        echo [WARN] Some manim tests failed
    ) else (
        echo [OK] Manim tests passed
    )
) else (
    echo.
    echo [3/3] Skipping tests (use --test to run)
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
echo Python Dependencies:
python -c "import manim; print('  [OK] manim', manim.__version__)" 2>nul || echo   [MISSING] manim not installed
python -c "import pytest; print('  [OK] pytest', pytest.__version__)" 2>nul || echo   [MISSING] pytest not installed

echo.
if "%BUILD_SUCCESS%"=="1" (
    echo ============================================================
    echo All builds completed successfully!
    echo ============================================================
    echo.
    echo Usage:
    echo   build_all.bat              Build all components
    echo   build_all.bat --test       Build and run quick tests
    echo   build_all.bat --skip-python  Skip Python dependency install
    echo   run_all_tests.bat          Run full test suite ^(~163 tests^)
    echo.
) else (
    echo ============================================================
    echo Some builds failed - check output above
    echo ============================================================
    exit /b 1
)

endlocal
