"""
Test Utilities for Manim Visualizer Testing

Provides helper functions for:
- Video validation (using ffprobe)
- Frame analysis (checking bounds, text readability)
- Trace file generation
- Performance measurement
- Visualizer discovery
"""

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# VIDEO VALIDATION
# ============================================================================

@dataclass
class VideoInfo:
    """Video file information."""
    duration: float  # seconds
    width: int
    height: int
    frame_count: int
    fps: float
    file_size: int  # bytes


def get_video_info(video_path: Path) -> Optional[VideoInfo]:
    """
    Get video information using ffprobe.

    Args:
        video_path: Path to video file

    Returns:
        VideoInfo object or None if ffprobe unavailable
    """
    try:
        result = subprocess.run(
            [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=duration,width,height,nb_frames,r_frame_rate',
                '-of', 'json',
                str(video_path)
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10
        )

        data = json.loads(result.stdout)
        stream = data.get('streams', [{}])[0]

        # Parse frame rate (may be fraction like "30/1")
        fps_str = stream.get('r_frame_rate', '30/1')
        if '/' in fps_str:
            num, den = map(int, fps_str.split('/'))
            fps = num / den if den != 0 else 30.0
        else:
            fps = float(fps_str)

        return VideoInfo(
            duration=float(stream.get('duration', 0)),
            width=int(stream.get('width', 0)),
            height=int(stream.get('height', 0)),
            frame_count=int(stream.get('nb_frames', 0)),
            fps=fps,
            file_size=video_path.stat().st_size
        )
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError, subprocess.TimeoutExpired) as e:
        logger.warning(f"Could not get video info: {e}")
        return None


def validate_video_quality(
    video_path: Path,
    min_duration: float = 5.0,
    max_duration: float = 120.0,
    expected_width: int = 1920,
    expected_height: int = 1080
) -> Tuple[bool, List[str]]:
    """
    Validate video quality against expected parameters.

    Args:
        video_path: Path to video
        min_duration: Minimum expected duration (seconds)
        max_duration: Maximum expected duration (seconds)
        expected_width: Expected video width
        expected_height: Expected video height

    Returns:
        (is_valid, list_of_issues)
    """
    issues = []

    # Check file exists
    if not video_path.exists():
        return False, ["Video file not found"]

    # Get video info
    info = get_video_info(video_path)
    if not info:
        issues.append("Could not read video metadata (ffprobe unavailable)")
        return len(issues) == 0, issues

    # Validate duration
    if info.duration < min_duration:
        issues.append(f"Video too short: {info.duration:.1f}s < {min_duration}s")
    if info.duration > max_duration:
        issues.append(f"Video too long: {info.duration:.1f}s > {max_duration}s")

    # Validate resolution
    if info.width != expected_width:
        issues.append(f"Unexpected width: {info.width} (expected {expected_width})")
    if info.height != expected_height:
        issues.append(f"Unexpected height: {info.height} (expected {expected_height})")

    # Validate frame count
    expected_frames = int(info.duration * info.fps)
    frame_diff = abs(info.frame_count - expected_frames)
    if frame_diff > info.fps:  # Allow 1 second tolerance
        issues.append(f"Frame count mismatch: {info.frame_count} vs expected ~{expected_frames}")

    # Validate file size (should be > 100KB for real video)
    if info.file_size < 100 * 1024:
        issues.append(f"Video file too small: {info.file_size / 1024:.1f}KB")

    return len(issues) == 0, issues


# ============================================================================
# VISUALIZER DISCOVERY
# ============================================================================

def discover_visualizer_scripts(base_dir: Path) -> List[Path]:
    """
    Discover all visualizer scripts.

    Args:
        base_dir: Base directory to search

    Returns:
        List of visualizer script paths
    """
    visualizers = []

    # Patterns for visualizer files
    patterns = [
        "*viz*.py",
        "*visualizer*.py"
    ]

    for pattern in patterns:
        found = list(base_dir.glob(pattern))
        visualizers.extend(found)

    # Filter out test files, __init__, etc.
    visualizers = [
        v for v in visualizers
        if 'test' not in v.name.lower()
        and v.name != '__init__.py'
        and '__pycache__' not in str(v)
    ]

    # Remove duplicates and sort
    visualizers = sorted(set(visualizers))

    return visualizers


def discover_trace_files(trace_dir: Path, limit: int = 5) -> List[Path]:
    """
    Discover trace files.

    Args:
        trace_dir: Directory containing traces
        limit: Maximum number of traces to return

    Returns:
        List of trace file paths
    """
    if not trace_dir.exists():
        return []

    traces = list(trace_dir.glob("trace_*.json"))[:limit]
    return traces


