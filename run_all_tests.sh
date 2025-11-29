#!/bin/bash
# ============================================================================
# TrueFlow Consolidated Test Runner
# ============================================================================
# Runs all tests for TrueFlow project including:
#   - Manim Visualizer tests (unit, integration, visual, e2e)
#   - Runtime Instrumentor tests (unit, error handling, end-to-end)
#   - Protocol Detection tests
#   - Frame Bounds Validation tests
#   - New Visualizers tests
# ============================================================================

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Activate virtual environment if it exists
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
elif [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# Set PYTHONPATH
export PYTHONPATH="$SCRIPT_DIR/src/main/resources/runtime_injector:$SCRIPT_DIR/src/main/resources:$SCRIPT_DIR:$SCRIPT_DIR/manim_visualizer"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Track results
TOTAL_PASSED=0
TOTAL_FAILED=0
FAILED_SUITES=""

echo ""
echo -e "${CYAN}============================================================================${NC}"
echo -e "${CYAN}                    TrueFlow Consolidated Test Runner                       ${NC}"
echo -e "${CYAN}============================================================================${NC}"
echo ""

# Check prerequisites
if ! command -v python &> /dev/null; then
    echo -e "${RED}ERROR: python not found${NC}"
    exit 1
fi

# Check if pytest is available, if not install dependencies
if ! python -m pytest --version &> /dev/null; then
    echo -e "${YELLOW}Installing test dependencies...${NC}"
    pip install -r manim_visualizer/requirements-test.txt -q
    if [ $? -ne 0 ]; then
        echo -e "${RED}ERROR: Failed to install test dependencies${NC}"
        exit 1
    fi
fi

# Check if manim is available, if not install it
if ! python -c "import manim" &> /dev/null; then
    echo -e "${YELLOW}Installing manim and visualizer dependencies...${NC}"
    pip install -r manim_visualizer/requirements.txt -q
    if [ $? -ne 0 ]; then
        echo -e "${RED}ERROR: Failed to install manim dependencies${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}All dependencies installed${NC}"

# Function to run a test suite
run_tests() {
    local name="$1"
    local dir="$2"
    shift 2
    local tests="$@"

    echo ""
    echo -e "${YELLOW}[$name] Running...${NC}"
    echo "------------------------------------------------------------------------"

    cd "$SCRIPT_DIR/$dir"

    if python -m pytest $tests -v --tb=short -q; then
        echo -e "${GREEN}$name: PASSED${NC}"
        ((TOTAL_PASSED++)) || true
    else
        echo -e "${RED}$name: FAILED${NC}"
        ((TOTAL_FAILED++)) || true
        FAILED_SUITES="$FAILED_SUITES\n  - $name"
    fi

    cd "$SCRIPT_DIR"
}

# ============================================================================
# Run all test suites
# ============================================================================

# Section 1: Manim Visualizer Unit Tests (70 tests)
run_tests "1/8 Manim Unit Tests" "manim_visualizer" \
    "tests/test_frame_bounds_validation.py tests/test_animation_pacing.py tests/test_base_trace_visualizer.py"

# Section 2: Visual Regression Tests (15 tests)
run_tests "2/8 Visual Regression" "manim_visualizer" \
    "tests/test_visual_regression.py"

# Section 3: E2E Regression Tests (22 tests)
run_tests "3/8 E2E Regression" "manim_visualizer" \
    "tests/test_e2e_regression.py"

# Section 4: Runtime Instrumentor Unit Tests (18 tests)
run_tests "4/8 Runtime Instrumentor" "." \
    "tests/test_runtime_instrumentor_unit.py"

# Section 5: Error Handling & End-to-End Tests (21 tests)
run_tests "5/8 Error Handling & E2E" "." \
    "tests/test_error_handling.py tests/test_end_to_end.py"

# Section 6: Protocol Detection Tests (4 tests)
run_tests "6/8 Protocol Detection" "." \
    "tests/test_protocol_detection_integration.py"

# Section 7: Manim Integration Tests (7 tests)
run_tests "7/8 Manim Integration" "manim_visualizer" \
    "test_integration.py test_plugin_integration.py"

# Section 8: New Visualizers Tests (6 tests - 2 known failures)
run_tests "8/8 New Visualizers" "manim_visualizer" \
    "test_new_visualizers.py test_comprehensive_enhancements.py"

# ============================================================================
# Summary
# ============================================================================
echo ""
echo -e "${CYAN}============================================================================${NC}"
echo -e "${CYAN}                           TEST SUMMARY                                     ${NC}"
echo -e "${CYAN}============================================================================${NC}"
echo ""
echo -e "  Test Suites Passed: ${GREEN}$TOTAL_PASSED${NC}"
echo -e "  Test Suites Failed: ${RED}$TOTAL_FAILED${NC}"

if [ "$TOTAL_FAILED" -gt 0 ]; then
    echo -e "\n  Failed suites:${RED}$FAILED_SUITES${NC}"
fi

echo ""
echo "Expected test counts per suite:"
echo "  1. Manim Unit Tests:        70 tests (frame bounds, animation pacing, base visualizer)"
echo "  2. Visual Regression:       15 tests"
echo "  3. E2E Regression:          22 tests"
echo "  4. Runtime Instrumentor:    18 tests"
echo "  5. Error Handling & E2E:    21 tests"
echo "  6. Protocol Detection:       4 tests"
echo "  7. Manim Integration:        7 tests"
echo "  8. New Visualizers:          6 tests (2 known failures)"
echo "  ----------------------------------"
echo "  TOTAL:                     ~163 tests"
echo ""
echo "Run individual test suites:"
echo "  - Quick tests:        ./gradlew runQuickTests"
echo "  - Fast tests:         ./gradlew runFastTests"
echo "  - Full regression:    ./gradlew runRegressionTests"
echo "  - Coverage report:    ./gradlew generateCoverageReport"
echo ""

exit $TOTAL_FAILED
