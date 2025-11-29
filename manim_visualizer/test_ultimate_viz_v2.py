"""
Test Script for Ultimate Architecture Visualization V2

Tests the perfect implementation with various trace files.
"""

import os
import sys
import glob
import subprocess
from pathlib import Path
from typing import List, Optional


def find_trace_files(base_path: str = ".pycharm_plugin/manim/traces") -> List[Path]:
    """
    Find all trace JSON files.

    Args:
        base_path: Base directory to search

    Returns:
        List of trace file paths
    """
    # Try absolute path first
    project_root = Path(__file__).parent.parent.parent
    trace_dir = project_root / base_path

    if not trace_dir.exists():
        # Try relative path
        trace_dir = Path(base_path)

    if not trace_dir.exists():
        print(f"ERROR: Trace directory not found: {trace_dir}")
        return []

    # Find all JSON files
    trace_files = list(trace_dir.glob("trace_*.json"))
    trace_files.sort()

    print(f"Found {len(trace_files)} trace files in {trace_dir}")
    return trace_files


def test_with_trace(trace_file: Path, output_name: Optional[str] = None) -> bool:
    """
    Test visualization with a specific trace file.

    Args:
        trace_file: Path to trace file
        output_name: Optional output filename

    Returns:
        True if successful, False otherwise
    """
    print(f"\n{'='*70}")
    print(f"Testing with: {trace_file.name}")
    print(f"{'='*70}")

    # Get script path
    script_path = Path(__file__).parent / "ultimate_architecture_viz_v2.py"

    if not script_path.exists():
        print(f"ERROR: Script not found: {script_path}")
        return False

    # Build command
    cmd = [
        sys.executable,
        str(script_path),
        str(trace_file)
    ]

    # Set output name if provided
    if output_name:
        os.environ['MANIM_OUTPUT_FILE'] = output_name

    # Run visualization
    try:
        print("\nRunning visualization...")
        print(f"Command: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        # Print output
        if result.stdout:
            print("\n--- STDOUT ---")
            print(result.stdout)

        if result.stderr:
            print("\n--- STDERR ---")
            print(result.stderr)

        # Check result
        if result.returncode == 0:
            print("\n[OK] SUCCESS: Video generated")
            return True
        else:
            print(f"\n[X] FAILED: Exit code {result.returncode}")
            return False

    except subprocess.TimeoutExpired:
        print("\n[X] FAILED: Timeout (>5 minutes)")
        return False

    except Exception as e:
        print(f"\n[X] FAILED: {e}")
        return False


def test_all_traces(max_tests: int = 3):
    """
    Test with multiple trace files.

    Args:
        max_tests: Maximum number of traces to test
    """
    print("="*70)
    print("ULTIMATE ARCHITECTURE VISUALIZATION V2 - TEST SUITE")
    print("="*70)

    # Find trace files
    trace_files = find_trace_files()

    if not trace_files:
        print("\nNo trace files found. Please ensure traces exist.")
        return

    # Test with up to max_tests files
    test_files = trace_files[:max_tests]
    results = []

    for i, trace_file in enumerate(test_files, 1):
        output_name = f"test_output_{i}"
        success = test_with_trace(trace_file, output_name)
        results.append((trace_file.name, success))

    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    for filename, success in results:
        status = "[OK] PASS" if success else "[X] FAIL"
        print(f"{status}: {filename}")

    # Overall result
    passed = sum(1 for _, success in results if success)
    total = len(results)

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("\n[SUCCESS] All tests passed!")
    else:
        print(f"\n[WARNING] {total - passed} test(s) failed")


def test_specific_trace(trace_pattern: str):
    """
    Test with a specific trace file matching a pattern.

    Args:
        trace_pattern: Pattern to match (e.g., "cycle_000003")
    """
    trace_files = find_trace_files()

    matching = [f for f in trace_files if trace_pattern in f.name]

    if not matching:
        print(f"No trace files matching pattern: {trace_pattern}")
        return

    if len(matching) > 1:
        print(f"Found {len(matching)} matching files:")
        for i, f in enumerate(matching, 1):
            print(f"  {i}. {f.name}")
        print(f"\nUsing first match: {matching[0].name}")

    test_with_trace(matching[0])


def test_validation_only():
    """Test validation without rendering."""
    print("="*70)
    print("VALIDATION TEST (No Rendering)")
    print("="*70)

    trace_files = find_trace_files()

    if not trace_files:
        print("No trace files found")
        return

    # Test first file
    trace_file = trace_files[0]
    print(f"\nValidating: {trace_file.name}")

    try:
        import json

        with open(trace_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Validate structure
        errors = []

        if not isinstance(data, dict):
            errors.append("Not a dictionary")

        if 'calls' not in data:
            errors.append("Missing 'calls' field")
        elif not isinstance(data['calls'], list):
            errors.append("'calls' is not a list")

        if errors:
            print("[X] VALIDATION FAILED:")
            for error in errors:
                print(f"  - {error}")
        else:
            print("[OK] VALIDATION PASSED")
            print(f"  - Event count: {len(data.get('calls', []))}")
            print(f"  - Correlation ID: {data.get('correlation_id', 'N/A')}")

            # Count call types
            call_types = {}
            for call in data.get('calls', []):
                call_type = call.get('type', 'unknown')
                call_types[call_type] = call_types.get(call_type, 0) + 1

            print(f"  - Call types:")
            for call_type, count in sorted(call_types.items()):
                print(f"    - {call_type}: {count}")

    except json.JSONDecodeError as e:
        print(f"[X] JSON PARSE ERROR: {e}")
    except Exception as e:
        print(f"[X] ERROR: {e}")


def main():
    """Main test runner."""
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "all":
            # Test multiple traces
            max_tests = int(sys.argv[2]) if len(sys.argv) > 2 else 3
            test_all_traces(max_tests)

        elif command == "validate":
            # Validation only
            test_validation_only()

        elif command == "find":
            # Just find and list trace files
            trace_files = find_trace_files()
            print(f"\nFound {len(trace_files)} trace files:")
            for f in trace_files:
                print(f"  - {f}")

        else:
            # Test specific pattern
            test_specific_trace(command)

    else:
        # Default: test with first trace file
        print("Testing with first available trace file...")
        print("(Use 'all', 'validate', 'find', or a pattern as argument)\n")

        trace_files = find_trace_files()

        if trace_files:
            test_with_trace(trace_files[0])
        else:
            print("No trace files found")


if __name__ == "__main__":
    main()
