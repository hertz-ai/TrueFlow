"""
Site customization file that automatically loads the runtime instrumentor.
This file is executed automatically by Python at startup (before any user code).

Place this file in PYTHONPATH or use: python -m site
"""

import os
import sys

# Debug: Always print to confirm sitecustomize.py is being loaded
print("[PyCharm Plugin] sitecustomize.py loaded from: {0}".format(__file__))
print("[PyCharm Plugin] PYCHARM_PLUGIN_TRACE_ENABLED = {0}".format(os.getenv('PYCHARM_PLUGIN_TRACE_ENABLED')))
print("[PyCharm Plugin] PYCHARM_PLUGIN_SOCKET_TRACE = {0}".format(os.getenv('PYCHARM_PLUGIN_SOCKET_TRACE')))
print("[PyCharm Plugin] PYTHONPATH = {0}".format(os.getenv('PYTHONPATH')))

# Only load if explicitly enabled via environment variable
if os.getenv('PYCHARM_PLUGIN_TRACE_ENABLED') == '1':
    print("[PyCharm Plugin] Attempting to load instrumentor...")
    try:
        # Import the runtime instrumentor from the same directory
        import python_runtime_instrumentor
        print("[PyCharm Plugin] Instrumentor loaded successfully!")
    except Exception as e:
        print("[PyCharm Plugin] Failed to load instrumentor: {0}".format(str(e)))
        import traceback
        traceback.print_exc()
else:
    print("[PyCharm Plugin] Tracing not enabled (PYCHARM_PLUGIN_TRACE_ENABLED != '1')")
