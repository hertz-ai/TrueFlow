#!/usr/bin/env python3
"""
MCP Discovery Protocol - Universal discovery for MCP servers, tools, skills, and datasources.

This implements a lightweight discovery protocol that allows:
1. MCP servers to advertise their capabilities
2. Clients to discover available services dynamically
3. Aggregation of multiple MCP servers into a unified interface

Discovery Methods:
- File-based: ~/.mcp/registry.json (local machine registry)
- UDP broadcast: Port 5353 (mDNS-style local network discovery)
- HTTP: /.well-known/mcp (per-server capability endpoint)
- Process scan: Find running MCP servers by known patterns

Protocol:
- Services register with: name, type, transport, capabilities, endpoint
- Clients query by: type, capability, name pattern
- Heartbeat keeps registry fresh (services must re-register periodically)

Usage:
    # As a discovery server (meta-MCP)
    python mcp_discovery_protocol.py serve

    # Register a service
    python mcp_discovery_protocol.py register --name "my-mcp" --type mcp_server --endpoint "stdio:my-mcp"

    # Query services
    python mcp_discovery_protocol.py query --type mcp_server

    # As MCP server exposing all discovered services
    python mcp_discovery_protocol.py mcp-gateway
"""

import asyncio
import json
import logging
import os
import socket
import struct
import sys
import time
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from enum import Enum
import threading

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("mcp-discovery")


# =============================================================================
# PROTOCOL DEFINITIONS
# =============================================================================

class ServiceType(str, Enum):
    """Types of discoverable services."""
    MCP_SERVER = "mcp_server"       # Full MCP server with tools/resources
    TOOL = "tool"                   # Individual tool/function
    SKILL = "skill"                 # Claude Code skill
    DATASOURCE = "datasource"       # Database, API, file source
    RESOURCE = "resource"           # MCP resource provider
    GATEWAY = "gateway"             # Aggregator/proxy service


class TransportType(str, Enum):
    """How to connect to the service."""
    STDIO = "stdio"                 # Standard input/output (subprocess)
    HTTP = "http"                   # HTTP/REST endpoint
    SSE = "sse"                     # Server-Sent Events
    WEBSOCKET = "websocket"         # WebSocket connection
    GRPC = "grpc"                   # gRPC
    UNIX_SOCKET = "unix_socket"     # Unix domain socket
    TCP = "tcp"                     # Raw TCP socket


@dataclass
class ServiceCapability:
    """A capability offered by a service."""
    name: str                       # Capability name (e.g., "code_analysis")
    description: str                # Human-readable description
    input_schema: Optional[Dict] = None   # JSON Schema for input
    output_schema: Optional[Dict] = None  # JSON Schema for output
    tags: List[str] = field(default_factory=list)  # Searchable tags


@dataclass
class ServiceEndpoint:
    """Connection endpoint for a service."""
    transport: TransportType
    address: str                    # Command (stdio), URL (http), path (socket)
    port: Optional[int] = None
    auth_required: bool = False
    auth_type: Optional[str] = None  # "bearer", "api_key", "oauth2"


@dataclass
class DiscoverableService:
    """A service that can be discovered."""
    id: str                         # Unique identifier (generated from name+endpoint)
    name: str                       # Human-readable name
    type: ServiceType
    endpoint: ServiceEndpoint
    version: str = "1.0.0"
    description: str = ""
    capabilities: List[ServiceCapability] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)      # Tool names for MCP servers
    resources: List[str] = field(default_factory=list)  # Resource URIs for MCP servers
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Registry metadata
    registered_at: str = ""
    last_seen: str = ""
    heartbeat_interval_sec: int = 60
    ttl_sec: int = 300              # Time-to-live before considered stale

    def __post_init__(self):
        if not self.id:
            # Generate ID from name and endpoint
            key = f"{self.name}:{self.endpoint.transport}:{self.endpoint.address}"
            self.id = hashlib.sha256(key.encode()).hexdigest()[:16]
        if not self.registered_at:
            self.registered_at = datetime.utcnow().isoformat()
        if not self.last_seen:
            self.last_seen = self.registered_at

    def is_alive(self) -> bool:
        """Check if service is still considered alive based on TTL."""
        last = datetime.fromisoformat(self.last_seen)
        return datetime.utcnow() - last < timedelta(seconds=self.ttl_sec)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        d['type'] = self.type.value
        d['endpoint']['transport'] = self.endpoint.transport.value
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> 'DiscoverableService':
        """Create from dictionary."""
        d['type'] = ServiceType(d['type'])
        d['endpoint'] = ServiceEndpoint(
            transport=TransportType(d['endpoint']['transport']),
            address=d['endpoint']['address'],
            port=d['endpoint'].get('port'),
            auth_required=d['endpoint'].get('auth_required', False),
            auth_type=d['endpoint'].get('auth_type')
        )
        d['capabilities'] = [ServiceCapability(**c) for c in d.get('capabilities', [])]
        return cls(**d)


