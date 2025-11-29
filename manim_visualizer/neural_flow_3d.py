"""
DEPRECATED: This file has been superseded by ultimate_architecture_viz.py

The neural flow visualization functionality has been integrated into
ultimate_architecture_viz.py which is the single active engine used by ManimAutoRenderer.kt.

DO NOT USE - Kept for reference only.
================================================================================
"""

from logging_config import setup_logger
logger = setup_logger(__name__)

"""
3D Neural Flow Visualizer - 3Blue1Brown Style

Creates dynamic 3D visualizations of embodied AI learning:
- Neural network layers with flowing activations
- Attention mechanisms as glowing connections
- Memory compression as spiraling data streams
- Learning updates as morphing geometries
"""

import numpy as np
from manim import *

class NeuralFlowScene3D(ThreeDScene):
    """
    3D visualization of neural network data flow through the embodied AI system.
    Shows perception → reasoning → action with dynamic attention flows.
    """

    def construct(self):
        # Setup 3D camera
        self.set_camera_orientation(phi=75 * DEGREES, theta=-45 * DEGREES)

        # Title
        title = Text("Embodied AI: Neural Data Flow", font_size=48, color=BLUE)
        title.to_edge(UP)
        self.add_fixed_in_frame_mobjects(title)
        self.play(Write(title))
        self.wait(0.5)

        # Create network architecture
        self.create_neural_architecture()
        self.wait(1)

        # Animate data flow
        self.animate_perception_to_action()
        self.wait(1)

        # Show attention mechanism
        self.visualize_attention_flow()
        self.wait(1)

        # Show learning update
        self.visualize_learning_dynamics()
        self.wait(2)

    def create_neural_architecture(self):
        """Create 3D neural network layers."""
        # Input layer (sensory stream)
        self.input_layer = self.create_layer(
            position=LEFT * 5,
            neurons=16,
            color=GREEN,
            label="Sensory\nInput"
        )

        # Encoder layer (Qwen-VL)
        self.encoder_layer = self.create_layer(
            position=LEFT * 2,
            neurons=12,
            color=BLUE,
            label="Vision\nEncoder"
        )

        # Latent dynamics (SDE-SSM)
        self.latent_layer = self.create_layer(
            position=ORIGIN,
            neurons=8,
            color=PURPLE,
            label="Latent\nDynamics"
        )

        # Memory compression
        self.memory_layer = self.create_layer(
            position=RIGHT * 2,
            neurons=6,
            color=ORANGE,
            label="Memory\nCompression"
        )

        # Output layer (decoder)
        self.output_layer = self.create_layer(
            position=RIGHT * 5,
            neurons=10,
            color=RED,
            label="Action\nOutput"
        )

        # Store layers
        self.layers = [
            self.input_layer,
            self.encoder_layer,
            self.latent_layer,
            self.memory_layer,
            self.output_layer
        ]

        # Animate layer creation
        for layer_group, label in self.layers:
            self.play(
                *[GrowFromCenter(neuron) for neuron in layer_group],
                FadeIn(label),
                run_time=0.5
            )

    def create_layer(self, position, neurons, color, label):
        """Create a 3D neural layer with spheres."""
        layer = VGroup()

        # Create neurons as spheres arranged in a grid
        rows = int(np.sqrt(neurons))
        cols = int(np.ceil(neurons / rows))

        for i in range(neurons):
            row = i // cols
            col = i % cols

            neuron = Sphere(radius=0.15, resolution=(8, 8))
            neuron.set_color(color)
            neuron.set_opacity(0.8)

            # Position in 3D grid
            x_offset = (col - cols/2) * 0.4
            y_offset = (row - rows/2) * 0.4
            neuron.move_to(position + RIGHT * x_offset + UP * y_offset)

            layer.add(neuron)

        # Add label
        layer_label = Text(label, font_size=20, color=color)
        layer_label.move_to(position + DOWN * 2)
        layer_label.rotate(PI/2, axis=RIGHT)  # Make it readable in 3D

        return (layer, layer_label)

    def animate_perception_to_action(self):
        """Animate data flowing through the network."""
        # Create flowing particles
        particles = VGroup()

        for _ in range(20):
            particle = Sphere(radius=0.05, resolution=(6, 6))
            particle.set_color(YELLOW)
            particle.set_opacity(0.9)
            particles.add(particle)

        # Animate particles flowing through layers
        for i in range(len(self.layers) - 1):
            current_layer, _ = self.layers[i]
            next_layer, _ = self.layers[i + 1]

            # Position particles at current layer
            for j, particle in enumerate(particles):
                start_neuron = current_layer[j % len(current_layer)]
                end_neuron = next_layer[j % len(next_layer)]

                particle.move_to(start_neuron.get_center())

                # Animate movement
                self.play(
                    particle.animate.move_to(end_neuron.get_center()),
                    rate_func=smooth,
                    run_time=0.8
                )

                # Flash the target neuron
                self.play(
                    end_neuron.animate.set_opacity(1).scale(1.2),
                    run_time=0.1
                )
                self.play(
                    end_neuron.animate.set_opacity(0.8).scale(1/1.2),
                    run_time=0.1
                )

    def visualize_attention_flow(self):
        """Show attention mechanism as glowing connections."""
        attention_lines = VGroup()

        # Get encoder and latent layers
        encoder_layer, _ = self.encoder_layer
        latent_layer, _ = self.latent_layer

        # Create attention connections (cross-attention)
        for i in range(5):  # Show 5 strong attention connections
            start_neuron = encoder_layer[np.random.randint(0, len(encoder_layer))]
            end_neuron = latent_layer[np.random.randint(0, len(latent_layer))]

            # Create glowing line
            line = Line3D(
                start_neuron.get_center(),
                end_neuron.get_center(),
                color=YELLOW,
                stroke_width=3
            )
            line.set_opacity(0)
            attention_lines.add(line)

        # Animate attention flowing
        self.play(
            *[line.animate.set_opacity(0.8) for line in attention_lines],
            run_time=1
        )

        # Pulse the connections
        for _ in range(3):
            self.play(
                *[line.animate.set_stroke(width=5, opacity=1) for line in attention_lines],
                run_time=0.3
            )
            self.play(
                *[line.animate.set_stroke(width=3, opacity=0.5) for line in attention_lines],
                run_time=0.3
            )

        # Fade out
        self.play(*[FadeOut(line) for line in attention_lines])

    def visualize_learning_dynamics(self):
        """Show learning as morphing neural weights."""
        latent_layer, _ = self.latent_layer

        # Create gradient flow visualization
        gradient_arrows = VGroup()

        for neuron in latent_layer:
            # Random gradient direction
            direction = np.random.randn(3)
            direction = direction / np.linalg.norm(direction) * 0.5

            arrow = Arrow3D(
                start=neuron.get_center(),
                end=neuron.get_center() + direction,
                color=RED,
                thickness=0.02
            )
            gradient_arrows.add(arrow)

        # Show gradients
        self.play(*[GrowArrow(arrow) for arrow in gradient_arrows])
        self.wait(0.5)

        # Animate weight updates (neurons move slightly)
        self.play(
            *[neuron.animate.shift(0.1 * (np.random.rand(3) - 0.5))
              for neuron in latent_layer],
            *[FadeOut(arrow) for arrow in gradient_arrows],
            run_time=1
        )


