from logging_config import setup_logger
logger = setup_logger(__name__)

"""
Animation Standards - Consistent timing, colors, and shapes for all visualizations

This module provides universal standards for all debug visualization animations:
- AnimationTiming: Standard timing for all animation types
- AnimationColors: Standard color coding for data types and operations
- DataTypeShapes: Standard shapes for representing different data types
- AnimationHelpers: Utility functions for common animation patterns
"""

from manim import *
import numpy as np
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass
from enum import Enum


# ============================================================================
# ANIMATION TIMING STANDARDS
# ============================================================================

class AnimationTiming:
    """Standard timing for all animations (in seconds)."""
    # Data flow
    DATA_FLOW_SHORT = 0.5      # Short distance data flow
    DATA_FLOW_LONG = 1.0       # Long distance data flow

    # Transformations
    TRANSFORM_SIMPLE = 0.5     # Simple transformation
    TRANSFORM_COMPLEX = 1.5    # Complex transformation (reshape, etc.)

    # Function calls
    FUNCTION_ENTRY = 0.5       # Entering function
    FUNCTION_COMPUTE = 0.3     # Computing inside function
    FUNCTION_RETURN = 0.5      # Returning from function
    FUNCTION_TOTAL = 1.3       # Total for complete function call

    # Error propagation
    ERROR_PROPAGATE = 0.3      # Error propagation per stack frame

    # Element-wise operations
    ELEMENT_DELAY = 0.05       # Delay between elements in staggered animations
    ELEMENT_OPERATION = 0.1    # Time for single element operation

    # Layer operations
    LAYER_CREATE = 0.4         # Creating a neural layer
    LAYER_ACTIVATION = 0.6     # Activation flowing through layer

    # Memory operations
    MEMORY_READ = 0.3          # Memory read operation
    MEMORY_WRITE = 0.4         # Memory write operation
    MEMORY_UPDATE = 0.7        # Memory update (read + write)

    @staticmethod
    def get_timing_for_operation(op_type: str) -> float:
        """Get standard timing for operation type."""
        timing_map = {
            'reshape': AnimationTiming.TRANSFORM_COMPLEX,
            'transpose': AnimationTiming.TRANSFORM_SIMPLE,
            'matmul': AnimationTiming.TRANSFORM_COMPLEX,
            'attention': AnimationTiming.LAYER_ACTIVATION * 2,
            'function_call': AnimationTiming.FUNCTION_TOTAL,
            'method_call': AnimationTiming.FUNCTION_TOTAL * 0.8,
            'assignment': AnimationTiming.DATA_FLOW_SHORT,
            'memory_read': AnimationTiming.MEMORY_READ,
            'memory_write': AnimationTiming.MEMORY_WRITE,
            'convolution': AnimationTiming.TRANSFORM_COMPLEX * 2,
            'batch_norm': AnimationTiming.TRANSFORM_SIMPLE,
        }
        return timing_map.get(op_type, AnimationTiming.DATA_FLOW_SHORT)


# ============================================================================
# COLOR STANDARDS
# ============================================================================

class AnimationColors:
    """Standard color coding for data types and operations."""

    # Data types
    INT = BLUE
    FLOAT = GREEN
    STRING = YELLOW
    BOOL = RED
    NONE = GRAY

    # Complex types
    TENSOR = PURPLE
    ARRAY = BLUE_D
    LIST = TEAL
    DICT = ORANGE
    SET = PINK
    TUPLE = BLUE_E
    OBJECT = MAROON

    # Neural network components
    QUERY = BLUE_C
    KEY = GREEN_C
    VALUE = ORANGE
    ATTENTION_WEIGHT = YELLOW

    # Operations
    ADD = GREEN_B
    MULTIPLY = RED_B
    DIVIDE = BLUE_B
    SUBTRACT = PURPLE_B

    # Status indicators
    NORMAL = WHITE
    COMPUTING = YELLOW
    ERROR = RED_E
    SUCCESS = GREEN_B
    WAITING = GRAY

    # Flow types
    DATA_FLOW = BLUE_C
    CONTROL_FLOW = PURPLE_C
    ERROR_FLOW = RED_C
    ASYNC_FLOW = TEAL

    # Layers
    INPUT_LAYER = GREEN_D
    HIDDEN_LAYER = BLUE_D
    OUTPUT_LAYER = RED_D

    # Memory
    CACHE_HIT = GREEN_C
    CACHE_MISS = RED_C
    MEMORY_CELL = BLUE_E

    # Gradient tracking
    REQUIRES_GRAD = YELLOW_E
    NO_GRAD = GRAY

    # Device
    GPU = GOLD
    CPU = GRAY_B

    @staticmethod
    def get_type_color(data_type: str) -> str:
        """Get color for data type."""
        color_map = {
            'int': AnimationColors.INT,
            'float': AnimationColors.FLOAT,
            'str': AnimationColors.STRING,
            'bool': AnimationColors.BOOL,
            'tensor': AnimationColors.TENSOR,
            'array': AnimationColors.ARRAY,
            'list': AnimationColors.LIST,
            'dict': AnimationColors.DICT,
            'set': AnimationColors.SET,
            'tuple': AnimationColors.TUPLE,
            'object': AnimationColors.OBJECT,
            'none': AnimationColors.NONE,
        }
        return color_map.get(data_type.lower(), AnimationColors.NORMAL)

    @staticmethod
    def get_operation_color(op_type: str) -> str:
        """Get color for operation type."""
        color_map = {
            'add': AnimationColors.ADD,
            'mul': AnimationColors.MULTIPLY,
            'div': AnimationColors.DIVIDE,
            'sub': AnimationColors.SUBTRACT,
            'matmul': AnimationColors.MULTIPLY,
        }
        return color_map.get(op_type.lower(), AnimationColors.NORMAL)

    @staticmethod
    def get_layer_color(layer_index: int, total_layers: int = 1) -> str:
        """Get color for neural network layer based on position."""
        if layer_index == 0:
            return AnimationColors.INPUT_LAYER
        elif layer_index == total_layers - 1:
            return AnimationColors.OUTPUT_LAYER
        else:
            # Interpolate between input and output colors
            ratio = layer_index / max(total_layers - 1, 1)
            return interpolate_color(AnimationColors.INPUT_LAYER, AnimationColors.OUTPUT_LAYER, ratio)


