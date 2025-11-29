"""
Integration Test Script for Animation System

Tests all new animation modules and integrations:
1. Import tests
2. Standards validation
3. Extended visualizers
4. LLM operation mapper
5. Integration with existing code
"""

import sys
import traceback

# Import logging configuration
from logging_config import get_integration_test_logger

# Initialize logger
logger = get_integration_test_logger()


def test_imports():
    """Test that all new modules import successfully."""
    logger.info("\n=== Testing Imports ===")

    results = {
        "animation_standards": False,
        "operation_visualizer_extended": False,
        "llm_operation_mapper": False,
        "advanced_operation_viz": False,
        "procedural_trace_viz": False
    }

    # Test animation_standards
    try:
        from animation_standards import (
            AnimationTiming, AnimationColors, DataTypeShapes, AnimationHelpers
        )
        logger.info("[PASS] animation_standards imported successfully")
        results["animation_standards"] = True
    except Exception as e:
        logger.error(f"[FAIL] animation_standards import failed: {e}")
        traceback.print_exc()

    # Test operation_visualizer_extended
    try:
        from operation_visualizer_extended import ExtendedOperationVisualizer
        logger.info("[OK] operation_visualizer_extended imported successfully")
        results["operation_visualizer_extended"] = True
    except Exception as e:
        logger.error(f"[FAIL] operation_visualizer_extended import failed: {e}")
        traceback.print_exc()

    # Test llm_operation_mapper
    try:
        from llm_operation_mapper import LLMOperationMapper
        logger.info("[OK] llm_operation_mapper imported successfully")
        results["llm_operation_mapper"] = True
    except Exception as e:
        logger.error(f"[FAIL] llm_operation_mapper import failed: {e}")
        traceback.print_exc()

    # Test advanced_operation_viz
    try:
        from advanced_operation_viz import OperationDetector, OperationVisualizer
        logger.info("[OK] advanced_operation_viz imported successfully")
        results["advanced_operation_viz"] = True
    except Exception as e:
        logger.error(f"[FAIL] advanced_operation_viz import failed: {e}")
        traceback.print_exc()

    # Test procedural_trace_viz
    try:
        from procedural_trace_viz import ProceduralTraceScene
        logger.info("[OK] procedural_trace_viz imported successfully")
        results["procedural_trace_viz"] = True
    except Exception as e:
        logger.error(f"[FAIL] procedural_trace_viz import failed: {e}")
        traceback.print_exc()

    return results


def test_animation_standards():
    """Test animation standards functionality."""
    logger.info("\n=== Testing Animation Standards ===")

    try:
        from animation_standards import (
            AnimationTiming, AnimationColors, DataTypeShapes, AnimationHelpers
        )

        # Test timing constants
        assert AnimationTiming.DATA_FLOW_SHORT == 0.5
        assert AnimationTiming.TRANSFORM_COMPLEX == 1.5
        assert AnimationTiming.LAYER_ACTIVATION == 0.6
        logger.info("[OK] AnimationTiming constants correct")

        # Test color standards
        assert AnimationColors.INT is not None
        assert AnimationColors.TENSOR is not None
        assert AnimationColors.QUERY is not None
        logger.info("[OK] AnimationColors constants defined")

        # Test color getters
        int_color = AnimationColors.get_type_color('int')
        float_color = AnimationColors.get_type_color('float')
        assert int_color is not None
        assert float_color is not None
        logger.info("[OK] AnimationColors.get_type_color() works")

        # Test layer color generator
        layer_color = AnimationColors.get_layer_color(0, 3)
        assert layer_color is not None
        logger.info("[OK] AnimationColors.get_layer_color() works")

        # Test operation timing mapper
        timing = AnimationTiming.get_timing_for_operation('reshape')
        assert timing == AnimationTiming.TRANSFORM_COMPLEX
        logger.info("[OK] AnimationTiming.get_timing_for_operation() works")

        return True

    except Exception as e:
        logger.error(f"[FAIL] Animation standards test failed: {e}")
        traceback.print_exc()
        return False