class MemoryCompressionSpiral(ThreeDScene):
    """
    Visualize hierarchical temporal compression as a 3D spiral.
    Shows how experiences compress from working → recent → hourly → daily memory.
    """

    def construct(self):
        self.set_camera_orientation(phi=70 * DEGREES, theta=-45 * DEGREES)

        # Title
        title = Text("Hierarchical Memory Compression", font_size=48, color=PURPLE)
        title.to_edge(UP)
        self.add_fixed_in_frame_mobjects(title)
        self.play(Write(title))

        # Create memory spiral
        self.create_memory_spiral()
        self.wait(1)

        # Animate compression
        self.animate_compression()
        self.wait(2)

    def create_memory_spiral(self):
        """Create 3D spiral representing memory tiers."""
        # Parameters for spiral
        num_turns = 4
        points_per_turn = 50
        total_points = num_turns * points_per_turn

        # Generate spiral points
        t = np.linspace(0, num_turns * 2 * PI, total_points)
        radius = 3 - t / (2 * PI * num_turns) * 2.5  # Spiral inward
        height = t / (2 * PI) * 0.5

        x = radius * np.cos(t)
        y = radius * np.sin(t)
        z = height

        points = np.column_stack([x, y, z])

        # Create spiral path
        self.spiral = VMobject()
        self.spiral.set_points_as_corners([*points])
        self.spiral.set_color_by_gradient(GREEN, BLUE, PURPLE, RED)
        self.spiral.set_stroke(width=4)

        # Create memory tier labels
        tier_positions = [
            (points[0], "Working\nMemory", GREEN),
            (points[total_points//4], "Recent\n(60min)", BLUE),
            (points[total_points//2], "Hourly\n(24h)", PURPLE),
            (points[3*total_points//4], "Daily\n(7d)", RED)
        ]

        self.tier_labels = VGroup()
        for pos, label_text, color in tier_positions:
            label = Text(label_text, font_size=24, color=color)
            label.move_to(pos + UP * 0.5)
            label.rotate(PI/2, axis=RIGHT)
            self.tier_labels.add(label)

        # Animate creation
        self.play(Create(self.spiral), run_time=3, rate_func=smooth)
        self.play(*[FadeIn(label) for label in self.tier_labels])

    def animate_compression(self):
        """Animate experiences flowing and compressing through memory tiers."""
        # Create experience particles
        experiences = VGroup()

        for _ in range(15):
            exp = Sphere(radius=0.08, resolution=(6, 6))
            exp.set_color(YELLOW)
            exp.set_opacity(0.9)
            experiences.add(exp)

        # Animate particles flowing down the spiral
        for exp in experiences:
            # Start at beginning of spiral
            start_point = self.spiral.point_from_proportion(0)
            exp.move_to(start_point)

            # Animate along spiral with compression (shrinking)
            self.play(
                MoveAlongPath(exp, self.spiral),
                exp.animate.scale(0.3),  # Compress as it moves
                run_time=2,
                rate_func=linear
            )

            # Fade out at the end
            self.play(FadeOut(exp), run_time=0.2)


class AttentionMechanismViz(ThreeDScene):
    """
    Visualize attention mechanism as dynamic 3D connections.
    Shows query-key-value attention with flowing energy.
    """

    def construct(self):
        self.set_camera_orientation(phi=75 * DEGREES, theta=-30 * DEGREES)

        # Title
        title = Text("Linear Attention Mechanism", font_size=48, color=BLUE)
        title.to_edge(UP)
        self.add_fixed_in_frame_mobjects(title)
        self.play(Write(title))

        # Create attention visualization
        self.create_attention_nodes()
        self.wait(1)

        # Show attention flow
        self.animate_attention_flow()
        self.wait(2)

    def create_attention_nodes(self):
        """Create query, key, value nodes."""
        # Query nodes (left)
        self.queries = VGroup()
        for i in range(6):
            node = Sphere(radius=0.15, resolution=(8, 8))
            node.set_color(GREEN)
            node.move_to(LEFT * 4 + UP * (i - 2.5) * 0.8)
            self.queries.add(node)

        # Key nodes (center)
        self.keys = VGroup()
        for i in range(6):
            node = Sphere(radius=0.15, resolution=(8, 8))
            node.set_color(BLUE)
            node.move_to(ORIGIN + UP * (i - 2.5) * 0.8)
            self.keys.add(node)

        # Value nodes (right)
        self.values = VGroup()
        for i in range(6):
            node = Sphere(radius=0.15, resolution=(8, 8))
            node.set_color(PURPLE)
            node.move_to(RIGHT * 4 + UP * (i - 2.5) * 0.8)
            self.values.add(node)

        # Labels
        q_label = Text("Query", font_size=24, color=GREEN).move_to(LEFT * 4 + DOWN * 3)
        k_label = Text("Key", font_size=24, color=BLUE).move_to(ORIGIN + DOWN * 3)
        v_label = Text("Value", font_size=24, color=PURPLE).move_to(RIGHT * 4 + DOWN * 3)

        for label in [q_label, k_label, v_label]:
            label.rotate(PI/2, axis=RIGHT)

        # Animate creation
        self.play(
            *[GrowFromCenter(node) for node in self.queries],
            *[GrowFromCenter(node) for node in self.keys],
            *[GrowFromCenter(node) for node in self.values],
            FadeIn(q_label), FadeIn(k_label), FadeIn(v_label)
        )

    def animate_attention_flow(self):
        """Show attention weights as flowing connections."""
        # Create attention matrix (query-key similarity)
        attention_lines = VGroup()

        for q_node in self.queries:
            # Each query attends to all keys (with varying strength)
            for k_node in self.keys:
                line = Line3D(
                    q_node.get_center(),
                    k_node.get_center(),
                    color=YELLOW,
                    stroke_width=2
                )
                line.set_opacity(np.random.rand() * 0.7 + 0.3)  # Random attention weight
                attention_lines.add(line)

        # Show attention connections
        self.play(*[Create(line) for line in attention_lines], run_time=1.5)
        self.wait(0.5)

        # Pulse the connections
        for _ in range(2):
            self.play(
                *[line.animate.set_opacity(line.get_opacity() * 1.5) for line in attention_lines],
                run_time=0.4
            )
            self.play(
                *[line.animate.set_opacity(line.get_opacity() / 1.5) for line in attention_lines],
                run_time=0.4
            )

        # Flow from keys to values
        value_lines = VGroup()
        for k_node, v_node in zip(self.keys, self.values):
            line = Line3D(
                k_node.get_center(),
                v_node.get_center(),
                color=ORANGE,
                stroke_width=3
            )
            value_lines.add(line)

        self.play(
            *[FadeOut(line) for line in attention_lines],
            *[Create(line) for line in value_lines],
            run_time=1
        )
