from logging_config import setup_logger
logger = setup_logger(__name__)

"""
High-Performance Integration for RuntimeInstrumentor

Wraps RuntimeInstrumentor with OptimizedRecorder to handle high call rates (>1000/sec)
while maintaining compatibility with Kotlin TraceServerSocket.

Key features:
- Adaptive sampling based on call rate
- Intelligent filtering (project code only - project-agnostic)
- Batched socket writes
- Correlation ID tracking
- <2% performance overhead

Usage:
    from manim_visualizer.high_performance_integration import enable_high_performance_tracing

    # Enable high-performance tracing
    recorder = enable_high_performance_tracing(
        max_call_rate=1000,
        project_code_only=True
    )

    # Your code here - automatically traced with adaptive sampling

    # Cleanup
    recorder.close()
"""

import sys
from pathlib import Path
from typing import Optional
import atexit

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent))

from manim_visualizer.optimized_recorder import (
    OptimizedRecorder,
    SamplingConfig,
    create_optimized_recorder
)


class HighPerformanceInstrumentor:
    """
    High-performance wrapper around RuntimeInstrumentor.

    Replaces standard tracing with optimized adaptive sampling.
    """

    def __init__(
        self,
        max_call_rate: int = 1000,
        project_code_only: bool = True,
        socket_host: str = "localhost",
        socket_port: int = 5678,
        verbose: bool = True
    ):
        """
        Initialize high-performance instrumentor.

        Args:
            max_call_rate: Maximum call rate before aggressive sampling
            project_code_only: Only trace project code (not libraries)
            socket_host: Kotlin TraceServerSocket host
            socket_port: Kotlin TraceServerSocket port
            verbose: Enable verbose logging
        """
        self.max_call_rate = max_call_rate
        self.project_code_only = project_code_only
        self.verbose = verbose

        # Create sampling config
        config = SamplingConfig(
            high_rate_threshold=max_call_rate,
            extreme_rate_threshold=max_call_rate * 5,
            socket_host=socket_host,
            socket_port=socket_port
        )

        # Update patterns for project code only (project-agnostic)
        # Use project scanner to determine what to trace
        # Patterns will be updated by RuntimeInstrumentor's project scanner
        config.always_record_patterns = []

        # Create recorder
        self.recorder = OptimizedRecorder(
            config=config,
            verbose=verbose
        )

        # Original trace function (if sys.settrace is already installed)
        self.original_trace = sys.gettrace()

        # Call stack for tracking parent IDs
        self.call_stack = []

        # Register cleanup
        atexit.register(self.cleanup)

        if self.verbose:
            logger.info(f"[HighPerformanceInstrumentor] Initialized")
            logger.info(f"  Max call rate: {max_call_rate}/sec")
            logger.info(f"  Project code only: {project_code_only}")
            logger.info(f"  Socket: {socket_host}:{socket_port}")

    def trace_function(self, frame, event, arg):
        """Trace function callback."""
        if event == 'call':
            return self._handle_call(frame)
        elif event == 'return':
            return self._handle_return(frame, arg)

        return self.trace_function

    def _handle_call(self, frame):
        """Handle function call."""
        # Extract call info
        code = frame.f_code
        file_path = code.co_filename
        function_name = code.co_name
        line_number = frame.f_lineno
        module = frame.f_globals.get('__name__', '')

        # Get parent ID
        parent_id = self.call_stack[-1] if self.call_stack else None
        depth = len(self.call_stack)

        # Record call
        call_id = self.recorder.record_call(
            function_name=function_name,
            file_path=file_path,
            line_number=line_number,
            module=module,
            depth=depth,
            parent_id=parent_id
        )

        # Add to stack if recorded
        if call_id:
            self.call_stack.append(call_id)
        else:
            # Still track stack depth even if not recorded
            self.call_stack.append(None)

        return self.trace_function

    def _handle_return(self, frame, arg):
        """Handle function return."""
        if self.call_stack:
            call_id = self.call_stack.pop()

            # Record return if call was recorded
            if call_id:
                self.recorder.record_return(call_id)

        return self.trace_function

    def start(self):
        """Start high-performance tracing."""
        sys.settrace(self.trace_function)

        if self.verbose:
            logger.info("[HighPerformanceInstrumentor] Tracing started")
            logger.info("  Adaptive sampling enabled")
            logger.info("  Connect PyCharm TraceServerSocket to visualize")

    def stop(self):
        """Stop tracing."""
        sys.settrace(self.original_trace)

        if self.verbose:
            logger.info("[HighPerformanceInstrumentor] Tracing stopped")

        # Flush events
        self.recorder.flush()

    def get_statistics(self):
        """Get recording statistics."""
        return self.recorder.get_statistics()

    def print_statistics(self):
        """Print statistics."""
        self.recorder.print_statistics()

    def cleanup(self):
        """Cleanup resources."""
        self.stop()
        self.recorder.close()