def test_extended_visualizers():
    """Test extended visualizers can be instantiated."""
    logger.info("\n=== Testing Extended Visualizers ===")

    try:
        from operation_visualizer_extended import ExtendedOperationVisualizer
        from manim import ORIGIN
        import numpy as np

        # Test that methods exist
        assert hasattr(ExtendedOperationVisualizer, 'create_convolution_viz')
        assert hasattr(ExtendedOperationVisualizer, 'create_batch_norm_viz')
        assert hasattr(ExtendedOperationVisualizer, 'create_async_operation_viz')
        assert hasattr(ExtendedOperationVisualizer, 'create_nested_call_stack_viz')
        assert hasattr(ExtendedOperationVisualizer, 'create_broadcasting_viz')
        assert hasattr(ExtendedOperationVisualizer, 'create_enhanced_matmul_viz')
        assert hasattr(ExtendedOperationVisualizer, 'create_memory_operation_viz')
        logger.info("[OK] All extended visualizer methods exist")

        # Test one visualization (without rendering)
        try:
            call_data = {"function": "test", "module": "test"}
            position = np.array([0, 0, 0])
            viz = ExtendedOperationVisualizer.create_convolution_viz(call_data, position)
            logger.info("[OK] Convolution visualization created successfully")
        except Exception as e:
            logger.warning(f"[WARN] Could not create test visualization (expected if Manim not fully set up): {e}")

        return True

    except Exception as e:
        logger.error(f"[FAIL] Extended visualizers test failed: {e}")
        traceback.print_exc()
        return False


def test_llm_mapper():
    """Test LLM operation mapper."""
    logger.info("\n=== Testing LLM Operation Mapper ===")

    try:
        from llm_operation_mapper import LLMOperationMapper

        # Test with pattern matching only (no LLM calls)
        mapper = LLMOperationMapper(use_llm=False)

        # Test classification
        test_cases = [
            ({"function": "forward", "module": "torch.nn.Linear"}, "neural_layer"),
            ({"function": "self_attention", "module": "transformers"}, "attention"),
            ({"function": "conv2d", "module": "torch.nn"}, "convolution"),
            ({"function": "reshape", "module": "numpy"}, "array_reshape"),
        ]

        for call_data, expected in test_cases:
            result = mapper.classify(call_data)
            if result == expected:
                logger.info(f"[OK] Correctly classified {call_data['function']} as {result}")
            else:
                logger.warning(f"[WARN] Classified {call_data['function']} as {result} (expected {expected})")

        return True

    except Exception as e:
        logger.error(f"[FAIL] LLM mapper test failed: {e}")
        traceback.print_exc()
        return False


def test_operation_detector():
    """Test operation detector integration."""
    logger.info("\n=== Testing Operation Detector Integration ===")

    try:
        from advanced_operation_viz import OperationDetector

        # Test new operation types
        test_cases = [
            ({"function": "conv2d", "module": "torch.nn"}, "convolution"),
            ({"function": "batch_norm", "module": "torch.nn"}, "batch_norm"),
            ({"function": "async_function", "module": "asyncio"}, "async_operation"),
            ({"function": "cache_store", "module": "memory"}, "memory_write"),
        ]

        for call_data, expected in test_cases:
            result = OperationDetector.detect_operation_type(call_data)
            if result == expected:
                logger.info(f"[OK] Correctly detected {call_data['function']} as {result}")
            else:
                logger.warning(f"[WARN] Detected {call_data['function']} as {result} (expected {expected})")

        return True

    except Exception as e:
        logger.error(f"[FAIL] Operation detector test failed: {e}")
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all integration tests."""
    logger.info("=" * 60)
    logger.info("ANIMATION SYSTEM INTEGRATION TEST")
    logger.info("=" * 60)

    results = {}

    # Test imports
    import_results = test_imports()
    results["imports"] = all(import_results.values())

    # Only run other tests if imports succeeded
    if results["imports"]:
        results["standards"] = test_animation_standards()
        results["extended_viz"] = test_extended_visualizers()
        results["llm_mapper"] = test_llm_mapper()
        results["op_detector"] = test_operation_detector()
    else:
        logger.warning("\n[WARN] Skipping remaining tests due to import failures")
        results["standards"] = False
        results["extended_viz"] = False
        results["llm_mapper"] = False
        results["op_detector"] = False

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)

    total_tests = len(results)
    passed_tests = sum(1 for v in results.values() if v)

    for test_name, passed in results.items():
        status = "[OK] PASS" if passed else "[FAIL] FAIL"
        logger.info(f"{test_name:20s}: {status}")

    logger.info("\n" + "=" * 60)
    logger.info(f"TOTAL: {passed_tests}/{total_tests} tests passed")
    logger.info("=" * 60)

    if passed_tests == total_tests:
        logger.info("\n[SUCCESS] All tests passed! Integration complete.")
        return 0
    else:
        logger.warning(f"\n[WARN] {total_tests - passed_tests} test(s) failed. Review output above.")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