# ============================================================================
# TRACE FILE GENERATION
# ============================================================================

def create_minimal_trace(
    num_calls: int = 3,
    include_errors: bool = False
) -> Dict:
    """
    Create minimal synthetic trace.

    Args:
        num_calls: Number of calls to include
        include_errors: Whether to include error events

    Returns:
        Trace data dictionary
    """
    calls = []

    for i in range(num_calls):
        calls.append({
            "type": "call",
            "call_id": f"call_{i}",
            "module": f"test.module{i % 3}",
            "function": f"function_{i}",
            "file": "/test.py",
            "line": 10 + i * 10,
            "depth": 0,
            "timestamp": 1700000000.0 + i
        })

    if include_errors:
        calls.append({
            "type": "error",
            "call_id": "call_err",
            "module": "test.error_module",
            "function": "failing_function",
            "error": "ValueError: Test error",
            "traceback": "Traceback...",
            "file": "/error.py",
            "line": 100,
            "timestamp": 1700000000.0 + num_calls
        })

    return {
        "correlation_id": "test_minimal",
        "calls": calls,
        "errors": ["ValueError: Test error"] if include_errors else []
    }


def create_comprehensive_trace() -> Dict:
    """
    Create comprehensive trace covering all learning phases.

    Returns:
        Trace data dictionary
    """
    phases = [
        ("sensor", "src.crawl4ai.embodied_ai.sensor", "capture", "ingest_data"),
        ("encoding", "src.crawl4ai.embodied_ai.encoder", "encode", "encode_multimodal"),
        ("reasoning", "src.crawl4ai.embodied_ai.learning.semantic_reasoner", "reason", "semantic_reasoning"),
        ("decoding", "src.crawl4ai.embodied_ai.decoder", "decode", "generate_output"),
        ("learning", "src.crawl4ai.embodied_ai.learning.learner", "learn", "learn_from_experience"),
        ("memory", "src.crawl4ai.embodied_ai.memory.hierarchical", "store", "hierarchical_store")
    ]

    calls = []
    for i, (phase, module, func_prefix, function) in enumerate(phases):
        calls.append({
            "type": "call",
            "call_id": f"call_{i}",
            "module": module,
            "function": function,
            "file": f"/{module.replace('.', '/')}.py",
            "line": 100 + i * 10,
            "depth": 0,
            "timestamp": 1700000000.0 + i,
            "learning_phase": phase
        })

    return {
        "correlation_id": "test_comprehensive",
        "calls": calls,
        "errors": []
    }


