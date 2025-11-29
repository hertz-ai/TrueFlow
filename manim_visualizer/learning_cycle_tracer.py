from logging_config import setup_logger
logger = setup_logger(__name__)

"""
Learning Cycle Tracer

Correlation ID lifecycle tied to learning cycles:
Input -> Prediction -> Error Computation -> Parameter Update

Each complete cycle:
- Gets unique correlation ID
- Generates separate video showing all parallel paths
- Synchronized to same time input
- Auto-completes when parameter update finishes

Usage:
    from manim_visualizer.learning_cycle_tracer import LearningCycleTracer

    tracer = LearningCycleTracer()

    # Cycle 1 starts
    with tracer.cycle(input_data=observation):
        prediction = model.forward(observation)
        error = compute_loss(prediction, target)
        optimizer.step()
    # Cycle 1 ends -> Video 1 generated

    # Cycle 2 starts (new correlation ID)
    with tracer.cycle(input_data=next_observation):
        prediction = model.forward(next_observation)
        error = compute_loss(prediction, target)
        optimizer.step()
    # Cycle 2 ends -> Video 2 generated
"""

import sys
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
import uuid
from datetime import datetime
from contextvars import ContextVar

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent))

from manim_visualizer.optimized_recorder import (
    OptimizedRecorder,
    SamplingConfig
)
from manim_visualizer.realtime_visualizer import BatchTraceVisualizer
from manim_visualizer.config import get_config


# Context variable for current cycle
current_cycle_var: ContextVar[Optional[str]] = ContextVar('current_cycle', default=None)


@dataclass
class LearningCyclePhase:
    """Represents a phase within a learning cycle."""
    name: str                       # "input", "forward", "loss", "backward", "update"
    start_time: float
    end_time: Optional[float] = None
    thread_ids: List[str] = field(default_factory=list)
    async_task_ids: List[str] = field(default_factory=list)
    call_count: int = 0


@dataclass
class LearningCycle:
    """Represents one complete learning cycle."""
    correlation_id: str
    input_data: Dict[str, Any]
    start_time: float
    end_time: Optional[float] = None

    # Phases
    phases: Dict[str, LearningCyclePhase] = field(default_factory=dict)
    current_phase: Optional[str] = None

    # Tracking
    all_thread_ids: List[str] = field(default_factory=list)
    all_async_task_ids: List[str] = field(default_factory=list)
    total_calls: int = 0

    # Files
    trace_file: str = ""
    video_file: str = ""
    status: str = "running"  # running, completed, failed


