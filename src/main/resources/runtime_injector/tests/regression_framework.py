"""
Autonomous Post-Build Regression Test Framework

This framework creates and executes comprehensive regression tests after each build.
It uses autonomous agents to:
1. Generate test scenarios
2. Render videos
3. Validate output quality
4. Check for visual regressions
5. Report results

Architecture:
- Test Generator Agent: Creates test scenarios from trace files
- Execution Agent: Renders videos and captures metrics
- Validation Agent: Checks visual quality and frame bounds
- Reporter Agent: Aggregates results and creates reports

Usage:
    python regression_framework.py --mode generate  # Generate test pack
    python regression_framework.py --mode execute   # Run all tests
    python regression_framework.py --mode validate  # Validate outputs
    python regression_framework.py --mode full      # Full autonomous run
"""

from logging_config import setup_logger
logger = setup_logger(__name__)

import json
import sys
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
import concurrent.futures
from enum import Enum


class TestStatus(Enum):
    """Test execution status."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class RegressionTest:
    """Single regression test case."""
    test_id: str
    test_name: str
    visualizer_script: str
    trace_file: str
    expected_duration_min: float
    expected_duration_max: float
    expected_frame_count_min: int
    expected_frame_count_max: int
    max_execution_time: float = 120.0  # 2 minutes max
    check_frame_bounds: bool = True
    check_text_readable: bool = True
    status: TestStatus = TestStatus.PENDING
    error_message: Optional[str] = None
    execution_time: Optional[float] = None
    video_path: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result['status'] = self.status.value
        return result

    @classmethod
    def from_dict(cls, data: Dict) -> 'RegressionTest':
        """Create from dictionary."""
        data['status'] = TestStatus(data['status'])
        return cls(**data)


@dataclass
class RegressionTestPack:
    """Collection of regression tests."""
    pack_id: str
    pack_name: str
    created_at: str
    tests: List[RegressionTest] = field(default_factory=list)

    def add_test(self, test: RegressionTest):
        """Add test to pack."""
        self.tests.append(test)

    def get_test(self, test_id: str) -> Optional[RegressionTest]:
        """Get test by ID."""
        for test in self.tests:
            if test.test_id == test_id:
                return test
        return None

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'pack_id': self.pack_id,
            'pack_name': self.pack_name,
            'created_at': self.created_at,
            'tests': [test.to_dict() for test in self.tests]
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'RegressionTestPack':
        """Create from dictionary."""
        tests = [RegressionTest.from_dict(t) for t in data['tests']]
        return cls(
            pack_id=data['pack_id'],
            pack_name=data['pack_name'],
            created_at=data['created_at'],
            tests=tests
        )

    def save(self, output_dir: Path):
        """Save test pack to JSON file."""
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"regression_pack_{self.pack_id}.json"

        with open(output_file, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

        logger.info(f"Saved test pack to {output_file}")
        return output_file

    @classmethod
    def load(cls, pack_file: Path) -> 'RegressionTestPack':
        """Load test pack from JSON file."""
        with open(pack_file, 'r') as f:
            data = json.load(f)

        return cls.from_dict(data)


class TestGeneratorAgent:
    """
    Autonomous agent that generates regression test scenarios.

    Scans for:
    - All visualizer scripts
    - Available trace files
    - Expected outputs
    """

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.visualizer_dir = base_dir
        self.trace_dir = base_dir.parent.parent / ".pycharm_plugin" / "manim" / "traces"

    def discover_visualizers(self) -> List[Path]:
        """Find all visualizer scripts."""
        visualizers = []

        # Find Python files ending with _viz.py or visualizer.py
        for pattern in ["*_viz.py", "*visualizer*.py"]:
            visualizers.extend(self.visualizer_dir.glob(pattern))

        logger.info(f"Discovered {len(visualizers)} visualizer scripts")
        return visualizers

    def discover_trace_files(self, limit: int = 5) -> List[Path]:
        """Find available trace files."""
        if not self.trace_dir.exists():
            logger.warning(f"Trace directory not found: {self.trace_dir}")
            return []

        traces = list(self.trace_dir.glob("trace_*.json"))[:limit]
        logger.info(f"Discovered {len(traces)} trace files")
        return traces

    def generate_test(
        self,
        visualizer: Path,
        trace: Path,
        test_id: str
    ) -> RegressionTest:
        """Generate a single regression test."""

        # Determine expected values based on visualizer type
        if "minimal" in visualizer.name.lower():
            expected_duration = (10, 20)  # 10-20 seconds
            expected_frames = (300, 600)  # At 30fps
        elif "ultimate" in visualizer.name.lower():
            expected_duration = (40, 60)  # 40-60 seconds
            expected_frames = (1200, 1800)
        else:
            expected_duration = (15, 45)  # Generic
            expected_frames = (450, 1350)

        return RegressionTest(
            test_id=test_id,
            test_name=f"{visualizer.stem}_{trace.stem}",
            visualizer_script=str(visualizer),
            trace_file=str(trace),
            expected_duration_min=expected_duration[0],
            expected_duration_max=expected_duration[1],
            expected_frame_count_min=expected_frames[0],
            expected_frame_count_max=expected_frames[1]
        )

    def generate_test_pack(self, pack_name: str = "post_build") -> RegressionTestPack:
        """Generate complete test pack."""
        pack_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        pack = RegressionTestPack(
            pack_id=pack_id,
            pack_name=pack_name,
            created_at=datetime.now().isoformat()
        )

        visualizers = self.discover_visualizers()
        traces = self.discover_trace_files()

        if not visualizers:
            logger.warning("No visualizers found")
            return pack

        if not traces:
            logger.warning("No trace files found, creating synthetic trace")
            traces = [self.create_synthetic_trace()]

        # Generate tests for each visualizer-trace combination
        test_counter = 0
        for visualizer in visualizers:
            for trace in traces:
                test_id = f"test_{pack_id}_{test_counter:03d}"
                test = self.generate_test(visualizer, trace, test_id)
                pack.add_test(test)
                test_counter += 1

        logger.info(f"Generated {len(pack.tests)} regression tests")
        return pack

    def create_synthetic_trace(self) -> Path:
        """Create a small synthetic trace file for testing."""
        trace_data = {
            "correlation_id": "synthetic_test",
            "calls": [
                {
                    "type": "call",
                    "call_id": f"call_{i}",
                    "module": f"test.module{i % 3}",
                    "function": f"func{i}",
                    "file": "/test.py",
                    "line": 10 + i,
                    "depth": 0
                }
                for i in range(5)
            ],
            "errors": []
        }

        temp_dir = Path(tempfile.gettempdir()) / "manim_regression"
        temp_dir.mkdir(exist_ok=True)

        trace_file = temp_dir / "synthetic_trace.json"
        with open(trace_file, 'w') as f:
            json.dump(trace_data, f)

        logger.info(f"Created synthetic trace: {trace_file}")
        return trace_file


class ExecutionAgent:
    """
    Autonomous agent that executes regression tests.

    Runs visualizers and captures:
    - Execution time
    - Video output
    - Errors and warnings
    """

    def __init__(self, python_path: str = sys.executable):
        self.python_path = python_path

    def execute_test(self, test: RegressionTest) -> RegressionTest:
        """Execute a single regression test."""
        logger.info(f"Executing test: {test.test_id} - {test.test_name}")

        test.status = TestStatus.RUNNING
        start_time = datetime.now()

        try:
            # Run visualizer script
            result = subprocess.run(
                [self.python_path, test.visualizer_script, test.trace_file],
                capture_output=True,
                text=True,
                timeout=test.max_execution_time
            )

            execution_time = (datetime.now() - start_time).total_seconds()
            test.execution_time = execution_time

            # Check for errors
            if result.returncode != 0:
                test.status = TestStatus.FAILED
                test.error_message = f"Process failed with code {result.returncode}: {result.stderr[:500]}"
                logger.error(f"Test {test.test_id} failed: {test.error_message}")
                return test

            # Look for video output
            media_dir = Path(test.visualizer_script).parent / "media" / "videos"
            if media_dir.exists():
                videos = list(media_dir.rglob("*.mp4"))
                if videos:
                    test.video_path = str(videos[-1])  # Most recent
                    logger.info(f"Video output: {test.video_path}")

            test.status = TestStatus.PASSED
            logger.info(f"Test {test.test_id} passed in {execution_time:.2f}s")

        except subprocess.TimeoutExpired:
            test.status = TestStatus.FAILED
            test.error_message = f"Timeout after {test.max_execution_time}s"
            logger.error(f"Test {test.test_id} timed out")

        except Exception as e:
            test.status = TestStatus.FAILED
            test.error_message = str(e)[:500]
            logger.error(f"Test {test.test_id} failed: {e}", exc_info=True)

        return test

    def execute_pack(
        self,
        pack: RegressionTestPack,
        max_workers: int = 4
    ) -> RegressionTestPack:
        """Execute all tests in pack (parallel execution)."""
        logger.info(f"Executing test pack: {pack.pack_name} ({len(pack.tests)} tests)")

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tests
            future_to_test = {
                executor.submit(self.execute_test, test): test
                for test in pack.tests
            }

            # Collect results
            for future in concurrent.futures.as_completed(future_to_test):
                test = future_to_test[future]
                try:
                    updated_test = future.result()
                    # Update test in pack
                    pack_test = pack.get_test(updated_test.test_id)
                    if pack_test:
                        pack_test.status = updated_test.status
                        pack_test.error_message = updated_test.error_message
                        pack_test.execution_time = updated_test.execution_time
                        pack_test.video_path = updated_test.video_path
                except Exception as e:
                    logger.error(f"Future failed for test {test.test_id}: {e}")

        return pack


class ValidationAgent:
    """
    Autonomous agent that validates test outputs.

    Checks:
    - Video duration within expected range
    - Frame count within expected range
    - Elements within frame bounds (if video exists)
    - Text readability
    """

    def validate_test(self, test: RegressionTest) -> RegressionTest:
        """Validate a completed test."""
        if test.status != TestStatus.PASSED:
            logger.info(f"Skipping validation for failed test: {test.test_id}")
            return test

        logger.info(f"Validating test: {test.test_id}")

        # Check execution time
        if test.execution_time:
            if not (test.expected_duration_min <= test.execution_time <= test.expected_duration_max):
                test.status = TestStatus.FAILED
                test.error_message = (
                    f"Duration {test.execution_time:.1f}s outside expected range "
                    f"[{test.expected_duration_min}, {test.expected_duration_max}]"
                )
                logger.warning(f"Test {test.test_id}: {test.error_message}")
                return test

        # Check video output exists
        if not test.video_path or not Path(test.video_path).exists():
            test.status = TestStatus.FAILED
            test.error_message = "No video output found"
            logger.warning(f"Test {test.test_id}: {test.error_message}")
            return test

        # TODO: Add ffprobe checks for frame count, resolution
        # TODO: Add frame-by-frame analysis for bounds checking

        logger.info(f"Test {test.test_id} validation passed")
        return test

    def validate_pack(self, pack: RegressionTestPack) -> RegressionTestPack:
        """Validate all tests in pack."""
        logger.info(f"Validating test pack: {pack.pack_name}")

        for test in pack.tests:
            self.validate_test(test)

        return pack


class ReporterAgent:
    """
    Autonomous agent that generates test reports.

    Creates:
    - Summary statistics
    - Detailed test results
    - HTML report (optional)
    """

    def generate_summary(self, pack: RegressionTestPack) -> Dict[str, Any]:
        """Generate summary statistics."""
        total = len(pack.tests)
        passed = sum(1 for t in pack.tests if t.status == TestStatus.PASSED)
        failed = sum(1 for t in pack.tests if t.status == TestStatus.FAILED)
        skipped = sum(1 for t in pack.tests if t.status == TestStatus.SKIPPED)

        total_time = sum(t.execution_time for t in pack.tests if t.execution_time)

        return {
            'pack_id': pack.pack_id,
            'pack_name': pack.pack_name,
            'total_tests': total,
            'passed': passed,
            'failed': failed,
            'skipped': skipped,
            'pass_rate': (passed / total * 100) if total > 0 else 0,
            'total_execution_time': total_time,
            'created_at': pack.created_at
        }

    def generate_report(
        self,
        pack: RegressionTestPack,
        output_dir: Path
    ) -> Path:
        """Generate detailed report."""
        output_dir.mkdir(parents=True, exist_ok=True)
        report_file = output_dir / f"regression_report_{pack.pack_id}.md"

        summary = self.generate_summary(pack)

        with open(report_file, 'w') as f:
            f.write(f"# Regression Test Report\n\n")
            f.write(f"**Pack**: {pack.pack_name}\n")
            f.write(f"**ID**: {pack.pack_id}\n")
            f.write(f"**Created**: {pack.created_at}\n\n")

            f.write(f"## Summary\n\n")
            f.write(f"| Metric | Value |\n")
            f.write(f"|--------|-------|\n")
            f.write(f"| Total Tests | {summary['total_tests']} |\n")
            f.write(f"| Passed | {summary['passed']} |\n")
            f.write(f"| Failed | {summary['failed']} |\n")
            f.write(f"| Skipped | {summary['skipped']} |\n")
            f.write(f"| Pass Rate | {summary['pass_rate']:.1f}% |\n")
            f.write(f"| Total Time | {summary['total_execution_time']:.1f}s |\n\n")

            f.write(f"## Test Results\n\n")

            for test in pack.tests:
                status_emoji = {
                    TestStatus.PASSED: "✅",
                    TestStatus.FAILED: "❌",
                    TestStatus.SKIPPED: "⏭️",
                    TestStatus.PENDING: "⏳",
                    TestStatus.RUNNING: "🔄"
                }.get(test.status, "❓")

                f.write(f"### {status_emoji} {test.test_name}\n\n")
                f.write(f"- **ID**: {test.test_id}\n")
                f.write(f"- **Status**: {test.status.value}\n")
                f.write(f"- **Visualizer**: {Path(test.visualizer_script).name}\n")
                f.write(f"- **Trace**: {Path(test.trace_file).name}\n")

                if test.execution_time:
                    f.write(f"- **Execution Time**: {test.execution_time:.2f}s\n")

                if test.video_path:
                    f.write(f"- **Video**: {test.video_path}\n")

                if test.error_message:
                    f.write(f"- **Error**: {test.error_message}\n")

                f.write(f"\n")

        logger.info(f"Generated report: {report_file}")
        return report_file


class RegressionFramework:
    """
    Main autonomous regression test framework.

    Orchestrates all agents to:
    1. Generate test pack
    2. Execute tests
    3. Validate results
    4. Generate reports
    """

    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            base_dir = Path(__file__).parent.parent

        self.base_dir = base_dir
        self.test_dir = base_dir / "tests"
        self.output_dir = base_dir / "regression_output"

        self.generator = TestGeneratorAgent(base_dir)
        self.executor = ExecutionAgent()
        self.validator = ValidationAgent()
        self.reporter = ReporterAgent()

    def generate_pack(self, pack_name: str = "post_build") -> RegressionTestPack:
        """Generate test pack."""
        logger.info("=== Generating test pack ===")
        pack = self.generator.generate_test_pack(pack_name)
        pack.save(self.output_dir)
        return pack

    def execute_pack(self, pack: RegressionTestPack) -> RegressionTestPack:
        """Execute test pack."""
        logger.info("=== Executing test pack ===")
        pack = self.executor.execute_pack(pack)
        pack.save(self.output_dir)
        return pack

    def validate_pack(self, pack: RegressionTestPack) -> RegressionTestPack:
        """Validate test pack."""
        logger.info("=== Validating test pack ===")
        pack = self.validator.validate_pack(pack)
        pack.save(self.output_dir)
        return pack

    def generate_report(self, pack: RegressionTestPack) -> Path:
        """Generate test report."""
        logger.info("=== Generating report ===")
        return self.reporter.generate_report(pack, self.output_dir)

    def run_full(self, pack_name: str = "post_build") -> Tuple[RegressionTestPack, Path]:
        """Run full autonomous regression test cycle."""
        logger.info("=== Starting full autonomous regression test cycle ===")

        # Generate
        pack = self.generate_pack(pack_name)
        logger.info(f"Generated {len(pack.tests)} tests")

        # Execute
        pack = self.execute_pack(pack)

        # Validate
        pack = self.validate_pack(pack)

        # Report
        report = self.generate_report(pack)

        # Summary
        summary = self.reporter.generate_summary(pack)
        logger.info(f"=== Regression test complete ===")
        logger.info(f"Pass rate: {summary['pass_rate']:.1f}% ({summary['passed']}/{summary['total_tests']})")
        logger.info(f"Report: {report}")

        return pack, report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Autonomous Regression Test Framework")
    parser.add_argument(
        '--mode',
        choices=['generate', 'execute', 'validate', 'full'],
        default='full',
        help='Operation mode'
    )
    parser.add_argument(
        '--pack-file',
        type=str,
        help='Path to existing test pack (for execute/validate modes)'
    )
    parser.add_argument(
        '--pack-name',
        type=str,
        default='post_build',
        help='Name for new test pack'
    )

    args = parser.parse_args()

    framework = RegressionFramework()

    if args.mode == 'generate':
        pack = framework.generate_pack(args.pack_name)
        print(f"Generated {len(pack.tests)} tests")
        print(f"Pack saved to: {framework.output_dir}")

    elif args.mode == 'execute':
        if not args.pack_file:
            print("Error: --pack-file required for execute mode")
            sys.exit(1)

        pack = RegressionTestPack.load(Path(args.pack_file))
        pack = framework.execute_pack(pack)
        print(f"Executed {len(pack.tests)} tests")

    elif args.mode == 'validate':
        if not args.pack_file:
            print("Error: --pack-file required for validate mode")
            sys.exit(1)

        pack = RegressionTestPack.load(Path(args.pack_file))
        pack = framework.validate_pack(pack)
        report = framework.generate_report(pack)
        print(f"Report: {report}")

    elif args.mode == 'full':
        pack, report = framework.run_full(args.pack_name)
        print(f"\nFull regression test complete!")
        print(f"Report: {report}")
