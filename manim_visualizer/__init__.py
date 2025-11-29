try:
    from .logging_config import setup_logger
except ImportError:
    from logging_config import setup_logger
logger = setup_logger(__name__)

"""
Manim Trace Visualizer

Animated visualization of execution traces from RuntimeInstrumentor.

Features:
- Real-time and batch visualization modes
- Animated method call visualization with call hierarchy
- Data flow animation showing parameter passing
- Parallel execution path visualization with synchronized timelines
- Multiple camera system for tracking parallel flows
- Project-agnostic filtering (optional path filtering)
"""

from .trace_to_manim import (
    TraceParser,
    ExecutionFlowScene,
    DataFlowScene,
    CallVisualization,
    generate_visualization
)

from .realtime_visualizer import (
    RealtimeTraceVisualizer,
    BatchTraceVisualizer
)

from .config import (
    VisualizationConfig,
    get_config,
    QUALITY_PRESETS
)

from .auto_recorder import (
    AutoRecorder,
    ExecutionSession,
    get_recorder,
    track_execution,
    tracked_execution
)

from .unified_tracing import (
    UnifiedTracer,
    trace,
    traced,
    start_unified_tracing,
    stop_unified_tracing
)

from .high_performance_integration import (
    HighPerformanceInstrumentor,
    enable_high_performance_tracing,
    disable_high_performance_tracing,
    high_performance_tracing,
    traced_with_sampling
)

from .learning_cycle_tracer import (
    LearningCycleTracer,
    LearningCycle,
    learning_cycle
)

__all__ = [
    # === RECOMMENDED FOR LEARNING: Cycle-Based Tracing ===
    "LearningCycleTracer",           # Tracer for learning cycles
    "LearningCycle",                 # Cycle data structure
    "learning_cycle",                # Context manager for cycles

    # === Unified Tracing (General Purpose) ===
    "trace",                          # Decorator for auto tracing + video
    "traced",                         # Context manager for auto tracing + video
    "UnifiedTracer",                  # Full unified tracer class
    "start_unified_tracing",
    "stop_unified_tracing",

    # === High-Performance (Sampling Only) ===
    "HighPerformanceInstrumentor",
    "enable_high_performance_tracing",
    "disable_high_performance_tracing",
    "high_performance_tracing",
    "traced_with_sampling",

    # Core visualization
    "TraceParser",
    "ExecutionFlowScene",
    "DataFlowScene",
    "CallVisualization",
    "generate_visualization",

    # Real-time and batch
    "RealtimeTraceVisualizer",
    "BatchTraceVisualizer",

    # Configuration
    "VisualizationConfig",
    "get_config",
    "QUALITY_PRESETS",

    # Auto-recording (legacy)
    "AutoRecorder",
    "ExecutionSession",
    "get_recorder",
    "track_execution",
    "tracked_execution"
]

__version__ = "1.0.0"
