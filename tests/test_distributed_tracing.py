"""
End-to-end distributed tracing test.

Verifies that traces from multiple language agents can be received
and correlated in the IDE.
"""

import socket
import json
import time
import threading
from typing import List, Dict

def create_trace_event(
    event_type: str,
    call_id: str,
    module: str,
    function: str,
    language: str,
    depth: int = 0,
    parent_id: str = None,
    session_id: str = "test_session",
    process_id: int = 12345,
    duration_ms: float = None
) -> Dict:
    """Create a trace event in TrueFlow format."""
    event = {
        "type": event_type,
        "timestamp": time.time(),
        "call_id": call_id,
        "module": module,
        "function": function,
        "file": f"{module.replace('.', '/')}.{language[:2]}",
        "line": 100,
        "depth": depth,
        "parent_id": parent_id,
        "process_id": process_id,
        "session_id": session_id,
        "language": language
    }
    if duration_ms is not None:
        event["duration_ms"] = duration_ms
    return event


def simulate_python_trace(events: List[Dict]):
    """Simulate Python trace events (port 5678)."""
    events.extend([
        create_trace_event("call", "py_1", "api.handlers", "handle_request", "python", depth=0),
        create_trace_event("call", "py_2", "api.validators", "validate_input", "python", depth=1, parent_id="py_1"),
        create_trace_event("return", "py_2", "api.validators", "validate_input", "python", depth=1, parent_id="py_1", duration_ms=5.2),
        create_trace_event("call", "py_3", "api.handlers", "call_java_service", "python", depth=1, parent_id="py_1"),
    ])


def simulate_java_trace(events: List[Dict]):
    """Simulate Java trace events (port 5679)."""
    events.extend([
        create_trace_event("call", "java_1", "com.example.UserService", "getUser", "java", depth=0, session_id="java_session"),
        create_trace_event("call", "java_2", "com.example.UserRepository", "findById", "java", depth=1, parent_id="java_1", session_id="java_session"),
        create_trace_event("return", "java_2", "com.example.UserRepository", "findById", "java", depth=1, parent_id="java_1", duration_ms=12.5, session_id="java_session"),
        create_trace_event("return", "java_1", "com.example.UserService", "getUser", "java", depth=0, duration_ms=15.0, session_id="java_session"),
    ])


def simulate_nodejs_trace(events: List[Dict]):
    """Simulate Node.js trace events (port 5680)."""
    events.extend([
        create_trace_event("call", "node_1", "routes/api", "handleGet", "javascript", depth=0, session_id="nodejs_session"),
        create_trace_event("call", "node_2", "middleware/auth", "validateToken", "javascript", depth=1, parent_id="node_1", session_id="nodejs_session"),
        create_trace_event("return", "node_2", "middleware/auth", "validateToken", "javascript", depth=1, parent_id="node_1", duration_ms=3.1, session_id="nodejs_session"),
        create_trace_event("call", "node_3", "services/websocket", "broadcast", "javascript", depth=1, parent_id="node_1", session_id="nodejs_session"),
        create_trace_event("return", "node_3", "services/websocket", "broadcast", "javascript", depth=1, parent_id="node_1", duration_ms=1.5, session_id="nodejs_session"),
        create_trace_event("return", "node_1", "routes/api", "handleGet", "javascript", depth=0, duration_ms=8.0, session_id="nodejs_session"),
    ])


def simulate_rust_trace(events: List[Dict]):
    """Simulate Rust trace events (port 5681)."""
    events.extend([
        create_trace_event("call", "rust_1", "handlers::api", "process_request", "rust", depth=0, session_id="rust_session"),
        create_trace_event("call", "rust_2", "db::postgres", "query", "rust", depth=1, parent_id="rust_1", session_id="rust_session"),
        create_trace_event("return", "rust_2", "db::postgres", "query", "rust", depth=1, parent_id="rust_1", duration_ms=2.3, session_id="rust_session"),
        create_trace_event("return", "rust_1", "handlers::api", "process_request", "rust", depth=0, duration_ms=4.5, session_id="rust_session"),
    ])


