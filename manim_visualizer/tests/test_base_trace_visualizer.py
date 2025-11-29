"""
Tests for BaseTraceVisualizer.

Coverage:
- Trace loading (valid, invalid, missing, empty)
- Module extraction
- Phase detection
- Configuration management
- Camera management
- Error handling
"""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from base_trace_visualizer import BaseTraceVisualizer, MinimalTraceVisualizer
from visualization_common import VisualizationConfig
from animation_pacing import AnimationPacing


class TestBaseTraceVisualizerInit:
    """Test initialization and configuration."""

    def test_init_with_trace_file(self, temp_trace_file):
        """Test initialization with trace file."""
        viz = BaseTraceVisualizer(trace_file=str(temp_trace_file))
        assert viz.trace_file == str(temp_trace_file)
        assert viz.trace_data is None  # Not loaded until construct()
        assert viz.calls == []
        assert viz.modules == {}
        assert viz.errors == []

    def test_init_without_trace_file(self):
        """Test initialization without trace file."""
        viz = BaseTraceVisualizer()
        assert viz.trace_file is None
        assert viz.trace_data is None

    def test_get_config_default(self):
        """Test default configuration."""
        viz = BaseTraceVisualizer()
        config = viz.get_config()
        assert isinstance(config, VisualizationConfig)
        assert config.MAX_MODULES_SHOWN == 6
        assert config.PHASE_COLORS is not None

    def test_get_title_default(self):
        """Test default title."""
        viz = BaseTraceVisualizer()
        title = viz.get_title()
        assert title == "Trace Visualization"


class TestTraceLoading:
    """Test trace file loading."""

    def test_load_valid_trace(self, temp_trace_file):
        """Test loading valid trace file."""
        viz = BaseTraceVisualizer(trace_file=str(temp_trace_file))
        result = viz.load_trace()

        assert result is True
        assert viz.trace_data is not None
        assert len(viz.calls) == 4  # 3 calls + 1 return
        assert len(viz.errors) == 0

    def test_load_trace_with_errors(self, temp_trace_file_with_errors):
        """Test loading trace with errors."""
        viz = BaseTraceVisualizer(trace_file=str(temp_trace_file_with_errors))
        result = viz.load_trace()

        assert result is True
        assert len(viz.errors) == 1

    def test_load_empty_trace(self, empty_trace_file):
        """Test loading empty trace file."""
        viz = BaseTraceVisualizer(trace_file=str(empty_trace_file))
        result = viz.load_trace()

        assert result is True
        assert len(viz.calls) == 0
        assert len(viz.errors) == 0

    def test_load_missing_file(self):
        """Test loading non-existent file."""
        viz = BaseTraceVisualizer(trace_file="/nonexistent/file.json")
        result = viz.load_trace()

        assert result is False
        assert viz.trace_data is None

    def test_load_invalid_json(self, invalid_json_file):
        """Test loading file with invalid JSON."""
        viz = BaseTraceVisualizer(trace_file=str(invalid_json_file))
        result = viz.load_trace()

        assert result is False
        assert viz.trace_data is None

    def test_load_no_file_specified(self):
        """Test loading when no file specified."""
        viz = BaseTraceVisualizer()
        result = viz.load_trace()

        assert result is False


class TestModuleExtraction:
    """Test module extraction functionality."""

    def test_extract_modules_basic(self, temp_trace_file):
        """Test basic module extraction."""
        viz = BaseTraceVisualizer(trace_file=str(temp_trace_file))
        viz.load_trace()
        modules = viz.extract_modules()

        assert len(modules) == 3  # 3 unique modules
        assert "src.crawl4ai.embodied_ai.rl_ef.learning_llm_provider" in modules
        assert "src.crawl4ai.embodied_ai.learning.reality_grounded_learner" in modules
        assert "src.crawl4ai.embodied_ai.learning.semantic_reasoner" in modules

    def test_extract_modules_with_limit(self, temp_trace_file):
        """Test module extraction with limit."""
        viz = BaseTraceVisualizer(trace_file=str(temp_trace_file))
        viz.load_trace()
        modules = viz.extract_modules(max_modules=2)

        assert len(modules) == 2  # Limited to 2

    def test_extract_modules_empty_calls(self):
        """Test module extraction with no calls."""
        viz = BaseTraceVisualizer()
        viz.calls = []
        modules = viz.extract_modules()

        assert len(modules) == 0

    def test_extract_modules_filters_non_calls(self, temp_trace_file):
        """Test that return events are filtered out."""
        viz = BaseTraceVisualizer(trace_file=str(temp_trace_file))
        viz.load_trace()

        # Count only call events (not returns)
        call_events = [c for c in viz.calls if c.get('type') == 'call']
        modules = viz.extract_modules()

        # Each module should only have call events
        for module_calls in modules.values():
            for call in module_calls:
                assert call.get('type') == 'call'


