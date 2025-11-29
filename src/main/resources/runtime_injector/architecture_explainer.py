from logging_config import setup_logger
logger = setup_logger(__name__)

"""
Architecture Visual Explainer for Code Architects

Automatically generates visual architecture diagrams from runtime traces:
- Discovered architecture (what the code ACTUALLY does at runtime)
- Module dependencies and coupling
- Data flow paths
- Architectural smells and anti-patterns
- Recommendations for refactoring

Purpose: Help architects understand the REAL architecture vs. intended design
"""

import json
import numpy as np
from manim import *
from collections import defaultdict
from typing import Dict, List, Tuple, Set
import re


class ArchitectureExtractor:
    """Extracts architecture from runtime trace data."""

    def __init__(self, trace_data: Dict):
        self.trace_data = trace_data
        self.modules = defaultdict(lambda: {
            'functions': set(),
            'calls_to': defaultdict(int),  # module -> count
            'calls_from': defaultdict(int),
            'total_calls': 0,
            'total_time': 0
        })
        self.layers = []  # Architectural layers
        self.components = {}  # Logical components
        self.anti_patterns = []

    def extract(self):
        """Extract architecture from trace."""
        self.analyze_modules()
        self.detect_layers()
        self.detect_components()
        self.find_anti_patterns()

        return {
            'modules': dict(self.modules),
            'layers': self.layers,
            'components': self.components,
            'anti_patterns': self.anti_patterns
        }

    def analyze_modules(self):
        """Analyze module structure and dependencies."""
        calls = self.trace_data.get('calls', [])
        call_times = {}

        for call in calls:
            module = call.get('module', 'unknown')
            if not module:
                continue

            function = call.get('function', '')
            call_id = call.get('call_id', '')

            if call.get('type') == 'call':
                self.modules[module]['functions'].add(function)
                self.modules[module]['total_calls'] += 1
                call_times[call_id] = call.get('timestamp', 0)

            elif call.get('type') == 'return':
                if call_id in call_times:
                    duration = call.get('timestamp', 0) - call_times[call_id]
                    self.modules[module]['total_time'] += duration

        # Analyze cross-module dependencies
        for call in calls:
            if call.get('type') != 'call':
                continue

            parent_id = call.get('parent_id')
            if not parent_id:
                continue

            # Find parent module
            parent_call = next((c for c in calls if c.get('call_id') == parent_id), None)
            if not parent_call:
                continue

            parent_module = parent_call.get('module', 'unknown')
            current_module = call.get('module', 'unknown')

            if parent_module != current_module:
                self.modules[parent_module]['calls_to'][current_module] += 1
                self.modules[current_module]['calls_from'][parent_module] += 1

    def detect_layers(self):
        """Detect architectural layers from dependencies."""
        # Simple layer detection: modules that don't call anyone are bottom layer
        module_levels = {}

        def get_level(module):
            if module in module_levels:
                return module_levels[module]

            calls_to = self.modules[module]['calls_to']
            if not calls_to:
                module_levels[module] = 0
                return 0

            max_child_level = max(get_level(dep) for dep in calls_to.keys())
            module_levels[module] = max_child_level + 1
            return module_levels[module]

        for module in self.modules.keys():
            get_level(module)

        # Group by level
        layers_dict = defaultdict(list)
        for module, level in module_levels.items():
            layers_dict[level].append(module)

        # Convert to list of layers (bottom to top)
        max_level = max(module_levels.values()) if module_levels else 0
        self.layers = [layers_dict[i] for i in range(max_level + 1)]

    def detect_components(self):
        """Detect logical components (highly cohesive module groups)."""
        # Simple component detection: modules with high mutual interaction
        # Use prefix-based grouping for now (e.g., "models.*" = models component)
        component_prefixes = defaultdict(list)

        for module in self.modules.keys():
            prefix = module.split('.')[0] if '.' in module else module
            component_prefixes[prefix].append(module)

        self.components = dict(component_prefixes)

    def find_anti_patterns(self):
        """Find architectural anti-patterns."""
        # Circular dependencies
        for module_a in self.modules.keys():
            for module_b in self.modules[module_a]['calls_to'].keys():
                if module_a in self.modules[module_b]['calls_to']:
                    self.anti_patterns.append({
                        'type': 'circular_dependency',
                        'modules': [module_a, module_b],
                        'severity': 'high',
                        'recommendation': f"Break circular dependency between {module_a} and {module_b}"
                    })

        # God modules (too many dependencies)
        for module, data in self.modules.items():
            num_deps = len(data['calls_to'])
            if num_deps > 10:  # Arbitrary threshold
                self.anti_patterns.append({
                    'type': 'god_module',
                    'module': module,
                    'num_dependencies': num_deps,
                    'severity': 'medium',
                    'recommendation': f"Module {module} has {num_deps} dependencies. Consider splitting."
                })

        # Unused modules (never called)
        # (This would require static analysis for complete picture)


