from logging_config import setup_logger
logger = setup_logger(__name__)

"""
Shared Visualization Components

Common utilities used across all visualizers to ensure consistency,
avoid duplication, and create cohesive multi-visualizer experiences.
"""

import numpy as np
from manim import *
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass

# Import animation standards if available
try:
    from animation_standards import AnimationTiming, AnimationColors
    STANDARDS_AVAILABLE = True
except ImportError:
    STANDARDS_AVAILABLE = False


@dataclass
class VisualizationConfig:
    """Shared configuration for all visualizers"""

    # Timing standards (in seconds)
    TRANSITION_FADE: float = 0.5
    OPERATION_DWELL: float = 1.2
    OVERVIEW_DURATION: float = 30.0
    PATTERN_DURATION: float = 20.0
    DATA_FLOW_DURATION: float = 45.0
    DEBUG_QUICK_SCAN: float = 30.0

    # Camera movement
    CAMERA_MOVE_DURATION: float = 1.0
    CAMERA_SMOOTH_RATE: Any = smooth

    # Visual limits (anti-overwhelm)
    MAX_MODULES_SHOWN: int = 6
    MAX_OPERATIONS_SHOWN: int = 15
    MAX_ERRORS_SHOWN: int = 3
    MAX_CONNECTIONS_SHOWN: int = 20

    # Phase colors (consistent across all visualizers)
    PHASE_COLORS: Dict[str, str] = None

    def __post_init__(self):
        if self.PHASE_COLORS is None:
            # Use standard colors (AnimationColors doesn't have phase-specific attributes)
            self.PHASE_COLORS = {
                'sensor': GREEN,
                'encoding': BLUE,
                'reasoning': PURPLE,
                'decoding': ORANGE,
                'learning': RED,
                'memory': YELLOW
            }


