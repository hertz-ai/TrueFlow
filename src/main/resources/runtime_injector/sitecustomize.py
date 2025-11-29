"""
Site customization file that automatically loads the runtime instrumentor.
This file is executed automatically by Python at startup (before any user code).

Place this file in PYTHONPATH or use: python -m site
"""

import os
import sys

# Support both TRUEFLOW_ENABLED and PYCHARM_PLUGIN_TRACE_ENABLED
trace_enabled = (
    os.getenv('TRUEFLOW_ENABLED') == '1' or
    os.getenv('PYCHARM_PLUGIN_TRACE_ENABLED') == '1'
)

# Debug: Always print to confirm sitecustomize.py is being loaded
print("[TrueFlow] sitecustomize.py loaded from: {0}".format(__file__))
print("[TrueFlow] TRUEFLOW_ENABLED = {0}".format(os.getenv('TRUEFLOW_ENABLED')))
print("[TrueFlow] PYCHARM_PLUGIN_TRACE_ENABLED = {0}".format(os.getenv('PYCHARM_PLUGIN_TRACE_ENABLED')))
print("[TrueFlow] PYTHONPATH = {0}".format(os.getenv('PYTHONPATH')))

# Only load if explicitly enabled via environment variable
if trace_enabled:
    print("[TrueFlow] Attempting to load instrumentor...")
    try:
        # Import the runtime instrumentor from the same directory
        import python_runtime_instrumentor
        print("[TrueFlow] Instrumentor loaded successfully!")
    except Exception as e:
        print("[TrueFlow] Failed to load instrumentor: {0}".format(str(e)))
        import traceback
        traceback.print_exc()
else:
    print("[TrueFlow] Tracing not enabled (set TRUEFLOW_ENABLED=1 or PYCHARM_PLUGIN_TRACE_ENABLED=1)")
