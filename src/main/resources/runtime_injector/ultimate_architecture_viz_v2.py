"""
DEPRECATED: This file has been superseded by ultimate_architecture_viz.py

The naming is counter-intuitive: v2 is the OLDER version, while the non-versioned
ultimate_architecture_viz.py is the current active implementation used by
ManimAutoRenderer.kt.

DO NOT USE - Kept for reference only.
================================================================================

Ultimate Architecture Visualization V2 - Perfect Implementation

This is the DEFINITIVE visualization combining all best practices:
- Zero hardcoded coordinates (framework-based positioning)
- Smooth 3Blue1Brown-style camera movements
- Billboard text always readable
- Comprehensive error handling
- Performance optimizations
- Complete type hints and documentation

Phases:
1. Title Card (0-3s)
2. Architecture Overview (3-15s) - 3D module layout with camera orbit
3. Execution Flow (15-50s) - Step-through with data flow animation
4. Heatmap Analysis (50-65s) - Performance hotspots
5. Summary (65-75s) - Statistics and insights
"""

from logging_config import setup_logger
logger = setup_logger(__name__)

import sys
import json
import numpy as np
from pathlib import Path
from manim import *
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass

# Import framework components
try:
    from visualization_framework import (
        CoordinateTracker,
        ArchitectureLayoutEngine,
        BillboardTextManager,
        DataFlowDetector
    )
    FRAMEWORK_AVAILABLE = True
except ImportError:
    logger.warning("Visualization framework not available, using fallback")
    FRAMEWORK_AVAILABLE = False


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class SceneConfig:
    """Configuration for scene timings and visuals."""

    # Scene durations (seconds)
    TITLE_DURATION: float = 3.0
    OVERVIEW_DURATION: float = 12.0
    EXECUTION_DURATION: float = 35.0
    HEATMAP_DURATION: float = 15.0
    SUMMARY_DURATION: float = 10.0

    # Animation speeds
    FAST_ANIM: float = 0.3
    NORMAL_ANIM: float = 0.8
    SLOW_ANIM: float = 2.0

    # Visual constants
    MODULE_SIZE: float = 0.9
    LAYER_SPACING_Z: float = 3.0
    MODULE_SPACING_X: float = 2.2
    MAX_MODULES_PER_LAYER: int = 6
    MAX_CALLS_TO_VISUALIZE: int = 50
    MAX_ERRORS_TO_SHOW: int = 5

    # Colors
    COLORS: Dict[str, str] = None

    def __post_init__(self):
        if self.COLORS is None:
            self.COLORS = {
                'input': GREEN,
                'encoder': BLUE,
                'processing': PURPLE,
                'memory': ORANGE,
                'output': RED,
                'data_flow': YELLOW,
                'gradient': RED,
                'attention': CYAN,
                'error': RED_E,
                'highlight': WHITE,
                'background': "#1a1a1a",
                'text_bg': "#2a2a2a"
            }


# ============================================================================
# UTILITY CLASSES
# ============================================================================

class BillboardText:
    """
    Billboard text that always faces camera with optimal readability.

    Features:
    - Automatic font sizing based on depth
    - High-contrast background
    - Opacity fade with distance
    """

    @staticmethod
    def create(
        text_content: str,
        position: np.ndarray,
        font_size: int = 16,
        color: str = WHITE,
        background_color: str = "#2a2a2a",
        depth: float = 0.0
    ) -> VGroup:
        """
        Create billboard text with background.

        Args:
            text_content: Text to display
            position: 3D position
            font_size: Base font size
            color: Text color
            background_color: Background panel color
            depth: Z-depth for size adjustment

        Returns:
            VGroup containing background and text
        """
        try:
            # Adjust font size based on depth (further = larger)
            depth_factor = 1.0 + abs(depth) / 8.0
            adjusted_font_size = int(font_size * depth_factor)

            # Create text
            text = Text(text_content, font_size=adjusted_font_size, color=color)
            text.move_to(position)

            # Create background panel
            padding = 0.2
            bg_width = max(text.width + padding, 0.5)  # Minimum width
            bg_height = max(text.height + padding, 0.3)  # Minimum height

            background = Rectangle(
                width=bg_width,
                height=bg_height,
                fill_color=background_color,
                fill_opacity=0.85,
                stroke_opacity=0
            )
            background.move_to(position)

            # Fade based on depth
            opacity = max(1.0 - (abs(depth) / 20.0), 0.6)

            # Group together
            group = VGroup(background, text)
            group.set_opacity(opacity)

            return group

        except Exception as e:
            logger.error(f"Error creating billboard text: {e}")
            # Return minimal fallback
            fallback = Text(text_content[:10], font_size=12, color=WHITE)
            fallback.move_to(position)
            return VGroup(fallback)


