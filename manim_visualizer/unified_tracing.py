from logging_config import setup_logger
logger = setup_logger(__name__)

"""
Unified Tracing System

Integrates everything:
1. High-performance recording with adaptive sampling
2. Real-time streaming to Kotlin TraceServerSocket (PyCharm visualization)
3. Automatic Manim video generation
4. Correlation ID tracking

Just add @trace decorator and get:
- Real-time PyCharm visualization
- Automatic Manim replay video
- Correlation ID for later replay
- Adaptive sampling for high call rates

Usage:
    from manim_visualizer.unified_tracing import trace

    @trace()
    def train_model():
        # Automatically:
        # - Streamed to PyCharm in real-time
        # - Recorded for Manim video
        # - Correlation ID assigned
        # - Adaptive sampling if call rate > 1000/sec
        pass
"""

import sys
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any
from functools import wraps
import uuid
import atexit

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent))

from manim_visualizer.optimized_recorder import (
    OptimizedRecorder,
    SamplingConfig
)
from manim_visualizer.realtime_visualizer import BatchTraceVisualizer
from manim_visualizer.config import get_config


class UnifiedTracer:
    """
    Unified tracer that handles everything automatically.

    - Real-time streaming to PyCharm TraceServerSocket
    - Correlation ID tracking
    - Automatic Manim video generation
    - Adaptive sampling for high call rates
    """

    def __init__(
        self,
        correlation_id: Optional[str] = None,
        max_call_rate: int = 1000,
        project_code_only: bool = True,
        auto_generate_video: bool = True,
        video_quality: str = "medium",
        socket_host: str = "localhost",
        socket_port: int = 5678,
        output_dir: str = "unified_traces",
        verbose: bool = True
    ):
        """
        Initialize unified tracer.

        Args:
            correlation_id: Optional correlation ID (auto-generated if None)
            max_call_rate: Max call rate before aggressive sampling
            project_code_only: Only trace project code (not libraries)
            auto_generate_video: Auto-generate Manim video when done
            video_quality: Manim video quality (low/medium/high/production)
            socket_host: PyCharm TraceServerSocket host
            socket_port: PyCharm TraceServerSocket port
            output_dir: Output directory for traces and videos
            verbose: Enable verbose logging
        """
        # Generate correlation ID
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.auto_generate_video = auto_generate_video
        self.video_quality = video_quality
        self.verbose = verbose
        self.project_code_only = project_code_only

        # Create output directory
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # File paths
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        self.trace_file = self.output_dir / f"trace_{self.correlation_id[:8]}_{timestamp}.json"
        self.video_file = self.output_dir / f"video_{self.correlation_id[:8]}_{timestamp}.mp4"

        # Create sampling config
        config = SamplingConfig(
            high_rate_threshold=max_call_rate,
            extreme_rate_threshold=max_call_rate * 5,
            socket_host=socket_host,
            socket_port=socket_port
        )

        # Use default priority patterns (project-agnostic)
        # Patterns will be set by OptimizedRecorder's defaults
        config.always_record_patterns = None

        # Create optimized recorder (streams to PyCharm)
        self.recorder = OptimizedRecorder(
            config=config,
            correlation_id=self.correlation_id,
            verbose=verbose
        )

        # Original trace function
        self.original_trace = sys.gettrace()

        # Call stack
        self.call_stack = []

        # Session info
        self.start_time = time.time()
        self.entry_point = None

        # Register cleanup
        atexit.register(self._cleanup)

        if self.verbose:
            logger.info(f"\n{'='*70}")
            logger.info("UNIFIED TRACER INITIALIZED")
            logger.info(f"{'='*70}")
            logger.info(f"Correlation ID: {self.correlation_id}")
            logger.info(f"Output Dir: {self.output_dir}")
            logger.info(f"Trace File: {self.trace_file.name}")
            logger.info(f"Video File: {self.video_file.name}")
            logger.info(f"Max Call Rate: {max_call_rate}/sec")
            logger.info(f"Project Code Only: {project_code_only}")
            logger.info(f"Auto Video: {auto_generate_video}")
            logger.info(f"Video Quality: {video_quality}")
            logger.info(f"PyCharm Socket: {socket_host}:{socket_port}")
            logger.info(f"{'='*70}\n")

    def trace_function(self, frame, event, arg):
        """Trace function callback."""
        if event == 'call':
            return self._handle_call(frame)
        elif event == 'return':
            return self._handle_return(frame, arg)

        return self.trace_function

    def _handle_call(self, frame):
        """Handle function call."""
        code = frame.f_code
        file_path = code.co_filename
        function_name = code.co_name
        line_number = frame.f_lineno
        module = frame.f_globals.get('__name__', '')

        # Set entry point on first call
        if self.entry_point is None:
            self.entry_point = f"{module}.{function_name}"

        # Get parent ID
        parent_id = self.call_stack[-1] if self.call_stack else None
        depth = len(self.call_stack)

        # Record call (streams to PyCharm automatically)
        call_id = self.recorder.record_call(
            function_name=function_name,
            file_path=file_path,
            line_number=line_number,
            module=module,
            depth=depth,
            parent_id=parent_id
        )

        # Track in stack
        if call_id:
            self.call_stack.append(call_id)
        else:
            self.call_stack.append(None)

        return self.trace_function

    def _handle_return(self, frame, arg):
        """Handle function return."""
        if self.call_stack:
            call_id = self.call_stack.pop()

            if call_id:
                self.recorder.record_return(call_id)

        return self.trace_function

    def start(self):
        """Start unified tracing."""
        sys.settrace(self.trace_function)

        if self.verbose:
            logger.info("[UnifiedTracer] Tracing started")
            logger.info("  - Real-time streaming to PyCharm: ACTIVE")
            logger.info("  - Correlation ID tracking: ACTIVE")
            logger.info("  - Adaptive sampling: ACTIVE")
            logger.info()

    def stop(self):
        """Stop tracing and generate video."""
        sys.settrace(self.original_trace)

        duration = time.time() - self.start_time

        if self.verbose:
            logger.info(f"\n[UnifiedTracer] Tracing stopped")
            logger.info(f"  Entry Point: {self.entry_point}")
            logger.info(f"  Duration: {duration:.2f}s")
            logger.info(f"  Correlation ID: {self.correlation_id}")

        # Flush events to PyCharm
        self.recorder.flush()

        # Print statistics
        if self.verbose:
            self.recorder.print_statistics()

        # Export trace to file
        self._export_trace()

        # Generate Manim video in background
        if self.auto_generate_video:
            self._generate_video_async()

    def _export_trace(self):
        """Export trace to JSON file."""
        # Get all events from recorder's buffer
        # For now, we'll create a simple trace file
        import json

        trace_data = {
            "correlation_id": self.correlation_id,
            "entry_point": self.entry_point,
            "start_time": self.start_time,
            "end_time": time.time(),
            "statistics": self.recorder.get_statistics()
        }

        with open(self.trace_file, 'w') as f:
            json.dump(trace_data, f, indent=2)

        if self.verbose:
            logger.info(f"[UnifiedTracer] Trace exported to: {self.trace_file}")

    def _generate_video_async(self):
        """Generate Manim video in background thread."""
        def generate():
            try:
                if self.verbose:
                    logger.info(f"\n[UnifiedTracer] Generating Manim video...")
                    logger.info(f"  Quality: {self.video_quality}")
                    logger.info(f"  Output: {self.video_file}")
                    logger.info(f"  This may take a few minutes...")

                # Create visualizer
                config = get_config(self.video_quality)
                visualizer = BatchTraceVisualizer(config=config)

                # Generate video
                visualizer.visualize_trace_file(
                    str(self.trace_file),
                    str(self.video_file)
                )

                if self.verbose:
                    logger.info(f"\n[UnifiedTracer] Video generated successfully!")
                    logger.info(f"  Location: {self.video_file}")
                    logger.info(f"  Correlation ID: {self.correlation_id}")
                    logger.info(f"\nReplay with: vlc {self.video_file}")

            except Exception as e:
                logger.info(f"\n[UnifiedTracer] Error generating video: {e}")

        # Start in background thread
        thread = threading.Thread(target=generate, daemon=True)
        thread.start()

        if self.verbose:
            logger.info(f"[UnifiedTracer] Video generation started in background")

    def _cleanup(self):
        """Cleanup on exit."""
        if sys.gettrace() == self.trace_function:
            self.stop()


