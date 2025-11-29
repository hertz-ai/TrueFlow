"""
Ultimate Architecture Visualization - 3Blue1Brown Style

Combines THE BEST features from all visualizers:
- system_architecture_3d.py: Module layout & 3D positioning
- coherent_unified_viz.py: Smooth phase transitions
- advanced_operation_viz.py: Operation-specific animations
- neural_flow_3d.py: Flow visualization techniques
- universal_data_flow_viz.py: Data flow detection
- visualization_framework.py: Coordinate tracking
- smooth_microanimations.py: Micro-animations

Creates ONE seamless video showing:
1. Architecture Overview (0-10s) - High-level structure
2. Execution Walkthrough (10-40s) - Step-by-step trace
3. Error Visualization (if errors) - Error propagation
4. Statistics Summary (last 10s) - Performance insights

3Blue1Brown principles:
- Smooth camera movements (no jumps)
- Clear visual hierarchy (focus + context)
- Intuitive colors (consistent meaning)
- Readable text (billboard, high contrast)
- Explanatory overlays (what's happening)
"""

from logging_config import setup_logger
logger = setup_logger(__name__)

import json
import numpy as np
import os
from pathlib import Path
from manim import *
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass


def cleanup_corrupted_svg_cache():
    """
    Remove corrupted (zero-byte) SVG files from Manim's text cache.

    This prevents cascading failures where one corrupted cache file
    breaks all subsequent video generation attempts.
    """
    cleaned = 0
    try:
        # Get Manim's text cache directory
        text_dir = config.get_dir("text_dir")
        if text_dir and text_dir.exists():
            for svg_file in text_dir.glob("*.svg"):
                if svg_file.stat().st_size == 0:
                    logger.warning(f"Removing corrupted (empty) SVG cache: {svg_file.name}")
                    svg_file.unlink()
                    cleaned += 1

        # Also check project-level media/texts
        project_dirs = [
            Path(".pycharm_plugin/manim/media/texts"),
            Path("media/texts"),
        ]
        for dir_path in project_dirs:
            if dir_path.exists():
                for svg_file in dir_path.glob("*.svg"):
                    if svg_file.stat().st_size == 0:
                        logger.warning(f"Removing corrupted (empty) SVG cache: {svg_file}")
                        svg_file.unlink()
                        cleaned += 1

        if cleaned > 0:
            logger.info(f"Cleaned {cleaned} corrupted SVG cache files")
    except Exception as e:
        logger.error(f"Error cleaning SVG cache: {e}")

    return cleaned

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
    FRAMEWORK_AVAILABLE = False
    logger.warning("Visualization framework not available")

# Import operation detection
try:
    from advanced_operation_viz import OperationDetector, OperationVisualizer
    OPERATION_VIZ_AVAILABLE = True
except ImportError:
    OPERATION_VIZ_AVAILABLE = False
    logger.warning("Operation visualizer not available")


# ============================================================================
# UTILITY CLASSES
# ============================================================================

class ImprovedBillboardText:
    """Billboard text with background for maximum readability in 3D scenes."""

    @staticmethod
    def create(text_content: str,
              position: np.ndarray,
              font_size: int = 16,
              color: str = WHITE,
              background_color: str = "#2a2a2a",
              depth: float = 0.0,
              fixed_in_frame: bool = False) -> VGroup:
        """Create billboard text with background panel.

        Args:
            text_content: The text to display
            position: 3D position for the text
            font_size: Font size
            color: Text color
            background_color: Background panel color
            depth: Z-depth (used for opacity fade)
            fixed_in_frame: If True, text stays flat (for add_fixed_in_frame_mobjects).
                           If False, text is rotated 70 degrees to face the 3D camera.
        """
        # Adjust font size based on depth (only if not fixed_in_frame)
        if not fixed_in_frame:
            depth_factor = 1.0 + abs(depth) / 8.0
            adjusted_font_size = int(font_size * depth_factor)
        else:
            adjusted_font_size = font_size

        # Create text at origin first
        text = Text(text_content, font_size=adjusted_font_size, color=color)

        # Create background panel
        padding = 0.2
        bg_width = text.width + padding
        bg_height = text.height + padding

        background = Rectangle(
            width=bg_width,
            height=bg_height,
            fill_color=background_color,
            fill_opacity=0.85,
            stroke_opacity=0
        )

        # Group at origin
        group = VGroup(background, text)

        # Only rotate for 3D objects, not for fixed_in_frame UI elements
        if not fixed_in_frame:
            # Rotate to face camera (camera is at phi=70 degrees, looking down)
            group.rotate(70 * DEGREES, axis=RIGHT)

        # Move to final position
        group.move_to(position)

        # Fade based on depth (only for 3D objects)
        if not fixed_in_frame:
            opacity = 1.0 - (abs(depth) / 20.0)
            group.set_opacity(max(opacity, 0.6))

        return group


class FIFACameraController:
    """
    FIFA-style camera that follows the action with smooth transitions.

    Shows at most 4 active elements:
    - 1 upstream (about to call)
    - 2 in focus (caller and callee)
    - 1 downstream (about to be called next)

    Camera smoothly tracks the action, showing data transformations.
    At the end, gently zooms out to show all components.
    """

    def __init__(self, scene: ThreeDScene, module_objects: Dict[str, VGroup]):
        self.scene = scene
        self.module_objects = module_objects
        self.current_focus = None
        self.visible_elements = set()
        self.dimmed_elements = set()

    def get_module_position(self, module_name: str) -> Optional[np.ndarray]:
        """Get center position of a module."""
        if module_name in self.module_objects:
            return self.module_objects[module_name][0].get_center()
        return None

    def compute_focus_window(self,
                            call_sequence: List[Dict],
                            current_idx: int) -> Dict[str, Any]:
        """
        Compute the 4-element focus window around current call.

        Returns:
            Dict with:
            - upstream: Module about to call (1 back)
            - caller: Current caller module
            - callee: Current callee module
            - downstream: Next module to be called
            - focus_center: Camera target position
        """
        window = {
            'upstream': None,
            'caller': None,
            'callee': None,
            'downstream': None,
            'focus_center': np.array([0, 0, 0])
        }

        # Current call
        if current_idx < len(call_sequence):
            current = call_sequence[current_idx]
            window['callee'] = current.get('module', '')

        # Previous call (caller)
        if current_idx > 0:
            prev = call_sequence[current_idx - 1]
            window['caller'] = prev.get('module', '')

        # Upstream (2 back)
        if current_idx > 1:
            upstream = call_sequence[current_idx - 2]
            window['upstream'] = upstream.get('module', '')

        # Downstream (next)
        if current_idx + 1 < len(call_sequence):
            downstream = call_sequence[current_idx + 1]
            window['downstream'] = downstream.get('module', '')

        # Compute focus center (weighted average of caller and callee)
        positions = []
        weights = []

        if window['caller']:
            pos = self.get_module_position(window['caller'])
            if pos is not None:
                positions.append(pos)
                weights.append(0.4)

        if window['callee']:
            pos = self.get_module_position(window['callee'])
            if pos is not None:
                positions.append(pos)
                weights.append(0.6)  # Slightly more weight to callee

        if positions:
            total_weight = sum(weights)
            window['focus_center'] = sum(p * w for p, w in zip(positions, weights)) / total_weight

        return window

    def update_visibility(self, window: Dict[str, Any], all_modules: List[str]):
        """
        Update module visibility based on focus window.

        Focused modules: Full opacity
        Window modules: Slightly dimmed
        Other modules: Very dimmed (but still visible for context)
        """
        focus_modules = {window['caller'], window['callee']} - {None}
        window_modules = {window['upstream'], window['downstream']} - {None}

        animations = []

        for module_name in all_modules:
            if module_name not in self.module_objects:
                continue

            module_group = self.module_objects[module_name]
            box = module_group[0]

            if module_name in focus_modules:
                # Full focus - bright and slightly larger
                animations.append(box.animate.set_opacity(1.0).scale(1.05))
            elif module_name in window_modules:
                # In window - visible but slightly dimmed
                animations.append(box.animate.set_opacity(0.7).scale(1.0))
            else:
                # Out of focus - dimmed for context
                animations.append(box.animate.set_opacity(0.3).scale(0.95))

        return animations

    def move_to_focus(self,
                     focus_center: np.ndarray,
                     caller_pos: Optional[np.ndarray] = None,
                     callee_pos: Optional[np.ndarray] = None) -> List:
        """
        Generate camera movement animations to focus on current action.

        Uses a side-view angle that minimizes parallax occlusion.
        """
        # Compute camera angle to view caller -> callee from the side
        if caller_pos is not None and callee_pos is not None:
            direction = callee_pos - caller_pos
            # Compute theta to view perpendicular to call direction
            theta = np.arctan2(direction[0], direction[1]) - 90 * DEGREES
        else:
            theta = -30 * DEGREES

        # Camera distance based on separation
        if caller_pos is not None and callee_pos is not None:
            separation = np.linalg.norm(callee_pos - caller_pos)
            # Closer zoom for nearby modules
            zoom = max(0.8, min(1.5, 4.0 / (separation + 2)))
        else:
            zoom = 1.0

        # Return camera movement parameters
        return {
            'frame_center': focus_center,
            'phi': 60 * DEGREES,  # Slightly less steep for less parallax
            'theta': theta,
            'zoom': zoom
        }


