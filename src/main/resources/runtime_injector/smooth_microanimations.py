from logging_config import setup_logger
logger = setup_logger(__name__)

"""
Smooth Microanimations for Embodied AI Visualization

Adds subtle, explanatory microanimations that make complex concepts intuitive:
- Attention weight visualization (glowing intensity = weight strength)
- Gradient flow with particle trails
- Dimension transformations with morphing
- Data type conversions with color transitions
- Memory compression with shrinking + fading
- Latent space interpolation with smooth paths
"""

import numpy as np
from manim import *
from typing import List, Tuple, Optional


class SmoothAttentionFlow(Animation):
    """
    Microanimation showing attention weights as flowing energy.
    Brightness and thickness of connections = attention strength.
    """

    def __init__(self, source_nodes: VGroup, target_nodes: VGroup,
                 attention_weights: np.ndarray, **kwargs):
        """
        Args:
            source_nodes: Query nodes
            target_nodes: Key/Value nodes
            attention_weights: Matrix of attention weights [n_queries, n_keys]
        """
        self.source_nodes = source_nodes
        self.target_nodes = target_nodes
        self.attention_weights = attention_weights

        # Create attention lines with varying opacity based on weights
        self.attention_lines = VGroup()
        for i, query_node in enumerate(source_nodes):
            for j, key_node in enumerate(target_nodes):
                weight = attention_weights[i, j] if i < len(attention_weights) and j < len(attention_weights[0]) else 0.1

                line = Line3D(
                    query_node.get_center(),
                    key_node.get_center(),
                    color=interpolate_color(BLUE, YELLOW, weight),
                    stroke_width=2 + weight * 6
                )
                line.set_opacity(0.3 + weight * 0.7)
                self.attention_lines.add(line)

        super().__init__(self.attention_lines, **kwargs)

    def interpolate_mobject(self, alpha):
        """Animate attention flowing with pulses."""
        for line in self.attention_lines:
            # Pulsing effect
            pulse = 0.8 + 0.2 * np.sin(alpha * 2 * PI * 3)  # 3 pulses
            line.set_stroke(width=line.stroke_width * pulse)


class DataFlowParticles(ThreeDScene):
    """Particle system showing data flowing through network with trails."""

    def create_particle_flow(self, start_pos: np.ndarray, end_pos: np.ndarray,
                            num_particles: int = 10, data_type: str = 'tensor',
                            show_trails: bool = True) -> VGroup:
        """
        Create flowing particles with motion trails.

        Args:
            start_pos: Starting position
            end_pos: Target position
            num_particles: Number of particles in stream
            data_type: 'tensor', 'scalar', 'gradient'
            show_trails: Whether to show motion trails
        """
        particles = VGroup()

        # Color and shape based on data type
        if data_type == 'tensor':
            color = BLUE
            shape_func = lambda: Cube(side_length=0.08)
        elif data_type == 'gradient':
            color = RED
            shape_func = lambda: Arrow3D(ORIGIN, UP * 0.1, thickness=0.01)
        else:  # scalar
            color = YELLOW
            shape_func = lambda: Sphere(radius=0.05)

        for i in range(num_particles):
            particle = shape_func()
            particle.set_color(color)
            particle.set_opacity(0.9)
            particle.set_sheen(0.8, direction=UP)

            # Stagger particles along path
            progress = i / num_particles
            particle.move_to(start_pos + (end_pos - start_pos) * progress)
            particles.add(particle)

        return particles

    def animate_particle_stream(self, particles: VGroup, start_pos: np.ndarray,
                               end_pos: np.ndarray, run_time: float = 1.0,
                               show_trails: bool = True):
        """Animate particles flowing with optional trails."""
        animations = []

        for i, particle in enumerate(particles):
            # Stagger animation start
            delay = i * 0.05

            # Main movement
            anim = particle.animate(run_time=run_time, rate_func=smooth).move_to(end_pos)
            animations.append(anim)

            if show_trails:
                # Add fading trail
                trail = TracedPath(particle.get_center, stroke_color=particle.get_color(),
                                  stroke_width=2, dissipating_time=0.5)
                self.add(trail)

        return AnimationGroup(*animations, lag_ratio=0.1)


