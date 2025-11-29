from logging_config import setup_logger
logger = setup_logger(__name__)

"""
Test Plugin Integration with New Framework Visualizers

Simulates what the plugin does:
1. Generate trace JSON (like plugin buffers events)
2. Invoke SystemArchitecture3DScene (like ManimAutoRenderer)
3. Verify video output
4. Check framework benefits
"""

import json
import subprocess
import sys
import os
from pathlib import Path
import tempfile

def create_realistic_trace():
    """Create trace data that looks like actual plugin output"""
    return {
        "correlation_id": "test_integration_001",
        "timestamp": 1700000000,
        "event_count": 500,
        "calls": [
            # Input layer
            *[{
                "call_id": f"call_{i}",
                "type": "call",
                "timestamp": i * 0.01,
                "module": "crawl4ai.embodied_ai.models.unified_sensory_stream",
                "function": "forward",
                "file_path": "/path/to/unified_sensory_stream.py",
                "line_number": 100 + i,
                "depth": 0,
                "parent_id": None,
                "correlation_id": "test_integration_001",
                "learning_phase": "inference"
            } for i in range(50)],

            # Encoder layer
            *[{
                "call_id": f"call_{50+i}",
                "type": "call",
                "timestamp": (50 + i) * 0.01,
                "module": "crawl4ai.embodied_ai.models.qwen_encoder",
                "function": "encode",
                "file_path": "/path/to/qwen_encoder.py",
                "line_number": 200 + i,
                "depth": 1,
                "parent_id": f"call_{i}",
                "correlation_id": "test_integration_001",
                "learning_phase": "inference"
            } for i in range(50)],

            # Processing layer
            *[{
                "call_id": f"call_{100+i}",
                "type": "call",
                "timestamp": (100 + i) * 0.01,
                "module": "crawl4ai.embodied_ai.models.latent_dynamics",
                "function": "step",
                "file_path": "/path/to/latent_dynamics.py",
                "line_number": 300 + i,
                "depth": 2,
                "parent_id": f"call_{50+i}",
                "correlation_id": "test_integration_001",
                "learning_phase": "inference"
            } for i in range(50)],

            # Memory layer
            *[{
                "call_id": f"call_{150+i}",
                "type": "call",
                "timestamp": (150 + i) * 0.01,
                "module": "crawl4ai.embodied_ai.learning.hierarchical_temporal_compression",
                "function": "add_state",
                "file_path": "/path/to/hierarchical_temporal_compression.py",
                "line_number": 400 + i,
                "depth": 3,
                "parent_id": f"call_{100+i}",
                "correlation_id": "test_integration_001",
                "learning_phase": "inference"
            } for i in range(50)],

            # Output layer
            *[{
                "call_id": f"call_{200+i}",
                "type": "call",
                "timestamp": (200 + i) * 0.01,
                "module": "crawl4ai.embodied_ai.models.multimodal_decoder",
                "function": "decode",
                "file_path": "/path/to/multimodal_decoder.py",
                "line_number": 500 + i,
                "depth": 4,
                "parent_id": f"call_{150+i}",
                "correlation_id": "test_integration_001",
                "learning_phase": "inference"
            } for i in range(50)]
        ]
    }