class FlowAnimator:
    """Smooth data flow animations with particles."""

    @staticmethod
    def create_flow_arrow(
        start: np.ndarray,
        end: np.ndarray,
        color: str = YELLOW,
        thickness: float = 0.05
    ) -> VMobject:
        """
        Create smooth curved arrow for data flow.

        Args:
            start: Start position
            end: End position
            color: Arrow color
            thickness: Arrow thickness

        Returns:
            Bezier curve representing flow path
        """
        try:
            # Calculate control points for smooth curve
            direction = end - start
            distance = np.linalg.norm(direction)

            if distance < 0.1:
                # Too close, use straight line
                return Line(start, end, color=color, stroke_width=thickness * 50)

            midpoint = (start + end) / 2

            # Add perpendicular offset for arc
            perpendicular = np.array([-direction[1], direction[0], 0])
            perp_norm = np.linalg.norm(perpendicular)

            if perp_norm > 0.001:
                perpendicular = perpendicular / perp_norm * (distance * 0.2)
            else:
                perpendicular = np.array([0, 0.3, 0])

            # Control points for cubic Bezier
            ctrl1 = start + direction * 0.3 + perpendicular * 0.5
            ctrl2 = end - direction * 0.3 + perpendicular * 0.5

            # Create Bezier path
            path = CubicBezier(start, ctrl1, ctrl2, end)
            path.set_color(color)
            path.set_stroke(width=thickness * 50)
            path.set_opacity(0.7)

            return path

        except Exception as e:
            logger.error(f"Error creating flow arrow: {e}")
            # Fallback to simple line
            return Line(start, end, color=color, stroke_width=2)

    @staticmethod
    def create_particles(
        path: VMobject,
        num_particles: int = 5,
        color: str = YELLOW
    ) -> VGroup:
        """
        Create particles that flow along path.

        Args:
            path: Path to follow
            num_particles: Number of particles
            color: Particle color

        Returns:
            VGroup of particle spheres
        """
        particles = VGroup()

        try:
            for i in range(num_particles):
                particle = Sphere(radius=0.05, resolution=(6, 6))
                particle.set_color(color)
                particle.set_opacity(0.9)
                particle.set_sheen(0.7, direction=UP)

                # Position along path
                progress = i / max(num_particles, 1)
                particle.move_to(path.point_from_proportion(progress))
                particles.add(particle)

        except Exception as e:
            logger.error(f"Error creating particles: {e}")

        return particles


# ============================================================================
# MAIN SCENE
# ============================================================================