class DataTransformationVisualizer:
    """
    Visualize data transformations during function calls.

    Shows dimension changes, tensor shapes, and data flow types.
    """

    @staticmethod
    def create_transform_label(
        start_shape: str,
        end_shape: str,
        transform_type: str,
        position: np.ndarray,
        color: str = YELLOW
    ) -> VGroup:
        """Create a label showing data transformation."""
        # Format: [1536-D] -> encoder -> [2048-D]
        label_text = f"{start_shape} -> {transform_type} -> {end_shape}"

        label = Text(label_text, font_size=14, color=color)

        # Background
        bg = Rectangle(
            width=label.width + 0.3,
            height=label.height + 0.15,
            fill_color="#1a1a2e",
            fill_opacity=0.9,
            stroke_color=color,
            stroke_width=1
        )

        group = VGroup(bg, label)
        group.move_to(position)

        return group

    @staticmethod
    def detect_transformation(call: Dict) -> Optional[Dict[str, str]]:
        """
        Detect data transformation from call metadata.

        Returns dict with start_shape, end_shape, transform_type.
        """
        func_name = call.get('function', call.get('function_name', ''))
        module = call.get('module', '')

        # Common transformations based on function/module names
        transforms = {
            'encode': {'type': 'encode', 'in': '[B,H,W,C]', 'out': '[B,1536]'},
            'forward': {'type': 'forward', 'in': '[B,D]', 'out': '[B,D]'},
            'project': {'type': 'project', 'in': '[B,1536]', 'out': '[B,2048]'},
            'predict': {'type': 'predict', 'in': '[B,2048]', 'out': '[B,1024]'},
            'decode': {'type': 'decode', 'in': '[B,1024]', 'out': '[B,vocab]'},
            'fuse': {'type': 'fuse', 'in': '[B,D1]+[B,D2]', 'out': '[B,2048]'},
            'compress': {'type': 'compress', 'in': '[B,2048]', 'out': '[B,128]'},
            'expand': {'type': 'expand', 'in': '[B,128]', 'out': '[B,1024]'},
        }

        func_lower = func_name.lower()
        for key, transform in transforms.items():
            if key in func_lower:
                return {
                    'start_shape': transform['in'],
                    'end_shape': transform['out'],
                    'transform_type': transform['type']
                }

        # Default: show function name as transform
        return {
            'start_shape': '[data]',
            'end_shape': '[data]',
            'transform_type': func_name[:15]
        }


class FlowAnimator:
    """Smooth data flow animations with transformation visualization."""

    @staticmethod
    def create_flow_arrow(start: np.ndarray,
                         end: np.ndarray,
                         color: str = YELLOW,
                         thickness: float = 0.05) -> VMobject:
        """Create smooth curved arrow for data flow."""
        # Control points for Bezier curve
        direction = end - start
        midpoint = (start + end) / 2

        # Add slight upward arc
        perpendicular = np.array([-direction[1], direction[0], 0])
        perpendicular = perpendicular / (np.linalg.norm(perpendicular) + 0.001)

        ctrl1 = start + direction * 0.3 + perpendicular * 0.4
        ctrl2 = end - direction * 0.3 + perpendicular * 0.4

        # Create Bezier path
        path = CubicBezier(start, ctrl1, ctrl2, end)
        path.set_color(color)
        path.set_stroke(width=thickness * 50)
        path.set_opacity(0.7)

        return path

    @staticmethod
    def create_transform_flow(
        start: np.ndarray,
        end: np.ndarray,
        transform_info: Dict[str, str],
        color: str = YELLOW
    ) -> Tuple[VMobject, VGroup]:
        """
        Create flow arrow with transformation label.

        Returns:
            Tuple of (flow_path, transform_label)
        """
        # Create the flow path
        path = FlowAnimator.create_flow_arrow(start, end, color)

        # Create transformation label at midpoint
        midpoint = (start + end) / 2 + np.array([0, 0.5, 0])  # Slightly above

        label = DataTransformationVisualizer.create_transform_label(
            start_shape=transform_info.get('start_shape', '[?]'),
            end_shape=transform_info.get('end_shape', '[?]'),
            transform_type=transform_info.get('transform_type', 'transform'),
            position=midpoint,
            color=color
        )

        return path, label

    @staticmethod
    def create_particles(path: VMobject,
                        num_particles: int = 5,
                        color: str = YELLOW) -> VGroup:
        """Create particles that flow along path."""
        particles = VGroup()

        for i in range(num_particles):
            particle = Sphere(radius=0.05, resolution=(6, 6))
            particle.set_color(color)
            particle.set_opacity(0.9)
            particle.set_sheen(0.7, direction=UP)

            # Position along path
            progress = i / num_particles
            particle.move_to(path.point_from_proportion(progress))
            particles.add(particle)

        return particles


# ============================================================================
# MAIN SCENE
# ============================================================================

