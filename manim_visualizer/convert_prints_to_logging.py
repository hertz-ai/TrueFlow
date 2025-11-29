"""
Script to convert all print() statements to logger calls in manim visualizer files.

Run this to complete the logging migration.
"""

import re
from pathlib import Path

# Files to update
FILES_TO_UPDATE = [
    'queue_aware_renderer.py',
    'procedural_trace_viz.py',
    'llm_operation_mapper.py',
    'test_integration.py',
    'advanced_operation_viz.py',
]


def convert_file(filepath: Path):
    """Convert print statements to logger calls in a file."""
    print(f"\nProcessing {filepath.name}...")

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content

    # Check if logging is already imported
    has_logging_import = 'from logging_config import' in content or 'import logging' in content

    if not has_logging_import:
        # Add logging import after other imports
        import_pattern = r'(import .*?\n(?:from .*?\n)*)'
        match = re.search(import_pattern, content)
        if match:
            imports_end = match.end()
            logger_name = filepath.stem  # Use filename as logger name
            logging_import = f"\n# Import logging configuration\nfrom logging_config import setup_logger\n\n# Initialize logger\nlogger = setup_logger('{logger_name}')\n"
            content = content[:imports_end] + logging_import + content[imports_end:]
            print(f"  Added logging import")

    # Replace print statements with appropriate logger calls
    patterns = [
        # Error patterns
        (r'print\(f?"?\[?ERROR\]?:?\s*([^"]*?)"\)', r'logger.error(\1)'),
        (r'print\(f?"?\[?Error\]?:?\s*([^"]*?)"\)', r'logger.error(\1)'),

        # Warning patterns
        (r'print\(f?"?\[?WARN\]?:?\s*([^"]*?)"\)', r'logger.warning(\1)'),
        (r'print\(f?"?\[?Warning\]?:?\s*([^"]*?)"\)', r'logger.warning(\1)'),

        # Debug patterns (Skip, Candidate, etc.)
        (r'print\(f?"?\[?Skip\]?:?\s*([^"]*?)"\)', r'logger.debug(\1)'),
        (r'print\(f?"?\[?Candidate\]?:?\s*([^"]*?)"\)', r'logger.debug(\1)'),

        # Info patterns (most others)
        (r'print\(f?"?\[?([A-Z][a-z]+)\]?:?\s*([^"]*?)"\)', r'logger.info(\2)'),

        # Generic print(f"...") -> logger.info(f"...")
        (r'print\((f"[^"]*?")\)', r'logger.info(\1)'),
        (r'print\((".*?")\)', r'logger.info(\1)'),

        # Test results
        (r'print\(f?"?\[?PASS\]?([^"]*?)"\)', r'logger.info(f"PASS\1")'),
        (r'print\(f?"?\[?FAIL\]?([^"]*?)"\)', r'logger.error(f"FAIL\1")'),
        (r'print\(f?"?\[?OK\]?([^"]*?)"\)', r'logger.info(f"OK\1")'),
    ]

    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)

    # Count changes
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✓ Updated {filepath.name}")
        return True
    else:
        print(f"  No changes needed for {filepath.name}")
        return False


def main():
    """Main conversion function."""
    print("="*60)
    print("CONVERTING PRINT STATEMENTS TO LOGGING")
    print("="*60)

    base_dir = Path(__file__).parent
    updated_files = []

    for filename in FILES_TO_UPDATE:
        filepath = base_dir / filename
        if filepath.exists():
            if convert_file(filepath):
                updated_files.append(filename)
        else:
            print(f"  Warning: {filename} not found")

    print("\n" + "="*60)
    print(f"SUMMARY: Updated {len(updated_files)} files")
    print("="*60)

    if updated_files:
        print("\nUpdated files:")
        for filename in updated_files:
            print(f"  - {filename}")

    print("\nLogs will be written to: .pycharm_plugin/logs/manim_visualizer_YYYYMMDD.log")
    print("\nRun any script to test logging:")
    print("  python queue_aware_renderer.py")
    print("  python test_integration.py")


if __name__ == '__main__':
    main()
