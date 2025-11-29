# ============================================================
# TrueFlow: Enable Socket Tracing for Python Scripts (PowerShell)
# ============================================================
# Usage: .\enable_tracing.ps1 your_script.py [args...]
#        .\enable_tracing.ps1 .\start.ps1 [args...]
#        .\enable_tracing.ps1 python your_script.py [args...]
#
# This script sets up the environment for socket-based tracing
# and then runs the provided command with tracing enabled.
# ============================================================

param(
    [Parameter(Position=0, Mandatory=$false)]
    [string]$Command,

    [Parameter(Position=1, ValueFromRemainingArguments=$true)]
    [string[]]$Arguments
)

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Set environment variables for tracing
$env:PYCHARM_PLUGIN_TRACE_ENABLED = "1"
$env:PYCHARM_PLUGIN_SOCKET_TRACE = "1"
$env:PYCHARM_PLUGIN_TRACE_PORT = "5678"
$env:PYCHARM_PLUGIN_TRACE_HOST = "127.0.0.1"

# Set PYTHONPATH to include the runtime_injector directory (for sitecustomize.py)
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$ScriptDir;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $ScriptDir
}

# Trace output directory
$env:CRAWL4AI_TRACE_DIR = Join-Path (Split-Path -Parent $ScriptDir) "traces"
if (-not (Test-Path $env:CRAWL4AI_TRACE_DIR)) {
    New-Item -ItemType Directory -Path $env:CRAWL4AI_TRACE_DIR -Force | Out-Null
}

# Enable UTF-8
$env:PYTHONIOENCODING = "UTF-8"
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " TrueFlow Socket Tracing Enabled" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Trace Port: $env:PYCHARM_PLUGIN_TRACE_HOST`:$env:PYCHARM_PLUGIN_TRACE_PORT" -ForegroundColor Yellow
Write-Host " PYTHONPATH: $env:PYTHONPATH" -ForegroundColor Yellow
Write-Host " Trace Dir:  $env:CRAWL4AI_TRACE_DIR" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host " Connect PyCharm TrueFlow plugin to receive trace events" -ForegroundColor White
Write-Host " Or run: Test-NetConnection localhost -Port 5678" -ForegroundColor White
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if any arguments were provided
if (-not $Command) {
    Write-Host "ERROR: No script or command provided" -ForegroundColor Red
    Write-Host ""
    Write-Host "Usage:" -ForegroundColor White
    Write-Host "  .\enable_tracing.ps1 your_script.py [args...]" -ForegroundColor Gray
    Write-Host "  .\enable_tracing.ps1 python your_script.py [args...]" -ForegroundColor Gray
    Write-Host "  .\enable_tracing.ps1 .\start.ps1 [args...]" -ForegroundColor Gray
    exit 1
}

# Build the full command
$FullCommand = $Command
if ($Arguments) {
    $FullCommand = "$Command $($Arguments -join ' ')"
}

Write-Host "Running: $FullCommand" -ForegroundColor White
Write-Host ""

# Run the provided command
try {
    if ($Arguments) {
        & $Command @Arguments
    } else {
        & $Command
    }
    $ExitCode = $LASTEXITCODE
} catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
    $ExitCode = 1
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Tracing session ended (exit code: $ExitCode)" -ForegroundColor $(if ($ExitCode -eq 0) { "Green" } else { "Red" })
Write-Host "============================================================" -ForegroundColor Cyan

exit $ExitCode
