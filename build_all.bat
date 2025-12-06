@echo off
REM ============================================================
REM TrueFlow - Build All Variants
REM Builds: PyCharm Plugin + IntelliJ Plugin + VS Code Extension
REM         + Java Agent + Python Deps
REM Usage: build_all.bat [--test] [--skip-python] [--skip-java-agent]
REM ============================================================

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "GRADLE_EXE=D:\gradle-8.10.1\bin\gradle.bat"
set "BUILD_SUCCESS=1"
set "RUN_TESTS=0"
set "SKIP_PYTHON=0"
set "SKIP_JAVA_AGENT=0"

REM Parse arguments
:parse_args
if "%~1"=="" goto :done_args
if /i "%~1"=="--test" set "RUN_TESTS=1"
if /i "%~1"=="--skip-python" set "SKIP_PYTHON=1"
if /i "%~1"=="--skip-java-agent" set "SKIP_JAVA_AGENT=1"
shift
goto :parse_args
:done_args

echo.
echo ============================================================
echo TrueFlow - Building All Components
echo   - JetBrains Plugin (PyCharm, IntelliJ, Android Studio)
echo   - Java Agent (for Java/Kotlin runtime instrumentation)
echo   - VS Code Extension
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
    echo [0/4] Installing Python Dependencies...
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
    echo [0/4] Skipping Python dependencies (--skip-python)
)

REM ============================================================
REM 1. Build JetBrains Plugin (Universal - works on PyCharm, IntelliJ, Android Studio)
REM ============================================================
echo.
echo [1/4] Building JetBrains Plugin (Universal)...
echo ------------------------------------------------------------

cd /d "%SCRIPT_DIR%"

REM Clean first
if exist "%GRADLE_EXE%" (
    call "%GRADLE_EXE%" clean --no-daemon -q
) else (
    call gradlew.bat clean --no-daemon -q 2>nul || call gradle clean --no-daemon -q
)

REM Build universal plugin (works on PyCharm, IntelliJ IDEA, Android Studio)
REM Python features are optional via plugin.xml dependency declaration
if exist "%GRADLE_EXE%" (
    call "%GRADLE_EXE%" buildPlugin --no-daemon
) else (
    call gradlew.bat buildPlugin --no-daemon 2>nul || call gradle buildPlugin --no-daemon
)

if %ERRORLEVEL% neq 0 (
    echo [FAILED] JetBrains plugin build failed!
    set "BUILD_SUCCESS=0"
) else (
    echo [SUCCESS] JetBrains plugin built successfully!
    echo   Works on: PyCharm, IntelliJ IDEA Ultimate/Community, Android Studio

    REM Display the built plugin
    for /f "delims=" %%i in ('dir /b "%SCRIPT_DIR%build\distributions\*.zip" 2^>nul') do (
        echo   Output: build\distributions\%%i
    )
)

REM ============================================================
REM 2. Build Java Agent (if not skipped)
REM ============================================================
if "%SKIP_JAVA_AGENT%"=="0" (
    echo.
    echo [2/4] Building Java Agent...
    echo ------------------------------------------------------------

    cd /d "%SCRIPT_DIR%java-agent"

    if not exist "build.gradle.kts" (
        echo [SKIPPED] Java agent - build.gradle.kts not found
        goto :java_agent_done
    )

    REM Build shadow JAR with all dependencies
    if exist "%SCRIPT_DIR%java-agent\gradlew.bat" (
        call gradlew.bat shadowJar --no-daemon
    ) else if exist "%GRADLE_EXE%" (
        call "%GRADLE_EXE%" shadowJar --no-daemon
    ) else (
        call gradle shadowJar --no-daemon
    )

    if %ERRORLEVEL% neq 0 (
        echo [FAILED] Java agent build failed!
        set "BUILD_SUCCESS=0"
    ) else (
        echo [SUCCESS] Java agent built successfully!

        REM Find and display the built agent
        for /f "delims=" %%i in ('dir /b "%SCRIPT_DIR%java-agent\build\libs\trueflow-agent*.jar" 2^>nul') do (
            echo   Output: java-agent\build\libs\%%i
        )
    )
) else (
    echo.
    echo [2/4] Skipping Java agent (--skip-java-agent)
)
:java_agent_done

