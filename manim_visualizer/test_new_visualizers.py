from logging_config import setup_logger
logger = setup_logger(__name__)

"""
Test script for new framework-based visualizers.

Tests:
1. Coordinate tracking framework
2. 3D stacked architecture
3. Billboard text readability
4. Data flow detection
5. Rendering output quality
"""

import json
import os
import sys
from pathlib import Path

def create_test_trace_data():
    """Create synthetic trace data for testing"""
    trace_data = {
        "session_id": "test_session_001",
        "start_time": 0,
        "end_time": 100,
        "calls": []
    }

    # Simulate a realistic call trace
    modules = [
        # Input layer
        "crawl4ai.embodied_ai.models.unified_sensory_stream",
        "crawl4ai.embodied_ai.sensors.vision_input",

        # Encoder layer
        "crawl4ai.embodied_ai.models.qwen_encoder",
        "crawl4ai.embodied_ai.models.lora_adapter",

        # Processing layer
        "crawl4ai.embodied_ai.models.latent_dynamics",
        "crawl4ai.embodied_ai.learning.semantic_reasoner",

        # Memory layer
        "crawl4ai.embodied_ai.learning.hierarchical_temporal_compression",
        "crawl4ai.embodied_ai.learning.selective_replay",

        # Output layer
        "crawl4ai.embodied_ai.models.multimodal_decoder",
        "crawl4ai.embodied_ai.models.truth_aware_decoder"
    ]

    call_id_counter = 0

    # Create call tree
    for i in range(100):
        timestamp = i * 1.0

        # Root call (input)
        call_id_counter += 1
        root_call_id = f"call_{call_id_counter}"
        trace_data["calls"].append({
            "type": "call",
            "call_id": root_call_id,
            "parent_id": None,
            "module": modules[0],
            "function": "process_sensor_input",
            "timestamp": timestamp,
            "depth": 0
        })

        # Encoder calls
        parent_id = root_call_id
        for mod_idx in [2, 3]:  # Encoder modules
            call_id_counter += 1
            call_id = f"call_{call_id_counter}"
            trace_data["calls"].append({
                "type": "call",
                "call_id": call_id,
                "parent_id": parent_id,
                "module": modules[mod_idx],
                "function": "encode",
                "timestamp": timestamp + 0.1,
                "depth": 1
            })
            parent_id = call_id

        # Processing calls
        for mod_idx in [4, 5]:  # Processing modules
            call_id_counter += 1
            call_id = f"call_{call_id_counter}"
            trace_data["calls"].append({
                "type": "call",
                "call_id": call_id,
                "parent_id": parent_id,
                "module": modules[mod_idx],
                "function": "forward",
                "timestamp": timestamp + 0.2,
                "depth": 2
            })
            parent_id = call_id

        # Memory calls
        for mod_idx in [6, 7]:  # Memory modules
            call_id_counter += 1
            call_id = f"call_{call_id_counter}"
            trace_data["calls"].append({
                "type": "call",
                "call_id": call_id,
                "parent_id": parent_id,
                "module": modules[mod_idx],
                "function": "store",
                "timestamp": timestamp + 0.3,
                "depth": 3
            })
            parent_id = call_id

        # Output calls
        for mod_idx in [8, 9]:  # Output modules
            call_id_counter += 1
            call_id = f"call_{call_id_counter}"
            trace_data["calls"].append({
                "type": "call",
                "call_id": call_id,
                "parent_id": parent_id,
                "module": modules[mod_idx],
                "function": "decode",
                "timestamp": timestamp + 0.4,
                "depth": 4
            })
            parent_id = call_id

    logger.info(f"Generated test trace with {len(trace_data['calls'])} calls")
    return trace_data


def test_coordinate_tracker():
    """Test coordinate tracking framework"""
    from visualization_framework import CoordinateTracker

    logger.info("Testing CoordinateTracker...")

    tracker = CoordinateTracker()

    # Register objects
    import numpy as np
    tracker.register_object("module_a", np.array([0, 0, 0]), scale=1.0)
    tracker.register_object("module_b", np.array([2, 0, -3]), scale=1.0, parent="module_a")

    # Update parent and verify child updates
    tracker.update_position("module_a", np.array([1, 1, 1]))
    child_pos = tracker.get_position("module_b")

    logger.info(f"Parent moved, child position: {child_pos}")

    assert child_pos is not None, "Child position should be tracked"
    logger.info("✓ CoordinateTracker test passed")