# =============================================================================
# REGISTRY - Local file-based service registry
# =============================================================================

class ServiceRegistry:
    """
    File-based service registry.

    Stores discovered services in ~/.mcp/registry.json
    Supports:
    - Registration with TTL
    - Query by type, capability, tags
    - Automatic cleanup of stale services
    """

    DEFAULT_PATH = Path.home() / ".mcp" / "registry.json"

    def __init__(self, registry_path: Path = None):
        self.path = registry_path or self.DEFAULT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.services: Dict[str, DiscoverableService] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        """Load registry from disk."""
        if self.path.exists():
            try:
                with open(self.path, 'r') as f:
                    data = json.load(f)
                for sid, sdata in data.get('services', {}).items():
                    try:
                        self.services[sid] = DiscoverableService.from_dict(sdata)
                    except Exception as e:
                        logger.warning(f"Failed to load service {sid}: {e}")
            except Exception as e:
                logger.error(f"Failed to load registry: {e}")

    def _save(self):
        """Save registry to disk."""
        with self._lock:
            data = {
                'version': '1.0.0',
                'updated_at': datetime.utcnow().isoformat(),
                'services': {sid: s.to_dict() for sid, s in self.services.items()}
            }
            with open(self.path, 'w') as f:
                json.dump(data, f, indent=2)

    def register(self, service: DiscoverableService) -> str:
        """Register or update a service. Returns service ID."""
        with self._lock:
            service.last_seen = datetime.utcnow().isoformat()
            self.services[service.id] = service
        self._save()
        logger.info(f"Registered service: {service.name} ({service.id})")
        return service.id

    def unregister(self, service_id: str) -> bool:
        """Unregister a service. Returns True if found and removed."""
        with self._lock:
            if service_id in self.services:
                del self.services[service_id]
                self._save()
                logger.info(f"Unregistered service: {service_id}")
                return True
        return False

    def heartbeat(self, service_id: str) -> bool:
        """Update last_seen for a service. Returns True if found."""
        with self._lock:
            if service_id in self.services:
                self.services[service_id].last_seen = datetime.utcnow().isoformat()
                self._save()
                return True
        return False

    def get(self, service_id: str) -> Optional[DiscoverableService]:
        """Get a specific service by ID."""
        return self.services.get(service_id)

    def query(
        self,
        service_type: Optional[ServiceType] = None,
        capability: Optional[str] = None,
        tag: Optional[str] = None,
        name_pattern: Optional[str] = None,
        include_stale: bool = False
    ) -> List[DiscoverableService]:
        """
        Query services with filters.

        Args:
            service_type: Filter by service type
            capability: Filter by capability name (partial match)
            tag: Filter by tag
            name_pattern: Filter by name (partial match)
            include_stale: Include services past their TTL

        Returns:
            List of matching services
        """
        results = []

        for service in self.services.values():
            # Check TTL
            if not include_stale and not service.is_alive():
                continue

            # Apply filters
            if service_type and service.type != service_type:
                continue

            if capability:
                cap_match = any(
                    capability.lower() in c.name.lower()
                    for c in service.capabilities
                )
                if not cap_match:
                    continue

            if tag and tag not in service.tags:
                continue

            if name_pattern and name_pattern.lower() not in service.name.lower():
                continue

            results.append(service)

        return results

    def cleanup_stale(self) -> int:
        """Remove stale services. Returns count of removed services."""
        with self._lock:
            stale_ids = [
                sid for sid, s in self.services.items()
                if not s.is_alive()
            ]
            for sid in stale_ids:
                del self.services[sid]
            if stale_ids:
                self._save()
                logger.info(f"Cleaned up {len(stale_ids)} stale services")
        return len(stale_ids)

    def get_all(self, include_stale: bool = False) -> List[DiscoverableService]:
        """Get all registered services."""
        if include_stale:
            return list(self.services.values())
        return [s for s in self.services.values() if s.is_alive()]


