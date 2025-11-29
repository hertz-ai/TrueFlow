"""
TrueFlow E2E Regression Test Configuration
==========================================

Shared fixtures and configuration for end-to-end testing.
"""

import pytest
import os
import sys
import tempfile
import shutil
import json
from pathlib import Path
from datetime import datetime

# Add project paths
TRUEFLOW_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(TRUEFLOW_ROOT / "runtime_injector"))
sys.path.insert(0, str(TRUEFLOW_ROOT / "manim_visualizer"))


@pytest.fixture(scope="session")
def trueflow_root():
    """Return the TrueFlow project root directory."""
    return TRUEFLOW_ROOT


@pytest.fixture(scope="session")
def runtime_injector_path():
    """Return path to runtime injector."""
    return TRUEFLOW_ROOT / "runtime_injector"


@pytest.fixture(scope="session")
def manim_visualizer_path():
    """Return path to manim visualizer."""
    return TRUEFLOW_ROOT / "manim_visualizer"


@pytest.fixture(scope="function")
def temp_project_dir():
    """Create a temporary project directory for testing."""
    temp_dir = tempfile.mkdtemp(prefix="trueflow_test_")
    yield Path(temp_dir)
    # Cleanup after test
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def temp_trace_dir(temp_project_dir):
    """Create a temporary trace directory."""
    trace_dir = temp_project_dir / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    return trace_dir


@pytest.fixture(scope="function")
def sample_python_app(temp_project_dir):
    """Create a sample Python application for testing instrumentation."""
    app_file = temp_project_dir / "sample_app.py"
    app_file.write_text('''
"""Sample application for TrueFlow testing."""

import time
import json

class DataProcessor:
    """Sample data processor class."""

    def __init__(self, name="default"):
        self.name = name
        self.data = []

    def load_data(self, items):
        """Load data items."""
        self.data = items
        return len(items)

    def process(self):
        """Process loaded data."""
        results = []
        for item in self.data:
            results.append(self._transform(item))
        return results

    def _transform(self, item):
        """Transform a single item."""
        return {"processed": item, "timestamp": time.time()}

class APIHandler:
    """Sample API handler."""

    def __init__(self, processor):
        self.processor = processor

    def handle_request(self, request_data):
        """Handle an API request."""
        self.processor.load_data(request_data.get("items", []))
        results = self.processor.process()
        return {"status": "success", "results": results}

def main():
    """Main entry point."""
    processor = DataProcessor("test")
    handler = APIHandler(processor)

    # Simulate API calls
    for i in range(3):
        response = handler.handle_request({"items": [f"item_{i}"]})
        print(f"Response {i}: {json.dumps(response)}")

    return "completed"

if __name__ == "__main__":
    main()
''')
    return app_file


@pytest.fixture(scope="function")
def sample_trace_json(temp_trace_dir):
    """Create a sample trace JSON file."""
    trace_data = {
        "session_id": "test_session_001",
        "start_time": datetime.now().isoformat(),
        "events": [
            {
                "type": "call",
                "timestamp": 0.001,
                "call_id": "call_001",
                "module": "sample_app",
                "function": "main",
                "file": "/test/sample_app.py",
                "line": 45,
                "depth": 0
            },
            {
                "type": "call",
                "timestamp": 0.002,
                "call_id": "call_002",
                "module": "sample_app",
                "function": "__init__",
                "class": "DataProcessor",
                "file": "/test/sample_app.py",
                "line": 10,
                "depth": 1
            },
            {
                "type": "call",
                "timestamp": 0.003,
                "call_id": "call_003",
                "module": "sample_app",
                "function": "handle_request",
                "class": "APIHandler",
                "file": "/test/sample_app.py",
                "line": 35,
                "depth": 1
            },
            {
                "type": "call",
                "timestamp": 0.004,
                "call_id": "call_004",
                "module": "sample_app",
                "function": "load_data",
                "class": "DataProcessor",
                "file": "/test/sample_app.py",
                "line": 15,
                "depth": 2
            },
            {
                "type": "call",
                "timestamp": 0.005,
                "call_id": "call_005",
                "module": "sample_app",
                "function": "process",
                "class": "DataProcessor",
                "file": "/test/sample_app.py",
                "line": 20,
                "depth": 2
            },
            {
                "type": "call",
                "timestamp": 0.006,
                "call_id": "call_006",
                "module": "sample_app",
                "function": "_transform",
                "class": "DataProcessor",
                "file": "/test/sample_app.py",
                "line": 27,
                "depth": 3
            }
        ],
        "statistics": {
            "total_calls": 6,
            "total_duration_ms": 10.5,
            "unique_functions": 6
        }
    }

    trace_file = temp_trace_dir / "test_trace.json"
    trace_file.write_text(json.dumps(trace_data, indent=2))
    return trace_file


@pytest.fixture(scope="session")
def python_executable():
    """Return Python executable path."""
    return sys.executable


# Test markers
def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests (fast, isolated)")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "slow: Slow tests (Manim rendering, etc.)")
    config.addinivalue_line("markers", "requires_manim: Tests requiring Manim installation")
    config.addinivalue_line("markers", "requires_plugin: Tests requiring PyCharm plugin")
