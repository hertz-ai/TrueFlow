"""
DEPRECATED: This file has been superseded by ultimate_architecture_viz.py

The system architecture visualization functionality has been integrated into
ultimate_architecture_viz.py (Phase 1: Architecture Overview) which is the single
active engine used by ManimAutoRenderer.kt.

DO NOT USE - Kept for reference only.
================================================================================
"""

from logging_config import setup_logger
logger = setup_logger(__name__)

"""
System Architecture 3D Visualizer - SAM GRANTSON STYLE

The ORIGINAL streamlined 3D perspective that works:
- Modules stacked PROPERLY in depth (front to back)
- Dependencies shown as clean flowing arrows
- Billboard text that's ACTUALLY readable
- No overlapping, no coordinate chaos

This is the architecture view you remember - clean, professional, 3blue1brown quality.
"""

import json
import numpy as np
from manim import *
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
from visualization_framework import (
    CoordinateTracker,
    ArchitectureLayoutEngine,
    BillboardTextManager,
    DataFlowDetector
)


class ImprovedBillboardText:
    """
    Billboard text that ACTUALLY works and is readable.

    Key improvements:
    - Background panel for contrast
    - Auto-sizing based on camera distance
    - Proper depth fadeout
    - Always screen-aligned (not 3D rotation artifacts)
    """

    @staticmethod
    def create(text_content: str,
              position: np.ndarray,
              font_size: int = 16,
              color: str = WHITE,
              background_color: str = "#2a2a2a",
              depth: float = 0.0) -> VGroup:
        """
        Create billboard text with background.

        Returns VGroup containing both text and background.
        """
        # Adjust font size based on depth
        depth_factor = 1.0 + abs(depth) / 8.0
        adjusted_font_size = int(font_size * depth_factor)

        # Create text
        text = Text(text_content, font_size=adjusted_font_size, color=color)
        text.move_to(position)

        # Create background panel
        padding = 0.2
        bg_width = text.width + padding
        bg_height = text.height + padding

        background = Rectangle(
            width=bg_width,
            height=bg_height,
            fill_color=background_color,
            fill_opacity=0.8,
            stroke_opacity=0
        )
        background.move_to(position)

        # Group together
        group = VGroup(background, text)

        # Fade based on depth (further = slightly more transparent)
        opacity = 1.0 - (abs(depth) / 20.0)
        group.set_opacity(max(opacity, 0.6))

        return group


