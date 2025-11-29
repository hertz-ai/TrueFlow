"""
PyCharm Plugin Logger

Centralized logging system for all pycharm-plugin components.
Logs are written to .pycharm_plugin/logs/ directory.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
import threading

# Global logger registry
_loggers = {}
_lock = threading.Lock()


def get_logger(name: str, log_dir: str = None) -> logging.Logger:
    """
    Get or create a logger for a specific component.

    Args:
        name: Logger name (e.g., "runtime_instrumentor", "auto_recorder")
        log_dir: Optional custom log directory (default: .pycharm_plugin/logs)

    Returns:
        Configured logger instance
    """
    with _lock:
        # Return existing logger if already created
        if name in _loggers:
            return _loggers[name]

        # Create new logger
        logger = logging.getLogger(f"pycharm_plugin.{name}")
        logger.setLevel(logging.DEBUG)

        # Remove existing handlers to avoid duplicates
        logger.handlers.clear()

        # Determine log directory
        if log_dir is None:
            # Default: .pycharm_plugin/logs/ in current directory
            log_dir = Path.cwd() / ".pycharm_plugin" / "logs"
        else:
            log_dir = Path(log_dir)

        # Create log directory if it doesn't exist
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create log file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d")
        log_file = log_dir / f"{name}_{timestamp}.log"

        # File handler - detailed logs
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Console handler - only warnings and errors by default
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.WARNING)
        console_formatter = logging.Formatter(
            fmt='[%(name)s] %(levelname)s: %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # Store in registry
        _loggers[name] = logger

        logger.info(f"Logger initialized - Log file: {log_file}")

        return logger


def set_console_level(logger_name: str, level: int):
    """
    Change console logging level for a specific logger.

    Args:
        logger_name: Name of the logger
        level: logging level (logging.DEBUG, logging.INFO, etc.)
    """
    if logger_name in _loggers:
        logger = _loggers[logger_name]
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stdout:
                handler.setLevel(level)


def enable_verbose(logger_name: str = None):
    """
    Enable verbose logging (DEBUG level) to console.

    Args:
        logger_name: Specific logger to make verbose (None = all loggers)
    """
    if logger_name:
        set_console_level(logger_name, logging.DEBUG)
    else:
        # Make all loggers verbose
        for name in _loggers:
            set_console_level(name, logging.DEBUG)


def disable_verbose(logger_name: str = None):
    """
    Disable verbose logging (back to WARNING level).

    Args:
        logger_name: Specific logger to quiet (None = all loggers)
    """
    if logger_name:
        set_console_level(logger_name, logging.WARNING)
    else:
        # Quiet all loggers
        for name in _loggers:
            set_console_level(name, logging.WARNING)


def cleanup_old_logs(days: int = 7, log_dir: str = None):
    """
    Clean up log files older than specified days.

    Args:
        days: Remove logs older than this many days
        log_dir: Log directory to clean (default: .pycharm_plugin/logs)
    """
    if log_dir is None:
        log_dir = Path.cwd() / ".pycharm_plugin" / "logs"
    else:
        log_dir = Path(log_dir)

    if not log_dir.exists():
        return

    import time
    cutoff_time = time.time() - (days * 86400)  # days to seconds

    removed_count = 0
    for log_file in log_dir.glob("*.log"):
        if log_file.stat().st_mtime < cutoff_time:
            try:
                log_file.unlink()
                removed_count += 1
            except Exception:
                pass

    if removed_count > 0:
        # Use logger if available, otherwise print
        if 'cleanup' in _loggers:
            _loggers['cleanup'].info(f"Cleaned up {removed_count} old log files")
        else:
            print(f"[PyCharm Plugin] Cleaned up {removed_count} old log files")


# Example usage
if __name__ == "__main__":
    print("="*70)
    print("LOGGER TEST - Centralized Logging Demo")
    print("="*70)

    # Test logger creation
    logger1 = get_logger("test_component")

    print("\n1. Testing logger methods:")
    logger1.debug("This is a debug message (file only)")
    logger1.info("This is an info message (file only)")
    logger1.warning("This is a warning (console + file)")
    logger1.error("This is an error (console + file)")

    # Enable verbose mode
    print("\n2. Enabling verbose mode...")
    enable_verbose("test_component")

    logger1.debug("Now debug messages appear on console too!")
    logger1.info("And info messages!")

    # Test exception logging
    print("\n3. Testing exception logging with traceback:")
    try:
        1 / 0
    except Exception as e:
        logger1.error("Division by zero error", exc_info=True)

    # Test cleanup
    print("\n4. Testing log cleanup...")
    cleanup_old_logs(days=7)

    print(f"\n5. Logs written to: {Path.cwd() / '.pycharm_plugin' / 'logs'}")
    print("\nCheck the log file for all logged messages including exception traceback!")
    print("="*70)
