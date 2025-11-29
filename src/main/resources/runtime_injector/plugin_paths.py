"""
Single source of truth for all plugin-related paths and directories.

ALL file operations, logging, and artifact storage MUST use these paths.
This ensures consistency between Python and Kotlin code.

This mirrors PluginPaths.kt in the Kotlin plugin code.
"""
import os
from pathlib import Path


class PluginPaths:
    """Centralized path management for the plugin."""

    @staticmethod
    def get_plugin_root(project_path: str = ".") -> Path:
        """
        Root directory for all plugin data: .pycharm_plugin/

        Args:
            project_path: Path to the project root. Defaults to current directory.

        Returns:
            Path to .pycharm_plugin/ directory
        """
        root = Path(project_path) / ".pycharm_plugin"
        root.mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def get_logs_dir(project_path: str = ".") -> Path:
        """
        Logs directory: .pycharm_plugin/logs/
        All plugin logs (Kotlin and Python) go here.

        Args:
            project_path: Path to the project root

        Returns:
            Path to logs directory
        """
        logs_dir = PluginPaths.get_plugin_root(project_path) / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir

    @staticmethod
    def get_manim_root(project_path: str = ".") -> Path:
        """
        Manim root directory: .pycharm_plugin/manim/

        Args:
            project_path: Path to the project root

        Returns:
            Path to manim directory
        """
        manim_root = PluginPaths.get_plugin_root(project_path) / "manim"
        manim_root.mkdir(parents=True, exist_ok=True)
        return manim_root

    @staticmethod
    def get_manim_traces_dir(project_path: str = ".") -> Path:
        """
        Manim traces directory: .pycharm_plugin/manim/traces/
        Trace JSON files are written here.

        Args:
            project_path: Path to the project root

        Returns:
            Path to traces directory
        """
        traces_dir = PluginPaths.get_manim_root(project_path) / "traces"
        traces_dir.mkdir(parents=True, exist_ok=True)
        return traces_dir

    @staticmethod
    def get_media_root(project_path: str = ".") -> Path:
        """
        Media root directory: .pycharm_plugin/manim/media/
        Contains all Manim-generated media (videos, images, texts)

        Args:
            project_path: Path to the project root

        Returns:
            Path to media directory
        """
        media_root = PluginPaths.get_manim_root(project_path) / "media"
        media_root.mkdir(parents=True, exist_ok=True)
        return media_root

    @staticmethod
    def get_manim_videos_dir(project_path: str = ".") -> Path:
        """
        Manim videos directory: .pycharm_plugin/manim/media/videos/
        Final rendered MP4 files are stored here.

        Args:
            project_path: Path to the project root

        Returns:
            Path to videos directory
        """
        videos_dir = PluginPaths.get_media_root(project_path) / "videos"
        videos_dir.mkdir(parents=True, exist_ok=True)
        return videos_dir

    @staticmethod
    def get_manim_images_dir(project_path: str = ".") -> Path:
        """
        Manim images directory: .pycharm_plugin/manim/media/images/
        Manim-generated images stored by quality level

        Args:
            project_path: Path to the project root

        Returns:
            Path to images directory
        """
        images_dir = PluginPaths.get_media_root(project_path) / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        return images_dir

    @staticmethod
    def get_manim_texts_dir(project_path: str = ".") -> Path:
        """
        Manim text directory: .pycharm_plugin/manim/media/texts/
        Manim-generated text files

        Args:
            project_path: Path to the project root

        Returns:
            Path to texts directory
        """
        texts_dir = PluginPaths.get_media_root(project_path) / "texts"
        texts_dir.mkdir(parents=True, exist_ok=True)
        return texts_dir

    @staticmethod
    def get_runtime_injector_dir(project_path: str = ".") -> Path:
        """
        Runtime injector directory: .pycharm_plugin/runtime_injector/
        Python runtime instrumentation code.

        Args:
            project_path: Path to the project root

        Returns:
            Path to runtime_injector directory
        """
        injector_dir = PluginPaths.get_plugin_root(project_path) / "runtime_injector"
        injector_dir.mkdir(parents=True, exist_ok=True)
        return injector_dir

    @staticmethod
    def get_traces_root(project_path: str = ".") -> Path:
        """
        Traces root directory: traces/
        (Note: This is at project root, not in .pycharm_plugin)

        Args:
            project_path: Path to the project root

        Returns:
            Path to traces directory
        """
        traces_root = Path(project_path) / "traces"
        traces_root.mkdir(parents=True, exist_ok=True)
        return traces_root

    @staticmethod
    def initialize_all(project_path: str = "."):
        """
        Initialize all directories - call this during plugin startup.

        Args:
            project_path: Path to the project root
        """
        PluginPaths.get_plugin_root(project_path)
        PluginPaths.get_logs_dir(project_path)
        PluginPaths.get_manim_root(project_path)
        PluginPaths.get_manim_traces_dir(project_path)
        PluginPaths.get_manim_videos_dir(project_path)
        PluginPaths.get_runtime_injector_dir(project_path)
        PluginPaths.get_traces_root(project_path)


# Convenience functions for backward compatibility
def get_log_dir(project_path: str = ".") -> Path:
    """Alias for get_logs_dir()"""
    return PluginPaths.get_logs_dir(project_path)


def get_video_output_dir(project_path: str = ".") -> Path:
    """Alias for get_manim_videos_dir()"""
    return PluginPaths.get_manim_videos_dir(project_path)


def get_trace_output_dir(project_path: str = ".") -> Path:
    """Alias for get_manim_traces_dir()"""
    return PluginPaths.get_manim_traces_dir(project_path)