class SystemArchitecture3DScene(ThreeDScene):
    """
    The GOOD architecture visualizer - like the original working version.

    Clean 3D perspective showing:
    1. System modules stacked by layer (input->processing->output)
    2. Dependencies as flowing arrows
    3. Proper depth perspective
    4. Readable labels with backgrounds

    Duration: ~20 seconds
    """

    def __init__(self, trace_file: str, **kwargs):
        super().__init__(**kwargs)
        self.trace_file = trace_file
        self.trace_data = None

        # Framework components
        self.tracker = CoordinateTracker()
        self.layout_engine = ArchitectureLayoutEngine(self.tracker)
        self.flow_detector = None

        # Visual storage
        self.module_objects: Dict[str, VGroup] = {}  # module -> (box, label)
        self.layer_groups: List[VGroup] = []
        self.dependency_arrows: VGroup = VGroup()

    def construct(self):
        """Main visualization sequence"""
        # Load data
        self.load_data()

        # Setup
        self.camera.background_color = "#1a1a1a"
        self.set_camera_orientation(phi=65 * DEGREES, theta=-50 * DEGREES, distance=15)

        # Title
        title = Text("System Architecture - 3D Perspective", font_size=44, color=GOLD, weight=BOLD)
        title.to_edge(UP, buff=0.5)
        self.add_fixed_in_frame_mobjects(title)
        self.play(Write(title, run_time=1.5))
        self.wait(0.5)

        # Phase 1: Build architecture (0-10s)
        self.build_layered_architecture()

        # Phase 2: Show dependencies (10-15s)
        self.show_dependencies()

        # Phase 3: Highlight key modules (15-18s)
        self.highlight_key_modules()

        # Finale
        self.play(FadeOut(title), run_time=0.5)
        self.wait(1)

    def load_data(self):
        """Load and analyze trace data"""
        with open(self.trace_file, 'r') as f:
            self.trace_data = json.load(f)

        self.flow_detector = DataFlowDetector(self.trace_data)
        logger.info(f"Loaded trace with {len(self.trace_data.get('calls', []))} calls")

    def build_layered_architecture(self):
        """
        Build the main 3D layered architecture.

        Stacking strategy (SAM GRANTSON approved):
        - Z = 0: Input layer (front, closest to camera)
        - Z = -3: Encoder layer
        - Z = -6: Processing layer
        - Z = -9: Memory layer
        - Z = -12: Output layer (back)

        This creates PROPER depth perspective.
        """
        # Extract architecture
        modules, layers = self._extract_layered_architecture()

        # Define layer info
        layer_info = [
            {"name": "Input Layer", "color": GREEN, "z_depth": 0},
            {"name": "Encoding Layer", "color": BLUE, "z_depth": -3},
            {"name": "Processing Layer", "color": PURPLE, "z_depth": -6},
            {"name": "Memory Layer", "color": ORANGE, "z_depth": -9},
            {"name": "Output Layer", "color": RED, "z_depth": -12}
        ]

        # Build each layer
        for layer_idx, layer_modules in enumerate(layers):
            if layer_idx >= len(layer_info):
                break

            info = layer_info[layer_idx]
            self.build_layer(
                layer_modules=layer_modules,
                layer_name=info["name"],
                color=info["color"],
                z_depth=info["z_depth"],
                layer_idx=layer_idx
            )

        # Orbit camera to show depth
        self.begin_ambient_camera_rotation(rate=0.08)
        self.wait(6)
        self.stop_ambient_camera_rotation()

    def build_layer(self,
                   layer_modules: List[str],
                   layer_name: str,
                   color: str,
                   z_depth: float,
                   layer_idx: int):
        """
        Build a single layer with proper 3D positioning.

        Modules arranged horizontally with even spacing.
        """
        layer_group = VGroup()

        # Layer title (billboard)
        layer_title = ImprovedBillboardText.create(
            text_content=layer_name,
            position=np.array([-7, 0, z_depth]),
            font_size=20,
            color=color,
            depth=z_depth
        )
        self.add_fixed_in_frame_mobjects(layer_title)
        self.play(FadeIn(layer_title), run_time=0.4)

        # Calculate horizontal spacing
        num_modules = min(len(layer_modules), 6)  # Max 6 modules per layer for clarity
        spacing = 2.2
        start_x = -(num_modules - 1) * spacing / 2

        for i, module_name in enumerate(layer_modules[:num_modules]):
            x_pos = start_x + i * spacing
            position = np.array([x_pos, 0, z_depth])

            # Register with tracker
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

            # Module label (billboard)
            short_name = module_name.split('.')[-1][:18]
            label = ImprovedBillboardText.create(
                text_content=short_name,
                position=position + DOWN * 0.8,
                font_size=13,
                color=WHITE,
                depth=z_depth
            )

            # Function count
            module_data = modules.get(module_name, {})
            num_funcs = len(module_data.get('functions', []))
            func_label = ImprovedBillboardText.create(
                text_content=f"{num_funcs} funcs",
                position=position + UP * 0.7,
                font_size=10,
                color=GRAY,
                depth=z_depth
            )

            # Store references
            module_group = VGroup(box, label, func_label)
            self.module_objects[module_name] = module_group
            layer_group.add(module_group)

            # Animate appearance
            self.add_fixed_in_frame_mobjects(label, func_label)
            self.play(
                GrowFromCenter(box),
                FadeIn(label),
                FadeIn(func_label),
                run_time=0.35
            )

        self.layer_groups.append(layer_group)

    def show_dependencies(self):
        """
        Show inter-module dependencies as flowing arrows.

        Uses detected data flows from trace.
        """
        subtitle = Text("Data Flow Dependencies", font_size=32, color=BLUE)
        subtitle.to_edge(UP, buff=1.2)
        self.add_fixed_in_frame_mobjects(subtitle)
        self.play(FadeIn(subtitle), run_time=0.5)

        # Detect flows
        flows = self.flow_detector.detect_flows()

        # Visualize top 20 flows
        arrows = []
        for source, target, count in flows[:20]:
            source_pos = self.tracker.get_position(source)
            target_pos = self.tracker.get_position(target)

            if source_pos is None or target_pos is None:
                continue

            # Arrow thickness based on frequency
            thickness = min(count / 8, 0.08)

            # Color based on frequency (hot = frequent)
            color = interpolate_color(YELLOW, RED, min(count / 50, 1))

            # Create curved arrow with proper 3D path
            arrow = self._create_3d_flow_arrow(source_pos, target_pos, color, thickness)
            arrows.append(arrow)
            self.dependency_arrows.add(arrow)

        # Animate arrows appearing
        self.play(
            *[Create(arrow) for arrow in arrows],
            run_time=3,
            lag_ratio=0.05
        )

        self.wait(2)
        self.play(FadeOut(subtitle), run_time=0.5)

    def _create_3d_flow_arrow(self,
                             start: np.ndarray,
                             end: np.ndarray,
                             color: str,
                             thickness: float) -> VMobject:
        """
        Create a smooth 3D curved arrow between two points.

        Uses Bezier curve for smooth flow appearance.
        """
        # Control points for smooth curve
        direction = end - start
        midpoint = (start + end) / 2
        perpendicular = np.array([-direction[1], direction[0], 0])
        perpendicular = perpendicular / (np.linalg.norm(perpendicular) + 0.001)

        ctrl1 = start + direction * 0.3 + perpendicular * 0.5
        ctrl2 = end - direction * 0.3 + perpendicular * 0.5

        # Create Bezier path
        path = CubicBezier(start, ctrl1, ctrl2, end)
        path.set_color(color)
        path.set_stroke(width=thickness * 50)
        path.set_opacity(0.7)

        return path

    def highlight_key_modules(self):
        """Highlight most critical modules"""
        subtitle = Text("Critical Modules", font_size=32, color=YELLOW)
        subtitle.to_edge(UP, buff=1.2)
        self.add_fixed_in_frame_mobjects(subtitle)
        self.play(FadeIn(subtitle), run_time=0.5)

        # Get top 5 modules by activity
        flows = self.flow_detector.flows
        module_activity = defaultdict(int)

        for source, target, count in flows:
            module_activity[source] += count
            module_activity[target] += count

        top_modules = sorted(module_activity.items(), key=lambda x: x[1], reverse=True)[:5]

        for module_name, activity in top_modules:
            if module_name in self.module_objects:
                module_group = self.module_objects[module_name]
                box = module_group[0]  # First element is the box

                # Pulse animation
                self.play(
                    box.animate.set_color(YELLOW).scale(1.15).set_opacity(0.95),
                    run_time=0.4
                )
                self.play(
                    box.animate.scale(1/1.15).set_opacity(0.75),
                    run_time=0.4
                )

        self.wait(1)
        self.play(FadeOut(subtitle), run_time=0.5)

    def _extract_layered_architecture(self) -> Tuple[Dict, List[List[str]]]:
        """
        Extract modules and organize into layers.

        Simple heuristic:
        - Layer 0: Modules with "input", "sensor", "stream" in name
        - Layer 1: Modules with "encoder", "embed" in name
        - Layer 2: Modules with "dynamic", "latent", "process" in name
        - Layer 3: Modules with "memory", "compress" in name
        - Layer 4: Modules with "decoder", "output", "action" in name
        """
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
            elif any(kw in lower_name for kw in ['encoder', 'embed', 'vision']):
                layers[1].append(module_name)
            elif any(kw in lower_name for kw in ['dynamic', 'latent', 'sde', 'ssm']):
                layers[2].append(module_name)
            elif any(kw in lower_name for kw in ['memory', 'compress', 'temporal']):
                layers[3].append(module_name)
            elif any(kw in lower_name for kw in ['decoder', 'output', 'action', 'truth']):
                layers[4].append(module_name)
            else:
                # Default to processing layer
                layers[2].append(module_name)

        # Remove empty layers and limit modules per layer
        layers = [layer[:6] for layer in layers if layer]

        logger.info(f"Organized {len(modules)} modules into {len(layers)} layers")

        return dict(modules), layers


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        logger.error("Usage: python system_architecture_3d.py <trace_json_file>")
        sys.exit(1)

    trace_file = sys.argv[1]

    from manim import config
    config.quality = 'high_quality'
    config.output_file = 'system_architecture_3d'

    scene = SystemArchitecture3DScene(trace_file)
    scene.render()

    logger.info("System architecture 3D visualization complete")
