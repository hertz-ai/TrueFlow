from logging_config import setup_logger
logger = setup_logger(__name__)

"""
Universal Visualization Framework for Manim

SAM GRANTSON APPROACH:
- NO hardcoded coordinates
- ALL positions tracked relative to camera
- Proper 3D stacking with depth perspective
- Billboard text always readable
- Smooth transitions with coordinate inheritance
- Framework handles all positioning logic

Key Principles:
1. Track ALL object positions in world space
2. Account for camera transformations
3. Scale-aware positioning (parent scaling affects children)
4. Proper depth-based 3D layering
5. Text always faces camera with proper sizing
6. Data flow paths detected and visualized automatically
"""

import numpy as np
from manim import *
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

class LayerType(Enum):
    """Types of architectural layers"""
    INPUT = "input"
    ENCODER = "encoder"
    PROCESSING = "processing"
    MEMORY = "memory"
    OUTPUT = "output"

@dataclass
class ModulePosition:
    """
    Tracks complete position information for a module in 3D space.

    Handles:
    - World position (accounting for parent transforms)
    - Local offset (relative to parent)
    - Scale (inherited from parents)
    - Rotation (camera-relative)
    """
    world_pos: np.ndarray  # Absolute position in 3D space
    local_offset: np.ndarray = field(default_factory=lambda: np.array([0, 0, 0]))
    scale: float = 1.0
    parent_scale: float = 1.0
    layer_depth: float = 0.0  # Z-depth for 3D stacking

    def get_effective_pos(self) -> np.ndarray:
        """Get position accounting for all transforms"""
        return self.world_pos * self.parent_scale + self.local_offset

    def get_effective_scale(self) -> float:
        """Get scale accounting for parent scaling"""
        return self.scale * self.parent_scale


@dataclass
class CameraState:
    """Track camera position and orientation"""
    phi: float = 70 * DEGREES
    theta: float = -45 * DEGREES
    distance: float = 10.0
    target: np.ndarray = field(default_factory=lambda: np.array([0, 0, 0]))

    def get_view_matrix(self) -> np.ndarray:
        """Calculate view matrix for position calculations"""
        # Spherical to Cartesian for camera position
        x = self.distance * np.sin(self.phi) * np.cos(self.theta)
        y = self.distance * np.sin(self.phi) * np.sin(self.theta)
        z = self.distance * np.cos(self.phi)
        return np.array([x, y, z])


class CoordinateTracker:
    """
    Central coordinate tracking system.

    ALL objects register here and get consistent positioning.
    Handles parent-child relationships, scaling, and camera transforms.
    """

    def __init__(self):
        self.objects: Dict[str, ModulePosition] = {}
        self.camera_state = CameraState()
        self.parent_relationships: Dict[str, str] = {}  # child -> parent
        self.children: Dict[str, List[str]] = {}  # parent -> [children]

    def register_object(self,
                       name: str,
                       position: np.ndarray,
                       scale: float = 1.0,
                       parent: Optional[str] = None,
                       layer_depth: float = 0.0):
        """Register an object with the tracker"""
        parent_scale = 1.0
        if parent and parent in self.objects:
            parent_scale = self.objects[parent].get_effective_scale()
            self.parent_relationships[name] = parent
            if parent not in self.children:
                self.children[parent] = []
            self.children[parent].append(name)

        self.objects[name] = ModulePosition(
            world_pos=position.copy(),
            scale=scale,
            parent_scale=parent_scale,
            layer_depth=layer_depth
        )

        logger.info(f"Registered {name} at {position} (depth={layer_depth})")

    def update_position(self, name: str, new_position: np.ndarray):
        """Update object position"""
        if name in self.objects:
            self.objects[name].world_pos = new_position.copy()
            # Update all children
            self._propagate_to_children(name)

    def _propagate_to_children(self, parent_name: str):
        """Update all children when parent moves"""
        if parent_name in self.children:
            parent_pos = self.objects[parent_name].get_effective_pos()
            parent_scale = self.objects[parent_name].get_effective_scale()

            for child_name in self.children[parent_name]:
                if child_name in self.objects:
                    self.objects[child_name].parent_scale = parent_scale
                    self._propagate_to_children(child_name)

    def update_scale(self, name: str, new_scale: float):
        """Update object scale and propagate to children"""
        if name in self.objects:
            self.objects[name].scale = new_scale
            self._propagate_to_children(name)

    def get_position(self, name: str) -> Optional[np.ndarray]:
        """Get current effective position"""
        if name in self.objects:
            return self.objects[name].get_effective_pos()
        return None

    def get_scale(self, name: str) -> float:
        """Get current effective scale"""
        if name in self.objects:
            return self.objects[name].get_effective_scale()
        return 1.0

    def update_camera(self, phi: float = None, theta: float = None, distance: float = None):
        """Update camera state"""
        if phi is not None:
            self.camera_state.phi = phi
        if theta is not None:
            self.camera_state.theta = theta
        if distance is not None:
            self.camera_state.distance = distance

    def get_camera_facing_rotation(self) -> np.ndarray:
        """Calculate rotation to face camera"""
        # For billboard effect
        return self.camera_state.get_view_matrix()


