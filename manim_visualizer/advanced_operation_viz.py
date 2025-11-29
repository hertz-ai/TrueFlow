"""
Advanced Operation-Specific 3D Visualizer

Creates unique awesome animations for each type of operation:
- Method calls: 3D boxes with glowing labels
- Neural layer calls: Grid of pulsing neurons with dimension labels
- Parameter passing: Flowing arrows with data type visualization
- Data types: Different 3D shapes (tensors=cubes, scalars=spheres, strings=ribbons)
- Dimensions: Size-coded shapes showing tensor dimensions
- Array operations: Transform animations (reshape, transpose, slice)
- Multi-camera: Separate camera tracking for parallel execution branches
"""

import json
import numpy as np
from manim import *
from collections import defaultdict
from typing import Dict, List, Tuple, Any, Optional
import re

# Import logging configuration
from logging_config import get_operation_viz_logger

# Initialize logger
logger = get_operation_viz_logger()

# Import animation standards and extended visualizers
try:
    from animation_standards import (
        AnimationTiming, AnimationColors, DataTypeShapes, AnimationHelpers
    )
    from operation_visualizer_extended import ExtendedOperationVisualizer
    STANDARDS_AVAILABLE = True
except ImportError:
    STANDARDS_AVAILABLE = False
    logger.warning("Animation standards not available. Using defaults.")

# Import LLM operation mapper for intelligent, language-agnostic detection
try:
    from llm_operation_mapper import LLMOperationMapper
    LLM_MAPPER_AVAILABLE = True
except ImportError:
    LLM_MAPPER_AVAILABLE = False
    logger.warning("LLM operation mapper not available. Using pattern matching only.")

# Import smooth microanimations
try:
    from smooth_microanimations import (
        DataFlowParticles, DimensionMorphAnimation,
        ease_in_out_cubic, ease_out_bounce
    )
    MICROANIMATIONS_AVAILABLE = True
except ImportError:
    MICROANIMATIONS_AVAILABLE = False
    # Fallback easing functions
    def ease_in_out_cubic(t):
        return 4 * t**3 if t < 0.5 else 1 - (-2 * t + 2)**3 / 2
    def ease_out_bounce(t):
        return smooth(t)  # Fallback to smooth