class PhaseDetector:
    """
    Shared phase detection logic used across all visualizers.
    Detects which learning phase a function call belongs to.
    """

    # Phase detection patterns (from runtime_instrumentor.py)
    PHASE_PATTERNS = {
        'sensor': [
            '_capture_loop', 'encode_video_frame', 'encode_image',
            'encode_text', 'encode_multimodal', 'encode_numpy',
            'process_video_frame_pair', 'capture', 'ingest'
        ],
        'encoding': [
            'encode', 'embed', 'encoder', 'embedding', 'tokenize',
            'qwen', 'vision_encoder', 'text_encoder'
        ],
        'reasoning': [
            'reason', 'semantic', 'attention', 'self_attn', 'cross_attn',
            'semantic_reasoner', 'compositional', 'relational'
        ],
        'decoding': [
            'decode', 'decoder', 'generate', 'output', 'predict'
        ],
        'learning': [
            'learn', 'train', 'step', 'update', 'backward', 'grad',
            '_learn_from_experience', 'learn_from_feedback'
        ],
        'memory': [
            'buffer', 'store', 'memory', 'compress', 'consolidate',
            'hierarchical_memory', 'temporal_compression'
        ]
    }

    @staticmethod
    def detect_phase(call_data: Dict[str, Any]) -> Optional[str]:
        """
        Detect which learning phase this call belongs to.

        Args:
            call_data: Dictionary with 'function', 'module', etc.

        Returns:
            Phase name ('sensor', 'encoding', etc.) or None
        """
        func = call_data.get('function', '').lower()
        module = call_data.get('module', '').lower()

        # Check explicit learning_phase field first
        explicit_phase = call_data.get('learning_phase')
        if explicit_phase:
            # Map common phase names to our standard phases
            phase_map = {
                'capture': 'sensor',
                'encode': 'encoding',
                'reason': 'reasoning',
                'decode': 'decoding',
                'learn': 'learning',
                'update': 'learning',
                'forward': 'encoding',  # Default forward to encoding
                'backward': 'learning'
            }
            return phase_map.get(explicit_phase, explicit_phase)

        # Pattern-based detection
        for phase, patterns in PhaseDetector.PHASE_PATTERNS.items():
            if any(pattern in func or pattern in module for pattern in patterns):
                return phase

        return None

    @staticmethod
    def group_calls_by_phase(calls: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Group function calls by their learning phase.

        Returns:
            Dictionary mapping phase name to list of calls in that phase
        """
        phases = {
            'sensor': [],
            'encoding': [],
            'reasoning': [],
            'decoding': [],
            'learning': [],
            'memory': [],
            'unknown': []
        }

        for call in calls:
            if call.get('type') not in ['call', 'return']:
                continue

            phase = PhaseDetector.detect_phase(call)
            if phase:
                phases[phase].append(call)
            else:
                phases['unknown'].append(call)

        # Remove empty phases
        return {k: v for k, v in phases.items() if v}


class CameraChoreographer:
    """
    Shared camera movement logic for smooth, centered compositions.
    All visualizers should use this for consistent camera behavior.
    """

    @staticmethod
    def center_on_object(
        scene: Scene,
        obj: Mobject,
        duration: float = 1.0,
        distance: Optional[float] = None
    ):
        """
        Smoothly move camera to center on object.

        Args:
            scene: Manim scene (ThreeDScene or Scene)
            obj: Object to center on
            duration: Movement duration in seconds
            distance: Optional camera distance (for 3D scenes)
        """
        obj_center = obj.get_center()

        if hasattr(scene, 'camera') and hasattr(scene.camera, 'frame'):
            # 3D scene
            if distance is not None:
                scene.play(
                    scene.camera.frame.animate.move_to(obj_center),
                    scene.camera.frame.animate.set_z(distance),
                    run_time=duration,
                    rate_func=smooth
                )
            else:
                scene.play(
                    scene.camera.frame.animate.move_to(obj_center),
                    run_time=duration,
                    rate_func=smooth
                )
        else:
            # 2D scene
            scene.play(
                scene.camera.frame.animate.move_to(obj_center),
                run_time=duration,
                rate_func=smooth
            )

    @staticmethod
    def create_smooth_pan(
        scene: Scene,
        start_obj: Mobject,
        end_obj: Mobject,
        duration: float = 1.5
    ):
        """
        Create smooth camera pan from start object to end object.
        """
        start_center = start_obj.get_center()
        end_center = end_obj.get_center()

        # Create smooth curve path for camera
        control_point = (start_center + end_center) / 2 + UP * 0.5

        # Animate camera along curve
        # (Simplified - actual implementation would use ValueTracker)
        scene.play(
            scene.camera.frame.animate.move_to(end_center),
            run_time=duration,
            rate_func=smooth
        )

    @staticmethod
    def create_overview_orbit(
        scene: ThreeDScene,
        center: np.ndarray = ORIGIN,
        duration: float = 3.0,
        distance: float = 10.0
    ):
        """
        Create smooth orbital camera movement for overview shots.
        """
        # Set camera to orbit
        scene.move_camera(
            phi=70 * DEGREES,
            theta=-45 * DEGREES,
            distance=distance,
            frame_center=center,
            run_time=duration,
            rate_func=smooth
        )

        # Start ambient rotation
        scene.begin_ambient_camera_rotation(rate=0.05)


class TransitionManager:
    """
    Manages smooth transitions between visualization sections.
    Ensures consistent fade-in/fade-out behavior.
    """

    @staticmethod
    def fade_transition(
        scene: Scene,
        old_objects: List[Mobject],
        new_objects: List[Mobject],
        duration: float = 0.5
    ):
        """
        Smooth cross-fade from old objects to new objects.
        """
        scene.play(
            *[FadeOut(obj, run_time=duration) for obj in old_objects],
            *[FadeIn(obj, run_time=duration, shift=UP*0.2) for obj in new_objects],
            lag_ratio=0.1
        )

    @staticmethod
    def section_title(
        scene: Scene,
        title: str,
        color: str = BLUE,
        duration: float = 1.0
    ) -> Text:
        """
        Create and animate section title card.
        """
        title_text = Text(title, font_size=36, color=color, weight=BOLD)
        title_text.to_edge(UP)

        scene.add_fixed_in_frame_mobjects(title_text)
        scene.play(Write(title_text), run_time=duration)

        return title_text

    @staticmethod
    def fade_section_title(scene: Scene, title_text: Text):
        """Fade out section title."""
        scene.play(FadeOut(title_text), run_time=0.3)
        scene.remove(title_text)


class VisualHierarchy:
    """
    Manages visual hierarchy to avoid overwhelming the viewer.
    Implements progressive disclosure and focus techniques.
    """

    @staticmethod
    def emphasize_object(
        scene: Scene,
        obj: Mobject,
        duration: float = 0.5,
        scale_factor: float = 1.2
    ):
        """
        Emphasize an object by scaling and highlighting it.
        """
        original_color = obj.get_color()

        # Pulse animation
        scene.play(
            obj.animate.scale(scale_factor).set_color(YELLOW),
            run_time=duration / 2
        )
        scene.play(
            obj.animate.scale(1 / scale_factor).set_color(original_color),
            run_time=duration / 2
        )

    @staticmethod
    def fade_background(
        scene: Scene,
        focus_obj: Mobject,
        background_objs: List[Mobject],
        opacity: float = 0.2
    ):
        """
        Fade background objects to emphasize focus object.
        """
        scene.play(
            *[obj.animate.set_opacity(opacity) for obj in background_objs],
            focus_obj.animate.set_opacity(1.0),
            run_time=0.3
        )

    @staticmethod
    def restore_background(
        scene: Scene,
        all_objs: List[Mobject],
        opacity: float = 1.0
    ):
        """
        Restore all objects to full opacity.
        """
        scene.play(
            *[obj.animate.set_opacity(opacity) for obj in all_objs],
            run_time=0.3
        )


class DataFlowHelpers:
    """
    Helper functions for creating data flow visualizations.
    Shared across multiple visualizers.
    """

    @staticmethod
    def create_particle_stream(
        start_pos: np.ndarray,
        end_pos: np.ndarray,
        num_particles: int = 5,
        color: str = BLUE,
        particle_type: str = 'sphere'
    ) -> VGroup:
        """
        Create particle stream for data flow visualization.

        Args:
            start_pos: Starting position
            end_pos: Ending position
            num_particles: Number of particles in stream
            color: Particle color
            particle_type: 'sphere', 'cube', or 'dot'

        Returns:
            VGroup containing all particles
        """
        particles = VGroup()

        for i in range(num_particles):
            if particle_type == 'sphere':
                particle = Sphere(radius=0.05, resolution=(6, 6))
            elif particle_type == 'cube':
                particle = Cube(side_length=0.08)
            else:
                particle = Dot3D(radius=0.04)

            particle.set_color(color)
            particle.set_opacity(0.9)
            particle.set_sheen(0.7, direction=UP)

            # Position along path
            progress = i / max(num_particles - 1, 1)
            particle.move_to(start_pos + (end_pos - start_pos) * progress)

            particles.add(particle)

        return particles

    @staticmethod
    def create_curved_path(
        start_pos: np.ndarray,
        end_pos: np.ndarray,
        height: float = 0.3,
        color: str = BLUE
    ) -> CubicBezier:
        """
        Create smooth curved path for data flow.
        """
        control = (start_pos + end_pos) / 2 + UP * height

        path = CubicBezier(
            start_pos,
            start_pos + (control - start_pos) * 0.5,
            end_pos + (control - end_pos) * 0.5,
            end_pos,
            color=color,
            stroke_width=2
        )
        path.set_opacity(0.6)

        return path

    @staticmethod
    def animate_flow(
        scene: Scene,
        particles: VGroup,
        path: CubicBezier,
        duration: float = 1.0
    ):
        """
        Animate particles flowing along path.
        """
        # Show path
        scene.play(Create(path), run_time=0.3)

        # Animate particles
        particle_anims = []
        for particle in particles:
            particle_anims.append(
                MoveAlongPath(particle, path, rate_func=smooth, run_time=duration)
            )

        scene.play(*particle_anims, lag_ratio=0.1)

        # Cleanup
        scene.play(
            FadeOut(path),
            FadeOut(particles),
            run_time=0.2
        )


# Singleton configuration instance
DEFAULT_CONFIG = VisualizationConfig()