# =============================================================================
# DISCOVERY METHODS
# =============================================================================

class MCPConfigDiscovery:
    """
    Discover MCP servers from Claude Desktop and other config files.

    Reads from:
    - ~/.config/claude/claude_desktop_config.json (Linux)
    - ~/Library/Application Support/Claude/claude_desktop_config.json (macOS)
    - %APPDATA%/Claude/claude_desktop_config.json (Windows)
    """

    @staticmethod
    def get_config_paths() -> List[Path]:
        """Get possible config file locations."""
        paths = []

        # Claude Desktop config
        if sys.platform == 'win32':
            appdata = os.environ.get('APPDATA', '')
            if appdata:
                paths.append(Path(appdata) / 'Claude' / 'claude_desktop_config.json')
        elif sys.platform == 'darwin':
            paths.append(Path.home() / 'Library' / 'Application Support' / 'Claude' / 'claude_desktop_config.json')
        else:
            paths.append(Path.home() / '.config' / 'claude' / 'claude_desktop_config.json')

        # Also check common MCP config locations
        paths.append(Path.home() / '.mcp' / 'config.json')
        paths.append(Path.home() / '.config' / 'mcp' / 'config.json')

        return paths

    @classmethod
    def discover(cls) -> List[DiscoverableService]:
        """Discover MCP servers from config files."""
        services = []

        for config_path in cls.get_config_paths():
            if not config_path.exists():
                continue

            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)

                # Claude Desktop format
                mcp_servers = config.get('mcpServers', {})
                for name, server_config in mcp_servers.items():
                    service = cls._parse_mcp_server(name, server_config, str(config_path))
                    if service:
                        services.append(service)

                logger.info(f"Discovered {len(mcp_servers)} servers from {config_path}")

            except Exception as e:
                logger.warning(f"Failed to read {config_path}: {e}")

        return services

    @staticmethod
    def _parse_mcp_server(name: str, config: Dict, source: str) -> Optional[DiscoverableService]:
        """Parse MCP server config into DiscoverableService."""
        try:
            command = config.get('command', '')
            args = config.get('args', [])
            env = config.get('env', {})

            # Determine transport
            if command:
                transport = TransportType.STDIO
                address = f"{command} {' '.join(args)}"
            else:
                # Might be HTTP or other transport
                url = config.get('url', config.get('endpoint', ''))
                if url.startswith('http'):
                    transport = TransportType.HTTP
                    address = url
                else:
                    return None

            return DiscoverableService(
                id="",  # Will be generated
                name=name,
                type=ServiceType.MCP_SERVER,
                endpoint=ServiceEndpoint(
                    transport=transport,
                    address=address
                ),
                description=config.get('description', f"MCP server from {source}"),
                metadata={
                    'source': source,
                    'env': env,
                    'original_config': config
                }
            )
        except Exception as e:
            logger.warning(f"Failed to parse MCP server {name}: {e}")
            return None