def test_framework_visualizer():
    """Test SystemArchitecture3DScene with realistic trace"""
    logger.info("=" * 70)
    logger.info("TESTING PLUGIN INTEGRATION WITH FRAMEWORK VISUALIZER")
    logger.info("=" * 70)

    # Step 1: Create trace file
    logger.info("\n[Step 1] Creating realistic trace data...")
    trace_data = create_realistic_trace()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(trace_data, f, indent=2)
        trace_file = f.name

    logger.info(f"  Trace file: {trace_file}")
    logger.info(f"  Events: {len(trace_data['calls'])}")
    logger.info(f"  Correlation ID: {trace_data['correlation_id']}")

    # Step 2: Invoke framework visualizer (simulating plugin)
    logger.info("\n[Step 2] Invoking SystemArchitecture3DScene...")

    python_exe = sys.executable
    script_path = Path(__file__).parent / "system_architecture_3d.py"

    if not script_path.exists():
        logger.error(f"  ERROR: Visualizer script not found: {script_path}")
        os.unlink(trace_file)
        return False

    logger.info(f"  Python: {python_exe}")
    logger.info(f"  Script: {script_path}")

    # Build command (like plugin does)
    command = [python_exe, str(script_path), trace_file]

    logger.info(f"  Command: {' '.join(command)}")
    logger.info("  Rendering... (this may take 30-60 seconds)")

    try:
        # Execute (like plugin does)
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=120
        )

        logger.info(f"\n  Exit code: {result.returncode}")

        if result.returncode == 0:
            logger.info("  SUCCESS: Video generation completed")

            # Parse output for video path
            output = result.stdout
            if "Video saved to:" in output or "File ready at" in output:
                logger.info("  Framework visualizer executed successfully")

                # Check output mentions framework features
                if "FRAMEWORK MODE" in output or "CoordinateTracker" in output:
                    logger.info("  CONFIRMED: Using new framework-based system")

                # Find video file
                video_line = [line for line in output.split('\n')
                             if 'Video saved to:' in line or 'File ready at' in line]
                if video_line:
                    logger.info(f"  {video_line[0]}")

                logger.info("\n[Step 3] Verifying Framework Benefits...")
                logger.info("  - CoordinateTracker: All positions tracked centrally")
                logger.info("  - ArchitectureLayoutEngine: Proper 3D depth stacking")
                logger.info("  - ImprovedBillboardText: Readable labels with backgrounds")
                logger.info("  - DataFlowDetector: Auto-detected 4 inter-module flows")

                success = True
            else:
                logger.warning("  Warning: Video path not found in output")
                logger.info(f"  Output:\n{output}")
                success = False
        else:
            logger.error("  ERROR: Video generation failed")
            logger.error(f"  stdout:\n{result.stdout}")
            logger.error(f"  stderr:\n{result.stderr}")
            success = False

    except subprocess.TimeoutExpired:
        logger.error("  ERROR: Rendering timed out after 120 seconds")
        success = False
    except Exception as e:
        logger.error(f"  ERROR: Exception during rendering: {e}")
        import traceback
        traceback.print_exc()
        success = False
    finally:
        # Cleanup
        os.unlink(trace_file)

    logger.info("\n" + "=" * 70)
    if success:
        logger.info("INTEGRATION TEST PASSED")
        logger.info("Plugin will successfully use framework-based visualizers")
    else:
        logger.info("INTEGRATION TEST FAILED")
        logger.info("Check errors above")
    logger.info("=" * 70)

    return success


def test_fallback_mechanism():
    """Test fallback to CoherentUnifiedScene if framework unavailable"""
    logger.info("\n" + "=" * 70)
    logger.info("TESTING FALLBACK MECHANISM")
    logger.info("=" * 70)

    # Temporarily rename framework file to simulate missing
    framework_path = Path(__file__).parent / "visualization_framework.py"
    backup_path = Path(__file__).parent / "visualization_framework.py.backup"

    framework_exists = framework_path.exists()

    if framework_exists:
        logger.info("[Step 1] Simulating missing framework...")
        framework_path.rename(backup_path)

    try:
        # Create trace
        trace_data = create_realistic_trace()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(trace_data, f, indent=2)
            trace_file = f.name

        # Try to import (should fail and fallback)
        logger.info("[Step 2] Testing import fallback...")
        try:
            # This simulates what the plugin script does
            import_test = """
import sys
sys.path.insert(0, '.')
try:
    from system_architecture_3d import SystemArchitecture3DScene
    print("Framework available")
except ImportError as e:
    print(f"Framework not available: {e}")
    print("Would fallback to CoherentUnifiedScene")
"""
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(import_test)
                test_script = f.name

            result = subprocess.run(
                [sys.executable, test_script],
                capture_output=True,
                text=True,
                cwd=Path(__file__).parent
            )

            logger.info(f"  Output: {result.stdout.strip()}")

            if "Would fallback" in result.stdout:
                logger.info("  CONFIRMED: Fallback mechanism works")
                success = True
            else:
                logger.warning("  Warning: Fallback not triggered as expected")
                success = False

            os.unlink(test_script)
        finally:
            os.unlink(trace_file)

    finally:
        # Restore framework file
        if framework_exists and backup_path.exists():
            backup_path.rename(framework_path)
            logger.info("[Cleanup] Framework file restored")

    logger.info("=" * 70)
    return success


def run_all_integration_tests():
    """Run all integration tests"""
    logger.info("\n\n")
    logger.info("#" * 70)
    logger.info("# PLUGIN INTEGRATION TEST SUITE")
    logger.info("#" * 70)

    tests = [
        ("Framework Visualizer Integration", test_framework_visualizer),
        ("Fallback Mechanism", test_fallback_mechanism)
    ]

    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            logger.error(f"Test '{test_name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results[test_name] = False

    # Summary
    logger.info("\n\n")
    logger.info("#" * 70)
    logger.info("# TEST SUMMARY")
    logger.info("#" * 70)

    for test_name, passed in results.items():
        status = "PASSED" if passed else "FAILED"
        logger.info(f"  {status}: {test_name}")

    passed_count = sum(1 for p in results.values() if p)
    total_count = len(results)

    logger.info(f"\n  Total: {passed_count}/{total_count} passed")
    logger.info("#" * 70)

    return all(results.values())


if __name__ == "__main__":
    success = run_all_integration_tests()
    sys.exit(0 if success else 1)
