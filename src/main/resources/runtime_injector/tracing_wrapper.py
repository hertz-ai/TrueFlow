#!/usr/bin/env python
"""
TrueFlow: Python Wrapper for Socket Tracing

Usage:
    python tracing_wrapper.py your_script.py [args...]
    python tracing_wrapper.py -m your_module [args...]

This wrapper sets up the tracing environment and then runs the target script.
It's useful when you can't modify PYTHONPATH externally.
"""

import os
import sys
import runpy

def setup_tracing():
    """Configure environment for TrueFlow socket tracing."""
    # Get the directory containing this wrapper
    wrapper_dir = os.path.dirname(os.path.abspath(__file__))

    # Set environment variables for tracing
    os.environ['PYCHARM_PLUGIN_TRACE_ENABLED'] = '1'
    os.environ['PYCHARM_PLUGIN_SOCKET_TRACE'] = '1'
    os.environ['PYCHARM_PLUGIN_TRACE_PORT'] = os.environ.get('PYCHARM_PLUGIN_TRACE_PORT', '5678')
    os.environ['PYCHARM_PLUGIN_TRACE_HOST'] = os.environ.get('PYCHARM_PLUGIN_TRACE_HOST', '127.0.0.1')

    # Add runtime_injector to path (for sitecustomize.py to load instrumentor)
    if wrapper_dir not in sys.path:
        sys.path.insert(0, wrapper_dir)

    # Set trace output directory
    trace_dir = os.path.join(os.path.dirname(wrapper_dir), 'traces')
    os.makedirs(trace_dir, exist_ok=True)
    os.environ['CRAWL4AI_TRACE_DIR'] = trace_dir

    print("=" * 60)
    print(" TrueFlow Socket Tracing Enabled (Python Wrapper)")
    print("=" * 60)
    print(f" Trace Port: {os.environ['PYCHARM_PLUGIN_TRACE_HOST']}:{os.environ['PYCHARM_PLUGIN_TRACE_PORT']}")
    print(f" Trace Dir:  {trace_dir}")
    print("=" * 60)
    print()

    # Now import the instrumentor to activate tracing
    try:
        import python_runtime_instrumentor
        print("[TrueFlow] Instrumentor loaded successfully")
    except ImportError as e:
        print(f"[TrueFlow] Warning: Could not load instrumentor: {e}")

    print()


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python tracing_wrapper.py your_script.py [args...]")
        print("  python tracing_wrapper.py -m your_module [args...]")
        sys.exit(1)

    # Setup tracing first
    setup_tracing()

    # Get the target script/module
    target = sys.argv[1]

    # Remove wrapper from argv so target script sees correct args
    sys.argv = sys.argv[1:]

    if target == '-m':
        # Run as module: python tracing_wrapper.py -m module_name [args...]
        if len(sys.argv) < 2:
            print("ERROR: Module name required after -m")
            sys.exit(1)
        module_name = sys.argv[1]
        sys.argv = sys.argv[1:]  # Remove -m from args
        print(f"Running module: {module_name}")
        print()
        runpy.run_module(module_name, run_name='__main__', alter_sys=True)
    else:
        # Run as script: python tracing_wrapper.py script.py [args...]
        script_path = os.path.abspath(target)
        if not os.path.exists(script_path):
            print(f"ERROR: Script not found: {script_path}")
            sys.exit(1)

        # Add script's directory to path
        script_dir = os.path.dirname(script_path)
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)

        print(f"Running script: {script_path}")
        print()

        # Run the script
        runpy.run_path(script_path, run_name='__main__')


if __name__ == '__main__':
    main()
