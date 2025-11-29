@echo off
REM ============================================================
REM TrueFlow: Enable Socket Tracing for Python Scripts
REM ============================================================
REM Usage: enable_tracing.bat your_script.py [args...]
REM        enable_tracing.bat start.bat [args...]
REM        enable_tracing.bat python your_script.py [args...]
REM
REM This script sets up the environment for socket-based tracing
REM and then runs the provided command with tracing enabled.
REM ============================================================

REM Get the directory where this script is located (.pycharm_plugin/runtime_injector)
set SCRIPT_DIR=%~dp0

REM Set environment variables for tracing
set PYCHARM_PLUGIN_TRACE_ENABLED=1
set PYCHARM_PLUGIN_SOCKET_TRACE=1
set PYCHARM_PLUGIN_TRACE_PORT=5678
set PYCHARM_PLUGIN_TRACE_HOST=127.0.0.1

REM Set PYTHONPATH to include the runtime_injector directory (for sitecustomize.py)
set PYTHONPATH=%SCRIPT_DIR%;%PYTHONPATH%

REM Trace output directory
set CRAWL4AI_TRACE_DIR=%SCRIPT_DIR%..\traces
if not exist "%CRAWL4AI_TRACE_DIR%" mkdir "%CRAWL4AI_TRACE_DIR%"

REM Enable UTF-8 for proper output
chcp 65001 >nul 2>&1
set PYTHONUTF8=1
set PYTHONIOENCODING=UTF-8

echo ============================================================
echo  TrueFlow Socket Tracing Enabled
echo ============================================================
echo  Trace Port: %PYCHARM_PLUGIN_TRACE_HOST%:%PYCHARM_PLUGIN_TRACE_PORT%
echo  PYTHONPATH: %PYTHONPATH%
echo  Trace Dir:  %CRAWL4AI_TRACE_DIR%
echo ============================================================
echo.
echo  Connect PyCharm TrueFlow plugin to receive trace events
echo  Or run: telnet localhost 5678 (to verify server)
echo.
echo ============================================================
echo.

REM Check if any arguments were provided
if "%~1"=="" (
    echo ERROR: No script or command provided
    echo.
    echo Usage:
    echo   enable_tracing.bat your_script.py [args...]
    echo   enable_tracing.bat python your_script.py [args...]
    echo   enable_tracing.bat start.bat [args...]
    exit /b 1
)

REM Run the provided command with all arguments
echo Running: %*
echo.
%*

REM Capture exit code
set EXIT_CODE=%ERRORLEVEL%

echo.
echo ============================================================
echo  Tracing session ended (exit code: %EXIT_CODE%)
echo ============================================================

exit /b %EXIT_CODE%