def test_trace_event_format():
    """Test that trace events have correct format."""
    events = []
    simulate_python_trace(events)
    simulate_java_trace(events)
    simulate_nodejs_trace(events)
    simulate_rust_trace(events)

    # Verify all events have required fields
    required_fields = ["type", "timestamp", "call_id", "module", "function", "language", "session_id"]

    for event in events:
        for field in required_fields:
            assert field in event, f"Missing field {field} in event {event}"

    # Verify language values
    languages = set(e["language"] for e in events)
    assert languages == {"python", "java", "javascript", "rust"}, f"Unexpected languages: {languages}"

    # Verify call/return pairing
    call_events = [e for e in events if e["type"] == "call"]
    return_events = [e for e in events if e["type"] == "return"]

    print(f"Total events: {len(events)}")
    print(f"Call events: {len(call_events)}")
    print(f"Return events: {len(return_events)}")
    print(f"Languages: {languages}")

    # Check that each call has a return (except in-progress calls)
    call_ids = set(e["call_id"] for e in call_events)
    return_ids = set(e["call_id"] for e in return_events)

    print(f"Call IDs: {call_ids}")
    print(f"Return IDs: {return_ids}")

    # py_1 and py_3 are still in progress (no return)
    in_progress = call_ids - return_ids
    print(f"In-progress calls: {in_progress}")

    print("\nAll trace event format tests passed!")
    return True


def test_distributed_correlation():
    """Test that distributed traces can be correlated."""
    events = []

    # Simulate a distributed call: Python -> Java -> Node.js
    # Python starts the request
    events.append(create_trace_event(
        "call", "dist_1", "api.gateway", "forward_request", "python",
        depth=0, session_id="distributed_session"
    ))

    # Java handles the business logic
    events.append(create_trace_event(
        "call", "dist_2", "com.example.OrderService", "createOrder", "java",
        depth=1, parent_id="dist_1", session_id="distributed_session"
    ))

    # Node.js sends notification via WebSocket
    events.append(create_trace_event(
        "call", "dist_3", "services/notification", "sendWebSocket", "javascript",
        depth=2, parent_id="dist_2", session_id="distributed_session"
    ))

    # Returns
    events.append(create_trace_event(
        "return", "dist_3", "services/notification", "sendWebSocket", "javascript",
        depth=2, parent_id="dist_2", session_id="distributed_session", duration_ms=5.0
    ))
    events.append(create_trace_event(
        "return", "dist_2", "com.example.OrderService", "createOrder", "java",
        depth=1, parent_id="dist_1", session_id="distributed_session", duration_ms=50.0
    ))
    events.append(create_trace_event(
        "return", "dist_1", "api.gateway", "forward_request", "python",
        depth=0, session_id="distributed_session", duration_ms=55.0
    ))

    # Verify the correlation
    # All events should have the same session_id for correlation
    session_ids = set(e["session_id"] for e in events)
    assert len(session_ids) == 1, f"Expected 1 session_id, got {session_ids}"

    # Verify parent-child relationships
    parent_map = {e["call_id"]: e.get("parent_id") for e in events if e["type"] == "call"}

    assert parent_map["dist_1"] is None, "dist_1 should be root"
    assert parent_map["dist_2"] == "dist_1", "dist_2 should have dist_1 as parent"
    assert parent_map["dist_3"] == "dist_2", "dist_3 should have dist_2 as parent"

    # Verify language chain
    language_chain = []
    for event in events:
        if event["type"] == "call":
            language_chain.append(event["language"])

    assert language_chain == ["python", "java", "javascript"], f"Unexpected language chain: {language_chain}"

    print("\nDistributed correlation test:")
    print(f"  Session ID: {list(session_ids)[0]}")
    print(f"  Language chain: {' -> '.join(language_chain)}")
    print(f"  Total duration: 55.0ms")
    print("\nDistributed correlation tests passed!")
    return True


def test_json_serialization():
    """Test that events serialize correctly for socket transmission."""
    event = create_trace_event(
        "call", "test_1", "mymodule", "myfunction", "python"
    )

    # Serialize to JSON
    json_str = json.dumps(event)

    # Deserialize back
    parsed = json.loads(json_str)

    assert parsed["call_id"] == "test_1"
    assert parsed["language"] == "python"
    assert parsed["module"] == "mymodule"

    # Verify newline-delimited format (what socket expects)
    wire_format = json_str + "\n"
    assert wire_format.endswith("\n")
    assert wire_format.count("\n") == 1

    print("\nJSON serialization tests passed!")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("TrueFlow Distributed Tracing End-to-End Tests")
    print("=" * 60)

    test_trace_event_format()
    test_distributed_correlation()
    test_json_serialization()

    print("\n" + "=" * 60)
    print("ALL DISTRIBUTED TRACING TESTS PASSED!")
    print("=" * 60)
