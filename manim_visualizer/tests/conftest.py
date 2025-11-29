"""
Pytest configuration and shared fixtures.
"""

import pytest
import json
import tempfile
from pathlib import Path
from typing import Dict, List


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
                "process_id": 12345,
                "session_id": "session_456",
                "correlation_id": "test_123",
                "learning_phase": "encoding"
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
                "process_id": 12345,
                "session_id": "session_456",
                "correlation_id": "test_123",
                "learning_phase": "learning"
            },
            {
                "type": "return",
                "timestamp": 1700000003.0,
                "call_id": "call_2",
                "module": "src.crawl4ai.embodied_ai.learning.reality_grounded_learner",
                "function": "learn_from_experience",
                "file": "/path/to/file2.py",
                "line": 200,
                "depth": 1,
                "parent_id": "call_1",
                "process_id": 12345,
                "session_id": "session_456",
                "correlation_id": "test_123",
                "learning_phase": "learning"
            },
            {
                "type": "call",
                "timestamp": 1700000004.0,
                "call_id": "call_3",
                "module": "src.crawl4ai.embodied_ai.learning.semantic_reasoner",
                "function": "reason",
                "file": "/path/to/file3.py",
                "line": 300,
                "depth": 1,
                "parent_id": "call_1",
                "process_id": 12345,
                "session_id": "session_456",
                "correlation_id": "test_123",
                "learning_phase": "reasoning"
            }
        ],
        "errors": []
    }


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
                "file": "/path/to/error.py",
                "line": 105
            }
        ],
        "errors": ["ValueError: Something went wrong"]
    }


@pytest.fixture
def temp_trace_file(sample_trace_data) -> Path:
    """Create temporary trace file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(sample_trace_data, f)
        return Path(f.name)


@pytest.fixture
def temp_trace_file_with_errors(trace_file_with_errors) -> Path:
    """Create temporary trace file with errors."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(trace_file_with_errors, f)
        return Path(f.name)


@pytest.fixture
def empty_trace_file() -> Path:
    """Create empty trace file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({"calls": [], "errors": []}, f)
        return Path(f.name)


@pytest.fixture
def invalid_json_file() -> Path:
    """Create file with invalid JSON."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("{ invalid json }")
        return Path(f.name)


@pytest.fixture
def cleanup_temp_files():
    """Cleanup fixture that runs after tests."""
    yield
    # Cleanup code can go here if needed