class UltimateArchitectureScene(ThreeDScene):
    """
    The ultimate architecture visualization combining all best practices.

    Video Structure:
    ===============

    PHASE 1: ARCHITECTURE OVERVIEW (0-10s)
    - Show 3D module structure with proper depth
    - Billboard labels, readable text
    - Smooth camera orbit
    - Color-coded by layer type

    PHASE 2: EXECUTION WALKTHROUGH (10-40s)
    - Step through each call in trace
    - Highlight active modules
    - Show data flow between functions
    - Display parameter types and values
    - Animate transformations

    PHASE 3: ERROR VISUALIZATION (if errors)
    - Show error locations in red
    - Trace error propagation
    - Highlight affected components

    PHASE 4: STATISTICS SUMMARY (last 10s)
    - Call counts per module
    - Performance hotspots
    - Most complex execution paths

    3Blue1Brown Style:
    ==================
    - Smooth transitions (run_time=2-3s, rate_func=smooth)
    - Progressive disclosure (show only relevant info)
    - Consistent colors (blue=data, green=success, red=error)
    - Large readable text (font_size=24+)
    - Explanatory overlays (text explaining what's happening)
    """

    def __init__(self, trace_file: str, **kwargs):
        super().__init__(**kwargs)
        self.trace_file = trace_file
        self.trace_data = None

        # Framework components
        if FRAMEWORK_AVAILABLE:
            self.tracker = CoordinateTracker()
            self.layout_engine = ArchitectureLayoutEngine(self.tracker)
            self.flow_detector = None
        else:
            self.tracker = None
            self.layout_engine = None
            self.flow_detector = None

        # Operation detector
        if OPERATION_VIZ_AVAILABLE:
            self.operation_detector = OperationDetector()
            self.operation_visualizer = OperationVisualizer()
        else:
            self.operation_detector = None
            self.operation_visualizer = None

        # Visual storage
        self.module_objects: Dict[str, VGroup] = {}
        self.call_objects: Dict[str, VGroup] = {}
        self.flow_arrows: VGroup = VGroup()

        # Statistics
        self.module_stats = defaultdict(lambda: {'calls': 0, 'time': 0})
        self.error_locations = []

    def construct(self):
        """Main visualization sequence."""
        # Clean corrupted SVG cache before rendering to prevent cascading failures
        cleanup_corrupted_svg_cache()

        # Setup
        self.camera.background_color = "#1a1a1a"

        # Load data
        self.load_and_analyze()

        # Title
        title = Text("Embodied AI: Complete Architecture Walkthrough",
                    font_size=40, color=GOLD, weight=BOLD)
        title.to_edge(UP, buff=0.5)
        self.add_fixed_in_frame_mobjects(title)
        self.play(Write(title, run_time=1.5))
        self.wait(0.5)

        # === PHASE 1: ARCHITECTURE OVERVIEW ===
        self.play(FadeOut(title), run_time=0.5)
        self.phase1_architecture_overview()

        # === PHASE 2: EXECUTION WALKTHROUGH (FIFA-style) ===
        self.phase2_execution_walkthrough()

        # === PHASE 3: DATA FLOW DEEP DIVE ===
        self.phase3_data_flow_deep_dive()

        # === PHASE 4: ERROR VISUALIZATION (if errors) ===
        if self.error_locations:
            self.phase4_error_visualization()

        # === PHASE 5: PERFORMANCE METRICS ===
        self.phase5_performance_metrics()

        # Finale
        self.wait(2)

    def load_and_analyze(self):
        """Load trace and extract architecture."""
        with open(self.trace_file, 'r') as f:
            self.trace_data = json.load(f)

        if FRAMEWORK_AVAILABLE:
            self.flow_detector = DataFlowDetector(self.trace_data)

        # Collect statistics
        calls = self.trace_data.get('calls', [])
        for call in calls:
            module = call.get('module', 'unknown')
            self.module_stats[module]['calls'] += 1

            # Check for errors (check both 'error' and 'exception' fields)
            if call.get('error') or call.get('exception'):
                self.error_locations.append(call)

        logger.info(f"Loaded trace with {len(calls)} calls, {len(self.error_locations)} errors")

    # ========================================================================
    # PHASE 1: ARCHITECTURE OVERVIEW
    # ========================================================================

    def phase1_architecture_overview(self):
        """
        Show high-level 3D architecture with smooth camera movement.

        Duration: 10 seconds
        - Modules stacked by layer (input -> output)
        - Color-coded by function
        - Billboard labels
        - Smooth camera orbit
        """
        # Phase title
        phase_title = Text("Phase 1: System Architecture",
                          font_size=36, color=BLUE)
        phase_title.to_edge(UP, buff=0.8)
        self.add_fixed_in_frame_mobjects(phase_title)
        self.play(FadeIn(phase_title, run_time=0.5))

        # Set camera
        self.set_camera_orientation(phi=70 * DEGREES, theta=-50 * DEGREES, distance=15)

        # Extract architecture
        modules, layers = self._extract_layered_architecture()

        # Layer configuration
        layer_info = [
            {"name": "Input/Sensor", "color": GREEN, "z_depth": 0},
            {"name": "Encoder", "color": BLUE, "z_depth": -3},
            {"name": "Processing", "color": PURPLE, "z_depth": -6},
            {"name": "Memory", "color": ORANGE, "z_depth": -9},
            {"name": "Output/Decoder", "color": RED, "z_depth": -12}
        ]

        # Build each layer
        all_modules = VGroup()
        for layer_idx, layer_modules in enumerate(layers):
            if layer_idx >= len(layer_info):
                break

            info = layer_info[layer_idx]
            layer_group = self.build_layer(
                layer_modules=layer_modules[:6],  # Max 6 per layer
                layer_name=info["name"],
                color=info["color"],
                z_depth=info["z_depth"],
                layer_idx=layer_idx
            )
            all_modules.add(layer_group)

        # Orbit camera to show 3D depth
        self.begin_ambient_camera_rotation(rate=0.08)
        self.wait(6)
        self.stop_ambient_camera_rotation()

        # Transition: Shrink architecture, keep visible
        self.play(
            all_modules.animate.scale(0.5).shift(UP * 2.5 + LEFT * 4),
            FadeOut(phase_title),
            run_time=2,
            rate_func=smooth
        )

    def build_layer(self,
                   layer_modules: List[str],
                   layer_name: str,
                   color: str,
                   z_depth: float,
                   layer_idx: int) -> VGroup:
        """Build a single architecture layer."""
        layer_group = VGroup()

        # Layer title - fixed_in_frame elements should use 2D screen coordinates (z=0)
        # Position vertically based on layer_idx to create a stacked legend on the left
        # Frame is approx 8 units tall (-4 to +4), put legend at top-left
        legend_y = 3.0 - layer_idx * 0.8  # Stack vertically from top
        layer_title = ImprovedBillboardText.create(
            text_content=layer_name,
            position=np.array([-6.0, legend_y, 0]),  # z=0 for fixed_in_frame (no Z occlusion!)
            font_size=22,
            color=color,
            depth=0,  # No depth for UI elements
            fixed_in_frame=True  # UI element, don't rotate
        )
        self.add_fixed_in_frame_mobjects(layer_title)
        self.play(FadeIn(layer_title, run_time=0.3))

        # Calculate spacing - ensure modules stay within frame bounds
        # Frame is 14 units wide, leave 1.5 unit margin on each side = 11 usable
        num_modules = len(layer_modules)
        max_span = 10.0  # Maximum span for all modules
        spacing = min(2.2, max_span / max(num_modules - 1, 1))
        start_x = -(num_modules - 1) * spacing / 2

        for i, module_name in enumerate(layer_modules):
            x_pos = start_x + i * spacing
            position = np.array([x_pos, 0, z_depth])

            # Register position
            if self.tracker:
                self.tracker.register_object(
                    name=module_name,
                    position=position,
                    layer_depth=z_depth
                )

            # Create module box
            box_size = 0.9
            box = Cube(side_length=box_size)
            box.set_color(color)
            box.set_opacity(0.75)
            box.set_sheen(0.5, direction=UP)
            box.move_to(position)

            # Module label - rotated to face camera in 3D space
            short_name = module_name.split('.')[-1][:18]
            label = ImprovedBillboardText.create(
                text_content=short_name,
                position=position + DOWN * 0.8,
                font_size=13,
                color=WHITE,
                depth=z_depth
            )

            # Function count - rotated to face camera in 3D space
            num_funcs = self.module_stats[module_name]['calls']
            func_label = ImprovedBillboardText.create(
                text_content=f"{num_funcs} calls",
                position=position + UP * 0.7,
                font_size=10,
                color=GRAY,
                depth=z_depth
            )

            # Store - include all in module_group so they move together
            module_group = VGroup(box, label, func_label)
            self.module_objects[module_name] = module_group
            layer_group.add(module_group)

            # Animate appearance (no fixed_in_frame - let them move with 3D objects)
            self.play(
                GrowFromCenter(box),
                FadeIn(label),
                FadeIn(func_label),
                run_time=0.4,
                rate_func=smooth
            )

        return layer_group

    # ========================================================================
    # PHASE 2: EXECUTION WALKTHROUGH (FIFA-STYLE CAMERA)
    # ========================================================================

    def phase2_execution_walkthrough(self):
        """
        FIFA-style execution walkthrough with dynamic camera.

        Features:
        - Shows at most 4 active elements (1 upstream, 2 focus, 1 downstream)
        - Smooth camera transitions following the action
        - Data transformation visualization during flow
        - Gentle zoom out at end to show all components
        """
        # Phase title
        phase_title = Text("Phase 2: Execution Walkthrough",
                          font_size=36, color=GREEN)
        phase_title.to_edge(UP, buff=0.8)
        self.add_fixed_in_frame_mobjects(phase_title)
        self.play(FadeIn(phase_title, run_time=0.5))

        # Initialize FIFA camera controller
        fifa_camera = FIFACameraController(self, self.module_objects)
        all_module_names = list(self.module_objects.keys())

        # Get calls
        calls = self.trace_data.get('calls', [])[:50]  # Limit to 50 calls

        if not calls:
            self.wait(2)
            self.play(FadeOut(phase_title), run_time=0.5)
            return

        # Initial camera setup - start with first module in focus
        first_call = calls[0]
        first_module = first_call.get('module', '')
        if first_module and first_module in self.module_objects:
            first_pos = self.module_objects[first_module][0].get_center()
            self.move_camera(
                frame_center=first_pos,
                phi=60*DEGREES,
                theta=-30*DEGREES,
                zoom=1.2,
                run_time=2,
                rate_func=smooth
            )

        # Track previous module for flow animation
        prev_module = None
        prev_pos = None
        current_call_overlay = None  # Track current call info overlay

        # Process each call with FIFA-style focus
        for i, call in enumerate(calls):
            # Compute focus window
            window = fifa_camera.compute_focus_window(calls, i)

            current_module = call.get('module', '')
            func_name = call.get('function', call.get('function_name', 'func'))

            # Get positions
            caller_pos = fifa_camera.get_module_position(window['caller']) if window['caller'] else None
            callee_pos = fifa_camera.get_module_position(window['callee']) if window['callee'] else None

            # Update module visibility (focus on active, dim others)
            visibility_anims = fifa_camera.update_visibility(window, all_module_names)

            # Compute camera parameters
            camera_params = fifa_camera.move_to_focus(
                window['focus_center'],
                caller_pos,
                callee_pos
            )

            # Create call info overlay showing ClassName.method()
            new_call_overlay = self._create_call_info_overlay(call, callee_pos if callee_pos is not None else np.array([0,0,0]))
            self.add_fixed_in_frame_mobjects(new_call_overlay)

            # Combine visibility animations with overlay transitions
            all_anims = visibility_anims.copy()

            if current_call_overlay is not None:
                all_anims.append(FadeOut(current_call_overlay))

            all_anims.append(FadeIn(new_call_overlay))

            if all_anims:
                self.play(*all_anims, run_time=0.4, rate_func=smooth)

            current_call_overlay = new_call_overlay

            # Show data flow with transformation
            if prev_module and prev_pos is not None and callee_pos is not None:
                # Detect transformation type
                transform_info = DataTransformationVisualizer.detect_transformation(call)

                # Create flow with transformation label
                flow_path, transform_label = FlowAnimator.create_transform_flow(
                    prev_pos,
                    callee_pos,
                    transform_info,
                    color=YELLOW
                )

                # Animate flow
                self.play(Create(flow_path), FadeIn(transform_label), run_time=0.3)

                # Create and animate particles
                particles = FlowAnimator.create_particles(flow_path, num_particles=3, color=YELLOW)
                self.play(
                    *[MoveAlongPath(p, flow_path, rate_func=smooth) for p in particles],
                    run_time=0.4
                )

                # Fade out flow elements
                self.play(
                    FadeOut(flow_path),
                    FadeOut(transform_label),
                    FadeOut(particles),
                    run_time=0.2
                )

            # Update previous module
            prev_module = current_module
            prev_pos = callee_pos

            # Brief pause every 5 calls
            if i % 5 == 0:
                self.wait(0.1)

        # Fade out last call overlay before zoom out
        if current_call_overlay is not None:
            self.play(FadeOut(current_call_overlay), run_time=0.3)

        # Final zoom out to show all components
        self._zoom_out_to_show_all()

        self.wait(1)
        self.play(FadeOut(phase_title), run_time=0.5)

    def _zoom_out_to_show_all(self):
        """
        Gently zoom out to show all components after execution walkthrough.

        Restores all modules to full visibility and positions camera
        to show the complete architecture.
        """
        # Reset all module visibility
        reset_anims = []
        for module_name, module_group in self.module_objects.items():
            box = module_group[0]
            reset_anims.append(box.animate.set_opacity(0.75).scale(1.0))

        # Calculate bounding box of all modules
        all_positions = []
        for module_group in self.module_objects.values():
            all_positions.append(module_group[0].get_center())

        if all_positions:
            center = np.mean(all_positions, axis=0)

            # Compute required zoom to fit all
            x_coords = [p[0] for p in all_positions]
            y_coords = [p[1] for p in all_positions]
            z_coords = [p[2] for p in all_positions]

            span_x = max(x_coords) - min(x_coords) + 4
            span_y = max(y_coords) - min(y_coords) + 4
            span_z = max(z_coords) - min(z_coords) + 4

            max_span = max(span_x, span_y, span_z)
            zoom = min(1.0, 8.0 / max_span)  # Fit within frame
        else:
            center = np.array([0, 0, 0])
            zoom = 1.0

        # Animate zoom out with visibility reset
        if reset_anims:
            self.play(
                *reset_anims,
                run_time=2,
                rate_func=smooth
            )

        # Final camera position showing full architecture
        self.move_camera(
            phi=70*DEGREES,
            theta=-45*DEGREES,
            zoom=zoom,
            run_time=2,
            rate_func=smooth
        )

    # ========================================================================
    # DEPRECATED LEGACY METHODS (kept for reference, not actively used)
    # ========================================================================
    # The following methods are deprecated and not called by the main flow:
    # - _phase2_legacy_execution_walkthrough
    # - _create_call_viz (legacy)
    # - _animate_data_flow (legacy)
    # - _pulse_module (legacy)
    # - _is_in_viewport (legacy)
    # - _layout_call_tree (legacy)
    # These have been replaced by FIFA-style camera system in phase2_execution_walkthrough()
    # ========================================================================

    def _create_call_viz(self, call: Dict, position: np.ndarray) -> VGroup:
        """DEPRECATED: Create visualization for a function call with class.method display."""
        # Extract class and method name
        func_name = call.get('function', call.get('function_name', 'func'))
        module = call.get('module', '')

        # Parse class name from module path (e.g., "learning.semantic_reasoner" -> "SemanticReasoner")
        class_name = self._extract_class_name(module, func_name)
        method_name = func_name[:20]

        # Box for function
        box = Cube(side_length=0.5)
        box.set_color(BLUE)
        box.set_opacity(0.7)
        box.set_sheen(0.5, direction=UP)
        box.move_to(position)

        # Class name label (above the box)
        class_label = ImprovedBillboardText.create(
            text_content=class_name,
            position=position + UP * 0.5,
            font_size=11,
            color=BLUE_B
        )

        # Method name label (below the box)
        method_label = ImprovedBillboardText.create(
            text_content=method_name,
            position=position + DOWN * 0.4,
            font_size=12,
            color=WHITE
        )

        # Return all so they move together
        return VGroup(box, class_label, method_label)

    def _extract_class_name(self, module: str, func_name: str) -> str:
        """
        Extract class name from module path.

        Examples:
            "learning.semantic_reasoner" + "forward" -> "SemanticReasoner"
            "models.qwen_vl_wrapper" + "encode_image" -> "QwenVLWrapper"
            "memory.episodic_memory" + "append" -> "EpisodicMemory"
        """
        if not module:
            return "Unknown"

        # Get last part of module path
        module_name = module.split('.')[-1]

        # Convert snake_case to PascalCase
        parts = module_name.split('_')
        class_name = ''.join(part.capitalize() for part in parts)

        # Truncate if too long
        return class_name[:18]

    def _create_call_info_overlay(self, call: Dict, position: np.ndarray) -> VGroup:
        """
        Create an overlay showing class.method info during FIFA-style walkthrough.

        Displays in the corner of the screen as a fixed-in-frame element.
        """
        func_name = call.get('function', call.get('function_name', 'func'))
        module = call.get('module', '')
        class_name = self._extract_class_name(module, func_name)

        # Format: ClassName.method_name()
        full_name = f"{class_name}.{func_name}()"

        # Create info box
        info_text = Text(full_name, font_size=20, color=WHITE)

        # Background
        bg = Rectangle(
            width=info_text.width + 0.4,
            height=info_text.height + 0.2,
            fill_color="#1a1a2e",
            fill_opacity=0.9,
            stroke_color=BLUE,
            stroke_width=2
        )

        group = VGroup(bg, info_text)
        group.to_corner(DR, buff=0.5)  # Bottom-right corner

        return group

    def _animate_data_flow(self, start: np.ndarray, end: np.ndarray):
        """DEPRECATED: Animate data flowing between calls."""
        # Create flow arrow
        flow = FlowAnimator.create_flow_arrow(start, end, color=YELLOW, thickness=0.05)

        # Create particles
        particles = FlowAnimator.create_particles(flow, num_particles=3, color=YELLOW)

        # Animate
        self.play(Create(flow), run_time=0.2)
        self.play(
            *[MoveAlongPath(p, flow, rate_func=smooth) for p in particles],
            run_time=0.5
        )
        self.play(FadeOut(flow), FadeOut(particles), run_time=0.2)

    def _pulse_module(self, module_name: str):
        """DEPRECATED: Pulse a module to show activity."""
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

    # ========================================================================
    # PHASE 3: DATA FLOW DEEP DIVE (Slow-motion with parameters)
    # ========================================================================

    def phase3_data_flow_deep_dive(self):
        """
        Deep dive into data flow with slow-motion visualization.

        Features:
        - Zoom into key data transformations (8x slowdown)
        - Show parameter names, types, and values
        - Display tensor shapes and dimensions
        - Visualize internal method transformations
        - Cover all data branches systematically
        """
        phase_title = Text("Phase 3: Data Flow Deep Dive",
                          font_size=36, color=ORANGE)
        phase_title.to_edge(UP, buff=0.8)
        self.add_fixed_in_frame_mobjects(phase_title)
        self.play(FadeIn(phase_title, run_time=0.5))

        calls = self.trace_data.get('calls', [])

        # Find key transformation calls (encode, forward, project, etc.)
        key_transforms = self._find_key_transformations(calls)

        # Track data branches for systematic coverage
        data_branches = self._analyze_data_branches(calls)

        # Show branch overview
        self._show_branch_overview(data_branches)

        # Deep dive into each key transformation
        for i, transform_call in enumerate(key_transforms[:5]):  # Limit to 5 deep dives
            self._deep_dive_transformation(transform_call, i + 1, len(key_transforms[:5]))

        self.wait(1)
        self.play(FadeOut(phase_title), run_time=0.5)

    def _find_key_transformations(self, calls: List[Dict]) -> List[Dict]:
        """Find calls that represent key data transformations."""
        key_keywords = [
            'encode', 'decode', 'forward', 'project', 'fuse', 'transform',
            'predict', 'compress', 'expand', 'learn', 'update'
        ]

        key_transforms = []
        for call in calls:
            func_name = call.get('function', call.get('function_name', '')).lower()
            for keyword in key_keywords:
                if keyword in func_name:
                    key_transforms.append(call)
                    break

        return key_transforms

    def _analyze_data_branches(self, calls: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Analyze data flow branches.

        Returns dict mapping branch names to their call sequences.
        """
        branches = defaultdict(list)

        # Group by module to identify branches
        for call in calls:
            module = call.get('module', 'unknown')
            # Identify branch by top-level module
            branch = module.split('.')[0] if '.' in module else module
            branches[branch].append(call)

        return dict(branches)

    def _show_branch_overview(self, branches: Dict[str, List[Dict]]):
        """Show overview of all data branches."""
        # Create branch summary panel
        branch_info = VGroup()

        title = Text("Data Flow Branches:", font_size=18, color=ORANGE)
        branch_info.add(title)

        for i, (branch_name, calls) in enumerate(list(branches.items())[:6]):
            branch_text = Text(
                f"  {branch_name}: {len(calls)} calls",
                font_size=14,
                color=WHITE
            )
            branch_info.add(branch_text)

        branch_info.arrange(DOWN, aligned_edge=LEFT, buff=0.15)
        branch_info.to_corner(UL, buff=0.5)

        # Background
        bg = Rectangle(
            width=branch_info.width + 0.4,
            height=branch_info.height + 0.3,
            fill_color="#1a1a2e",
            fill_opacity=0.9,
            stroke_color=ORANGE,
            stroke_width=1
        )
        bg.move_to(branch_info.get_center())

        panel = VGroup(bg, branch_info)
        self.add_fixed_in_frame_mobjects(panel)
        self.play(FadeIn(panel), run_time=0.5)
        self.wait(2)
        self.play(FadeOut(panel), run_time=0.3)

    def _deep_dive_transformation(self, call: Dict, index: int, total: int):
        """
        Deep dive into a single transformation with slow-motion.

        Shows:
        - Zoom into the transformation
        - Parameter details (name, type, value/shape)
        - Internal data flow
        - Output transformation
        """
        module = call.get('module', '')
        func_name = call.get('function', call.get('function_name', 'func'))
        class_name = self._extract_class_name(module, func_name)

        # Get module position for zoom
        if module in self.module_objects:
            module_pos = self.module_objects[module][0].get_center()
        else:
            module_pos = np.array([0, 0, 0])

        # Progress indicator
        progress_text = Text(
            f"Deep Dive {index}/{total}: {class_name}.{func_name}()",
            font_size=16,
            color=ORANGE
        )
        progress_text.to_corner(UR, buff=0.5)
        self.add_fixed_in_frame_mobjects(progress_text)
        self.play(FadeIn(progress_text), run_time=0.3)

        # SLOW MOTION: Zoom into module (8x slower)
        # Use move_camera for ThreeDCamera (no .animate property)
        self.move_camera(
            frame_center=module_pos,
            run_time=1.5,
            rate_func=smooth
        )
        self.move_camera(
            phi=45*DEGREES,
            theta=-20*DEGREES,
            zoom=2.0,  # Zoom in close
            run_time=1.5,
            rate_func=smooth
        )

        # Create parameter visualization panel
        param_panel = self._create_parameter_panel(call)
        self.add_fixed_in_frame_mobjects(param_panel)
        self.play(FadeIn(param_panel), run_time=0.5)

        # Show internal transformation animation
        self._animate_internal_transformation(call, module_pos)

        # Hold for inspection
        self.wait(1.5)

        # Fade out and zoom back
        self.play(
            FadeOut(param_panel),
            FadeOut(progress_text),
            run_time=0.3
        )

        # Zoom back out
        self.move_camera(
            phi=60*DEGREES,
            theta=-30*DEGREES,
            zoom=1.0,
            run_time=1.0,
            rate_func=smooth
        )

    def _create_parameter_panel(self, call: Dict) -> VGroup:
        """
        Create a panel showing parameter details.

        Shows parameter names, types, tensor shapes, and sample values.
        """
        func_name = call.get('function', call.get('function_name', 'func'))
        args = call.get('args', {})
        kwargs = call.get('kwargs', {})

        # Detect tensor shapes and types from function context
        param_info = self._infer_parameter_info(func_name, args, kwargs)

        panel_items = VGroup()

        # Header
        header = Text(f"Parameters:", font_size=16, color=YELLOW)
        panel_items.add(header)

        # Parameter entries
        for param_name, param_details in list(param_info.items())[:6]:
            param_type = param_details.get('type', 'unknown')
            param_shape = param_details.get('shape', '')
            param_value = param_details.get('value', '')

            # Format: param_name: Type[shape] = value
            if param_shape:
                param_text = f"  {param_name}: {param_type}{param_shape}"
            else:
                param_text = f"  {param_name}: {param_type}"

            if param_value:
                param_text += f" = {param_value}"

            text = Text(param_text[:50], font_size=12, color=WHITE)
            panel_items.add(text)

        # Output info
        output_header = Text("Output:", font_size=16, color=GREEN)
        panel_items.add(output_header)

        output_info = self._infer_output_info(func_name)
        output_text = Text(f"  {output_info}", font_size=12, color=WHITE)
        panel_items.add(output_text)

        panel_items.arrange(DOWN, aligned_edge=LEFT, buff=0.1)
        panel_items.to_corner(DL, buff=0.5)

        # Background
        bg = Rectangle(
            width=panel_items.width + 0.4,
            height=panel_items.height + 0.3,
            fill_color="#1a1a2e",
            fill_opacity=0.95,
            stroke_color=YELLOW,
            stroke_width=1
        )
        bg.move_to(panel_items.get_center())

        return VGroup(bg, panel_items)

    def _infer_parameter_info(self, func_name: str, args: Dict, kwargs: Dict) -> Dict:
        """
        Infer parameter information from function name and context.

        Returns dict of param_name -> {type, shape, value}
        """
        func_lower = func_name.lower()

        # Common parameter patterns based on function type
        param_patterns = {
            'encode': {
                'input': {'type': 'Tensor', 'shape': '[B,C,H,W]'},
                'return_attention': {'type': 'bool', 'value': 'False'}
            },
            'forward': {
                'x': {'type': 'Tensor', 'shape': '[B,D]'},
                'hidden_state': {'type': 'Optional[Tensor]', 'shape': '[B,H]'}
            },
            'project': {
                'features': {'type': 'Tensor', 'shape': '[B,1536]'},
                'output': {'type': 'Tensor', 'shape': '[B,2048]'}
            },
            'predict': {
                'current_state': {'type': 'Tensor', 'shape': '[B,2048]'},
                'action': {'type': 'Tensor', 'shape': '[B,64]'}
            },
            'learn': {
                'experience': {'type': 'Experience', 'shape': ''},
                'learning_rate': {'type': 'float', 'value': '0.001'}
            },
            'fuse': {
                'visual': {'type': 'Tensor', 'shape': '[B,1536]'},
                'language': {'type': 'Tensor', 'shape': '[B,1536]'},
                'audio': {'type': 'Optional[Tensor]', 'shape': '[B,512]'}
            },
            'compress': {
                'state': {'type': 'Tensor', 'shape': '[B,2048]'},
                'output': {'type': 'Tensor', 'shape': '[B,128]'}
            }
        }

        for pattern_key, params in param_patterns.items():
            if pattern_key in func_lower:
                return params

        # Default parameters
        return {
            'input': {'type': 'Tensor', 'shape': '[B,D]'},
            'kwargs': {'type': 'Dict', 'value': '...'}
        }

    def _infer_output_info(self, func_name: str) -> str:
        """Infer output information from function name."""
        func_lower = func_name.lower()

        output_patterns = {
            'encode': 'Tensor[B,1536], Optional[Attention]',
            'forward': 'Tensor[B,D]',
            'project': 'Tensor[B,2048]',
            'predict': 'Tensor[B,1024] (next_state)',
            'decode': 'Tensor[B,vocab_size]',
            'learn': 'Dict{loss, metrics}',
            'fuse': 'Tensor[B,2048] (unified)',
            'compress': 'Tensor[B,128] (latent)',
            'expand': 'Tensor[B,1024]'
        }

        for pattern_key, output in output_patterns.items():
            if pattern_key in func_lower:
                return output

        return 'Tensor[B,D]'

    def _animate_internal_transformation(self, call: Dict, position: np.ndarray):
        """
        Animate internal data transformation within a method.

        Shows data flowing through the transformation.
        """
        func_name = call.get('function', call.get('function_name', ''))
        transform_info = DataTransformationVisualizer.detect_transformation(call)

        # Create input tensor visualization
        input_shape = transform_info.get('start_shape', '[B,D]')
        output_shape = transform_info.get('end_shape', '[B,D]')

        # Input tensor (left of module)
        input_tensor = self._create_tensor_viz(input_shape, position + LEFT * 1.5, BLUE)

        # Output tensor (right of module)
        output_tensor = self._create_tensor_viz(output_shape, position + RIGHT * 1.5, GREEN)

        # Animate: input appears
        self.play(FadeIn(input_tensor), run_time=0.4)

        # Animate: transformation arrow
        transform_arrow = Arrow(
            position + LEFT * 0.8,
            position + RIGHT * 0.8,
            color=YELLOW,
            buff=0.1
        )
        transform_label = Text(
            transform_info.get('transform_type', 'transform'),
            font_size=12,
            color=YELLOW
        )
        transform_label.next_to(transform_arrow, UP, buff=0.1)

        self.play(
            GrowArrow(transform_arrow),
            FadeIn(transform_label),
            run_time=0.5
        )

        # Animate: output appears
        self.play(FadeIn(output_tensor), run_time=0.4)

        # Hold
        self.wait(0.5)

        # Cleanup
        self.play(
            FadeOut(input_tensor),
            FadeOut(output_tensor),
            FadeOut(transform_arrow),
            FadeOut(transform_label),
            run_time=0.3
        )

    def _create_tensor_viz(self, shape_str: str, position: np.ndarray, color) -> VGroup:
        """Create a visual representation of a tensor."""
        # Create a small 3D box representing the tensor
        tensor_box = Cube(side_length=0.4)
        tensor_box.set_color(color)
        tensor_box.set_opacity(0.8)
        tensor_box.move_to(position)

        # Shape label
        shape_label = Text(shape_str, font_size=10, color=color)
        shape_label.next_to(tensor_box, DOWN, buff=0.1)

        return VGroup(tensor_box, shape_label)

    # ========================================================================
    # PHASE 4: ERROR VISUALIZATION
    # ========================================================================

    def phase4_error_visualization(self):
        """Show errors and their propagation."""
        phase_title = Text("Phase 4: Error Analysis",
                          font_size=36, color=RED)
        phase_title.to_edge(UP, buff=0.8)
        self.add_fixed_in_frame_mobjects(phase_title)
        self.play(FadeIn(phase_title, run_time=0.5))

        # Show error locations
        for error_call in self.error_locations[:5]:  # Show up to 5 errors
            module = error_call.get('module', '')
            error_msg = error_call.get('error', 'Unknown error')[:50]

            # Highlight error module
            if module in self.module_objects:
                box = self.module_objects[module][0]
                self.play(
                    box.animate.set_color(RED).set_opacity(1),
                    run_time=0.5
                )

                # Show error message (fixed in frame overlay)
                error_text = ImprovedBillboardText.create(
                    text_content=f"Error: {error_msg}",
                    position=box.get_center() + UP * 1.5,
                    font_size=14,
                    color=RED,
                    fixed_in_frame=True  # UI element, don't rotate
                )
                self.add_fixed_in_frame_mobjects(error_text)
                self.play(FadeIn(error_text), run_time=0.5)
                self.wait(1)
                self.play(FadeOut(error_text), run_time=0.3)

        self.wait(1)
        self.play(FadeOut(phase_title), run_time=0.5)

    # ========================================================================
    # PHASE 5: PERFORMANCE METRICS (Enhanced with Timing)
    # ========================================================================

    def phase5_performance_metrics(self):
        """
        Show enhanced execution statistics with timing metrics.

        Features:
        - Call counts per module (bar chart)
        - Time spent per module (if available)
        - Source-to-sink latency (data path timing)
        - Learning cycle timing (error calc + model update)
        """
        phase_title = Text("Phase 5: Performance Metrics",
                          font_size=36, color=PURPLE)
        phase_title.to_edge(UP, buff=0.8)
        self.add_fixed_in_frame_mobjects(phase_title)
        self.play(FadeIn(phase_title, run_time=0.5))

        # Calculate timing metrics
        timing_metrics = self._calculate_timing_metrics()

        # === PART 1: Call Count Bar Chart ===
        self._show_call_count_chart()

        # === PART 2: Timing Metrics Panel ===
        self._show_timing_panel(timing_metrics)

        # === PART 3: Data Path Timing ===
        self._show_data_path_timing(timing_metrics)

        self.wait(1)
        self.play(FadeOut(phase_title), run_time=0.5)

    def _calculate_timing_metrics(self) -> Dict[str, Any]:
        """
        Calculate timing metrics from trace data.

        Returns:
            Dict with timing information
        """
        calls = self.trace_data.get('calls', [])

        metrics = {
            'total_duration_ms': 0,
            'module_times': defaultdict(float),
            'source_to_sink_ms': 0,
            'learning_cycle_ms': 0,
            'avg_call_time_ms': 0,
            'slowest_calls': []
        }

        if not calls:
            return metrics

        # Calculate times from timestamps
        timestamps = []
        for call in calls:
            ts = call.get('timestamp', 0)
            if ts:
                timestamps.append(ts)

            # Accumulate module time (estimate from call frequency)
            module = call.get('module', 'unknown')
            duration = call.get('duration_ms', 0.1)  # Default 0.1ms per call
            metrics['module_times'][module] += duration

        # Total duration
        if len(timestamps) >= 2:
            metrics['total_duration_ms'] = max(timestamps) - min(timestamps)
        else:
            # Estimate from call count
            metrics['total_duration_ms'] = len(calls) * 0.5  # 0.5ms per call avg

        # Average call time
        if calls:
            metrics['avg_call_time_ms'] = metrics['total_duration_ms'] / len(calls)

        # Identify source (input) and sink (output) modules
        source_modules = ['audio_stream', 'screen_capture', 'webcam', 'input']
        sink_modules = ['decoder', 'output', 'response', 'learn', 'update']

        source_time = None
        sink_time = None

        for call in calls:
            module = call.get('module', '').lower()
            ts = call.get('timestamp', 0)

            for src in source_modules:
                if src in module and source_time is None:
                    source_time = ts
                    break

            for snk in sink_modules:
                if snk in module:
                    sink_time = ts

        if source_time and sink_time:
            metrics['source_to_sink_ms'] = sink_time - source_time

        # Learning cycle time (learn_from_reality calls)
        learning_times = []
        for call in calls:
            func = call.get('function', call.get('function_name', '')).lower()
            if 'learn' in func:
                learning_times.append(call.get('duration_ms', 1.0))

        if learning_times:
            metrics['learning_cycle_ms'] = sum(learning_times)

        # Find slowest calls
        call_times = []
        for call in calls:
            func = call.get('function', call.get('function_name', 'func'))
            module = call.get('module', '')
            duration = call.get('duration_ms', 0.1)
            call_times.append((f"{module}.{func}", duration))

        call_times.sort(key=lambda x: x[1], reverse=True)
        metrics['slowest_calls'] = call_times[:5]

        return metrics

    def _show_call_count_chart(self):
        """Show bar chart of call counts per module."""
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
            height = (stats['calls'] / max_calls) * 2.5
            bar = Rectangle(
                width=0.5,
                height=height,
                fill_color=interpolate_color(GREEN, RED, i/5),
                fill_opacity=0.8,
                stroke_opacity=0
            )
            bar.move_to(np.array([-3 + i*1.5, -1.5 + height/2, 0]))
            bars.add(bar)

            # Label
            module_name = module.split('.')[-1][:12]
            label = Text(
                f"{module_name}\n{stats['calls']}",
                font_size=10,
                color=WHITE
            )
            label.next_to(bar, UP, buff=0.1)
            labels.add(label)

        chart_title = Text("Calls per Module", font_size=16, color=WHITE)
        chart_title.move_to(np.array([-0.5, 1.5, 0]))

        chart_group = VGroup(chart_title, bars, labels)
        self.add_fixed_in_frame_mobjects(chart_group)

        self.play(
            FadeIn(chart_title),
            *[GrowFromEdge(bar, DOWN) for bar in bars],
            *[FadeIn(label) for label in labels],
            run_time=1.5,
            rate_func=smooth
        )

        self.wait(1.5)
        self.play(FadeOut(chart_group), run_time=0.5)

    def _show_timing_panel(self, metrics: Dict[str, Any]):
        """Show timing metrics panel."""
        panel_items = VGroup()

        # Title
        title = Text("Timing Metrics", font_size=18, color=PURPLE)
        panel_items.add(title)

        # Total duration
        total_text = Text(
            f"Total Duration: {metrics['total_duration_ms']:.1f} ms",
            font_size=14, color=WHITE
        )
        panel_items.add(total_text)

        # Average call time
        avg_text = Text(
            f"Avg Call Time: {metrics['avg_call_time_ms']:.3f} ms",
            font_size=14, color=WHITE
        )
        panel_items.add(avg_text)

        # Source to sink
        if metrics['source_to_sink_ms'] > 0:
            s2s_text = Text(
                f"Source-to-Sink: {metrics['source_to_sink_ms']:.1f} ms",
                font_size=14, color=YELLOW
            )
            panel_items.add(s2s_text)

        # Learning cycle
        if metrics['learning_cycle_ms'] > 0:
            learn_text = Text(
                f"Learning Cycle: {metrics['learning_cycle_ms']:.1f} ms",
                font_size=14, color=GREEN
            )
            panel_items.add(learn_text)

        panel_items.arrange(DOWN, aligned_edge=LEFT, buff=0.15)
        panel_items.to_corner(UL, buff=0.5)

        # Background
        bg = Rectangle(
            width=panel_items.width + 0.4,
            height=panel_items.height + 0.3,
            fill_color="#1a1a2e",
            fill_opacity=0.9,
            stroke_color=PURPLE,
            stroke_width=1
        )
        bg.move_to(panel_items.get_center())

        panel = VGroup(bg, panel_items)
        self.add_fixed_in_frame_mobjects(panel)
        self.play(FadeIn(panel), run_time=0.5)
        self.wait(2)
        self.play(FadeOut(panel), run_time=0.3)

    def _show_data_path_timing(self, metrics: Dict[str, Any]):
        """Show data path timing visualization."""
        # Show slowest calls
        if not metrics['slowest_calls']:
            return

        panel_items = VGroup()

        title = Text("Slowest Operations", font_size=18, color=RED)
        panel_items.add(title)

        for i, (call_name, duration) in enumerate(metrics['slowest_calls'][:5]):
            # Truncate call name
            short_name = call_name.split('.')[-1][:20] if '.' in call_name else call_name[:20]
            call_text = Text(
                f"{i+1}. {short_name}: {duration:.2f} ms",
                font_size=12, color=WHITE
            )
            panel_items.add(call_text)

        panel_items.arrange(DOWN, aligned_edge=LEFT, buff=0.12)
        panel_items.to_corner(UR, buff=0.5)

        # Background
        bg = Rectangle(
            width=panel_items.width + 0.4,
            height=panel_items.height + 0.3,
            fill_color="#1a1a2e",
            fill_opacity=0.9,
            stroke_color=RED,
            stroke_width=1
        )
        bg.move_to(panel_items.get_center())

        panel = VGroup(bg, panel_items)
        self.add_fixed_in_frame_mobjects(panel)
        self.play(FadeIn(panel), run_time=0.5)

        # Summary at bottom
        total_calls = sum(s['calls'] for s in self.module_stats.values())
        summary = Text(
            f"Total: {total_calls} calls | {metrics['total_duration_ms']:.1f}ms | "
            f"Avg: {metrics['avg_call_time_ms']:.3f}ms/call",
            font_size=16, color=GOLD
        )
        summary.to_edge(DOWN, buff=0.5)
        self.add_fixed_in_frame_mobjects(summary)
        self.play(FadeIn(summary), run_time=0.5)

        self.wait(2)
        self.play(FadeOut(panel), FadeOut(summary), run_time=0.5)

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _extract_layered_architecture(self) -> Tuple[Dict, List[List[str]]]:
        """Extract modules and organize into layers."""
        calls = self.trace_data.get('calls', [])
        modules = defaultdict(lambda: {'functions': set(), 'calls': 0})

        for call in calls:
            module = call.get('module', '').lower()
            if module:
                func = call.get('function', '')
                modules[module]['functions'].add(func)
                modules[module]['calls'] += 1

        # Categorize into layers
        layers = [[], [], [], [], []]

        for module_name in modules.keys():
            lower_name = module_name.lower()

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
                layers[2].append(module_name)

        # Remove empty layers
        layers = [layer for layer in layers if layer]

        return dict(modules), layers

    def _is_in_viewport(self, position: np.ndarray, margin: float = 0.5) -> bool:
        """
        DEPRECATED: Check if a 3D position is within the camera's viewport.

        For ThreeDScene with phi=70deg camera, frame bounds are approximately:
        - X: -7 to +7 (14 units wide)
        - Y: -4 to +4 (8 units tall)
        - Z: Ignored for viewport check (depth doesn't affect screen bounds)
        """
        # Frame bounds (Manim default frame is 14.22 x 8 units)
        x_min, x_max = -6.5 + margin, 6.5 - margin
        y_min, y_max = -3.5 + margin, 3.5 - margin

        in_bounds = (x_min <= position[0] <= x_max and
                     y_min <= position[1] <= y_max)

        if not in_bounds:
            logger.warning(f"OUT OF BOUNDS: position {position} outside viewport [{x_min},{x_max}] x [{y_min},{y_max}]")

        return in_bounds

    def _layout_call_tree(self, calls: List[Dict]) -> Dict[str, np.ndarray]:
        """
        DEPRECATED: Layout calls in tree structure with viewport bounds checking and auto-relayout.

        If positions exceed viewport, automatically scales and shifts to fit.
        """
        if not calls:
            return {}

        # First pass: calculate raw positions
        raw_positions = {}
        max_depth = 0
        y_pos = 2

        for i, call in enumerate(calls):
            call_id = call.get('call_id', f'call_{i}')
            depth = call.get('depth', 0)
            max_depth = max(max_depth, depth)

            x_pos = depth * 0.8  # Base horizontal spread per depth
            raw_positions[call_id] = np.array([x_pos, y_pos, 0])
            y_pos -= 0.8

        # Calculate bounding box
        all_positions = list(raw_positions.values())
        x_coords = [p[0] for p in all_positions]
        y_coords = [p[1] for p in all_positions]

        raw_x_min, raw_x_max = min(x_coords), max(x_coords)
        raw_y_min, raw_y_max = min(y_coords), max(y_coords)

        raw_width = raw_x_max - raw_x_min if raw_x_max > raw_x_min else 1.0
        raw_height = raw_y_max - raw_y_min if raw_y_max > raw_y_min else 1.0

        # Target viewport bounds (with margin)
        margin = 1.0
        target_x_min, target_x_max = -5.5 + margin, 5.5 - margin  # Leave space for legend
        target_y_min, target_y_max = -3.0 + margin, 2.5 - margin  # Leave space for title

        target_width = target_x_max - target_x_min
        target_height = target_y_max - target_y_min

        # Calculate scale factor (uniform scaling to preserve aspect)
        scale_x = target_width / raw_width if raw_width > 0 else 1.0
        scale_y = target_height / raw_height if raw_height > 0 else 1.0
        scale = min(scale_x, scale_y, 1.0)  # Don't scale up, only down

        # Check if relayout needed
        needs_relayout = (raw_x_max > target_x_max or raw_x_min < target_x_min or
                         raw_y_max > target_y_max or raw_y_min < target_y_min)

        if needs_relayout:
            logger.info(f"AUTO-RELAYOUT: {len(calls)} calls exceed viewport, "
                       f"raw bounds=[{raw_x_min:.1f},{raw_x_max:.1f}]x[{raw_y_min:.1f},{raw_y_max:.1f}], "
                       f"scale={scale:.2f}")

        # Apply scaling and centering
        positions = {}
        raw_center_x = (raw_x_min + raw_x_max) / 2
        raw_center_y = (raw_y_min + raw_y_max) / 2
        target_center_x = (target_x_min + target_x_max) / 2
        target_center_y = (target_y_min + target_y_max) / 2

        out_of_bounds_count = 0
        for call_id, raw_pos in raw_positions.items():
            # Scale around raw center
            scaled_x = (raw_pos[0] - raw_center_x) * scale + target_center_x
            scaled_y = (raw_pos[1] - raw_center_y) * scale + target_center_y

            position = np.array([scaled_x, scaled_y, 0])
            positions[call_id] = position

            # Log if still out of bounds after relayout
            if not self._is_in_viewport(position):
                out_of_bounds_count += 1

        if out_of_bounds_count > 0:
            logger.warning(f"RELAYOUT INCOMPLETE: {out_of_bounds_count}/{len(calls)} "
                          f"calls still out of viewport after auto-relayout")
        else:
            logger.info(f"Layout complete: {len(calls)} calls fit within viewport")

        return positions


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        logger.error("Usage: python ultimate_architecture_viz.py <trace_json_file>")
        sys.exit(1)

    trace_file = sys.argv[1]

    from manim import config
    config.quality = 'high_quality'
    config.output_file = 'ultimate_architecture'
    config.frame_rate = 30

    scene = UltimateArchitectureScene(trace_file)
    scene.render()

    logger.info(f"Ultimate architecture visualization complete!")