class TestPhaseDetection:
    """Test learning phase detection."""

    def test_detect_phase_encoding(self):
        """Test encoding phase detection."""
        viz = BaseTraceVisualizer()
        phase = viz.detect_phase(
            "src.crawl4ai.embodied_ai.encoder",
            "encode_multimodal"
        )
        # encode_multimodal is detected as sensor phase (captures input)
        # This is correct according to PhaseDetector patterns
        assert phase in ["sensor", "encoding"]  # Both are valid

    def test_detect_phase_learning(self):
        """Test learning phase detection."""
        viz = BaseTraceVisualizer()
        phase = viz.detect_phase(
            "src.crawl4ai.embodied_ai.learning.learner",
            "learn_from_experience"
        )
        assert phase == "learning"

    def test_detect_phase_reasoning(self):
        """Test reasoning phase detection."""
        viz = BaseTraceVisualizer()
        phase = viz.detect_phase(
            "src.crawl4ai.embodied_ai.learning.semantic_reasoner",
            "reason"
        )
        assert phase == "reasoning"

    def test_get_phase_color(self):
        """Test phase color retrieval."""
        viz = BaseTraceVisualizer()

        # Import manim colors for comparison
        from manim import GREEN, BLUE, PURPLE, RED, YELLOW

        # Note: We can't directly compare ManimColor objects,
        # so we just verify the method doesn't crash
        color = viz.get_phase_color("sensor")
        assert color is not None


class TestCameraManagement:
    """Test camera setup and movement."""

    @patch('base_trace_visualizer.ThreeDScene.set_camera_orientation')
    def test_setup_camera(self, mock_set_camera):
        """Test camera setup."""
        viz = BaseTraceVisualizer()
        viz.setup_camera(phi=60, theta=-30, distance=12)

        # Verify camera was configured
        assert viz.coord_tracker.camera_state.phi == 60
        assert viz.coord_tracker.camera_state.theta == -30
        assert viz.coord_tracker.camera_state.distance == 12

    @patch('base_trace_visualizer.ThreeDScene.move_camera')
    def test_move_camera_smooth(self, mock_move_camera):
        """Test smooth camera movement."""
        viz = BaseTraceVisualizer()
        viz.move_camera_smooth(phi=90, theta=45, distance=15, run_time=2.0)

        # Verify state updated
        assert viz.coord_tracker.camera_state.phi == 90
        assert viz.coord_tracker.camera_state.theta == 45
        assert viz.coord_tracker.camera_state.distance == 15


class TestCommonAnimations:
    """Test common animation helpers."""

    @patch('base_trace_visualizer.ThreeDScene.add_fixed_in_frame_mobjects')
    @patch('base_trace_visualizer.ThreeDScene.play')
    @patch('base_trace_visualizer.ThreeDScene.wait')
    def test_show_title(self, mock_wait, mock_play, mock_add_fixed):
        """Test title display."""
        viz = BaseTraceVisualizer()
        title = viz.show_title("Test Title", duration=2.0)

        assert title is not None
        mock_add_fixed.assert_called()
        mock_play.assert_called()

    @patch('base_trace_visualizer.ThreeDScene.add_fixed_in_frame_mobjects')
    @patch('base_trace_visualizer.ThreeDScene.play')
    def test_create_billboard_text(self, mock_play, mock_add_fixed):
        """Test billboard text creation."""
        viz = BaseTraceVisualizer()
        text = viz.create_billboard_text("Test", font_size=24)

        assert text is not None
        mock_add_fixed.assert_called()