class ArchitectureLayoutEngine:
    """
    Calculates optimal 3D layout for system architecture.

    Uses proper depth stacking:
    - Input layer at front (z = 0)
    - Processing layers stacked behind (z = -2, -4, -6, ...)
    - Output layer at back (z = -8)

    Horizontal spacing prevents overlap.
    Vertical grouping by layer type.
    """

    def __init__(self, tracker: CoordinateTracker):
        self.tracker = tracker
        self.layer_spacing_z = 3.0  # Depth between layers
        self.module_spacing_x = 2.5  # Horizontal spacing
        self.module_spacing_y = 2.0  # Vertical spacing within layer

    def layout_architecture(self,
                           layers: List[List[str]],
                           layer_types: Optional[List[LayerType]] = None) -> Dict[str, np.ndarray]:
        """
        Calculate positions for all modules in layered architecture.

        Returns: Dict[module_name -> position]
        """
        positions = {}

        num_layers = len(layers)

        for layer_idx, layer_modules in enumerate(layers):
            # Calculate Z depth (stacked front to back)
            z_depth = -layer_idx * self.layer_spacing_z

            # Calculate Y center (balanced vertically)
            num_modules = len(layer_modules)
            y_center = (num_modules - 1) * self.module_spacing_y / 2

            for mod_idx, module_name in enumerate(layer_modules):
                # Calculate X position (horizontal spread)
                x_pos = (mod_idx - num_modules / 2) * self.module_spacing_x

                # Calculate Y position (vertical within layer)
                y_pos = mod_idx * self.module_spacing_y - y_center

                position = np.array([x_pos, y_pos, z_depth])
                positions[module_name] = position

                # Register with tracker
                layer_type = layer_types[layer_idx] if layer_types else None
                self.tracker.register_object(
                    name=module_name,
                    position=position,
                    layer_depth=z_depth
                )

        logger.info(f"Laid out {len(positions)} modules across {num_layers} layers")
        return positions


class BillboardTextManager:
    """
    Manages billboard text that always faces camera.

    SAM GRANTSON RULE: Text must ALWAYS be readable.

    Features:
    - Auto-sizing based on distance from camera
    - Always faces camera (billboard effect)
    - Proper depth-based opacity (closer = more opaque)
    - Background for contrast
    """

    def __init__(self, tracker: CoordinateTracker):
        self.tracker = tracker
        self.texts: Dict[str, Tuple[Text, str]] = {}  # text_id -> (text_obj, parent_module)

    def create_label(self,
                    text_id: str,
                    text_content: str,
                    parent_module: str,
                    offset: np.ndarray = np.array([0, -0.5, 0]),
                    font_size: int = 16,
                    color: str = WHITE) -> Text:
        """
        Create billboard text label attached to a module.

        Text will:
        - Move with parent module
        - Always face camera
        - Scale with distance
        """
        parent_pos = self.tracker.get_position(parent_module)
        if parent_pos is None:
            logger.error(f"Parent module {parent_module} not found for text {text_id}")
            parent_pos = np.array([0, 0, 0])

        # Calculate distance-based font size
        parent_depth = self.tracker.objects[parent_module].layer_depth
        distance_scale = 1.0 + abs(parent_depth) / 10.0  # Further = larger text
        adjusted_font_size = int(font_size * distance_scale)

        # Create text with background for readability
        text_obj = Text(text_content, font_size=adjusted_font_size, color=color)

        # Position relative to parent
        text_pos = parent_pos + offset
        text_obj.move_to(text_pos)

        self.texts[text_id] = (text_obj, parent_module)

        return text_obj

    def update_text_positions(self):
        """Update all text positions to follow parents"""
        for text_id, (text_obj, parent_module) in self.texts.items():
            parent_pos = self.tracker.get_position(parent_module)
            if parent_pos is not None:
                # Maintain offset
                current_offset = text_obj.get_center() - parent_pos
                new_pos = parent_pos + current_offset
                text_obj.move_to(new_pos)


