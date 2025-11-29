"""
Comprehensive Test Suite for Ultimate Architecture Visualization

This test suite thoroughly tests all aspects of the visualization:
1. Basic execution tests
2. Edge case handling
3. Visual quality checks
4. Performance testing
5. Integration testing

Run with: python comprehensive_test_suite.py
"""

import json
import os
import sys
import time
import traceback
import subprocess
import glob
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

# Test results tracking
@dataclass
class TestResult:
    test_name: str
    passed: bool
    duration: float
    error_message: str = ""
    notes: str = ""

class TestReport:
    def __init__(self):
        self.results: List[TestResult] = []
        self.start_time = time.time()

    def add_result(self, result: TestResult):
        self.results.append(result)
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.test_name} ({result.duration:.2f}s)")
        if not result.passed:
            print(f"      Error: {result.error_message}")
        if result.notes:
            print(f"      Notes: {result.notes}")

    def summary(self) -> str:
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed
        total_time = time.time() - self.start_time

        return f"""
========================================
TEST SUMMARY
========================================
Total Tests: {len(self.results)}
Passed: {passed}
Failed: {failed}
Total Time: {total_time:.2f}s
Success Rate: {(passed/len(self.results)*100):.1f}%
========================================
"""

# Test utilities
class TestUtilities:
    @staticmethod
    def find_trace_files(limit: int = 10) -> List[str]:
        """Find available trace files."""
        patterns = [
            ".pycharm_plugin/manim/traces/*.json",
            "traces/*.json"
        ]

        files = []
        for pattern in patterns:
            files.extend(glob.glob(pattern))

        return sorted(files)[:limit]

    @staticmethod
    def create_test_trace(filename: str, calls: List[Dict]) -> str:
        """Create a test trace file."""
        trace = {
            "correlation_id": "test_trace",
            "timestamp": time.time(),
            "calls": calls
        }

        # Use absolute path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        full_path = os.path.join(script_dir, filename)

        with open(full_path, 'w') as f:
            json.dump(trace, f, indent=2)

        return full_path

    @staticmethod
    def run_visualization(trace_file: str, timeout: int = 300) -> Tuple[bool, str, float]:
        """
        Run the visualization and return (success, output, duration).
        """
        start = time.time()
        try:
            result = subprocess.run(
                [sys.executable, "ultimate_architecture_viz.py", trace_file],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            duration = time.time() - start

            success = result.returncode == 0
            output = result.stdout + "\n" + result.stderr

            return success, output, duration

        except subprocess.TimeoutExpired:
            duration = time.time() - start
            return False, f"Timeout after {timeout}s", duration
        except Exception as e:
            duration = time.time() - start
            return False, str(e), duration

    @staticmethod
    def check_video_exists(pattern: str = "media/videos/**/ultimate_architecture*.mp4") -> bool:
        """Check if video file was created."""
        files = glob.glob(pattern, recursive=True)
        return len(files) > 0

    @staticmethod
    def get_video_size(pattern: str = "media/videos/**/ultimate_architecture*.mp4") -> int:
        """Get size of generated video in bytes."""
        files = glob.glob(pattern, recursive=True)
        if files:
            return os.path.getsize(files[0])
        return 0


# ============================================================================
# TEST SUITE
# ============================================================================

class ManimVisualizationTests:
    def __init__(self):
        self.report = TestReport()
        self.utils = TestUtilities()

    # ========================================================================
    # FUNCTIONAL TESTS
    # ========================================================================

    def test_basic_execution(self):
        """Test 1: Basic execution with real trace file."""
        test_name = "Basic Execution"
        start = time.time()

        try:
            # Find a real trace
            traces = self.utils.find_trace_files(limit=1)
            if not traces:
                self.report.add_result(TestResult(
                    test_name, False, time.time() - start,
                    "No trace files found"
                ))
                return

            # Run visualization
            success, output, duration = self.utils.run_visualization(traces[0])

            # Check video created
            video_exists = self.utils.check_video_exists()

            if success and video_exists:
                video_size = self.utils.get_video_size()
                self.report.add_result(TestResult(
                    test_name, True, duration,
                    notes=f"Video created ({video_size/1024/1024:.1f}MB)"
                ))
            else:
                self.report.add_result(TestResult(
                    test_name, False, duration,
                    f"Success={success}, Video={video_exists}\n{output[-500:]}"
                ))

        except Exception as e:
            self.report.add_result(TestResult(
                test_name, False, time.time() - start,
                f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            ))

    def test_empty_trace(self):
        """Test 2: Handle empty trace (0 calls)."""
        test_name = "Empty Trace"
        start = time.time()

        try:
            # Create empty trace
            trace_file = self.utils.create_test_trace(
                "test_empty.json",
                calls=[]
            )

            success, output, duration = self.utils.run_visualization(trace_file)

            # Should handle gracefully
            self.report.add_result(TestResult(
                test_name, success, duration,
                "" if success else f"Failed to handle empty trace\n{output[-500:]}"
            ))

            # Cleanup
            if os.path.exists(trace_file):
                os.remove(trace_file)

        except Exception as e:
            self.report.add_result(TestResult(
                test_name, False, time.time() - start,
                f"{type(e).__name__}: {str(e)}"
            ))

    def test_single_call(self):
        """Test 3: Handle single call."""
        test_name = "Single Call"
        start = time.time()

        try:
            # Create trace with single call
            trace_file = self.utils.create_test_trace(
                "test_single.json",
                calls=[{
                    "call_id": "call_1",
                    "module": "test_module",
                    "function": "test_func",
                    "depth": 0,
                    "timestamp": time.time()
                }]
            )

            success, output, duration = self.utils.run_visualization(trace_file)

            self.report.add_result(TestResult(
                test_name, success, duration,
                "" if success else f"Failed on single call\n{output[-500:]}"
            ))

            # Cleanup
            if os.path.exists(trace_file):
                os.remove(trace_file)

        except Exception as e:
            self.report.add_result(TestResult(
                test_name, False, time.time() - start,
                f"{type(e).__name__}: {str(e)}"
            ))

    def test_large_trace(self):
        """Test 4: Handle large trace (100+ calls)."""
        test_name = "Large Trace (100 calls)"
        start = time.time()

        try:
            # Create large trace
            calls = []
            for i in range(100):
                calls.append({
                    "call_id": f"call_{i}",
                    "module": f"module_{i % 5}",
                    "function": f"func_{i % 10}",
                    "depth": i % 3,
                    "timestamp": time.time() + i
                })

            trace_file = self.utils.create_test_trace("test_large.json", calls)

            success, output, duration = self.utils.run_visualization(trace_file, timeout=600)

            # Check reasonable time
            acceptable_time = duration < 600  # Should complete in 10 min

            self.report.add_result(TestResult(
                test_name, success and acceptable_time, duration,
                "" if success else f"Failed on large trace\n{output[-500:]}",
                f"Processed 100 calls in {duration:.1f}s"
            ))

            # Cleanup
            if os.path.exists(trace_file):
                os.remove(trace_file)

        except Exception as e:
            self.report.add_result(TestResult(
                test_name, False, time.time() - start,
                f"{type(e).__name__}: {str(e)}"
            ))

    def test_trace_with_errors(self):
        """Test 5: Handle trace with errors."""
        test_name = "Trace with Errors"
        start = time.time()

        try:
            # Create trace with errors
            calls = [
                {
                    "call_id": "call_1",
                    "module": "test_module",
                    "function": "test_func",
                    "depth": 0,
                    "timestamp": time.time()
                },
                {
                    "call_id": "call_2",
                    "module": "error_module",
                    "function": "error_func",
                    "depth": 1,
                    "timestamp": time.time(),
                    "error": "Test error message"
                }
            ]

            trace_file = self.utils.create_test_trace("test_errors.json", calls)

            success, output, duration = self.utils.run_visualization(trace_file)

            # Should handle errors and show phase 3
            self.report.add_result(TestResult(
                test_name, success, duration,
                "" if success else f"Failed on error trace\n{output[-500:]}",
                "Should show Phase 3: Error Analysis"
            ))

            # Cleanup
            if os.path.exists(trace_file):
                os.remove(trace_file)

        except Exception as e:
            self.report.add_result(TestResult(
                test_name, False, time.time() - start,
                f"{type(e).__name__}: {str(e)}"
            ))

    def test_malformed_json(self):
        """Test 6: Handle malformed JSON."""
        test_name = "Malformed JSON"
        start = time.time()

        try:
            # Create malformed JSON
            script_dir = os.path.dirname(os.path.abspath(__file__))
            trace_file = os.path.join(script_dir, "test_malformed.json")
            with open(trace_file, 'w') as f:
                f.write("{invalid json content")

            success, output, duration = self.utils.run_visualization(trace_file)

            # Should fail gracefully
            error_handled = "json" in output.lower() or "parse" in output.lower()

            self.report.add_result(TestResult(
                test_name, error_handled, duration,
                "" if error_handled else "Did not handle JSON error gracefully",
                "Should show clear error message"
            ))

            # Cleanup
            if os.path.exists(trace_file):
                os.remove(trace_file)

        except Exception as e:
            self.report.add_result(TestResult(
                test_name, False, time.time() - start,
                f"{type(e).__name__}: {str(e)}"
            ))

    def test_missing_fields(self):
        """Test 7: Handle trace with missing required fields."""
        test_name = "Missing Fields"
        start = time.time()

        try:
            # Create trace with missing fields
            calls = [
                {
                    "call_id": "call_1"
                    # Missing module, function, etc.
                },
                {
                    "module": "test",
                    # Missing call_id, function
                }
            ]

            trace_file = self.utils.create_test_trace("test_missing.json", calls)

            success, output, duration = self.utils.run_visualization(trace_file)

            # Should handle gracefully with defaults
            self.report.add_result(TestResult(
                test_name, success, duration,
                "" if success else f"Failed on missing fields\n{output[-500:]}",
                "Should use default values"
            ))

            # Cleanup
            if os.path.exists(trace_file):
                os.remove(trace_file)

        except Exception as e:
            self.report.add_result(TestResult(
                test_name, False, time.time() - start,
                f"{type(e).__name__}: {str(e)}"
            ))

    def test_nonexistent_file(self):
        """Test 8: Handle non-existent file."""
        test_name = "Non-existent File"
        start = time.time()

        try:
            success, output, duration = self.utils.run_visualization("nonexistent.json")

            # Should fail with clear error
            error_handled = "not found" in output.lower() or "no such file" in output.lower()

            self.report.add_result(TestResult(
                test_name, error_handled, duration,
                "" if error_handled else "Did not handle missing file gracefully",
                "Should show clear error message"
            ))

        except Exception as e:
            self.report.add_result(TestResult(
                test_name, False, time.time() - start,
                f"{type(e).__name__}: {str(e)}"
            ))

    # ========================================================================
    # VISUAL QUALITY TESTS
    # ========================================================================

    def test_video_properties(self):
        """Test 9: Check video file properties."""
        test_name = "Video Properties"
        start = time.time()

        try:
            # Find generated video
            videos = glob.glob("media/videos/**/ultimate_architecture*.mp4", recursive=True)

            if not videos:
                self.report.add_result(TestResult(
                    test_name, False, time.time() - start,
                    "No video file found"
                ))
                return

            video_path = videos[0]
            size = os.path.getsize(video_path)

            # Check file size is reasonable (> 1MB, < 100MB)
            size_ok = 1024*1024 < size < 100*1024*1024

            notes = f"Size: {size/1024/1024:.1f}MB, Path: {video_path}"

            self.report.add_result(TestResult(
                test_name, size_ok, time.time() - start,
                "" if size_ok else f"Size {size/1024/1024:.1f}MB outside acceptable range",
                notes
            ))

        except Exception as e:
            self.report.add_result(TestResult(
                test_name, False, time.time() - start,
                f"{type(e).__name__}: {str(e)}"
            ))

    # ========================================================================
    # PERFORMANCE TESTS
    # ========================================================================

    def test_rendering_performance(self):
        """Test 10: Measure rendering performance."""
        test_name = "Rendering Performance"
        start = time.time()

        try:
            # Create medium trace (50 calls)
            calls = []
            for i in range(50):
                calls.append({
                    "call_id": f"call_{i}",
                    "module": f"module_{i % 5}",
                    "function": f"func_{i % 10}",
                    "depth": i % 3,
                    "timestamp": time.time() + i
                })

            trace_file = self.utils.create_test_trace("test_perf.json", calls)

            success, output, duration = self.utils.run_visualization(trace_file, timeout=300)

            # Should complete in reasonable time (< 5 min for 50 calls)
            acceptable = duration < 300

            self.report.add_result(TestResult(
                test_name, success and acceptable, duration,
                "" if acceptable else f"Too slow: {duration:.1f}s for 50 calls",
                f"Throughput: {50/duration:.1f} calls/sec"
            ))

            # Cleanup
            if os.path.exists(trace_file):
                os.remove(trace_file)

        except Exception as e:
            self.report.add_result(TestResult(
                test_name, False, time.time() - start,
                f"{type(e).__name__}: {str(e)}"
            ))

    # ========================================================================
    # RUN ALL TESTS
    # ========================================================================

    def run_all_tests(self):
        """Run all tests in sequence."""
        print("=" * 60)
        print("MANIM VISUALIZATION TEST SUITE")
        print("=" * 60)
        print()

        # Functional tests
        print("FUNCTIONAL TESTS")
        print("-" * 60)
        self.test_basic_execution()
        self.test_empty_trace()
        self.test_single_call()
        self.test_large_trace()
        self.test_trace_with_errors()
        self.test_malformed_json()
        self.test_missing_fields()
        self.test_nonexistent_file()

        # Visual quality tests
        print()
        print("VISUAL QUALITY TESTS")
        print("-" * 60)
        self.test_video_properties()

        # Performance tests
        print()
        print("PERFORMANCE TESTS")
        print("-" * 60)
        self.test_rendering_performance()

        # Print summary
        print()
        print(self.report.summary())

        # Generate detailed report
        self.generate_detailed_report()

    def generate_detailed_report(self):
        """Generate detailed markdown report."""
        report_path = "TEST_REPORT.md"

        with open(report_path, 'w') as f:
            f.write("# Test Report: Ultimate Architecture Visualization\n\n")
            f.write(f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            # Summary
            passed = sum(1 for r in self.report.results if r.passed)
            failed = len(self.report.results) - passed
            total_time = time.time() - self.report.start_time

            f.write("## Test Summary\n\n")
            f.write(f"- **Total Tests**: {len(self.report.results)}\n")
            f.write(f"- **Passed**: {passed}\n")
            f.write(f"- **Failed**: {failed}\n")
            f.write(f"- **Success Rate**: {(passed/len(self.report.results)*100):.1f}%\n")
            f.write(f"- **Total Time**: {total_time:.2f}s\n\n")

            # Detailed results
            f.write("## Test Results\n\n")
            f.write("| Test | Status | Duration (s) | Notes |\n")
            f.write("|------|--------|--------------|-------|\n")

            for result in self.report.results:
                status = "PASS" if result.passed else "FAIL"
                notes = result.notes if result.passed else result.error_message
                notes = notes.replace('\n', ' ')[:100]  # Truncate
                f.write(f"| {result.test_name} | {status} | {result.duration:.2f} | {notes} |\n")

            # Failed tests details
            failed_tests = [r for r in self.report.results if not r.passed]
            if failed_tests:
                f.write("\n## Failed Tests Details\n\n")
                for result in failed_tests:
                    f.write(f"### {result.test_name}\n\n")
                    f.write(f"**Duration**: {result.duration:.2f}s\n\n")
                    f.write(f"**Error**:\n```\n{result.error_message}\n```\n\n")

            # Recommendations
            f.write("\n## Recommendations\n\n")
            if failed > 0:
                f.write(f"1. Fix {failed} failing test(s) immediately\n")
            if any("Too slow" in r.error_message for r in self.report.results):
                f.write("2. Optimize rendering performance for large traces\n")
            if any("gracefully" in r.error_message for r in self.report.results):
                f.write("3. Improve error handling and user messages\n")

            f.write("\n## Next Steps\n\n")
            f.write("1. Review failed tests and fix issues\n")
            f.write("2. Re-run test suite to verify fixes\n")
            f.write("3. Add visual quality inspection (manual)\n")
            f.write("4. Test plugin integration\n")

        print(f"\nDetailed report generated: {report_path}")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    tests = ManimVisualizationTests()
    tests.run_all_tests()