class OperationDetector:
    """
    Detects specific operation types from trace data.

    Uses multi-layer detection strategy:
    1. Hardcoded patterns (fast, deterministic)
    2. LLM-based semantic classification (slow, intelligent, language-agnostic)
    """

    # Class-level LLM mapper (lazy initialization)
    _llm_mapper = None

    @classmethod
    def get_llm_mapper(cls):
        """Get or initialize LLM mapper."""
        if cls._llm_mapper is None and LLM_MAPPER_AVAILABLE:
            cls._llm_mapper = LLMOperationMapper(use_llm=False)  # Use pattern matching only by default
        return cls._llm_mapper

    @staticmethod
    def detect_operation_type(call_data: Dict[str, Any]) -> str:
        """
        Detect operation type from function and module names.

        Falls back through multiple strategies:
        1. Hardcoded pattern matching (fast, deterministic)
        2. LLM semantic classification (if available, language-agnostic)
        3. Default to 'method_call'
        """
        func = call_data.get('function', '').lower()
        module = call_data.get('module', '').lower()

        # === HARDCODED PATTERNS (Fast, deterministic) ===

        # Neural network operations
        if 'forward' in func and any(kw in module for kw in ['layer', 'nn', 'model', 'qwen', 'encoder', 'decoder']):
            return 'neural_layer'
        elif any(kw in func for kw in ['attention', 'self_attn', 'cross_attn']):
            return 'attention'
        elif any(kw in func for kw in ['conv1d', 'conv2d', 'conv3d', 'convolution']):
            return 'convolution'
        elif any(kw in func for kw in ['batchnorm', 'batch_norm', 'bn1d', 'bn2d']):
            return 'batch_norm'
        elif 'backward' in func or 'grad' in func:
            return 'gradient'

        # Array operations
        elif any(kw in func for kw in ['reshape', 'view', 'transpose', 'permute']):
            return 'array_reshape'
        elif any(kw in func for kw in ['matmul', 'dot', 'mm', '@']):
            return 'matrix_multiply'
        elif any(kw in func for kw in ['broadcast', 'expand']):
            return 'broadcasting'
        elif any(kw in func for kw in ['concat', 'stack', 'cat']):
            return 'array_concat'
        elif any(kw in func for kw in ['slice', 'index', 'select']):
            return 'array_slice'

        # Data type operations
        elif any(kw in func for kw in ['to_tensor', 'from_numpy', 'tensor']):
            return 'tensor_creation'
        elif any(kw in func for kw in ['encode', 'decode', 'embed']):
            return 'encoding'

        # Async/parallel operations
        elif any(kw in func for kw in ['async', 'await', '__await__']):
            return 'async_operation'
        elif 'thread' in func or 'threading' in module:
            return 'async_operation'
        elif 'pool' in func or 'multiprocessing' in module:
            return 'async_operation'

        # Memory operations
        elif any(kw in func for kw in ['compress', 'cache', 'store', '__setitem__']):
            return 'memory_write'
        elif any(kw in func for kw in ['retrieve', 'load', 'fetch', '__getitem__']):
            return 'memory_read'
        elif 'update' in func and any(kw in module for kw in ['cache', 'memory', 'dict']):
            return 'memory_update'

        # Control flow (detect by depth changes)
        elif call_data.get('depth', 0) > call_data.get('parent_depth', 0) + 1:
            return 'nested_call'

        # === LLM FALLBACK (Intelligent, language-agnostic) ===
        else:
            mapper = OperationDetector.get_llm_mapper()
            if mapper:
                return mapper.classify(call_data)

        # === DEFAULT FALLBACK ===
        return 'method_call'

    @staticmethod
    def extract_dimensions(call_data: Dict[str, Any]) -> Optional[Tuple[int, ...]]:
        """Extract tensor dimensions from parameters or return value."""
        params = call_data.get('parameters', {})
        return_val = call_data.get('return_value')

        # Look for shape/size in parameters
        for key, value in params.items():
            if 'shape' in str(key).lower():
                # Parse shape like "(1, 512, 768)" or "[1, 512, 768]"
                match = re.findall(r'\d+', str(value))
                if match:
                    return tuple(int(d) for d in match[:3])  # Max 3 dims for visualization

        return None

    @staticmethod
    def extract_data_type(call_data: Dict[str, Any]) -> str:
        """Extract data type from parameters."""
        params = call_data.get('parameters', {})

        for key, value in params.items():
            if 'dtype' in str(key).lower():
                dtype = str(value).lower()
                if 'float' in dtype:
                    return 'float'
                elif 'int' in dtype:
                    return 'int'
                elif 'bool' in dtype:
                    return 'bool'

        # Default based on context
        func = call_data.get('function', '').lower()
        if any(kw in func for kw in ['attention', 'softmax', 'layer_norm']):
            return 'float'
        elif 'index' in func or 'id' in func:
            return 'int'

        return 'unknown'