# ============================================================================
# SHAPE STANDARDS
# ============================================================================

class DataTypeShapes:
    """Standard shapes for representing different data types."""

    @staticmethod
    def create_primitive(value: Any, data_type: str, position: np.ndarray = ORIGIN) -> Mobject:
        """Create standard visualization for primitive types."""
        color = AnimationColors.get_type_color(data_type)

        if data_type == 'bool':
            # Binary cube for boolean
            shape = Cube(side_length=0.2)
            shape.set_color(GREEN if value else RED)
            shape.set_opacity(0.8)
        elif data_type == 'str':
            # Text label for strings
            shape = Text(str(value)[:20], font_size=18, color=color)
        else:
            # Sphere for int/float/other
            shape = Sphere(radius=0.15, resolution=(8, 8))
            shape.set_color(color)
            shape.set_opacity(0.9)

            # Add value label
            label = Text(str(value)[:10], font_size=14, color=WHITE)
            label.next_to(shape, DOWN, buff=0.1)
            shape = VGroup(shape, label)

        shape.move_to(position)
        return shape

    @staticmethod
    def create_array_1d(size: int, position: np.ndarray = ORIGIN, color: str = None) -> VGroup:
        """Create 1D array visualization (row of spheres)."""
        if color is None:
            color = AnimationColors.ARRAY

        array = VGroup()
        spacing = 0.3

        for i in range(min(size, 10)):  # Max 10 elements shown
            sphere = Sphere(radius=0.1, resolution=(6, 6))
            sphere.set_color(color)
            sphere.set_opacity(0.8)
            sphere.move_to(position + RIGHT * (i - size/2) * spacing)
            array.add(sphere)

        if size > 10:
            dots = Text("...", font_size=20, color=color)
            dots.move_to(position + RIGHT * (5 * spacing))
            array.add(dots)

        return array

    @staticmethod
    def create_array_2d(rows: int, cols: int, position: np.ndarray = ORIGIN, color: str = None) -> VGroup:
        """Create 2D array visualization (grid of spheres)."""
        if color is None:
            color = AnimationColors.ARRAY

        grid = VGroup()
        spacing = 0.3

        max_rows = min(rows, 6)
        max_cols = min(cols, 6)

        for i in range(max_rows):
            for j in range(max_cols):
                sphere = Sphere(radius=0.08, resolution=(6, 6))
                sphere.set_color(color)
                sphere.set_opacity(0.8)

                x = (j - max_cols/2) * spacing
                y = (max_rows/2 - i) * spacing
                sphere.move_to(position + RIGHT * x + UP * y)
                grid.add(sphere)

        return grid

    @staticmethod
    def create_tensor_3d(dims: Tuple[int, int, int], position: np.ndarray = ORIGIN,
                        requires_grad: bool = False, device: str = "cpu") -> VGroup:
        """Create 3D tensor visualization (cube grid)."""
        d0, d1, d2 = dims
        color = AnimationColors.TENSOR

        tensor = VGroup()
        spacing = 0.25

        max_d0 = min(d0, 4)
        max_d1 = min(d1, 4)
        max_d2 = min(d2, 4)

        for i in range(max_d0):
            for j in range(max_d1):
                for k in range(max_d2):
                    sphere = Sphere(radius=0.06, resolution=(6, 6))
                    sphere.set_color(color)
                    sphere.set_opacity(0.7)

                    x = (k - max_d2/2) * spacing
                    y = (max_d1/2 - j) * spacing
                    z = (i - max_d0/2) * spacing
                    sphere.move_to(position + RIGHT * x + UP * y + OUT * z)
                    tensor.add(sphere)

        # Add gradient indicator
        if requires_grad:
            outline = Cube(side_length=max_d2 * spacing * 1.2)
            outline.set_stroke(AnimationColors.REQUIRES_GRAD, width=2)
            outline.set_fill(opacity=0)
            outline.move_to(position)
            tensor.add(outline)

        # Add device indicator
        if device == "gpu":
            device_label = Text("GPU", font_size=12, color=AnimationColors.GPU)
            device_label.next_to(tensor, DOWN, buff=0.2)
            tensor.add(device_label)

        return tensor

    @staticmethod
    def create_object(class_name: str, attributes: Dict[str, Any], position: np.ndarray = ORIGIN) -> VGroup:
        """Create object visualization (box with attributes)."""
        obj = VGroup()

        # Container box
        box = Cube(side_length=0.8)
        box.set_color(AnimationColors.OBJECT)
        box.set_opacity(0.3)
        box.move_to(position)
        obj.add(box)

        # Class name label
        label = Text(class_name[:15], font_size=16, color=AnimationColors.OBJECT)
        label.move_to(position + UP * 0.5)
        obj.add(label)

        # Attribute spheres inside
        attr_count = min(len(attributes), 4)
        for i, (attr_name, attr_value) in enumerate(list(attributes.items())[:attr_count]):
            attr_sphere = Sphere(radius=0.08, resolution=(6, 6))
            attr_sphere.set_color(AnimationColors.get_type_color(type(attr_value).__name__))
            attr_sphere.move_to(position + UP * (0.1 - i * 0.2))
            obj.add(attr_sphere)

        return obj


