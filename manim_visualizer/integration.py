from logging_config import setup_logger
logger = setup_logger(__name__)

"""
Integration module for connecting RuntimeInstrumentor with Manim visualizer.

Provides convenience functions and decorators for easy integration.
"""

import sys
import os
from pathlib import Path
from typing import Optional, Callable
from functools import wraps
import atexit

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime_injector.python_runtime_instrumentor import (
    RuntimeInstrumentor,
    TraceSocketServer
)
from manim_visualizer.realtime_visualizer import RealtimeTraceVisualizer
from manim_visualizer.config import get_config
from manim_visualizer.auto_recorder import (
    get_recorder,
    track_execution,
    tracked_execution
)

# Export auto recorder utilities
__all__ = [
    'ManimTracingContext',
    'trace_with_manim',
    'tracer',
    'quick_visualize',
    'get_recorder',
    'track_execution',
    'tracked_execution'
]


class ManimTracingContext:
    """
    Context manager for easy tracing with Manim visualization.

    Usage:
        with ManimTracingContext(realtime=True):
            # Your code here
            learner.train()
    """

    def __init__(
        self,
        project_root: Optional[str] = None,
        output_file: str = "trace.json",
        realtime: bool = False,
        quality: str = "medium",
        auto_visualize: bool = True
    ):
        """
        Initialize tracing context.

        Args:
            project_root: Project root directory (auto-detected if None)
            output_file: Output trace file name
            realtime: Enable real-time visualization
            quality: Rendering quality (low, medium, high, production)
            auto_visualize: Automatically visualize after tracing
        """
        if project_root is None:
            # Auto-detect project root (project-agnostic)
            from auto_recorder import AutoRecorder
            project_root = AutoRecorder._detect_project_root()

        self.project_root = project_root or str(Path.cwd())
        self.output_file = output_file
        self.realtime = realtime
        self.quality = quality
        self.auto_visualize = auto_visualize

        self.instrumentor: Optional[RuntimeInstrumentor] = None
        self.server: Optional[TraceSocketServer] = None
        self.visualizer: Optional[RealtimeTraceVisualizer] = None

    def __enter__(self):
        """Start tracing."""
        # Create instrumentor
        self.instrumentor = RuntimeInstrumentor(
            project_root=self.project_root,
            output_format="json"
        )

        # Start real-time visualization if requested
        if self.realtime:
            # Start socket server
            self.server = TraceSocketServer(self.instrumentor, port=5678)
            self.server.start()
            logger.info("[ManimTracing] Socket server started on port 5678")

            # Start visualizer
            config = get_config(self.quality)
            self.visualizer = RealtimeTraceVisualizer(
                host="localhost",
                port=5678,
                config=config
            )
            self.visualizer.start()
            logger.info(f"[ManimTracing] Real-time visualization started ({self.quality} quality)")

        # Start tracing
        self.instrumentor.start_trace()
        logger.info("[ManimTracing] Tracing started")

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop tracing and generate visualization."""
        # Stop tracing
        if self.instrumentor:
            self.instrumentor.stop_trace()
            logger.info("[ManimTracing] Tracing stopped")

            # Export trace
            self.instrumentor.export_json(self.output_file)
            logger.info(f"[ManimTracing] Trace exported to {self.output_file}")

        # Stop real-time visualization
        if self.visualizer:
            self.visualizer.stop()
            logger.info("[ManimTracing] Real-time visualization stopped")

        if self.server:
            self.server.stop()
            logger.info("[ManimTracing] Socket server stopped")

        # Auto-visualize if requested and not real-time
        if self.auto_visualize and not self.realtime:
            from manim_visualizer.realtime_visualizer import BatchTraceVisualizer

            logger.info(f"[ManimTracing] Generating animation ({self.quality} quality)...")
            config = get_config(self.quality)
            visualizer = BatchTraceVisualizer(config=config)

            output_path = str(Path(self.output_file).with_suffix('.mp4'))
            visualizer.visualize_trace_file(self.output_file, output_path)
            logger.info(f"[ManimTracing] Animation saved to {output_path}")


def trace_with_manim(
    output_file: str = "trace.json",
    realtime: bool = False,
    quality: str = "medium",
    auto_visualize: bool = True
):
    """
    Decorator to trace a function with Manim visualization.

    Usage:
        @trace_with_manim(realtime=True, quality="high")
        def train_model():
            # Your code here
            pass

        train_model()
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            with ManimTracingContext(
                output_file=output_file,
                realtime=realtime,
                quality=quality,
                auto_visualize=auto_visualize
            ):
                return func(*args, **kwargs)
        return wrapper
    return decorator