class ArchitectureExplainerScene(ThreeDScene):
    """
    Visual architecture explainer for code architects.

    Shows:
    1. Discovered runtime architecture
    2. Module dependencies (with metrics)
    3. Architectural layers
    4. Anti-patterns and smells
    5. Recommendations
    """

    def __init__(self, trace_file, **kwargs):
        super().__init__(**kwargs)
        self.trace_file = trace_file
        self.trace_data = None
        self.architecture = None
        self.module_positions = {}

    def construct(self):
        # Load and extract architecture
        self.load_trace()
        self.extract_architecture()

        # Setup camera
        self.set_camera_orientation(phi=70 * DEGREES, theta=-45 * DEGREES)
        self.begin_ambient_camera_rotation(rate=0.05)

        # Title
        title = Text("Runtime Architecture Analysis", font_size=42, color=BLUE)
        title.to_edge(UP)
        self.add_fixed_in_frame_mobjects(title)
        self.play(Write(title))
        self.wait(0.5)

        # Show discovered architecture
        self.visualize_architecture()
        self.wait(2)

        # Show dependencies
        self.visualize_dependencies()
        self.wait(2)

        # Show anti-patterns
        if self.architecture['anti_patterns']:
            self.visualize_anti_patterns()
            self.wait(2)

        # Show recommendations
        self.show_recommendations()
        self.wait(2)

    def load_trace(self):
        """Load trace JSON."""
        with open(self.trace_file, 'r') as f:
            self.trace_data = json.load(f)

    def extract_architecture(self):
        """Extract architecture from trace."""
        extractor = ArchitectureExtractor(self.trace_data)
        self.architecture = extractor.extract()

    def visualize_architecture(self):
        """Visualize discovered architecture as layered 3D structure."""
        subtitle = Text("Discovered Architecture (Runtime)", font_size=24, color=GREEN)
        subtitle.to_edge(UP).shift(DOWN * 0.8)
        self.add_fixed_in_frame_mobjects(subtitle)
        self.play(FadeIn(subtitle))

        layers = self.architecture['layers']
        layer_spacing = 2.5
        module_spacing = 1.5

        # Visualize each layer
        for layer_idx, layer_modules in enumerate(layers):
            y_pos = layer_idx * layer_spacing - len(layers) * layer_spacing / 2

            # Layer label
            layer_label = Text(f"Layer {layer_idx}", font_size=18, color=YELLOW)
            layer_label.move_to(np.array([-5, y_pos, 0]))
            layer_label.rotate(PI/2, axis=RIGHT)
            self.add_fixed_in_frame_mobjects(layer_label)
            self.play(FadeIn(layer_label), run_time=0.2)

            # Visualize modules in this layer
            for mod_idx, module in enumerate(layer_modules[:6]):  # Limit to 6 modules per layer
                x_pos = (mod_idx - len(layer_modules) / 2) * module_spacing

                # Module box
                module_data = self.architecture['modules'][module]
                num_functions = len(module_data['functions'])

                # Size based on number of functions
                box_scale = 0.3 + min(num_functions / 10, 0.7)
                box = Cube(side_length=box_scale)

                # Color based on layer
                layer_colors = [GREEN, BLUE, PURPLE, ORANGE, RED]
                box.set_color(layer_colors[layer_idx % len(layer_colors)])
                box.set_opacity(0.7)
                box.set_sheen(0.5, direction=UP)
                box.move_to(np.array([x_pos, y_pos, 0]))

                # Module name
                module_name = module.split('.')[-1][:12]
                label = Text(module_name, font_size=10, color=WHITE)
                label.move_to(np.array([x_pos, y_pos - box_scale - 0.3, 0]))
                label.rotate(PI/2, axis=RIGHT)

                # Function count
                func_count = Text(f"{num_functions} funcs", font_size=8, color=YELLOW)
                func_count.move_to(np.array([x_pos, y_pos + box_scale + 0.2, 0]))
                func_count.rotate(PI/2, axis=RIGHT)

                self.module_positions[module] = np.array([x_pos, y_pos, 0])

                self.play(
                    GrowFromCenter(box),
                    FadeIn(label),
                    FadeIn(func_count),
                    run_time=0.3
                )

        self.wait(0.5)
        self.play(FadeOut(subtitle))

    def visualize_dependencies(self):
        """Visualize module dependencies as flowing connections."""
        subtitle = Text("Module Dependencies", font_size=24, color=BLUE)
        subtitle.to_edge(UP).shift(DOWN * 0.8)
        self.add_fixed_in_frame_mobjects(subtitle)
        self.play(FadeIn(subtitle))

        dependencies = VGroup()

        # Draw top N dependencies
        all_deps = []
        for module, data in self.architecture['modules'].items():
            for target, count in data['calls_to'].items():
                if module in self.module_positions and target in self.module_positions:
                    all_deps.append((module, target, count))

        # Sort by count and take top 20
        all_deps.sort(key=lambda x: x[2], reverse=True)
        top_deps = all_deps[:20]

        for source, target, count in top_deps:
            start_pos = self.module_positions[source]
            end_pos = self.module_positions[target]

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

            # Call count label
            mid_point = (start_pos + end_pos) / 2 + UP * 0.5
            count_label = Text(f"{count}", font_size=8, color=YELLOW)
            count_label.move_to(mid_point)
            count_label.rotate(PI/2, axis=RIGHT)
            dependencies.add(count_label)

        # Animate dependencies appearing
        self.play(*[Create(dep) for dep in dependencies], run_time=2)
        self.wait(1)
        self.play(FadeOut(dependencies), FadeOut(subtitle))

    def visualize_anti_patterns(self):
        """Visualize anti-patterns with warnings."""
        subtitle = Text("Anti-Patterns Detected!", font_size=28, color=RED)
        subtitle.to_edge(UP).shift(DOWN * 0.8)
        self.add_fixed_in_frame_mobjects(subtitle)
        self.play(Write(subtitle))

        warnings = VGroup()
        y_pos = 1.5

        for anti_pattern in self.architecture['anti_patterns'][:5]:
            # Warning symbol (flashing red triangle)
            warning = RegularPolygon(n=3, color=RED, fill_opacity=0.8)
            warning.scale(0.3)
            warning.move_to(np.array([-3, y_pos, 0]))

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

            issue_label = Text(desc, font_size=12, color=RED)
            issue_label.move_to(np.array([0, y_pos, 0]))
            issue_label.rotate(PI/2, axis=RIGHT)

            # Severity indicator
            severity_colors = {'high': RED, 'medium': ORANGE, 'low': YELLOW}
            severity_label = Text(
                severity.upper(),
                font_size=10,
                color=severity_colors.get(severity, YELLOW)
            )
            severity_label.move_to(np.array([3, y_pos, 0]))
            severity_label.rotate(PI/2, axis=RIGHT)

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

    def show_recommendations(self):
        """Show architectural recommendations."""
        subtitle = Text("Recommendations", font_size=28, color=GREEN)
        subtitle.to_edge(UP).shift(DOWN * 0.8)
        self.add_fixed_in_frame_mobjects(subtitle)
        self.play(Write(subtitle))

        recommendations = VGroup()
        y_pos = 1.5

        # Generate recommendations from anti-patterns
        for anti_pattern in self.architecture['anti_patterns'][:4]:
            recommendation = anti_pattern.get('recommendation', '')

            if recommendation:
                # Checkmark
                check = Text("✓", font_size=20, color=GREEN)
                check.move_to(np.array([-3, y_pos, 0]))
                check.rotate(PI/2, axis=RIGHT)

                # Recommendation text
                rec_label = Text(recommendation[:50], font_size=11, color=WHITE)
                rec_label.move_to(np.array([0.5, y_pos, 0]))
                rec_label.rotate(PI/2, axis=RIGHT)

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
            check = Text("•", font_size=20, color=BLUE)
            check.move_to(np.array([-3, y_pos, 0]))
            check.rotate(PI/2, axis=RIGHT)

            rec_label = Text(rec_text, font_size=11, color=WHITE)
            rec_label.move_to(np.array([0.5, y_pos, 0]))
            rec_label.rotate(PI/2, axis=RIGHT)

            recommendations.add(check, rec_label)

            self.play(
                FadeIn(check),
                FadeIn(rec_label),
                run_time=0.3
            )

            y_pos -= 0.7

        self.wait(2)
        self.play(FadeOut(recommendations), FadeOut(subtitle))


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        logger.info("Usage: python architecture_explainer.py <trace_json_file>")
        sys.exit(1)

    trace_file = sys.argv[1]

    from manim import config
    config.quality = 'medium_quality'
    config.output_file = 'architecture_analysis'

    scene = ArchitectureExplainerScene(trace_file)
    scene.render()

    logger.info(f"Architecture visualization saved")