# ============================================================================
# ANIMATION HELPERS
# ============================================================================

class AnimationHelpers:
    """Utility functions for common animation patterns."""

    @staticmethod
    def create_particle_flow(start_pos: np.ndarray, end_pos: np.ndarray,
                            color: str = None, num_particles: int = 5) -> List[Mobject]:
        """Create particle flow animation from start to end."""
        if color is None:
            color = AnimationColors.DATA_FLOW

        particles = []
        for i in range(num_particles):
            particle = Sphere(radius=0.04, resolution=(6, 6))
            particle.set_color(color)
            particle.set_opacity(0.9)
            particle.move_to(start_pos)
            particles.append(particle)

        return particles

    @staticmethod
    def create_glow_effect(mobject: Mobject, color: str = None) -> Mobject:
        """Create glowing effect around mobject."""
        if color is None:
            color = AnimationColors.COMPUTING

        glow = mobject.copy()
        glow.set_color(color)
        glow.set_opacity(0.3)
        glow.scale(1.2)
        return glow

    @staticmethod
    def create_dimension_labels(dims: Tuple[int, ...], position: np.ndarray = ORIGIN) -> VGroup:
        """Create dimension labels for tensors/arrays."""
        labels = VGroup()

        for i, dim in enumerate(dims):
            label = Text(f"D{i}: {dim}", font_size=12, color=WHITE)
            label.move_to(position + DOWN * (0.3 + i * 0.2))
            labels.add(label)

        return labels

    @staticmethod
    def create_connection_web(source_layer: VGroup, target_layer: VGroup,
                             color: str = None, opacity: float = 0.2) -> VGroup:
        """Create connection web between two layers."""
        if color is None:
            color = AnimationColors.NORMAL

        connections = VGroup()

        # Sample connections (not all, would be too dense)
        sample_rate = max(len(source_layer) // 10, 1)

        for i, source in enumerate(source_layer):
            if i % sample_rate == 0:
                for j, target in enumerate(target_layer):
                    if j % sample_rate == 0:
                        line = Line(source.get_center(), target.get_center())
                        line.set_stroke(color, width=0.5, opacity=opacity)
                        connections.add(line)

        return connections

    @staticmethod
    def create_error_explosion(position: np.ndarray) -> VGroup:
        """Create error explosion effect."""
        explosion = VGroup()

        # Central sphere
        center = Sphere(radius=0.2, resolution=(8, 8))
        center.set_color(AnimationColors.ERROR)
        center.set_opacity(0.8)
        center.move_to(position)
        explosion.add(center)

        # Radiating particles
        for angle in range(0, 360, 30):
            particle = Sphere(radius=0.05, resolution=(6, 6))
            particle.set_color(AnimationColors.ERROR)
            rad = np.radians(angle)
            offset = RIGHT * np.cos(rad) * 0.4 + UP * np.sin(rad) * 0.4
            particle.move_to(position + offset)
            explosion.add(particle)

        return explosion


# ============================================================================
# EASING FUNCTIONS (for smooth animations)
# ============================================================================

def ease_in_out_cubic(t):
    """Smooth easing function."""
    if t < 0.5:
        return 4 * t * t * t
    else:
        return 1 - pow(-2 * t + 2, 3) / 2

def ease_out_bounce(t):
    """Bouncy easing function."""
    n1 = 7.5625
    d1 = 2.75

    if t < 1 / d1:
        return n1 * t * t
    elif t < 2 / d1:
        return n1 * (t - 1.5 / d1) * t + 0.75
    elif t < 2.5 / d1:
        return n1 * (t - 2.25 / d1) * t + 0.9375
    else:
        return n1 * (t - 2.625 / d1) * t + 0.984375