class OperationVisualizer:
    """Creates 3D visual elements for different operation types."""

    @staticmethod
    def create_method_call_viz(call_data: Dict, position: np.ndarray) -> VGroup:
        """Create visualization for generic method call."""
        func_name = call_data.get('function', 'method')[:20]

        # Create glowing box
        box = Cube(side_length=0.6)
        box.set_color(BLUE)
        box.set_opacity(0.7)
        box.set_sheen(0.5, direction=UP)
        box.move_to(position)

        # Function name label
        label = Text(func_name, font_size=14, color=WHITE)
        label.move_to(position + DOWN * 0.4)
        label.rotate(PI/2, axis=RIGHT)

        return VGroup(box, label)

    @staticmethod
    def create_neural_layer_viz(call_data: Dict, position: np.ndarray, dimensions: Optional[Tuple] = None) -> VGroup:
        """Create visualization for neural network layer."""
        func_name = call_data.get('function', 'layer')[:15]

        # Create grid of neurons based on dimensions
        if dimensions and len(dimensions) >= 2:
            rows = min(int(np.sqrt(dimensions[-2])), 5)
            cols = min(int(np.sqrt(dimensions[-1])), 5)
        else:
            rows, cols = 3, 3

        layer = VGroup()
        for i in range(rows):
            for j in range(cols):
                neuron = Sphere(radius=0.08, resolution=(6, 6))
                neuron.set_color(GREEN)
                neuron.set_opacity(0.9)
                neuron.set_sheen(0.7, direction=UP)

                x_offset = (j - cols/2) * 0.25
                y_offset = (i - rows/2) * 0.25
                neuron.move_to(position + RIGHT * x_offset + UP * y_offset)
                layer.add(neuron)

        # Dimension label
        if dimensions:
            dim_text = f"{dimensions}"
            dim_label = Text(dim_text, font_size=12, color=GREEN)
        else:
            dim_label = Text(func_name, font_size=12, color=GREEN)

        dim_label.move_to(position + DOWN * 0.7)
        dim_label.rotate(PI/2, axis=RIGHT)

        return VGroup(layer, dim_label)

    @staticmethod
    def create_attention_viz(call_data: Dict, position: np.ndarray) -> VGroup:
        """Create visualization for attention mechanism."""
        # Create cross pattern of glowing connections
        center = Sphere(radius=0.12, color=YELLOW)
        center.set_opacity(0.9)
        center.set_sheen(0.9, direction=UP)
        center.move_to(position)

        # Surrounding nodes (query, key, value representations)
        satellites = VGroup()
        for i in range(6):
            angle = i * PI / 3
            sat_pos = position + np.array([np.cos(angle), np.sin(angle), 0]) * 0.5
            sat = Sphere(radius=0.06, color=PURPLE)
            sat.set_opacity(0.7)
            sat.move_to(sat_pos)
            satellites.add(sat)

        # Connecting lines (attention weights)
        connections = VGroup()
        for sat in satellites:
            line = Line3D(center.get_center(), sat.get_center(), color=YELLOW)
            line.set_stroke(width=2, opacity=0.6)
            connections.add(line)

        label = Text("Attention", font_size=12, color=YELLOW)
        label.move_to(position + DOWN * 0.8)
        label.rotate(PI/2, axis=RIGHT)

        return VGroup(center, satellites, connections, label)

    @staticmethod
    def create_array_reshape_viz(call_data: Dict, position: np.ndarray, dimensions: Optional[Tuple] = None) -> VGroup:
        """Create visualization for array reshape operation with smooth morphing."""
        # Create morphing cube that shows dimension change
        if dimensions:
            # Scale cube based on dimensions
            scale_x = min(dimensions[0] / 100, 1.5) if len(dimensions) > 0 else 1
            scale_y = min(dimensions[1] / 100, 1.5) if len(dimensions) > 1 else 1
            scale_z = min(dimensions[2] / 100, 1.5) if len(dimensions) > 2 else 1
        else:
            scale_x = scale_y = scale_z = 1

        # Start with default cube, will morph during animation
        cube = Cube()
        cube.set_color(ORANGE)
        cube.set_opacity(0.6)
        cube.set_sheen(0.5, direction=UP)
        cube.move_to(position)

        # Dimension labels showing transformation
        if dimensions:
            dim_text = f"{dimensions}"
            dim_label = Text(dim_text, font_size=10, color=YELLOW)
            dim_label.move_to(position + UP * 0.6)
            dim_label.rotate(PI/2, axis=RIGHT)
        else:
            dim_label = Text("Reshape", font_size=10, color=YELLOW)
            dim_label.move_to(position + UP * 0.6)
            dim_label.rotate(PI/2, axis=RIGHT)

        # Arrows showing transformation with pulsing
        arrows = VGroup()
        for i, direction in enumerate([RIGHT, UP, OUT]):
            # Scale arrow based on dimension
            scales = [scale_x, scale_y, scale_z]
            length = 0.3 + scales[i] * 0.2

            arrow = Arrow3D(
                start=position,
                end=position + direction * length,
                color=interpolate_color(ORANGE, YELLOW, scales[i] / 1.5),
                thickness=0.015
            )
            arrow.set_sheen(0.7, direction=UP)
            arrows.add(arrow)

        label = Text(f"Reshape", font_size=12, color=ORANGE)
        label.move_to(position + DOWN * 0.7)
        label.rotate(PI/2, axis=RIGHT)

        return VGroup(cube, arrows, dim_label, label)

    @staticmethod
    def create_matrix_multiply_viz(call_data: Dict, position: np.ndarray) -> VGroup:
        """Create visualization for matrix multiplication."""
        # Two overlapping rectangles showing multiplication
        mat1 = Prism(dimensions=[0.6, 0.4, 0.05])
        mat1.set_color(RED)
        mat1.set_opacity(0.6)
        mat1.move_to(position + LEFT * 0.3)
        mat1.rotate(PI/6, axis=UP)

        mat2 = Prism(dimensions=[0.4, 0.6, 0.05])
        mat2.set_color(BLUE)
        mat2.set_opacity(0.6)
        mat2.move_to(position + RIGHT * 0.3)
        mat2.rotate(-PI/6, axis=UP)

        # Result matrix
        result = Prism(dimensions=[0.6, 0.6, 0.08])
        result.set_color(PURPLE)
        result.set_opacity(0.4)
        result.move_to(position)

        label = Text("MatMul", font_size=12, color=PURPLE)
        label.move_to(position + DOWN * 0.6)
        label.rotate(PI/2, axis=RIGHT)

        return VGroup(mat1, mat2, result, label)

    @staticmethod
    def create_parameter_flow_viz(start_pos: np.ndarray, end_pos: np.ndarray, data_type: str = 'unknown') -> VGroup:
        """Create flowing arrow showing parameter passing with data type and smooth particles."""
        # Color based on data type
        type_colors = {
            'float': YELLOW,
            'int': GREEN,
            'bool': RED,
            'tensor': BLUE,
            'unknown': GRAY
        }
        color = type_colors.get(data_type, GRAY)

        # Create smooth curved path instead of straight arrow
        # Bezier curve for more organic flow
        control_point = (start_pos + end_pos) / 2 + UP * 0.3

        # Arrow with smooth curve
        arrow = CubicBezier(
            start_pos,
            start_pos + (control_point - start_pos) * 0.5,
            end_pos + (control_point - end_pos) * 0.5,
            end_pos,
            color=color,
            stroke_width=2
        )
        arrow.set_opacity(0.6)

        # Create particle stream (3-5 particles for smooth flow)
        particles = VGroup()
        num_particles = 4

        for i in range(num_particles):
            # Data type indicator shape
            if data_type == 'tensor':
                particle = Cube(side_length=0.06)
            elif data_type == 'float':
                particle = Sphere(radius=0.05)
            elif data_type == 'int':
                particle = Octahedron(radius=0.05)
            else:
                particle = Dot3D(point=start_pos, radius=0.04)

            particle.set_color(color)
            particle.set_opacity(0.9)
            particle.set_sheen(0.7, direction=UP)

            # Position particles along path
            progress = i / num_particles
            particle.move_to(arrow.point_from_proportion(progress))
            particles.add(particle)

        return VGroup(arrow, particles)


