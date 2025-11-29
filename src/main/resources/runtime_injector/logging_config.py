"""
Centralized Logging Configuration for Manim Visualizer

All manim visualizer modules use this for consistent logging to files.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime

# Log directory (same as plugin logs)
# __file__ is in: pycharm-plugin/manim_visualizer/logging_config.py
# OR in: .pycharm_plugin/manim_visualizer/logging_config.py (when deployed)
# Need to find project root and go to .pycharm_plugin/logs/

current_file = Path(__file__).resolve()

# Determine project root and log directory
# Find the project root by looking for .pycharm_plugin directory
project_root = None
for parent in [current_file.parent, current_file.parent.parent, current_file.parent.parent.parent]:
    if (parent / ".pycharm_plugin").exists():
        project_root = parent
        break

if project_root is None:
    # Fallback: assume we're in project root
    project_root = current_file.parent.parent.parent

# Always use project_root/.pycharm_plugin/logs
LOG_DIR = project_root / ".pycharm_plugin" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Date stamp for log files
DATE_STAMP = datetime.now().strftime("%Y%m%d")


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Set up logger with both file and console output.

    Args:
        name: Logger name (usually __name__ from calling module)
        level: Logging level (default: INFO)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid duplicate handlers - clear existing handlers first
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.setLevel(level)

    # Prevent propagation to root logger (avoids duplicate console output)
    logger.propagate = False

    # File handler - detailed logs
    log_file = LOG_DIR / f"manim_visualizer_{DATE_STAMP}.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)

    # Console handler - important messages only
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | [%(name)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)

    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# Pre-configured loggers for common modules
def get_queue_renderer_logger():
    """Get logger for queue_aware_renderer."""
    return setup_logger('queue_aware_renderer')


def get_procedural_viz_logger():
    """Get logger for procedural_trace_viz."""
    return setup_logger('procedural_trace_viz')


def get_llm_mapper_logger():
    """Get logger for llm_operation_mapper."""
    return setup_logger('llm_operation_mapper')


def get_operation_viz_logger():
    """Get logger for advanced_operation_viz."""
    return setup_logger('advanced_operation_viz')


def get_integration_test_logger():
    """Get logger for test_integration."""
    return setup_logger('test_integration')


# Log current configuration (only once, at module import)
_init_logger = setup_logger('logging_config')
_init_logger.info(f"Logging configured. Log directory: {LOG_DIR}")
_init_logger.info(f"Log file: manim_visualizer_{DATE_STAMP}.log")

# Capture Manim's own logger output
def capture_manim_logger():
    """
    Capture Manim's logger and redirect to our log file.
    This ensures all Manim rendering logs are captured.
    """
    try:
        import logging as _logging
        manim_logger = _logging.getLogger('manim')

        # Remove ALL of Manim's default handlers (including Rich handler)
        manim_logger.handlers.clear()

        # Add our file handler to Manim's logger
        log_file = LOG_DIR / f"manim_visualizer_{DATE_STAMP}.log"
        manim_file_handler = _logging.FileHandler(log_file, encoding='utf-8')
        manim_file_handler.setLevel(_logging.DEBUG)
        manim_formatter = _logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        manim_file_handler.setFormatter(manim_formatter)
        manim_logger.addHandler(manim_file_handler)

        # Add a simple console handler (replaces Rich handler)
        manim_console_handler = _logging.StreamHandler(sys.stdout)
        manim_console_handler.setLevel(_logging.INFO)
        manim_console_formatter = _logging.Formatter(
            '%(asctime)s | %(levelname)-8s | [%(name)s] %(message)s',
            datefmt='%H:%M:%S'
        )
        manim_console_handler.setFormatter(manim_console_formatter)
        manim_logger.addHandler(manim_console_handler)

        manim_logger.propagate = False
        _init_logger.info("Manim logger captured and redirected to plugin logs")
        return True
    except Exception as e:
        _init_logger.warning(f"Could not capture Manim logger: {e}")
        return False

# Try to capture Manim logger if it's already imported
if 'manim' in sys.modules:
    capture_manim_logger()
else:
    # If Manim isn't imported yet, visualizers should call capture_manim_logger() after importing
    _init_logger.debug("Manim not yet imported, call capture_manim_logger() after importing manim")


def ensure_manim_logging():
    """
    Call this after importing manim in your visualizer to ensure Manim logs are captured.

    Example:
        from manim import *
        from logging_config import ensure_manim_logging
        ensure_manim_logging()
    """
    if 'manim' not in sys.modules:
        _init_logger.warning("ensure_manim_logging() called but manim not imported yet")
        return False
    return capture_manim_logger()
