"""
Branch Coverage Analyzer - Extracts all branches and call sites from Python source.

This enables the "Why Not Covered" feature by analyzing:
1. All branch points (if/elif/else, try/except, for/while, match/case)
2. All call sites (where functions are called from)
3. Conditions for each branch

Combined with runtime trace data, this allows us to show:
- Which branches were NOT taken
- WHY a function wasn't called (which branch condition wasn't satisfied)
- Root cause analysis tracing back to the source of dead code
"""

from __future__ import print_function
import ast
import os
import sys
import json

class BranchInfo:
    """Information about a branch point in the code."""

    def __init__(self, branch_type, line, end_line, condition_text, parent_function):
        self.branch_type = branch_type  # 'if', 'elif', 'else', 'try', 'except', 'for', 'while', 'match', 'case'
        self.line = line
        self.end_line = end_line
        self.condition_text = condition_text  # The condition expression as string
        self.parent_function = parent_function
        self.branch_id = f"{parent_function}:{line}:{branch_type}"
        self.children = []  # Nested branches
        self.calls_inside = []  # Function calls inside this branch

    def to_dict(self):
        return {
            'branch_id': self.branch_id,
            'type': self.branch_type,
            'line': self.line,
            'end_line': self.end_line,
            'condition': self.condition_text,
            'parent_function': self.parent_function,
            'calls_inside': self.calls_inside,
            'children': [c.to_dict() for c in self.children]
        }


class CallSiteInfo:
    """Information about where a function is called from."""

    def __init__(self, callee_name, caller_function, line, in_branch=None):
        self.callee_name = callee_name  # The function being called
        self.caller_function = caller_function  # The function containing the call
        self.line = line
        self.in_branch = in_branch  # BranchInfo if call is inside a branch, None if unconditional

    def to_dict(self):
        return {
            'callee': self.callee_name,
            'caller': self.caller_function,
            'line': self.line,
            'in_branch': self.in_branch.to_dict() if self.in_branch else None
        }


