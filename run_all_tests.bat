@echo off
REM ============================================================================
REM TrueFlow Consolidated Test Runner
REM ============================================================================
REM Runs all tests for TrueFlow project including:
REM   - Manim Visualizer tests (unit, integration, visual, e2e)
REM   - Runtime Instrumentor tests (unit, error handling, end-to-end)
REM   - Protocol Detection tests
REM   - AI Explanation tests
REM   - Frame Bounds Validation tests
REM
REM PYTHONPATH is set via conftest.py, so no environment variable issues!
REM ============================================================================

setlocal enabledelayedexpansion

REM Set project root
set PROJECT_ROOT=%~dp0
cd /d %PROJECT_ROOT%

REM Activate virtual environment if it exists
if exist "%PROJECT_ROOT%.venv\Scripts\activate.bat" (
    call "%PROJECT_ROOT%.venv\Scripts\activate.bat"
    echo [OK] Activated .venv
) else if exist "%PROJECT_ROOT%venv\Scripts\activate.bat" (
    call "%PROJECT_ROOT%venv\Scripts\activate.bat"
    echo [OK] Activated venv
)

REM Colors for output (Windows 10+)
set "GREEN=[92m"
set "RED=[91m"
set "YELLOW=[93m"
set "CYAN=[96m"
set "RESET=[0m"

REM Counters
set TOTAL_PASSED=0
set TOTAL_FAILED=0
set TEST_SECTIONS=0

echo.
echo %CYAN%============================================================================%RESET%
echo %CYAN%                    TrueFlow Consolidated Test Runner                       %RESET%
echo %CYAN%============================================================================%RESET%
echo.

REM Check if pytest is available, if not install dependencies
python -m pytest --version >nul 2>&1
if errorlevel 1 (
    echo %YELLOW%Installing test dependencies...%RESET%
    pip install pytest pytest-cov pytest-html -q
    if errorlevel 1 (
        echo %RED%ERROR: Failed to install test dependencies%RESET%
        exit /b 1
    )
)

REM Check if manim is available, if not install it
python -c "import manim" >nul 2>&1
if errorlevel 1 (
    echo %YELLOW%Installing manim dependencies...%RESET%
    pip install manim -q
    if errorlevel 1 (
        echo %RED%WARNING: manim not installed, some tests will be skipped%RESET%
    )
)

echo %GREEN%Dependencies ready%RESET%
echo.

REM ============================================================================
REM Section 1: Runtime Instrumentor Unit Tests (18 tests)
REM ============================================================================
echo %YELLOW%[1/11] Running Runtime Instrumentor Unit Tests...%RESET%
echo ------------------------------------------------------------------------
python -m pytest tests/test_runtime_instrumentor_unit.py -v --tb=short 2>&1
if errorlevel 1 (
    echo %RED%Some tests failed%RESET%
    set /a TOTAL_FAILED+=1
) else (
    echo %GREEN%All tests passed%RESET%
    set /a TOTAL_PASSED+=1
)
set /a TEST_SECTIONS+=1

REM ============================================================================
REM Section 2: Error Handling Tests (10 tests)
REM ============================================================================
echo.
echo %YELLOW%[2/11] Running Error Handling Tests...%RESET%
echo ------------------------------------------------------------------------
python -m pytest tests/test_error_handling.py -v --tb=short 2>&1
if errorlevel 1 (
    echo %RED%Some tests failed%RESET%
    set /a TOTAL_FAILED+=1
) else (
    echo %GREEN%All tests passed%RESET%
    set /a TOTAL_PASSED+=1
)
set /a TEST_SECTIONS+=1

REM ============================================================================
REM Section 3: End-to-End Tests (11 tests)
REM ============================================================================
echo.
echo %YELLOW%[3/11] Running End-to-End Tests...%RESET%
echo ------------------------------------------------------------------------
python -m pytest tests/test_end_to_end.py -v --tb=short 2>&1
if errorlevel 1 (
    echo %RED%Some tests failed%RESET%
    set /a TOTAL_FAILED+=1
) else (
    echo %GREEN%All tests passed%RESET%
    set /a TOTAL_PASSED+=1
)
set /a TEST_SECTIONS+=1

REM ============================================================================
REM Section 4: Protocol Detection Tests (4 tests)
REM ============================================================================
echo.
echo %YELLOW%[4/11] Running Protocol Detection Tests...%RESET%
echo ------------------------------------------------------------------------
python -m pytest tests/test_protocol_detection_integration.py -v --tb=short 2>&1
if errorlevel 1 (
    echo %RED%Some tests failed%RESET%
    set /a TOTAL_FAILED+=1
) else (
    echo %GREEN%All tests passed%RESET%
    set /a TOTAL_PASSED+=1
)
set /a TEST_SECTIONS+=1

REM ============================================================================
REM Section 5: AI Explanation Tests (22 tests)
REM ============================================================================
echo.
echo %YELLOW%[5/11] Running AI Explanation Tests...%RESET%
echo ------------------------------------------------------------------------
python -m pytest tests/test_ai_explanation.py -v --tb=short 2>&1
if errorlevel 1 (
    echo %RED%Some tests failed%RESET%
    set /a TOTAL_FAILED+=1
) else (
    echo %GREEN%All tests passed%RESET%
    set /a TOTAL_PASSED+=1
)
set /a TEST_SECTIONS+=1

