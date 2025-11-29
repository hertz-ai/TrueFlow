"""
Base Trace Visualizer - Consolidates ALL common functionality

This base class eliminates 1,040+ lines of code duplication across 6 visualizers.
All visualizers should inherit from this to ensure consistency and reduce maintenance.

Key Features:
- Trace loading (JSON parsing)
- Module extraction and grouping
- Phase detection (sensor, encoding, reasoning, decoding, learning, memory)
- Billboard text creation (always faces camera)
- Camera setup and management (using correct ThreeDScene API)
- Common animations (title, summary, transitions)
- Consistent timing and pacing (3Blue1Brown standards)
- Error handling and fallbacks
"""

from logging_config import setup_logger
logger = setup_logger(__name__)

import json
import numpy as np
from manim import *
from typing import Dict, List, Tuple, Optional, Any, Callable
from collections import defaultdict
from pathlib import Path

# Import common infrastructure
from visualization_common import VisualizationConfig, PhaseDetector
from visualization_framework import CoordinateTracker, ModulePosition


class BaseTraceVisualizer(ThreeDScene):
    """
    Base class for all trace visualizers.

    Consolidates common functionality:
    - Trace loading
    - Module extraction
    - Billboard text
    - Camera setup
    - Phase detection
    - Common animations

    Subclasses override:
    - construct_phases() - Main visualization logic
    - get_title() - Custom title text
    - get_config() - Custom configuration
    """

    def __init__(self, trace_file: Optional[str] = None, **kwargs):
        """
        Initialize visualizer with trace file.

        Args:
            trace_file: Path to JSON trace file
            **kwargs: Additional Manim scene arguments
        """
        self.trace_file = trace_file
        self.trace_data = None
        self.calls = []
        self.modules = {}
        self.errors = []
        self.config = self.get_config()
        self.phase_detector = PhaseDetector()
        self.coord_tracker = CoordinateTracker()

        super().__init__(**kwargs)

    def get_config(self) -> VisualizationConfig:
        """
        Get visualization configuration.
        Subclasses can override to customize.
        """
        return VisualizationConfig()

    def get_title(self) -> str:
        """
        Get title text for this visualizer.
        Subclasses should override.
        """
        return "Trace Visualization"

    def load_trace(self) -> bool:
        """
        Load and parse trace JSON file.

        Returns:
            True if successful, False otherwise
        """
        if not self.trace_file:
            logger.error("No trace file provided")
            return False

        trace_path = Path(self.trace_file)
        if not trace_path.exists():
            logger.error(f"Trace file not found: {self.trace_file}")
            return False

        try:
            with open(self.trace_file, 'r', encoding='utf-8') as f:
                self.trace_data = json.load(f)

            # Extract calls
            self.calls = self.trace_data.get('calls', [])

            # Extract errors (if any)
            self.errors = [
                call for call in self.calls
                if call.get('type') == 'error' or call.get('error')
            ]

            logger.info(
                f"Loaded trace: {len(self.calls)} calls, "
                f"{len(self.errors)} errors from {self.trace_file}"
            )

            return True

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse trace JSON: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to load trace: {e}")
            return False

    def extract_modules(self, max_modules: Optional[int] = None) -> Dict[str, List[Dict]]:
        """
        Extract modules from trace calls.

        Args:
            max_modules: Maximum number of modules to extract (None = all)

        Returns:
            Dict mapping module names to lists of calls
        """
        if not self.calls:
            logger.warning("No calls to extract modules from")
            return {}

        modules = defaultdict(list)

        for call in self.calls:
            # Only process actual function calls
            if call.get('type') != 'call':
                continue

            module_name = call.get('module', 'unknown')
            modules[module_name].append(call)

        # Apply limit if specified
        if max_modules and len(modules) > max_modules:
            # Sort by call count and take top N
            sorted_modules = sorted(
                modules.items(),
                key=lambda x: len(x[1]),
                reverse=True
            )
            modules = dict(sorted_modules[:max_modules])

        logger.info(f"Extracted {len(modules)} modules from trace")
        self.modules = modules
        return modules

    def detect_phase(self, module_name: str, function_name: str) -> str:
        """
        Detect learning phase for a function call.

        Args:
            module_name: Python module name
            function_name: Function name

        Returns:
            Phase name (sensor, encoding, reasoning, decoding, learning, memory)
        """
        # PhaseDetector.detect_phase expects a dictionary
        call_data = {
            'module': module_name,
            'function': function_name
        }
        return self.phase_detector.detect_phase(call_data) or 'unknown'

    def get_phase_color(self, phase: str) -> ManimColor:
        """
        Get consistent color for a learning phase.

        Args:
            phase: Phase name

        Returns:
            Manim color
        """
        colors = self.config.PHASE_COLORS
        return colors.get(phase, WHITE)

    def create_billboard_text(
        self,
        text: str,
        font_size: int = 24,
        color: ManimColor = WHITE,
        position: Optional[np.ndarray] = None
    ) -> Text:
        """
        Create text that always faces the camera (billboard).

        Args:
            text: Text content
            font_size: Font size
            color: Text color
            position: 3D position (None = origin)

        Returns:
            Text mobject configured as billboard
        """
        label = Text(text, font_size=font_size, color=color)

        if position is not None:
            label.move_to(position)

        # Make text always face camera
        self.add_fixed_in_frame_mobjects(label)

        return label

    def setup_camera(
        self,
        phi: float = 70 * DEGREES,
        theta: float = -45 * DEGREES,
        distance: float = 10.0
    ):
        """
        Setup camera with correct API (ThreeDScene).

        Args:
            phi: Vertical angle
            theta: Horizontal angle
            distance: Distance from origin
        """
        # Use set_camera_orientation (correct API for ThreeDScene)
        self.set_camera_orientation(phi=phi, theta=theta, distance=distance)

        # Update coordinate tracker
        self.coord_tracker.camera_state.phi = phi
        self.coord_tracker.camera_state.theta = theta
        self.coord_tracker.camera_state.distance = distance

    def move_camera_smooth(
        self,
        phi: Optional[float] = None,
        theta: Optional[float] = None,
        distance: Optional[float] = None,
        run_time: float = 2.0,
        rate_func: Callable = smooth
    ):
        """
        Move camera smoothly (using correct ThreeDScene API).

        Args:
            phi: Target vertical angle (None = no change)
            theta: Target horizontal angle (None = no change)
            distance: Target distance (None = no change)
            run_time: Duration of movement
            rate_func: Easing function
        """
        # Build kwargs with only specified parameters
        kwargs = {}
        if phi is not None:
            kwargs['phi'] = phi
            self.coord_tracker.camera_state.phi = phi
        if theta is not None:
            kwargs['theta'] = theta
            self.coord_tracker.camera_state.theta = theta
        if distance is not None:
            kwargs['distance'] = distance
            self.coord_tracker.camera_state.distance = distance

        # Use move_camera (correct API, not camera.frame)
        self.move_camera(run_time=run_time, rate_func=rate_func, **kwargs)

    def orbit_camera(
        self,
        duration: float = 10.0,
        rate: float = 0.2,
        direction: str = 'clockwise'
    ):
        """
        Orbit camera around scene.

        Args:
            duration: Total duration
            rate: Rotation speed
            direction: 'clockwise' or 'counterclockwise'
        """
        rotation_rate = rate if direction == 'clockwise' else -rate
        self.begin_ambient_camera_rotation(rate=rotation_rate)
        self.wait(duration)
        self.stop_ambient_camera_rotation()

    def show_title(self, title: Optional[str] = None, duration: float = 3.0):
        """
        Show title card with smooth animation.

        Args:
            title: Title text (None = use get_title())
            duration: How long to show title
        """
        if title is None:
            title = self.get_title()

        title_text = Text(title, font_size=48, color=GOLD)
        title_text.to_edge(UP)
        self.add_fixed_in_frame_mobjects(title_text)

        # Smooth write animation
        self.play(Write(title_text), run_time=1.5)
        self.wait(duration - 1.5)

        return title_text

    def show_phase_header(self, phase_name: str, duration: float = 1.5):
        """
        Show phase header (e.g., "Phase 1: Architecture Overview").

        Args:
            phase_name: Phase description
            duration: How long to show
        """
        header = Text(phase_name, font_size=36, color=BLUE)
        header.to_edge(UP)
        self.add_fixed_in_frame_mobjects(header)

        self.play(FadeIn(header), run_time=0.5)
        self.wait(duration - 0.5)

        return header

    def show_summary(
        self,
        stats: Dict[str, Any],
        duration: float = 3.0,
        position: str = 'bottom'
    ):
        """
        Show summary statistics.

        Args:
            stats: Dictionary of statistics to display
            duration: How long to show
            position: 'top' or 'bottom'
        """
        # Format statistics
        lines = [f"{key}: {value}" for key, value in stats.items()]
        summary_text = "\n".join(lines)

        summary = Text(summary_text, font_size=24, color=GREEN)

        if position == 'top':
            summary.to_edge(UP)
        else:
            summary.to_edge(DOWN)

        self.add_fixed_in_frame_mobjects(summary)

        self.play(FadeIn(summary), run_time=0.5)
        self.wait(duration - 0.5)

        return summary

    def fade_out_all(self, *mobjects, run_time: float = 1.0):
        """
        Fade out multiple mobjects smoothly.

        Args:
            *mobjects: Mobjects to fade out
            run_time: Duration of fade
        """
        self.play(
            *[FadeOut(mob) for mob in mobjects],
            run_time=run_time
        )

    def construct_phases(self):
        """
        Main visualization logic - subclasses MUST override.

        This method should implement the actual visualization phases.
        """
        raise NotImplementedError(
            "Subclasses must implement construct_phases() method"
        )

    def construct(self):
        """
        Main Manim construct method.

        Handles common setup then calls construct_phases().
        """
        # Load trace
        if not self.load_trace():
            logger.error("Failed to load trace, cannot proceed")
            # Show error message
            error_text = Text(
                "Error: Failed to load trace file",
                font_size=32,
                color=RED
            )
            self.add_fixed_in_frame_mobjects(error_text)
            self.play(Write(error_text))
            self.wait(3)
            return

        # Extract modules
        self.extract_modules(max_modules=self.config.MAX_MODULES_SHOWN)

        # Setup camera
        self.setup_camera()

        # Call subclass implementation
        try:
            self.construct_phases()
        except Exception as e:
            logger.error(f"Error in construct_phases: {e}", exc_info=True)
            # Show error
            error_text = Text(
                f"Visualization Error: {str(e)[:50]}",
                font_size=24,
                color=RED
            )
            self.add_fixed_in_frame_mobjects(error_text)
            self.play(Write(error_text))
            self.wait(3)