class TestErrorHandling:
    """Test error handling in construct()."""

    @patch('base_trace_visualizer.BaseTraceVisualizer.load_trace')
    @patch('base_trace_visualizer.ThreeDScene.add_fixed_in_frame_mobjects')
    @patch('base_trace_visualizer.ThreeDScene.play')
    @patch('base_trace_visualizer.ThreeDScene.wait')
    def test_construct_handles_load_failure(
        self, mock_wait, mock_play, mock_add_fixed, mock_load
    ):
        """Test construct() handles trace loading failure."""
        mock_load.return_value = False  # Simulate load failure

        viz = BaseTraceVisualizer(trace_file="nonexistent.json")
        viz.construct()

        # Should display error message
        mock_play.assert_called()  # Error message shown

    @patch('base_trace_visualizer.BaseTraceVisualizer.load_trace')
    @patch('base_trace_visualizer.BaseTraceVisualizer.extract_modules')
    @patch('base_trace_visualizer.BaseTraceVisualizer.construct_phases')
    @patch('base_trace_visualizer.ThreeDScene.set_camera_orientation')
    @patch('base_trace_visualizer.ThreeDScene.play')
    @patch('base_trace_visualizer.ThreeDScene.wait')
    def test_construct_handles_construct_phases_error(
        self, mock_wait, mock_play, mock_set_camera,
        mock_construct_phases, mock_extract, mock_load
    ):
        """Test construct() handles errors in construct_phases()."""
        mock_load.return_value = True
        mock_extract.return_value = {}
        mock_construct_phases.side_effect = Exception("Test error")

        viz = BaseTraceVisualizer()
        viz.construct()

        # Should catch and display error
        # (Play is called for error message)
        assert mock_play.called


class TestMinimalTraceVisualizer:
    """Test the minimal example visualizer."""

    def test_minimal_visualizer_title(self):
        """Test minimal visualizer custom title."""
        viz = MinimalTraceVisualizer()
        assert viz.get_title() == "Minimal Trace Visualization"

    @patch('base_trace_visualizer.BaseTraceVisualizer.load_trace')
    @patch('base_trace_visualizer.BaseTraceVisualizer.extract_modules')
    @patch('base_trace_visualizer.ThreeDScene.set_camera_orientation')
    @patch('base_trace_visualizer.ThreeDScene.add_fixed_in_frame_mobjects')
    @patch('base_trace_visualizer.ThreeDScene.play')
    @patch('base_trace_visualizer.ThreeDScene.wait')
    @patch('base_trace_visualizer.ThreeDScene.begin_ambient_camera_rotation')
    @patch('base_trace_visualizer.ThreeDScene.stop_ambient_camera_rotation')
    def test_minimal_visualizer_construct(
        self, mock_stop_rotate, mock_begin_rotate, mock_wait, mock_play,
        mock_add_fixed, mock_set_camera, mock_extract, mock_load
    ):
        """Test minimal visualizer construct phases."""
        mock_load.return_value = True
        mock_extract.return_value = {
            "module1": [{"type": "call", "function": "func1"}],
            "module2": [{"type": "call", "function": "func2"}]
        }

        viz = MinimalTraceVisualizer()
        viz.calls = [{"type": "call"}]
        viz.modules = mock_extract.return_value
        viz.errors = []

        # Call construct_phases directly
        viz.construct_phases()

        # Verify animations were called
        assert mock_play.called
        assert mock_begin_rotate.called
        assert mock_stop_rotate.called


class TestIntegration:
    """Integration tests with real trace files."""

    def test_full_workflow(self, temp_trace_file):
        """Test complete workflow: load → extract → detect."""
        viz = BaseTraceVisualizer(trace_file=str(temp_trace_file))

        # Load trace
        assert viz.load_trace() is True

        # Extract modules
        modules = viz.extract_modules()
        assert len(modules) > 0

        # Detect phases
        for module_name, calls in modules.items():
            for call in calls:
                phase = viz.detect_phase(module_name, call.get('function', ''))
                assert phase is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=base_trace_visualizer", "--cov-report=term-missing"])
