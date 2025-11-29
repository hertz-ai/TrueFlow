"""
Procedural 3D Trace Visualizer

Analyzes trace data to automatically generate appropriate 3D visualizations:
- Detects patterns (neural networks, data flow, recursion, etc.)
- Generates procedural 3D scenes matching the execution pattern
- Creates dynamic animations showing data transformations
"""

import json
import numpy as np
from manim import *
from collections import defaultdict

# Import logging configuration
from logging_config import get_procedural_viz_logger

# Initialize logger
logger = get_procedural_viz_logger()

# Import animation standards
try:
    from animation_standards import AnimationTiming, AnimationColors
    STANDARDS_AVAILABLE = True
except ImportError:
    STANDARDS_AVAILABLE = False
    logger.warning("Animation standards not available. Using hardcoded defaults.")


class ProceduralTraceScene(ThreeDScene):
    """
    Automatically generates 3D visualization based on trace analysis.
    Detects execution patterns and creates appropriate visual metaphors.
    """

    def __init__(self, trace_file, **kwargs):
        super().__init__(**kwargs)
        self.trace_file = trace_file
        self.trace_data = None
        self.execution_graph = None

    def construct(self):
        # Load and analyze trace
        self.load_trace()
        self.analyze_execution_pattern()

        # Setup 3D camera
        self.set_camera_orientation(phi=70 * DEGREES, theta=-45 * DEGREES)
        self.begin_ambient_camera_rotation(rate=0.1)

        # Generate procedural visualization
        if self.is_neural_network_pattern():
            self.visualize_as_neural_network()
        elif self.is_recursive_pattern():
            self.visualize_as_fractal()
        elif self.is_pipeline_pattern():
            self.visualize_as_data_pipeline()
        else:
            self.visualize_as_execution_graph()

    def load_trace(self):
        """Load trace JSON."""
        with open(self.trace_file, 'r') as f:
            self.trace_data = json.load(f)

    def analyze_execution_pattern(self):
        """Analyze trace to detect execution patterns."""
        calls = self.trace_data.get('calls', [])

        # Build execution graph
        self.execution_graph = {
            'nodes': {},
            'edges': [],
            'modules': defaultdict(list),
            'call_counts': defaultdict(int),
            'max_depth': 0
        }

        for call in calls:
            func_key = f"{call.get('module', '')}.{call.get('function', '')}"
            call_id = call.get('call_id', '')
            depth = call.get('depth', 0)

            self.execution_graph['nodes'][call_id] = {
                'function': func_key,
                'depth': depth,
                'timestamp': call.get('timestamp', 0)
            }

            self.execution_graph['modules'][call.get('module', '')].append(call_id)
            self.execution_graph['call_counts'][func_key] += 1
            self.execution_graph['max_depth'] = max(self.execution_graph['max_depth'], depth)

            # Build edges from parent-child relationships
            parent_id = call.get('parent_id')
            if parent_id:
                self.execution_graph['edges'].append((parent_id, call_id))

    def is_neural_network_pattern(self):
        """Detect if this is a neural network execution."""
        nn_keywords = ['forward', 'backward', 'layer', 'attention', 'encoder', 'decoder']
        functions = [node['function'] for node in self.execution_graph['nodes'].values()]

        matches = sum(1 for func in functions if any(kw in func.lower() for kw in nn_keywords))
        return matches > len(functions) * 0.3

    def is_recursive_pattern(self):
        """Detect recursive calls."""
        # Check for functions calling themselves
        for (parent, child) in self.execution_graph['edges']:
            parent_func = self.execution_graph['nodes'].get(parent, {}).get('function', '')
            child_func = self.execution_graph['nodes'].get(child, {}).get('function', '')
            if parent_func == child_func:
                return True
        return False

    def is_pipeline_pattern(self):
        """Detect sequential pipeline (low branching factor)."""
        avg_children = len(self.execution_graph['edges']) / max(len(self.execution_graph['nodes']), 1)
        return avg_children < 1.5 and len(self.execution_graph['nodes']) > 3

    def visualize_as_neural_network(self):
        """Visualize as 3D neural network with flowing activations."""
        title = Text("Neural Network Execution", font_size=42, color=BLUE)
        title.to_edge(UP)
        self.add_fixed_in_frame_mobjects(title)
        self.play(Write(title))

        # Extract unique modules as layers
        modules = list(self.execution_graph['modules'].keys())[:5]  # Max 5 layers

        layers = []
        layer_positions = np.linspace(-4, 4, len(modules))

        for i, module in enumerate(modules):
            layer_name = module.split('.')[-1]
            num_neurons = min(len(self.execution_graph['modules'][module]), 12)

            layer = self.create_neural_layer(
                position=RIGHT * layer_positions[i],
                neurons=num_neurons,
                color=self.get_color_for_layer(i, len(modules)),
                label=layer_name
            )
            layers.append(layer)

        # Animate layer creation
        layer_create_time = AnimationTiming.LAYER_CREATE if STANDARDS_AVAILABLE else 0.4
        for layer_group, label in layers:
            self.play(
                *[GrowFromCenter(neuron) for neuron in layer_group],
                FadeIn(label),
                run_time=layer_create_time
            )

        self.wait(0.5)

        # Animate data flow
        self.animate_network_activations(layers)

    def create_neural_layer(self, position, neurons, color, label):
        """Create 3D neural layer."""
        layer = VGroup()

        rows = int(np.sqrt(neurons))
        cols = int(np.ceil(neurons / rows))

        for i in range(neurons):
            row = i // cols
            col = i % cols

            neuron = Sphere(radius=0.12, resolution=(8, 8))
            neuron.set_color(color)
            neuron.set_opacity(0.8)
            neuron.set_sheen(0.5, direction=UP)

            x_offset = (col - cols/2) * 0.35
            y_offset = (row - rows/2) * 0.35
            neuron.move_to(position + RIGHT * x_offset + UP * y_offset)

            layer.add(neuron)

        layer_label = Text(label[:15], font_size=18, color=color)
        layer_label.move_to(position + DOWN * 2)
        layer_label.rotate(PI/2, axis=RIGHT)

        return (layer, layer_label)

    def animate_network_activations(self, layers):
        """Animate activations flowing through network."""
        num_particles = 10

        for i in range(len(layers) - 1):
            current_layer, _ = layers[i]
            next_layer, _ = layers[i + 1]

            particles = VGroup()
            for j in range(num_particles):
                particle = Sphere(radius=0.04, resolution=(6, 6))
                particle.set_color(YELLOW)
                particle.set_opacity(0.9)
                particle.move_to(current_layer[j % len(current_layer)].get_center())
                particles.add(particle)

            # Animate particle flow
            animations = []
            for j, particle in enumerate(particles):
                target = next_layer[j % len(next_layer)]
                animations.append(particle.animate.move_to(target.get_center()))
                animations.append(target.animate.set_opacity(1).scale(1.15))

            activation_time = AnimationTiming.LAYER_ACTIVATION if STANDARDS_AVAILABLE else 0.6
            self.play(*animations, run_time=activation_time, rate_func=smooth)

            # Reset target neurons
            for neuron in next_layer:
                self.play(neuron.animate.set_opacity(0.8).scale(1/1.15), run_time=0.1)

            # Remove particles
            self.play(*[FadeOut(p) for p in particles], run_time=0.2)

    def visualize_as_fractal(self):
        """Visualize recursive execution as fractal tree."""
        title = Text("Recursive Execution Tree", font_size=42, color=GREEN)
        title.to_edge(UP)
        self.add_fixed_in_frame_mobjects(title)
        self.play(Write(title))

        # Create fractal tree
        tree = self.create_fractal_tree(
            start_pos=DOWN * 2,
            direction=UP,
            length=2,
            depth=self.execution_graph['max_depth'],
            angle=30 * DEGREES
        )

        self.play(Create(tree), run_time=3, rate_func=smooth)
        self.wait(1)

        # Pulse through the tree
        self.animate_tree_traversal(tree)

    def create_fractal_tree(self, start_pos, direction, length, depth, angle):
        """Create 3D fractal tree."""
        if depth == 0 or length < 0.1:
            return VGroup()

        tree = VGroup()

        # Main branch
        end_pos = start_pos + direction * length
        branch = Line3D(start_pos, end_pos, color=self.get_color_for_depth(depth))
        branch.set_stroke(width=3 * depth)
        tree.add(branch)

        # Recursive branches
        if depth > 1:
            # Left branch
            left_dir = self.rotate_vector_3d(direction, angle, UP)
            left_tree = self.create_fractal_tree(
                end_pos, left_dir, length * 0.7, depth - 1, angle
            )
            tree.add(left_tree)

            # Right branch
            right_dir = self.rotate_vector_3d(direction, -angle, UP)
            right_tree = self.create_fractal_tree(
                end_pos, right_dir, length * 0.7, depth - 1, angle
            )
            tree.add(right_tree)

        return tree

    def rotate_vector_3d(self, vector, angle, axis):
        """Rotate 3D vector around axis."""
        # Simple rotation using rotation matrix
        c, s = np.cos(angle), np.sin(angle)
        if np.allclose(axis, UP):
            R = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
        else:
            R = np.eye(3)  # Fallback to identity

        return R @ vector

    def animate_tree_traversal(self, tree):
        """Animate traversal through fractal tree."""
        for branch in tree:
            if isinstance(branch, Line3D):
                self.play(
                    branch.animate.set_color(YELLOW).set_stroke(width=branch.stroke_width * 1.5),
                    run_time=0.1
                )
                self.play(
                    branch.animate.set_color(branch.color).set_stroke(width=branch.stroke_width),
                    run_time=0.1
                )

    def visualize_as_data_pipeline(self):
        """Visualize as flowing data pipeline."""
        title = Text("Data Processing Pipeline", font_size=42, color=PURPLE)
        title.to_edge(UP)
        self.add_fixed_in_frame_mobjects(title)
        self.play(Write(title))

        # Create pipeline stages
        stages = list(self.execution_graph['modules'].keys())[:6]
        stage_positions = np.linspace(-5, 5, len(stages))

        stage_objects = []
        for i, stage in enumerate(stages):
            # Create stage as a box
            box = Cube(side_length=0.8)
            box.set_color(self.get_color_for_layer(i, len(stages)))
            box.set_opacity(0.7)
            box.move_to(RIGHT * stage_positions[i])

            label = Text(stage.split('.')[-1][:10], font_size=16, color=WHITE)
            label.move_to(box.get_center() + DOWN * 0.6)
            label.rotate(PI/2, axis=RIGHT)

            stage_objects.append((box, label))

        # Animate stage creation
        for box, label in stage_objects:
            self.play(GrowFromCenter(box), FadeIn(label), run_time=0.3)

        # Create data flow pipe
        pipes = VGroup()
        for i in range(len(stage_objects) - 1):
            start = stage_objects[i][0].get_right()
            end = stage_objects[i + 1][0].get_left()

            pipe = Cylinder(radius=0.05, height=np.linalg.norm(end - start))
            pipe.set_color(BLUE)
            pipe.set_opacity(0.5)
            pipe.rotate(PI/2, axis=UP)
            pipe.move_to((start + end) / 2)
            pipes.add(pipe)

        self.play(*[GrowFromCenter(pipe) for pipe in pipes])

        # Animate data packets flowing
        self.animate_pipeline_flow(stage_objects, pipes)

    def animate_pipeline_flow(self, stages, pipes):
        """Animate data flowing through pipeline."""
        for _ in range(2):  # Two cycles
            packet = Sphere(radius=0.15, resolution=(8, 8))
            packet.set_color(YELLOW)
            packet.set_sheen(0.8, direction=UP)

            for i, ((box, _), pipe) in enumerate(zip(stages[:-1], pipes)):
                # Start at stage
                packet.move_to(box.get_center())

                if i == 0:
                    self.play(GrowFromCenter(packet))

                # Move through pipe
                self.play(
                    packet.animate.move_to(stages[i + 1][0].get_center()),
                    run_time=0.8,
                    rate_func=smooth
                )

                # Process at stage (pulse)
                self.play(
                    stages[i + 1][0].animate.set_opacity(1).scale(1.1),
                    run_time=0.2
                )
                self.play(
                    stages[i + 1][0].animate.set_opacity(0.7).scale(1/1.1),
                    run_time=0.2
                )

            self.play(FadeOut(packet))

    def visualize_as_execution_graph(self):
        """Fallback: visualize as generic 3D execution graph."""
        title = Text("Execution Flow Graph", font_size=42, color=ORANGE)
        title.to_edge(UP)
        self.add_fixed_in_frame_mobjects(title)
        self.play(Write(title))

        # Create nodes
        nodes = {}
        max_nodes = 15  # Limit for performance

        for i, (call_id, data) in enumerate(list(self.execution_graph['nodes'].items())[:max_nodes]):
            # Position based on depth and timestamp
            depth = data['depth']
            timestamp = data['timestamp']

            x = (depth - self.execution_graph['max_depth']/2) * 1.5
            y = (i - max_nodes/2) * 0.4
            z = np.sin(timestamp) * 0.5

            node = Sphere(radius=0.15, resolution=(8, 8))
            node.set_color(self.get_color_for_depth(depth))
            node.move_to(np.array([x, y, z]))
            nodes[call_id] = node

        # Create edges
        edges = VGroup()
        for parent_id, child_id in self.execution_graph['edges']:
            if parent_id in nodes and child_id in nodes:
                line = Line3D(
                    nodes[parent_id].get_center(),
                    nodes[child_id].get_center(),
                    color=GRAY,
                    stroke_width=2
                )
                edges.add(line)

        # Animate
        self.play(*[GrowFromCenter(node) for node in nodes.values()], run_time=1.5)
        if len(edges) > 0:
            self.play(*[Create(edge) for edge in edges], run_time=1)

    def get_color_for_layer(self, index, total):
        """Get color for layer based on position."""
        if STANDARDS_AVAILABLE:
            return AnimationColors.get_layer_color(index, total)
        else:
            # Fallback to hardcoded colors
            colors = [GREEN, BLUE, PURPLE, ORANGE, RED, YELLOW]
            return colors[index % len(colors)]

    def get_color_for_depth(self, depth):
        """Get color based on call depth."""
        colors = [GREEN, BLUE, PURPLE, RED, ORANGE]
        return colors[min(depth, len(colors) - 1)]