class UDPDiscovery:
    """
    UDP broadcast-based discovery (mDNS-style).

    Services broadcast their presence on a multicast group.
    Clients listen for announcements.
    """

    MULTICAST_GROUP = '224.0.0.251'  # mDNS multicast
    DISCOVERY_PORT = 5353
    MAGIC_HEADER = b'MCPDISCO'

    def __init__(self):
        self.sock = None
        self._running = False

    def create_announcement(self, service: DiscoverableService) -> bytes:
        """Create announcement packet for a service."""
        data = {
            'magic': 'MCPDISCO',
            'version': 1,
            'action': 'announce',
            'service': service.to_dict()
        }
        return self.MAGIC_HEADER + json.dumps(data).encode('utf-8')

    def parse_announcement(self, data: bytes) -> Optional[DiscoverableService]:
        """Parse announcement packet."""
        if not data.startswith(self.MAGIC_HEADER):
            return None
        try:
            payload = json.loads(data[len(self.MAGIC_HEADER):].decode('utf-8'))
            if payload.get('magic') == 'MCPDISCO' and payload.get('action') == 'announce':
                return DiscoverableService.from_dict(payload['service'])
        except Exception as e:
            logger.debug(f"Failed to parse announcement: {e}")
        return None

    async def announce(self, service: DiscoverableService, interval: int = 30):
        """Periodically announce a service via UDP broadcast."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

        packet = self.create_announcement(service)

        self._running = True
        while self._running:
            try:
                sock.sendto(packet, (self.MULTICAST_GROUP, self.DISCOVERY_PORT))
                logger.debug(f"Announced service: {service.name}")
            except Exception as e:
                logger.error(f"Announce error: {e}")
            await asyncio.sleep(interval)

        sock.close()

    async def listen(self, callback, timeout: float = None):
        """
        Listen for service announcements.

        Args:
            callback: Function called with each discovered DiscoverableService
            timeout: Stop listening after this many seconds (None = forever)
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', self.DISCOVERY_PORT))

        # Join multicast group
        mreq = struct.pack('4sl', socket.inet_aton(self.MULTICAST_GROUP), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.setblocking(False)

        self._running = True
        start = time.time()

        while self._running:
            if timeout and time.time() - start > timeout:
                break

            try:
                data, addr = sock.recvfrom(65535)
                service = self.parse_announcement(data)
                if service:
                    logger.info(f"Discovered via UDP: {service.name} from {addr}")
                    await callback(service)
            except BlockingIOError:
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Listen error: {e}")
                await asyncio.sleep(1)

        sock.close()

    def stop(self):
        """Stop announcing or listening."""
        self._running = False


class HTTPProbe:
    """
    Probe HTTP endpoints for MCP capability.

    Checks /.well-known/mcp for service metadata.
    """

    WELL_KNOWN_PATH = '/.well-known/mcp'

    @classmethod
    async def probe(cls, base_url: str) -> Optional[DiscoverableService]:
        """
        Probe an HTTP endpoint for MCP capability.

        Args:
            base_url: Base URL to probe (e.g., http://localhost:8080)

        Returns:
            DiscoverableService if MCP-capable, None otherwise
        """
        import urllib.request
        import urllib.error

        url = base_url.rstrip('/') + cls.WELL_KNOWN_PATH

        try:
            req = urllib.request.Request(url, method='GET')
            req.add_header('Accept', 'application/json')

            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode('utf-8'))
                    return cls._parse_well_known(data, base_url)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                logger.debug(f"HTTP probe error for {url}: {e}")
        except Exception as e:
            logger.debug(f"Probe failed for {url}: {e}")

        return None

    @staticmethod
    def _parse_well_known(data: Dict, base_url: str) -> Optional[DiscoverableService]:
        """Parse /.well-known/mcp response."""
        try:
            return DiscoverableService(
                id="",
                name=data.get('name', 'Unknown MCP Server'),
                type=ServiceType.MCP_SERVER,
                endpoint=ServiceEndpoint(
                    transport=TransportType.HTTP,
                    address=base_url
                ),
                version=data.get('version', '1.0.0'),
                description=data.get('description', ''),
                tools=data.get('tools', []),
                resources=data.get('resources', []),
                capabilities=[
                    ServiceCapability(name=c['name'], description=c.get('description', ''))
                    for c in data.get('capabilities', [])
                ],
                tags=data.get('tags', [])
            )
        except Exception as e:
            logger.warning(f"Failed to parse well-known response: {e}")
            return None

    @classmethod
    async def scan_ports(
        cls,
        host: str = 'localhost',
        ports: List[int] = None,
        callback = None
    ) -> List[DiscoverableService]:
        """
        Scan common ports for MCP servers.

        Args:
            host: Host to scan
            ports: Ports to check (defaults to common MCP ports)
            callback: Called for each discovered service

        Returns:
            List of discovered services
        """
        if ports is None:
            ports = [
                8080, 8081, 8765,  # Common MCP/API ports
                3000, 3001,        # Dev servers
                5000, 5001,        # Flask defaults
                8000, 8001,        # FastAPI/uvicorn
                9000, 9001,        # Various services
            ]

        services = []

        for port in ports:
            url = f"http://{host}:{port}"
            service = await cls.probe(url)
            if service:
                services.append(service)
                if callback:
                    await callback(service)

        return services


# =============================================================================
# MCP GATEWAY SERVER - Exposes all discovered services
# =============================================================================