class DimensionMorphAnimation(Animation):
    """
    Smooth morphing animation showing tensor dimension changes.
    Visualizes reshapes, transposes, and broadcasts.
    """

    def __init__(self, mobject: Mobject,
                 start_dims: Tuple[int, ...],
                 end_dims: Tuple[int, ...],
                 operation: str = 'reshape',
                 **kwargs):
        """
        Args:
            mobject: The shape to morph
            start_dims: Initial dimensions (e.g., (2, 4, 3))
            end_dims: Target dimensions (e.g., (8, 3))
            operation: 'reshape', 'transpose', 'broadcast'
        """
        self.start_dims = start_dims
        self.end_dims = end_dims
        self.operation = operation

        super().__init__(mobject, **kwargs)

    def interpolate_mobject(self, alpha):
        """Smoothly morph between dimension representations."""
        # Calculate intermediate dimensions
        if self.operation == 'reshape':
            # Smooth scaling in each dimension
            for i in range(3):
                start_scale = self.start_dims[i] / 100 if i < len(self.start_dims) else 1
                end_scale = self.end_dims[i] / 100 if i < len(self.end_dims) else 1
                current_scale = interpolate(start_scale, end_scale, smooth(alpha))

                # Apply scale
                if i == 0:
                    self.mobject.stretch(current_scale / self.mobject.width, 0)
                elif i == 1:
                    self.mobject.stretch(current_scale / self.mobject.height, 1)
                elif i == 2:
                    self.mobject.stretch(current_scale / self.mobject.depth, 2)

        elif self.operation == 'transpose':
            # Rotate to show transpose
            self.mobject.rotate(alpha * PI/2, axis=OUT)

        # Color transition to show transformation
        start_color = BLUE
        end_color = GREEN
        self.mobject.set_color(interpolate_color(start_color, end_color, alpha))


class GradientFlowVisualization(ThreeDScene):
    """Visualize gradient backpropagation with flowing arrows and intensity."""

    def create_gradient_flow(self, layers: List[VGroup],
                            gradient_magnitudes: Optional[List[float]] = None):
        """
        Create gradient flow visualization from output to input.

        Args:
            layers: List of neural network layer VGroups
            gradient_magnitudes: Magnitude of gradients at each layer
        """
        if gradient_magnitudes is None:
            gradient_magnitudes = [1.0] * len(layers)

        gradient_arrows = VGroup()

        # Flow from output layer backwards
        for i in range(len(layers) - 1, 0, -1):
            current_layer = layers[i]
            prev_layer = layers[i - 1]
            magnitude = gradient_magnitudes[i - 1]

            # Create gradient arrows
            for curr_neuron in current_layer:
                for prev_neuron in prev_layer:
                    # Arrow size and color based on gradient magnitude
                    arrow = Arrow3D(
                        curr_neuron.get_center(),
                        prev_neuron.get_center(),
                        color=interpolate_color(BLUE, RED, magnitude),
                        thickness=0.01 + magnitude * 0.03
                    )
                    arrow.set_opacity(0.3 + magnitude * 0.6)
                    gradient_arrows.add(arrow)

        return gradient_arrows

    def animate_gradient_propagation(self, gradient_arrows: VGroup,
                                     layers: List[VGroup],
                                     run_time: float = 2.0):
        """Animate gradients flowing backwards through network."""
        # Animate in waves from output to input
        wave_animations = []

        for i, arrow in enumerate(gradient_arrows):
            # Stagger based on layer depth
            delay = (i / len(gradient_arrows)) * run_time * 0.5

            # Pulse animation
            wave_animations.append(
                Succession(
                    Wait(delay),
                    arrow.animate(rate_func=there_and_back, run_time=0.5).scale(1.3),
                    arrow.animate(run_time=0.3).set_opacity(arrow.get_opacity() * 0.5)
                )
            )

        return AnimationGroup(*wave_animations, lag_ratio=0.05)


class MemoryCompressionMicroAnim(ThreeDScene):
    """Microanimation showing hierarchical memory compression."""

    def create_compression_effect(self, experience_group: VGroup,
                                  compression_ratio: float = 0.3,
                                  target_tier: str = 'hourly'):
        """
        Show experience being compressed to higher memory tier.

        Args:
            experience_group: Group of objects representing experiences
            compression_ratio: How much to shrink (0.3 = 30% of original size)
            target_tier: 'recent', 'hourly', 'daily'
        """
        tier_colors = {
            'working': GREEN,
            'recent': BLUE,
            'hourly': PURPLE,
            'daily': RED
        }
        target_color = tier_colors.get(target_tier, GRAY)

        # Create compression animation
        compression_anims = []

        for exp in experience_group:
            # Shrink + fade + color change
            compression_anims.extend([
                exp.animate(rate_func=smooth).scale(compression_ratio),
                exp.animate.set_color(target_color),
                exp.animate.set_opacity(0.6)
            ])

        return AnimationGroup(*compression_anims)


