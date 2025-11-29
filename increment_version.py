#!/usr/bin/env python3
"""
Auto-increment plugin version on each build.

Updates version in:
1. gradle.properties (single source of truth, read by both Gradle and PluginLogger.kt at runtime)
"""

import re
import sys
from pathlib import Path

def increment_version(version_str):
    """Increment patch version (1.2.0 -> 1.2.1)."""
    parts = version_str.split('.')
    if len(parts) != 3:
        print(f"[FAIL] Invalid version format: {version_str}")
        return version_str

    major, minor, patch = parts
    new_patch = int(patch) + 1
    return f"{major}.{minor}.{new_patch}"

def update_file(filepath, pattern, replacement_template):
    """Update version in a file using regex."""
    content = filepath.read_text(encoding='utf-8')

    # Find current version
    match = re.search(pattern, content)
    if not match:
        print(f"[FAIL] Version pattern not found in {filepath}")
        return None

    old_version = match.group(1)
    new_version = increment_version(old_version)

    # Replace
    new_content = re.sub(pattern, replacement_template.format(new_version), content)
    filepath.write_text(new_content, encoding='utf-8')

    print(f"[OK] Updated {filepath.name}: {old_version} -> {new_version}")
    return new_version

def main():
    plugin_dir = Path(__file__).parent

    # Update gradle.properties (single source of truth)
    gradle_props = plugin_dir / "gradle.properties"
    new_version = update_file(
        gradle_props,
        r'pluginVersion = ([0-9]+\.[0-9]+\.[0-9]+)',
        'pluginVersion = {0}'
    )

    if not new_version:
        print("[FAIL] Could not update gradle.properties")
        sys.exit(1)

    print(f"\n[OK] Version incremented to: {new_version}")
    print(f"[OK] Artifact will be named: pycharm-plugin-{new_version}.jar")
    print(f"[OK] PluginLogger.kt reads version from gradle.properties at runtime")

if __name__ == "__main__":
    main()
