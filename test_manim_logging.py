#!/usr/bin/env python
"""
Test script to verify Manim logging is captured.
"""

import sys
from pathlib import Path

# Add manim_visualizer to path
sys.path.insert(0, str(Path(__file__).parent / "pycharm-plugin" / "manim_visualizer"))

# Import logging config (this should capture Manim logger)
from logging_config import setup_logger

# Get a logger
logger = setup_logger('test_manim_logging')
logger.info("Test script started")

# Now import Manim (after logging_config has captured its logger)
try:
    from manim import logger as manim_logger
    logger.info("Manim imported successfully")

    # Try to log something with Manim's logger
    manim_logger.info("This is a test message from Manim's logger")
    manim_logger.debug("This is a debug message from Manim's logger")

    logger.info("Manim logging test completed")
    logger.info(f"Check log file at: {Path('.pycharm_plugin/logs').resolve()}")

except Exception as e:
    logger.error(f"Failed to test Manim logging: {e}")
    import traceback
    traceback.print_exc()
