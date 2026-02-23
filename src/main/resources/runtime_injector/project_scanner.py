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
        """Extract all function and method names with line numbers from a Python file.

        Methods are extracted with class context: ClassName.method_name
        This matches the co_qualname used in runtime tracing.
        """
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

        # Use a visitor to properly track class context
        self._extract_with_context(tree, functions, func_lines, class_name=None)

        return functions, func_lines

    def _extract_with_context(self, node, functions, func_lines, class_name=None):
        """Recursively extract functions with proper class context.

        Handles nested classes by building full qualified names like:
        OuterClass.InnerClass.method (matching Python's co_qualname)
        """
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                # Build nested class name: OuterClass.InnerClass
                nested_class_name = "{0}.{1}".format(class_name, child.name) if class_name else child.name
                # Recurse into class with its full nested name as context
                self._extract_with_context(child, functions, func_lines, class_name=nested_class_name)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Build qualified name like co_qualname does
                if class_name:
                    full_name = "{0}.{1}".format(class_name, child.name)
                else:
                    full_name = child.name
                functions.add(full_name)
                func_lines[full_name] = child.lineno
                # Also recurse into nested functions/classes (keep same class context)
                self._extract_with_context(child, functions, func_lines, class_name=class_name)
            else:
                # Continue recursing for other nodes (e.g., if blocks with class defs)
                self._extract_with_context(child, functions, func_lines, class_name=class_name)

    def extract_function_metadata(self, filepath, function_name):
        """Extract full metadata for a specific function via AST.

        Args:
            filepath: Absolute path to the Python source file
            function_name: Function name, optionally qualified (e.g. 'ClassName.method')

        Returns:
            dict with keys: name, qualified_name, docstring, is_async, is_method,
            parameters (list of dicts), return_annotation, decorators, source_code,
            source_lines (start, end). Returns None if function not found.
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                source = f.read()
                source_lines = source.splitlines()
        except Exception:
            return None

        try:
            tree = ast.parse(source, filename=filepath)
        except SyntaxError:
            return None

        # Find the function node in the AST
        node = self._find_function_node(tree, function_name)
        if node is None:
            return None

        # Extract docstring
        docstring = ast.get_docstring(node)

        # Extract parameters
        parameters = []
        args_node = node.args

        # Count how many positional args have defaults (they align to the end)
        num_defaults = len(args_node.defaults)
        num_args = len(args_node.args)

        for i, arg in enumerate(args_node.args):
            param = {
                'name': arg.arg,
                'annotation': self._unparse_annotation(arg.annotation),
                'has_default': False,
                'default': None
            }
            # Defaults align to the end of positional args
            default_idx = i - (num_args - num_defaults)
            if default_idx >= 0:
                param['has_default'] = True
                param['default'] = self._unparse_annotation(args_node.defaults[default_idx])
            parameters.append(param)

        # *args
        if args_node.vararg:
            parameters.append({
                'name': '*' + args_node.vararg.arg,
                'annotation': self._unparse_annotation(args_node.vararg.annotation),
                'has_default': False,
                'default': None
            })

        # keyword-only args
        for i, arg in enumerate(args_node.kwonlyargs):
            param = {
                'name': arg.arg,
                'annotation': self._unparse_annotation(arg.annotation),
                'has_default': False,
                'default': None
            }
            if i < len(args_node.kw_defaults) and args_node.kw_defaults[i] is not None:
                param['has_default'] = True
                param['default'] = self._unparse_annotation(args_node.kw_defaults[i])
            parameters.append(param)

        # **kwargs
        if args_node.kwarg:
            parameters.append({
                'name': '**' + args_node.kwarg.arg,
                'annotation': self._unparse_annotation(args_node.kwarg.annotation),
                'has_default': False,
                'default': None
            })

        # Extract return annotation
        return_annotation = self._unparse_annotation(node.returns)

        # Extract decorators
        decorators = []
        for dec in node.decorator_list:
            decorators.append(self._unparse_annotation(dec))

        # Is it a method? (first param is self or cls)
        is_method = (len(args_node.args) > 0 and
                     args_node.args[0].arg in ('self', 'cls'))

        # Extract source code
        start_line = node.lineno
        end_line = getattr(node, 'end_lineno', start_line)
        func_source = '\n'.join(source_lines[start_line - 1:end_line])

        return {
            'name': node.name,
            'qualified_name': function_name,
            'docstring': docstring,
            'is_async': isinstance(node, ast.AsyncFunctionDef),
            'is_method': is_method,
            'parameters': parameters,
            'return_annotation': return_annotation,
            'decorators': decorators,
            'source_code': func_source,
            'source_lines': (start_line, end_line)
        }

    def _find_function_node(self, tree, qualified_name, class_name=None):
        """Find a FunctionDef/AsyncFunctionDef node by qualified name in the AST."""
        parts = qualified_name.split('.')

        for child in ast.iter_child_nodes(tree):
            if isinstance(child, ast.ClassDef):
                current_class = "{0}.{1}".format(class_name, child.name) if class_name else child.name
                # If the qualified name starts with this class, recurse into it
                if qualified_name.startswith(current_class + '.') or qualified_name == current_class:
                    result = self._find_function_node(child, qualified_name, class_name=current_class)
                    if result is not None:
                        return result
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                full_name = "{0}.{1}".format(class_name, child.name) if class_name else child.name
                if full_name == qualified_name:
                    return child
                # Also check just the bare function name (for top-level functions)
                if class_name is None and child.name == qualified_name:
                    return child
                # Recurse for nested functions
                result = self._find_function_node(child, qualified_name, class_name=class_name)
                if result is not None:
                    return result
            else:
                result = self._find_function_node(child, qualified_name, class_name=class_name)
                if result is not None:
                    return result
        return None

    @staticmethod
    def _unparse_annotation(node):
        """Convert an AST annotation node back to a string. Returns None if no annotation."""
        if node is None:
            return None
        try:
            # Python 3.9+
            return ast.unparse(node)
        except AttributeError:
            # Fallback for older Python: try common patterns
            if isinstance(node, ast.Name):
                return node.id
            elif isinstance(node, ast.Constant):
                return repr(node.value)
            elif isinstance(node, ast.Attribute):
                return ast.dump(node)
            return str(type(node).__name__)

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