REM ============================================================
REM 3. Build VS Code Extension (TypeScript/npm)
REM    Uses build-both.js to auto-increment version and build
REM    for both Open VSX (hevolve-ai) and VS Marketplace (hertzai)
REM ============================================================
echo.
echo [3/4] Building VS Code Extension...
echo ------------------------------------------------------------

cd /d "%SCRIPT_DIR%vscode-extension"

if not exist "package.json" (
    echo [SKIPPED] VS Code extension - package.json not found
    goto :vscode_done
)

REM Install dependencies if node_modules doesn't exist
if not exist "node_modules" (
    echo   Installing npm dependencies...
    call npm install
)

REM Use build-both.js for auto-increment and dual-marketplace build
if not exist "build-both.js" goto :vscode_fallback

echo   Running build-both.js (auto-increment + dual marketplace)...
call node build-both.js
if %ERRORLEVEL% neq 0 (
    echo [FAILED] VS Code extension build failed!
    set "BUILD_SUCCESS=0"
) else (
    echo [SUCCESS] VS Code extension built successfully!
)
goto :vscode_done

:vscode_fallback
REM Fallback to simple compile if build-both.js doesn't exist
call npm run compile
if %ERRORLEVEL% neq 0 (
    echo [FAILED] VS Code extension build failed!
    set "BUILD_SUCCESS=0"
    goto :vscode_done
)
echo [SUCCESS] VS Code extension built successfully!
echo   Output: %SCRIPT_DIR%vscode-extension\out\

REM Package VSIX if vsce is available
where vsce >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo   Packaging VSIX...
    call vsce package
    for /f "delims=" %%i in ('dir /b "*.vsix" 2^>nul') do echo   VSIX: %%i
) else (
    echo   [INFO] Install vsce to package VSIX: npm install -g @vscode/vsce
)

:vscode_done

REM ============================================================
REM 4. Run Tests (if --test flag provided)
REM ============================================================
if "%RUN_TESTS%"=="1" (
    echo.
    echo [4/4] Running Tests...
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
    echo [4/4] Skipping tests (use --test to run)
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
echo JetBrains Plugin (PyCharm, IntelliJ IDEA, Android Studio):
if exist "build\distributions\*.zip" (
    for /f "delims=" %%i in ('dir /b "build\distributions\*.zip" 2^>nul') do (
        echo   [OK] build\distributions\%%i
    )
) else (
    echo   [MISSING] No plugin ZIP found
)

echo.
echo Java Agent (for Java runtime instrumentation):
if exist "java-agent\build\libs\trueflow-agent*.jar" (
    for /f "delims=" %%i in ('dir /b "java-agent\build\libs\trueflow-agent*.jar" 2^>nul') do (
        echo   [OK] java-agent\build\libs\%%i
    )
) else (
    echo   [MISSING] Java agent JAR not found
)

echo.
echo VS Code Extension:
if exist "vscode-extension\out\extension.js" (
    echo   [OK] vscode-extension\out\extension.js
    for /f "delims=" %%i in ('dir /b "vscode-extension\trueflow-openvsx-*.vsix" 2^>nul') do (
        echo   [OK] vscode-extension\%%i ^(Open VSX - hevolve-ai^)
    )
    for /f "delims=" %%i in ('dir /b "vscode-extension\trueflow-vsmarketplace-*.vsix" 2^>nul') do (
        echo   [OK] vscode-extension\%%i ^(VS Marketplace - hertzai^)
    )
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
    echo   build_all.bat                    Build all components
    echo   build_all.bat --test             Build and run quick tests
    echo   build_all.bat --skip-python      Skip Python dependency install
    echo   build_all.bat --skip-java-agent  Skip Java agent build
    echo   run_all_tests.bat                Run full test suite ^(~163 tests^)
    echo.
    echo Java Agent Usage:
    echo   java -javaagent:java-agent/build/libs/trueflow-agent.jar -jar your-app.jar
    echo   TRUEFLOW_ENABLED=1 java -javaagent:trueflow-agent.jar=includes=com.myapp -jar app.jar
    echo.
) else (
    echo ============================================================
    echo Some builds failed - check output above
    echo ============================================================
    exit /b 1
)

endlocal