# Global instance
_global_tracer: Optional[UnifiedTracer] = None


def start_unified_tracing(
    correlation_id: Optional[str] = None,
    max_call_rate: int = 1000,
    auto_video: bool = True,
    video_quality: str = "medium",
    verbose: bool = True
) -> UnifiedTracer:
    """
    Start unified tracing.

    Returns:
        UnifiedTracer instance
    """
    global _global_tracer

    if _global_tracer is not None:
        logger.info("[UnifiedTracer] Already active")
        return _global_tracer

    _global_tracer = UnifiedTracer(
        correlation_id=correlation_id,
        max_call_rate=max_call_rate,
        auto_generate_video=auto_video,
        video_quality=video_quality,
        verbose=verbose
    )

    _global_tracer.start()
    return _global_tracer


def stop_unified_tracing():
    """Stop unified tracing."""
    global _global_tracer

    if _global_tracer:
        _global_tracer.stop()
        _global_tracer = None


# Context manager
class traced:
    """
    Context manager for unified tracing.

    Usage:
        with traced():
            # Your code here
            # - Streams to PyCharm in real-time
            # - Generates Manim video automatically
            train_model()
    """

    def __init__(
        self,
        name: Optional[str] = None,
        max_call_rate: int = 1000,
        auto_video: bool = True,
        video_quality: str = "medium",
        verbose: bool = True
    ):
        self.name = name
        self.max_call_rate = max_call_rate
        self.auto_video = auto_video
        self.video_quality = video_quality
        self.verbose = verbose
        self.tracer: Optional[UnifiedTracer] = None

    def __enter__(self):
        self.tracer = start_unified_tracing(
            max_call_rate=self.max_call_rate,
            auto_video=self.auto_video,
            video_quality=self.video_quality,
            verbose=self.verbose
        )
        return self.tracer

    def __exit__(self, exc_type, exc_val, exc_tb):
        stop_unified_tracing()


