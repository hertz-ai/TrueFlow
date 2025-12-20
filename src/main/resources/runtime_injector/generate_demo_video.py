"""
Generate a demo video from a sample trace file.
Run with: python generate_demo_video.py
"""
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from logging_config import setup_logger
logger = setup_logger(__name__)

import json
import numpy as np
from manim import *
from collections import defaultdict


class DemoTraceScene(ThreeDScene):
    """
    Demo trace visualization for sample trace files.
    """

    def construct(self):
        # Use the medium trace file
        trace_file = os.path.join(
            os.path.dirname(__file__),
            "tests", "fixtures", "traces", "sample_trace_medium.json"
        )

        logger.info(f"Loading trace file: {trace_file}")

        with open(trace_file, 'r') as f:
            self.trace_data = json.load(f)

        calls = self.trace_data.get('calls', [])
        logger.info(f"Loaded trace with {len(calls)} calls")

        # Extract modules
        modules = {}
        for call in calls:
            if call.get('type') != 'call':
                continue
            module_name = call.get('module', 'unknown')
            if module_name not in modules:
                modules[module_name] = []
            modules[module_name].append(call)

        logger.info(f"Found {len(modules)} modules")

        # Set up camera
        self.set_camera_orientation(phi=60 * DEGREES, theta=-45 * DEGREES)

        # Title
        title = Text("TrueFlow - Execution Trace Visualization", font_size=32, color=GOLD)
        title.to_edge(UP)
        self.add_fixed_in_frame_mobjects(title)
        self.play(Write(title), run_time=1)

        # Subtitle
        subtitle = Text("Unblackbox LLM Code with Deterministic Truth", font_size=20, color=WHITE)
        subtitle.next_to(title, DOWN)
        self.add_fixed_in_frame_mobjects(subtitle)
        self.play(FadeIn(subtitle), run_time=0.5)
        self.wait(0.5)

        # Create module boxes in 3D
        module_boxes = VGroup()
        colors = [BLUE, GREEN, RED, ORANGE, PURPLE, TEAL, MAROON, GOLD]

        # Position modules in a grid
        max_modules = min(len(modules), 8)  # Limit to 8 modules
        rows = 2
        cols = 4

        for i, (module_name, module_calls) in enumerate(list(modules.items())[:max_modules]):
            row = i // cols
            col = i % cols

            # Create box
            box = Cube(side_length=1.2, fill_opacity=0.5, fill_color=colors[i % len(colors)])
            box.move_to(
                RIGHT * (col - cols/2 + 0.5) * 2.5 +
                UP * (rows/2 - row - 0.5) * 2.5 +
                OUT * 0
            )

            # Module label
            short_name = module_name.split('.')[-1][:15]
            label = Text(short_name, font_size=14, color=WHITE)
            label.next_to(box, UP, buff=0.1)

            # Call count badge
            count_badge = Circle(radius=0.25, fill_opacity=1, fill_color=YELLOW, stroke_width=0)
            count_text = Text(str(len(module_calls)), font_size=12, color=BLACK)
            count_text.move_to(count_badge)
            count_group = VGroup(count_badge, count_text)
            count_group.next_to(box, RIGHT + UP, buff=-0.2)

            # Group and add
            module_group = VGroup(box, label, count_group)
            module_boxes.add(module_group)

        # Animate modules appearing
        self.play(
            LaggedStart(*[GrowFromCenter(m[0]) for m in module_boxes], lag_ratio=0.15),
            run_time=2
        )
        self.play(
            LaggedStart(*[FadeIn(m[1]) for m in module_boxes], lag_ratio=0.1),
            LaggedStart(*[FadeIn(m[2]) for m in module_boxes], lag_ratio=0.1),
            run_time=1
        )

        # Animate call flow between modules
        self.wait(0.5)

        # Draw some arrows to show data flow
        if len(module_boxes) >= 2:
            arrow1 = Arrow3D(
                module_boxes[0][0].get_center(),
                module_boxes[1][0].get_center(),
                color=YELLOW,
                thickness=0.02
            )
            self.play(GrowArrow(arrow1), run_time=0.5)

            if len(module_boxes) >= 3:
                arrow2 = Arrow3D(
                    module_boxes[1][0].get_center(),
                    module_boxes[2][0].get_center(),
                    color=YELLOW,
                    thickness=0.02
                )
                self.play(GrowArrow(arrow2), run_time=0.5)

        # Rotate camera to show 3D
        self.begin_ambient_camera_rotation(rate=0.2)
        self.wait(3)
        self.stop_ambient_camera_rotation()

        # Final frame with stats
        self.play(
            FadeOut(subtitle),
            run_time=0.5
        )

        stats = Text(
            f"Modules: {len(modules)} | Calls: {len(calls)}",
            font_size=20,
            color=GREEN
        )
        stats.next_to(title, DOWN)
        self.add_fixed_in_frame_mobjects(stats)
        self.play(FadeIn(stats), run_time=0.5)

        self.wait(2)


if __name__ == "__main__":
    # Run with manim
    import subprocess

    script_path = os.path.abspath(__file__)
    output_dir = os.path.join(os.path.dirname(__file__), "demo_output")

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Run manim
    cmd = [
        "manim",
        "-ql",  # Low quality for quick preview (-qm for medium, -qh for high)
        "--media_dir", output_dir,
        script_path,
        "DemoTraceScene"
    ]

    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd)

    # Show output location
    video_path = os.path.join(output_dir, "videos", "generate_demo_video", "480p15", "DemoTraceScene.mp4")
    print(f"\nVideo should be at: {video_path}")