def save_trace_to_file(trace_data: Dict) -> Path:
    """
    Save trace data to temporary file.

    Args:
        trace_data: Trace dictionary

    Returns:
        Path to created file
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(trace_data, f)
        return Path(f.name)


# ============================================================================
# PERFORMANCE MEASUREMENT
# ============================================================================

class PerformanceTimer:
    """Context manager for timing code execution."""

    def __init__(self, description: str = "Operation"):
        self.description = description
        self.start_time = None
        self.elapsed = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed = time.time() - self.start_time
        logger.info(f"{self.description} took {self.elapsed:.3f}s")
        return False


def measure_execution_time(func, *args, **kwargs) -> Tuple[Any, float]:
    """
    Measure function execution time.

    Args:
        func: Function to execute
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        (result, elapsed_time)
    """
    start = time.time()
    result = func(*args, **kwargs)
    elapsed = time.time() - start
    return result, elapsed


# ============================================================================
# FRAME ANALYSIS
# ============================================================================

def check_frame_bounds(video_path: Path, sample_count: int = 10) -> Tuple[bool, List[str]]:
    """
    Check if video frames have elements within bounds.

    Note: This is a placeholder. Full implementation would require
    OpenCV or similar to extract frames and analyze pixel data.

    Args:
        video_path: Path to video
        sample_count: Number of frames to sample

    Returns:
        (all_in_bounds, list_of_issues)
    """
    issues = []

    # Check file exists
    if not video_path.exists():
        return False, ["Video file not found"]

    # TODO: Implement frame extraction and analysis
    # Would require:
    # 1. Extract frames using ffmpeg
    # 2. Load frames with PIL/OpenCV
    # 3. Check for non-black pixels near edges (indicates cutoff elements)
    # 4. Check for text readability (contrast, size)

    # For now, just verify file is readable
    try:
        video_path.stat()
    except Exception as e:
        issues.append(f"Cannot read video file: {e}")

    return len(issues) == 0, issues


# ============================================================================
# TEST DATA FIXTURES
# ============================================================================

class TraceFixtures:
    """Predefined trace fixtures for testing."""

    @staticmethod
    def empty_trace() -> Dict:
        """Empty trace (no calls)."""
        return {"calls": [], "errors": []}

    @staticmethod
    def single_call_trace() -> Dict:
        """Single function call."""
        return {
            "correlation_id": "single_call",
            "calls": [
                {
                    "type": "call",
                    "call_id": "call_1",
                    "module": "test.module",
                    "function": "test_function",
                    "file": "/test.py",
                    "line": 10,
                    "depth": 0,
                    "timestamp": 1700000000.0
                }
            ],
            "errors": []
        }

    @staticmethod
    def nested_calls_trace() -> Dict:
        """Nested function calls."""
        return {
            "correlation_id": "nested_calls",
            "calls": [
                {
                    "type": "call",
                    "call_id": "call_1",
                    "module": "test.outer",
                    "function": "outer_function",
                    "file": "/test.py",
                    "line": 10,
                    "depth": 0,
                    "parent_id": None,
                    "timestamp": 1700000000.0
                },
                {
                    "type": "call",
                    "call_id": "call_2",
                    "module": "test.inner",
                    "function": "inner_function",
                    "file": "/test.py",
                    "line": 20,
                    "depth": 1,
                    "parent_id": "call_1",
                    "timestamp": 1700000001.0
                },
                {
                    "type": "return",
                    "call_id": "call_2",
                    "module": "test.inner",
                    "function": "inner_function",
                    "file": "/test.py",
                    "line": 20,
                    "depth": 1,
                    "timestamp": 1700000002.0
                },
                {
                    "type": "return",
                    "call_id": "call_1",
                    "module": "test.outer",
                    "function": "outer_function",
                    "file": "/test.py",
                    "line": 10,
                    "depth": 0,
                    "timestamp": 1700000003.0
                }
            ],
            "errors": []
        }


# ============================================================================
# ASSERTION HELPERS
# ============================================================================

def assert_video_valid(
    video_path: Path,
    min_duration: float = 5.0,
    max_duration: float = 120.0
):
    """
    Assert that video is valid (raises AssertionError if not).

    Args:
        video_path: Path to video
        min_duration: Minimum expected duration
        max_duration: Maximum expected duration
    """
    is_valid, issues = validate_video_quality(
        video_path,
        min_duration=min_duration,
        max_duration=max_duration
    )

    if not is_valid:
        raise AssertionError(f"Video validation failed:\n" + "\n".join(f"  - {issue}" for issue in issues))


def assert_trace_valid(trace_data: Dict):
    """
    Assert that trace data is valid.

    Args:
        trace_data: Trace dictionary
    """
    assert isinstance(trace_data, dict), "Trace must be a dictionary"
    assert "calls" in trace_data, "Trace must have 'calls' field"
    assert isinstance(trace_data["calls"], list), "Trace 'calls' must be a list"


def assert_execution_time_under(elapsed: float, max_time: float, operation: str = "Operation"):
    """
    Assert that execution time is under limit.

    Args:
        elapsed: Elapsed time in seconds
        max_time: Maximum allowed time
        operation: Description of operation
    """
    assert elapsed < max_time, f"{operation} too slow: {elapsed:.2f}s > {max_time}s"


# ============================================================================
# SUBPROCESS HELPERS
# ============================================================================

def run_visualizer_script(
    script_path: Path,
    trace_file: Path,
    timeout: int = 120
) -> subprocess.CompletedProcess:
    """
    Run visualizer script with trace file.

    Args:
        script_path: Path to visualizer script
        trace_file: Path to trace JSON
        timeout: Timeout in seconds

    Returns:
        CompletedProcess result
    """
    import sys

    result = subprocess.run(
        [sys.executable, str(script_path), str(trace_file)],
        capture_output=True,
        text=True,
        timeout=timeout
    )

    return result


def check_render_success(result: subprocess.CompletedProcess) -> Tuple[bool, str]:
    """
    Check if render was successful.

    Args:
        result: CompletedProcess from run_visualizer_script

    Returns:
        (success, error_message)
    """
    if result.returncode == 0:
        return True, ""

    # Check for common error patterns
    stderr_lower = result.stderr.lower()
    stdout_lower = result.stdout.lower()

    if "traceback" in stderr_lower:
        return False, "Python traceback in stderr"

    if "error" in stderr_lower and "0 errors" not in stderr_lower:
        return False, f"Errors in stderr: {result.stderr[:200]}"

    if "usage:" in stdout_lower:
        return False, "Script requires different arguments"

    return False, f"Non-zero return code: {result.returncode}"
