@echo off
REM Enable PyCharm Plugin Tracing for any Python script or batch file
REM Usage: enable_tracing.bat your_script.py
REM        enable_tracing.bat start.bat

REM Get the directory where this script is located
set SCRIPT_DIR=%~dp0

REM Set environment variables for tracing
set PYCHARM_PLUGIN_TRACE_ENABLED=1
set CRAWL4AI_TRACE_DIR=%SCRIPT_DIR%..\traces
set PYTHONPATH=%SCRIPT_DIR%

echo [PyCharm Plugin] Tracing enabled
echo [PyCharm Plugin] PYTHONPATH=%PYTHONPATH%
echo [PyCharm Plugin] Trace directory: %CRAWL4AI_TRACE_DIR%
echo.

REM Run the provided command with all arguments
%*