REM ============================================================================
REM Section 6: Manim Frame Bounds + Animation Pacing Tests (43 tests)
REM ============================================================================
echo.
echo %YELLOW%[6/11] Running Manim Frame Bounds + Animation Pacing Tests...%RESET%
echo ------------------------------------------------------------------------
python -m pytest manim_visualizer/tests/test_frame_bounds_validation.py manim_visualizer/tests/test_animation_pacing.py -v --tb=short 2>&1
if errorlevel 1 (
    echo %RED%Some tests failed%RESET%
    set /a TOTAL_FAILED+=1
) else (
    echo %GREEN%All tests passed%RESET%
    set /a TOTAL_PASSED+=1
)
set /a TEST_SECTIONS+=1

REM ============================================================================
REM Section 7: Manim Visual Regression Tests (15 tests)
REM ============================================================================
echo.
echo %YELLOW%[7/11] Running Visual Regression Tests...%RESET%
echo ------------------------------------------------------------------------
python -m pytest manim_visualizer/tests/test_visual_regression.py -v --tb=short 2>&1
if errorlevel 1 (
    echo %RED%Some tests failed%RESET%
    set /a TOTAL_FAILED+=1
) else (
    echo %GREEN%All tests passed%RESET%
    set /a TOTAL_PASSED+=1
)
set /a TEST_SECTIONS+=1

REM ============================================================================
REM Section 8: Manim E2E Regression Tests (22 tests)
REM ============================================================================
echo.
echo %YELLOW%[8/11] Running E2E Regression Tests...%RESET%
echo ------------------------------------------------------------------------
python -m pytest manim_visualizer/tests/test_e2e_regression.py -v --tb=short 2>&1
if errorlevel 1 (
    echo %RED%Some tests failed%RESET%
    set /a TOTAL_FAILED+=1
) else (
    echo %GREEN%All tests passed%RESET%
    set /a TOTAL_PASSED+=1
)
set /a TEST_SECTIONS+=1

REM ============================================================================
REM Section 9: Base Trace Visualizer Tests (18 tests)
REM ============================================================================
echo.
echo %YELLOW%[9/11] Running Base Trace Visualizer Tests...%RESET%
echo ------------------------------------------------------------------------
python -m pytest manim_visualizer/tests/test_base_trace_visualizer.py -v --tb=short 2>&1
if errorlevel 1 (
    echo %RED%Some tests failed%RESET%
    set /a TOTAL_FAILED+=1
) else (
    echo %GREEN%All tests passed%RESET%
    set /a TOTAL_PASSED+=1
)
set /a TEST_SECTIONS+=1

REM ============================================================================
REM Section 10: MCP Hub Tests (35 tests)
REM ============================================================================
echo.
echo %YELLOW%[10/11] Running MCP Hub Tests...%RESET%
echo ------------------------------------------------------------------------
python -m pytest tests/test_mcp_hub.py -v --tb=short 2>&1
if errorlevel 1 (
    echo %RED%Some tests failed%RESET%
    set /a TOTAL_FAILED+=1
) else (
    echo %GREEN%All tests passed%RESET%
    set /a TOTAL_PASSED+=1
)
set /a TEST_SECTIONS+=1

REM ============================================================================
REM Section 11: llama.cpp Installation Tests (36 tests)
REM ============================================================================
echo.
echo %YELLOW%[11/11] Running llama.cpp Installation Tests...%RESET%
echo ------------------------------------------------------------------------
python -m pytest tests/test_llama_cpp_installation.py -v --tb=short 2>&1
if errorlevel 1 (
    echo %RED%Some tests failed%RESET%
    set /a TOTAL_FAILED+=1
) else (
    echo %GREEN%All tests passed%RESET%
    set /a TOTAL_PASSED+=1
)
set /a TEST_SECTIONS+=1

REM ============================================================================
REM Summary
REM ============================================================================
echo.
echo %CYAN%============================================================================%RESET%
echo %CYAN%                           TEST RUN COMPLETE                                %RESET%
echo %CYAN%============================================================================%RESET%
echo.
echo Test Sections: %TEST_SECTIONS% total
echo   %GREEN%Passed: %TOTAL_PASSED%%RESET%
echo   %RED%Failed: %TOTAL_FAILED%%RESET%
echo.
echo Expected test counts per section:
echo   1. Runtime Instrumentor Unit:  18 tests
echo   2. Error Handling:             10 tests
echo   3. End-to-End:                 11 tests
echo   4. Protocol Detection:          4 tests
echo   5. AI Explanation:             22 tests
echo   6. Frame Bounds + Pacing:      43 tests
echo   7. Visual Regression:          15 tests
echo   8. E2E Regression:             22 tests
echo   9. Base Trace Visualizer:      18 tests
echo  10. MCP Hub:                    35 tests
echo  11. llama.cpp Installation:     36 tests
echo   ----------------------------------
echo   TOTAL:                        ~234 tests
echo.
echo Quick commands:
echo   python -m pytest tests/ -v                    # All root tests
echo   python -m pytest manim_visualizer/tests/ -v  # All manim tests
echo   python -m pytest -x                          # Stop on first failure
echo   python -m pytest --lf                        # Re-run last failed
echo.

cd /d %PROJECT_ROOT%
endlocal