class LatentSpaceInterpolation(ThreeDScene):
    """Smooth interpolation in latent space visualization."""

    def create_latent_path(self, start_state: np.ndarray, end_state: np.ndarray,
                          num_steps: int = 20) -> VGroup:
        """
        Create visual path through latent space.

        Args:
            start_state: Starting latent vector
            end_state: Target latent vector
            num_steps: Number of interpolation steps
        """
        path_points = []

        # Spherical interpolation for smoother path
        for i in range(num_steps):
            alpha = i / (num_steps - 1)
            # Slerp for more natural interpolation
            interp_state = self.slerp(start_state, end_state, alpha)
            path_points.append(interp_state)

        # Create path visualization
        path = VGroup()
        for i in range(len(path_points) - 1):
            segment = Line3D(
                path_points[i],
                path_points[i + 1],
                color=interpolate_color(GREEN, BLUE, i / len(path_points))
            )
            path.add(segment)

        return path

    def slerp(self, v0: np.ndarray, v1: np.ndarray, t: float) -> np.ndarray:
        """Spherical linear interpolation."""
        # Normalize vectors
        v0_norm = v0 / np.linalg.norm(v0)
        v1_norm = v1 / np.linalg.norm(v1)

        # Calculate angle
        dot = np.clip(np.dot(v0_norm, v1_norm), -1.0, 1.0)
        theta = np.arccos(dot)

        if theta < 1e-6:
            # Vectors are parallel, use linear interpolation
            return v0 + t * (v1 - v0)

        # Slerp formula
        return (np.sin((1 - t) * theta) / np.sin(theta)) * v0 + \
               (np.sin(t * theta) / np.sin(theta)) * v1

    def animate_latent_traversal(self, path: VGroup,
                                 state_indicator: Mobject,
                                 run_time: float = 3.0):
        """Animate smooth movement through latent space."""
        return MoveAlongPath(state_indicator, path,
                           rate_func=smooth, run_time=run_time)


class ConceptExplainerMicroAnim(ThreeDScene):
    """Microanimations that explain abstract concepts visually."""

    def explain_attention_mechanism(self, query_pos: np.ndarray,
                                   key_positions: List[np.ndarray],
                                   attention_weights: np.ndarray):
        """
        Visual explanation of attention: Query 'attending' to Keys.
        Brightness of connections = attention weight.
        """
        # Create query indicator
        query = Sphere(radius=0.15, color=GREEN)
        query.set_sheen(0.8, direction=UP)
        query.move_to(query_pos)

        # Create keys
        keys = VGroup()
        connections = VGroup()

        for i, key_pos in enumerate(key_positions):
            key = Sphere(radius=0.12, color=BLUE)
            key.move_to(key_pos)
            keys.add(key)

            # Attention connection
            weight = attention_weights[i] if i < len(attention_weights) else 0.1
            connection = Line3D(
                query_pos, key_pos,
                color=interpolate_color(GRAY, YELLOW, weight),
                stroke_width=1 + weight * 5
            )
            connection.set_opacity(0.2 + weight * 0.8)
            connections.add(connection)

        # Animate: Query pulses, then connections light up based on weights
        animations = [
            query.animate(rate_func=there_and_back, run_time=0.5).scale(1.2),
            *[key.animate(rate_func=there_and_back, run_time=0.3).scale(1 + attention_weights[i] * 0.5)
              for i, key in enumerate(keys)],
            *[conn.animate(run_time=0.4).set_opacity(conn.get_opacity() * 1.5)
              for conn in connections]
        ]

        return query, keys, connections, animations

    def explain_residual_connection(self, input_path: VGroup,
                                   transform_path: VGroup,
                                   output_pos: np.ndarray):
        """
        Visual explanation of residual connections: input + f(input).
        Shows two paths merging.
        """
        # Input path (straight line - identity)
        identity_path = Line3D(
            input_path.get_start(),
            output_pos,
            color=BLUE,
            stroke_width=3
        )

        # Transform path (curved - transformation)
        transform_path_visual = CubicBezier(
            input_path.get_start(),
            input_path.get_start() + UP * 2,
            transform_path.get_end() + UP * 2,
            output_pos,
            color=RED,
            stroke_width=3
        )

        # Merge point
        merge_point = Sphere(radius=0.15, color=PURPLE)
        merge_point.move_to(output_pos)

        # Plus sign to show addition
        plus = MathTex("+", color=WHITE).scale(0.8)
        plus.move_to(output_pos + LEFT * 0.5)
        plus.rotate(PI/2, axis=RIGHT)

        return VGroup(identity_path, transform_path_visual, merge_point, plus)


# Easing functions for even smoother animations
def ease_in_out_cubic(t):
    """Smooth cubic easing."""
    return 4 * t**3 if t < 0.5 else 1 - (-2 * t + 2)**3 / 2


def ease_in_out_elastic(t):
    """Elastic easing with bounce."""
    c5 = (2 * PI) / 4.5
    if t == 0 or t == 1:
        return t
    if t < 0.5:
        return -(2**(20 * t - 10) * np.sin((20 * t - 11.125) * c5)) / 2
    return (2**(-20 * t + 10) * np.sin((20 * t - 11.125) * c5)) / 2 + 1


def ease_out_bounce(t):
    """Bouncing easing at end."""
    n1 = 7.5625
    d1 = 2.75

    if t < 1 / d1:
        return n1 * t * t
    elif t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    elif t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    else:
        t -= 2.625 / d1
        return n1 * t * t + 0.984375
