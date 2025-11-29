from logging_config import setup_logger
logger = setup_logger(__name__)

"""
Configuration for Manim trace visualization.
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass
class VisualizationConfig:
    """Configuration for trace visualization."""

    # Filter settings
    # Project-agnostic: Auto-detect from project structure (no hardcoded paths)
    # Set to None to trace all project files, or specify a subdirectory name
    filter_path: str = None
    exclude_packages: Tuple[str, ...] = (
        "site-packages",
        "python3",
        "lib/python",
        "typing",
        "collections",
        "abc"
    )

    # Visualization settings
    max_function_name_length: int = 30
    call_box_width: float = 4.0
    call_box_height: float = 1.5
    vertical_spacing: float = 2.0
    depth_spacing: float = 1.5
    thread_spacing: float = 6.0

    # Animation timing
    fade_in_time: float = 0.3
    arrow_creation_time: float = 0.2
    max_wait_time: float = 2.0
    timeline_scale: float = 0.01  # 1 second real time = 0.01 Manim units

    # Camera settings
    camera_distance: float = 8.0
    camera_height: float = 3.0
    camera_pan_speed: float = 2.0

    # Colors (RGB tuples)
    color_ai_agent: str = "#9D4EDD"  # Purple
    color_framework: str = "#4CC9F0"  # Blue
    color_async: str = "#06FFA5"  # Green
    color_default: str = "#FFFFFF"  # White
    color_parameter: str = "#F77F00"  # Orange
    color_timeline: str = "#FFD60A"  # Yellow

    # Performance settings
    max_calls_to_render: int = 100
    enable_parallel_rendering: bool = True
    quality: str = "medium_quality"  # low_quality, medium_quality, high_quality, production_quality

    # Output settings
    output_format: str = "mp4"
    fps: int = 30
    resolution: Tuple[int, int] = (1920, 1080)

    # Debug settings
    show_call_ids: bool = False
    show_timestamps: bool = True
    show_depth_indicators: bool = True
    verbose_logging: bool = True


# Default configuration instance
DEFAULT_CONFIG = VisualizationConfig()


# Quality presets
QUALITY_PRESETS = {
    "low": {
        "quality": "low_quality",
        "fps": 15,
        "resolution": (854, 480),
        "max_calls_to_render": 50
    },
    "medium": {
        "quality": "medium_quality",
        "fps": 30,
        "resolution": (1280, 720),
        "max_calls_to_render": 100
    },
    "high": {
        "quality": "high_quality",
        "fps": 60,
        "resolution": (1920, 1080),
        "max_calls_to_render": 200
    },
    "production": {
        "quality": "production_quality",
        "fps": 60,
        "resolution": (3840, 2160),
        "max_calls_to_render": 500
    }
}


def get_config(quality_preset: str = "medium") -> VisualizationConfig:
    """
    Get configuration with quality preset applied.

    Args:
        quality_preset: Quality preset name (low, medium, high, production)

    Returns:
        Configuration instance
    """
    config = VisualizationConfig()

    if quality_preset in QUALITY_PRESETS:
        preset = QUALITY_PRESETS[quality_preset]
        config.quality = preset["quality"]
        config.fps = preset["fps"]
        config.resolution = preset["resolution"]
        config.max_calls_to_render = preset["max_calls_to_render"]

    return config