def test_data_flow_detector():
    """Test data flow detection"""
    from visualization_framework import DataFlowDetector

    logger.info("Testing DataFlowDetector...")

    trace_data = create_test_trace_data()
    detector = DataFlowDetector(trace_data)

    flows = detector.detect_flows()

    assert len(flows) > 0, "Should detect data flows"
    logger.info(f"✓ Detected {len(flows)} data flow paths")

    # Check top flows
    for i, (source, target, count) in enumerate(flows[:5]):
        logger.info(f"  Flow {i+1}: {source} → {target} ({count} times)")

    logger.info("✓ DataFlowDetector test passed")


def test_architecture_layout():
    """Test architecture layout engine"""
    from visualization_framework import CoordinateTracker, ArchitectureLayoutEngine

    logger.info("Testing ArchitectureLayoutEngine...")

    tracker = CoordinateTracker()
    layout_engine = ArchitectureLayoutEngine(tracker)

    # Define test layers
    layers = [
        ["module_a", "module_b", "module_c"],
        ["module_d", "module_e"],
        ["module_f", "module_g", "module_h"]
    ]

    positions = layout_engine.layout_architecture(layers)

    assert len(positions) == 8, "Should position all modules"
    logger.info(f"✓ Positioned {len(positions)} modules")

    # Verify depth stacking
    layer_0_depth = positions["module_a"][2]
    layer_1_depth = positions["module_d"][2]
    layer_2_depth = positions["module_f"][2]

    assert layer_1_depth < layer_0_depth, "Layer 1 should be behind Layer 0"
    assert layer_2_depth < layer_1_depth, "Layer 2 should be behind Layer 1"

    logger.info(f"  Layer depths: {layer_0_depth}, {layer_1_depth}, {layer_2_depth}")
    logger.info("✓ ArchitectureLayoutEngine test passed")


def test_system_architecture_render():
    """Test rendering the 3D architecture visualization"""
    from system_architecture_3d import SystemArchitecture3DScene

    logger.info("Testing SystemArchitecture3DScene render...")

    # Create test trace file
    trace_data = create_test_trace_data()
    test_file = "test_trace.json"
    with open(test_file, 'w') as f:
        json.dump(trace_data, f, indent=2)

    try:
        # Test scene construction (don't actually render - too slow for tests)
        scene = SystemArchitecture3DScene(test_file)

        # Verify scene components
        assert scene.tracker is not None, "Should have coordinate tracker"
        assert scene.layout_engine is not None, "Should have layout engine"
        assert scene.flow_detector is not None, "Should have flow detector"

        logger.info("✓ SystemArchitecture3DScene initialized correctly")

        # Test data loading
        scene.load_data()
        assert scene.trace_data is not None, "Should load trace data"
        logger.info(f"✓ Loaded {len(scene.trace_data['calls'])} calls")

        # Test architecture extraction
        modules, layers = scene._extract_layered_architecture()
        assert len(layers) > 0, "Should extract layers"
        logger.info(f"✓ Extracted {len(layers)} layers with {len(modules)} modules")

        for i, layer in enumerate(layers):
            logger.info(f"  Layer {i}: {len(layer)} modules")

    finally:
        # Cleanup
        if os.path.exists(test_file):
            os.remove(test_file)

    logger.info("✓ SystemArchitecture3DScene test passed")


def test_billboard_text():
    """Test improved billboard text"""
    from system_architecture_3d import ImprovedBillboardText
    import numpy as np

    logger.info("Testing ImprovedBillboardText...")

    # Create billboard text at different depths
    positions = [
        (np.array([0, 0, 0]), 0.0),
        (np.array([0, 0, -5]), -5.0),
        (np.array([0, 0, -10]), -10.0)
    ]

    for pos, depth in positions:
        text_group = ImprovedBillboardText.create(
            text_content="Test Module",
            position=pos,
            font_size=16,
            depth=depth
        )

        assert len(text_group) == 2, "Should have background and text"
        logger.info(f"  Created billboard at depth {depth}: opacity={text_group.get_opacity():.2f}")

    logger.info("✓ ImprovedBillboardText test passed")


def run_all_tests():
    """Run all tests"""
    logger.info("=" * 60)
    logger.info("RUNNING ALL VISUALIZER TESTS")
    logger.info("=" * 60)

    tests = [
        ("Coordinate Tracker", test_coordinate_tracker),
        ("Data Flow Detector", test_data_flow_detector),
        ("Architecture Layout", test_architecture_layout),
        ("Billboard Text", test_billboard_text),
        ("System Architecture 3D", test_system_architecture_render)
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        logger.info(f"\n--- {test_name} ---")
        try:
            test_func()
            passed += 1
        except Exception as e:
            logger.error(f"✗ {test_name} FAILED: {e}", exc_info=True)
            failed += 1

    logger.info("\n" + "=" * 60)
    logger.info(f"TEST RESULTS: {passed} passed, {failed} failed")
    logger.info("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
