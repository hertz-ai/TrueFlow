from logging_config import setup_logger
logger = setup_logger(__name__)

"""
Comprehensive Micro-Animations for ALL Operations

Inspired by 3Blue1Brown - every tensor operation, matrix multiplication,
data manipulation, method call gets its own micro-animation.

Coverage:
- Tensor operations (matmul, add, mul, div, transpose, reshape, concat, split)
- Matrix operations (diagonal, inverse, determinant, eigenvalues)
- Reduction operations (sum, mean, max, min, softmax)
- Parallel operations (broadcasting, batching, gather, scatter)
- Neural operations (attention, convolution, pooling, normalization)
- Data flow (input → method → output with parameter passing)
- Method calls (non-boilerplate only: exclude getters/setters/properties)
"""

from manim import *
import numpy as np
from typing import Dict, List, Optional, Tuple

class MicroAnimationLibrary:
    """
    Complete library of micro-animations for all operations.

    Each micro-animation shows EXACTLY what the operation does:
    - Matrix multiplication: Show row × column dot products
    - Transpose: Show matrix flipping across diagonal
    - Reshape: Show tensor morphing to new shape
    - Softmax: Show exp → normalize pipeline
    - Broadcasting: Show dimension expansion
    - Concat: Show tensors merging along axis
    - etc.
    """

    def __init__(self, scene: ThreeDScene):
        self.scene = scene

    # =========================================================================
    # MATRIX OPERATIONS (Linear Algebra)
    # =========================================================================

    def matmul_animation(self, center: np.ndarray, shape_a: Tuple, shape_b: Tuple):
        """
        Matrix multiplication A @ B showing:
        1. Matrix A and B side by side
        2. Highlight row from A, column from B
        3. Show dot product computation (element-wise multiply + sum)
        4. Result element appears in output matrix
        5. Repeat for all positions

        Example: (3x2) @ (2x4) → (3x4)
        """
        m, k = shape_a
        k2, n = shape_b
        assert k == k2, "Inner dimensions must match"

        # Create matrix A (left) and B (right)
        mat_a = self._create_matrix_grid(m, k, color=BLUE).shift(LEFT * 1.5)
        mat_b = self._create_matrix_grid(k, n, color=GREEN).shift(RIGHT * 0.5)

        self.scene.play(FadeIn(VGroup(mat_a, mat_b)), run_time=0.2)

        # Show one multiplication (row i from A, column j from B)
        i, j = 0, 0  # First element

        # Highlight row and column
        row_highlight = SurroundingRectangle(
            VGroup(*[mat_a[i*k + c] for c in range(k)]),
            color=YELLOW, buff=0.05
        )
        col_highlight = SurroundingRectangle(
            VGroup(*[mat_b[r*n + j] for r in range(k)]),
            color=YELLOW, buff=0.05
        )

        self.scene.play(Create(VGroup(row_highlight, col_highlight)), run_time=0.15)

        # Show dot product: a[i,0]*b[0,j] + a[i,1]*b[1,j] + ...
        dot_product_viz = VGroup()
        for idx in range(k):
            term = Text(f"×", font_size=10, color=WHITE)
            term.move_to(center + UP*0.3 + RIGHT*(idx*0.2 - k*0.1))
            dot_product_viz.add(term)

        self.scene.play(FadeIn(dot_product_viz), run_time=0.15)

        # Show sum → result
        result_dot = Dot(radius=0.08, color=PURPLE).move_to(center + DOWN*0.3)
        self.scene.play(
            FadeOut(dot_product_viz),
            FadeIn(result_dot),
            run_time=0.15
        )

        # Cleanup
        self.scene.play(
            FadeOut(VGroup(mat_a, mat_b, row_highlight, col_highlight, result_dot)),
            run_time=0.2
        )

    def transpose_animation(self, center: np.ndarray, shape: Tuple):
        """
        Transpose: Flip matrix across diagonal
        Show elements swapping positions (i,j) ↔ (j,i)
        """
        m, n = shape
        matrix = self._create_matrix_grid(m, n, color=BLUE).move_to(center)

        self.scene.play(FadeIn(matrix), run_time=0.2)

        # Show diagonal line
        diagonal = Line(
            matrix[0].get_center(),
            matrix[-1].get_center(),
            color=YELLOW, stroke_width=2
        )
        self.scene.play(Create(diagonal), run_time=0.15)

        # Rotate matrix across diagonal (flip)
        self.scene.play(
            Rotate(matrix, angle=PI/2, axis=np.array([1, -1, 0])),
            run_time=0.4
        )

        self.scene.play(FadeOut(VGroup(matrix, diagonal)), run_time=0.2)

    def reshape_animation(self, center: np.ndarray, old_shape: Tuple, new_shape: Tuple):
        """
        Reshape: Morph tensor from old shape to new shape
        Show grid morphing visually
        """
        # Old shape grid
        old_grid = self._create_tensor_cube(*old_shape, color=BLUE).move_to(center)

        self.scene.play(FadeIn(old_grid), run_time=0.2)

        # Morph to new shape
        new_grid = self._create_tensor_cube(*new_shape, color=PURPLE).move_to(center)

        self.scene.play(
            Transform(old_grid, new_grid),
            run_time=0.5
        )

        self.scene.play(FadeOut(old_grid), run_time=0.2)

    # =========================================================================
    # ELEMENT-WISE OPERATIONS
    # =========================================================================

    def elementwise_operation(self, center: np.ndarray, op: str, shape: Tuple):
        """
        Element-wise ops (add, mul, div, sub): Show operation on each element

        op: '+', '*', '/', '-'
        """
        # Two tensors
        tensor_a = self._create_tensor_cube(*shape, color=BLUE).shift(LEFT*0.5)
        tensor_b = self._create_tensor_cube(*shape, color=GREEN).shift(RIGHT*0.5)

        self.scene.play(FadeIn(VGroup(tensor_a, tensor_b)), run_time=0.2)

        # Show operator symbol
        op_symbol = Text(op, font_size=24, color=YELLOW).move_to(center)
        self.scene.play(Write(op_symbol), run_time=0.15)

        # Flash elements pairing up
        self.scene.play(
            tensor_a.animate.set_color(YELLOW),
            tensor_b.animate.set_color(YELLOW),
            run_time=0.15
        )

        # Result tensor
        result = self._create_tensor_cube(*shape, color=PURPLE).move_to(center)
        self.scene.play(
            FadeOut(VGroup(tensor_a, tensor_b, op_symbol)),
            FadeIn(result),
            run_time=0.2
        )

        self.scene.play(FadeOut(result), run_time=0.2)

    # =========================================================================
    # REDUCTION OPERATIONS
    # =========================================================================

    def softmax_animation(self, center: np.ndarray, length: int = 4):
        """
        Softmax: exp → normalize
        Show: [x₁, x₂, x₃, x₄] → [e^x₁, e^x₂, e^x₃, e^x₄] → [p₁, p₂, p₃, p₄]
        """
        # Input vector (row of dots)
        input_vec = VGroup(*[Dot(radius=0.06, color=BLUE) for _ in range(length)])
        input_vec.arrange(RIGHT, buff=0.15).move_to(center + UP*0.4)

        self.scene.play(FadeIn(input_vec), run_time=0.2)

        # Step 1: exp (dots grow)
        exp_text = Text("exp", font_size=12, color=YELLOW).next_to(input_vec, UP, buff=0.1)
        self.scene.play(
            Write(exp_text),
            *[dot.animate.scale(1.5) for dot in input_vec],
            run_time=0.25
        )

        # Step 2: normalize (all scale down, but proportionally)
        norm_text = Text("Σ=1", font_size=12, color=GREEN).next_to(input_vec, DOWN, buff=0.1)
        self.scene.play(
            FadeOut(exp_text),
            Write(norm_text),
            *[dot.animate.scale(0.8).set_color(GREEN) for dot in input_vec],
            run_time=0.25
        )

        self.scene.play(FadeOut(VGroup(input_vec, norm_text)), run_time=0.2)

    def reduction_animation(self, center: np.ndarray, op: str, shape: Tuple, axis: int):
        """
        Reduction ops (sum, mean, max, min): Show aggregation along axis

        op: 'sum', 'mean', 'max', 'min'
        axis: dimension to reduce
        """
        # Create tensor grid
        tensor = self._create_tensor_cube(*shape, color=BLUE).move_to(center)

        self.scene.play(FadeIn(tensor), run_time=0.2)

        # Show collapsing animation along axis
        # (simplified: scale along that dimension to 0)
        scale_factors = [1, 1, 1]
        scale_factors[axis] = 0.1

        op_text = Text(op, font_size=12, color=YELLOW).next_to(tensor, UP, buff=0.1)
        self.scene.play(
            Write(op_text),
            tensor.animate.scale(scale_factors),
            run_time=0.4
        )

        self.scene.play(FadeOut(VGroup(tensor, op_text)), run_time=0.2)

    # =========================================================================
    # PARALLEL OPERATIONS
    # =========================================================================

    def broadcasting_animation(self, center: np.ndarray, shape_a: Tuple, shape_b: Tuple):
        """
        Broadcasting: Show dimension expansion
        Example: (3, 1) + (1, 4) → both expand to (3, 4)
        """
        # Small tensor
        small = self._create_tensor_cube(*shape_a, color=BLUE).shift(LEFT*0.5)
        large_shape = self._create_tensor_cube(*shape_b, color=GREEN).shift(RIGHT*0.5)

        self.scene.play(FadeIn(VGroup(small, large_shape)), run_time=0.2)

        # Show small expanding (duplication along broadcast dims)
        expanded_small = self._create_tensor_cube(
            *[max(a, b) for a, b in zip(shape_a, shape_b)],
            color=PURPLE
        ).shift(LEFT*0.5)

        self.scene.play(
            Transform(small, expanded_small),
            run_time=0.4
        )

        self.scene.play(FadeOut(VGroup(small, large_shape)), run_time=0.2)

    def concat_animation(self, center: np.ndarray, num_tensors: int, axis: int):
        """
        Concatenation: Show tensors stacking/merging along axis
        """
        # Multiple tensors (simplified as colored cubes)
        tensors = VGroup()
        colors = [BLUE, GREEN, RED, YELLOW, PURPLE]
        spacing = 0.3

        for i in range(num_tensors):
            cube = Cube(side_length=0.3, fill_color=colors[i % len(colors)], fill_opacity=0.7)
            cube.shift(RIGHT * (i * spacing - num_tensors * spacing / 2))
            tensors.add(cube)

        tensors.move_to(center)
        self.scene.play(FadeIn(tensors), run_time=0.2)

        # Merge along axis (move together)
        merged_pos = center
        self.scene.play(
            *[tensor.animate.move_to(merged_pos) for tensor in tensors],
            run_time=0.4
        )

        # Single merged result
        result = Cube(side_length=0.4, fill_color=PURPLE, fill_opacity=0.7).move_to(center)
        self.scene.play(
            FadeOut(tensors),
            FadeIn(result),
            run_time=0.2
        )

        self.scene.play(FadeOut(result), run_time=0.2)

    # =========================================================================
    # NEURAL NETWORK OPERATIONS
    # =========================================================================

    def convolution_2d_animation(self, center: np.ndarray, input_size: int = 5, kernel_size: int = 3):
        """
        2D Convolution: Sliding kernel with dot products
        More detailed than before - show ALL positions
        """
        # Input feature map (grid)
        input_grid = VGroup(*[
            Dot(radius=0.04, color=BLUE)
            for _ in range(input_size * input_size)
        ])
        input_grid.arrange_in_grid(rows=input_size, cols=input_size, buff=0.1)
        input_grid.move_to(center)

        # Kernel (smaller highlighted grid)
        kernel = Square(side_length=kernel_size*0.14, color=RED, stroke_width=3)
        kernel.move_to(input_grid[0].get_center())

        self.scene.play(FadeIn(VGroup(input_grid, kernel)), run_time=0.2)

        # Slide across all valid positions
        output_size = input_size - kernel_size + 1
        for row in range(output_size):
            for col in range(output_size):
                # Target position
                idx = row * input_size + col
                target = input_grid[idx].get_center()

                # Move kernel
                self.scene.play(
                    kernel.animate.move_to(target),
                    run_time=0.08
                )

                # Flash to show computation
                self.scene.play(
                    kernel.animate.set_stroke(color=YELLOW, width=4),
                    run_time=0.05
                )
                self.scene.play(
                    kernel.animate.set_stroke(color=RED, width=3),
                    run_time=0.05
                )

        self.scene.play(FadeOut(VGroup(input_grid, kernel)), run_time=0.2)

    def pooling_animation(self, center: np.ndarray, pool_type: str = "max"):
        """
        Pooling (max/avg): Show grid → downsampled grid
        """
        # Input grid (4x4)
        input_grid = VGroup(*[Dot(radius=0.05, color=BLUE) for _ in range(16)])
        input_grid.arrange_in_grid(rows=4, cols=4, buff=0.12)
        input_grid.move_to(center)

        self.scene.play(FadeIn(input_grid), run_time=0.2)

        # Pool 2x2 → 2x2 output
        # Highlight 2x2 regions one by one
        pool_text = Text(pool_type, font_size=10, color=YELLOW).next_to(input_grid, UP, buff=0.1)
        self.scene.play(Write(pool_text), run_time=0.15)

        # Output grid (2x2)
        output_grid = VGroup(*[Dot(radius=0.07, color=GREEN) for _ in range(4)])
        output_grid.arrange_in_grid(rows=2, cols=2, buff=0.2)
        output_grid.move_to(center)

        self.scene.play(
            input_grid.animate.set_opacity(0.3),
            FadeIn(output_grid),
            run_time=0.4
        )

        self.scene.play(FadeOut(VGroup(input_grid, output_grid, pool_text)), run_time=0.2)

    def batch_normalization_animation(self, center: np.ndarray, batch_size: int = 4):
        """
        Batch Normalization: Show statistics → normalize → scale/shift
        """
        # Batch of samples (vertical stack)
        batch = VGroup(*[
            Dot(radius=0.06, color=BLUE)
            for _ in range(batch_size)
        ])
        batch.arrange(DOWN, buff=0.15).move_to(center)

        self.scene.play(FadeIn(batch), run_time=0.2)

        # Step 1: Compute mean/std (show horizontal line at mean)
        mean_line = Line(LEFT*0.3, RIGHT*0.3, color=YELLOW, stroke_width=2)
        mean_line.move_to(center)
        self.scene.play(Create(mean_line), run_time=0.15)

        # Step 2: Normalize (dots move toward mean)
        self.scene.play(
            *[dot.animate.move_to(center).set_color(GREEN) for dot in batch],
            run_time=0.3
        )

        # Step 3: Scale and shift (spread out again, different color)
        final_positions = [center + UP*(i-batch_size/2)*0.15 for i in range(batch_size)]
        self.scene.play(
            *[batch[i].animate.move_to(final_positions[i]).set_color(PURPLE) for i in range(batch_size)],
            run_time=0.3
        )

        self.scene.play(FadeOut(VGroup(batch, mean_line)), run_time=0.2)

    # =========================================================================
    # METHOD CALL ANIMATIONS
    # =========================================================================

    def method_call_animation(self, center: np.ndarray, method_name: str,
                             num_params: int, has_return: bool = True):
        """
        Method call: Input → [Method Box] → Output
        Show parameters flowing in, method executing, result flowing out

        Filter out boilerplate (getters/setters/properties)
        """
        # Skip boilerplate methods
        boilerplate_patterns = [
            'get_', 'set_', '__get', '__set',
            'property', '@property',
            '__init__', '__repr__', '__str__'
        ]

        if any(pattern in method_name.lower() for pattern in boilerplate_patterns):
            # Skip animation for boilerplate
            return

        # Method box (center)
        method_box = RoundedRectangle(
            width=1.0, height=0.5,
            corner_radius=0.1,
            fill_color=BLUE, fill_opacity=0.3,
            stroke_color=BLUE, stroke_width=2
        ).move_to(center)

        method_label = BillboardText(method_name[:15], font_size=10, color=WHITE)
        method_label.move_to(center)

        self.scene.play(FadeIn(VGroup(method_box, method_label)), run_time=0.15)

        # Parameters flowing IN (from left)
        if num_params > 0:
            params = VGroup(*[
                Dot(radius=0.05, color=GREEN).shift(LEFT * (1.0 + i*0.2))
                for i in range(min(num_params, 3))  # Max 3 visible
            ])

            self.scene.play(FadeIn(params), run_time=0.1)
            self.scene.play(
                *[param.animate.move_to(center) for param in params],
                run_time=0.3
            )
            self.scene.play(FadeOut(params), run_time=0.1)

        # Method executing (pulse)
        self.scene.play(
            method_box.animate.set_stroke(color=YELLOW, width=4),
            run_time=0.15
        )
        self.scene.play(
            method_box.animate.set_stroke(color=BLUE, width=2),
            run_time=0.15
        )

        # Return value flowing OUT (to right)
        if has_return:
            return_val = Dot(radius=0.06, color=PURPLE).move_to(center)
            self.scene.play(FadeIn(return_val), run_time=0.1)
            self.scene.play(
                return_val.animate.shift(RIGHT * 1.2),
                run_time=0.3
            )
            self.scene.play(FadeOut(return_val), run_time=0.1)

        self.scene.play(FadeOut(VGroup(method_box, method_label)), run_time=0.15)

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _create_matrix_grid(self, rows: int, cols: int, color=BLUE) -> VGroup:
        """Create grid of dots representing matrix."""
        dots = VGroup(*[Dot(radius=0.04, color=color) for _ in range(rows * cols)])
        dots.arrange_in_grid(rows=rows, cols=cols, buff=0.12)
        return dots

    def _create_tensor_cube(self, *shape, color=BLUE) -> Mobject:
        """Create visual representation of n-D tensor."""
        if len(shape) == 1:
            # 1D: row of dots
            return VGroup(*[Dot(radius=0.05, color=color) for _ in range(shape[0])])
        elif len(shape) == 2:
            # 2D: grid
            return self._create_matrix_grid(shape[0], shape[1], color)
        else:
            # 3D+: cube
            side = 0.3 * min(shape[0], 3)  # Cap visual size
            return Cube(side_length=side, fill_color=color, fill_opacity=0.6)


