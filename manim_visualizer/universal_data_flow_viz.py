"""
DEPRECATED: This file has been superseded by ultimate_architecture_viz.py

The data flow visualization functionality has been integrated into
ultimate_architecture_viz.py (Phase 3: Data Flow Deep Dive) which is the single
active engine used by ManimAutoRenderer.kt.

DO NOT USE - Kept for reference only.
================================================================================

Universal Data Flow Visualizer - Complete Source-to-Sink Animation

Creates comprehensive visualizations showing ENTIRE execution cycle:
- Source to sink: Entry point → All intermediate steps → Final output
- Complete data passing between ALL layers, methods, operations
- Shows transformations at each step with data flow animations
- Builds incrementally using procedural composition
- Uses existing animation standards


Handles ALL data flow scenarios:
- Data sharing (assignment, references, copying)
- Data transformation (reshaping, operations, broadcasting)
- Data passing (function calls, method invocations)
- All data types (primitives, collections, arrays, tensors, objects)
- Tensor operations (complete coverage)
- Neural layer operations (attention, convolution, etc.)
- Async/parallel processing
- Memory operations
- Control flow data
- Error/exception handling

Animation standards enforced:
- Consistent timing
- Standard color coding
- Standardized shapes
- Smooth transitions
- Informative camera movement
"""

from manim import *
import json
import numpy as np
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass
from enum import Enum

# Import logging configuration
try:
    from logging_config import setup_logger
    logger = setup_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)

# Import comprehensive micro-animations library
try:
    from comprehensive_micro_animations import ComprehensiveMicroAnimator
    COMPREHENSIVE_ANIMS_AVAILABLE = True
except ImportError:
    COMPREHENSIVE_ANIMS_AVAILABLE = False

# Import advanced operation detection
try:
    from advanced_operation_viz import OperationDetector, OperationVisualizer
    from operation_visualizer_extended import ExtendedOperationVisualizer
    SPECIALIZED_VIZ_AVAILABLE = True
except ImportError:
    SPECIALIZED_VIZ_AVAILABLE = False

# Import particle flow animations
try:
    from smooth_microanimations import DataFlowParticles
    PARTICLE_FLOW_AVAILABLE = True
except ImportError:
    PARTICLE_FLOW_AVAILABLE = False

# Import pattern detection
try:
    from procedural_trace_viz import ProceduralTraceScene
    PATTERN_DETECTION_AVAILABLE = True
except ImportError:
    PATTERN_DETECTION_AVAILABLE = False

# ============================================================================
# ANIMATION STANDARDS
# ============================================================================

class AnimationTiming:
    """Standard timing for all animations."""
    DATA_FLOW_SHORT = 0.5     # Short distance data flow
    DATA_FLOW_LONG = 1.0      # Long distance data flow
    TRANSFORM_SIMPLE = 0.5    # Simple transformation
    TRANSFORM_COMPLEX = 1.5   # Complex transformation (reshape, etc.)
    FUNCTION_ENTRY = 0.5      # Entering function
    FUNCTION_COMPUTE = 0.3    # Computing inside function
    FUNCTION_RETURN = 0.5     # Returning from function
    ERROR_PROPAGATE = 0.3     # Error propagation per frame

class AnimationColors:
    """Standard color coding for data types and operations."""
    # Data types
    INT = BLUE
    FLOAT = GREEN
    STRING = YELLOW
    BOOL = RED
    TENSOR = PURPLE
    OBJECT = ORANGE

    # Operations
    ADD = GREEN
    MULTIPLY = RED
    DIVIDE = BLUE
    SUBTRACT = YELLOW

    # Status
    NORMAL = WHITE
    COMPUTING = YELLOW
    ERROR = RED
    SUCCESS = GREEN

    # Flow types
    DATA_FLOW = BLUE
    CONTROL_FLOW = PURPLE
    ERROR_FLOW = RED
    REFERENCE = GRAY

# ============================================================================
# DATA TYPE REPRESENTATIONS
# ============================================================================

class DataShape(Enum):
    """Shape representations for different data types."""
    PRIMITIVE_SPHERE = "sphere"
    ARRAY_GRID = "grid"
    TENSOR_CUBE = "cube"
    OBJECT_BOX = "box"
    FUNCTION_ROUNDED_BOX = "rounded_box"
    LAYER_NEURONS = "neurons"

@dataclass
class DataVisualization:
    """Represents a visualized data object."""
    data_type: str
    shape: DataShape
    mobject: Mobject
    dimensions: Optional[Tuple[int, ...]] = None
    label: Optional[Text] = None
    metadata: Dict[str, Any] = None

class BillboardText(Text):
    """
    Text that always faces the camera regardless of 3D rotation.
    Ensures text legibility at all camera angles in 3D scenes.
    
    Note: This uses a simpler approach - text maintains forward-facing orientation
    without storing scene reference (which would break deep copy).
    """
    def __init__(self, text_string, font_size=14, color=WHITE, scene=None, **kwargs):
        super().__init__(text_string, font_size=font_size, color=color, **kwargs)
        # Don't store scene reference to avoid pickle issues
        # Text will be rendered normally in 3D space

class DataVisualizer:
    """Creates consistent visual representations for all data types."""

    @staticmethod
    def create_primitive(value: Any, data_type: str) -> DataVisualization:
        """Create visualization for primitive types."""
        if data_type == "int":
            sphere = Sphere(radius=0.2, color=AnimationColors.INT)
            label = Text(str(value), font_size=16).move_to(sphere)
        elif data_type == "float":
            sphere = Sphere(radius=0.2, color=AnimationColors.FLOAT)
            label = Text(f"{value:.2f}", font_size=16).move_to(sphere)
        elif data_type == "str":
            # Ribbon/scroll shape for strings
            rect = RoundedRectangle(height=0.3, width=min(len(str(value)) * 0.1, 2),
                                     corner_radius=0.1, color=AnimationColors.STRING)
            label = Text(str(value)[:20], font_size=14).move_to(rect)
            sphere = VGroup(rect, label)
            label = None  # Already included
        elif data_type == "bool":
            # Cube for boolean (binary)
            cube = Cube(side_length=0.3, fill_color=AnimationColors.SUCCESS if value else AnimationColors.ERROR,
                        fill_opacity=0.7)
            label = Text("T" if value else "F", font_size=16).move_to(cube)
        else:
            sphere = Sphere(radius=0.2, color=AnimationColors.NORMAL)
            label = Text(str(value)[:10], font_size=16).move_to(sphere)

        return DataVisualization(
            data_type=data_type,
            shape=DataShape.PRIMITIVE_SPHERE,
            mobject=sphere,
            label=label
        )

    @staticmethod
    def create_array(values: List[Any], dimensions: Tuple[int, ...]) -> DataVisualization:
        """Create visualization for arrays/lists."""
        if len(dimensions) == 1:
            # 1D array: Row of spheres
            spheres = VGroup(*[
                Sphere(radius=0.15, color=AnimationColors.INT)
                for _ in range(min(dimensions[0], 10))  # Cap at 10 for vis
            ])
            spheres.arrange(RIGHT, buff=0.3)

        elif len(dimensions) == 2:
            # 2D array: Grid
            rows, cols = dimensions[0], dimensions[1]
            rows, cols = min(rows, 5), min(cols, 5)  # Cap for visualization
            spheres = VGroup(*[
                VGroup(*[Sphere(radius=0.1, color=AnimationColors.INT) for _ in range(cols)])
                for _ in range(rows)
            ])
            for row in spheres:
                row.arrange(RIGHT, buff=0.2)
            spheres.arrange(DOWN, buff=0.2)
        else:
            # Higher dimensions: Show as 2D slice with depth indicator
            spheres = VGroup(*[
                VGroup(*[Sphere(radius=0.1, color=AnimationColors.INT) for _ in range(5)])
                for _ in range(5)
            ])
            for row in spheres:
                row.arrange(RIGHT, buff=0.2)
            spheres.arrange(DOWN, buff=0.2)

        # Add dimension labels
        label = Text(f"Shape: {dimensions}", font_size=14).next_to(spheres, UP)

        return DataVisualization(
            data_type="array",
            shape=DataShape.ARRAY_GRID,
            mobject=spheres,
            dimensions=dimensions,
            label=label
        )

    @staticmethod
    def create_tensor(dimensions: Tuple[int, ...], requires_grad: bool = False,
                      device: str = "cpu") -> DataVisualization:
        """Create visualization for PyTorch/NumPy tensors."""
        if len(dimensions) == 1:
            # 1D tensor
            vis = DataVisualizer.create_array([], dimensions)
            vis.mobject.set_color(AnimationColors.TENSOR)
        elif len(dimensions) == 2:
            # 2D tensor
            vis = DataVisualizer.create_array([], dimensions)
            vis.mobject.set_color(AnimationColors.TENSOR)
        elif len(dimensions) == 3:
            # 3D tensor: Cube grid
            d0, d1, d2 = [min(d, 4) for d in dimensions]  # Cap each dim
            cubes = VGroup()
            for i in range(d0):
                for j in range(d1):
                    for k in range(d2):
                        cube = Cube(side_length=0.15, fill_color=AnimationColors.TENSOR,
                                    fill_opacity=0.6)
                        cube.move_to([i*0.3, j*0.3, k*0.3])
                        cubes.add(cube)
            vis = DataVisualization(
                data_type="tensor",
                shape=DataShape.TENSOR_CUBE,
                mobject=cubes,
                dimensions=dimensions
            )
        else:
            # 4D+: Show as 3D with extra label
            vis = DataVisualizer.create_tensor(dimensions[:3])

        # Add gradient tracking indicator
        if requires_grad:
            outline = SurroundingRectangle(vis.mobject, color=YELLOW, buff=0.1)
            vis.mobject = VGroup(vis.mobject, outline)

        # Add device indicator
        if device == "cuda" or device.startswith("cuda"):
            glow = vis.mobject.copy().set_color(GREEN).set_opacity(0.3).scale(1.1)
            vis.mobject = VGroup(glow, vis.mobject)

        # Add dimension labels
        dim_text = Text(f"Tensor {dimensions}", font_size=14)
        dim_text.next_to(vis.mobject, UP)
        vis.label = dim_text

        return vis

    @staticmethod
    def create_object(class_name: str, attributes: Dict[str, Any]) -> DataVisualization:
        """Create visualization for custom objects."""
        # Container box
        box = RoundedRectangle(height=2, width=2.5, corner_radius=0.2,
                                color=AnimationColors.OBJECT)

        # Class name label
        name_label = Text(class_name, font_size=18, color=WHITE)
        name_label.move_to(box.get_top() + DOWN*0.3)

        # Attribute visualizations
        attr_group = VGroup()
        for i, (key, value) in enumerate(list(attributes.items())[:5]):  # Max 5 attrs
            attr_viz = DataVisualizer.create_primitive(value, type(value).__name__)
            attr_label = Text(f"{key}:", font_size=12).next_to(attr_viz.mobject, LEFT, buff=0.2)
            attr_line = VGroup(attr_label, attr_viz.mobject)
            attr_group.add(attr_line)

        attr_group.arrange(DOWN, buff=0.2, center=False, aligned_edge=LEFT)
        attr_group.move_to(box.get_center())

        obj_vis = VGroup(box, name_label, attr_group)

        return DataVisualization(
            data_type="object",
            shape=DataShape.OBJECT_BOX,
            mobject=obj_vis,
            metadata={"class": class_name, "attributes": attributes}
        )

    @staticmethod
    def create_function_box(function_name: str, is_method: bool = False) -> Mobject:
        """Create visualization for function/method."""
        box = RoundedRectangle(height=0.8, width=2, corner_radius=0.3,
                                color=AnimationColors.COMPUTING, fill_opacity=0.3)
        label = Text(function_name, font_size=16).move_to(box)

        if is_method:
            # Add indicator for method (attached to object)
            indicator = Dot(color=AnimationColors.OBJECT, radius=0.05)
            indicator.next_to(box, LEFT, buff=0)
            return VGroup(box, label, indicator)

        return VGroup(box, label)

    @staticmethod
    def create_layer_visualization(layer_type: str, input_dim: int, output_dim: int) -> Mobject:
        """Create visualization for neural network layer."""
        # Input neurons
        input_neurons = VGroup(*[
            Circle(radius=0.1, color=AnimationColors.TENSOR, fill_opacity=0.7)
            for _ in range(min(input_dim, 8))
        ])
        input_neurons.arrange(DOWN, buff=0.2)

        # Output neurons
        output_neurons = VGroup(*[
            Circle(radius=0.1, color=AnimationColors.SUCCESS, fill_opacity=0.7)
            for _ in range(min(output_dim, 8))
        ])
        output_neurons.arrange(DOWN, buff=0.2)
        output_neurons.shift(RIGHT * 3)

        # Connections (sample, not all)
        connections = VGroup()
        for i in range(min(3, len(input_neurons))):
            for j in range(min(3, len(output_neurons))):
                line = Line(input_neurons[i].get_center(), output_neurons[j].get_center(),
                           stroke_width=0.5, color=GRAY, stroke_opacity=0.3)
                connections.add(line)

        # Layer label
        label = Text(layer_type, font_size=14).move_to([1.5, -1.5, 0])

        return VGroup(connections, input_neurons, output_neurons, label)

