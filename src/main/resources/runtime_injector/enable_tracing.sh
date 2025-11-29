#!/bin/bash
# ============================================================
# TrueFlow: Enable Socket Tracing for Python Scripts
# ============================================================
# Usage: ./enable_tracing.sh your_script.py [args...]
#        ./enable_tracing.sh ./start.sh [args...]
#        ./enable_tracing.sh python your_script.py [args...]
#
# This script sets up the environment for socket-based tracing
# and then runs the provided command with tracing enabled.
# ============================================================

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Set environment variables for tracing
export PYCHARM_PLUGIN_TRACE_ENABLED=1
export PYCHARM_PLUGIN_SOCKET_TRACE=1
export PYCHARM_PLUGIN_TRACE_PORT=5678
export PYCHARM_PLUGIN_TRACE_HOST=127.0.0.1

# Set PYTHONPATH to include the runtime_injector directory (for sitecustomize.py)
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH}"

# Trace output directory
export CRAWL4AI_TRACE_DIR="${SCRIPT_DIR}/../traces"
mkdir -p "${CRAWL4AI_TRACE_DIR}"

# Enable UTF-8
export PYTHONIOENCODING=UTF-8
export PYTHONUTF8=1

echo "============================================================"
echo " TrueFlow Socket Tracing Enabled"
echo "============================================================"
echo " Trace Port: ${PYCHARM_PLUGIN_TRACE_HOST}:${PYCHARM_PLUGIN_TRACE_PORT}"
echo " PYTHONPATH: ${PYTHONPATH}"
echo " Trace Dir:  ${CRAWL4AI_TRACE_DIR}"
echo "============================================================"
echo ""
echo " Connect PyCharm TrueFlow plugin to receive trace events"
echo " Or run: nc -zv localhost 5678 (to verify server)"
echo ""
echo "============================================================"
echo ""

# Check if any arguments were provided
if [ $# -eq 0 ]; then
    echo "ERROR: No script or command provided"
    echo ""
    echo "Usage:"
    echo "  ./enable_tracing.sh your_script.py [args...]"
    echo "  ./enable_tracing.sh python your_script.py [args...]"
    echo "  ./enable_tracing.sh ./start.sh [args...]"
    exit 1
fi

# Run the provided command with all arguments
echo "Running: $@"
echo ""
"$@"

# Capture exit code
EXIT_CODE=$?

echo ""
echo "============================================================"
echo " Tracing session ended (exit code: ${EXIT_CODE})"
echo "============================================================"

exit ${EXIT_CODE}
