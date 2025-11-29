"""
ROOT pytest configuration for TrueFlow.

This conftest.py is loaded FIRST by pytest and sets up PYTHONPATH
before any test discovery or imports happen.

This is the recommended way to handle import paths in pytest.
"""

import sys
import os
from pathlib import Path

# Get project root directory - this file is at the root
PROJECT_ROOT = Path(__file__).parent

# Add all necessary paths to sys.path BEFORE any imports
# ORDER MATTERS - more specific paths first
paths_to_add = [
    str(PROJECT_ROOT / "manim_visualizer"),  # For logging_config, etc.
    str(PROJECT_ROOT / "src" / "main" / "resources" / "runtime_injector"),
    str(PROJECT_ROOT / "src" / "main" / "resources"),
    str(PROJECT_ROOT),
    str(PROJECT_ROOT / "tests"),
]

for path in paths_to_add:
    if path not in sys.path:
        sys.path.insert(0, path)

# Set environment variable for any subprocess calls
os.environ["PYTHONPATH"] = os.pathsep.join(paths_to_add + [os.environ.get("PYTHONPATH", "")])


# Now we can safely import pytest and other modules
import pytest


def pytest_configure(config):
    """Configure pytest with custom markers and settings."""
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
    config.addinivalue_line(
        "markers", "visual: marks visual regression tests"
    )


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