# ============================================================================
# ANIMATION GENERATORS
# ============================================================================

class DataFlowAnimator:
    """Generates animations for all data flow scenarios."""

    @staticmethod
    def animate_assignment(scene: Scene, source_viz: DataVisualization,
                          dest_name: str, is_reference: bool = False):
        """Animate variable assignment (copy or reference)."""
        # Create destination box
        dest_box = Rectangle(height=0.5, width=1.5, color=WHITE)
        dest_label = Text(dest_name, font_size=14).move_to(dest_box)
        dest = VGroup(dest_box, dest_label)
        dest.shift(RIGHT * 3)

        scene.play(Create(dest), run_time=0.3)

        if is_reference:
            # Reference: Dashed arrow
            arrow = DashedLine(source_viz.mobject.get_right(), dest.get_left(),
                              color=AnimationColors.REFERENCE)
            scene.play(Create(arrow), run_time=AnimationTiming.DATA_FLOW_SHORT)

            # Pulsing to show shared reference
            scene.play(
                source_viz.mobject.animate.set_color(YELLOW),
                dest.animate.set_color(YELLOW),
                run_time=0.3
            )
            scene.play(
                source_viz.mobject.animate.set_color(WHITE),
                dest.animate.set_color(WHITE),
                run_time=0.3
            )
        else:
            # Copy: Particle flow
            particle = source_viz.mobject.copy().scale(0.3)
            scene.play(
                particle.animate.move_to(dest.get_center()),
                run_time=AnimationTiming.DATA_FLOW_SHORT,
                rate_func=rate_functions.ease_in_out_cubic
            )
            scene.play(FadeOut(particle), FadeIn(source_viz.mobject.copy().move_to(dest)))

    @staticmethod
    def animate_transformation(scene: Scene, source_viz: DataVisualization,
                              transform_type: str, target_dims: Tuple[int, ...]):
        """Animate data transformation (reshape, transpose, etc.)."""
        if transform_type == "reshape":
            # Morph shape from source to target dimensions
            target_viz = DataVisualizer.create_tensor(target_dims)
            target_viz.mobject.move_to(source_viz.mobject.get_center())

            # Show morphing animation
            scene.play(
                Transform(source_viz.mobject, target_viz.mobject),
                Transform(source_viz.label, target_viz.label) if source_viz.label else Animation(Mobject()),
                run_time=AnimationTiming.TRANSFORM_COMPLEX,
                rate_func=rate_functions.ease_in_out_cubic
            )

        elif transform_type == "transpose":
            # Rotate animation
            scene.play(
                Rotate(source_viz.mobject, angle=PI/2, axis=OUT),
                run_time=AnimationTiming.TRANSFORM_SIMPLE
            )
            # Update dimension label
            if source_viz.label and source_viz.dimensions:
                new_dims = source_viz.dimensions[::-1]  # Reverse
                new_label = Text(f"Tensor {new_dims}", font_size=14)
                new_label.next_to(source_viz.mobject, UP)
                scene.play(Transform(source_viz.label, new_label), run_time=0.3)

    @staticmethod
    def animate_function_call(scene: Scene, function_name: str,
                             args: List[DataVisualization],
                             return_viz: Optional[DataVisualization] = None):
        """Animate function call with parameters."""
        # Create function box
        func_box = DataVisualizer.create_function_box(function_name)
        func_box.shift(UP * 1.5)

        scene.play(FadeIn(func_box), run_time=0.3)

        # Animate arguments flowing into function
        arg_particles = VGroup(*[arg.mobject.copy().scale(0.3) for arg in args])
        scene.play(
            *[particle.animate.move_to(func_box.get_center())
              for particle in arg_particles],
            run_time=AnimationTiming.FUNCTION_ENTRY,
            rate_func=rate_functions.ease_in_cubic
        )

        # Compute (pulsing function box)
        scene.play(
            func_box.animate.set_color(AnimationColors.COMPUTING),
            run_time=AnimationTiming.FUNCTION_COMPUTE / 2
        )
        scene.play(
            func_box.animate.set_color(WHITE),
            run_time=AnimationTiming.FUNCTION_COMPUTE / 2
        )

        # Return value
        if return_viz:
            result_particle = return_viz.mobject.copy().scale(0.3).move_to(func_box)
            scene.play(
                result_particle.animate.shift(DOWN * 2),
                run_time=AnimationTiming.FUNCTION_RETURN,
                rate_func=rate_functions.ease_out_cubic
            )
            scene.play(Transform(result_particle, return_viz.mobject))

        scene.play(FadeOut(func_box), run_time=0.3)

    @staticmethod
    def animate_tensor_operation(scene: Scene, op_type: str,
                                 tensors: List[DataVisualization],
                                 result: DataVisualization):
        """Animate tensor operations (matmul, concat, etc.)."""
        if op_type == "matmul":
            # Matrix multiplication visualization
            A, B = tensors[0], tensors[1]

            # Show connection pattern
            for i in range(min(3, A.dimensions[0] if A.dimensions else 3)):
                for j in range(min(3, B.dimensions[1] if B.dimensions else 3)):
                    # Highlight row from A and column from B
                    scene.play(
                        A.mobject[i].animate.set_color(YELLOW),
                        B.mobject[j].animate.set_color(YELLOW),
                        run_time=0.1
                    )
                    # Show result element appearing
                    if hasattr(result.mobject, '__getitem__'):
                        scene.play(
                            result.mobject[i*B.dimensions[1] + j].animate.set_opacity(1),
                            run_time=0.1
                        )
                    scene.play(
                        A.mobject[i].animate.set_color(WHITE),
                        B.mobject[j].animate.set_color(WHITE),
                        run_time=0.05
                    )

        elif op_type == "concat":
            # Concatenation: Move tensors together
            tensors[1].mobject.next_to(tensors[0].mobject, RIGHT, buff=0.1)
            scene.play(
                tensors[1].mobject.animate.shift(LEFT * 0.1),
                run_time=AnimationTiming.TRANSFORM_SIMPLE
            )
            # Merge into result
            scene.play(
                Transform(VGroup(*[t.mobject for t in tensors]), result.mobject),
                run_time=AnimationTiming.TRANSFORM_SIMPLE
            )

    @staticmethod
    def animate_async_operation(scene: Scene, main_track: Mobject, async_track: Mobject):
        """Animate async/parallel execution."""
        # Split screen visualization
        divider = Line(UP * 3, DOWN * 3, color=GRAY)
        scene.play(Create(divider), run_time=0.3)

        main_track.shift(LEFT * 2)
        async_track.shift(RIGHT * 2)

        # Both execute in parallel (use add_updater for continuous animation)
        scene.play(
            main_track.animate.shift(DOWN * 2),
            async_track.animate.shift(DOWN * 2),
            run_time=2,
            rate_func=rate_functions.linear
        )

        # Merge results
        scene.play(
            async_track.animate.move_to(main_track.get_center() + RIGHT * 0.5),
            run_time=0.5
        )
        scene.play(FadeOut(divider), run_time=0.3)

# ============================================================================
# MAIN SCENE CLASS
# ============================================================================