class MCPGateway:
    """
    MCP Gateway Server that aggregates all discovered services.

    Acts as a meta-MCP server that:
    1. Discovers all available MCP servers
    2. Exposes unified tools from all servers
    3. Routes requests to appropriate backend
    """

    def __init__(self, registry: ServiceRegistry):
        self.registry = registry
        self.server = None

    async def start(self):
        """Start the MCP gateway server."""
        try:
            from mcp.server import Server
            from mcp.server.stdio import stdio_server
        except ImportError:
            logger.error("MCP SDK not installed")
            return

        self.server = Server("mcp-gateway")

        # Register discovery tools
        @self.server.tool()
        async def discover_services(
            service_type: str = "",
            capability: str = "",
            refresh: bool = False
        ) -> str:
            """
            Discover available services (MCP servers, tools, datasources).

            Args:
                service_type: Filter by type (mcp_server, tool, skill, datasource)
                capability: Filter by capability name
                refresh: Re-scan for new services

            Returns:
                JSON list of discovered services
            """
            if refresh:
                await self._refresh_discovery()

            stype = ServiceType(service_type) if service_type else None
            services = self.registry.query(service_type=stype, capability=capability)

            return json.dumps([s.to_dict() for s in services], indent=2)

        @self.server.tool()
        async def list_all_tools() -> str:
            """
            List all tools from all discovered MCP servers.

            Returns:
                JSON with tools grouped by server
            """
            result = {}
            for service in self.registry.query(service_type=ServiceType.MCP_SERVER):
                if service.tools:
                    result[service.name] = {
                        'tools': service.tools,
                        'endpoint': service.endpoint.address
                    }
            return json.dumps(result, indent=2)

        @self.server.tool()
        async def call_remote_tool(
            server_name: str,
            tool_name: str,
            arguments: str = "{}"
        ) -> str:
            """
            Call a tool on a remote MCP server.

            Args:
                server_name: Name of the MCP server
                tool_name: Name of the tool to call
                arguments: JSON string of tool arguments

            Returns:
                Tool result or error message
            """
            services = self.registry.query(
                service_type=ServiceType.MCP_SERVER,
                name_pattern=server_name
            )

            if not services:
                return f"Server '{server_name}' not found"

            service = services[0]
            args = json.loads(arguments)

            # Route to appropriate transport
            if service.endpoint.transport == TransportType.STDIO:
                return await self._call_stdio_tool(service, tool_name, args)
            elif service.endpoint.transport == TransportType.HTTP:
                return await self._call_http_tool(service, tool_name, args)
            else:
                return f"Unsupported transport: {service.endpoint.transport}"

        @self.server.tool()
        async def register_service(
            name: str,
            service_type: str,
            transport: str,
            address: str,
            description: str = "",
            tools: str = "[]",
            tags: str = "[]"
        ) -> str:
            """
            Register a new service in the discovery registry.

            Args:
                name: Service name
                service_type: Type (mcp_server, tool, skill, datasource)
                transport: Transport type (stdio, http, sse, websocket)
                address: Connection address (command for stdio, URL for http)
                description: Service description
                tools: JSON array of tool names
                tags: JSON array of tags

            Returns:
                Registration confirmation with service ID
            """
            service = DiscoverableService(
                id="",
                name=name,
                type=ServiceType(service_type),
                endpoint=ServiceEndpoint(
                    transport=TransportType(transport),
                    address=address
                ),
                description=description,
                tools=json.loads(tools),
                tags=json.loads(tags)
            )

            sid = self.registry.register(service)
            return f"Registered service '{name}' with ID: {sid}"

        @self.server.tool()
        async def refresh_discovery() -> str:
            """
            Refresh service discovery by scanning all sources.

            Scans:
            - Claude Desktop config files
            - Known HTTP ports
            - UDP broadcasts

            Returns:
                Summary of discovered services
            """
            count = await self._refresh_discovery()
            return f"Discovery complete. Found {count} services."

        # Run the gateway server
        logger.info("Starting MCP Gateway Server...")
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )

    async def _refresh_discovery(self) -> int:
        """Refresh discovery from all sources."""
        count = 0

        # Discover from config files
        for service in MCPConfigDiscovery.discover():
            self.registry.register(service)
            count += 1

        # Scan HTTP ports
        for service in await HTTPProbe.scan_ports():
            self.registry.register(service)
            count += 1

        # Clean up stale entries
        self.registry.cleanup_stale()

        return count

    async def _call_stdio_tool(
        self,
        service: DiscoverableService,
        tool_name: str,
        args: Dict
    ) -> str:
        """Call a tool on a stdio-based MCP server."""
        # This would spawn the MCP server and communicate via MCP protocol
        # Simplified implementation - in practice use mcp client library
        return f"Would call {tool_name} on {service.name} with {args}"

    async def _call_http_tool(
        self,
        service: DiscoverableService,
        tool_name: str,
        args: Dict
    ) -> str:
        """Call a tool on an HTTP-based MCP server."""
        import urllib.request

        url = f"{service.endpoint.address}/tools/{tool_name}"

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(args).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode('utf-8')
        except Exception as e:
            return f"Error calling {tool_name}: {e}"