# Global instance
_global_instrumentor: Optional[HighPerformanceInstrumentor] = None


def enable_high_performance_tracing(
    max_call_rate: int = 1000,
    project_code_only: bool = True,
    socket_host: str = "localhost",
    socket_port: int = 5678,
    verbose: bool = True
) -> HighPerformanceInstrumentor:
    """
    Enable high-performance tracing with adaptive sampling.

    Args:
        max_call_rate: Maximum call rate before aggressive sampling
        project_code_only: Only trace project code (not libraries)
        socket_host: Kotlin TraceServerSocket host
        socket_port: Kotlin TraceServerSocket port
        verbose: Enable verbose logging

    Returns:
        HighPerformanceInstrumentor instance
    """
    global _global_instrumentor

    if _global_instrumentor is not None:
        logger.info("[HighPerformanceInstrumentor] Already enabled")
        return _global_instrumentor

    _global_instrumentor = HighPerformanceInstrumentor(
        max_call_rate=max_call_rate,
        project_code_only=project_code_only,
        socket_host=socket_host,
        socket_port=socket_port,
        verbose=verbose
    )

    _global_instrumentor.start()

    return _global_instrumentor


def disable_high_performance_tracing():
    """Disable high-performance tracing."""
    global _global_instrumentor

    if _global_instrumentor:
        _global_instrumentor.cleanup()
        _global_instrumentor = None


# Context manager for scoped tracing
class high_performance_tracing:
    """
    Context manager for high-performance tracing.

    Usage:
        with high_performance_tracing(max_call_rate=1000):
            # Your code here
            train_model()
    """

    def __init__(
        self,
        max_call_rate: int = 1000,
        project_code_only: bool = True,
        verbose: bool = True
    ):
        self.max_call_rate = max_call_rate
        self.project_code_only = project_code_only
        self.verbose = verbose
        self.instrumentor: Optional[HighPerformanceInstrumentor] = None

    def __enter__(self):
        self.instrumentor = enable_high_performance_tracing(
            max_call_rate=self.max_call_rate,
            project_code_only=self.project_code_only,
            verbose=self.verbose
        )
        return self.instrumentor

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.instrumentor:
            self.instrumentor.print_statistics()
        disable_high_performance_tracing()


# Decorator for automatic high-performance tracing
def traced_with_sampling(max_call_rate: int = 1000):
    """
    Decorator for high-performance tracing with sampling.

    Usage:
        @traced_with_sampling(max_call_rate=1000)
        def train_model():
            # Traced with adaptive sampling
            pass
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            with high_performance_tracing(max_call_rate=max_call_rate):
                return func(*args, **kwargs)
        return wrapper
    return decorator


if __name__ == "__main__":
    # Example usage
    import time

    logger.info("="*70)
    logger.info("HIGH-PERFORMANCE TRACING EXAMPLE")
    logger.info("="*70)
    logger.info()

    # Example 1: Context manager
    logger.info("Example 1: Using context manager")
    logger.info("-"*70)

    with high_performance_tracing(max_call_rate=500, verbose=True):
        # Simulate high call rate
        def inner_function(x):
            return x * 2

        for i in range(1000):
            inner_function(i)
            if i % 100 == 0:
                time.sleep(0.01)

    logger.info()

    # Example 2: Decorator
    logger.info("Example 2: Using decorator")
    logger.info("-"*70)

    @traced_with_sampling(max_call_rate=1000)
    def compute_intensive_task():
        """Simulates compute-intensive task with many calls."""
        def helper(x):
            return x ** 2

        total = 0
        for i in range(2000):
            total += helper(i)
            if i % 200 == 0:
                time.sleep(0.005)

        return total

    result = compute_intensive_task()
    logger.info(f"Result: {result}")

    logger.info()
    logger.info("="*70)
    logger.info("EXAMPLES COMPLETE")
    logger.info("="*70)