class UniversalDataFlowScene(ThreeDScene):
    """Main scene that generates animations for any trace data."""

    def __init__(self, trace_file=None, simplified_mode=True, **kwargs):
        super().__init__(**kwargs)
        self.trace_file = trace_file
        self.trace_data = None
        self.simplified_mode = simplified_mode
        self.system_pattern = 'generic'  # Will be set by pattern detection

        # Initialize comprehensive micro-animation system
        if COMPREHENSIVE_ANIMS_AVAILABLE:
            self.comprehensive_animator = ComprehensiveMicroAnimator(self)
        else:
            self.comprehensive_animator = None

        # Initialize particle flow system
        if PARTICLE_FLOW_AVAILABLE:
            self.data_flow_particles = DataFlowParticles()
        else:
            self.data_flow_particles = None

        # Initialize operation detector
        if SPECIALIZED_VIZ_AVAILABLE:
            self.op_detector = OperationDetector()
            self.op_visualizer = OperationVisualizer()
            self.extended_visualizer = ExtendedOperationVisualizer()
        else:
            self.op_detector = None
            self.op_visualizer = None
            self.extended_visualizer = None

    def safe_camera_move(self, *animations, run_time=1.5, rate_func=None):
        """
        Safely perform camera movements, skipping if ThreeDCamera doesn't support frame.

        Args:
            *animations: Animation objects (may include camera.frame animations)
            run_time: Animation duration
            rate_func: Rate function for animation
        """
        if not hasattr(self.camera, 'frame'):
            logger.debug("ThreeDCamera detected, skipping camera.frame animations")
            # Filter out camera.frame animations, play the rest
            non_camera_anims = [anim for anim in animations
                               if not (hasattr(anim, 'mobject') and anim.mobject == getattr(self.camera, 'frame', None))]
            if non_camera_anims:
                kwargs = {'run_time': run_time}
                if rate_func:
                    kwargs['rate_func'] = rate_func
                self.play(*non_camera_anims, **kwargs)
            return

        # Has frame attribute, play all animations
        kwargs = {'run_time': run_time}
        if rate_func:
            kwargs['rate_func'] = rate_func
        try:
            self.play(*animations, **kwargs)
        except AttributeError as e:
            logger.warning(f"Camera animation failed: {e}", exc_info=True)

    def construct(self):
        # If trace file provided, visualize it; otherwise show demos
        if self.trace_file:
            self.visualize_from_trace()
        else:
            self.demonstrate_all_scenarios()

    def visualize_from_trace(self):
        """
        Generate UNIFIED visualization from trace JSON file.

        ONE COHERENT VIDEO with smooth transitions:
        1. PHASE 1: Architecture Overview - Layered 3D modules with orbiting camera
        2. PHASE 2: Dependencies - Flowing connections (shrink arch to upper-left, keep visible)
        3. PHASE 3: Recommendations - Float in from right (fade deps to 30%, keep visible)
        4. PHASE 4: Data Journey - Complete call tree with parallel branches (move recs to sidebar)

        Key principles:
        - End position of phase N = start position of phase N+1
        - All text billboard-facing (always readable)
        - No occlusion - everything visible when needed
        - 3Blue1Brown style smooth camera work
        - Parallel branches in call tree spread in X, Y, Z (no stacking)
        """
        # Load trace
        with open(self.trace_file, 'r') as f:
            self.trace_data = json.load(f)

        # === PATTERN DETECTION (Auto-tune visualization based on system type) ===
        if PATTERN_DETECTION_AVAILABLE:
            try:
                pattern_detector = ProceduralTraceScene()
                pattern_detector.execution_graph = self._build_execution_graph_for_pattern()

                if pattern_detector.is_neural_network_pattern():
                    self.system_pattern = 'neural_network'
                    logger.info("[Pattern] Detected: Neural Network")
                elif pattern_detector.is_recursive_pattern():
                    self.system_pattern = 'recursive'
                    logger.info("[Pattern] Detected: Recursive Algorithm")
                elif pattern_detector.is_pipeline_pattern():
                    self.system_pattern = 'pipeline'
                    logger.info("[Pattern] Detected: Data Pipeline")
                else:
                    self.system_pattern = 'generic'
                    logger.info("[Pattern] Using generic flow")
            except Exception as e:
                self.system_pattern = 'generic'
                logger.warning(f"Pattern detection failed, using generic: {e}", exc_info=True)

        # Setup camera for PROPER 3D VIEWING
        # phi=60° gives good 3D perspective (not too flat, not too steep)
        # theta=-30° provides angled view to see X, Y, Z spread
        self.camera.background_color = "#1e1e1e"
        self.set_camera_orientation(phi=60 * DEGREES, theta=-30 * DEGREES, distance=10)

        # PHASE 1: Architecture Overview with orbiting camera
        arch_group = self.show_architecture_overview()
        self.wait(2)

        # TRANSITION 1→2: Move architecture to upper-left corner for landscape view
        # Architecture stays visible throughout as context
        if arch_group:
            self.play(
                arch_group.animate.scale(0.4).to_corner(UL).shift(DOWN * 0.5),
                run_time=1.5
            )

        # PHASE 2: Dependencies overlay on architecture
        deps_group = self.visualize_dependencies()
        self.wait(2)

        # TRANSITION 2→3: Fade dependencies to background, keep visible
        if deps_group:
            self.play(
                deps_group.animate.set_opacity(0.3),
                run_time=1
            )

        # PHASE 3: Recommendations (no anti-patterns for cleaner flow)
        recs_group = self.show_recommendations()
        self.wait(2)

        # TRANSITION 3→4: Move recommendations to left sidebar, shrink
        if recs_group:
            self.play(
                recs_group.animate.scale(0.4).to_edge(LEFT).shift(DOWN * 2),
                run_time=1.5
            )

        # PHASE 4: Data Journey through call tree with parallel branches
        # Focus camera on LEFT side initially (start of execution)
        # ThreeDCamera doesn't have 'frame' attribute, skip camera shift for 3D scenes
        if hasattr(self.camera, 'frame'):
            try:
                # ThreeDCamera doesn't have 'frame' attribute, skip camera operations for 3D scenes
                if hasattr(self.camera, 'frame'):
                    try:
                    self.play(
                        self.camera.frame.animate.shift(LEFT * 5),
                        run_time=1.5
                    )
                    except AttributeError as e:
                        logger.debug(f"Camera operation skipped: {e}")
                else:
                    logger.debug("ThreeDCamera detected, skipping frame operation")
            except AttributeError as e:
                logger.debug(f"Camera shift skipped: {e}")
        else:
            logger.debug("ThreeDCamera detected, skipping frame shift")

        correlation_id = self.trace_data.get('correlation_id', 'unknown')
        title = BillboardText(f"Data Flow: {correlation_id}", font_size=32, color=BLUE)
        title.to_edge(UP)
        self.add_fixed_in_frame_mobjects(title)
        self.play(Write(title), run_time=0.8)

        # Extract source-to-sink path
        path = self.extract_main_path()

        if not path:
            # No path found, show error
            error_text = BillboardText("No data flow path detected", font_size=24, color=RED)
            self.add_fixed_in_frame_mobjects(error_text)
            self.play(FadeIn(error_text))
            self.wait(2)
            return

        # Visualize complete data journey with depth-based camera tracking
        # Camera zooms in for nested calls, zooms out on returns
        # All text billboards face camera for constant legibility
        # Parallel branches spread in 3D space (no stacking at center)
        self.visualize_data_journey(path)

        # Cleanup
        self.play(FadeOut(title), run_time=0.5)
        self.wait(1)

    def show_architecture_overview(self, focus_layer: int = 0):
        """
        PHASE 1: Show architectural overview with orbiting camera.
        - Layered 3D modules
        - Billboard text for labels (always readable)
        - Camera orbits around architecture
        - Returns VGroup for transitions

        Args:
            focus_layer: Index of layer to focus on (default: 0 = entry layer)

        Returns:
            VGroup containing all architecture elements
        """
        # Import architecture extractor
        try:
            import sys
            import os
            sys.path.insert(0, os.path.dirname(__file__))
            from architecture_explainer import ArchitectureExtractor

            # Extract architecture
            extractor = ArchitectureExtractor(self.trace_data)
            arch = extractor.extract()

            # Initialize module_positions for dependencies phase
            self.module_positions = {}

            # Create overview title
            overview_title = BillboardText("System Architecture", font_size=36, color=GOLD)
            overview_title.to_edge(UP)
            self.add_fixed_in_frame_mobjects(overview_title)
            self.play(Write(overview_title), run_time=1.0)

            # Show layers as stacked 3D boxes with individual modules
            layers = arch.get('layers', [])
            if layers:
                layer_viz = VGroup()
                z_pos = 0

                # Vanishing point for perspective
                vanishing_point = np.array([0, 0, -10])

                for i, layer_modules in enumerate(layers):
                    # Distance from focus determines perspective
                    distance_from_focus = abs(i - focus_layer)

                    # PERSPECTIVE EFFECTS
                    # Scale: focused layer at 1.0, decreases by 15% per layer away
                    scale = max(0.4, 1.0 - (distance_from_focus * 0.15))

                    # Opacity: focused layer at 1.0, decreases by 25% per layer away
                    opacity = max(0.3, 1.0 - (distance_from_focus * 0.25))

                    # Z position: focused layer at 0, others recede into distance
                    z_offset = (i - focus_layer) * -1.5

                    # Perspective factor: objects farther from camera appear smaller
                    perspective_factor = 1.0 - (abs(z_offset) / 15.0)
                    perspective_factor = max(0.5, perspective_factor)

                    # Create layer box with perspective
                    layer_height = 0.5 * scale
                    layer_width = min(len(layer_modules) * 1.5, 8) * scale

                    layer_box = Prism(dimensions=[layer_width * perspective_factor,
                                                   layer_height * perspective_factor,
                                                   0.3 * scale])

                    # Color and opacity based on focus
                    if i == focus_layer:
                        layer_box.set_fill(GOLD, opacity=0.6)
                        layer_box.set_stroke(GOLD, width=3)
                    else:
                        layer_box.set_fill(BLUE, opacity=opacity * 0.5)
                        layer_box.set_stroke(BLUE, width=2)

                    # CIRCULAR LAYOUT - Keep everything CENTERED and IN FRAME
                    # Arrange layers in a circle viewed from 3D angle
                    # NO diagonal staircase that goes out of frame!
                    radius = 3.5  # Fixed radius to keep in frame
                    angle = (i / max(len(layers), 1)) * 2 * PI
                    x_layer_pos = radius * np.cos(angle)  # Circle around center
                    y_layer_pos = radius * np.sin(angle)  # Circle around center
                    z_layer_pos = 0  # Keep all in same Z plane for visibility

                    layer_box.move_to([x_layer_pos, y_layer_pos, z_layer_pos])
                    layer_box.scale(perspective_factor)

                    # Layer label with BillboardText (DONT rotate - should always face camera!)
                    layer_label = BillboardText(f"Layer {i}: {len(layer_modules)} modules",
                                     font_size=int(16 * scale), color=WHITE if i == focus_layer else GRAY,
                                     scene=self)
                    layer_label.next_to(layer_box, UP, buff=0.1 * scale)
                    # DO NOT rotate billboard text - it should always face camera

                    # IMPORTANT: Store individual module positions for dependency arrows
                    # Position modules around the layer's actual 3D position
                    num_modules = min(len(layer_modules), 10)  # Cap for visualization
                    module_spacing = layer_width / (num_modules + 1) if num_modules > 0 else 1.0

                    for j, module_name in enumerate(layer_modules[:num_modules]):
                        # Calculate module position RELATIVE to layer's 3D position
                        x_module_offset = -layer_width/2 + (j + 1) * module_spacing
                        module_pos = np.array([
                            x_layer_pos + x_module_offset,  # Use layer's X position
                            y_layer_pos,                     # Use layer's Y position
                            z_layer_pos                      # Use layer's Z position
                        ])
                        self.module_positions[module_name] = module_pos

                    layer_viz.add(VGroup(layer_box, layer_label))

                # Animate architecture appearing from bottom-right to top-left (following diagonal)
                self.play(
                    *[FadeIn(layer, shift=UP*0.3 + LEFT*0.3, scale=0.7) for layer in layer_viz],
                    run_time=2.5,
                    lag_ratio=0.4
                )

                # Camera movement: Arc around the 3D staircase to show depth
                # Start position already set by set_camera_orientation
                # Move camera to show architecture from different angle
                self.move_camera(
                    phi=70 * DEGREES,   # Slightly steeper to see vertical spread
                    theta=-60 * DEGREES,  # Rotate more to see horizontal spread
                    run_time=2.0
                )
                self.wait(0.5)

                # Return to original viewing angle for transitions
                self.move_camera(
                    phi=60 * DEGREES,
                    theta=-30 * DEGREES,
                    run_time=1.5
                )

                # Return layer_viz for smooth transitions (don't fade out yet)
                # Caller will handle transitions
                return layer_viz

        except Exception as e:
            # Fallback: Simple overview
            overview_text = Text("Entering Execution Trace...", font_size=32, color=GREEN)
            self.add_fixed_in_frame_mobjects(overview_text)
            self.play(Write(overview_text), run_time=1.0)
            self.wait(1)
            self.play(FadeOut(overview_text), run_time=0.5)
            return None

    def visualize_dependencies(self):
        """
        PHASE 2: Visualize module dependencies as flowing connections.
        Overlays on architecture (center, Z=0).
        """
        try:
            from architecture_explainer import ArchitectureExtractor

            # Extract architecture
            extractor = ArchitectureExtractor(self.trace_data)
            arch = extractor.extract()

            subtitle = BillboardText("Module Dependencies", font_size=24, color=BLUE)
            subtitle.to_edge(UP).shift(DOWN * 0.8)
            self.add_fixed_in_frame_mobjects(subtitle)
            self.play(FadeIn(subtitle))

            dependencies = VGroup()
            module_positions = getattr(self, 'module_positions', {})

            # Draw top N dependencies
            all_deps = []
            for module, data in arch['modules'].items():
                for target, count in data['calls_to'].items():
                    if module in module_positions and target in module_positions:
                        all_deps.append((module, target, count))

            # Sort by count and take top 20
            all_deps.sort(key=lambda x: x[2], reverse=True)
            top_deps = all_deps[:20]

            for source, target, count in top_deps:
                start_pos = module_positions[source]
                end_pos = module_positions[target]

                # Thickness based on call count
                thickness = min(count / 10, 5)

                # Curved arrow
                arrow = CubicBezier(
                    start_pos,
                    start_pos + (end_pos - start_pos) * 0.3 + UP * 0.5,
                    end_pos + (start_pos - end_pos) * 0.3 + UP * 0.5,
                    end_pos,
                    color=interpolate_color(BLUE, RED, min(count / 100, 1)),
                    stroke_width=thickness
                )
                arrow.set_opacity(0.6)
                dependencies.add(arrow)

            # Animate dependencies appearing
            if len(dependencies) > 0:
                self.play(*[Create(dep) for dep in dependencies], run_time=2)
                self.wait(1)
                # Don't fade out yet - caller will handle transitions
                self.play(FadeOut(subtitle))
                return dependencies
            else:
                self.play(FadeOut(subtitle))
                return None

        except Exception as e:
            return None  # Skip if architecture not available

    def visualize_anti_patterns(self):
        """
        PHASE 3: Visualize anti-patterns with warnings (RIGHT SIDE, X=+6, Z=-2).
        Camera pans to the right to show these warnings in their own space.
        """
        try:
            from architecture_explainer import ArchitectureExtractor

            # Extract architecture
            extractor = ArchitectureExtractor(self.trace_data)
            arch = extractor.extract()

            if not arch['anti_patterns']:
                return  # No anti-patterns to show

            # Pan camera to the right
            if hasattr(self.camera, 'frame'):
                # ThreeDCamera doesn't have 'frame' attribute, skip camera operations for 3D scenes
                if hasattr(self.camera, 'frame'):
                    try:
                    self.play(
                        self.camera.frame.animate.shift(RIGHT * 6 + OUT * 2),
                        run_time=2
                    )
                    except AttributeError as e:
                        logger.debug(f"Camera operation skipped: {e}")
                else:
                    logger.debug("ThreeDCamera detected, skipping frame operation")

            subtitle = BillboardText("Anti-Patterns Detected!", font_size=28, color=RED)
            subtitle.move_to([6, 3, -2])
            self.add_fixed_in_frame_mobjects(subtitle)
            self.play(Write(subtitle))

            warnings = VGroup()
            y_pos = 1.5

            for anti_pattern in arch['anti_patterns'][:5]:
                # Warning symbol (flashing red triangle)
                warning = RegularPolygon(n=3, color=RED, fill_opacity=0.8)
                warning.scale(0.3)
                warning.move_to(np.array([4, y_pos, -2]))

                # Issue description
                issue_type = anti_pattern.get('type', 'unknown')
                severity = anti_pattern.get('severity', 'medium')

                if issue_type == 'circular_dependency':
                    modules = anti_pattern.get('modules', [])
                    desc = f"Circular: {modules[0][:15]} <-> {modules[1][:15]}"
                elif issue_type == 'god_module':
                    module = anti_pattern.get('module', '')
                    num_deps = anti_pattern.get('num_dependencies', 0)
                    desc = f"God Module: {module[:20]} ({num_deps} deps)"
                else:
                    desc = issue_type[:30]

                issue_label = BillboardText(desc, font_size=12, color=RED)
                issue_label.move_to(np.array([6, y_pos, -2]))

                # Severity indicator
                severity_colors = {'high': RED, 'medium': ORANGE, 'low': YELLOW}
                severity_label = BillboardText(
                    severity.upper(),
                    font_size=10,
                    color=severity_colors.get(severity, YELLOW)
                )
                severity_label.move_to(np.array([8, y_pos, -2]))

                warnings.add(warning, issue_label, severity_label)

                self.play(
                    SpinInFromNothing(warning),
                    FadeIn(issue_label),
                    FadeIn(severity_label),
                    run_time=0.4
                )

                # Flash warning
                self.play(
                    warning.animate(rate_func=there_and_back).scale(1.3),
                    run_time=0.3
                )

                y_pos -= 0.8

            self.wait(1)
            self.play(FadeOut(warnings), FadeOut(subtitle))

            # Pan camera back to center
            if hasattr(self.camera, 'frame'):
                # ThreeDCamera doesn't have 'frame' attribute, skip camera operations for 3D scenes
                if hasattr(self.camera, 'frame'):
                    try:
                    self.play(
                        self.camera.frame.animate.shift(LEFT * 6 + IN * 2),
                        run_time=2
                    )
                    except AttributeError as e:
                        logger.debug(f"Camera operation skipped: {e}")
                else:
                    logger.debug("ThreeDCamera detected, skipping frame operation")

        except Exception as e:
            logger.error(f"Failed to extract architecture: {e}", exc_info=True)

    def show_recommendations(self):
        """
        PHASE 4: Show architectural recommendations (LEFT SIDE, X=-6, Z=-2).
        Camera pans to the left to show these suggestions in their own space.
        """
        try:
            from architecture_explainer import ArchitectureExtractor

            # Extract architecture
            extractor = ArchitectureExtractor(self.trace_data)
            arch = extractor.extract()

            # Pan camera to the left
            if hasattr(self.camera, 'frame'):
                # ThreeDCamera doesn't have 'frame' attribute, skip camera operations for 3D scenes
                if hasattr(self.camera, 'frame'):
                    try:
                    self.play(
                        self.camera.frame.animate.shift(LEFT * 6 + OUT * 2),
                        run_time=2
                    )
                    except AttributeError as e:
                        logger.debug(f"Camera operation skipped: {e}")
                else:
                    logger.debug("ThreeDCamera detected, skipping frame operation")

            subtitle = BillboardText("Recommendations", font_size=28, color=GREEN)
            subtitle.move_to([-6, 3, -2])
            self.add_fixed_in_frame_mobjects(subtitle)
            self.play(Write(subtitle))

            recommendations = VGroup()
            y_pos = 1.5

            # Generate recommendations from anti-patterns
            for anti_pattern in arch['anti_patterns'][:4]:
                recommendation = anti_pattern.get('recommendation', '')

                if recommendation:
                    # Checkmark
                    check = BillboardText("✓", font_size=20, color=GREEN)
                    check.move_to(np.array([-8, y_pos, -2]))

                    # Recommendation text
                    rec_label = BillboardText(recommendation[:50], font_size=11, color=WHITE)
                    rec_label.move_to(np.array([-5, y_pos, -2]))

                    recommendations.add(check, rec_label)

                    self.play(
                        FadeIn(check),
                        FadeIn(rec_label),
                        run_time=0.3
                    )

                    y_pos -= 0.7

            # General recommendations
            general_recs = [
                "Consider reducing inter-module coupling",
                "Group related modules into components",
                "Add clear layer boundaries"
            ]

            for rec_text in general_recs:
                check = BillboardText("•", font_size=20, color=BLUE)
                check.move_to(np.array([-8, y_pos, -2]))

                rec_label = BillboardText(rec_text, font_size=11, color=WHITE)
                rec_label.move_to(np.array([-5, y_pos, -2]))

                recommendations.add(check, rec_label)

                self.play(
                    FadeIn(check),
                    FadeIn(rec_label),
                    run_time=0.3
                )

                y_pos -= 0.7

            self.wait(2)
            # Don't fade out yet - caller will handle transitions
            self.play(FadeOut(subtitle))

            # Pan camera back to center
            if hasattr(self.camera, 'frame'):
                # ThreeDCamera doesn't have 'frame' attribute, skip camera operations for 3D scenes
                if hasattr(self.camera, 'frame'):
                    try:
                    self.play(
                        self.camera.frame.animate.shift(RIGHT * 6 + IN * 2),
                        run_time=2
                    )
                    except AttributeError as e:
                        logger.debug(f"Camera operation skipped: {e}")
                else:
                    logger.debug("ThreeDCamera detected, skipping frame operation")

            return recommendations

        except Exception as e:
            return None  # Skip if architecture not available

    def extract_main_path(self) -> List[Dict]:
        """
        Extract complete execution path with call/return pairs.
        Returns list of events including both 'call' and 'return' events to show full flow.

        FILTERS OUT BOILERPLATE:
        - Getters/setters (get_*, set_*, __get*, __set*)
        - Properties (@property)
        - Logging/context noise (format, get_request_id, context_logger calls)
        - Magic methods (__init__, __repr__, __str__, __len__, etc.)
        - Trivial utilities (to_dict, from_dict, validate, check_*)
        """
        calls = self.trace_data.get('calls', [])

        # Boilerplate patterns to EXCLUDE
        boilerplate_patterns = [
            # Getters/setters
            'get_', 'set_', '__get', '__set',
            # Properties
            '@property', 'property',
            # Magic/dunder methods (except compute-heavy ones like __matmul__, __call__)
            '__init__', '__repr__', '__str__', '__len__', '__contains__',
            '__iter__', '__next__', '__enter__', '__exit__', '__del__',
            # Logging/context
            'format', 'get_request_id', 'get_execution_path', 'get_api_source',
            'get_input_source', 'set_api_source', 'set_input_source',
            'log', 'debug', 'info', 'warning', 'error', 'critical',
            # Trivial utilities
            'to_dict', 'from_dict', 'validate', 'check_',
        ]

        # Boilerplate modules to EXCLUDE entirely
        boilerplate_modules = [
            'context_logger', 'logging', 'logger', 'traceback'
        ]

        # Build complete event sequence (calls and returns)
        events = []
        call_stack = []

        for event in calls:
            event_type = event.get('type')

            # BOILERPLATE FILTERING (for 'call' events)
            if event_type == 'call':
                func_name = event.get('function', '').lower()
                module = event.get('module', '').lower()

                # Skip if matches boilerplate pattern
                is_boilerplate = any(pattern in func_name for pattern in boilerplate_patterns)

                # Skip if module is pure boilerplate
                is_boilerplate_module = any(bm in module for bm in boilerplate_modules)

                if is_boilerplate or is_boilerplate_module:
                    continue  # SKIP this event

                events.append(event)
                call_stack.append(event)

            elif event_type == 'return':
                # Match with corresponding call
                call_id = event.get('call_id')
                # Find the call event
                matching_call = next((e for e in reversed(call_stack) if e.get('call_id') == call_id), None)
                if matching_call:
                    # Add return event with reference to call
                    return_event = event.copy()
                    return_event['matching_call'] = matching_call
                    events.append(return_event)
                    call_stack.remove(matching_call)

        # In simplified mode, limit to main path
        if self.simplified_mode:
            # Take only top-level calls and their immediate children
            max_depth = 2
            events = [e for e in events if e.get('depth', 0) <= max_depth]

        # Limit total events
        max_events = 20
        if len(events) > max_events:
            indices = np.linspace(0, len(events) - 1, max_events, dtype=int)
            events = [events[i] for i in indices]

        return events

    def _analyze_operation(self, call: Dict) -> Dict:
        """
        Dynamically analyze ANY operation comprehensively.

        Returns detailed metadata for creating perfect human-quality animations.

        ENHANCED: Uses OperationDetector for better pattern matching if available.
        """
        func = call.get('function', 'unknown')
        module = call.get('module', '')

        # === ENHANCEMENT: Use OperationDetector if available ===
        op_type = None
        dimensions = None
        if self.op_detector and SPECIALIZED_VIZ_AVAILABLE:
            try:
                op_type = OperationDetector.detect_operation_type(call)
                dimensions = OperationDetector.extract_dimensions(call)
            except Exception as e:
                # Fallback to local detection
                logger.warning(f"OperationDetector failed, using local detection: {e}", exc_info=True)

        metadata = {
            'function': func,
            'module': module,
            'category': self._infer_category(func, module, op_type),  # Enhanced
            'transformation_type': self._infer_transformation(func),
            'visualization_style': None,
            'color_scheme': None,
            'explanation': '',
            'micro_anim_type': None,
            'op_type': op_type,  # NEW: from OperationDetector
            'dimensions': dimensions  # NEW: tensor dimensions
        }

        metadata['visualization_style'] = self._suggest_visualization(metadata['category'])
        metadata['color_scheme'] = self._get_color_scheme(metadata['category'])
        metadata['explanation'] = self._generate_explanation(metadata)
        metadata['micro_anim_type'] = self._get_micro_animation_type(metadata['category'])

        return metadata

    def _infer_category(self, func: str, module: str, op_type: str = None) -> str:
        """
        Dynamically infer category from naming patterns.

        ENHANCED: Uses op_type from OperationDetector if available.
        """
        # === ENHANCEMENT: Use OperationDetector result if available ===
        if op_type:
            # Map op_type to category
            op_type_map = {
                'neural_layer': 'encoding',
                'attention': 'attention',
                'matrix_multiply': 'linear',
                'convolution': 'convolution',
                'batch_norm': 'normalization',
                'pooling': 'pooling',
                'activation': 'activation',
                'reshape': 'reshape',
                'split': 'split',
                'merge': 'merge',
                'broadcast': 'arithmetic',
                'async': 'generic',
                'method_call': 'generic'
            }
            if op_type in op_type_map:
                return op_type_map[op_type]

        # === FALLBACK: Local pattern matching ===
        text = f"{func} {module}".lower()

        if any(x in text for x in ['encode', 'embed', 'encoder']):
            return 'encoding'
        if any(x in text for x in ['decode', 'decoder', 'generate']):
            return 'decoding'
        if any(x in text for x in ['attention', 'attn']):
            return 'attention'
        if any(x in text for x in ['conv', 'convolution']):
            return 'convolution'
        if any(x in text for x in ['pool', 'pooling']):
            return 'pooling'
        if any(x in text for x in ['norm', 'normalize']):
            return 'normalization'
        if any(x in text for x in ['linear', 'dense', 'fc', 'proj']):
            return 'linear'
        if any(x in text for x in ['relu', 'gelu', 'sigmoid', 'tanh', 'softmax']):
            return 'activation'
        if any(x in text for x in ['reshape', 'view', 'transpose', 'permute']):
            return 'reshape'
        if any(x in text for x in ['split', 'chunk']):
            return 'split'
        if any(x in text for x in ['concat', 'cat', 'stack']):
            return 'merge'
        if any(x in text for x in ['add', 'sub', 'mul', 'div', 'matmul']):
            return 'arithmetic'

        return 'generic'

    def _infer_transformation(self, func: str) -> str:
        """Infer transformation type."""
        fl = func.lower()
        if any(x in fl for x in ['reshape', 'view', 'transpose']):
            return 'shape_change'
        if any(x in fl for x in ['add', 'mul', 'matmul']):
            return 'arithmetic'
        if any(x in fl for x in ['concat', 'stack']):
            return 'merge'
        if any(x in fl for x in ['split', 'chunk']):
            return 'split'
        return 'computation'

    def _suggest_visualization(self, category: str) -> str:
        """Suggest visualization based on category."""
        viz_map = {
            'attention': 'attention_heatmap',
            'convolution': 'sliding_kernel',
            'linear': 'matrix_multiply',
            'reshape': 'morphing',
            'split': 'branching',
            'merge': 'converging',
            'arithmetic': 'computation_box'
        }
        return viz_map.get(category, 'generic_box')

    def _get_color_scheme(self, category: str) -> Dict:
        """Color scheme per category."""
        schemes = {
            'encoding': {'primary': BLUE, 'accent': TEAL},
            'decoding': {'primary': GREEN, 'accent': YELLOW},
            'attention': {'primary': PURPLE, 'accent': PINK},
            'convolution': {'primary': RED, 'accent': ORANGE},
            'linear': {'primary': BLUE, 'accent': TEAL},
            'activation': {'primary': YELLOW, 'accent': GOLD},
            'pooling': {'primary': ORANGE, 'accent': RED},
            'normalization': {'primary': GREEN, 'accent': TEAL},
            'reshape': {'primary': PURPLE, 'accent': BLUE},
            'split': {'primary': ORANGE, 'accent': YELLOW},
            'merge': {'primary': GREEN, 'accent': BLUE},
            'arithmetic': {'primary': YELLOW, 'accent': ORANGE},
            'generic': {'primary': GRAY, 'accent': WHITE}
        }
        return schemes.get(category, {'primary': WHITE, 'accent': GRAY})

    def _generate_explanation(self, metadata: Dict) -> str:
        """Human-readable explanation."""
        category = metadata['category']
        func = metadata['function']

        explanations = {
            'encoding': f'Transforms input into latent representation',
            'decoding': f'Generates output from latent state',
            'attention': f'Computes attention to focus on relevant features',
            'convolution': f'Extracts spatial patterns via convolution',
            'linear': f'Linear transformation: W * x + b',
            'activation': f'Non-linear activation: {func}(x)',
            'reshape': f'Reshapes tensor dimensions',
            'split': f'Splits into parallel branches',
            'merge': f'Merges parallel streams',
            'arithmetic': f'Computes {func}',
            'generic': f'Executes {func}'
        }
        return explanations.get(category, f'Calls {func}')

    def _get_micro_animation_type(self, category: str) -> str:
        """Micro-animation style per category."""
        anim_map = {
            'attention': 'pulse_glow',
            'linear': 'shimmer_sweep',
            'convolution': 'kernel_slide',
            'activation': 'wave_ripple',
            'encoding': 'spiral_compress',
            'decoding': 'spiral_expand',
            'reshape': 'morph_flow',
            'split': 'diverge_particle',
            'merge': 'converge_particle'
        }
        return anim_map.get(category, 'gentle_pulse')

    def visualize_data_journey(self, path: List[Dict]):
        """
        ENHANCED: Complete source-to-sink visualization with FULL execution details.

        Features:
        - Function calls with parameters (names, types, values, shapes)
        - Layer internals (input → operations → output)
        - Tensor shapes at each step
        - Return values
        - Seamless stitching between all operations
        - Call stack visualization
        - Performance stats overlay with real-time updates
        - Data-centered FIFA camera (data always in center)
        - 3D depth separation with proper spacing
        - TIME-BOXING: Limits max events to prevent overwhelming videos
        """
        # ENHANCEMENT: Time-boxing to prevent overwhelming videos
        # Max 100 events per visualization (configurable)
        MAX_EVENTS = 100
        original_path_len = len(path)

        if len(path) > MAX_EVENTS:
            # Sample events intelligently:
            # - Keep first 20 (entry points)
            # - Sample middle events
            # - Keep last 20 (exit/return points)
            sampled_path = []
            sampled_path.extend(path[:20])  # First 20

            # Sample middle (every Nth event)
            middle_section = path[20:-20]
            sample_rate = max(1, len(middle_section) // (MAX_EVENTS - 40))
            sampled_path.extend(middle_section[::sample_rate])

            sampled_path.extend(path[-20:])  # Last 20

            path = sampled_path
            logger.info(f"Time-boxing: Sampled {len(path)} events from {original_path_len} (MAX={MAX_EVENTS})")

        # Track Y position per depth level for proper spacing
        depth_y_positions = {}  # {depth: current_y_for_that_depth}
        all_objects = []
        active_calls = {}  # Track active function calls
        call_stack_viz = VGroup()  # Visual call stack on the side
        prev_output = None  # Previous operation's output for seamless stitching
        data_object = None  # Current data being processed (for camera tracking)

        # Create call stack display area
        stack_title = BillboardText("Call Stack", font_size=14, color=BLUE)
        stack_title.to_edge(LEFT).shift(UP*2.5)
        call_stack_viz.add(stack_title)
        self.add_fixed_in_frame_mobjects(stack_title)

        # Create performance stats overlay
        perf_stats = self._create_performance_overlay()
        self.add_fixed_in_frame_mobjects(perf_stats)

        for i, event in enumerate(path):
            event_type = event.get('type', 'call')

            if event_type == 'call':
                # FUNCTION CALL - Show complete entry
                func_name = event.get('function', 'unknown')
                module = event.get('module', '')
                call_id = event.get('call_id', '')
                depth = event.get('depth', 0)

                # ENHANCEMENT: Update performance overlay in real-time
                self._update_performance_overlay(i, depth)

                # Analyze operation
                metadata = self._analyze_operation(event)

                # Initialize Y position for this depth level if not exists
                if depth not in depth_y_positions:
                    depth_y_positions[depth] = 3 - (depth * 0.5)  # Start higher for deeper levels

                # Get current Y for this depth level
                current_y_for_depth = depth_y_positions[depth]

                # LANDSCAPE LEFT-TO-RIGHT FLOW
                # X: PRIMARY axis - data flows LEFT to RIGHT (execution sequence)
                # Y: Depth of call stack (nested calls go DOWN)
                # Z: Parallel branches spread in depth (into/out of screen)

                # X position: sequence counter (increases left to right)
                x_pos = i * 1.8  # Execution sequence flows left to right

                # Y position: call depth (deeper calls go down)
                y_pos = -depth * 1.5  # Nested calls lower

                # Z position: spread parallel branches at same depth
                z_pos = current_y_for_depth * 0.5  # Use old Y tracking for Z spread

                position = np.array([x_pos, y_pos, z_pos])

                # Create function entry box
                entry_box = self._create_function_entry(
                    func_name, module, event, metadata, position
                )
                all_objects.append(entry_box)
                active_calls[call_id] = {
                    'viz': entry_box,
                    'position': position,
                    'metadata': metadata,
                    'event': event
                }

                # Update call stack visualization
                stack_item = Text(f"{func_name}", font_size=10, color=WHITE)
                stack_item.next_to(call_stack_viz, DOWN, aligned_edge=LEFT, buff=0.1)
                call_stack_viz.add(stack_item)
                self.add_fixed_in_frame_mobjects(stack_item)

                # Camera tracking: Follow data LEFT to RIGHT (X-axis)
                # Smooth 3Blue1Brown style pan to keep current function centered
                if hasattr(self.camera, 'frame'):
                    try:
                        # ThreeDCamera doesn't have 'frame' attribute, skip camera operations for 3D scenes
                        if hasattr(self.camera, 'frame'):
                            try:
                            self.play(
                                self.camera.frame.animate.move_to(position),
                                run_time=0.8,  # Slower, more deliberate
                                rate_func=rate_functions.ease_in_out_cubic  # Smooth acceleration/deceleration
                            )
                            except AttributeError as e:
                                logger.debug(f"Camera operation skipped: {e}")
                        else:
                            logger.debug("ThreeDCamera detected, skipping frame operation")
                    except AttributeError as e:
                        # Fallback if frame exists but operation fails
                        logger.debug(f"Camera tracking failed: {e}")
                else:
                    logger.debug("ThreeDCamera detected, skipping camera tracking")

                # Animate function entry
                self.play(
                    FadeIn(entry_box, shift=RIGHT*0.3, scale=0.8),
                    run_time=0.4
                )

                # Show parameters flowing IN
                param_viz = self._visualize_parameters(event, position)
                if param_viz:
                    self.play(FadeIn(param_viz, shift=DOWN*0.2), run_time=0.3)
                    all_objects.append(param_viz)

                    # Show data flow from previous output (seamless stitching)
                    if prev_output:
                        # Determine data type from metadata for specialized particle visualization
                        data_type = 'tensor'  # default
                        if metadata.get('dimensions'):
                            data_type = 'tensor'
                        elif metadata.get('op_type') in ['activation', 'scalar']:
                            data_type = 'scalar'
                        elif metadata.get('op_type') in ['gradient', 'backward']:
                            data_type = 'gradient'

                        self._animate_seamless_stitch(
                            prev_output, param_viz,
                            metadata['color_scheme']['accent'],
                            data_type=data_type
                        )

                # Perform internal operations
                operation_viz = self._create_operation_visualization(metadata, position + DOWN*0.8)
                all_objects.append(operation_viz.mobject)

                self.play(FadeIn(operation_viz.mobject, scale=0.7), run_time=0.3)

                # Micro-animation showing what happens inside
                self._animate_micro_transformation(operation_viz.mobject, metadata)

                # Store for seamless connection to next operation
                active_calls[call_id]['operation_viz'] = operation_viz.mobject

                # Update Y position for this depth level (move down for next call at same depth)
                depth_y_positions[depth] = current_y_for_depth - 1.5

            elif event_type == 'return':
                # FUNCTION RETURN - Show output and complete the flow
                call_id = event.get('call_id', '')
                matching_call = event.get('matching_call')

                if call_id in active_calls:
                    call_info = active_calls[call_id]
                    position = call_info['position']

                    # Create return value visualization
                    return_viz = self._visualize_return_value(
                        event, position + DOWN*1.5
                    )

                    if return_viz:
                        all_objects.append(return_viz)

                        # Animate data flowing OUT
                        if 'operation_viz' in call_info:
                            self._animate_data_flow_particles(
                                call_info['operation_viz'].get_center(),
                                return_viz.get_center(),
                                GREEN
                            )

                        self.play(FadeIn(return_viz, shift=UP*0.2), run_time=0.3)

                        # This becomes input for next operation (seamless stitching)
                        prev_output = return_viz

                    # Mark function as complete
                    self.play(
                        call_info['viz'].animate.set_color(GREEN).set_opacity(0.5),
                        run_time=0.2
                    )

                    # Remove from call stack visualization
                    if len(call_stack_viz) > 1:
                        last_item = call_stack_viz[-1]
                        call_stack_viz.remove(last_item)
                        self.play(FadeOut(last_item), run_time=0.2)

                    del active_calls[call_id]

            # Prevent screen from getting too crowded
            if i > 3 and i < len(path) - 2:
                # Fade older objects
                fade_idx = max(0, i - 4)
                if fade_idx < len(all_objects):
                    self.play(
                        all_objects[fade_idx].animate.set_opacity(0.15),
                        run_time=0.1
                    )

        # Final overview - show complete flow
        self.play(
            *[obj.animate.set_opacity(0.4) for obj in all_objects],
            run_time=0.5
        )

        # Highlight the complete data flow path
        if len(all_objects) > 0:
            self.play(
                all_objects[0].animate.set_color(BLUE).set_opacity(1),  # Entry
                all_objects[-1].animate.set_color(GREEN).set_opacity(1),  # Exit
                run_time=0.8
            )

        self.wait(2)

    def _create_function_entry(self, func_name: str, module: str, event: Dict,
                               metadata: Dict, position: np.ndarray) -> Mobject:
        """
        ENHANCED: Create specialized function entry visualization based on operation type.

        Uses OperationVisualizer for specialized visualizations when op_type is detected:
        - neural_layer: Grid with dimensions
        - attention: Multi-head attention mechanism
        - matrix_multiply: Matrix multiplication diagram
        - convolution: Convolutional operation
        - generic/unknown: Standard function box
        """
        colors = metadata['color_scheme']
        op_type = metadata.get('op_type', None)
        dimensions = metadata.get('dimensions', None)

        # === ENHANCEMENT: Use specialized visualizers based on op_type ===
        if self.op_visualizer and SPECIALIZED_VIZ_AVAILABLE and op_type:
            try:
                if op_type == 'neural_layer':
                    # Create neural layer visualization with dimension grids
                    viz = self.op_visualizer.create_neural_layer_viz(event, position, dimensions)
                    return viz

                elif op_type == 'attention':
                    # Create attention mechanism visualization
                    viz = self.op_visualizer.create_attention_viz(event, position)
                    return viz

                elif op_type == 'matrix_multiply':
                    # Create matrix multiply visualization
                    viz = self.op_visualizer.create_matrix_multiply_viz(event, position)
                    return viz

                elif op_type in ['reshape', 'transpose', 'permute']:
                    # Create array reshape visualization
                    viz = self.op_visualizer.create_array_reshape_viz(event, position, dimensions)
                    return viz

                elif op_type == 'convolution' and self.extended_visualizer:
                    # Use extended visualizer for convolution
                    viz = self.extended_visualizer.create_convolution_viz(event, position)
                    return viz

                else:
                    # Use method call visualization for other types
                    viz = self.op_visualizer.create_method_call_viz(event, position)
                    return viz
            except Exception as e:
                # Fallback to standard box on any error
                logger.warning(f"Specialized viz failed for {op_type}, using standard box: {e}", exc_info=True)

        # === FALLBACK: Standard function box ===
        box = RoundedRectangle(
            width=2.5, height=0.6,
            corner_radius=0.1,
            fill_color=colors['primary'],
            fill_opacity=0.3,
            stroke_color=colors['accent'],
            stroke_width=2
        )

        # Function name
        name_text = BillboardText(func_name[:20], font_size=14, color=WHITE)

        # Module name (smaller)
        module_text = BillboardText(module[:15], font_size=8, color=GRAY)
        module_text.next_to(name_text, DOWN, buff=0.05)

        # Entry arrow
        entry_arrow = Arrow(LEFT*0.3, ORIGIN, color=colors['accent'], stroke_width=3)
        entry_arrow.next_to(box, LEFT, buff=0.1)

        # Combine
        group = VGroup(box, name_text, module_text, entry_arrow)
        group.move_to(position)

        return group

    def _visualize_parameters(self, event: Dict, position: np.ndarray) -> Optional[Mobject]:
        """
        Visualize function parameters with names, types, and shapes.
        Shows actual tensor dimensions if available.
        """
        params_group = VGroup()

        # Extract parameters from event (if available in trace)
        params = event.get('params', [])
        args_repr = event.get('args_repr', '')

        if params or args_repr:
            # Show actual parameter info
            if isinstance(params, list) and len(params) > 0:
                # Show first 2 params with types
                for i, param in enumerate(params[:2]):
                    if isinstance(param, dict):
                        param_name = param.get('name', f'arg{i}')
                        param_type = param.get('type', 'unknown')
                        param_shape = param.get('shape', None)

                        if param_shape:
                            label_text = f"{param_name}: {param_type}{param_shape}"
                        else:
                            label_text = f"{param_name}: {param_type}"
                    else:
                        label_text = f"arg{i}: {str(param)[:15]}"

                    param_label = BillboardText(label_text, font_size=9, color=YELLOW)
                    param_label.move_to(position + DOWN*(0.3 + i*0.15))
                    params_group.add(param_label)
            elif args_repr:
                # Show args_repr (truncated)
                param_label = BillboardText(f"({args_repr[:30]})", font_size=9, color=YELLOW)
                param_label.move_to(position + DOWN*0.3)
                params_group.add(param_label)

        if len(params_group) == 0:
            # Fallback: Show generic parameter indicator
            param_label = BillboardText("params", font_size=10, color=YELLOW)
            param_box = RoundedRectangle(
                width=0.8, height=0.3,
                corner_radius=0.05,
                stroke_color=YELLOW,
                fill_opacity=0.2
            )
            params_group.add(VGroup(param_box, param_label))

        params_group.move_to(position + DOWN*0.4)
        return params_group

    def _visualize_return_value(self, event: Dict, position: np.ndarray) -> Optional[Mobject]:
        """
        Visualize return value with type and shape information.
        """
        ret_group = VGroup()

        # Extract return value info from event
        ret_val = event.get('return_value', None)
        ret_type = event.get('return_type', '')
        ret_shape = event.get('return_shape', None)
        ret_repr = event.get('return_repr', '')

        if ret_type or ret_shape or ret_repr:
            # Show actual return info
            if ret_shape:
                label_text = f"→ {ret_type}{ret_shape}"
            elif ret_type:
                label_text = f"→ {ret_type}"
            elif ret_repr:
                label_text = f"→ {ret_repr[:20]}"
            else:
                label_text = "→ return"

            ret_label = BillboardText(label_text, font_size=10, color=GREEN)
            ret_group.add(ret_label)
        else:
            # Fallback: Generic return indicator
            ret_box = RoundedRectangle(
                width=1.0, height=0.4,
                corner_radius=0.05,
                stroke_color=GREEN,
                fill_color=GREEN,
                fill_opacity=0.2
            )
            ret_label = BillboardText("return", font_size=10, color=GREEN)
            ret_group.add(VGroup(ret_box, ret_label))

        ret_group.move_to(position)
        return ret_group

    def _animate_seamless_stitch(self, source: Mobject, dest: Mobject, color, data_type: str = 'tensor'):
        """
        Seamlessly connect output of one operation to input of next in TRUE 3D.
        Shows data flowing naturally without hickups through 3D space.
        Uses Arrow3D for proper 3D depth connections.

        ENHANCED: Uses DataFlowParticles with data-type-specific shapes if available.
        """
        # Create smooth flowing connector
        start = source.get_center()
        end = dest.get_center()

        # === ENHANCEMENT: Try DataFlowParticles first ===
        if self.data_flow_particles and PARTICLE_FLOW_AVAILABLE:
            try:
                # Use advanced particle flow with trails and data-type shapes
                particles = self.data_flow_particles.create_particle_flow(
                    start, end,
                    num_particles=5,
                    data_type=data_type,
                    show_trails=True
                )

                # Add particles to scene
                self.add(particles)

                # Animate particles flowing
                anim = self.data_flow_particles.animate_particle_stream(
                    particles, start, end,
                    run_time=AnimationTiming.DATA_FLOW_SHORT,
                    show_trails=True
                )
                self.play(anim)
                self.play(FadeOut(particles), run_time=0.2)
                return  # Success!
            except Exception as e:
                # Fallback to existing arrow + particles
                logger.warning(f"Particle flow failed, using arrow fallback: {e}", exc_info=True)

        # === FALLBACK: Existing 3D arrow + particle implementation ===
        # Create 3D arrow showing data flow direction
        arrow_3d = Arrow3D(
            start=start,
            end=end,
            color=color,
            thickness=0.02,
            height=0.15,
            base_radius=0.04
        )

        # Animate arrow appearing with particles
        self.play(
            Create(arrow_3d),
            run_time=0.3
        )

        # Bezier curve for particle flow (follows 3D path)
        # Calculate control points for smooth 3D curve
        mid_point = (start + end) / 2
        # Arc upward slightly for visibility
        control1 = start + (UP * 0.2)
        control2 = end + (UP * 0.2)

        path = CubicBezier(start, control1, control2, end)

        # 3D particles flowing along path
        particles = VGroup()
        for i in range(3):
            particle = Sphere(radius=0.05, color=color, resolution=(6, 6))
            particle.move_to(start)
            particles.add(particle)

        self.play(
            *[MoveAlongPath(p, path) for p in particles],
            run_time=0.5,
            rate_func=rate_functions.ease_in_out_sine,
            lag_ratio=0.3
        )

        self.play(
            *[FadeOut(p, scale=0.3) for p in particles],
            FadeOut(arrow_3d),
            run_time=0.2
        )

    def _create_operation_visualization(self, metadata: Dict, position: np.ndarray) -> DataVisualization:
        """Create visualization for ANY operation based on metadata."""
        category = metadata['category']
        colors = metadata['color_scheme']
        func = metadata['function']

        # Create geometric shape based on category
        if category in ['encoding', 'decoding']:
            # Encoder/Decoder: Layered cubes showing compression/expansion
            cubes = VGroup()
            for i in range(3):
                size = 0.5 - i*0.1 if category == 'encoding' else 0.3 + i*0.1
                cube = Cube(side_length=size, fill_color=colors['primary'], fill_opacity=0.7)
                cube.shift(OUT * i * 0.15)
                cubes.add(cube)
            shape = cubes

        elif category == 'attention':
            # Attention: Grid showing attention mechanism
            grid = VGroup()
            for i in range(4):
                for j in range(4):
                    cell = Square(side_length=0.15, fill_color=colors['primary'], fill_opacity=0.6)
                    cell.move_to([i*0.18 - 0.27, j*0.18 - 0.27, 0])
                    grid.add(cell)
            shape = grid

        elif category == 'linear':
            # Linear: Matrix structure
            matrix = VGroup(
                Rectangle(width=1.2, height=0.8, fill_color=colors['primary'], fill_opacity=0.5),
                BillboardText("W", font_size=20, color=WHITE, scene=self).shift(LEFT*0.3),
                BillboardText("×", font_size=16, color=WHITE, scene=self),
                BillboardText("x", font_size=20, color=WHITE, scene=self).shift(RIGHT*0.3)
            ).arrange(RIGHT, buff=0.15)
            shape = matrix

        elif category == 'convolution':
            # Convolution: Sliding kernel visualization
            base = Rectangle(width=1.5, height=1.5, fill_color=colors['accent'], fill_opacity=0.3)
            kernel = Rectangle(width=0.5, height=0.5, fill_color=colors['primary'], fill_opacity=0.8)
            kernel.shift(LEFT*0.5 + UP*0.5)
            shape = VGroup(base, kernel)

        elif category in ['split', 'merge']:
            # Split/Merge: Branching arrows
            if category == 'split':
                arrows = VGroup(
                    Arrow(ORIGIN, UP*0.5 + LEFT*0.3, color=colors['primary']),
                    Arrow(ORIGIN, UP*0.5, color=colors['primary']),
                    Arrow(ORIGIN, UP*0.5 + RIGHT*0.3, color=colors['primary'])
                )
            else:
                arrows = VGroup(
                    Arrow(DOWN*0.5 + LEFT*0.3, ORIGIN, color=colors['primary']),
                    Arrow(DOWN*0.5, ORIGIN, color=colors['primary']),
                    Arrow(DOWN*0.5 + RIGHT*0.3, ORIGIN, color=colors['primary'])
                )
            shape = arrows

        elif category == 'activation':
            # Activation: Wave/curve showing non-linearity
            axes = Axes(x_range=[-1, 1, 0.5], y_range=[-1, 1, 0.5], x_length=1, y_length=1)
            # Sigmoid/ReLU/etc curve
            curve = axes.plot(lambda x: np.tanh(x*2), color=colors['primary'])
            shape = VGroup(axes, curve).scale(0.6)

        else:
            # Generic: Simple cube with label
            cube = Cube(side_length=0.6, fill_color=colors['primary'], fill_opacity=0.7)
            shape = cube

        # Add function label
        label = BillboardText(func[:25], font_size=13, color=WHITE, scene=self)
        label.next_to(shape, UP, buff=0.2)
        label.rotate(PI/2, axis=RIGHT)

        # Combine shape and label
        combined = VGroup(shape, label)
        combined.move_to(position)

        return DataVisualization(
            data_type=category,
            shape=DataShape.FUNCTION_ROUNDED_BOX,
            mobject=combined,
            metadata=metadata
        )

    def _animate_data_flow_particles(self, start_pos: np.ndarray, end_pos: np.ndarray, color):
        """Beautiful particle flow animation showing data moving between operations."""
        # Create multiple particles for rich visual
        particles = VGroup()
        for i in range(5):
            particle = Dot(radius=0.05, color=color)
            particle.move_to(start_pos)
            particle.set_opacity(0.8)
            particles.add(particle)

        # Animate particles flowing along path with stagger
        animations = []
        for i, particle in enumerate(particles):
            animations.append(
                particle.animate.move_to(end_pos)
            )

        self.play(
            *animations,
            run_time=0.6,
            rate_func=rate_functions.ease_in_out_sine,
            lag_ratio=0.2  # Stagger the particles
        )

        # Particles merge/disappear at destination
        self.play(
            *[FadeOut(p, scale=0.5) for p in particles],
            run_time=0.2
        )

    def _animate_micro_transformation(self, mobject: Mobject, metadata: Dict):
        """
        COMPREHENSIVE micro-animations for ALL operations.

        Priority:
        1. Try comprehensive library (matmul, transpose, softmax, pooling, etc.)
        2. Fall back to existing category-specific animations
        3. Generic pulse for unknown operations

        Shows:
        - Tensor operations (matmul row×column, transpose flip, reshape morph)
        - Element-wise ops (add, mul, div with visual pairing)
        - Reductions (sum, mean, max with aggregation)
        - Broadcasting (dimension expansion)
        - Neural ops (convolution sliding, attention Q·K·V, pooling)
        - Method calls (params in → execute → result out)
        """
        center = mobject.get_center()
        func_name = metadata.get('function', '').lower()

        # Try comprehensive library first (if available)
        if COMPREHENSIVE_ANIMS_AVAILABLE:
            try:
                animator = ComprehensiveMicroAnimator(self)

                # Build comprehensive metadata from function name and existing metadata
                comp_metadata = {
                    'operation': func_name,
                    'function': metadata.get('function', ''),
                    'shapes': metadata.get('shapes', [(3, 4)]),
                    'type': 'method_call' if metadata.get('category') == 'utility' else 'operation',
                    'num_params': metadata.get('num_params', 0),
                    'has_return': True,
                }

                # Try to animate with comprehensive library
                animator.animate_operation(center, comp_metadata)
                return  # Success - animation done!

            except Exception as e:
                # Log error and fall back to existing animations
                logger.warning(f"Micro-animation failed for {func_name}: {e}", exc_info=True)
                # Continue to fallback animations below

        # Existing category-based animations (FALLBACK)
        anim_type = metadata['micro_anim_type']

        if anim_type == 'pulse_glow':
            # Attention: Show ACTUAL Q·K^T → softmax → weights·V mechanism
            center = mobject.get_center()
            
            # Create Q, K, V vectors (small spheres)
            q = Sphere(radius=0.08, color=BLUE, resolution=(6, 6)).shift(center + LEFT*0.4)
            k = Sphere(radius=0.08, color=GREEN, resolution=(6, 6)).shift(center)
            v = Sphere(radius=0.08, color=RED, resolution=(6, 6)).shift(center + RIGHT*0.4)
            
            # Show Q, K, V
            self.play(FadeIn(VGroup(q, k, v)), run_time=0.15)
            
            # Show Q·K^T (dot product line)
            attention_line = Line(q.get_center(), k.get_center(), color=YELLOW, stroke_width=4)
            self.play(Create(attention_line), run_time=0.15)
            
            # Show softmax (glow/highlight)
            self.play(attention_line.animate.set_color(GOLD).set_stroke(width=6), run_time=0.15)
            
            # Show weighted sum (attention weights · V)
            result = Sphere(radius=0.1, color=PURPLE, resolution=(6, 6)).move_to(center)
            self.play(
                FadeOut(VGroup(q, k, attention_line)),
                Transform(v, result),
                run_time=0.2
            )
            self.play(FadeOut(v), run_time=0.1)

        elif anim_type == 'shimmer_sweep':
            # Linear: Shimmer sweep across matrix
            self.play(
                mobject.animate.shift(RIGHT*0.05),
                run_time=0.2,
                rate_func=rate_functions.there_and_back
            )

        elif anim_type == 'kernel_slide':
            # Convolution: Show ACTUAL sliding kernel with dot products
            center = mobject.get_center()
            
            # Input feature map (3x3 grid of small dots)
            input_grid = VGroup(*[Dot(radius=0.03, color=BLUE) for _ in range(9)])
            input_grid.arrange_in_grid(rows=3, cols=3, buff=0.08)
            input_grid.move_to(center)
            
            # Kernel (2x2 smaller grid, highlighted)
            kernel = VGroup(*[Dot(radius=0.025, color=RED) for _ in range(4)])
            kernel.arrange_in_grid(rows=2, cols=2, buff=0.06)
            kernel.move_to(input_grid[0].get_center())
            
            self.play(FadeIn(VGroup(input_grid, kernel)), run_time=0.15)
            
            # Slide kernel across positions (4 positions for 3x3 input, 2x2 kernel)
            positions = [
                input_grid[0].get_center(),  # Top-left
                input_grid[1].get_center(),  # Top-right  
                input_grid[3].get_center(),  # Bottom-left
                input_grid[4].get_center()   # Bottom-right
            ]
            
            for i, pos in enumerate(positions):
                # Flash to show dot product computation
                self.play(kernel.animate.set_color(YELLOW), run_time=0.08)
                self.play(kernel.animate.set_color(RED), run_time=0.08)
                
                # Move to next position (except last)
                if i < len(positions) - 1:
                    self.play(kernel.animate.move_to(pos), run_time=0.15)
            
            # Show output feature map
            output = Dot(radius=0.05, color=GREEN).move_to(center)
            self.play(
                FadeOut(VGroup(input_grid, kernel)),
                FadeIn(output),
                run_time=0.2
            )
            self.play(FadeOut(output), run_time=0.1)

        elif anim_type == 'wave_ripple':
            # Activation: Ripple effect
            self.play(
                mobject.animate.scale(1.08),
                run_time=0.15,
                rate_func=rate_functions.there_and_back
            )
            self.play(
                mobject.animate.scale(1.05),
                run_time=0.15,
                rate_func=rate_functions.there_and_back
            )

        elif anim_type == 'spiral_compress':
            # Encoding: Spiral inward
            self.play(
                Rotate(mobject, angle=PI/4, about_point=mobject.get_center()),
                mobject.animate.scale(0.9),
                run_time=0.4
            )

        elif anim_type == 'spiral_expand':
            # Decoding: Spiral outward
            self.play(
                Rotate(mobject, angle=PI/4, about_point=mobject.get_center()),
                mobject.animate.scale(1.1),
                run_time=0.4
            )

        elif anim_type == 'morph_flow':
            # Reshape: Morphing animation
            self.play(
                mobject.animate.stretch(1.2, 0),  # Stretch along x
                run_time=0.2
            )
            self.play(
                mobject.animate.stretch(1/1.2, 0).stretch(1.2, 1),  # Restore x, stretch y
                run_time=0.2
            )

        elif anim_type in ['diverge_particle', 'converge_particle']:
            # Split/Merge: Already handled by arrow visualization
            self.play(
                mobject.animate.set_color(metadata['color_scheme']['accent']),
                run_time=0.2,
                rate_func=rate_functions.there_and_back
            )

        else:
            # Generic: Gentle pulse
            self.play(
                mobject.animate.scale(1.03),
                run_time=0.25,
                rate_func=rate_functions.there_and_back
            )

    def _smart_camera_tracking(self, target: Mobject, depth: int = 0, smooth: bool = True):
        """
        FIFA-style camera tracking with ZOOM IN/OUT based on call depth.
        - Zoom IN when entering deeper method calls (shows inner workings)
        - Zoom OUT when returning to show context
        - Camera moves in TRUE 3D space (X, Y, Z + phi, theta, distance)
        """
        if not isinstance(target, Mobject):
            return

        target_center = target.get_center()
        target_z = target_center[2]

        # ZOOM LOGIC based on depth
        base_distance = 8.0
        zoom_distance = base_distance - (depth * 0.8)  # Closer for deeper calls
        zoom_distance = max(4.0, min(zoom_distance, 12.0))  # Clamp between 4.0 and 12.0

        # FIFA camera style: Adjust viewing angle based on data position
        # Deeper objects (negative Z) get more tilted view to show depth
        phi_adjust = 70 * DEGREES + (abs(target_z) * 5 * DEGREES)

        # Adjust theta (horizontal rotation) based on target X position
        theta_adjust = -30 * DEGREES + (target_center[0] * 2 * DEGREES)

        # Move camera with all three parameters
        if (abs(target_z) > 0.5 or depth > 0) and smooth:
            try:
                self.move_camera(
                    phi=phi_adjust,
                    theta=theta_adjust,
                    distance=zoom_distance,
                    run_time=0.3
                )
            except Exception as e:
                # Fallback: skip camera movement if not supported
                logger.warning(f"Camera movement not supported: {e}", exc_info=True)

    def _create_performance_overlay(self) -> VGroup:
        """
        ENHANCED: Create performance stats overlay with real-time updates.

        Shows:
        - Total events processed
        - Current function depth
        - Progress percentage
        - Correlation ID
        """
        overlay = VGroup()

        # Title
        title = BillboardText("Performance", font_size=14, color=GOLD)
        title.to_edge(RIGHT).to_edge(UP).shift(LEFT*0.3 + DOWN*0.2)

        # Extract stats from trace
        total_events = self.trace_data.get('event_count', 0)
        correlation_id = self.trace_data.get('correlation_id', 'N/A')[:8]

        # Enhanced stats display with placeholders for updates
        stats_text = f"""Events: 0/{total_events}
Depth: 0
Progress: 0%
ID: {correlation_id}"""

        # Use BillboardText for always-readable stats
        stats = BillboardText(stats_text, font_size=10, color=WHITE)
        stats.next_to(title, DOWN, aligned_edge=RIGHT, buff=0.2)

        overlay.add(title, stats)

        # Store reference for updates
        self.perf_overlay_stats = stats
        self.total_events = total_events
        self.current_event_idx = 0

        return overlay

    def _update_performance_overlay(self, event_idx: int, depth: int):
        """
        ENHANCED: Update performance overlay with current progress.

        Args:
            event_idx: Current event index
            depth: Current call stack depth
        """
        if not hasattr(self, 'perf_overlay_stats'):
            return

        self.current_event_idx = event_idx
        progress = int((event_idx / max(self.total_events, 1)) * 100)
        correlation_id = self.trace_data.get('correlation_id', 'N/A')[:8]

        # Update stats text
        stats_text = f"""Events: {event_idx}/{self.total_events}
Depth: {depth}
Progress: {progress}%
ID: {correlation_id}"""

        # Create new text and replace old one
        new_stats = BillboardText(stats_text, font_size=10, color=WHITE)
        new_stats.move_to(self.perf_overlay_stats.get_center())

        # Animate the update (quick fade)
        try:
            self.remove(self.perf_overlay_stats)
            self.add_fixed_in_frame_mobjects(new_stats)
            self.perf_overlay_stats = new_stats
        except Exception as e:
            # Fail if animation not possible
            logger.warning(f"Performance overlay update failed: {e}", exc_info=True)

    @staticmethod
    def create_parameter_flow(start_pos: np.ndarray, end_pos: np.ndarray) -> VGroup:
        """Create simple parameter flow visualization."""
        # Straight line with arrow
        arrow = Arrow3D(
            start=start_pos,
            end=end_pos,
            color=BLUE,
            thickness=0.02
        )
        return VGroup(arrow)

    def demonstrate_all_scenarios(self):
        """Demonstrate all animation scenarios."""
        self.camera.background_color = "#1e1e1e"  # Dark theme

        title = Text("Universal Data Flow Visualization", font_size=32, color=BLUE)
        title.to_edge(UP)
        self.add_fixed_in_frame_mobjects(title)
        self.play(Write(title))
        self.wait(0.5)

        # Scenario 1: Primitive assignment
        self.clear()
        subtitle = Text("1. Primitive Assignment", font_size=24)
        self.add_fixed_in_frame_mobjects(subtitle.to_edge(UP))
        self.play(Write(subtitle))

        int_viz = DataVisualizer.create_primitive(42, "int")
        int_viz.mobject.shift(LEFT * 2)
        self.play(FadeIn(int_viz.mobject), FadeIn(int_viz.label))

        DataFlowAnimator.animate_assignment(self, int_viz, "x", is_reference=False)
        self.wait(1)

        # Scenario 2: Tensor transformation
        self.clear()
        subtitle = Text("2. Tensor Reshape", font_size=24)
        self.add_fixed_in_frame_mobjects(subtitle.to_edge(UP))
        self.play(Write(subtitle))

        tensor_viz = DataVisualizer.create_tensor((2, 3, 4))
        tensor_viz.mobject.shift(LEFT * 2)
        self.play(FadeIn(tensor_viz.mobject), FadeIn(tensor_viz.label))

        DataFlowAnimator.animate_transformation(self, tensor_viz, "reshape", (6, 4))
        self.wait(1)

        # Scenario 3: Function call
        self.clear()
        subtitle = Text("3. Function Call", font_size=24)
        self.add_fixed_in_frame_mobjects(subtitle.to_edge(UP))
        self.play(Write(subtitle))

        arg1 = DataVisualizer.create_primitive(10, "int")
        arg1.mobject.shift(LEFT * 3 + DOWN)
        arg2 = DataVisualizer.create_primitive(20, "int")
        arg2.mobject.shift(LEFT * 1.5 + DOWN)

        self.play(FadeIn(arg1.mobject), FadeIn(arg2.mobject))

        result = DataVisualizer.create_primitive(30, "int")
        result.mobject.shift(DOWN * 2)

        DataFlowAnimator.animate_function_call(self, "add()", [arg1, arg2], result)
        self.wait(1)

        # More scenarios can be added...

        end_text = Text("Complete Animation System Ready", font_size=28, color=GREEN)
        self.add_fixed_in_frame_mobjects(end_text)
        self.play(Write(end_text))
        self.wait(2)

    def _build_execution_graph_for_pattern(self) -> Dict:
        """Build execution graph for pattern detection."""
        calls = self.trace_data.get('calls', [])
        modules = set(call.get('module', '') for call in calls if call.get('module'))
        functions = [call.get('function', '') for call in calls]

        # Build simple graph structure
        nodes = {}
        for call in calls:
            call_id = call.get('call_id', '')
            if call_id:
                nodes[call_id] = call

        return {
            'nodes': nodes,
            'modules': modules,
            'max_depth': max((call.get('depth', 0) for call in calls), default=0),
            'functions': functions
        }

# ============================================================================
# TRACE PARSER & MAIN ENTRY
# ============================================================================

def generate_animation_from_trace(trace_file: str, output_file: str, simplified_mode: bool = True):
    """
    Generate animation from trace JSON file.

    Args:
        trace_file: Path to trace JSON file
        output_file: Output video filename
        simplified_mode: If True, show only main execution path (not all branches)
    """
    config.quality = 'medium_quality'
    config.output_file = output_file

    scene = UniversalDataFlowScene(trace_file=trace_file, simplified_mode=simplified_mode)
    scene.render()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        trace_file = sys.argv[1]
        output_file = sys.argv[2] if len(sys.argv) > 2 else "data_flow_animation"
        generate_animation_from_trace(trace_file, output_file)
    else:
        # Run demo
        config.quality = 'medium_quality'
        config.output_file = 'universal_data_flow_demo'
        scene = UniversalDataFlowScene()
        scene.render()
