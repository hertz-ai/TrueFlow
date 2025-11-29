"""
Manual Testing Script for Ultimate Architecture Visualization

This script allows step-by-step manual testing with detailed output.
"""

import json
import os
import sys
import subprocess
import glob
import time
from pathlib import Path

print("=" * 70)
print("MANUAL TEST SCRIPT - Ultimate Architecture Visualization")
print("=" * 70)
print()

# Test 1: Check if visualization script exists
print("[TEST 1] Checking if visualization script exists...")
viz_script = Path(__file__).parent / "ultimate_architecture_viz.py"
if viz_script.exists():
    print(f"  PASS: Found {viz_script}")
else:
    print(f"  FAIL: Not found {viz_script}")
    sys.exit(1)

# Test 2: Find available trace files
print("\n[TEST 2] Finding available trace files...")
trace_patterns = [
    str(Path(__file__).parent.parent.parent / ".pycharm_plugin" / "manim" / "traces" / "*.json"),
    str(Path(__file__).parent.parent.parent / "traces" / "*.json")
]

trace_files = []
for pattern in trace_patterns:
    found = glob.glob(pattern)
    trace_files.extend(found)
    if found:
        print(f"  Found {len(found)} files matching {pattern}")

if trace_files:
    print(f"  PASS: Found {len(trace_files)} trace files total")
    test_trace = trace_files[0]
    print(f"  Using: {test_trace}")
else:
    print("  FAIL: No trace files found")
    print("  Will create a test trace...")

    # Create test trace
    test_trace = Path(__file__).parent / "test_manual.json"
    trace_data = {
        "correlation_id": "manual_test",
        "timestamp": time.time(),
        "calls": [
            {
                "call_id": "call_1",
                "type": "call",
                "timestamp": time.time(),
                "module": "test.module.input",
                "function": "process_input",
                "file_path": "/test/input.py",
                "line_number": 10,
                "depth": 0
            },
            {
                "call_id": "call_2",
                "type": "call",
                "timestamp": time.time(),
                "module": "test.module.encoder",
                "function": "encode",
                "file_path": "/test/encoder.py",
                "line_number": 20,
                "depth": 1
            },
            {
                "call_id": "call_3",
                "type": "call",
                "timestamp": time.time(),
                "module": "test.module.processing",
                "function": "process",
                "file_path": "/test/process.py",
                "line_number": 30,
                "depth": 1
            },
            {
                "call_id": "call_4",
                "type": "call",
                "timestamp": time.time(),
                "module": "test.module.decoder",
                "function": "decode",
                "file_path": "/test/decoder.py",
                "line_number": 40,
                "depth": 0
            }
        ]
    }

    with open(test_trace, 'w') as f:
        json.dump(trace_data, f, indent=2)

    print(f"  Created test trace: {test_trace}")

# Test 3: Validate trace structure
print(f"\n[TEST 3] Validating trace structure...")
try:
    with open(test_trace, 'r') as f:
        data = json.load(f)

    if "calls" in data:
        print(f"  PASS: Valid JSON with {len(data['calls'])} calls")

        # Show first call
        if data['calls']:
            first_call = data['calls'][0]
            print(f"  First call: {first_call.get('module', 'N/A')}.{first_call.get('function', 'N/A')}")
    else:
        print("  WARN: No 'calls' field in trace")

except json.JSONDecodeError as e:
    print(f"  FAIL: Invalid JSON - {e}")
except Exception as e:
    print(f"  FAIL: {e}")

# Test 4: Check dependencies
print(f"\n[TEST 4] Checking dependencies...")
try:
    import manim
    print(f"  PASS: manim installed (version {manim.__version__})")
except ImportError:
    print("  FAIL: manim not installed")
    sys.exit(1)

try:
    import numpy
    print(f"  PASS: numpy installed")
except ImportError:
    print("  FAIL: numpy not installed")
    sys.exit(1)

# Test 5: Run visualization (with timeout)
print(f"\n[TEST 5] Running visualization...")
print(f"  Command: python {viz_script} {test_trace}")
print(f"  This may take 1-3 minutes...")
print()

start_time = time.time()
try:
    result = subprocess.run(
        [sys.executable, str(viz_script), str(test_trace)],
        capture_output=True,
        text=True,
        timeout=300  # 5 minute timeout
    )

    duration = time.time() - start_time
    print(f"  Completed in {duration:.1f} seconds")
    print()

    if result.returncode == 0:
        print("  PASS: Visualization completed successfully")
    else:
        print(f"  FAIL: Visualization failed with exit code {result.returncode}")

    # Show output
    if result.stdout:
        print("\n  STDOUT:")
        for line in result.stdout.split('\n')[-20:]:  # Last 20 lines
            print(f"    {line}")

    if result.stderr:
        print("\n  STDERR:")
        for line in result.stderr.split('\n')[-20:]:  # Last 20 lines
            print(f"    {line}")

except subprocess.TimeoutExpired:
    duration = time.time() - start_time
    print(f"  FAIL: Timeout after {duration:.1f} seconds")
except Exception as e:
    duration = time.time() - start_time
    print(f"  FAIL: {e}")

# Test 6: Check for output video
print(f"\n[TEST 6] Checking for output video...")
video_patterns = [
    str(Path(__file__).parent / "media" / "videos" / "**" / "*.mp4"),
    str(Path(__file__).parent.parent.parent / "media" / "videos" / "**" / "*.mp4")
]

videos = []
for pattern in video_patterns:
    found = glob.glob(pattern, recursive=True)
    videos.extend(found)

if videos:
    print(f"  PASS: Found {len(videos)} video file(s)")
    for vid in videos[-3:]:  # Show last 3
        size_mb = os.path.getsize(vid) / 1024 / 1024
        print(f"    - {os.path.basename(vid)} ({size_mb:.1f} MB)")
else:
    print("  FAIL: No video files found")

# Test 7: Summary
print("\n" + "=" * 70)
print("TEST SUMMARY")
print("=" * 70)
print()

if videos:
    print("SUCCESS: Video generated successfully!")
    print(f"Location: {videos[-1]}")
    print()
    print("Manual Visual Inspection:")
    print("  1. Open the video file")
    print("  2. Check: Is text readable?")
    print("  3. Check: Are animations smooth?")
    print("  4. Check: Do colors make sense?")
    print("  5. Check: Does camera movement help understanding?")
else:
    print("INCOMPLETE: Video not generated")
    print("Review the error messages above")

print()
print("=" * 70)