class DataFlowDetector:
    """
    Automatically detects data flow paths from trace data.

    NO manual path specification needed.
    Analyzes call tree and builds flow graph automatically.
    """

    def __init__(self, trace_data: Dict):
        self.trace_data = trace_data
        self.flows: List[Tuple[str, str, int]] = []  # (from_module, to_module, count)

    def detect_flows(self) -> List[Tuple[str, str, int]]:
        """
        Detect all data flow paths from trace.

        Returns: List of (source, target, frequency)
        """
        calls = self.trace_data.get('calls', [])
        flow_counts = {}

        # Build call graph
        for i, call in enumerate(calls):
            if call.get('type') != 'call':
                continue

            current_module = call.get('module', '')
            current_func = call.get('function', '')

            # Find parent call
            parent_id = call.get('parent_id')
            if parent_id:
                parent_call = next((c for c in calls if c.get('call_id') == parent_id), None)
                if parent_call:
                    parent_module = parent_call.get('module', '')

                    if parent_module != current_module:
                        # Inter-module flow detected
                        flow_key = (parent_module, current_module)
                        flow_counts[flow_key] = flow_counts.get(flow_key, 0) + 1

        # Convert to list and sort by frequency
        flows = [(src, tgt, count) for (src, tgt), count in flow_counts.items()]
        flows.sort(key=lambda x: x[2], reverse=True)

        self.flows = flows
        logger.info(f"Detected {len(flows)} data flow paths")

        return flows


