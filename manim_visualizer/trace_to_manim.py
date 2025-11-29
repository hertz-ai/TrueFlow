from logging_config import setup_logger
logger = setup_logger(__name__)

"""
Manim Trace Visualizer

Converts runtime trace data from RuntimeInstrumentor into animated Manim scenes
showing method calls, data flow, and parallel execution paths.

Features:
- Animated method call visualization with call hierarchy
- Data flow animation showing parameter passing
- Parallel execution path visualization with synchronized timelines
- Multiple camera system for tracking parallel flows
- Optional filtering to specific project paths (project-agnostic)
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from collections import defaultdict
import math

from manim import (
    Scene, VGroup, Text, Rectangle, Circle, Arrow, Line,
    FadeIn, FadeOut, Create, Write as ManimWrite, Transform,
    RIGHT, LEFT, UP, DOWN, ORIGIN,
    WHITE, BLUE, GREEN, RED, YELLOW, ORANGE, PURPLE,
    MovingCameraScene, ThreeDScene
)


@dataclass
class TraceCall:
    """Represents a single function call from trace data."""
    call_id: str
    function_name: str
    module: str
    file_path: str
    line_number: int
    start_time: float
    end_time: Optional[float]
    duration_ms: Optional[float]
    parent_id: Optional[str]
    depth: int
    parameters: Dict[str, Any]
    return_value: Any
    framework: Optional[str]
    invocation_type: str
    is_ai_agent: bool


@dataclass
class ExecutionThread:
    """Represents a parallel execution thread."""
    thread_id: str
    calls: List[TraceCall]
    start_time: float
    end_time: float
    camera_position: Tuple[float, float, float]


class TraceParser:
    """
    Parses trace JSON files from RuntimeInstrumentor.
    Optionally filters to specific folder/path (project-agnostic).
    """

    def __init__(self, trace_file_path: str, filter_path: str = None):
        """
        Initialize trace parser.

        Args:
            trace_file_path: Path to trace JSON file
            filter_path: Only include calls from this path (default: None = include all)
        """
        self.trace_file_path = Path(trace_file_path)
        self.filter_path = filter_path
        self.calls: List[TraceCall] = []
        self.call_hierarchy: Dict[str, List[TraceCall]] = defaultdict(list)
        self.threads: Dict[str, ExecutionThread] = {}

    def load_trace(self) -> None:
        """Load and parse trace JSON file."""
        with open(self.trace_file_path, 'r', encoding='utf-8') as f:
            trace_data = json.load(f)

        # Parse calls
        for call_data in trace_data.get('calls', []):
            # Filter to specified path (if any)
            file_path = call_data.get('file_path', '')
            if self.filter_path and self.filter_path not in file_path:
                continue

            call = TraceCall(
                call_id=call_data.get('call_id', ''),
                function_name=call_data.get('function_name', ''),
                module=call_data.get('module', ''),
                file_path=file_path,
                line_number=call_data.get('line_number', 0),
                start_time=call_data.get('start_time', 0.0),
                end_time=call_data.get('end_time'),
                duration_ms=call_data.get('duration_ms'),
                parent_id=call_data.get('parent_id'),
                depth=call_data.get('depth', 0),
                parameters=call_data.get('parameters', {}),
                return_value=call_data.get('return_value'),
                framework=call_data.get('framework'),
                invocation_type=call_data.get('invocation_type', 'sync'),
                is_ai_agent=call_data.get('is_ai_agent', False)
            )

            self.calls.append(call)

            # Build hierarchy
            parent_id = call.parent_id or 'root'
            self.call_hierarchy[parent_id].append(call)

    def detect_parallel_threads(self) -> None:
        """
        Detect parallel execution threads based on overlapping timestamps.
        """
        # Sort calls by start time
        sorted_calls = sorted(self.calls, key=lambda c: c.start_time)

        # Track active threads
        active_threads: List[List[TraceCall]] = []

        for call in sorted_calls:
            # Find thread where this call fits (no overlap with last call)
            placed = False
            for thread in active_threads:
                if thread[-1].end_time and thread[-1].end_time <= call.start_time:
                    thread.append(call)
                    placed = True
                    break

            if not placed:
                # Create new thread
                active_threads.append([call])

        # Convert to ExecutionThread objects
        for i, thread_calls in enumerate(active_threads):
            thread_id = f"thread_{i}"
            start_time = thread_calls[0].start_time
            end_time = max(c.end_time or c.start_time for c in thread_calls)

            # Position cameras in a circle around origin
            angle = (2 * math.pi * i) / len(active_threads)
            camera_x = 8 * math.cos(angle)
            camera_y = 8 * math.sin(angle)

            self.threads[thread_id] = ExecutionThread(
                thread_id=thread_id,
                calls=thread_calls,
                start_time=start_time,
                end_time=end_time,
                camera_position=(camera_x, camera_y, 3)
            )

    def get_call_tree(self, parent_id: Optional[str] = None) -> List[TraceCall]:
        """Get call tree starting from parent_id."""
        parent_key = parent_id or 'root'
        return self.call_hierarchy.get(parent_key, [])


class CallVisualization:
    """
    Manim visualization elements for a function call.
    """

    def __init__(self, call: TraceCall, position: Tuple[float, float, float]):
        self.call = call
        self.position = position

        # Visual elements
        self.box = Rectangle(
            width=4,
            height=1.5,
            fill_opacity=0.3,
            fill_color=self._get_color()
        ).move_to(position)

        # Function name
        self.name_text = Text(
            self._format_function_name(),
            font_size=20,
            color=WHITE
        ).move_to(position + UP * 0.3)

        # Duration indicator
        duration_str = f"{call.duration_ms:.2f}ms" if call.duration_ms else "..."
        self.duration_text = Text(
            duration_str,
            font_size=16,
            color=YELLOW
        ).move_to(position + DOWN * 0.3)

        # Parameter flow indicators
        self.param_arrows: List[Arrow] = []

        # Group all elements
        self.group = VGroup(self.box, self.name_text, self.duration_text)

    def _get_color(self) -> str:
        """Get color based on call properties."""
        if self.call.is_ai_agent:
            return PURPLE
        elif self.call.framework:
            return BLUE
        elif self.call.invocation_type == 'async':
            return GREEN
        else:
            return WHITE

    def _format_function_name(self) -> str:
        """Format function name for display."""
        name = self.call.function_name
        if len(name) > 30:
            name = name[:27] + "..."
        return name

    def add_parameter_arrow(self, from_pos: Tuple[float, float, float]) -> Arrow:
        """Add arrow showing parameter flow."""
        arrow = Arrow(
            start=from_pos,
            end=self.position + LEFT * 2,
            color=ORANGE,
            buff=0.1
        )
        self.param_arrows.append(arrow)
        return arrow


class ExecutionFlowScene(MovingCameraScene):
    """
    Manim scene that visualizes execution flow with multiple cameras.

    Features:
    - Animated method calls appearing in sequence
    - Call hierarchy shown as vertical stack
    - Parallel threads shown side-by-side
    - Multiple cameras tracking different threads
    - Synchronized timelines
    """

    def __init__(self, trace_parser: TraceParser, **kwargs):
        super().__init__(**kwargs)
        self.trace_parser = trace_parser
        self.visualizations: Dict[str, CallVisualization] = {}
        self.timeline_scale = 0.01  # 1 second = 0.01 Manim units

    def construct(self):
        """Main scene construction."""
        # Title
        title = Text("Embodied AI Execution Flow", font_size=36)
        title.to_edge(UP)
        self.play(ManimWrite(title))
        self.wait(0.5)

        # Detect parallel threads
        self.trace_parser.detect_parallel_threads()

        # Render each thread
        if len(self.trace_parser.threads) == 1:
            # Single thread - simple sequential visualization
            self._render_single_thread()
        else:
            # Multiple threads - parallel visualization with multiple cameras
            self._render_parallel_threads()

        self.wait(2)

    def _render_single_thread(self):
        """Render single thread execution flow."""
        thread = list(self.trace_parser.threads.values())[0]

        # Track current position
        current_y = 2
        call_stack: List[CallVisualization] = []

        for call in thread.calls:
            # Calculate position based on depth
            x_offset = call.depth * 1.5
            position = (x_offset, current_y, 0)

            # Create visualization
            viz = CallVisualization(call, position)
            self.visualizations[call.call_id] = viz

            # Animate appearance
            self.play(
                FadeIn(viz.group),
                run_time=0.3
            )

            # Show parameter flow from parent
            if call.parent_id and call.parent_id in self.visualizations:
                parent_viz = self.visualizations[call.parent_id]
                arrow = viz.add_parameter_arrow(parent_viz.position)
                self.play(Create(arrow), run_time=0.2)

            # Wait proportional to actual duration
            if call.duration_ms:
                wait_time = min(call.duration_ms / 1000, 2.0)  # Max 2 seconds
                self.wait(wait_time)

            # Move down for next call
            current_y -= 2

            # Camera follows
            if current_y < -4:
                self.play(
                    self.camera.frame.animate.shift(DOWN * 2),
                    run_time=0.3
                )

    def _render_parallel_threads(self):
        """Render multiple parallel threads with synchronized cameras."""
        # Position threads horizontally
        thread_spacing = 6
        threads = list(self.trace_parser.threads.values())

        # Calculate overall timeline
        global_start = min(t.start_time for t in threads)
        global_end = max(t.end_time for t in threads)
        total_duration = global_end - global_start

        # Create timeline indicator
        timeline = Line(
            start=LEFT * 5,
            end=RIGHT * 5,
            color=YELLOW
        ).to_edge(DOWN)
        self.add(timeline)

        # Render each thread in parallel
        for i, thread in enumerate(threads):
            # Position thread
            x_base = (i - len(threads) / 2) * thread_spacing

            # Render thread calls
            current_y = 2

            for call in thread.calls:
                # Calculate position
                x_offset = x_base + call.depth * 0.5
                position = (x_offset, current_y, 0)

                # Create visualization
                viz = CallVisualization(call, position)
                self.visualizations[call.call_id] = viz

                # Calculate timing relative to global timeline
                relative_start = (call.start_time - global_start) / total_duration if total_duration > 0 else 0

                # Animate appearance at synchronized time
                self.play(
                    FadeIn(viz.group),
                    run_time=0.2
                )

                # Show parameter flow
                if call.parent_id and call.parent_id in self.visualizations:
                    parent_viz = self.visualizations[call.parent_id]
                    arrow = viz.add_parameter_arrow(parent_viz.position)
                    self.play(Create(arrow), run_time=0.1)

                current_y -= 1.5

        # Camera pans across all threads
        self.play(
            self.camera.frame.animate.move_to(ORIGIN),
            run_time=2
        )


class DataFlowScene(Scene):
    """
    Scene showing detailed data flow and parameter passing.
    """

    def __init__(self, trace_parser: TraceParser, **kwargs):
        super().__init__(**kwargs)
        self.trace_parser = trace_parser

    def construct(self):
        """Visualize data flow between function calls."""
        title = Text("Parameter Data Flow", font_size=36)
        title.to_edge(UP)
        self.play(ManimWrite(title))

        # Get first few calls to demonstrate data flow
        calls = self.trace_parser.calls[:10]

        # Position calls in grid
        grid_width = 3
        current_x = -5
        current_y = 2

        for i, call in enumerate(calls):
            if i > 0 and i % grid_width == 0:
                current_x = -5
                current_y -= 2

            position = (current_x, current_y, 0)
            viz = CallVisualization(call, position)

            self.play(FadeIn(viz.group), run_time=0.3)

            # Show parameters as flowing data
            if call.parameters:
                param_text = Text(
                    f"Params: {len(call.parameters)}",
                    font_size=14,
                    color=GREEN
                ).next_to(viz.box, DOWN)
                self.play(FadeIn(param_text), run_time=0.2)

            current_x += 4

        self.wait(2)


def generate_visualization(trace_file: str, output_path: str = None):
    """
    Generate Manim visualization from trace file.

    Args:
        trace_file: Path to trace JSON file
        output_path: Output path for rendered video (default: trace_animation.mp4)
    """
    # Parse trace (no filter - include all project code)
    parser = TraceParser(trace_file, filter_path=None)
    parser.load_trace()

    logger.info(f"Loaded {len(parser.calls)} calls from trace file")

    # Create scene
    scene = ExecutionFlowScene(parser)

    # Render
    if output_path is None:
        output_path = "trace_animation.mp4"

    logger.info(f"Rendering animation to {output_path}...")
    scene.render()

    return output_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        logger.info("Usage: python trace_to_manim.py <trace_json_file> [output_path]")
        sys.exit(1)

    trace_file = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    generate_visualization(trace_file, output_path)
