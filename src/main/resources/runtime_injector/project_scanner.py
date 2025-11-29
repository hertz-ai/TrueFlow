"""
Project Scanner - Scans Python project to find all user-defined functions/methods.

This eliminates the need for hardcoded filtering patterns. Instead, we:
1. Scan the project directory for all .py files
2. Parse them to extract function/method definitions
3. Build a whitelist of (file, function) pairs to trace
4. Only trace functions that are in this whitelist

This approach is much more accurate than pattern matching.
"""

from __future__ import print_function
import os
import ast
import sys

class ProjectScanner(object):
    """Scans a Python project to find all user-defined functions."""

    def __init__(self, project_root):
        self.project_root = os.path.abspath(project_root)
        self.functions = {}  # {file_path: set(function_names)}
        self.function_lines = {}  # {file_path: {function_name: line_number}}
        self.file_set = set()  # Set of all project files (for fast lookup)

    def scan(self):
        """Scan the project directory for all Python files and extract functions."""
        print("[ProjectScanner] Scanning project: {0}".format(self.project_root))

        file_count = 0
        function_count = 0

        for root, dirs, files in os.walk(self.project_root):
            # Skip common non-source directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in [
                '__pycache__', 'venv', 'env', '.git', '.idea', 'node_modules',
                'build', 'dist', 'eggs', '.eggs', '.tox', '.pytest_cache'
            ]]

            for filename in files:
                if filename.endswith('.py'):
                    filepath = os.path.join(root, filename)
                    self.file_set.add(os.path.abspath(filepath))

                    try:
                        functions, func_lines = self._extract_functions(filepath)
                        if functions:
                            abs_path = os.path.abspath(filepath)
                            self.functions[abs_path] = functions
                            self.function_lines[abs_path] = func_lines
                            file_count += 1
                            function_count += len(functions)
                    except Exception as e:
                        # Silently skip files that can't be parsed
                        pass

        print("[ProjectScanner] Found {0} functions in {1} files".format(
            function_count, file_count))
        return self.functions

    def _extract_functions(self, filepath):
        """Extract all function and method names with line numbers from a Python file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                source = f.read()
        except:
            # Try without encoding for Python 2
            with open(filepath, 'r') as f:
                source = f.read()

        try:
            tree = ast.parse(source, filename=filepath)
        except SyntaxError:
            return set(), {}

        functions = set()
        func_lines = {}  # {function_name: line_number}

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions.add(node.name)
                func_lines[node.name] = node.lineno
            elif isinstance(node, ast.AsyncFunctionDef):
                functions.add(node.name)
                func_lines[node.name] = node.lineno

        return functions, func_lines

    def get_function_line(self, filepath, function_name):
        """Get the line number for a function in a file."""
        abs_path = os.path.abspath(filepath)
        file_lines = self.function_lines.get(abs_path, {})
        return file_lines.get(function_name, 0)

    def should_trace(self, filepath, function_name):
        """
        Check if a function should be traced.

        Returns True if:
        - File is in the project
        - Function is defined in that file
        """
        abs_path = os.path.abspath(filepath)

        # Fast check: is file even in project?
        if abs_path not in self.file_set:
            return False

        # Check if function exists in this file
        file_functions = self.functions.get(abs_path, set())
        return function_name in file_functions

    def is_project_file(self, filepath):
        """Check if a file is part of the project."""
        abs_path = os.path.abspath(filepath)
        return abs_path in self.file_set

    def get_stats(self):
        """Get statistics about the scan."""
        total_files = len(self.functions)
        total_functions = sum(len(funcs) for funcs in self.functions.values())
        return {
            'files': total_files,
            'functions': total_functions
        }


def scan_project(project_root):
    """Scan a project and return the scanner instance."""
    scanner = ProjectScanner(project_root)
    scanner.scan()
    return scanner


if __name__ == '__main__':
    # Test the scanner
    if len(sys.argv) > 1:
        project_root = sys.argv[1]
    else:
        project_root = os.getcwd()

    scanner = scan_project(project_root)
    stats = scanner.get_stats()

    print("\n=== Scan Results ===")
    print("Files: {0}".format(stats['files']))
    print("Functions: {0}".format(stats['functions']))
    print("\nExample files:")
    for filepath, functions in list(scanner.functions.items())[:5]:
        print("  {0}: {1} functions".format(
            os.path.basename(filepath), len(functions)))
