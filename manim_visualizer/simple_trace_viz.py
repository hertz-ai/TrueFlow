"""
Simple working trace visualizer (no camera.frame issues).
"""
from logging_config import setup_logger
logger = setup_logger(__name__)

import json
import numpy as np
from manim import *
from collections import defaultdict


class SimpleTraceScene(ThreeDScene):
    """
    Simple, working 3D trace visualization.
    - No camera.frame usage (ThreeDCamera doesn't have it)
    - Clean module stacking
    - No complex features that break
    """

    def __init__(self, trace_file=None, **kwargs):
        self.trace_file = trace_file
        super().__init__(**kwargs)

    def construct(self):
        # Load trace data
        if not self.trace_file:
            logger.error("No trace file provided")
            return

        with open(self.trace_file, 'r') as f:
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

        # Title
        title = Text("Execution Trace Visualization", font_size=36, color=GOLD)
        title.to_edge(UP)
        self.add_fixed_in_frame_mobjects(title)
        self.play(Write(title), run_time=1)

        # Create module boxes in 3D
        module_boxes = VGroup()
        z_offset = 0

        for i, (module_name, module_calls) in enumerate(list(modules.items())[:10]):  # Limit to 10
            # Create box
            box = Cube(side_length=1, fill_opacity=0.3, fill_color=BLUE)
            box.shift(OUT * z_offset)

            # Module label
            short_name = module_name.split('.')[-1][:20]
            label = Text(short_name, font_size=16, color=WHITE)
            label.next_to(box, UP)

            # Call count
            count_text = Text(f"{len(module_calls)} calls", font_size=12, color=YELLOW)
            count_text.next_to(box, DOWN)

            # Group and add
            module_group = VGroup(box, label, count_text)
            module_boxes.add(module_group)

            # Animate
            self.play(
                GrowFromCenter(box),
                FadeIn(label),
                FadeIn(count_text),
                run_time=0.5
            )

            z_offset += 1.5

        # Rotate view
        self.set_camera_orientation(phi=60 * DEGREES, theta=-45 * DEGREES)
        self.wait(1)

        # Slow rotation
        self.begin_ambient_camera_rotation(rate=0.2)
        self.wait(5)
        self.stop_ambient_camera_rotation()

        # Summary
        summary = Text(
            f"Total: {len(calls)} calls across {len(modules)} modules",
            font_size=24,
            color=GREEN
        )
        summary.to_edge(DOWN)
        self.add_fixed_in_frame_mobjects(summary)
        self.play(FadeIn(summary), run_time=1)

        self.wait(2)

        # Fade out
        self.play(
            FadeOut(title),
            FadeOut(summary),
            FadeOut(module_boxes),
            run_time=1
        )


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        trace_file = sys.argv[1]
        scene = SimpleTraceScene(trace_file=trace_file)
        scene.render()
    else:
        print("Usage: python simple_trace_viz.py <trace_file.json>")