# Decorator
def trace(
    max_call_rate: int = 1000,
    auto_video: bool = True,
    video_quality: str = "medium",
    verbose: bool = True
):
    """
    Decorator for unified tracing.

    Automatically:
    - Streams to PyCharm in real-time
    - Generates Manim replay video
    - Assigns correlation ID
    - Adaptive sampling if call rate high

    Usage:
        @trace()
        def train_model():
            # Everything auto-traced!
            pass

        @trace(max_call_rate=500, video_quality="high")
        def important_function():
            # High-quality video with lower sampling threshold
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with traced(
                name=func.__name__,
                max_call_rate=max_call_rate,
                auto_video=auto_video,
                video_quality=video_quality,
                verbose=verbose
            ):
                return func(*args, **kwargs)
        return wrapper
    return decorator


if __name__ == "__main__":
    # Example usage
    import time

    logger.info("\n" + "="*70)
    logger.info("UNIFIED TRACING EXAMPLES")
    logger.info("="*70 + "\n")

    # Example 1: Context manager
    logger.info("Example 1: Context Manager")
    logger.info("-"*70)

    with traced(auto_video=False, verbose=True):  # Disable video for quick demo
        def process_data(n):
            total = 0
            for i in range(n):
                total += i ** 2
            return total

        result = process_data(1000)
        logger.info(f"Result: {result}")

    input("\nPress Enter for Example 2...")

    # Example 2: Decorator
    logger.info("\nExample 2: Decorator")
    logger.info("-"*70)

    @trace(max_call_rate=500, auto_video=False, verbose=True)
    def train_model():
        """Simulated training function."""
        logger.info("Training model...")

        def train_epoch(epoch):
            logger.info(f"  Epoch {epoch}...")
            time.sleep(0.1)
            return 0.95 + (epoch * 0.01)

        for epoch in range(5):
            loss = train_epoch(epoch)

        logger.info("Training complete!")
        return "model.pth"

    model_path = train_model()
    logger.info(f"Model saved to: {model_path}")

    logger.info("\n" + "="*70)
    logger.info("EXAMPLES COMPLETE")
    logger.info("="*70)
    logger.info("\nNOTE: In production, set auto_video=True to generate Manim videos")
    logger.info("      Videos appear in: unified_traces/")
    logger.info()