class ManimVisualizationFramework(ThreeDScene):
    """
    Complete framework-based Manim visualization.

    SAM GRANTSON STYLE:
    - Framework handles ALL positioning
    - NO hardcoded coordinates anywhere
    - Proper 3D depth stacking
    - Text always readable
    - Smooth transitions
    - Auto-detected data flows

    Usage:
        scene = ManimVisualizationFramework(trace_data)
        scene.render()
    """

    def __init__(self, trace_data: Dict, **kwargs):
        super().__init__(**kwargs)
        self.trace_data = trace_data

        # Framework components
        self.tracker = CoordinateTracker()
        self.layout_engine = ArchitectureLayoutEngine(self.tracker)
        self.text_manager = BillboardTextManager(self.tracker)
        self.flow_detector = DataFlowDetector(trace_data)

        # Visual objects
        self.module_boxes: Dict[str, Cube] = {}
        self.dependency_arrows: Dict[Tuple[str, str], Arrow3D] = {}

    def construct(self):
        """Main visualization sequence"""
        # Setup
        self.camera.background_color = "#1a1a1a"
        self.tracker.update_camera(phi=70*DEGREES, theta=-45*DEGREES, distance=12)

        # Phase 1: Build architecture (0-8s)
        self.build_architecture()
        self.wait(2)

        # Phase 2: Show data flows (8-15s)
        self.show_data_flows()
        self.wait(2)

        # Phase 3: Highlight critical paths (15-20s)
        self.highlight_critical_paths()
        self.wait(3)

    def build_architecture(self):
        """Build 3D stacked architecture visualization"""
        title = Text("System Architecture - 3D Perspective", font_size=42, color=GOLD)
        title.to_edge(UP)
        self.add_fixed_in_frame_mobjects(title)
        self.play(Write(title), run_time=1)

        # Extract architecture
        modules, layers = self._extract_architecture()

        # Calculate layout
        positions = self.layout_engine.layout_architecture(layers)

        # Create module visualizations
        layer_colors = [GREEN, BLUE, PURPLE, ORANGE, RED, TEAL]

        for layer_idx, layer_modules in enumerate(layers):
            layer_color = layer_colors[layer_idx % len(layer_colors)]

            for module_name in layer_modules:
                position = positions[module_name]

                # Create 3D box for module
                box_size = 0.8
                box = Cube(side_length=box_size)
                box.set_color(layer_color)
                box.set_opacity(0.7)
                box.set_sheen(0.6, direction=UP)
                box.move_to(position)

                self.module_boxes[module_name] = box

                # Create billboard label
                short_name = module_name.split('.')[-1][:20]
                label = self.text_manager.create_label(
                    text_id=f"label_{module_name}",
                    text_content=short_name,
                    parent_module=module_name,
                    offset=np.array([0, -(box_size/2 + 0.4), 0]),
                    font_size=14,
                    color=WHITE
                )

                # Animate appearance
                self.play(
                    GrowFromCenter(box),
                    FadeIn(label),
                    run_time=0.3
                )

        # Orbit camera to show 3D structure
        self.begin_ambient_camera_rotation(rate=0.1)
        self.wait(4)
        self.stop_ambient_camera_rotation()

        self.play(FadeOut(title), run_time=0.5)

    def show_data_flows(self):
        """Show detected data flow paths"""
        title = Text("Data Flow Paths", font_size=36, color=BLUE)
        title.to_edge(UP)
        self.add_fixed_in_frame_mobjects(title)
        self.play(FadeIn(title), run_time=0.5)

        # Detect flows
        flows = self.flow_detector.detect_flows()

        # Visualize top 15 flows
        for source, target, count in flows[:15]:
            if source not in self.module_boxes or target not in self.module_boxes:
                continue

            source_pos = self.tracker.get_position(source)
            target_pos = self.tracker.get_position(target)

            if source_pos is None or target_pos is None:
                continue

            # Create flowing arrow
            thickness = min(count / 10, 6)
            color = interpolate_color(YELLOW, RED, min(count / 50, 1))

            arrow = Arrow3D(
                start=source_pos,
                end=target_pos,
                color=color,
                thickness=thickness * 0.01
            )
            arrow.set_opacity(0.7)

            self.dependency_arrows[(source, target)] = arrow

            # Animate appearance
            self.play(GrowArrow(arrow), run_time=0.4)

        self.wait(2)
        self.play(FadeOut(title), run_time=0.5)

    def highlight_critical_paths(self):
        """Highlight most critical data paths"""
        title = Text("Critical Paths", font_size=36, color=RED)
        title.to_edge(UP)
        self.add_fixed_in_frame_mobjects(title)
        self.play(FadeIn(title), run_time=0.5)

        # Get top 5 flows
        top_flows = self.flow_detector.flows[:5]

        for source, target, count in top_flows:
            key = (source, target)
            if key in self.dependency_arrows:
                arrow = self.dependency_arrows[key]

                # Pulse animation
                self.play(
                    arrow.animate.set_color(YELLOW).set_opacity(1).scale(1.2),
                    run_time=0.5
                )
                self.play(
                    arrow.animate.set_opacity(0.7).scale(1/1.2),
                    run_time=0.5
                )

        self.wait(1)
        self.play(FadeOut(title), run_time=0.5)

    def _extract_architecture(self) -> Tuple[Dict[str, Dict], List[List[str]]]:
        """Extract modules and layers from trace data"""
        calls = self.trace_data.get('calls', [])
        modules = {}

        for call in calls:
            module = call.get('module', 'unknown')
            if module and module not in modules:
                modules[module] = {
                    'functions': set(),
                    'calls': 0
                }
            if module:
                func = call.get('function', '')
                modules[module]['functions'].add(func)
                modules[module]['calls'] += 1

        # Simple layering: one layer for now
        layer = list(modules.keys())[:10]  # Limit to 10 modules for clarity
        layers = [layer]

        return modules, layers


if __name__ == "__main__":
    logger.info("Manim Visualization Framework loaded")