class LearningCycleTracer:
    """
    Tracer that understands learning cycles.

    Each cycle (input -> pred -> error -> update) gets:
    - Unique correlation ID
    - Separate video showing all parallel paths
    - Synchronized timeline from same input time
    """

    def __init__(
        self,
        output_dir: str = "learning_cycles",
        max_call_rate: int = 1000,
        video_quality: str = "medium",
        auto_generate_video: bool = True,
        verbose: bool = True
    ):
        """
        Initialize learning cycle tracer.

        Args:
            output_dir: Output directory for cycles
            max_call_rate: Max call rate before sampling
            video_quality: Manim video quality
            auto_generate_video: Auto-generate videos
            verbose: Enable verbose logging
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.max_call_rate = max_call_rate
        self.video_quality = video_quality
        self.auto_generate_video = auto_generate_video
        self.verbose = verbose

        # Active cycles indexed by correlation ID
        self.cycles: Dict[str, LearningCycle] = {}
        self.current_cycle_id: Optional[str] = None

        # Recorder for current cycle
        self.current_recorder: Optional[OptimizedRecorder] = None

        # Original trace function
        self.original_trace = sys.gettrace()

        # Call stack
        self.call_stack = []

        # Cycle counter
        self.cycle_count = 0

        if self.verbose:
            logger.info(f"\n{'='*70}")
            logger.info("LEARNING CYCLE TRACER INITIALIZED")
            logger.info(f"{'='*70}")
            logger.info(f"Output Dir: {self.output_dir}")
            logger.info(f"Max Call Rate: {max_call_rate}/sec")
            logger.info(f"Video Quality: {video_quality}")
            logger.info(f"Auto Video: {auto_generate_video}")
            logger.info(f"{'='*70}\n")

    def start_cycle(
        self,
        input_data: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None
    ) -> str:
        """
        Start a new learning cycle.

        Args:
            input_data: Input data for this cycle
            correlation_id: Optional correlation ID (auto-generated if None)

        Returns:
            Correlation ID for this cycle
        """
        # Generate correlation ID
        if correlation_id is None:
            correlation_id = f"cycle_{self.cycle_count:06d}_{uuid.uuid4().hex[:8]}"

        self.cycle_count += 1

        # Create cycle
        cycle = LearningCycle(
            correlation_id=correlation_id,
            input_data=input_data or {},
            start_time=time.time()
        )

        # Generate file paths
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        cycle.trace_file = str(
            self.output_dir / f"trace_{correlation_id}_{timestamp}.json"
        )
        cycle.video_file = str(
            self.output_dir / f"video_{correlation_id}_{timestamp}.mp4"
        )

        # Store cycle
        self.cycles[correlation_id] = cycle
        self.current_cycle_id = correlation_id
        current_cycle_var.set(correlation_id)

        # Create recorder for this cycle
        config = SamplingConfig(
            high_rate_threshold=self.max_call_rate,
            extreme_rate_threshold=self.max_call_rate * 5,
            always_record_patterns=[
                # Project-agnostic: Priority patterns for learning cycles
                "forward",
                "backward",
                "loss",
                "error",
                "update",
                "step",
                "learn"
            ]
        )

        self.current_recorder = OptimizedRecorder(
            config=config,
            correlation_id=correlation_id,
            verbose=False  # Suppress individual recorder logs
        )

        # Start tracing
        sys.settrace(self.trace_function)

        if self.verbose:
            logger.info(f"\n[LearningCycle] CYCLE STARTED: {correlation_id}")
            logger.info(f"  Input: {str(input_data)[:100]}...")
            logger.info(f"  Trace: {Path(cycle.trace_file).name}")
            logger.info(f"  Video: {Path(cycle.video_file).name}")

        return correlation_id

    def set_phase(self, phase_name: str):
        """
        Set current phase within learning cycle.

        Args:
            phase_name: Phase name (input, forward, loss, backward, update)
        """
        if not self.current_cycle_id:
            return

        cycle = self.cycles[self.current_cycle_id]

        # End previous phase
        if cycle.current_phase and cycle.current_phase in cycle.phases:
            cycle.phases[cycle.current_phase].end_time = time.time()

        # Start new phase
        phase = LearningCyclePhase(
            name=phase_name,
            start_time=time.time()
        )
        cycle.phases[phase_name] = phase
        cycle.current_phase = phase_name

        if self.verbose:
            logger.info(f"  [{phase_name.upper()}] Phase started")

    def end_cycle(self, status: str = "completed"):
        """
        End current learning cycle and generate video.

        Args:
            status: Cycle status (completed, failed)
        """
        if not self.current_cycle_id:
            if self.verbose:
                logger.info("[LearningCycle] WARNING: No active cycle to end")
            return

        cycle = self.cycles[self.current_cycle_id]
        cycle.end_time = time.time()
        cycle.status = status

        # End current phase
        if cycle.current_phase and cycle.current_phase in cycle.phases:
            cycle.phases[cycle.current_phase].end_time = time.time()

        # Stop tracing
        sys.settrace(self.original_trace)

        # Get statistics from recorder
        if self.current_recorder:
            stats = self.current_recorder.get_statistics()
            cycle.total_calls = stats['total_calls']

            # Flush and close recorder
            self.current_recorder.flush()
            self.current_recorder.close()

        duration = cycle.end_time - cycle.start_time

        if self.verbose:
            logger.info(f"\n[LearningCycle] CYCLE COMPLETED: {cycle.correlation_id}")
            logger.info(f"  Duration: {duration:.3f}s")
            logger.info(f"  Status: {status}")
            logger.info(f"  Total Calls: {cycle.total_calls}")
            logger.info(f"  Phases:")
            for phase_name, phase in cycle.phases.items():
                phase_duration = (phase.end_time or time.time()) - phase.start_time
                logger.info(f"    {phase_name}: {phase_duration:.3f}s")

        # Export trace
        self._export_cycle_trace(cycle)

        # Generate video
        if self.auto_generate_video:
            self._generate_cycle_video_async(cycle)

        # Clear current cycle
        self.current_cycle_id = None
        self.current_recorder = None
        current_cycle_var.set(None)

    def trace_function(self, frame, event, arg):
        """Trace function callback."""
        if not self.current_recorder:
            return None

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

        # Auto-detect phase from function name
        self._auto_detect_phase(function_name, module)

        # Get parent ID
        parent_id = self.call_stack[-1] if self.call_stack else None
        depth = len(self.call_stack)

        # Record call
        call_id = self.current_recorder.record_call(
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

            # Update phase stats
            if self.current_cycle_id:
                cycle = self.cycles[self.current_cycle_id]
                if cycle.current_phase and cycle.current_phase in cycle.phases:
                    cycle.phases[cycle.current_phase].call_count += 1

        else:
            self.call_stack.append(None)

        return self.trace_function

    def _handle_return(self, frame, arg):
        """Handle function return."""
        if self.call_stack:
            call_id = self.call_stack.pop()

            if call_id and self.current_recorder:
                self.current_recorder.record_return(call_id)

        return self.trace_function

    def _auto_detect_phase(self, function_name: str, module: str):
        """Auto-detect learning phase from function name."""
        function_lower = function_name.lower()

        # Phase detection patterns
        if 'forward' in function_lower or 'predict' in function_lower:
            if not self.current_cycle_id or self.cycles[self.current_cycle_id].current_phase != 'forward':
                self.set_phase('forward')

        elif 'loss' in function_lower or 'error' in function_lower or 'compute_loss' in function_lower:
            if not self.current_cycle_id or self.cycles[self.current_cycle_id].current_phase != 'loss':
                self.set_phase('loss')

        elif 'backward' in function_lower or 'grad' in function_lower:
            if not self.current_cycle_id or self.cycles[self.current_cycle_id].current_phase != 'backward':
                self.set_phase('backward')

        elif 'update' in function_lower or 'step' in function_lower or 'optimizer' in module.lower():
            if not self.current_cycle_id or self.cycles[self.current_cycle_id].current_phase != 'update':
                self.set_phase('update')

    def _export_cycle_trace(self, cycle: LearningCycle):
        """
        Export cycle trace to JSON in format compatible with Manim visualizer.

        IMPORTANT: All parallel paths from same input go into SAME trace file
        so they appear in SAME video with synchronized timelines.
        """
        import json

        # Get all calls from recorder for this cycle
        all_calls = []
        if self.current_recorder and hasattr(self.current_recorder, 'event_buffer'):
            # Collect all buffered events
            with self.current_recorder.event_buffer.lock:
                buffer = self.current_recorder.event_buffer.buffer.copy()

            # Convert events to call format
            for event in buffer:
                if event.get('type') == 'call':
                    call_record = {
                        "call_id": event.get('call_id', ''),
                        "function_name": event.get('function', ''),
                        "module": event.get('module', ''),
                        "file_path": event.get('file', ''),
                        "line_number": event.get('line', 0),
                        "start_time": event.get('timestamp', 0.0),
                        "end_time": None,  # Will be filled by return event
                        "duration_ms": None,
                        "parent_id": event.get('parent_id'),
                        "depth": event.get('depth', 0),
                        "thread_id": str(event.get('process_id', '')),  # Actually thread
                        "session_id": event.get('session_id', ''),
                        "parameters": {},
                        "return_value": None,
                        "framework": None,
                        "invocation_type": "sync",
                        "is_ai_agent": False
                    }
                    all_calls.append(call_record)

        # Build trace data in Manim-compatible format
        # ALL PARALLEL PATHS IN SAME TRACE = SAME VIDEO
        trace_data = {
            "correlation_id": cycle.correlation_id,
            "input_data": cycle.input_data,
            "start_time": cycle.start_time,
            "end_time": cycle.end_time,
            "duration": cycle.end_time - cycle.start_time if cycle.end_time else 0,
            "status": cycle.status,

            # Metadata
            "metadata": {
                "total_calls": cycle.total_calls,
                "phases": {
                    name: {
                        "start_time": phase.start_time,
                        "end_time": phase.end_time,
                        "duration": (phase.end_time or time.time()) - phase.start_time,
                        "call_count": phase.call_count,
                        "thread_ids": phase.thread_ids,
                        "async_task_ids": phase.async_task_ids
                    }
                    for name, phase in cycle.phases.items()
                },
                "all_thread_ids": cycle.all_thread_ids,
                "all_async_task_ids": cycle.all_async_task_ids
            },

            # ALL CALLS (parallel paths included)
            # This is what Manim uses to detect parallel threads
            "calls": all_calls
        }

        with open(cycle.trace_file, 'w') as f:
            json.dump(trace_data, f, indent=2)

        if self.verbose:
            logger.info(f"  Trace exported: {cycle.trace_file}")
            logger.info(f"    Total calls: {len(all_calls)}")
            logger.info(f"    Threads: {len(set(c.get('thread_id', '') for c in all_calls))}")
            logger.info(f"    → Single video will show all parallel paths synchronized")

    def _generate_cycle_video_async(self, cycle: LearningCycle):
        """Generate video for cycle in background."""
        def generate():
            try:
                if self.verbose:
                    logger.info(f"  Generating video for {cycle.correlation_id}...")

                # Create visualizer
                config = get_config(self.video_quality)
                visualizer = BatchTraceVisualizer(config=config)

                # Generate video
                visualizer.visualize_trace_file(
                    cycle.trace_file,
                    cycle.video_file
                )

                if self.verbose:
                    logger.info(f"  ✓ Video generated: {cycle.video_file}")

            except Exception as e:
                if self.verbose:
                    logger.info(f"  ✗ Video generation failed: {e}")
                cycle.status = "video_failed"

        # Start in background
        thread = threading.Thread(target=generate, daemon=True)
        thread.start()

    def get_cycle(self, correlation_id: str) -> Optional[LearningCycle]:
        """Get cycle by correlation ID."""
        return self.cycles.get(correlation_id)

    def list_cycles(self, status: Optional[str] = None) -> List[LearningCycle]:
        """List all cycles, optionally filtered by status."""
        cycles = list(self.cycles.values())

        if status:
            cycles = [c for c in cycles if c.status == status]

        # Sort by start time (most recent first)
        cycles.sort(key=lambda c: c.start_time, reverse=True)

        return cycles

    def print_summary(self):
        """Print summary of all cycles."""
        cycles = self.list_cycles()

        logger.info(f"\n{'='*70}")
        logger.info("LEARNING CYCLES SUMMARY")
        logger.info(f"{'='*70}")
        logger.info(f"Total Cycles: {len(cycles)}")
        logger.info(f"Completed: {len([c for c in cycles if c.status == 'completed'])}")
        logger.info(f"Failed: {len([c for c in cycles if c.status == 'failed'])}")
        logger.info()

        for i, cycle in enumerate(cycles[:10], 1):  # Show last 10
            duration = (cycle.end_time or time.time()) - cycle.start_time
            logger.info(f"{i}. {cycle.correlation_id}")
            logger.info(f"   Status: {cycle.status}")
            logger.info(f"   Duration: {duration:.3f}s")
            logger.info(f"   Calls: {cycle.total_calls}")
            logger.info(f"   Phases: {', '.join(cycle.phases.keys())}")
            logger.info(f"   Video: {Path(cycle.video_file).name}")
            logger.info()

        logger.info(f"{'='*70}\n")


# Context manager for learning cycles
class learning_cycle:
    """
    Context manager for learning cycles.

    Usage:
        tracer = LearningCycleTracer()

        with tracer.cycle(input_data={"observation": obs}):
            # Input -> Prediction -> Error -> Update
            prediction = model(obs)
            error = loss(prediction, target)
            optimizer.step()

        # Video generated showing all parallel paths
    """

    def __init__(
        self,
        tracer: LearningCycleTracer,
        input_data: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None
    ):
        self.tracer = tracer
        self.input_data = input_data
        self.correlation_id = correlation_id

    def __enter__(self):
        self.correlation_id = self.tracer.start_cycle(
            input_data=self.input_data,
            correlation_id=self.correlation_id
        )
        return self.correlation_id

    def __exit__(self, exc_type, exc_val, exc_tb):
        status = "failed" if exc_type else "completed"
        self.tracer.end_cycle(status=status)


# Add cycle method to tracer
LearningCycleTracer.cycle = lambda self, **kwargs: learning_cycle(self, **kwargs)


if __name__ == "__main__":
    # Example usage
    import torch
    import torch.nn as nn

    logger.info("\n" + "="*70)
    logger.info("LEARNING CYCLE TRACER EXAMPLE")
    logger.info("="*70 + "\n")

    # Create tracer
    tracer = LearningCycleTracer(
        auto_generate_video=False,  # Disable for quick demo
        verbose=True
    )

    # Simulate training loop
    class SimpleModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.fc = nn.Linear(10, 1)

        def forward(self, x):
            return self.fc(x)

    model = SimpleModel()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01)

    # Training loop with cycles
    for epoch in range(3):
        logger.info(f"\n{'='*70}")
        logger.info(f"EPOCH {epoch+1}")
        logger.info(f"{'='*70}")

        # Cycle 1: Forward pass and update
        with tracer.cycle(input_data={"epoch": epoch, "batch": 0}):
            # Input
            x = torch.randn(32, 10)
            y = torch.randn(32, 1)

            # Forward (auto-detected)
            output = model(x)

            # Loss (auto-detected)
            loss = nn.functional.mse_loss(output, y)

            # Backward (auto-detected)
            optimizer.zero_grad()
            loss.backward()

            # Update (auto-detected)
            optimizer.step()

            logger.info(f"    Loss: {loss.item():.4f}")

    # Print summary
    tracer.print_summary()

    logger.info("\n" + "="*70)
    logger.info("EXAMPLE COMPLETE")
    logger.info("="*70)
    logger.info("\nIn production, set auto_generate_video=True to generate videos")
    logger.info("Each cycle gets its own video showing all parallel paths!\n")