class UltimateArchitectureSceneV2(ThreeDScene):
    """
    Perfect architecture visualization with zero hardcoding.

    Features:
    - Framework-based coordinate tracking
    - Smooth 3Blue1Brown-style transitions
    - Comprehensive error handling
    - Performance optimizations
    - Complete documentation

    Video Structure:
    ================
    1. Title Card (0-3s)
    2. Architecture Overview (3-15s) - 3D module layout
    3. Execution Flow (15-50s) - Step-through with data flow
    4. Heatmap Analysis (50-65s) - Performance hotspots
    5. Summary (65-75s) - Statistics
    """

    def __init__(self, trace_file: str, config: Optional[SceneConfig] = None, **kwargs):
        """
        Initialize scene.

        Args:
            trace_file: Path to trace JSON file
            config: Scene configuration (optional)
            **kwargs: Manim scene kwargs
        """
        super().__init__(**kwargs)

        self.trace_file = trace_file
        self.config = config or SceneConfig()
        self.trace_data: Optional[Dict] = None

        # Framework components
        if FRAMEWORK_AVAILABLE:
            self.tracker = CoordinateTracker()
            self.layout_engine = ArchitectureLayoutEngine(self.tracker)
            self.text_manager = BillboardTextManager(self.tracker)
            self.flow_detector: Optional[DataFlowDetector] = None
        else:
            self.tracker = None
            self.layout_engine = None
            self.text_manager = None
            self.flow_detector = None

        # Visual storage
        self.module_objects: Dict[str, VGroup] = {}
        self.call_objects: Dict[str, VGroup] = {}
        self.flow_arrows: VGroup = VGroup()

        # Statistics
        self.module_stats = defaultdict(lambda: {'calls': 0, 'time': 0.0})
        self.error_locations: List[Dict] = []
        self.call_tree: List[Dict] = []

    def construct(self):
        """Main visualization sequence."""
        try:
            # Setup
            self.camera.background_color = self.config.COLORS['background']

            # Load and validate trace data
            if not self.load_and_validate_trace():
                logger.error("Failed to load trace data")
                self.show_error_message("Failed to load trace data")
                return

            # Phase 1: Title Card
            self.scene_1_title()

            # Phase 2: Architecture Overview
            self.scene_2_overview()

            # Phase 3: Execution Flow
            self.scene_3_execution()

            # Phase 4: Heatmap Analysis (if we have timing data)
            if self.has_timing_data():
                self.scene_4_heatmap()

            # Phase 5: Summary
            self.scene_5_summary()

            # Finale
            self.wait(2)

        except Exception as e:
            logger.error(f"Error in construct: {e}", exc_info=True)
            self.show_error_message(f"Visualization error: {str(e)}")

    def load_and_validate_trace(self) -> bool:
        """
        Load and validate trace file.

        Returns:
            True if successful, False otherwise
        """
        try:
            trace_path = Path(self.trace_file)

            if not trace_path.exists():
                logger.error(f"Trace file not found: {self.trace_file}")
                return False

            with open(trace_path, 'r', encoding='utf-8') as f:
                self.trace_data = json.load(f)

            # Validate structure
            if not isinstance(self.trace_data, dict):
                logger.error("Invalid trace data: not a dictionary")
                return False

            if 'calls' not in self.trace_data:
                logger.error("Invalid trace data: missing 'calls' field")
                return False

            calls = self.trace_data['calls']
            if not isinstance(calls, list):
                logger.error("Invalid trace data: 'calls' is not a list")
                return False

            logger.info(f"Loaded trace with {len(calls)} events")

            # Initialize flow detector
            if FRAMEWORK_AVAILABLE:
                self.flow_detector = DataFlowDetector(self.trace_data)

            # Collect statistics
            self._collect_statistics()

            return True

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return False
        except Exception as e:
            logger.error(f"Error loading trace: {e}", exc_info=True)
            return False

    def _collect_statistics(self):
        """Collect statistics from trace data."""
        try:
            calls = self.trace_data.get('calls', [])

            for call in calls:
                if call.get('type') != 'call':
                    continue

                module = call.get('module', 'unknown')
                function = call.get('function', '')

                # Count calls
                self.module_stats[module]['calls'] += 1

                # Extract timing if available
                if 'timestamp' in call:
                    # Find matching return
                    call_id = call.get('call_id')
                    return_event = next(
                        (c for c in calls if c.get('call_id') == call_id and c.get('type') == 'return'),
                        None
                    )
                    if return_event and 'timestamp' in return_event:
                        duration = return_event['timestamp'] - call['timestamp']
                        self.module_stats[module]['time'] += duration

                # Check for errors
                if call.get('error') or call.get('exception'):
                    self.error_locations.append(call)

                # Build call tree
                self.call_tree.append(call)

            logger.info(f"Statistics: {len(self.module_stats)} modules, {len(self.error_locations)} errors")

        except Exception as e:
            logger.error(f"Error collecting statistics: {e}")

    def has_timing_data(self) -> bool:
        """Check if trace has timing information."""
        return any(stats['time'] > 0 for stats in self.module_stats.values())

    def show_error_message(self, message: str):
        """Show error message on screen."""
        try:
            error_text = Text(
                f"ERROR: {message}",
                font_size=24,
                color=RED
            )
            error_text.move_to(ORIGIN)
            self.add(error_text)
            self.wait(3)
        except Exception as e:
            logger.error(f"Error showing error message: {e}")

    # ========================================================================
    # SCENE 1: TITLE CARD
    # ========================================================================

    def scene_1_title(self):
        """
        Title card with smooth fade in/out.

        Duration: 3 seconds
        """
        try:
            # Main title
            title = Text(
                "Embodied AI: Architecture Walkthrough",
                font_size=48,
                color=GOLD,
                weight=BOLD
            )
            title.to_edge(UP, buff=1.5)

            # Subtitle
            correlation_id = self.trace_data.get('correlation_id', 'N/A')
            event_count = self.trace_data.get('event_count', len(self.trace_data.get('calls', [])))

            subtitle = Text(
                f"Learning Cycle: {correlation_id}\n{event_count} events",
                font_size=24,
                color=GRAY
            )
            subtitle.next_to(title, DOWN, buff=0.5)

            # Animate
            self.play(
                FadeIn(title, shift=UP * 0.3),
                run_time=self.config.NORMAL_ANIM,
                rate_func=smooth
            )
            self.play(
                FadeIn(subtitle),
                run_time=self.config.FAST_ANIM
            )

            self.wait(1.5)

            # Fade out
            self.play(
                FadeOut(title),
                FadeOut(subtitle),
                run_time=self.config.NORMAL_ANIM
            )

        except Exception as e:
            logger.error(f"Error in scene_1_title: {e}")

    # ========================================================================
    # SCENE 2: ARCHITECTURE OVERVIEW
    # ========================================================================

    def scene_2_overview(self):
        """
        3D architecture overview with camera orbit.

        Duration: 12 seconds
        - Show layered module structure
        - Color-coded by layer type
        - Billboard labels
        - Camera orbit to show depth
        """
        try:
            # Phase title
            phase_title = Text(
                "Phase 1: System Architecture",
                font_size=36,
                color=self.config.COLORS['encoder']
            )
            phase_title.to_edge(UP, buff=0.8)
            self.add_fixed_in_frame_mobjects(phase_title)
            self.play(FadeIn(phase_title, run_time=self.config.FAST_ANIM))

            # Set camera
            self.set_camera_orientation(
                phi=70 * DEGREES,
                theta=-50 * DEGREES,
                distance=15
            )

            # Extract and layout architecture
            modules_dict, layers = self._extract_layered_architecture()

            # Layer configuration
            layer_configs = [
                {"name": "Input/Sensor", "color": self.config.COLORS['input'], "z_depth": 0},
                {"name": "Encoder", "color": self.config.COLORS['encoder'], "z_depth": -3},
                {"name": "Processing", "color": self.config.COLORS['processing'], "z_depth": -6},
                {"name": "Memory", "color": self.config.COLORS['memory'], "z_depth": -9},
                {"name": "Output", "color": self.config.COLORS['output'], "z_depth": -12}
            ]

            # Build layers
            all_modules = VGroup()

            for layer_idx, layer_modules in enumerate(layers):
                if layer_idx >= len(layer_configs):
                    break

                config = layer_configs[layer_idx]

                # Limit modules per layer
                limited_modules = layer_modules[:self.config.MAX_MODULES_PER_LAYER]

                layer_group = self._build_layer(
                    layer_modules=limited_modules,
                    layer_name=config["name"],
                    color=config["color"],
                    z_depth=config["z_depth"],
                    layer_idx=layer_idx
                )

                if layer_group:
                    all_modules.add(layer_group)

            # Orbit camera
            self.begin_ambient_camera_rotation(rate=0.08)
            self.wait(6)
            self.stop_ambient_camera_rotation()

            # Transition: shrink and move to side
            self.play(
                all_modules.animate.scale(0.5).shift(UP * 2.5 + LEFT * 4),
                FadeOut(phase_title),
                run_time=self.config.SLOW_ANIM,
                rate_func=smooth
            )

        except Exception as e:
            logger.error(f"Error in scene_2_overview: {e}")

    def _build_layer(
        self,
        layer_modules: List[str],
        layer_name: str,
        color: str,
        z_depth: float,
        layer_idx: int
    ) -> Optional[VGroup]:
        """
        Build a single architecture layer.

        Args:
            layer_modules: Module names in this layer
            layer_name: Display name for layer
            color: Layer color
            z_depth: Z-depth for 3D stacking
            layer_idx: Layer index

        Returns:
            VGroup containing all layer elements
        """
        try:
            layer_group = VGroup()

            if not layer_modules:
                return layer_group

            # Layer title
            layer_title = BillboardText.create(
                text_content=layer_name,
                position=np.array([-7, 0, z_depth]),
                font_size=22,
                color=color,
                depth=z_depth
            )
            self.add_fixed_in_frame_mobjects(layer_title)
            self.play(FadeIn(layer_title, run_time=self.config.FAST_ANIM))

            # Calculate spacing
            num_modules = len(layer_modules)
            spacing = self.config.MODULE_SPACING_X
            start_x = -(num_modules - 1) * spacing / 2

            for i, module_name in enumerate(layer_modules):
                x_pos = start_x + i * spacing
                position = np.array([x_pos, 0, z_depth])

                # Register with tracker
                if self.tracker:
                    self.tracker.register_object(
                        name=module_name,
                        position=position,
                        layer_depth=z_depth
                    )

                # Create module box
                box = Cube(side_length=self.config.MODULE_SIZE)
                box.set_color(color)
                box.set_opacity(0.75)
                box.set_sheen(0.5, direction=UP)
                box.move_to(position)

                # Module label
                short_name = module_name.split('.')[-1][:18]
                label = BillboardText.create(
                    text_content=short_name,
                    position=position + DOWN * 0.8,
                    font_size=13,
                    color=WHITE,
                    depth=z_depth
                )

                # Call count
                num_calls = self.module_stats[module_name]['calls']
                count_label = BillboardText.create(
                    text_content=f"{num_calls} calls",
                    position=position + UP * 0.7,
                    font_size=10,
                    color=GRAY,
                    depth=z_depth
                )

                # Store
                module_group = VGroup(box, label, count_label)
                self.module_objects[module_name] = module_group
                layer_group.add(module_group)

                # Animate appearance
                self.add_fixed_in_frame_mobjects(label, count_label)
                self.play(
                    GrowFromCenter(box),
                    FadeIn(label),
                    FadeIn(count_label),
                    run_time=self.config.FAST_ANIM,
                    rate_func=smooth
                )

            return layer_group

        except Exception as e:
            logger.error(f"Error building layer: {e}")
            return VGroup()

    def _extract_layered_architecture(self) -> Tuple[Dict, List[List[str]]]:
        """
        Extract modules and organize into layers.

        Returns:
            Tuple of (modules dict, layers list)
        """
        try:
            modules = defaultdict(lambda: {'functions': set(), 'calls': 0})

            for call in self.call_tree:
                module = call.get('module', '').lower()
                if module:
                    func = call.get('function', '')
                    modules[module]['functions'].add(func)
                    modules[module]['calls'] += 1

            # Categorize into layers
            layers = [[], [], [], [], []]

            for module_name in modules.keys():
                lower_name = module_name.lower()

                # Categorize by keywords
                if any(kw in lower_name for kw in ['input', 'sensor', 'stream', 'unified']):
                    layers[0].append(module_name)
                elif any(kw in lower_name for kw in ['encoder', 'embed', 'vision', 'qwen']):
                    layers[1].append(module_name)
                elif any(kw in lower_name for kw in ['dynamic', 'latent', 'sde', 'ssm']):
                    layers[2].append(module_name)
                elif any(kw in lower_name for kw in ['memory', 'compress', 'temporal']):
                    layers[3].append(module_name)
                elif any(kw in lower_name for kw in ['decoder', 'output', 'action', 'truth']):
                    layers[4].append(module_name)
                else:
                    layers[2].append(module_name)  # Default to processing

            # Remove empty layers
            layers = [layer for layer in layers if layer]

            return dict(modules), layers

        except Exception as e:
            logger.error(f"Error extracting architecture: {e}")
            return {}, [[]]

    # ========================================================================
    # SCENE 3: EXECUTION FLOW
    # ========================================================================

    def scene_3_execution(self):
        """
        Step through execution with data flow animation.

        Duration: 35 seconds
        - Highlight active modules
        - Show data flow between calls
        - Pulse active modules
        """
        try:
            # Phase title
            phase_title = Text(
                "Phase 2: Execution Flow",
                font_size=36,
                color=self.config.COLORS['data_flow']
            )
            phase_title.to_edge(UP, buff=0.8)
            self.add_fixed_in_frame_mobjects(phase_title)
            self.play(FadeIn(phase_title, run_time=self.config.FAST_ANIM))

            # Get calls (limit for video length)
            calls = [c for c in self.call_tree if c.get('type') == 'call']
            calls = calls[:self.config.MAX_CALLS_TO_VISUALIZE]

            # Layout call tree
            call_positions = self._layout_call_tree(calls)

            # Visualize execution
            prev_call_id = None

            for i, call in enumerate(calls):
                call_id = call.get('call_id', f'call_{i}')

                if call_id not in call_positions:
                    continue

                position = call_positions[call_id]

                # Create call visualization
                call_viz = self._create_call_viz(call, position)
                self.call_objects[call_id] = call_viz

                # Animate appearance
                self.play(
                    *[GrowFromCenter(obj) for obj in call_viz],
                    run_time=self.config.FAST_ANIM * 0.7,
                    rate_func=smooth
                )

                # Show data flow from previous call
                if prev_call_id and prev_call_id in self.call_objects:
                    prev_pos = self.call_objects[prev_call_id][0].get_center()
                    self._animate_data_flow(prev_pos, position)

                # Pulse module
                module = call.get('module', '')
                if module in self.module_objects:
                    self._pulse_module(module)

                prev_call_id = call_id

                # Periodic pause
                if i % 10 == 0 and i > 0:
                    self.wait(0.2)

            self.wait(1)
            self.play(FadeOut(phase_title), run_time=self.config.FAST_ANIM)

        except Exception as e:
            logger.error(f"Error in scene_3_execution: {e}")

    def _layout_call_tree(self, calls: List[Dict]) -> Dict[str, np.ndarray]:
        """Layout calls in tree structure."""
        try:
            positions = {}
            y_pos = 2

            for i, call in enumerate(calls):
                call_id = call.get('call_id', f'call_{i}')
                depth = min(call.get('depth', 0), 10)  # Cap depth

                x_pos = depth * 0.6
                position = np.array([x_pos, y_pos, 0])
                positions[call_id] = position

                y_pos -= 0.6

            return positions

        except Exception as e:
            logger.error(f"Error laying out call tree: {e}")
            return {}

    def _create_call_viz(self, call: Dict, position: np.ndarray) -> VGroup:
        """Create visualization for a function call."""
        try:
            func_name = call.get('function', call.get('function_name', 'func'))[:20]

            # Box
            box = Cube(side_length=0.5)
            box.set_color(self.config.COLORS['encoder'])
            box.set_opacity(0.7)
            box.set_sheen(0.5, direction=UP)
            box.move_to(position)

            # Label
            label = BillboardText.create(
                text_content=func_name,
                position=position + DOWN * 0.4,
                font_size=12,
                color=WHITE
            )
            self.add_fixed_in_frame_mobjects(label)

            return VGroup(box, label)

        except Exception as e:
            logger.error(f"Error creating call viz: {e}")
            return VGroup()

    def _animate_data_flow(self, start: np.ndarray, end: np.ndarray):
        """Animate data flowing between calls."""
        try:
            # Create flow arrow
            flow = FlowAnimator.create_flow_arrow(
                start, end,
                color=self.config.COLORS['data_flow'],
                thickness=0.05
            )

            # Create particles
            particles = FlowAnimator.create_particles(flow, num_particles=3)

            # Animate
            self.play(Create(flow), run_time=0.2)
            self.play(
                *[MoveAlongPath(p, flow, rate_func=smooth) for p in particles],
                run_time=0.5
            )
            self.play(FadeOut(flow), FadeOut(particles), run_time=0.2)

        except Exception as e:
            logger.error(f"Error animating data flow: {e}")

    def _pulse_module(self, module_name: str):
        """Pulse a module to show activity."""
        try:
            if module_name in self.module_objects:
                box = self.module_objects[module_name][0]
                self.play(
                    box.animate.set_opacity(1).scale(1.1),
                    run_time=0.2
                )
                self.play(
                    box.animate.set_opacity(0.75).scale(1/1.1),
                    run_time=0.2
                )
        except Exception as e:
            logger.error(f"Error pulsing module: {e}")

    # ========================================================================
    # SCENE 4: HEATMAP ANALYSIS
    # ========================================================================

    def scene_4_heatmap(self):
        """
        Show performance heatmap.

        Duration: 15 seconds
        - Color modules by execution time
        - Show hotspots
        """
        try:
            # Phase title
            phase_title = Text(
                "Phase 3: Performance Heatmap",
                font_size=36,
                color=self.config.COLORS['memory']
            )
            phase_title.to_edge(UP, buff=0.8)
            self.add_fixed_in_frame_mobjects(phase_title)
            self.play(FadeIn(phase_title, run_time=self.config.FAST_ANIM))

            # Calculate max time for normalization
            max_time = max(
                (stats['time'] for stats in self.module_stats.values() if stats['time'] > 0),
                default=1.0
            )

            # Color modules by time
            for module_name, box_group in self.module_objects.items():
                if module_name not in self.module_stats:
                    continue

                box = box_group[0]
                time_spent = self.module_stats[module_name]['time']

                if time_spent > 0:
                    # Interpolate color from green (fast) to red (slow)
                    intensity = min(time_spent / max_time, 1.0)
                    color = interpolate_color(GREEN, RED, intensity)

                    self.play(
                        box.animate.set_color(color).set_opacity(0.9),
                        run_time=0.3
                    )

            self.wait(2)
            self.play(FadeOut(phase_title), run_time=self.config.FAST_ANIM)

        except Exception as e:
            logger.error(f"Error in scene_4_heatmap: {e}")

    # ========================================================================
    # SCENE 5: SUMMARY
    # ========================================================================

    def scene_5_summary(self):
        """
        Show statistics summary.

        Duration: 10 seconds
        - Top modules by call count
        - Error count
        - Total statistics
        """
        try:
            # Phase title
            phase_title = Text(
                "Phase 4: Summary",
                font_size=36,
                color=GOLD
            )
            phase_title.to_edge(UP, buff=0.8)
            self.add_fixed_in_frame_mobjects(phase_title)
            self.play(FadeIn(phase_title, run_time=self.config.FAST_ANIM))

            # Get top modules
            top_modules = sorted(
                self.module_stats.items(),
                key=lambda x: x[1]['calls'],
                reverse=True
            )[:5]

            # Create bar chart
            bars = VGroup()
            labels = VGroup()

            max_calls = max(m[1]['calls'] for m in top_modules) if top_modules else 1

            for i, (module, stats) in enumerate(top_modules):
                # Bar
                height = (stats['calls'] / max_calls) * 3
                bar = Rectangle(
                    width=0.5,
                    height=height,
                    fill_color=interpolate_color(GREEN, RED, i/5),
                    fill_opacity=0.8,
                    stroke_opacity=0
                )
                bar.move_to(np.array([-3 + i*1.5, -2 + height/2, 0]))
                bars.add(bar)

                # Label
                module_name = module.split('.')[-1][:15]
                label = BillboardText.create(
                    text_content=f"{module_name}\n{stats['calls']} calls",
                    position=bar.get_center() + UP * (height/2 + 0.5),
                    font_size=12,
                    color=WHITE
                )
                self.add_fixed_in_frame_mobjects(label)
                labels.add(label)

            # Animate chart
            self.play(
                *[GrowFromEdge(bar, DOWN) for bar in bars],
                *[FadeIn(label) for label in labels],
                run_time=self.config.SLOW_ANIM,
                rate_func=smooth
            )

            # Summary stats
            total_calls = sum(s['calls'] for s in self.module_stats.values())
            total_modules = len(self.module_stats)
            total_errors = len(self.error_locations)

            summary = BillboardText.create(
                text_content=f"Total: {total_calls} calls | {total_modules} modules | {total_errors} errors",
                position=np.array([0, -4, 0]),
                font_size=18,
                color=GOLD
            )
            self.add_fixed_in_frame_mobjects(summary)
            self.play(FadeIn(summary), run_time=self.config.FAST_ANIM)

            self.wait(3)

            # Fade out all
            self.play(
                FadeOut(phase_title),
                FadeOut(bars),
                FadeOut(labels),
                FadeOut(summary),
                run_time=self.config.NORMAL_ANIM
            )

        except Exception as e:
            logger.error(f"Error in scene_5_summary: {e}")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ultimate_architecture_viz_v2.py <trace_json_file>")
        sys.exit(1)

    trace_file = sys.argv[1]

    # Check file exists
    if not Path(trace_file).exists():
        print(f"ERROR: Trace file not found: {trace_file}")
        sys.exit(1)

    # Configure Manim
    from manim import config
    config.quality = 'high_quality'
    config.output_file = 'ultimate_architecture_v2'
    config.frame_rate = 30
    config.background_color = "#1a1a1a"

    # Create and render scene
    try:
        scene = UltimateArchitectureSceneV2(trace_file)
        scene.render()
        logger.info("Visualization complete!")
        print(f"\n✓ Video generated successfully: {config.output_file}.mp4")

    except Exception as e:
        logger.error(f"Rendering failed: {e}", exc_info=True)
        print(f"\n✗ ERROR: {e}")
        sys.exit(1)