class BranchCoverageAnalyzer(ast.NodeVisitor):
    """
    Analyzes Python source code to extract all branches and call sites.

    This is used to determine WHY code wasn't executed:
    - If a function wasn't called, we can find all call sites and check which branch wasn't taken
    - We can trace back through the call graph to find the root cause
    """

    def __init__(self, source_code, file_path):
        self.source_code = source_code
        self.source_lines = source_code.split('\n')
        self.file_path = file_path

        # Results
        self.functions = {}  # {func_name: {'line': N, 'branches': [], 'calls': []}}
        self.branches = []  # All branch points
        self.call_sites = []  # All function calls
        self.call_graph = {}  # {caller: [callees]}
        self.classes = {}  # {class_name: {'line': N, 'methods': [], 'attributes': {}}}

        # Type tracking for cross-class call resolution
        self.class_attributes = {}  # {ClassName: {attr_name: TypeName}}
        self.local_types = {}  # {func_name: {var_name: TypeName}}
        self.imports = {}  # {alias: full_name}

        # State during traversal
        self._current_function = None
        self._current_class = None
        self._branch_stack = []  # Stack of current branch context

    def analyze(self):
        """Parse and analyze the source code."""
        try:
            tree = ast.parse(self.source_code, filename=self.file_path)
            self.visit(tree)
        except SyntaxError as e:
            print(f"[BranchAnalyzer] Syntax error in {self.file_path}: {e}")
        return self

    def _get_source_segment(self, node):
        """Extract the source code for a node (condition text)."""
        try:
            if hasattr(ast, 'get_source_segment'):
                # Python 3.8+
                return ast.get_source_segment(self.source_code, node) or ''
            else:
                # Fallback for older Python
                return ast.dump(node)
        except:
            return ''

    def _get_full_name(self, name):
        """Get fully qualified name including class if applicable."""
        if self._current_class:
            return f"{self._current_class}.{name}"
        return name

    def visit_Import(self, node):
        """Track imports for type resolution."""
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.imports[name] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        """Track from imports for type resolution."""
        module = node.module or ''
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            full_name = f"{module}.{alias.name}" if module else alias.name
            self.imports[name] = full_name
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        """Track class context for method names."""
        old_class = self._current_class
        self._current_class = node.name

        # Register the class
        self.classes[node.name] = {
            'line': node.lineno,
            'methods': [],
            'attributes': {},
            'bases': [self._get_base_name(b) for b in node.bases]
        }
        self.class_attributes[node.name] = {}

        self.generic_visit(node)
        self._current_class = old_class

    def _get_base_name(self, node):
        """Extract base class name."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return None

    def visit_Assign(self, node):
        """Track assignments to infer types for cross-class call resolution."""
        # Get the assigned value's type (if it's a constructor call)
        assigned_type = self._get_assigned_type(node.value)

        for target in node.targets:
            if isinstance(target, ast.Attribute):
                # self.x = SomeClass() -> class attribute
                if isinstance(target.value, ast.Name) and target.value.id == 'self' and self._current_class:
                    attr_name = target.attr
                    if assigned_type:
                        self.class_attributes[self._current_class][attr_name] = assigned_type
                    # Also track in classes dict
                    if self._current_class in self.classes:
                        self.classes[self._current_class]['attributes'][attr_name] = assigned_type
            elif isinstance(target, ast.Name) and self._current_function:
                # x = SomeClass() -> local variable
                var_name = target.id
                if assigned_type:
                    if self._current_function not in self.local_types:
                        self.local_types[self._current_function] = {}
                    self.local_types[self._current_function][var_name] = assigned_type

        self.generic_visit(node)

    def _get_assigned_type(self, node):
        """Infer the type from an assignment value (constructor call)."""
        if isinstance(node, ast.Call):
            # SomeClass() or module.SomeClass()
            if isinstance(node.func, ast.Name):
                return node.func.id
            elif isinstance(node.func, ast.Attribute):
                return node.func.attr
        return None

    def visit_FunctionDef(self, node):
        """Extract function definition with its branches and calls."""
        self._process_function(node)

    def visit_AsyncFunctionDef(self, node):
        """Extract async function definition."""
        self._process_function(node)

    def _process_function(self, node):
        """Process a function/method definition."""
        old_function = self._current_function
        func_name = self._get_full_name(node.name)
        self._current_function = func_name

        self.functions[func_name] = {
            'name': node.name,
            'full_name': func_name,
            'line': node.lineno,
            'end_line': getattr(node, 'end_lineno', node.lineno),
            'branches': [],
            'calls': [],
            'is_async': isinstance(node, ast.AsyncFunctionDef)
        }

        # Initialize call graph entry
        if func_name not in self.call_graph:
            self.call_graph[func_name] = []

        # Visit function body
        self.generic_visit(node)

        self._current_function = old_function

    def visit_If(self, node):
        """Extract if/elif/else branches."""
        if not self._current_function:
            self.generic_visit(node)
            return

        # Main if condition
        condition_text = self._get_source_segment(node.test)
        branch = BranchInfo(
            branch_type='if',
            line=node.lineno,
            end_line=getattr(node, 'end_lineno', node.lineno),
            condition_text=condition_text,
            parent_function=self._current_function
        )

        self.branches.append(branch)
        self.functions[self._current_function]['branches'].append(branch.to_dict())

        # Track branch context for calls inside
        self._branch_stack.append(branch)

        # Visit if body
        for child in node.body:
            self.visit(child)

        self._branch_stack.pop()

        # Handle elif/else
        if node.orelse:
            if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
                # elif - visit recursively (will be handled as another If)
                elif_node = node.orelse[0]
                elif_condition = self._get_source_segment(elif_node.test)
                elif_branch = BranchInfo(
                    branch_type='elif',
                    line=elif_node.lineno,
                    end_line=getattr(elif_node, 'end_lineno', elif_node.lineno),
                    condition_text=elif_condition,
                    parent_function=self._current_function
                )
                self.branches.append(elif_branch)
                self.functions[self._current_function]['branches'].append(elif_branch.to_dict())

                self._branch_stack.append(elif_branch)
                self.visit(elif_node)
                self._branch_stack.pop()
            else:
                # else block
                else_line = node.orelse[0].lineno if node.orelse else node.lineno
                else_branch = BranchInfo(
                    branch_type='else',
                    line=else_line,
                    end_line=getattr(node, 'end_lineno', else_line),
                    condition_text=f"not ({condition_text})",
                    parent_function=self._current_function
                )
                self.branches.append(else_branch)
                self.functions[self._current_function]['branches'].append(else_branch.to_dict())

                self._branch_stack.append(else_branch)
                for child in node.orelse:
                    self.visit(child)
                self._branch_stack.pop()

    def visit_Try(self, node):
        """Extract try/except/finally branches."""
        if not self._current_function:
            self.generic_visit(node)
            return

        # Try block
        try_branch = BranchInfo(
            branch_type='try',
            line=node.lineno,
            end_line=getattr(node, 'end_lineno', node.lineno),
            condition_text='try block (no exception)',
            parent_function=self._current_function
        )
        self.branches.append(try_branch)
        self.functions[self._current_function]['branches'].append(try_branch.to_dict())

        self._branch_stack.append(try_branch)
        for child in node.body:
            self.visit(child)
        self._branch_stack.pop()

        # Except handlers
        for handler in node.handlers:
            exc_type = ''
            if handler.type:
                exc_type = self._get_source_segment(handler.type)
            except_branch = BranchInfo(
                branch_type='except',
                line=handler.lineno,
                end_line=getattr(handler, 'end_lineno', handler.lineno),
                condition_text=f"except {exc_type}" if exc_type else "except (bare)",
                parent_function=self._current_function
            )
            self.branches.append(except_branch)
            self.functions[self._current_function]['branches'].append(except_branch.to_dict())

            self._branch_stack.append(except_branch)
            for child in handler.body:
                self.visit(child)
            self._branch_stack.pop()

        # Finally block (always executed, but still a distinct code path)
        if node.finalbody:
            finally_branch = BranchInfo(
                branch_type='finally',
                line=node.finalbody[0].lineno,
                end_line=getattr(node, 'end_lineno', node.finalbody[0].lineno),
                condition_text='finally (always executed)',
                parent_function=self._current_function
            )
            self.branches.append(finally_branch)
            self.functions[self._current_function]['branches'].append(finally_branch.to_dict())

            self._branch_stack.append(finally_branch)
            for child in node.finalbody:
                self.visit(child)
            self._branch_stack.pop()

    def visit_For(self, node):
        """Extract for loop (may not execute if iterable is empty)."""
        if not self._current_function:
            self.generic_visit(node)
            return

        iter_text = self._get_source_segment(node.iter)
        target_text = self._get_source_segment(node.target)

        for_branch = BranchInfo(
            branch_type='for',
            line=node.lineno,
            end_line=getattr(node, 'end_lineno', node.lineno),
            condition_text=f"for {target_text} in {iter_text}",
            parent_function=self._current_function
        )
        self.branches.append(for_branch)
        self.functions[self._current_function]['branches'].append(for_branch.to_dict())

        self._branch_stack.append(for_branch)
        for child in node.body:
            self.visit(child)
        self._branch_stack.pop()

        # For-else (executed if loop completes without break)
        if node.orelse:
            for_else_branch = BranchInfo(
                branch_type='for_else',
                line=node.orelse[0].lineno,
                end_line=getattr(node, 'end_lineno', node.orelse[0].lineno),
                condition_text=f"for-else (loop completed without break)",
                parent_function=self._current_function
            )
            self.branches.append(for_else_branch)
            self.functions[self._current_function]['branches'].append(for_else_branch.to_dict())

            self._branch_stack.append(for_else_branch)
            for child in node.orelse:
                self.visit(child)
            self._branch_stack.pop()

    def visit_While(self, node):
        """Extract while loop."""
        if not self._current_function:
            self.generic_visit(node)
            return

        condition_text = self._get_source_segment(node.test)

        while_branch = BranchInfo(
            branch_type='while',
            line=node.lineno,
            end_line=getattr(node, 'end_lineno', node.lineno),
            condition_text=f"while {condition_text}",
            parent_function=self._current_function
        )
        self.branches.append(while_branch)
        self.functions[self._current_function]['branches'].append(while_branch.to_dict())

        self._branch_stack.append(while_branch)
        for child in node.body:
            self.visit(child)
        self._branch_stack.pop()

        # While-else
        if node.orelse:
            while_else_branch = BranchInfo(
                branch_type='while_else',
                line=node.orelse[0].lineno,
                end_line=getattr(node, 'end_lineno', node.orelse[0].lineno),
                condition_text=f"while-else (loop completed without break)",
                parent_function=self._current_function
            )
            self.branches.append(while_else_branch)
            self.functions[self._current_function]['branches'].append(while_else_branch.to_dict())

            self._branch_stack.append(while_else_branch)
            for child in node.orelse:
                self.visit(child)
            self._branch_stack.pop()

    def visit_Match(self, node):
        """Extract match/case (Python 3.10+)."""
        if not self._current_function:
            self.generic_visit(node)
            return

        subject_text = self._get_source_segment(node.subject)

        for case in node.cases:
            pattern_text = self._get_source_segment(case.pattern) if hasattr(case, 'pattern') else 'case'
            case_branch = BranchInfo(
                branch_type='case',
                line=case.lineno if hasattr(case, 'lineno') else node.lineno,
                end_line=getattr(case, 'end_lineno', node.lineno),
                condition_text=f"match {subject_text}: case {pattern_text}",
                parent_function=self._current_function
            )
            self.branches.append(case_branch)
            self.functions[self._current_function]['branches'].append(case_branch.to_dict())

            self._branch_stack.append(case_branch)
            for child in case.body:
                self.visit(child)
            self._branch_stack.pop()

    def visit_Call(self, node):
        """Extract function call sites."""
        if not self._current_function:
            self.generic_visit(node)
            return

        # Get the called function name
        callee_name = self._get_call_name(node.func)
        if callee_name:
            # Get current branch context (if any)
            current_branch = self._branch_stack[-1] if self._branch_stack else None

            call_site = CallSiteInfo(
                callee_name=callee_name,
                caller_function=self._current_function,
                line=node.lineno,
                in_branch=current_branch
            )

            self.call_sites.append(call_site)
            self.functions[self._current_function]['calls'].append(call_site.to_dict())

            # Update call graph
            if callee_name not in self.call_graph[self._current_function]:
                self.call_graph[self._current_function].append(callee_name)

            # If inside a branch, track that this call is conditional
            if current_branch:
                current_branch.calls_inside.append(callee_name)

        # Continue visiting arguments
        self.generic_visit(node)

    def _get_call_name(self, node):
        """Extract the name of a called function."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            # Method call like obj.method()
            value = self._get_call_name(node.value)
            if value:
                return f"{value}.{node.attr}"
            return node.attr
        elif isinstance(node, ast.Subscript):
            # Subscript call like items[0]()
            return None
        return None

    def resolve_call(self, raw_callee_name):
        """
        Resolve a raw call name to its actual class.method form.

        Examples:
            self.service.process -> ServiceClass.process (if self.service is ServiceClass)
            helper.do_work -> HelperClass.do_work (if helper is HelperClass)
        """
        parts = raw_callee_name.split('.')

        if len(parts) < 2:
            return raw_callee_name

        # Handle self.attr.method pattern
        if parts[0] == 'self' and self._current_class:
            if len(parts) == 2:
                # self.method() -> CurrentClass.method
                return f"{self._current_class}.{parts[1]}"
            elif len(parts) >= 3:
                # self.attr.method() -> resolve attr's type
                attr_name = parts[1]
                method_name = parts[-1]
                if self._current_class in self.class_attributes:
                    attr_type = self.class_attributes[self._current_class].get(attr_name)
                    if attr_type:
                        return f"{attr_type}.{method_name}"

        # Handle local variable type resolution
        if self._current_function and parts[0] in self.local_types.get(self._current_function, {}):
            var_type = self.local_types[self._current_function][parts[0]]
            method_name = parts[-1]
            return f"{var_type}.{method_name}"

        return raw_callee_name

    def get_resolved_call_graph(self):
        """Return call graph with resolved cross-class references."""
        resolved = {}
        for caller, callees in self.call_graph.items():
            resolved[caller] = []
            for callee in callees:
                # Try to resolve each callee
                resolved_callee = self._resolve_callee(callee, caller)
                if resolved_callee not in resolved[caller]:
                    resolved[caller].append(resolved_callee)
        return resolved

    def _resolve_callee(self, raw_callee, caller_function):
        """Resolve a callee name to its actual class.method form."""
        parts = raw_callee.split('.')

        if len(parts) < 2:
            return raw_callee

        # Determine the class context of the caller
        caller_class = None
        if '.' in caller_function:
            caller_class = caller_function.split('.')[0]

        # Handle self.attr.method pattern
        if parts[0] == 'self' and caller_class:
            if len(parts) == 2:
                # self.method() -> CallerClass.method
                return f"{caller_class}.{parts[1]}"
            elif len(parts) >= 3:
                # self.attr.method() -> resolve attr's type
                attr_name = parts[1]
                method_name = parts[-1]
                if caller_class in self.class_attributes:
                    attr_type = self.class_attributes[caller_class].get(attr_name)
                    if attr_type:
                        return f"{attr_type}.{method_name}"

        # Handle local variable type resolution
        if caller_function in self.local_types and parts[0] in self.local_types[caller_function]:
            var_type = self.local_types[caller_function][parts[0]]
            method_name = parts[-1]
            return f"{var_type}.{method_name}"

        return raw_callee

    def to_dict(self):
        """Export analysis results as dictionary."""
        return {
            'file': self.file_path,
            'functions': self.functions,
            'classes': self.classes,
            'branches': [b.to_dict() for b in self.branches],
            'call_sites': [c.to_dict() for c in self.call_sites],
            'call_graph': self.call_graph,
            'resolved_call_graph': self.get_resolved_call_graph(),
            'class_attributes': self.class_attributes,
            'stats': {
                'total_functions': len(self.functions),
                'total_classes': len(self.classes),
                'total_branches': len(self.branches),
                'total_call_sites': len(self.call_sites)
            }
        }

    def to_json(self, indent=2):
        """Export analysis results as JSON."""
        return json.dumps(self.to_dict(), indent=indent)


