#!/usr/bin/env python3
"""
TrueFlow - Comprehensive E2E Regression Test Suite
===================================================

Master test runner that validates ALL functionalities:
1. Runtime Injector (Python instrumentation)
2. Manim Visualizer (3D video generation, frame bounds)
3. Export Formats (PlantUML, JSON, Mermaid, etc.)
4. Protocol Detection (SQL, gRPC, WebSocket, etc.)
5. Plugin Integration

Usage:
    python run_regression.py                 # Run all tests
    python run_regression.py --quick         # Quick tests only (skip slow)
    python run_regression.py --manim         # Manim tests only
    python run_regression.py --injector      # Runtime injector tests only
    python run_regression.py --integration   # Integration tests only
    python run_regression.py --report        # Generate HTML report
"""

import subprocess
import sys
import os
import argparse
import time
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional

# Project paths
TRUEFLOW_ROOT = Path(__file__).parent
MANIM_VISUALIZER = TRUEFLOW_ROOT / "manim_visualizer"
RUNTIME_INJECTOR = TRUEFLOW_ROOT / "runtime_injector"
TESTS_DIR = TRUEFLOW_ROOT / "tests"
E2E_TESTS_DIR = TESTS_DIR / "e2e"


class Colors:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    """Print a styled header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(70)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}\n")


def print_section(text: str):
    """Print a section header."""
    print(f"\n{Colors.CYAN}{'-'*50}{Colors.ENDC}")
    print(f"{Colors.CYAN}{text}{Colors.ENDC}")
    print(f"{Colors.CYAN}{'-'*50}{Colors.ENDC}")

def print_result(name: str, passed: bool, duration: float, details: str = ""):
    """Print a test result."""
    status = f"{Colors.GREEN}PASSED{Colors.ENDC}" if passed else f"{Colors.FAIL}FAILED{Colors.ENDC}"
    print(f"  [{status}] {name} ({duration:.2f}s)")
    if details and not passed:
        print(f"         {Colors.WARNING}{details[:100]}{Colors.ENDC}")


def run_pytest(
    test_paths: List[str],
    markers: str = "",
    extra_args: List[str] = None,
    timeout: int = 300,
    extra_pythonpath: List[str] = None
) -> Tuple[bool, float, str]:
    """
    Run pytest on specified test paths.

    Returns:
        (passed, duration, output)
    """
    if extra_args is None:
        extra_args = []

    cmd = [
        sys.executable, "-m", "pytest",
        "-v",
        "--tb=short",
        "--no-header",
    ]

    if markers:
        cmd.extend(["-m", markers])

    cmd.extend(extra_args)
    cmd.extend(test_paths)

    start_time = time.time()

    # Set up environment with additional PYTHONPATH
    env = os.environ.copy()
    if extra_pythonpath:
        existing_path = env.get("PYTHONPATH", "")
        new_paths = os.pathsep.join(extra_pythonpath)
        env["PYTHONPATH"] = f"{new_paths}{os.pathsep}{existing_path}" if existing_path else new_paths

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(TRUEFLOW_ROOT),
            env=env
        )
        duration = time.time() - start_time
        passed = result.returncode == 0
        output = result.stdout + result.stderr

        return passed, duration, output

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return False, duration, "TIMEOUT"

    except Exception as e:
        duration = time.time() - start_time
        return False, duration, str(e)


def run_unittest(test_path: str, timeout: int = 120) -> Tuple[bool, float, str]:
    """Run unittest on specified path."""
    cmd = [sys.executable, "-m", "unittest", test_path, "-v"]

    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(TRUEFLOW_ROOT)
        )
        duration = time.time() - start_time
        passed = result.returncode == 0
        output = result.stdout + result.stderr

        return passed, duration, output

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return False, duration, "TIMEOUT"

    except Exception as e:
        duration = time.time() - start_time
        return False, duration, str(e)


class RegressionTestSuite:
    """Master regression test suite."""

    def __init__(self, args):
        self.args = args
        self.results: List[Dict] = []
        self.start_time = None
        self.end_time = None

    def run_runtime_injector_tests(self) -> bool:
        """Run runtime injector tests."""
        print_section("Runtime Injector Tests")

        test_files = [
            ("Unit Tests", str(TESTS_DIR / "test_runtime_instrumentor_unit.py")),
            ("Error Handling", str(TESTS_DIR / "test_error_handling.py")),
            ("Protocol Detection", str(TESTS_DIR / "test_protocol_detection_integration_FIXED.py")),
            ("End-to-End", str(TESTS_DIR / "test_end_to_end.py")),
        ]

        all_passed = True

        for name, test_file in test_files:
            if Path(test_file).exists():
                passed, duration, output = run_pytest([test_file])
                self.results.append({
                    "category": "Runtime Injector",
                    "name": name,
                    "passed": passed,
                    "duration": duration,
                    "file": test_file
                })
                print_result(name, passed, duration)
                if not passed:
                    all_passed = False
            else:
                print(f"  [SKIP] {name} - file not found")

        return all_passed

    def run_manim_visualizer_tests(self) -> bool:
        """Run Manim visualizer tests including frame bounds."""
        print_section("Manim Visualizer Tests")

        test_files = [
            ("Frame Bounds Validation", str(MANIM_VISUALIZER / "tests" / "test_frame_bounds_validation.py")),
            ("Animation Pacing", str(MANIM_VISUALIZER / "tests" / "test_animation_pacing.py")),
            ("Base Trace Visualizer", str(MANIM_VISUALIZER / "tests" / "test_base_trace_visualizer.py")),
            ("Visual Regression", str(MANIM_VISUALIZER / "tests" / "test_visual_regression.py")),
            ("E2E Regression", str(MANIM_VISUALIZER / "tests" / "test_e2e_regression.py")),
        ]

        all_passed = True

        # Add manim_visualizer to PYTHONPATH for proper imports
        manim_pythonpath = [str(MANIM_VISUALIZER)]

        for name, test_file in test_files:
            if Path(test_file).exists():
                # Use manim_visualizer as working directory for proper imports
                passed, duration, output = run_pytest(
                    [test_file],
                    extra_args=["--ignore=.venv"],
                    extra_pythonpath=manim_pythonpath
                )
                self.results.append({
                    "category": "Manim Visualizer",
                    "name": name,
                    "passed": passed,
                    "duration": duration,
                    "file": test_file
                })
                print_result(name, passed, duration)
                if not passed:
                    all_passed = False
            else:
                print(f"  [SKIP] {name} - file not found")

        return all_passed

    def run_manim_integration_tests(self) -> bool:
        """Run Manim integration tests (slower, actual rendering)."""
        print_section("Manim Integration Tests (Slow)")

        test_files = [
            ("Plugin Integration", str(MANIM_VISUALIZER / "test_plugin_integration.py")),
            ("Comprehensive Enhancements", str(MANIM_VISUALIZER / "test_comprehensive_enhancements.py")),
            ("New Visualizers", str(MANIM_VISUALIZER / "test_new_visualizers.py")),
        ]

        all_passed = True

        # Add manim_visualizer to PYTHONPATH for proper imports
        manim_pythonpath = [str(MANIM_VISUALIZER)]

        for name, test_file in test_files:
            if Path(test_file).exists():
                passed, duration, output = run_pytest(
                    [test_file],
                    extra_args=["--ignore=.venv"],
                    timeout=600,  # 10 min for rendering tests
                    extra_pythonpath=manim_pythonpath
                )
                self.results.append({
                    "category": "Manim Integration",
                    "name": name,
                    "passed": passed,
                    "duration": duration,
                    "file": test_file
                })
                print_result(name, passed, duration)
                if not passed:
                    all_passed = False
            else:
                print(f"  [SKIP] {name} - file not found")

        return all_passed

    def run_plugin_tests(self) -> bool:
        """Run PyCharm plugin tests."""
        print_section("PyCharm Plugin Tests")

        test_files = [
            ("Plugin Automated", str(TRUEFLOW_ROOT / "test_plugin_automated.py")),
            ("Plugin E2E", str(TRUEFLOW_ROOT / "test_plugin_e2e.py")),
        ]

        all_passed = True

        for name, test_file in test_files:
            if Path(test_file).exists():
                passed, duration, output = run_pytest([test_file])
                self.results.append({
                    "category": "PyCharm Plugin",
                    "name": name,
                    "passed": passed,
                    "duration": duration,
                    "file": test_file
                })
                print_result(name, passed, duration)
                if not passed:
                    all_passed = False
            else:
                print(f"  [SKIP] {name} - file not found")

        return all_passed

    def run_quick_tests(self) -> bool:
        """Run quick tests only (skip slow rendering tests)."""
        print_header("TrueFlow Quick Regression Tests")
        self.start_time = datetime.now()

        injector_ok = self.run_runtime_injector_tests()
        manim_ok = self.run_manim_visualizer_tests()

        self.end_time = datetime.now()
        return injector_ok and manim_ok

    def run_all_tests(self) -> bool:
        """Run all tests including slow ones."""
        print_header("TrueFlow Full Regression Test Suite")
        self.start_time = datetime.now()

        injector_ok = self.run_runtime_injector_tests()
        manim_ok = self.run_manim_visualizer_tests()

        if not self.args.quick:
            integration_ok = self.run_manim_integration_tests()
            plugin_ok = self.run_plugin_tests()
        else:
            integration_ok = True
            plugin_ok = True

        self.end_time = datetime.now()
        return injector_ok and manim_ok and integration_ok and plugin_ok

    def print_summary(self):
        """Print test summary."""
        print_header("Test Summary")

        total = len(self.results)
        passed = sum(1 for r in self.results if r["passed"])
        failed = total - passed

        duration = (self.end_time - self.start_time).total_seconds()

        # Group by category
        categories = {}
        for r in self.results:
            cat = r["category"]
            if cat not in categories:
                categories[cat] = {"passed": 0, "failed": 0}
            if r["passed"]:
                categories[cat]["passed"] += 1
            else:
                categories[cat]["failed"] += 1

        print(f"Total Tests: {total}")
        print(f"Passed: {Colors.GREEN}{passed}{Colors.ENDC}")
        print(f"Failed: {Colors.FAIL}{failed}{Colors.ENDC}")
        print(f"Duration: {duration:.2f}s")
        print()

        print("By Category:")
        for cat, counts in categories.items():
            status = f"{Colors.GREEN}OK{Colors.ENDC}" if counts["failed"] == 0 else f"{Colors.FAIL}FAIL{Colors.ENDC}"
            print(f"  {cat}: {counts['passed']}/{counts['passed'] + counts['failed']} [{status}]")

        # Show failed tests
        if failed > 0:
            print(f"\n{Colors.FAIL}Failed Tests:{Colors.ENDC}")
            for r in self.results:
                if not r["passed"]:
                    print(f"  - {r['category']}: {r['name']}")
                    print(f"    File: {r['file']}")

        # Overall status
        print()
        if failed == 0:
            print(f"{Colors.GREEN}{Colors.BOLD}ALL TESTS PASSED!{Colors.ENDC}")
            return True
        else:
            print(f"{Colors.FAIL}{Colors.BOLD}SOME TESTS FAILED!{Colors.ENDC}")
            return False

    def generate_report(self):
        """Generate HTML test report."""
        report_dir = TRUEFLOW_ROOT / "build" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)

        report_file = report_dir / f"regression_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>TrueFlow Regression Test Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        .summary {{ background: #f5f5f5; padding: 20px; border-radius: 5px; }}
        .passed {{ color: green; }}
        .failed {{ color: red; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background: #4CAF50; color: white; }}
        tr:nth-child(even) {{ background: #f2f2f2; }}
        .status-pass {{ background: #dff0d8; }}
        .status-fail {{ background: #f2dede; }}
    </style>
</head>
<body>
    <h1>TrueFlow Regression Test Report</h1>
    <div class="summary">
        <p><strong>Date:</strong> {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p><strong>Duration:</strong> {(self.end_time - self.start_time).total_seconds():.2f}s</p>
        <p><strong>Total:</strong> {len(self.results)}</p>
        <p><strong>Passed:</strong> <span class="passed">{sum(1 for r in self.results if r['passed'])}</span></p>
        <p><strong>Failed:</strong> <span class="failed">{sum(1 for r in self.results if not r['passed'])}</span></p>
    </div>

    <table>
        <tr>
            <th>Category</th>
            <th>Test Name</th>
            <th>Status</th>
            <th>Duration</th>
        </tr>
"""
        for r in self.results:
            status = "PASSED" if r["passed"] else "FAILED"
            status_class = "status-pass" if r["passed"] else "status-fail"
            html += f"""
        <tr class="{status_class}">
            <td>{r['category']}</td>
            <td>{r['name']}</td>
            <td>{status}</td>
            <td>{r['duration']:.2f}s</td>
        </tr>"""

        html += """
    </table>
</body>
</html>"""

        report_file.write_text(html)
        print(f"\nReport generated: {report_file}")


def main():
    parser = argparse.ArgumentParser(description="TrueFlow Regression Test Suite")
    parser.add_argument("--quick", action="store_true", help="Run quick tests only (skip slow)")
    parser.add_argument("--manim", action="store_true", help="Run Manim tests only")
    parser.add_argument("--injector", action="store_true", help="Run runtime injector tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    parser.add_argument("--report", action="store_true", help="Generate HTML report")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    suite = RegressionTestSuite(args)

    # Run appropriate tests
    if args.manim:
        suite.start_time = datetime.now()
        print_header("Manim Visualizer Tests")
        suite.run_manim_visualizer_tests()
        if not args.quick:
            suite.run_manim_integration_tests()
        suite.end_time = datetime.now()

    elif args.injector:
        suite.start_time = datetime.now()
        suite.run_runtime_injector_tests()
        suite.end_time = datetime.now()

    elif args.integration:
        suite.start_time = datetime.now()
        suite.run_manim_integration_tests()
        suite.run_plugin_tests()
        suite.end_time = datetime.now()

    elif args.quick:
        suite.run_quick_tests()

    else:
        suite.run_all_tests()

    # Print summary
    all_passed = suite.print_summary()

    # Generate report if requested
    if args.report:
        suite.generate_report()

    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
