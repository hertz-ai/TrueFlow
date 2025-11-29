#!/bin/bash
# ============================================================
# TrueFlow - Build All Variants
# Builds: PyCharm Plugin + VS Code Extension
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_SUCCESS=1

echo ""
echo "============================================================"
echo "TrueFlow - Building All Variants"
echo "============================================================"
echo ""

# ============================================================
# 1. Build PyCharm Plugin (Kotlin/Gradle)
# ============================================================
echo ""
echo "[1/2] Building PyCharm Plugin..."
echo "------------------------------------------------------------"

cd "$SCRIPT_DIR"

if command -v gradle &> /dev/null; then
    gradle clean buildPlugin --no-daemon
elif [ -f "./gradlew" ]; then
    ./gradlew clean buildPlugin --no-daemon
else
    echo "[ERROR] Gradle not found. Install Gradle or use gradlew"
    BUILD_SUCCESS=0
fi

if [ $? -eq 0 ]; then
    echo "[SUCCESS] PyCharm plugin built successfully!"
    find "$SCRIPT_DIR/build/distributions" -name "*.zip" 2>/dev/null | while read f; do
        echo "  Output: $f"
    done
else
    echo "[FAILED] PyCharm plugin build failed!"
    BUILD_SUCCESS=0
fi

# ============================================================
# 2. Build VS Code Extension (TypeScript/npm)
# ============================================================
echo ""
echo "[2/2] Building VS Code Extension..."
echo "------------------------------------------------------------"

cd "$SCRIPT_DIR/vscode-extension"

if [ -f "package.json" ]; then
    # Install dependencies if node_modules doesn't exist
    if [ ! -d "node_modules" ]; then
        echo "  Installing npm dependencies..."
        npm install
    fi

    # Compile TypeScript
    npm run compile

    if [ $? -eq 0 ]; then
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
if [ "$BUILD_SUCCESS" -eq 1 ]; then
    echo "============================================================"
    echo "All builds completed successfully!"
    echo "============================================================"
else
    echo "============================================================"
    echo "Some builds failed - check output above"
    echo "============================================================"
    exit 1
fi