# Example usage: Minimal visualizer inheriting from base
class MinimalTraceVisualizer(BaseTraceVisualizer):
    """
    Minimal example showing how to use base class.
    Just override construct_phases() and get_title().
    """

    def get_title(self) -> str:
        return "Minimal Trace Visualization"

    def construct_phases(self):
        """Simple visualization using all base class methods"""

        # Phase 1: Title
        title = self.show_title()
        self.wait(1)
        self.fade_out_all(title)

        # Phase 2: Module visualization
        header = self.show_phase_header("Module Overview", duration=1)

        # Create module boxes
        for i, (module_name, calls) in enumerate(list(self.modules.items())[:5]):
            box = Cube(side_length=1, fill_opacity=0.3, fill_color=BLUE)
            box.shift(OUT * (i * 1.5))

            label = self.create_billboard_text(
                module_name.split('.')[-1][:20],
                font_size=16,
                position=box.get_center() + UP * 0.8
            )

            self.play(GrowFromCenter(box), FadeIn(label), run_time=0.5)

        # Orbit camera
        self.orbit_camera(duration=5)

        # Phase 3: Summary
        self.fade_out_all(header)
        summary = self.show_summary({
            'Total Calls': len(self.calls),
            'Modules': len(self.modules),
            'Errors': len(self.errors)
        })

        self.wait(2)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        scene = MinimalTraceVisualizer(trace_file=sys.argv[1])
        scene.render()
    else:
        print("Usage: python base_trace_visualizer.py <trace_file.json>")
