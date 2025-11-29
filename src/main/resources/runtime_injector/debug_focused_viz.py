"""
DEPRECATED: This file has been superseded by ultimate_architecture_viz.py

The debug visualization functionality has been integrated into ultimate_architecture_viz.py
(Phase 4: Error Visualization) which is the single active engine used by ManimAutoRenderer.kt.

DO NOT USE - Kept for reference only.
================================================================================
"""

from logging_config import setup_logger
logger = setup_logger(__name__)

"""
Debug-Focused Visualization Engine

THIS IS A DEBUGGING TOOL - visualizations must reveal ROOT CAUSES of bugs:
- Error propagation paths (where did the exception originate?)
- Performance bottlenecks (which calls are slow? why?)
- Data corruption (type mismatches, null values, dimension errors)
- Race conditions (parallel execution conflicts)
- Memory issues (retention patterns, circular references)
- Dead code (never-executed paths highlighted)
- Unexpected branches (assertions failed, edge cases hit)
"""

import json
import numpy as np
from manim import *
from collections import defaultdict
from typing import Dict, List, Tuple, Any, Optional
import re

# Import LLM explainer for intelligent concept explanations
try:
    from llm_explainer import get_llm_explainer
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False


class DebugTraceAnalyzer:
    """Analyzes trace data to find bugs and issues."""

    def __init__(self, trace_data: Dict):
        self.trace_data = trace_data
        self.errors = []
        self.bottlenecks = []
        self.anomalies = []
        self.dead_code = []
        self.race_conditions = []

    def analyze(self):
        """Run all debug analyses."""
        self.find_errors()
        self.find_bottlenecks()
        self.find_anomalies()
        self.find_dead_code()
        self.find_race_conditions()

        return {
            'errors': self.errors,
            'bottlenecks': self.bottlenecks,
            'anomalies': self.anomalies,
            'dead_code': self.dead_code,
            'race_conditions': self.race_conditions
        }

    def find_errors(self):
        """Find exceptions and error propagation paths."""
        calls = self.trace_data.get('calls', [])

        for call in calls:
            # Look for error indicators
            return_val = str(call.get('return_value', ''))
            error_keywords = ['error', 'exception', 'none', 'null', 'nan', 'inf']

            if any(kw in return_val.lower() for kw in error_keywords):
                self.errors.append({
                    'call_id': call.get('call_id'),
                    'function': call.get('function'),
                    'module': call.get('module'),
                    'type': 'error_return',
                    'value': return_val,
                    'timestamp': call.get('timestamp'),
                    'file': call.get('file_path'),
                    'line': call.get('line_number')
                })

            # Look for failed assertions or validations
            func_name = call.get('function', '').lower()
            if 'assert' in func_name or 'validate' in func_name or 'check' in func_name:
                self.errors.append({
                    'call_id': call.get('call_id'),
                    'function': call.get('function'),
                    'type': 'validation',
                    'timestamp': call.get('timestamp')
                })

    def find_bottlenecks(self):
        """Find slow execution paths and performance issues."""
        calls = self.trace_data.get('calls', [])

        # Calculate call durations
        call_times = {}
        for call in calls:
            if call.get('type') == 'call':
                call_times[call.get('call_id')] = call.get('timestamp')
            elif call.get('type') == 'return':
                call_id = call.get('call_id')
                if call_id in call_times:
                    duration = call.get('timestamp') - call_times[call_id]
                    call_times[call_id] = duration

        # Find unusually slow calls (> 2 std deviations from mean)
        if call_times:
            durations = [d for d in call_times.values() if isinstance(d, float)]
            if durations:
                mean_duration = np.mean(durations)
                std_duration = np.std(durations)
                threshold = mean_duration + 2 * std_duration

                for call_id, duration in call_times.items():
                    if isinstance(duration, float) and duration > threshold:
                        # Find the call details
                        call_details = next((c for c in calls if c.get('call_id') == call_id), None)
                        if call_details:
                            self.bottlenecks.append({
                                'call_id': call_id,
                                'function': call_details.get('function'),
                                'module': call_details.get('module'),
                                'duration': duration,
                                'threshold': threshold,
                                'slowness_factor': duration / mean_duration,
                                'file': call_details.get('file_path'),
                                'line': call_details.get('line_number')
                            })

    def find_anomalies(self):
        """Find unexpected behavior and data anomalies."""
        calls = self.trace_data.get('calls', [])

        # Track function call frequencies
        call_counts = defaultdict(int)
        for call in calls:
            if call.get('type') == 'call':
                func_key = f"{call.get('module')}.{call.get('function')}"
                call_counts[func_key] += 1

        # Find functions called unusually many times (potential loops/recursion issues)
        if call_counts:
            mean_count = np.mean(list(call_counts.values()))
            std_count = np.std(list(call_counts.values()))
            threshold = mean_count + 3 * std_count

            for func_key, count in call_counts.items():
                if count > threshold and count > 10:  # Must be called > 10 times and > 3 std
                    self.anomalies.append({
                        'type': 'excessive_calls',
                        'function': func_key,
                        'count': count,
                        'expected': mean_count,
                        'severity': count / mean_count
                    })

        # Find type mismatches in parameters
        # (This would require parameter type tracking in the trace data)

    def find_dead_code(self):
        """Find code paths that were never executed."""
        # This requires comparing trace with static analysis
        # For now, flag functions that appear in module but never called
        calls = self.trace_data.get('calls', [])
        called_functions = set()

        for call in calls:
            if call.get('type') == 'call':
                func_key = f"{call.get('module')}.{call.get('function')}"
                called_functions.add(func_key)

        # Note: Complete dead code detection requires static analysis
        # This is a simplified version

    def find_race_conditions(self):
        """Find potential race conditions in parallel execution."""
        calls = self.trace_data.get('calls', [])

        # Track overlapping function executions
        active_calls = {}  # call_id -> (start_time, function)

        for call in calls:
            call_id = call.get('call_id')
            timestamp = call.get('timestamp')

            if call.get('type') == 'call':
                active_calls[call_id] = (timestamp, call.get('function'))
            elif call.get('type') == 'return':
                if call_id in active_calls:
                    start_time, func_name = active_calls[call_id]

                    # Check for overlapping calls to same function
                    for other_id, (other_start, other_func) in active_calls.items():
                        if other_id != call_id and other_func == func_name:
                            # Potential race condition
                            self.race_conditions.append({
                                'type': 'concurrent_access',
                                'function': func_name,
                                'call_id_1': call_id,
                                'call_id_2': other_id,
                                'overlap_start': max(start_time, other_start),
                                'overlap_end': timestamp
                            })

                    del active_calls[call_id]


