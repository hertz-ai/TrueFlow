from logging_config import setup_logger
logger = setup_logger(__name__)

"""
Extended Operation Visualizers - Fills gaps in animation coverage

Adds missing visualizations:
- Convolution (sliding window)
- Batch Normalization (statistics visualization)
- Async Operations (parallel tracks)
- Nested Calls (call stack)
- Broadcasting (ghost copy expansion)
- Enhanced Matrix Multiplication (row-column highlighting)
- Memory Operations (cache grid)
- Control Flow (conditional branches, loops)
"""

import numpy as np
from manim import *
from typing import Dict, List, Tuple, Any, Optional
from animation_standards import (
    AnimationTiming, AnimationColors, DataTypeShapes,
    AnimationHelpers, ease_in_out_cubic
)


class ExtendedOperationVisualizer:
    """Extended visualizations for operations not in base system."""

    @staticmethod
    def create_convolution_viz(call_data: Dict, position: np.ndarray,
                               input_channels: int = 3, output_channels: int = 64,
                               kernel_size: int = 3) -> VGroup:
        """
        Visualize convolution operation with sliding window.

        Shows:
        - Input: 3-channel image (RGB layers)
        - Kernel: 3x3 sliding window
        - Sliding animation across image
        - Output: 64 feature maps
        """
        viz = VGroup()

        # Input image (3 channels stacked)
        input_layer = VGroup()
        for c in range(min(input_channels, 3)):
            channel = DataTypeShapes.create_array_2d(
                8, 8,  # 8x8 input image
                position=position + OUT * (c * 0.2 - 0.2),
                color=AnimationColors.get_layer_color(c, input_channels)
            )
            input_layer.add(channel)
        viz.add(input_layer)

        # Kernel window (glowing rectangle)
        kernel_size_visual = kernel_size * 0.3
        kernel = Rectangle(
            width=kernel_size_visual,
            height=kernel_size_visual,
            color=AnimationColors.COMPUTING,
            stroke_width=3
        )
        kernel.set_fill(AnimationColors.COMPUTING, opacity=0.3)
        kernel.move_to(position + UP * 0.8 + LEFT * 0.8)
        viz.add(kernel)

        # Kernel label
        kernel_label = Text(f"{kernel_size}x{kernel_size} kernel",
                           font_size=12, color=AnimationColors.COMPUTING)
        kernel_label.next_to(kernel, UP, buff=0.1)
        viz.add(kernel_label)

        # Output feature maps (preview of first few)
        output_position = position + RIGHT * 3
        output_maps = VGroup()
        for i in range(min(output_channels, 4)):
            feature_map = DataTypeShapes.create_array_2d(
                6, 6,  # 6x6 output (depends on stride/padding)
                position=output_position + OUT * (i * 0.15),
                color=AnimationColors.get_layer_color(i, output_channels)
            )
            feature_map.scale(0.7)
            output_maps.add(feature_map)

        viz.add(output_maps)

        # Connection arrow
        arrow = Arrow(
            input_layer.get_right(),
            output_maps.get_left(),
            color=AnimationColors.DATA_FLOW,
            stroke_width=2
        )
        viz.add(arrow)

        # Output label
        output_label = Text(f"{output_channels} feature maps",
                           font_size=12, color=WHITE)
        output_label.next_to(output_maps, DOWN, buff=0.2)
        viz.add(output_label)

        return viz

    @staticmethod
    def create_batch_norm_viz(call_data: Dict, position: np.ndarray,
                             batch_size: int = 32, features: int = 256) -> VGroup:
        """
        Visualize batch normalization.

        Shows:
        - Input: Batch of samples (multiple rows)
        - Statistics: Mean/variance computation
        - Normalization: Shift/scale animation
        - Output: Normalized samples
        """
        viz = VGroup()

        # Input batch (show sample of batch)
        batch_samples = min(batch_size, 8)
        feature_samples = min(features, 8)

        input_batch = VGroup()
        for b in range(batch_samples):
            sample = DataTypeShapes.create_array_1d(
                feature_samples,
                position=position + UP * (batch_samples/2 - b) * 0.25,
                color=AnimationColors.TENSOR
            )
            sample.scale(0.7)
            input_batch.add(sample)
        viz.add(input_batch)

        # Statistics visualization (mean and variance indicators)
        stats_position = position + RIGHT * 2
        mean_indicator = Text("μ", font_size=24, color=AnimationColors.COMPUTING)
        mean_indicator.move_to(stats_position + UP * 0.5)

        var_indicator = Text("σ²", font_size=24, color=AnimationColors.COMPUTING)
        var_indicator.move_to(stats_position + DOWN * 0.5)

        stats = VGroup(mean_indicator, var_indicator)
        viz.add(stats)

        # Output batch (normalized)
        output_position = position + RIGHT * 4
        output_batch = VGroup()
        for b in range(batch_samples):
            sample = DataTypeShapes.create_array_1d(
                feature_samples,
                position=output_position + UP * (batch_samples/2 - b) * 0.25,
                color=AnimationColors.SUCCESS  # Green indicates normalized
            )
            sample.scale(0.7)
            output_batch.add(sample)
        viz.add(output_batch)

        # Arrows
        arrow1 = Arrow(input_batch.get_right(), stats.get_left(),
                      color=AnimationColors.DATA_FLOW, stroke_width=2)
        arrow2 = Arrow(stats.get_right(), output_batch.get_left(),
                      color=AnimationColors.DATA_FLOW, stroke_width=2)
        viz.add(arrow1, arrow2)

        # Label
        label = Text(f"BatchNorm1d({features})", font_size=14, color=WHITE)
        label.move_to(position + DOWN * 2)
        viz.add(label)

        return viz

    @staticmethod
    def create_async_operation_viz(call_data: Dict, position: np.ndarray) -> VGroup:
        """
        Visualize async operation with parallel execution tracks.

        Shows:
        - Main thread track (central)
        - Async track (branching off)
        - Await point (clock icon)
        - Merge back (results combine)
        """
        viz = VGroup()

        # Main thread track
        main_track = Line(
            position + LEFT * 2,
            position + RIGHT * 2,
            color=AnimationColors.DATA_FLOW,
            stroke_width=3
        )
        viz.add(main_track)

        main_label = Text("Main Thread", font_size=12, color=AnimationColors.DATA_FLOW)
        main_label.next_to(main_track, UP, buff=0.1).shift(LEFT * 1.5)
        viz.add(main_label)

        # Async track (branches off)
        branch_point = position + LEFT * 0.5
        async_track = VGroup()

        # Branch line
        branch = Line(
            branch_point,
            branch_point + DOWN * 1.5 + RIGHT * 1.5,
            color=AnimationColors.ASYNC_FLOW,
            stroke_width=3
        )
        async_track.add(branch)

        # Async execution path
        async_exec = Line(
            branch_point + DOWN * 1.5 + RIGHT * 1.5,
            branch_point + DOWN * 1.5 + RIGHT * 2.5,
            color=AnimationColors.ASYNC_FLOW,
            stroke_width=3
        )
        async_track.add(async_exec)

        # Merge back
        merge = Line(
            branch_point + DOWN * 1.5 + RIGHT * 2.5,
            position + RIGHT * 1,
            color=AnimationColors.ASYNC_FLOW,
            stroke_width=3
        )
        async_track.add(merge)

        viz.add(async_track)

        async_label = Text("Async Task", font_size=12, color=AnimationColors.ASYNC_FLOW)
        async_label.next_to(async_exec, DOWN, buff=0.1)
        viz.add(async_label)

        # Await point (clock icon)
        await_point = position
        clock = Circle(radius=0.15, color=AnimationColors.WAITING)
        clock.move_to(await_point)

        clock_hand = Line(clock.get_center(), clock.get_center() + UP * 0.1,
                         color=AnimationColors.WAITING, stroke_width=2)

        await_icon = VGroup(clock, clock_hand)
        viz.add(await_icon)

        await_label = Text("await", font_size=10, color=AnimationColors.WAITING)
        await_label.next_to(await_icon, DOWN, buff=0.15)
        viz.add(await_label)

        return viz

    @staticmethod
    def create_nested_call_stack_viz(call_data: Dict, position: np.ndarray,
                                    depth: int = 3) -> VGroup:
        """
        Visualize nested function calls with call stack.

        Shows:
        - Stack frames growing vertically
        - Data flowing through nested calls
        - Return values flowing back up
        """
        viz = VGroup()

        stack_frames = VGroup()
        frame_height = 0.5
        frame_width = 2.0

        for i in range(min(depth, 5)):
            # Stack frame box
            frame = Rectangle(
                width=frame_width - i * 0.2,
                height=frame_height,
                color=AnimationColors.get_layer_color(i, depth),
                stroke_width=2
            )
            frame.set_fill(AnimationColors.get_layer_color(i, depth), opacity=0.2)
            frame.move_to(position + UP * (i * (frame_height + 0.1)))

            # Function name label
            func_name = f"func{depth - i}"
            label = Text(func_name, font_size=12, color=WHITE)
            label.move_to(frame.get_center())

            frame_group = VGroup(frame, label)
            stack_frames.add(frame_group)

        viz.add(stack_frames)

        # Call stack label
        stack_label = Text("Call Stack", font_size=14, color=WHITE)
        stack_label.next_to(stack_frames, DOWN, buff=0.3)
        viz.add(stack_label)

        # Data flow arrow (upward through stack)
        if depth > 1:
            arrow = Arrow(
                stack_frames[0].get_center(),
                stack_frames[-1].get_center(),
                color=AnimationColors.DATA_FLOW,
                stroke_width=2
            )
            viz.add(arrow)

        return viz

    @staticmethod
    def create_broadcasting_viz(call_data: Dict, position: np.ndarray,
                               shape_a: Tuple[int, ...] = (3, 1),
                               shape_b: Tuple[int, ...] = (1, 4)) -> VGroup:
        """
        Visualize broadcasting with ghost copy expansion.

        Shows:
        - Two tensors with different shapes
        - Ghost copies showing broadcast expansion
        - Element-wise operation after broadcast
        - Result in broadcasted shape
        """
        viz = VGroup()

        # Tensor A (3, 1)
        tensor_a_pos = position + LEFT * 2
        tensor_a = DataTypeShapes.create_array_2d(
            shape_a[0], shape_a[1],
            position=tensor_a_pos,
            color=AnimationColors.TENSOR
        )
        viz.add(tensor_a)

        a_label = Text(f"{shape_a}", font_size=10, color=WHITE)
        a_label.next_to(tensor_a, DOWN, buff=0.1)
        viz.add(a_label)

        # Tensor B (1, 4)
        tensor_b_pos = position + LEFT * 2 + DOWN * 1.5
        tensor_b = DataTypeShapes.create_array_2d(
            shape_b[0], shape_b[1],
            position=tensor_b_pos,
            color=AnimationColors.TENSOR
        )
        viz.add(tensor_b)

        b_label = Text(f"{shape_b}", font_size=10, color=WHITE)
        b_label.next_to(tensor_b, DOWN, buff=0.1)
        viz.add(b_label)

        # Ghost copies (showing broadcast expansion)
        broadcast_shape = (shape_a[0], shape_b[1])  # (3, 4)

        # Ghost of A expanded
        ghost_a = DataTypeShapes.create_array_2d(
            broadcast_shape[0], broadcast_shape[1],
            position=position,
            color=AnimationColors.TENSOR
        )
        ghost_a.set_opacity(0.3)
        viz.add(ghost_a)

        # Ghost of B expanded
        ghost_b = DataTypeShapes.create_array_2d(
            broadcast_shape[0], broadcast_shape[1],
            position=position + OUT * 0.2,
            color=AnimationColors.TENSOR
        )
        ghost_b.set_opacity(0.3)
        viz.add(ghost_b)

        # Result tensor (broadcasted shape)
        result_pos = position + RIGHT * 2.5
        result = DataTypeShapes.create_array_2d(
            broadcast_shape[0], broadcast_shape[1],
            position=result_pos,
            color=AnimationColors.SUCCESS
        )
        viz.add(result)

        result_label = Text(f"{broadcast_shape}", font_size=10, color=AnimationColors.SUCCESS)
        result_label.next_to(result, DOWN, buff=0.1)
        viz.add(result_label)

        # Arrows
        arrow = Arrow(
            tensor_a.get_right() + RIGHT * 0.5,
            result.get_left(),
            color=AnimationColors.DATA_FLOW,
            stroke_width=2
        )
        viz.add(arrow)

        # Broadcasting label
        broadcast_label = Text("Broadcasting", font_size=12, color=AnimationColors.COMPUTING)
        broadcast_label.move_to(position + UP * 1.2)
        viz.add(broadcast_label)

        return viz

    @staticmethod
    def create_enhanced_matmul_viz(call_data: Dict, position: np.ndarray,
                                  shape_a: Tuple[int, int] = (4, 3),
                                  shape_b: Tuple[int, int] = (3, 5)) -> VGroup:
        """
        Enhanced matrix multiplication with row-column highlighting.

        Shows:
        - Matrix A (M×K) and Matrix B (K×N)
        - Row-column highlighting during multiplication
        - Result matrix (M×N) building element by element
        """
        viz = VGroup()
        M, K = shape_a
        K2, N = shape_b

        # Matrix A
        matrix_a_pos = position + LEFT * 2.5
        matrix_a = DataTypeShapes.create_array_2d(
            M, K,
            position=matrix_a_pos,
            color=AnimationColors.TENSOR
        )
        viz.add(matrix_a)

        a_label = Text(f"A: {M}×{K}", font_size=12, color=WHITE)
        a_label.next_to(matrix_a, DOWN, buff=0.2)
        viz.add(a_label)

        # Matrix B
        matrix_b_pos = position
        matrix_b = DataTypeShapes.create_array_2d(
            K2, N,
            position=matrix_b_pos,
            color=AnimationColors.TENSOR
        )
        viz.add(matrix_b)

        b_label = Text(f"B: {K}×{N}", font_size=12, color=WHITE)
        b_label.next_to(matrix_b, DOWN, buff=0.2)
        viz.add(b_label)

        # Result matrix C
        result_pos = position + RIGHT * 2.5
        result = DataTypeShapes.create_array_2d(
            M, N,
            position=result_pos,
            color=AnimationColors.SUCCESS
        )
        viz.add(result)

        c_label = Text(f"C: {M}×{N}", font_size=12, color=AnimationColors.SUCCESS)
        c_label.next_to(result, DOWN, buff=0.2)
        viz.add(c_label)

        # Highlight example (first row of A, first column of B)
        # This would be animated in the actual scene
        highlight_row = Rectangle(
            width=K * 0.3,
            height=0.3,
            color=AnimationColors.COMPUTING,
            stroke_width=3
        )
        highlight_row.move_to(matrix_a.get_top() + DOWN * 0.15)
        highlight_row.set_fill(AnimationColors.COMPUTING, opacity=0.3)

        highlight_col = Rectangle(
            width=0.3,
            height=K2 * 0.3,
            color=AnimationColors.COMPUTING,
            stroke_width=3
        )
        highlight_col.move_to(matrix_b.get_left() + RIGHT * 0.15)
        highlight_col.set_fill(AnimationColors.COMPUTING, opacity=0.3)

        highlights = VGroup(highlight_row, highlight_col)
        viz.add(highlights)

        # Operation symbol
        matmul_symbol = Text("@", font_size=24, color=AnimationColors.MULTIPLY)
        matmul_symbol.move_to((matrix_a_pos + matrix_b_pos) / 2)
        viz.add(matmul_symbol)

        return viz

    @staticmethod
    def create_memory_operation_viz(call_data: Dict, position: np.ndarray,
                                   operation: str = "read") -> VGroup:
        """
        Visualize memory operations (cache read/write/update).

        Shows:
        - Cache grid structure
        - Key hashing to index
        - Value read/write with cell highlighting
        """
        viz = VGroup()

        # Cache grid (8 cells)
        cache_grid = VGroup()
        grid_size = 8
        cell_size = 0.3

        for i in range(grid_size):
            cell = Square(side_length=cell_size)
            cell.set_stroke(AnimationColors.MEMORY_CELL, width=2)
            cell.set_fill(AnimationColors.MEMORY_CELL, opacity=0.2)
            cell.move_to(position + RIGHT * (i - grid_size/2) * (cell_size + 0.05))
            cache_grid.add(cell)

        viz.add(cache_grid)

        # Cache label
        cache_label = Text("Cache Memory", font_size=12, color=WHITE)
        cache_label.next_to(cache_grid, UP, buff=0.2)
        viz.add(cache_label)

        # Highlight accessed cell (e.g., cell 3)
        accessed_cell = cache_grid[3].copy()
        accessed_cell.set_stroke(
            AnimationColors.CACHE_HIT if operation == "read" else AnimationColors.COMPUTING,
            width=4
        )
        accessed_cell.set_fill(
            AnimationColors.CACHE_HIT if operation == "read" else AnimationColors.COMPUTING,
            opacity=0.5
        )
        viz.add(accessed_cell)

        # Key and value visualization
        if operation == "write":
            # Key → Index
            key_pos = position + LEFT * 3 + UP * 0.5
            key = Text("key", font_size=12, color=AnimationColors.STRING)
            key.move_to(key_pos)

            hash_arrow = Arrow(key.get_right(), accessed_cell.get_top(),
                             color=AnimationColors.DATA_FLOW, stroke_width=2)

            # Value → Cell
            value_pos = position + LEFT * 3 + DOWN * 0.5
            value = Sphere(radius=0.1)
            value.set_color(AnimationColors.FLOAT)
            value.move_to(value_pos)

            value_arrow = Arrow(value.get_right(), accessed_cell.get_bottom(),
                               color=AnimationColors.DATA_FLOW, stroke_width=2)

            viz.add(key, hash_arrow, value, value_arrow)

        elif operation == "read":
            # Cell → Value out
            value_out_pos = position + RIGHT * 3
            value_out = Sphere(radius=0.1)
            value_out.set_color(AnimationColors.FLOAT)
            value_out.move_to(value_out_pos)

            read_arrow = Arrow(accessed_cell.get_right(), value_out.get_left(),
                              color=AnimationColors.CACHE_HIT, stroke_width=2)

            viz.add(value_out, read_arrow)

        # Operation label
        op_label = Text(f"cache[key] {'←' if operation == 'write' else '→'} value",
                       font_size=10, color=WHITE)
        op_label.next_to(cache_grid, DOWN, buff=0.3)
        viz.add(op_label)

        return viz


# Export function to get timing for extended operations
def get_extended_operation_timing(op_type: str) -> float:
    """Get timing for extended operation types."""
    extended_timing = {
        'convolution': AnimationTiming.TRANSFORM_COMPLEX * 2,  # 3.0s
        'batch_norm': AnimationTiming.TRANSFORM_SIMPLE,        # 0.5s
        'async_operation': AnimationTiming.FUNCTION_TOTAL,     # 1.3s
        'nested_call': AnimationTiming.FUNCTION_TOTAL * 1.5,   # ~2.0s
        'broadcasting': AnimationTiming.TRANSFORM_COMPLEX,     # 1.5s
        'matmul_enhanced': AnimationTiming.TRANSFORM_COMPLEX,  # 1.5s
        'memory_read': AnimationTiming.MEMORY_READ,            # 0.3s
        'memory_write': AnimationTiming.MEMORY_WRITE,          # 0.4s
        'memory_update': AnimationTiming.MEMORY_UPDATE,        # 0.7s
    }
    return extended_timing.get(op_type, AnimationTiming.DATA_FLOW_SHORT)