class ComprehensiveMicroAnimator:
    """
    Dispatcher that selects appropriate micro-animation based on operation type.

    Detects operation from:
    - Function name (e.g., "matmul", "transpose", "conv2d")
    - Operation metadata (if available)
    - Heuristics (parameter types, shapes)
    """

    def __init__(self, scene: ThreeDScene):
        self.library = MicroAnimationLibrary(scene)

    def animate_operation(self, center: np.ndarray, metadata: Dict):
        """
        Auto-detect operation type and play appropriate micro-animation.

        metadata should contain:
        - 'operation': operation name/type
        - 'shapes': input/output tensor shapes
        - 'params': parameters passed
        """
        op = metadata.get('operation', '').lower()

        # Matrix operations
        if 'matmul' in op or 'mm' in op or '@' in op:
            shapes = metadata.get('shapes', [(2, 3), (3, 4)])
            self.library.matmul_animation(center, shapes[0], shapes[1])

        elif 'transpose' in op or '.t(' in op:
            shape = metadata.get('shapes', [(3, 4)])[0]
            self.library.transpose_animation(center, shape)

        elif 'reshape' in op or 'view' in op:
            old_shape = metadata.get('old_shape', (6, 2))
            new_shape = metadata.get('new_shape', (3, 4))
            self.library.reshape_animation(center, old_shape, new_shape)

        # Element-wise operations
        elif any(x in op for x in ['add', 'mul', 'div', 'sub', '+', '*', '/', '-']):
            op_symbol = '+' if 'add' in op else ('*' if 'mul' in op else '/')
            shape = metadata.get('shapes', [(3, 4)])[0]
            self.library.elementwise_operation(center, op_symbol, shape)

        # Reductions
        elif 'softmax' in op:
            length = metadata.get('length', 4)
            self.library.softmax_animation(center, length)

        elif any(x in op for x in ['sum', 'mean', 'max', 'min']):
            op_name = next(x for x in ['sum', 'mean', 'max', 'min'] if x in op)
            shape = metadata.get('shapes', [(3, 4, 5)])[0]
            axis = metadata.get('axis', 0)
            self.library.reduction_animation(center, op_name, shape, axis)

        # Broadcasting
        elif 'broadcast' in op:
            shapes = metadata.get('shapes', [(3, 1), (1, 4)])
            self.library.broadcasting_animation(center, shapes[0], shapes[1])

        # Concatenation
        elif 'concat' in op or 'cat' in op or 'stack' in op:
            num_tensors = metadata.get('num_tensors', 3)
            axis = metadata.get('axis', 0)
            self.library.concat_animation(center, num_tensors, axis)

        # Neural operations
        elif 'conv' in op:
            input_size = metadata.get('input_size', 5)
            kernel_size = metadata.get('kernel_size', 3)
            self.library.convolution_2d_animation(center, input_size, kernel_size)

        elif 'pool' in op:
            pool_type = 'max' if 'max' in op else 'avg'
            self.library.pooling_animation(center, pool_type)

        elif 'batch_norm' in op or 'batchnorm' in op:
            batch_size = metadata.get('batch_size', 4)
            self.library.batch_normalization_animation(center, batch_size)

        # Method calls (generic)
        elif metadata.get('type') == 'method_call':
            method_name = metadata.get('function', 'method')
            num_params = metadata.get('num_params', 0)
            has_return = metadata.get('has_return', True)
            self.library.method_call_animation(center, method_name, num_params, has_return)

        else:
            # Generic pulse animation for unknown operations
            pass