class DebugVisualizationScene(ThreeDScene):
    """
    Debug-focused 3D visualization that highlights issues and root causes.

    Visual Language:
    - RED = Errors, exceptions, failures
    - ORANGE = Warnings, slow performance
    - YELLOW = Anomalies, unexpected behavior
    - BLUE = Normal execution
    - PURPLE = Race conditions, concurrency issues
    - GRAY = Dead code, unused paths
    """

    def __init__(self, trace_file, **kwargs):
        super().__init__(**kwargs)
        self.trace_file = trace_file
        self.trace_data = None
        self.analyzer = None
        self.debug_results = None

    def construct(self):
        # Load and analyze trace
        self.load_trace()
        self.analyze_for_bugs()

        # Get LLM explainer if available
        llm = get_llm_explainer() if LLM_AVAILABLE else None

        # Setup camera
        self.set_camera_orientation(phi=70 * DEGREES, theta=-45 * DEGREES)

        # Title with severity indicator
        severity = self.get_severity_level()
        title_color = RED if severity == 'critical' else ORANGE if severity == 'warning' else GREEN
        title = Text(f"Debug Analysis: {severity.upper()}", font_size=36, color=title_color)
        title.to_edge(UP)
        self.add_fixed_in_frame_mobjects(title)
        self.play(Write(title))

        # LLM-powered execution pattern analysis
        if llm:
            pattern_explanation = llm.analyze_execution_pattern(self.trace_data)
            self.show_llm_explanation("What This Code Does", pattern_explanation)
            self.wait(2)

        # Show debug summary
        self.show_debug_summary()
        self.wait(1)

        # Visualize errors first (most critical)
        if self.debug_results['errors']:
            # LLM explains error propagation
            if llm and self.debug_results['errors']:
                error_funcs = [e.get('function', 'unknown') for e in self.debug_results['errors'][:3]]
                error_explanation = llm.explain_error_propagation(error_funcs)
                self.show_llm_explanation("Error Propagation", error_explanation)
                self.wait(1)

            self.visualize_errors()
            self.wait(1)

        # Then bottlenecks
        if self.debug_results['bottlenecks']:
            # LLM explains bottleneck cause
            if llm and self.debug_results['bottlenecks']:
                bottleneck = self.debug_results['bottlenecks'][0]
                func = bottleneck.get('function', 'unknown')
                duration = bottleneck.get('duration', 0)
                context = {'slowness_factor': bottleneck.get('slowness_factor', 1)}
                bottleneck_explanation = llm.explain_bottleneck(func, duration, context)
                self.show_llm_explanation("Why Is It Slow?", bottleneck_explanation)
                self.wait(1)

            self.visualize_bottlenecks()
            self.wait(1)

        # Then anomalies
        if self.debug_results['anomalies']:
            self.visualize_anomalies()
            self.wait(1)

        # Finally race conditions
        if self.debug_results['race_conditions']:
            self.visualize_race_conditions()
            self.wait(1)

        self.wait(2)

    def show_llm_explanation(self, title: str, explanation: str):
        """Display LLM-generated explanation as subtitle."""
        # Wrap text to fit screen (max 80 chars per line)
        words = explanation.split()
        lines = []
        current_line = []
        current_length = 0

        for word in words:
            if current_length + len(word) + 1 > 80:
                lines.append(' '.join(current_line))
                current_line = [word]
                current_length = len(word)
            else:
                current_line.append(word)
                current_length += len(word) + 1

        if current_line:
            lines.append(' '.join(current_line))

        # Display title
        title_text = Text(title, font_size=18, color=YELLOW)
        title_text.to_edge(UP).shift(DOWN * 1.2)
        self.add_fixed_in_frame_mobjects(title_text)
        self.play(FadeIn(title_text), run_time=0.3)

        # Display explanation lines
        y_pos = 1.0
        for line in lines[:4]:  # Max 4 lines
            line_text = Text(line, font_size=12, color=WHITE)
            line_text.move_to(np.array([0, y_pos, 0]))
            line_text.rotate(PI/2, axis=RIGHT)
            self.play(FadeIn(line_text), run_time=0.2)
            y_pos -= 0.4

        # Fade out after display
        self.wait(2)
        self.play(FadeOut(title_text), *[FadeOut(obj) for obj in self.mobjects if isinstance(obj, Text)])

    def load_trace(self):
        """Load trace JSON."""
        with open(self.trace_file, 'r') as f:
            self.trace_data = json.load(f)

    def analyze_for_bugs(self):
        """Analyze trace for bugs and issues."""
        self.analyzer = DebugTraceAnalyzer(self.trace_data)
        self.debug_results = self.analyzer.analyze()

    def get_severity_level(self):
        """Determine overall severity level."""
        if self.debug_results['errors']:
            return 'critical'
        elif self.debug_results['bottlenecks'] or self.debug_results['race_conditions']:
            return 'warning'
        elif self.debug_results['anomalies']:
            return 'info'
        return 'ok'

    def show_debug_summary(self):
        """Show summary of found issues."""
        summary_text = f"""
Errors: {len(self.debug_results['errors'])}
Bottlenecks: {len(self.debug_results['bottlenecks'])}
Anomalies: {len(self.debug_results['anomalies'])}
Race Conditions: {len(self.debug_results['race_conditions'])}
        """.strip()

        summary = Text(summary_text, font_size=18, color=WHITE)
        summary.to_edge(LEFT).shift(DOWN * 0.5)
        self.add_fixed_in_frame_mobjects(summary)
        self.play(FadeIn(summary))

    def visualize_errors(self):
        """Visualize error propagation paths."""
        subtitle = Text("ERROR PROPAGATION", font_size=24, color=RED)
        subtitle.to_edge(UP).shift(DOWN * 1)
        self.add_fixed_in_frame_mobjects(subtitle)
        self.play(Write(subtitle))

        # Create error chain visualization
        error_chain = VGroup()
        y_pos = 1

        for i, error in enumerate(self.debug_results['errors'][:5]):  # Show top 5
            # Error indicator (pulsing red sphere)
            error_node = Sphere(radius=0.2, color=RED)
            error_node.set_opacity(0.9)
            error_node.move_to(np.array([0, y_pos, 0]))

            # Error label
            error_label = Text(
                f"{error.get('function', 'unknown')}\n{error.get('type', 'error')}",
                font_size=14,
                color=RED
            )
            error_label.move_to(np.array([0, y_pos, 0]) + RIGHT * 1)
            error_label.rotate(PI/2, axis=RIGHT)

            # File/line info
            file_info = Text(
                f"{error.get('file', 'unknown')}:{error.get('line', '?')}",
                font_size=10,
                color=YELLOW
            )
            file_info.move_to(np.array([0, y_pos, 0]) + RIGHT * 2.5)
            file_info.rotate(PI/2, axis=RIGHT)

            error_chain.add(error_node, error_label, file_info)

            # Animate with pulsing red warning
            self.play(
                GrowFromCenter(error_node),
                FadeIn(error_label),
                FadeIn(file_info),
                run_time=0.4
            )

            # Pulse to draw attention
            self.play(
                error_node.animate(rate_func=there_and_back).scale(1.3),
                run_time=0.3
            )

            y_pos -= 1.2

        self.wait(0.5)
        self.play(FadeOut(error_chain), FadeOut(subtitle))

    def visualize_bottlenecks(self):
        """Visualize performance bottlenecks."""
        subtitle = Text("PERFORMANCE BOTTLENECKS", font_size=24, color=ORANGE)
        subtitle.to_edge(UP).shift(DOWN * 1)
        self.add_fixed_in_frame_mobjects(subtitle)
        self.play(Write(subtitle))

        # Create bottleneck visualization (height = slowness)
        bottleneck_viz = VGroup()
        x_pos = -4

        for bottleneck in self.debug_results['bottlenecks'][:8]:  # Show top 8
            slowness = bottleneck.get('slowness_factor', 1)
            height = min(slowness / 10, 2)  # Cap height at 2

            # Bar showing slowness
            bar = Prism(dimensions=[0.3, height, 0.3])
            bar.set_color(interpolate_color(YELLOW, RED, min(slowness / 20, 1)))
            bar.set_opacity(0.8)
            bar.move_to(np.array([x_pos, height/2 - 1, 0]))

            # Function label
            func_label = Text(
                bottleneck.get('function', 'unknown')[:15],
                font_size=10,
                color=ORANGE
            )
            func_label.move_to(np.array([x_pos, -1.5, 0]))
            func_label.rotate(PI/2, axis=RIGHT)

            # Slowness factor label
            factor_label = Text(
                f"{slowness:.1f}x",
                font_size=12,
                color=RED
            )
            factor_label.move_to(np.array([x_pos, height - 0.5, 0]))
            factor_label.rotate(PI/2, axis=RIGHT)

            bottleneck_viz.add(bar, func_label, factor_label)

            self.play(
                GrowFromEdge(bar, DOWN),
                FadeIn(func_label),
                FadeIn(factor_label),
                run_time=0.3
            )

            x_pos += 1.2

        self.wait(0.5)
        self.play(FadeOut(bottleneck_viz), FadeOut(subtitle))

    def visualize_anomalies(self):
        """Visualize anomalies and unexpected behavior."""
        subtitle = Text("ANOMALIES DETECTED", font_size=24, color=YELLOW)
        subtitle.to_edge(UP).shift(DOWN * 1)
        self.add_fixed_in_frame_mobjects(subtitle)
        self.play(Write(subtitle))

        # Show excessive call loops
        for anomaly in self.debug_results['anomalies'][:3]:
            if anomaly.get('type') == 'excessive_calls':
                # Spiral showing repeated calls
                spiral = self.create_call_spiral(
                    anomaly.get('count', 10),
                    anomaly.get('function', 'unknown')
                )
                self.play(Create(spiral), run_time=2)
                self.wait(0.5)
                self.play(FadeOut(spiral))

        self.play(FadeOut(subtitle))

    def create_call_spiral(self, call_count, function_name):
        """Create spiral showing excessive function calls."""
        num_turns = min(call_count / 20, 5)
        points_per_turn = 30
        total_points = int(num_turns * points_per_turn)

        t = np.linspace(0, num_turns * 2 * PI, total_points)
        radius = 2 - t / (2 * PI * num_turns) * 1.5
        height = t / (2 * PI) * 0.3

        x = radius * np.cos(t)
        y = radius * np.sin(t)
        z = height

        points = np.column_stack([x, y, z])

        spiral = VMobject()
        spiral.set_points_as_corners([*points])
        spiral.set_color(YELLOW)
        spiral.set_stroke(width=3)

        return spiral

    def visualize_race_conditions(self):
        """Visualize potential race conditions."""
        subtitle = Text("RACE CONDITIONS", font_size=24, color=PURPLE)
        subtitle.to_edge(UP).shift(DOWN * 1)
        self.add_fixed_in_frame_mobjects(subtitle)
        self.play(Write(subtitle))

        # Show conflicting parallel accesses
        for race in self.debug_results['race_conditions'][:3]:
            # Two spheres colliding
            sphere1 = Sphere(radius=0.15, color=PURPLE)
            sphere2 = Sphere(radius=0.15, color=PURPLE)

            sphere1.move_to(LEFT * 2)
            sphere2.move_to(RIGHT * 2)

            self.play(GrowFromCenter(sphere1), GrowFromCenter(sphere2))

            # Move towards each other (conflict)
            self.play(
                sphere1.animate.move_to(ORIGIN + LEFT * 0.1),
                sphere2.animate.move_to(ORIGIN + RIGHT * 0.1),
                run_time=1
            )

            # Flash to show conflict
            self.play(
                sphere1.animate.set_color(RED),
                sphere2.animate.set_color(RED),
                run_time=0.2
            )

            self.play(FadeOut(sphere1), FadeOut(sphere2))

        self.play(FadeOut(subtitle))


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        logger.info("Usage: python debug_focused_viz.py <trace_json_file>")
        sys.exit(1)

    trace_file = sys.argv[1]

    from manim import config
    config.quality = 'medium_quality'
    config.output_file = 'debug_analysis'

    scene = DebugVisualizationScene(trace_file)
    scene.render()

    logger.info(f"Debug visualization saved")
