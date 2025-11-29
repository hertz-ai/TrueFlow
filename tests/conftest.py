"""
Root pytest configuration for TrueFlow tests.

This conftest.py ensures proper PYTHONPATH setup for all test modules
regardless of how pytest is invoked (command line, IDE, CI, etc.).
"""

import sys
import os
from pathlib import Path

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent

# Add all necessary paths to sys.path BEFORE any imports
# This fixes the ModuleNotFoundError issues on fresh builds
paths_to_add = [
    str(PROJECT_ROOT),
    str(PROJECT_ROOT / "src" / "main" / "resources" / "runtime_injector"),
    str(PROJECT_ROOT / "src" / "main" / "resources"),
    str(PROJECT_ROOT / "manim_visualizer"),
    str(PROJECT_ROOT / "tests"),
]

for path in paths_to_add:
    if path not in sys.path:
        sys.path.insert(0, path)

# Set environment variable as well for subprocess calls
os.environ["PYTHONPATH"] = os.pathsep.join(paths_to_add + [os.environ.get("PYTHONPATH", "")])


# Now we can safely import test utilities
import pytest
import json
import tempfile
from typing import Dict


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the project root directory."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def runtime_injector_path() -> Path:
    """Return the runtime_injector directory path."""
    return PROJECT_ROOT / "src" / "main" / "resources" / "runtime_injector"


@pytest.fixture(scope="session")
def manim_visualizer_path() -> Path:
    """Return the manim_visualizer directory path."""
    return PROJECT_ROOT / "manim_visualizer"


@pytest.fixture
def sample_trace_data() -> Dict:
    """Sample trace data for testing."""
    return {
        "correlation_id": "test_123",
        "session_id": "session_456",
        "timestamp": 1700000000.0,
        "calls": [
            {
                "type": "call",
                "timestamp": 1700000001.0,
                "call_id": "call_1",
                "module": "src.crawl4ai.embodied_ai.rl_ef.learning_llm_provider",
                "function": "__init__",
                "file": "/path/to/file.py",
                "line": 100,
                "depth": 0,
                "parent_id": None,
            },
            {
                "type": "call",
                "timestamp": 1700000002.0,
                "call_id": "call_2",
                "module": "src.crawl4ai.embodied_ai.learning.reality_grounded_learner",
                "function": "learn_from_experience",
                "file": "/path/to/file2.py",
                "line": 200,
                "depth": 1,
                "parent_id": "call_1",
            },
            {
                "type": "return",
                "timestamp": 1700000003.0,
                "call_id": "call_2",
                "module": "src.crawl4ai.embodied_ai.learning.reality_grounded_learner",
                "function": "learn_from_experience",
                "depth": 1,
            },
        ],
        "errors": []
    }


@pytest.fixture
def temp_trace_file(sample_trace_data, tmp_path) -> Path:
    """Create temporary trace file."""
    trace_file = tmp_path / "test_trace.json"
    with open(trace_file, 'w') as f:
        json.dump(sample_trace_data, f)
    return trace_file


@pytest.fixture
def trace_file_with_errors() -> Dict:
    """Trace data with errors."""
    return {
        "correlation_id": "test_error",
        "calls": [
            {
                "type": "call",
                "call_id": "err_1",
                "module": "test.module",
                "function": "failing_function",
                "file": "/path/to/error.py",
                "line": 100,
                "depth": 0
            },
            {
                "type": "error",
                "call_id": "err_1",
                "module": "test.module",
                "function": "failing_function",
                "error": "ValueError: Something went wrong",
                "traceback": "Traceback...",
            }
        ],
        "errors": ["ValueError: Something went wrong"]
    }


# Configure pytest markers
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "manim: marks tests that require manim"
    )
    config.addinivalue_line(
        "markers", "integration: marks integration tests"
    )
    config.addinivalue_line(
        "markers", "e2e: marks end-to-end tests"
    )