class GlobalManimTracer:
    """
    Global singleton for easy tracing setup.

    Usage:
        from manim_visualizer.integration import tracer

        tracer.start(realtime=True)
        # Your code here
        tracer.stop()
    """

    def __init__(self):
        self.context: Optional[ManimTracingContext] = None
        self._active = False

    def start(
        self,
        project_root: Optional[str] = None,
        output_file: str = "trace.json",
        realtime: bool = False,
        quality: str = "medium",
        auto_visualize: bool = True
    ):
        """Start global tracing."""
        if self._active:
            logger.info("[ManimTracing] Already active, stopping previous session")
            self.stop()

        self.context = ManimTracingContext(
            project_root=project_root,
            output_file=output_file,
            realtime=realtime,
            quality=quality,
            auto_visualize=auto_visualize
        )
        self.context.__enter__()
        self._active = True

        # Register cleanup on exit
        atexit.register(self.stop)

    def stop(self):
        """Stop global tracing."""
        if self.context and self._active:
            self.context.__exit__(None, None, None)
            self._active = False

    @property
    def active(self) -> bool:
        """Check if tracing is active."""
        return self._active


# Global tracer instance
tracer = GlobalManimTracer()


# Convenience function for quick visualization
def quick_visualize(
    trace_file: str,
    quality: str = "medium",
    output_file: Optional[str] = None
):
    """
    Quick visualization of existing trace file.

    Args:
        trace_file: Path to trace JSON file
        quality: Rendering quality
        output_file: Output video path (auto-generated if None)

    Returns:
        Path to generated video
    """
    from manim_visualizer.realtime_visualizer import BatchTraceVisualizer

    config = get_config(quality)
    visualizer = BatchTraceVisualizer(config=config)

    if output_file is None:
        output_file = str(Path(trace_file).with_suffix('.mp4'))

    return visualizer.visualize_trace_file(trace_file, output_file)


# Example usage script
def example_usage():
    """Example demonstrating different usage patterns."""
    logger.info("=== Manim Tracer Examples ===\n")

    # Example 1: Context manager
    logger.info("Example 1: Context Manager")
    logger.info("---------------------------")
    print("""
with ManimTracingContext(realtime=True, quality="medium"):
    # Your code here
    learner = RealityGroundedLearner()
    learner.train()
    """)

    # Example 2: Decorator
    logger.info("\nExample 2: Decorator")
    logger.info("--------------------")
    print("""
@trace_with_manim(realtime=True, quality="high")
def train_model():
    learner = RealityGroundedLearner()
    learner.train()

train_model()
    """)

    # Example 3: Global tracer
    logger.info("\nExample 3: Global Tracer")
    logger.info("------------------------")
    print("""
from manim_visualizer.integration import tracer

tracer.start(realtime=True, quality="medium")

# Your code here
learner = RealityGroundedLearner()
learner.train()

tracer.stop()
    """)

    # Example 4: Quick visualize
    logger.info("\nExample 4: Quick Visualization")
    logger.info("-------------------------------")
    print("""
from manim_visualizer.integration import quick_visualize

video_path = quick_visualize("trace.json", quality="high")
logger.info(f"Video saved to {video_path}")
    """)

    logger.info("\n=== End Examples ===")


if __name__ == "__main__":
    example_usage()