class ProjectBranchAnalyzer:
    """Analyzes an entire project for branch coverage."""

    def __init__(self, project_root):
        self.project_root = os.path.abspath(project_root)
        self.files = {}  # {file_path: BranchCoverageAnalyzer}
        self.all_functions = {}  # {full_name: file_path}
        self.all_classes = {}  # {class_name: file_path}
        self.global_call_graph = {}  # {caller: [callees]} across all files
        self.global_resolved_call_graph = {}  # {caller: [callees]} with types resolved
        self.global_class_attributes = {}  # {ClassName: {attr: Type}}

    def scan(self):
        """Scan all Python files in the project."""
        print(f"[ProjectBranchAnalyzer] Scanning: {self.project_root}")

        for root, dirs, files in os.walk(self.project_root):
            # Skip non-source directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in [
                '__pycache__', 'venv', 'env', '.git', '.idea', 'node_modules',
                'build', 'dist', 'eggs', '.eggs', '.tox', '.pytest_cache'
            ]]

            for filename in files:
                if filename.endswith('.py'):
                    filepath = os.path.join(root, filename)
                    self._analyze_file(filepath)

        # First pass: collect all class attributes for cross-file resolution
        for file_path, analyzer in self.files.items():
            for class_name, attrs in analyzer.class_attributes.items():
                if class_name not in self.global_class_attributes:
                    self.global_class_attributes[class_name] = {}
                self.global_class_attributes[class_name].update(attrs)

        # Build global call graph (raw)
        for file_path, analyzer in self.files.items():
            for caller, callees in analyzer.call_graph.items():
                if caller not in self.global_call_graph:
                    self.global_call_graph[caller] = []
                self.global_call_graph[caller].extend(callees)

        # Build resolved call graph with cross-class connections
        self._build_resolved_call_graph()

        print(f"[ProjectBranchAnalyzer] Analyzed {len(self.files)} files, "
              f"{len(self.all_functions)} functions, {len(self.all_classes)} classes, "
              f"{sum(len(a.branches) for a in self.files.values())} branches")

        return self

    def _build_resolved_call_graph(self):
        """Build a resolved call graph using global type information.

        Only includes functions that are defined in the project (in all_functions).
        External library calls are filtered out.
        """
        for caller, callees in self.global_call_graph.items():
            # Only include callers that are in the project
            if caller not in self.all_functions:
                continue

            if caller not in self.global_resolved_call_graph:
                self.global_resolved_call_graph[caller] = []

            for callee in callees:
                resolved = self._resolve_global_callee(callee, caller)
                # Only include callees that are in the project (filter out external libs)
                if resolved in self.all_functions and resolved not in self.global_resolved_call_graph[caller]:
                    self.global_resolved_call_graph[caller].append(resolved)

    def _resolve_global_callee(self, raw_callee, caller_function):
        """Resolve a callee using global type information."""
        parts = raw_callee.split('.')

        if len(parts) < 2:
            # Check if it's a direct function call that exists
            if raw_callee in self.all_functions:
                return raw_callee
            # Could be a constructor call - check classes
            if raw_callee in self.all_classes:
                return f"{raw_callee}.__init__"
            return raw_callee

        # Determine caller's class context
        caller_class = None
        if '.' in caller_function:
            caller_class = caller_function.split('.')[0]

        # Handle self.method() -> CallerClass.method
        if parts[0] == 'self' and caller_class:
            if len(parts) == 2:
                resolved = f"{caller_class}.{parts[1]}"
                if resolved in self.all_functions:
                    return resolved
                return raw_callee

            # Handle self.attr.method() -> resolve attr's type
            if len(parts) >= 3:
                attr_name = parts[1]
                method_name = parts[-1]
                # Check caller class's attributes
                if caller_class in self.global_class_attributes:
                    attr_type = self.global_class_attributes[caller_class].get(attr_name)
                    if attr_type:
                        resolved = f"{attr_type}.{method_name}"
                        if resolved in self.all_functions:
                            return resolved

        # Handle ClassName.method() or module.ClassName.method()
        # Check if any part matches a known class
        for i, part in enumerate(parts[:-1]):
            if part in self.all_classes:
                method_name = parts[-1]
                resolved = f"{part}.{method_name}"
                if resolved in self.all_functions:
                    return resolved

        # Fuzzy match: check if method name matches any known class method
        method_name = parts[-1]
        for func_name in self.all_functions:
            if func_name.endswith(f".{method_name}"):
                # Potential match - but be careful with common names
                return func_name

        return raw_callee

    def _analyze_file(self, filepath):
        """Analyze a single file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                source = f.read()
        except:
            try:
                with open(filepath, 'r') as f:
                    source = f.read()
            except Exception as e:
                print(f"[ProjectBranchAnalyzer] Could not read {filepath}: {e}")
                return

        try:
            analyzer = BranchCoverageAnalyzer(source, filepath)
            analyzer.analyze()
            self.files[filepath] = analyzer

            # Track all functions globally
            for func_name in analyzer.functions:
                self.all_functions[func_name] = filepath

            # Track all classes globally
            for class_name in analyzer.classes:
                self.all_classes[class_name] = filepath

        except Exception as e:
            print(f"[ProjectBranchAnalyzer] Error analyzing {filepath}: {e}")

    def find_callers(self, function_name):
        """Find all places where a function is called from."""
        callers = []
        for file_path, analyzer in self.files.items():
            for call_site in analyzer.call_sites:
                if call_site.callee_name == function_name or call_site.callee_name.endswith(f".{function_name}"):
                    callers.append({
                        'file': file_path,
                        'caller': call_site.caller_function,
                        'line': call_site.line,
                        'in_branch': call_site.in_branch.to_dict() if call_site.in_branch else None
                    })
        return callers

    def analyze_why_not_covered(self, dead_function, covered_functions):
        """
        Analyze why a function wasn't called.

        Args:
            dead_function: The function that wasn't executed
            covered_functions: Set of functions that WERE executed

        Returns:
            Analysis explaining why the function wasn't called
        """
        result = {
            'function': dead_function,
            'status': 'DEAD',
            'reasons': [],
            'root_cause': None
        }

        # Find all call sites for this function
        callers = self.find_callers(dead_function)

        if not callers:
            result['reasons'].append({
                'type': 'NO_CALL_SITES',
                'explanation': f"No code in the project calls {dead_function}. It may be dead code or only called externally."
            })
            result['root_cause'] = 'NO_CALL_SITES'
            return result

        for caller_info in callers:
            caller = caller_info['caller']

            if caller not in covered_functions:
                # The calling function wasn't executed either
                result['reasons'].append({
                    'type': 'CALLER_NOT_EXECUTED',
                    'caller': caller,
                    'file': caller_info['file'],
                    'line': caller_info['line'],
                    'explanation': f"Caller function '{caller}' was not executed"
                })
            elif caller_info['in_branch']:
                # Caller was executed but call is inside a branch
                branch = caller_info['in_branch']
                result['reasons'].append({
                    'type': 'BRANCH_NOT_TAKEN',
                    'caller': caller,
                    'file': caller_info['file'],
                    'line': caller_info['line'],
                    'branch_type': branch['type'],
                    'branch_condition': branch['condition'],
                    'branch_line': branch['line'],
                    'explanation': f"Call is inside a {branch['type']} branch at line {branch['line']} with condition: {branch['condition']}"
                })
            else:
                # Caller was executed and call is unconditional - shouldn't happen for dead function
                result['reasons'].append({
                    'type': 'UNEXPECTED',
                    'caller': caller,
                    'explanation': f"Unexpected: caller '{caller}' was executed with unconditional call"
                })

        # Determine root cause
        branch_reasons = [r for r in result['reasons'] if r['type'] == 'BRANCH_NOT_TAKEN']
        caller_reasons = [r for r in result['reasons'] if r['type'] == 'CALLER_NOT_EXECUTED']

        if branch_reasons:
            result['root_cause'] = 'BRANCH_NOT_TAKEN'
            result['root_cause_detail'] = branch_reasons[0]
        elif caller_reasons:
            result['root_cause'] = 'CALLER_NOT_EXECUTED'
            result['root_cause_detail'] = caller_reasons[0]

        return result

    def find_callers_resolved(self, function_name):
        """Find callers using the resolved call graph."""
        callers = []
        for caller, callees in self.global_resolved_call_graph.items():
            if function_name in callees:
                # Find the file for this caller
                file_path = self.all_functions.get(caller, 'unknown')
                callers.append({
                    'caller': caller,
                    'file': file_path
                })
        return callers

    def to_dict(self):
        """Export full analysis as dictionary."""
        return {
            'project_root': self.project_root,
            'files': {fp: a.to_dict() for fp, a in self.files.items()},
            'all_functions': self.all_functions,
            'all_classes': self.all_classes,
            'global_call_graph': self.global_call_graph,
            'global_resolved_call_graph': self.global_resolved_call_graph,
            'global_class_attributes': self.global_class_attributes,
            'stats': {
                'total_files': len(self.files),
                'total_functions': len(self.all_functions),
                'total_classes': len(self.all_classes),
                'total_branches': sum(len(a.branches) for a in self.files.values()),
                'total_call_sites': sum(len(a.call_sites) for a in self.files.values())
            }
        }

    def to_json(self, indent=2):
        """Export full analysis as JSON."""
        return json.dumps(self.to_dict(), indent=indent, default=str)


def analyze_project(project_root):
    """Convenience function to analyze a project."""
    analyzer = ProjectBranchAnalyzer(project_root)
    analyzer.scan()
    return analyzer


if __name__ == '__main__':
    # Test the analyzer
    if len(sys.argv) > 1:
        project_root = sys.argv[1]
    else:
        project_root = os.getcwd()

    analyzer = analyze_project(project_root)

    print("\n=== Branch Analysis Results ===")
    stats = analyzer.to_dict()['stats']
    print(f"Files: {stats['total_files']}")
    print(f"Functions: {stats['total_functions']}")
    print(f"Branches: {stats['total_branches']}")
    print(f"Call Sites: {stats['total_call_sites']}")

    # Show sample functions with branches
    print("\n=== Sample Functions with Branches ===")
    count = 0
    for file_path, file_analyzer in analyzer.files.items():
        for func_name, func_info in file_analyzer.functions.items():
            if func_info['branches']:
                print(f"\n{func_name} ({os.path.basename(file_path)}:{func_info['line']})")
                for branch in func_info['branches'][:3]:
                    print(f"  - {branch['type']} at line {branch['line']}: {branch['condition'][:50]}...")
                count += 1
                if count >= 5:
                    break
        if count >= 5:
            break