# =============================================================================
# CLI INTERFACE
# =============================================================================

async def cmd_serve():
    """Run the MCP gateway server."""
    registry = ServiceRegistry()

    # Initial discovery
    for service in MCPConfigDiscovery.discover():
        registry.register(service)

    gateway = MCPGateway(registry)
    await gateway.start()


async def cmd_register(name: str, stype: str, transport: str, address: str, **kwargs):
    """Register a service."""
    registry = ServiceRegistry()

    service = DiscoverableService(
        id="",
        name=name,
        type=ServiceType(stype),
        endpoint=ServiceEndpoint(
            transport=TransportType(transport),
            address=address
        ),
        description=kwargs.get('description', ''),
        tags=kwargs.get('tags', [])
    )

    sid = registry.register(service)
    print(f"Registered: {name} (ID: {sid})")


async def cmd_query(stype: str = None, capability: str = None, tag: str = None):
    """Query registered services."""
    registry = ServiceRegistry()

    service_type = ServiceType(stype) if stype else None
    services = registry.query(service_type=service_type, capability=capability, tag=tag)

    for s in services:
        print(f"\n{s.name} ({s.type.value})")
        print(f"  ID: {s.id}")
        print(f"  Endpoint: {s.endpoint.transport.value}://{s.endpoint.address}")
        print(f"  Tools: {', '.join(s.tools) if s.tools else 'None'}")
        print(f"  Alive: {s.is_alive()}")


async def cmd_discover():
    """Run discovery and show results."""
    registry = ServiceRegistry()

    print("Discovering from config files...")
    for service in MCPConfigDiscovery.discover():
        registry.register(service)
        print(f"  Found: {service.name}")

    print("\nScanning HTTP ports...")
    for service in await HTTPProbe.scan_ports():
        registry.register(service)
        print(f"  Found: {service.name} at {service.endpoint.address}")

    print(f"\nTotal services: {len(registry.get_all())}")


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='MCP Discovery Protocol')
    subparsers = parser.add_subparsers(dest='command', help='Command')

    # serve command
    subparsers.add_parser('serve', help='Run MCP gateway server')

    # register command
    reg_parser = subparsers.add_parser('register', help='Register a service')
    reg_parser.add_argument('--name', required=True, help='Service name')
    reg_parser.add_argument('--type', required=True, choices=['mcp_server', 'tool', 'skill', 'datasource'])
    reg_parser.add_argument('--transport', required=True, choices=['stdio', 'http', 'sse', 'websocket'])
    reg_parser.add_argument('--address', required=True, help='Connection address')
    reg_parser.add_argument('--description', default='', help='Description')

    # query command
    query_parser = subparsers.add_parser('query', help='Query services')
    query_parser.add_argument('--type', choices=['mcp_server', 'tool', 'skill', 'datasource'])
    query_parser.add_argument('--capability', help='Filter by capability')
    query_parser.add_argument('--tag', help='Filter by tag')

    # discover command
    subparsers.add_parser('discover', help='Run discovery')

    args = parser.parse_args()

    if args.command == 'serve':
        asyncio.run(cmd_serve())
    elif args.command == 'register':
        asyncio.run(cmd_register(args.name, args.type, args.transport, args.address))
    elif args.command == 'query':
        asyncio.run(cmd_query(args.type, args.capability, args.tag))
    elif args.command == 'discover':
        asyncio.run(cmd_discover())
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
