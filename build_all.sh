#!/bin/bash
# ============================================================
# TrueFlow - Build All Variants
# Builds: PyCharm Plugin + VS Code Extension + Python Deps
# Usage: ./build_all.sh [--test] [--skip-python]
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_SUCCESS=1
RUN_TESTS=0
SKIP_PYTHON=0

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --test) RUN_TESTS=1; shift ;;
        --skip-python) SKIP_PYTHON=1; shift ;;
        *) shift ;;
    esac
done

echo ""
echo "============================================================"
echo "TrueFlow - Building All Variants"
echo "============================================================"
echo ""

# Activate virtual environment if it exists
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
    echo "[OK] Activated .venv"
elif [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
    echo "[OK] Activated venv"
fi

# ============================================================
# 0. Install Python Dependencies (if not skipped)
# ============================================================
if [ "$SKIP_PYTHON" -eq 0 ]; then
    echo ""
    echo "[0/3] Installing Python Dependencies..."
    echo "------------------------------------------------------------"

    cd "$SCRIPT_DIR"

    # Install manim visualizer dependencies
    if [ -f "manim_visualizer/requirements.txt" ]; then
        pip install -r manim_visualizer/requirements.txt -q 2>/dev/null
        if [ $? -eq 0 ]; then
            echo "  [OK] Manim dependencies installed"
        else
            echo "  [WARN] Some manim dependencies may have failed"
        fi
    fi

    # Install test dependencies
    if [ -f "manim_visualizer/requirements-test.txt" ]; then
        pip install -r manim_visualizer/requirements-test.txt -q 2>/dev/null
        if [ $? -eq 0 ]; then
            echo "  [OK] Test dependencies installed"
        else
            echo "  [WARN] Some test dependencies may have failed"
        fi
    fi
else
    echo ""
    echo "[0/3] Skipping Python dependencies (--skip-python)"
fi

# ============================================================
# 1. Build PyCharm Plugin (Kotlin/Gradle)
# ============================================================
echo ""
echo "[1/3] Building PyCharm Plugin..."
echo "------------------------------------------------------------"

cd "$SCRIPT_DIR"

if command -v gradle &> /dev/null; then
    gradle clean buildPlugin --no-daemon || BUILD_SUCCESS=0
elif [ -f "./gradlew" ]; then
    ./gradlew clean buildPlugin --no-daemon || BUILD_SUCCESS=0
else
    echo "[ERROR] Gradle not found. Install Gradle or use gradlew"
    BUILD_SUCCESS=0
fi

if [ $BUILD_SUCCESS -eq 1 ]; then
    echo "[SUCCESS] PyCharm plugin built successfully!"
    find "$SCRIPT_DIR/build/distributions" -name "*.zip" 2>/dev/null | while read f; do
        echo "  Output: $f"
    done
fi

# ============================================================
# 2. Build VS Code Extension (TypeScript/npm)
# ============================================================
echo ""
echo "[2/3] Building VS Code Extension..."
echo "------------------------------------------------------------"

cd "$SCRIPT_DIR/vscode-extension"

if [ -f "package.json" ]; then
    # Install dependencies if node_modules doesn't exist
    if [ ! -d "node_modules" ]; then
        echo "  Installing npm dependencies..."
        npm install
    fi

    # Compile TypeScript
    if npm run compile; then
        echo "[SUCCESS] VS Code extension built successfully!"
        echo "  Output: $SCRIPT_DIR/vscode-extension/out/"

        # Package VSIX if vsce is available
        if command -v vsce &> /dev/null; then
            echo "  Packaging VSIX..."
            vsce package
            ls -la *.vsix 2>/dev/null
        else
            echo "  [INFO] Install vsce to package VSIX: npm install -g @vscode/vsce"
        fi
    else
        echo "[FAILED] VS Code extension build failed!"
        BUILD_SUCCESS=0
    fi
else
    echo "[SKIPPED] VS Code extension - package.json not found"
fi

# ============================================================
# 3. Run Tests (if --test flag provided)
# ============================================================
if [ "$RUN_TESTS" -eq 1 ]; then
    echo ""
    echo "[3/3] Running Tests..."
    echo "------------------------------------------------------------"

    cd "$SCRIPT_DIR"

    # Set PYTHONPATH
    export PYTHONPATH="$SCRIPT_DIR/src/main/resources/runtime_injector:$SCRIPT_DIR/src/main/resources:$SCRIPT_DIR:$SCRIPT_DIR/manim_visualizer"

    # Run quick tests
    if python -m pytest tests/test_runtime_instrumentor_unit.py tests/test_error_handling.py -v --tb=short -q; then
        echo "[OK] Core tests passed"
    else
        echo "[WARN] Some tests failed"
    fi

    cd "$SCRIPT_DIR/manim_visualizer"
    if python -m pytest tests/test_frame_bounds_validation.py tests/test_animation_pacing.py -v --tb=short -q; then
        echo "[OK] Manim tests passed"
    else
        echo "[WARN] Some manim tests failed"
    fi
else
    echo ""
    echo "[3/3] Skipping tests (use --test to run)"
fi

# ============================================================
# Summary
# ============================================================
echo ""
echo "============================================================"
echo "Build Summary"
echo "============================================================"

cd "$SCRIPT_DIR"

echo ""
echo "PyCharm Plugin:"
if ls build/distributions/*.zip 1> /dev/null 2>&1; then
    for f in build/distributions/*.zip; do
        echo "  [OK] $f"
    done
else
    echo "  [MISSING] No plugin ZIP found"
fi

echo ""
echo "VS Code Extension:"
if [ -f "vscode-extension/out/extension.js" ]; then
    echo "  [OK] vscode-extension/out/extension.js"
else
    echo "  [MISSING] Extension not compiled"
fi

echo ""
echo "Python Dependencies:"
python -c "import manim; print('  [OK] manim', manim.__version__)" 2>/dev/null || echo "  [MISSING] manim not installed"
python -c "import pytest; print('  [OK] pytest', pytest.__version__)" 2>/dev/null || echo "  [MISSING] pytest not installed"

echo ""
if [ "$BUILD_SUCCESS" -eq 1 ]; then
    echo "============================================================"
    echo "All builds completed successfully!"
    echo "============================================================"
    echo ""
    echo "Usage:"
    echo "  ./build_all.sh              Build all components"
    echo "  ./build_all.sh --test       Build and run quick tests"
    echo "  ./build_all.sh --skip-python  Skip Python dependency install"
    echo "  ./run_all_tests.sh          Run full test suite (~163 tests)"
    echo ""
else
    echo "============================================================"
    echo "Some builds failed - check output above"
    echo "============================================================"
    exit 1
fi
