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

NOTE: All imports are lazy to avoid import errors during pytest discovery.
Use explicit imports when needed, e.g.:
    from manim_visualizer.trace_to_manim import TraceParser
"""

# Lazy imports to avoid import errors during test discovery
def __getattr__(name):
    """Lazy import handler for module attributes."""
    # Map attribute names to their module sources
    _imports = {
        # trace_to_manim
        'TraceParser': 'trace_to_manim',
        'ExecutionFlowScene': 'trace_to_manim',
        'DataFlowScene': 'trace_to_manim',
        'CallVisualization': 'trace_to_manim',
        'generate_visualization': 'trace_to_manim',
        # realtime_visualizer
        'RealtimeTraceVisualizer': 'realtime_visualizer',
        'BatchTraceVisualizer': 'realtime_visualizer',
        # config
        'VisualizationConfig': 'config',
        'get_config': 'config',
        'QUALITY_PRESETS': 'config',
        # auto_recorder
        'AutoRecorder': 'auto_recorder',
        'ExecutionSession': 'auto_recorder',
        'get_recorder': 'auto_recorder',
        'track_execution': 'auto_recorder',
        'tracked_execution': 'auto_recorder',
        # unified_tracing
        'UnifiedTracer': 'unified_tracing',
        'trace': 'unified_tracing',
        'traced': 'unified_tracing',
        'start_unified_tracing': 'unified_tracing',
        'stop_unified_tracing': 'unified_tracing',
        # high_performance_integration
        'HighPerformanceInstrumentor': 'high_performance_integration',
        'enable_high_performance_tracing': 'high_performance_integration',
        'disable_high_performance_tracing': 'high_performance_integration',
        'high_performance_tracing': 'high_performance_integration',
        'traced_with_sampling': 'high_performance_integration',
        # learning_cycle_tracer
        'LearningCycleTracer': 'learning_cycle_tracer',
        'LearningCycle': 'learning_cycle_tracer',
        'learning_cycle': 'learning_cycle_tracer',
    }

    if name in _imports:
        import importlib
        module = importlib.import_module(f'.{_imports[name]}', __name__)
        return getattr(module, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

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