class AdvancedOperationScene(ThreeDScene):
    """
    Advanced 3D scene with per-operation animations and multi-camera support.

    Features:
    - Unique animation for each operation type
    - Multi-camera tracking for parallel execution
    - Data flow visualization with type information
    - Dynamic camera movements following execution flow
    """

    def __init__(self, trace_file, **kwargs):
        super().__init__(**kwargs)
        self.trace_file = trace_file
        self.trace_data = None
        self.detector = OperationDetector()
        self.visualizer = OperationVisualizer()
        self.operation_objects = {}  # call_id -> VGroup mapping
        self.parallel_branches = []  # List of execution branches

    def construct(self):
        # Load trace
        self.load_trace()

        # Detect parallel branches
        self.detect_parallel_branches()

        # Setup initial camera
        self.set_camera_orientation(phi=70 * DEGREES, theta=-45 * DEGREES)

        # Title
        title = Text("Embodied AI: Advanced Operation Flow", font_size=36, color=BLUE)
        title.to_edge(UP)
        self.add_fixed_in_frame_mobjects(title)
        self.play(Write(title))
        self.wait(0.5)

        # Visualize execution
        if len(self.parallel_branches) > 1:
            self.visualize_parallel_execution()
        else:
            self.visualize_sequential_execution()

        self.wait(2)

    def load_trace(self):
        """Load trace JSON."""
        with open(self.trace_file, 'r') as f:
            self.trace_data = json.load(f)

    def detect_parallel_branches(self):
        """Detect parallel execution branches from trace."""
        calls = self.trace_data.get('calls', [])

        # Build call tree
        call_tree = defaultdict(list)
        for call in calls:
            if call.get('type') not in ['call', 'return']:
                continue
            parent_id = call.get('parent_id') or 'root'
            call_tree[parent_id].append(call)

        # Find nodes with multiple children (branching points)
        branches = []
        for parent_id, children in call_tree.items():
            if len(children) > 1:
                # Multiple parallel branches
                for child in children:
                    branch = self.extract_branch(child, call_tree)
                    if len(branch) > 0:
                        branches.append(branch)

        if len(branches) == 0:
            # No parallel branches, treat as single sequential branch
            branches = [calls]

        self.parallel_branches = branches

    def extract_branch(self, start_call: Dict, call_tree: Dict) -> List[Dict]:
        """Extract all calls in a branch starting from start_call."""
        branch = [start_call]
        call_id = start_call.get('call_id')

        # Recursively get all children
        children = call_tree.get(call_id, [])
        for child in children:
            branch.extend(self.extract_branch(child, call_tree))

        return branch

    def visualize_sequential_execution(self):
        """Visualize single sequential execution flow."""
        calls = self.parallel_branches[0] if self.parallel_branches else []

        current_y = 2
        prev_call_id = None

        for call in calls:
            if call.get('type') not in ['call', 'return']:
                continue

            call_id = call.get('call_id', '')
            depth = call.get('depth', 0)

            # Calculate position
            x_offset = depth * 1.2
            position = np.array([x_offset, current_y, 0])

            # Detect operation type
            op_type = self.detector.detect_operation_type(call)
            dimensions = self.detector.extract_dimensions(call)
            data_type = self.detector.extract_data_type(call)

            # Create visualization based on operation type
            viz_obj = self.create_operation_visual(op_type, call, position, dimensions)
            self.operation_objects[call_id] = viz_obj

            # Animate appearance with smooth bounce
            self.play(*[GrowFromCenter(obj) for obj in viz_obj],
                     run_time=0.4, rate_func=ease_out_bounce)

            # Show parameter flow from previous call with smooth particle stream
            if prev_call_id and prev_call_id in self.operation_objects:
                prev_pos = self.operation_objects[prev_call_id][0].get_center()
                flow_viz = self.visualizer.create_parameter_flow_viz(prev_pos, position, data_type)

                # Animate curved path appearing
                self.play(Create(flow_viz[0]), run_time=0.3, rate_func=ease_in_out_cubic)

                # Animate particles flowing along path with smooth cubic easing
                particle_anims = []
                for particle in flow_viz[1]:
                    particle_anims.append(
                        MoveAlongPath(particle, flow_viz[0],
                                    rate_func=ease_in_out_cubic, run_time=0.6)
                    )

                self.play(*particle_anims)

                # Fade out flow visualization
                self.play(FadeOut(flow_viz), run_time=0.2)

            # Move camera to follow
            if current_y < -3:
                self.play(self.camera.frame.animate.shift(DOWN * 1.5), run_time=0.2)

            current_y -= 1.5
            prev_call_id = call_id

    def visualize_parallel_execution(self):
        """Visualize parallel execution with multi-camera tracking."""
        # Position branches horizontally
        branch_spacing = 5
        num_branches = len(self.parallel_branches)

        # Create subtitle showing parallel execution
        subtitle = Text(f"Parallel Execution: {num_branches} Branches", font_size=24, color=GREEN)
        subtitle.to_edge(UP).shift(DOWN * 0.8)
        self.add_fixed_in_frame_mobjects(subtitle)
        self.play(FadeIn(subtitle))

        # Process each branch
        for branch_idx, branch_calls in enumerate(self.parallel_branches):
            x_base = (branch_idx - num_branches / 2) * branch_spacing
            current_y = 1

            # Branch label
            branch_label = Text(f"Branch {branch_idx + 1}", font_size=18, color=ORANGE)
            branch_label.move_to(np.array([x_base, 2.5, 0]))
            branch_label.rotate(PI/2, axis=RIGHT)
            self.play(FadeIn(branch_label), run_time=0.2)

            prev_call_id = None

            for call in branch_calls:
                if call.get('type') not in ['call', 'return']:
                    continue

                call_id = call.get('call_id', '')
                depth = call.get('depth', 0)

                # Position within branch
                x_offset = x_base + depth * 0.3
                position = np.array([x_offset, current_y, 0])

                # Detect operation type
                op_type = self.detector.detect_operation_type(call)
                dimensions = self.detector.extract_dimensions(call)
                data_type = self.detector.extract_data_type(call)

                # Create visualization
                viz_obj = self.create_operation_visual(op_type, call, position, dimensions)
                self.operation_objects[call_id] = viz_obj

                # Animate
                self.play(*[GrowFromCenter(obj) for obj in viz_obj], run_time=0.2)

                # Parameter flow
                if prev_call_id and prev_call_id in self.operation_objects:
                    prev_pos = self.operation_objects[prev_call_id][0].get_center()
                    flow_viz = self.visualizer.create_parameter_flow_viz(prev_pos, position, data_type)
                    self.play(GrowArrow(flow_viz[0]), run_time=0.15)
                    self.play(flow_viz[1].animate.move_to(position), run_time=0.3, rate_func=smooth)
                    self.remove(flow_viz)

                current_y -= 1
                prev_call_id = call_id

        # Pan camera across all branches
        self.play(
            self.camera.frame.animate.move_to(ORIGIN),
            run_time=2,
            rate_func=smooth
        )

    def create_operation_visual(self, op_type: str, call_data: Dict, position: np.ndarray, dimensions: Optional[Tuple] = None) -> VGroup:
        """Create visual elements for specific operation type."""
        # Existing operations
        if op_type == 'neural_layer':
            return self.visualizer.create_neural_layer_viz(call_data, position, dimensions)
        elif op_type == 'attention':
            return self.visualizer.create_attention_viz(call_data, position)
        elif op_type == 'array_reshape':
            return self.visualizer.create_array_reshape_viz(call_data, position, dimensions)
        elif op_type == 'matrix_multiply':
            return self.visualizer.create_matrix_multiply_viz(call_data, position)

        # Extended operations (if standards available)
        elif STANDARDS_AVAILABLE:
            if op_type == 'convolution':
                return ExtendedOperationVisualizer.create_convolution_viz(call_data, position)
            elif op_type == 'batch_norm':
                return ExtendedOperationVisualizer.create_batch_norm_viz(call_data, position)
            elif op_type == 'broadcasting':
                return ExtendedOperationVisualizer.create_broadcasting_viz(call_data, position)
            elif op_type == 'async_operation':
                return ExtendedOperationVisualizer.create_async_operation_viz(call_data, position)
            elif op_type == 'nested_call':
                depth = call_data.get('depth', 3)
                return ExtendedOperationVisualizer.create_nested_call_stack_viz(call_data, position, depth)
            elif op_type == 'memory_write':
                return ExtendedOperationVisualizer.create_memory_operation_viz(call_data, position, operation='write')
            elif op_type == 'memory_read':
                return ExtendedOperationVisualizer.create_memory_operation_viz(call_data, position, operation='read')
            elif op_type == 'memory_update':
                return ExtendedOperationVisualizer.create_memory_operation_viz(call_data, position, operation='update')
            elif op_type == 'matmul_enhanced':
                return ExtendedOperationVisualizer.create_enhanced_matmul_viz(call_data, position)

        # Default fallback
        return self.visualizer.create_method_call_viz(call_data, position)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        logger.info("Usage: python advanced_operation_viz.py <trace_json_file>")
        sys.exit(1)

    trace_file = sys.argv[1]

    # Render the scene
    from manim import config
    config.quality = 'medium_quality'
    config.output_file = 'advanced_operations'

    scene = AdvancedOperationScene(trace_file)
    scene.render()

    logger.info(f"Video saved to: {scene.renderer.file_writer.movie_file_path}")
