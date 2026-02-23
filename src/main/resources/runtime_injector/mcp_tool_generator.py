"""
MCP Tool Generator - Generates standalone MCP servers from Python functions.

Given a function's metadata (extracted via ProjectScanner.extract_function_metadata()),
this module generates a complete, standalone MCP server .py file that wraps the function
as an MCP tool callable by any MCP client (Claude Desktop, other TrueFlow projects, etc.).

The generated server has only one dependency: the `mcp` pip package.
No TrueFlow dependency is needed to run a generated server.

Usage:
    from project_scanner import ProjectScanner
    from mcp_tool_generator import MCPToolGenerator

    scanner = ProjectScanner("/path/to/project")
    metadata = scanner.extract_function_metadata("/path/to/file.py", "my_function")
    generator = MCPToolGenerator()
    result = generator.generate(metadata, "/path/to/file.py", "my_function")
    print(result["server_path"])  # ~/.trueflow/generated_mcp_servers/mcp_tool_my_function.py
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path


# Python type annotation -> JSON Schema type mapping
TYPE_MAP = {
    'str': 'string',
    'int': 'integer',
    'float': 'number',
    'bool': 'boolean',
    'list': 'array',
    'List': 'array',
    'tuple': 'array',
    'Tuple': 'array',
    'dict': 'object',
    'Dict': 'object',
    'bytes': 'string',
    'bytearray': 'string',
    'None': 'null',
    'NoneType': 'null',
    'Any': 'string',
}


class MCPToolGenerator(object):
    """Generates standalone MCP server files from function metadata."""

    def __init__(self, output_dir=None):
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path.home() / ".trueflow" / "generated_mcp_servers"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.registry_path = Path.home() / ".trueflow" / "exposed_tools.json"

    def generate(self, metadata, source_file, function_name, strategy="import",
                 tool_name_override=None, project_root=None, server_url=None):
        """Generate a standalone MCP server wrapping the given function.

        Args:
            metadata: dict from ProjectScanner.extract_function_metadata()
            source_file: absolute path to the source file
            function_name: qualified function name (e.g. "ClassName.method")
            strategy: "import" (imports from original module), "embed" (copies source),
                      or "proxy" (HTTP calls to live server via /_trueflow/invoke)
            tool_name_override: custom tool name (defaults to sanitized function name)
            project_root: project root for sys.path insertion (defaults to source file's dir)
            server_url: base URL for proxy strategy (e.g. "http://localhost:8000")

        Returns:
            dict with {tool_name, server_path, input_schema, claude_desktop_config}
        """
        if metadata is None:
            return {"error": "No metadata provided for function: {0}".format(function_name)}

        # Derive tool name
        tool_name = tool_name_override or self._sanitize_tool_name(function_name)

        # Build JSON Schema for input parameters
        input_schema = self._build_input_schema(metadata)

        # Derive module path from source file
        if project_root is None:
            project_root = os.path.dirname(os.path.abspath(source_file))
        module_path = self._derive_module_path(source_file, project_root)

        # Prepare template variables
        is_method = metadata.get('is_method', False)
        is_async = metadata.get('is_async', False)
        bare_name = metadata['name']  # Just the function/method name
        docstring = metadata.get('docstring') or "MCP tool wrapping {0}".format(function_name)
        # Escape triple quotes in docstring
        docstring = docstring.replace('"""', '\\"\\"\\"')

        # Build import and call expressions
        if is_method and '.' in function_name:
            # Class method: import the class, instantiate it
            class_name = function_name.rsplit('.', 1)[0]
            # Handle nested classes: OuterClass.InnerClass -> import OuterClass
            top_class = class_name.split('.')[0]
            import_line = "from {module} import {cls}".format(module=module_path, cls=top_class)
            if '.' in class_name:
                # Nested: OuterClass.InnerClass
                instance_expr = "{cls}()".format(cls=class_name)
            else:
                instance_expr = "{cls}()".format(cls=class_name)
            instance_setup = "_instance = {expr}  # Configure constructor args if needed".format(
                expr=instance_expr)
            call_expr = "_instance.{method}".format(method=bare_name)
        else:
            # Top-level function
            import_line = "from {module} import {func}".format(module=module_path, func=bare_name)
            instance_setup = ""
            call_expr = bare_name

        await_prefix = "await " if is_async else ""

        # Render server code
        if strategy == "proxy":
            resolved_url = server_url or "http://localhost:8000"
            server_code = self._render_proxy_server(
                tool_name=tool_name,
                docstring=docstring,
                input_schema=input_schema,
                function_name=function_name,
                source_file=source_file,
                source_line=metadata.get('source_lines', (0, 0))[0],
                server_url=resolved_url
            )
        elif strategy == "embed":
            server_code = self._render_embedded_server(
                tool_name=tool_name,
                docstring=docstring,
                input_schema=input_schema,
                source_code=metadata.get('source_code', ''),
                call_expr=call_expr,
                await_prefix=await_prefix,
                is_method=is_method,
                function_name=function_name,
                source_file=source_file,
                metadata=metadata
            )
        else:
            server_code = self._render_import_server(
                tool_name=tool_name,
                docstring=docstring,
                input_schema=input_schema,
                import_line=import_line,
                instance_setup=instance_setup,
                call_expr=call_expr,
                await_prefix=await_prefix,
                project_root=project_root,
                function_name=function_name,
                source_file=source_file,
                source_line=metadata.get('source_lines', (0, 0))[0]
            )

        # Write server file
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', tool_name)
        server_filename = "mcp_tool_{0}.py".format(safe_name)
        server_path = str(self.output_dir / server_filename)

        with open(server_path, 'w', encoding='utf-8') as f:
            f.write(server_code)

        # Make executable on Unix
        try:
            os.chmod(server_path, 0o755)
        except Exception:
            pass

        # Build Claude Desktop config snippet
        claude_config = {
            tool_name: {
                "command": "python",
                "args": [server_path]
            }
        }

        result = {
            "tool_name": tool_name,
            "server_path": server_path,
            "input_schema": input_schema,
            "claude_desktop_config": claude_config,
            "strategy": strategy,
            "function_name": function_name,
            "source_file": source_file
        }
        if strategy == "proxy" and server_url:
            result["server_url"] = server_url

        # Save to persistent registry
        self._save_to_registry(result)

        return result

    def list_exposed_tools(self):
        """List all previously generated MCP tools from the registry."""
        registry = self._load_registry()
        return registry.get("tools", {})

    def unexpose_tool(self, tool_name):
        """Remove a tool from the registry and delete its server file."""
        registry = self._load_registry()
        tools = registry.get("tools", {})

        if tool_name not in tools:
            return {"error": "Tool not found: {0}".format(tool_name)}

        tool_info = tools[tool_name]
        server_path = tool_info.get("server_path", "")

        # Delete server file
        if server_path and os.path.exists(server_path):
            os.remove(server_path)

        # Remove from registry
        del tools[tool_name]
        registry["tools"] = tools
        self._save_registry(registry)

        return {"status": "removed", "tool_name": tool_name}

    def generate_openapi_spec(self, functions, server_url="http://localhost:8000"):
        """Generate OpenAPI 3.0 spec for functions exposed via /_trueflow/invoke.

        Works for any language/framework. The spec describes the generic invoke
        endpoint plus per-function documentation.

        Args:
            functions: list of dicts, each with at minimum:
                - function_name: qualified name (e.g. "mymodule.my_func")
                - metadata: dict from extract_function_metadata() (or equivalent)
                  Can also include 'language' (default 'python')
            server_url: base URL of the running server

        Returns:
            dict with {spec_path, spec} where spec is the OpenAPI dict
        """
        func_names = []
        per_function_schemas = {}

        for fn in functions:
            fname = fn.get("function_name", "unknown")
            func_names.append(fname)
            meta = fn.get("metadata")
            if meta:
                schema = self._build_input_schema(meta)
            else:
                schema = {"type": "object", "properties": {}}
            per_function_schemas[fname] = schema

        # Build the combined args schema (oneOf for each function's args)
        args_schemas = []
        for fname, schema in per_function_schemas.items():
            args_schemas.append({
                "type": "object",
                "title": "Args for {0}".format(fname),
                "properties": schema.get("properties", {}),
                "required": schema.get("required", [])
            })

        spec = {
            "openapi": "3.0.3",
            "info": {
                "title": "TrueFlow Exposed Functions",
                "description": "Auto-generated API for functions exposed via TrueFlow runtime instrumentation.",
                "version": "1.0.0",
                "contact": {
                    "name": "TrueFlow",
                    "url": "https://github.com/hevolve-ai/trueflow"
                }
            },
            "servers": [
                {"url": server_url, "description": "Live application server"}
            ],
            "paths": {
                "/_trueflow/invoke": {
                    "post": {
                        "summary": "Invoke an exposed function",
                        "description": "Call any registered function by name with arguments. "
                                       "The function executes in the live server process.",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["function_name"],
                                        "properties": {
                                            "function_name": {
                                                "type": "string",
                                                "enum": func_names,
                                                "description": "Qualified function name to invoke"
                                            },
                                            "args": {
                                                "type": "object",
                                                "description": "Keyword arguments for the function"
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "responses": {
                            "200": {
                                "description": "Function executed successfully",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "result": {
                                                    "description": "Return value of the function"
                                                },
                                                "function": {
                                                    "type": "string",
                                                    "description": "Function that was called"
                                                }
                                            }
                                        }
                                    }
                                }
                            },
                            "400": {"description": "Invalid request (missing function_name)"},
                            "404": {"description": "Function not found in registry"},
                            "500": {"description": "Function execution error"}
                        }
                    }
                },
                "/_trueflow/functions": {
                    "get": {
                        "summary": "List exposed functions",
                        "description": "Returns all functions registered in the callable registry.",
                        "responses": {
                            "200": {
                                "description": "List of callable functions",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "functions": {
                                                    "type": "array",
                                                    "items": {"type": "string"}
                                                },
                                                "count": {"type": "integer"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "/_trueflow/openapi.json": {
                    "get": {
                        "summary": "Get this OpenAPI spec",
                        "description": "Returns the auto-generated OpenAPI specification.",
                        "responses": {
                            "200": {
                                "description": "OpenAPI 3.0 specification",
                                "content": {
                                    "application/json": {
                                        "schema": {"type": "object"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        # Add per-function documentation as x-trueflow-functions extension
        spec["x-trueflow-functions"] = {}
        for fn in functions:
            fname = fn.get("function_name", "unknown")
            meta = fn.get("metadata", {})
            lang = fn.get("language", "python")
            spec["x-trueflow-functions"][fname] = {
                "language": lang,
                "is_async": meta.get("is_async", False),
                "is_method": meta.get("is_method", False),
                "docstring": meta.get("docstring", ""),
                "parameters": per_function_schemas.get(fname, {}),
                "return_type": meta.get("return_annotation", ""),
                "source_file": fn.get("source_file", ""),
            }

        # Save spec file
        spec_path = str(self.output_dir / "openapi_spec.json")
        with open(spec_path, 'w', encoding='utf-8') as f:
            json.dump(spec, f, indent=2, default=str)

        return {"spec_path": spec_path, "spec": spec}

    def generate_mcp_client(self, tool_name, server_path=None):
        """Generate a standalone MCP client script for calling a generated MCP server.

        The client communicates via JSON-RPC over stdio with the MCP server subprocess.
        Works with any MCP server (import, embed, or proxy strategy).

        Args:
            tool_name: name of the tool to call
            server_path: path to the MCP server .py file (if None, looks up in registry)

        Returns:
            dict with {client_path, tool_name}
        """
        if server_path is None:
            # Look up from registry
            registry = self._load_registry()
            tools = registry.get("tools", {})
            if tool_name not in tools:
                return {"error": "Tool not found in registry: {0}".format(tool_name)}
            server_path = tools[tool_name]["server_path"]

        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', tool_name)
        client_filename = "mcp_client_{0}.py".format(safe_name)
        client_path = str(self.output_dir / client_filename)

        client_code = '''#!/usr/bin/env python3
"""
Auto-generated MCP client for tool: {tool_name}
Generated by TrueFlow on {timestamp}

Usage as CLI:
    python {client_filename} --arg1 value1 --arg2 value2

Usage as library:
    from {module_name} import call_{safe_name}
    import asyncio
    result = asyncio.run(call_{safe_name}(arg1="value1"))
"""
import asyncio
import json
import subprocess
import sys


SERVER_PATH = {server_path_repr}
TOOL_NAME = "{tool_name}"


class MCPClient(object):
    """Minimal MCP client that communicates via JSON-RPC over stdio."""

    def __init__(self, server_command):
        self.server_command = server_command
        self.process = None
        self._request_id = 0

    async def start(self):
        """Start the MCP server subprocess."""
        self.process = await asyncio.create_subprocess_exec(
            *self.server_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

    async def _send_request(self, method, params=None):
        """Send a JSON-RPC request and read the response."""
        self._request_id += 1
        request = {{
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
        }}
        if params is not None:
            request["params"] = params

        line = json.dumps(request) + "\\n"
        self.process.stdin.write(line.encode("utf-8"))
        await self.process.stdin.drain()

        # Read response line
        resp_line = await asyncio.wait_for(
            self.process.stdout.readline(), timeout=60.0
        )
        if not resp_line:
            raise RuntimeError("Server closed connection")
        return json.loads(resp_line.decode("utf-8"))

    async def initialize(self):
        """Send MCP initialize handshake."""
        resp = await self._send_request("initialize", {{
            "protocolVersion": "2024-11-05",
            "capabilities": {{}},
            "clientInfo": {{"name": "trueflow-client", "version": "1.0.0"}}
        }})
        # Send initialized notification
        notif = json.dumps({{"jsonrpc": "2.0", "method": "notifications/initialized"}}) + "\\n"
        self.process.stdin.write(notif.encode("utf-8"))
        await self.process.stdin.drain()
        return resp

    async def call_tool(self, name, arguments):
        """Call a tool on the MCP server."""
        resp = await self._send_request("tools/call", {{
            "name": name,
            "arguments": arguments
        }})
        if "error" in resp:
            raise RuntimeError("MCP error: {{0}}".format(resp["error"]))
        result = resp.get("result", {{}})
        content = result.get("content", [])
        if content and len(content) > 0:
            return content[0].get("text", "")
        return json.dumps(result)

    async def close(self):
        """Terminate the server subprocess."""
        if self.process:
            self.process.stdin.close()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()


async def call_{safe_name}(**kwargs):
    """Call the {tool_name} tool with the given arguments.

    Returns the result as a string.
    """
    client = MCPClient([sys.executable, SERVER_PATH])
    try:
        await client.start()
        await client.initialize()
        result = await client.call_tool(TOOL_NAME, kwargs)
        return result
    finally:
        await client.close()


async def _main():
    import argparse
    parser = argparse.ArgumentParser(
        description="MCP client for {tool_name}"
    )
    parser.add_argument("--json", type=str, help="JSON string of arguments")
    # Also accept any --key=value pairs
    args, unknown = parser.parse_known_args()

    kwargs = {{}}
    if args.json:
        kwargs = json.loads(args.json)
    else:
        # Parse --key=value or --key value pairs from unknown args
        i = 0
        while i < len(unknown):
            arg = unknown[i]
            if arg.startswith("--"):
                key = arg[2:].replace("-", "_")
                if "=" in key:
                    k, v = key.split("=", 1)
                    kwargs[k] = v
                elif i + 1 < len(unknown) and not unknown[i + 1].startswith("--"):
                    kwargs[key] = unknown[i + 1]
                    i += 1
                else:
                    kwargs[key] = True
            i += 1

    result = await call_{safe_name}(**kwargs)
    print(result)


if __name__ == "__main__":
    asyncio.run(_main())
'''.format(
            tool_name=tool_name,
            safe_name=safe_name,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            client_filename=client_filename,
            module_name="mcp_client_{0}".format(safe_name),
            server_path_repr=repr(str(server_path))
        )

        with open(client_path, 'w', encoding='utf-8') as f:
            f.write(client_code)

        try:
            os.chmod(client_path, 0o755)
        except Exception:
            pass

        return {"client_path": client_path, "tool_name": tool_name}

    def _build_input_schema(self, metadata):
        """Build JSON Schema from AST-extracted parameter metadata."""
        properties = {}
        required = []

        for param in metadata.get('parameters', []):
            name = param['name']

            # Skip self/cls for methods
            if name in ('self', 'cls'):
                continue

            # Skip *args/**kwargs for now (handle specially)
            if name.startswith('*'):
                continue

            prop = {}
            annotation = param.get('annotation')

            if annotation:
                json_type = self._python_type_to_json(annotation)
                prop.update(json_type)
            else:
                prop['type'] = 'string'  # Default fallback

            if param.get('has_default') and param.get('default') is not None:
                # Try to parse default as a Python literal
                default_str = param['default']
                try:
                    import ast as _ast
                    default_val = _ast.literal_eval(default_str)
                    prop['default'] = default_val
                except Exception:
                    prop['default'] = default_str
            elif not param.get('has_default'):
                required.append(name)

            properties[name] = prop

        schema = {
            'type': 'object',
            'properties': properties,
        }
        if required:
            schema['required'] = required

        return schema

    def _python_type_to_json(self, annotation):
        """Convert a Python type annotation string to a JSON Schema type spec."""
        if annotation is None:
            return {'type': 'string'}

        ann = annotation.strip()

        # Direct type mapping
        if ann in TYPE_MAP:
            return {'type': TYPE_MAP[ann]}

        # Optional[X] -> type of X, without required
        if ann.startswith('Optional[') and ann.endswith(']'):
            inner = ann[9:-1]
            inner_type = self._python_type_to_json(inner)
            return inner_type

        # List[X] or list[X]
        if (ann.startswith('List[') or ann.startswith('list[')) and ann.endswith(']'):
            inner = ann[ann.index('[') + 1:-1]
            return {'type': 'array', 'items': self._python_type_to_json(inner)}

        # Dict[K, V] or dict[K, V]
        if (ann.startswith('Dict[') or ann.startswith('dict[')) and ann.endswith(']'):
            return {'type': 'object'}

        # Union[X, Y] -> just use first non-None type
        if ann.startswith('Union[') and ann.endswith(']'):
            inner = ann[6:-1]
            parts = [p.strip() for p in inner.split(',')]
            for part in parts:
                if part != 'None' and part != 'NoneType':
                    return self._python_type_to_json(part)
            return {'type': 'string'}

        # X | Y (Python 3.10+ union syntax)
        if ' | ' in ann:
            parts = [p.strip() for p in ann.split('|')]
            for part in parts:
                if part != 'None' and part != 'NoneType':
                    return self._python_type_to_json(part)
            return {'type': 'string'}

        # Fallback: treat as string with description
        return {'type': 'string', 'description': 'Python type: {0}'.format(ann)}

    def _render_import_server(self, tool_name, docstring, input_schema, import_line,
                              instance_setup, call_expr, await_prefix, project_root,
                              function_name, source_file, source_line):
        """Render an import-based MCP server (imports function from original module)."""
        schema_str = json.dumps(input_schema, indent=12)

        instance_line = ""
        if instance_setup:
            instance_line = "\n{0}\n".format(instance_setup)

        return '''#!/usr/bin/env python3
"""
Auto-generated MCP server wrapping: {function_name}
Source: {source_file}:{source_line}
Generated by TrueFlow on {timestamp}

Usage:
    python {server_filename}

Add to Claude Desktop (claude_desktop_config.json):
    "mcpServers": {{
        "{tool_name}": {{
            "command": "python",
            "args": ["{server_path}"]
        }}
    }}
"""
import asyncio
import json
import sys
from pathlib import Path

# Add project root to path so we can import the original function
sys.path.insert(0, {project_root_repr})

# MCP SDK (install with: pip install mcp)
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("MCP SDK not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

# Import the original function
{import_line}
{instance_line}
server = Server("{tool_name}")


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="{tool_name}",
            description="""{docstring}""",
            inputSchema={schema_str}
        )
    ]


@server.call_tool()
async def call_tool(name, arguments):
    if name != "{tool_name}":
        return [TextContent(type="text", text="Unknown tool: " + name)]

    try:
        result = {await_prefix}{call_expr}(**arguments)
        return [TextContent(type="text", text=json.dumps(result, default=str))]
    except Exception as e:
        return [TextContent(type="text", text="Error: " + str(e))]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
'''.format(
            function_name=function_name,
            source_file=source_file,
            source_line=source_line,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            server_filename="mcp_tool_{0}.py".format(re.sub(r'[^a-zA-Z0-9_]', '_', tool_name)),
            server_path=str(self.output_dir / "mcp_tool_{0}.py".format(
                re.sub(r'[^a-zA-Z0-9_]', '_', tool_name))),
            tool_name=tool_name,
            project_root_repr=repr(str(project_root)),
            import_line=import_line,
            instance_line=instance_line,
            docstring=docstring,
            schema_str=schema_str,
            await_prefix=await_prefix,
            call_expr=call_expr
        )

    def _render_embedded_server(self, tool_name, docstring, input_schema, source_code,
                                call_expr, await_prefix, is_method, function_name,
                                source_file, metadata):
        """Render an embedded MCP server (copies function source into the file)."""
        schema_str = json.dumps(input_schema, indent=12)
        source_line = metadata.get('source_lines', (0, 0))[0]

        return '''#!/usr/bin/env python3
"""
Auto-generated MCP server (embedded) wrapping: {function_name}
Source: {source_file}:{source_line}
Generated by TrueFlow on {timestamp}

This server contains a copy of the function source. Changes to the original
function will NOT be reflected here. Re-generate to update.
"""
import asyncio
import json
import sys

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("MCP SDK not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)


# === Embedded function source ===
{source_code}


server = Server("{tool_name}")


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="{tool_name}",
            description="""{docstring}""",
            inputSchema={schema_str}
        )
    ]


@server.call_tool()
async def call_tool(name, arguments):
    if name != "{tool_name}":
        return [TextContent(type="text", text="Unknown tool: " + name)]

    try:
        result = {await_prefix}{call_expr}(**arguments)
        return [TextContent(type="text", text=json.dumps(result, default=str))]
    except Exception as e:
        return [TextContent(type="text", text="Error: " + str(e))]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
'''.format(
            function_name=function_name,
            source_file=source_file,
            source_line=source_line,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            tool_name=tool_name,
            source_code=source_code,
            docstring=docstring,
            schema_str=schema_str,
            await_prefix=await_prefix,
            call_expr=call_expr
        )

    def _render_proxy_server(self, tool_name, docstring, input_schema,
                              function_name, source_file, source_line, server_url):
        """Render a proxy MCP server that calls the live app via /_trueflow/invoke.

        This strategy works with ANY language/framework that has the TrueFlow
        endpoint injected. The generated MCP server is always Python (MCP SDK),
        but the target server can be Python, Java, Node.js, etc.
        """
        schema_str = json.dumps(input_schema, indent=12)

        return '''#!/usr/bin/env python3
"""
Auto-generated MCP server (proxy) wrapping: {function_name}
Source: {source_file}:{source_line}
Generated by TrueFlow on {timestamp}

Strategy: PROXY - calls the live running server via /_trueflow/invoke.
The target function runs in its original process with full runtime context
(DB connections, auth state, caches, etc.).

Target server: {server_url}

Usage:
    python {server_filename}

Add to Claude Desktop (claude_desktop_config.json):
    "mcpServers": {{
        "{tool_name}": {{
            "command": "python",
            "args": ["{server_path}"]
        }}
    }}
"""
import asyncio
import json
import sys

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("MCP SDK not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

SERVER_URL = "{server_url}"
FUNCTION_NAME = "{function_name}"

server = Server("{tool_name}")


async def _invoke_remote(function_name, arguments):
    """Call the live server via /_trueflow/invoke endpoint."""
    url = SERVER_URL.rstrip("/") + "/_trueflow/invoke"
    payload = json.dumps({{"function_name": function_name, "args": arguments}})
    payload_bytes = payload.encode("utf-8")

    # Try httpx first (async, better), fall back to urllib (stdlib)
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                content=payload_bytes,
                headers={{"Content-Type": "application/json"}}
            )
            resp.raise_for_status()
            return resp.text
    except ImportError:
        pass

    # Fallback: urllib.request (sync, but works without extra deps)
    import urllib.request
    req = urllib.request.Request(
        url,
        data=payload_bytes,
        headers={{"Content-Type": "application/json"}},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return json.dumps({{"error": "HTTP {{0}}: {{1}}".format(e.code, body)}})
    except urllib.error.URLError as e:
        return json.dumps({{"error": "Server unreachable: {{0}}".format(str(e.reason))}})


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="{tool_name}",
            description="""{docstring}""",
            inputSchema={schema_str}
        )
    ]


@server.call_tool()
async def call_tool(name, arguments):
    if name != "{tool_name}":
        return [TextContent(type="text", text="Unknown tool: " + name)]

    try:
        result_text = await _invoke_remote(FUNCTION_NAME, arguments)
        return [TextContent(type="text", text=result_text)]
    except Exception as e:
        return [TextContent(type="text", text="Proxy error: " + str(e))]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
'''.format(
            function_name=function_name,
            source_file=source_file,
            source_line=source_line,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            server_filename="mcp_tool_{0}.py".format(re.sub(r'[^a-zA-Z0-9_]', '_', tool_name)),
            server_path=str(self.output_dir / "mcp_tool_{0}.py".format(
                re.sub(r'[^a-zA-Z0-9_]', '_', tool_name))),
            tool_name=tool_name,
            server_url=server_url,
            docstring=docstring,
            schema_str=schema_str
        )

    def _derive_module_path(self, source_file, project_root):
        """Derive Python module path from file path relative to project root.

        e.g. /project/myapp/utils.py -> myapp.utils
        """
        abs_file = os.path.abspath(source_file)
        abs_root = os.path.abspath(project_root)

        # Get relative path
        try:
            rel = os.path.relpath(abs_file, abs_root)
        except ValueError:
            # Different drives on Windows
            return os.path.splitext(os.path.basename(source_file))[0]

        # Convert path separators and remove .py
        module = rel.replace(os.sep, '.').replace('/', '.')
        if module.endswith('.py'):
            module = module[:-3]

        # Remove __init__ suffix
        if module.endswith('.__init__'):
            module = module[:-9]

        return module

    @staticmethod
    def _sanitize_tool_name(function_name):
        """Create a safe MCP tool name from a function name."""
        # Replace dots with underscores, strip special chars
        name = re.sub(r'[^a-zA-Z0-9_]', '_', function_name)
        # Ensure it starts with a letter
        if name and not name[0].isalpha():
            name = 'tool_' + name
        return name.lower()

    def _load_registry(self):
        """Load the persistent tool registry."""
        if self.registry_path.exists():
            try:
                with open(str(self.registry_path), 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"tools": {}}

    def _save_registry(self, registry):
        """Save the persistent tool registry."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(self.registry_path), 'w', encoding='utf-8') as f:
            json.dump(registry, f, indent=2, default=str)

    def _save_to_registry(self, result):
        """Save a generated tool to the persistent registry."""
        registry = self._load_registry()
        tools = registry.get("tools", {})

        entry = {
            "server_path": result["server_path"],
            "source_file": result["source_file"],
            "function_name": result["function_name"],
            "strategy": result["strategy"],
            "generated_at": datetime.now().isoformat(),
            "input_schema": result["input_schema"]
        }
        if result.get("server_url"):
            entry["server_url"] = result["server_url"]
        tools[result["tool_name"]] = entry

        registry["tools"] = tools
        self._save_registry(registry)


if __name__ == '__main__':
    # Quick test: generate a tool from a function in this file
    import argparse
    parser = argparse.ArgumentParser(description='Generate MCP server from a Python function')
    parser.add_argument('file', help='Python source file')
    parser.add_argument('function', help='Function name (e.g. my_func or MyClass.method)')
    parser.add_argument('--strategy', choices=['import', 'embed', 'proxy'], default='import')
    parser.add_argument('--project-root', help='Project root directory')
    parser.add_argument('--output-dir', help='Output directory for generated servers')
    parser.add_argument('--tool-name', help='Custom tool name')
    parser.add_argument('--server-url', help='Target server URL for proxy strategy (e.g. http://localhost:8000)')
    args = parser.parse_args()

    from project_scanner import ProjectScanner

    scanner = ProjectScanner(args.project_root or os.path.dirname(args.file))
    metadata = scanner.extract_function_metadata(args.file, args.function)

    if metadata is None:
        print("Error: Function '{0}' not found in {1}".format(args.function, args.file))
        sys.exit(1)

    generator = MCPToolGenerator(output_dir=args.output_dir)
    result = generator.generate(
        metadata, args.file, args.function,
        strategy=args.strategy,
        tool_name_override=args.tool_name,
        project_root=args.project_root,
        server_url=args.server_url
    )

    if "error" in result:
        print("Error: {0}".format(result["error"]))
        sys.exit(1)

    print("MCP Tool Generated:")
    print("  Tool name: {0}".format(result["tool_name"]))
    print("  Server: {0}".format(result["server_path"]))
    print("  Schema: {0}".format(json.dumps(result["input_schema"], indent=2)))
    print("\nClaude Desktop config:")
    print(json.dumps(result["claude_desktop_config"], indent=2))
