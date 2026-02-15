"""
Axiom MCP Integration Layer

Implements Model Context Protocol client for connecting to MCP servers
Manages tool registry and execution
"""

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Optional, Literal
from enum import Enum


# ============================================================================
# MCP PROTOCOL TYPES
# ============================================================================

class MCPProtocol(Enum):
    STDIO = "stdio"  # Standard input/output
    SSE = "sse"      # Server-Sent Events
    WEBSOCKET = "websocket"

@dataclass
class MCPServerConfig:
    """Configuration for MCP server connection"""
    name: str
    protocol: MCPProtocol
    
    # For stdio
    command: Optional[str] = None
    args: Optional[list[str]] = None
    
    # For SSE/WebSocket
    url: Optional[str] = None
    
    # Authentication
    auth: Optional[dict] = None
    
    # Timeouts
    connection_timeout: int = 30
    request_timeout: int = 60

@dataclass
class MCPTool:
    """Tool exposed by MCP server"""
    name: str
    description: str
    parameters: dict  # JSON Schema
    server: str
    
    def to_openai_function(self) -> dict:
        """Convert to OpenAI function calling format"""
        return {
            "type": "function",
            "function": {
                "name": f"{self.server}.{self.name}",
                "description": self.description,
                "parameters": self.parameters
            }
        }

@dataclass
class ToolResult:
    """Result from tool execution"""
    output: Any
    is_error: bool = False
    error_message: Optional[str] = None
    metadata: dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


# ============================================================================
# TRANSPORT LAYERS
# ============================================================================

class Transport:
    """Base transport class"""
    
    async def connect(self):
        raise NotImplementedError
    
    async def send(self, message: dict) -> dict:
        raise NotImplementedError
    
    async def close(self):
        raise NotImplementedError


class StdioTransport(Transport):
    """
    Standard I/O transport for local MCP servers
    
    Launches subprocess and communicates via stdin/stdout
    """
    
    def __init__(self, command: str, args: list[str]):
        self.command = command
        self.args = args
        self.process: Optional[asyncio.subprocess.Process] = None
        self.message_id = 0
    
    async def connect(self):
        """Launch subprocess"""
        
        self.process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
    
    async def send(self, message: dict) -> dict:
        """Send JSON-RPC message and wait for response"""
        
        if not self.process:
            raise RuntimeError("Not connected")
        
        # Add message ID
        self.message_id += 1
        message["id"] = self.message_id
        
        # Send message
        json_msg = json.dumps(message) + "\n"
        self.process.stdin.write(json_msg.encode())
        await self.process.stdin.drain()
        
        # Read response
        response_line = await self.process.stdout.readline()
        response = json.loads(response_line.decode())
        
        return response
    
    async def close(self):
        """Close subprocess"""
        
        if self.process:
            self.process.terminate()
            await self.process.wait()


class SSETransport(Transport):
    """
    Server-Sent Events transport for remote MCP servers
    
    Uses HTTP POST for requests, SSE for streaming responses
    """
    
    def __init__(self, url: str, auth: Optional[dict] = None):
        self.url = url
        self.auth = auth
        self.session = None
    
    async def connect(self):
        """Establish HTTP session"""
        
        import aiohttp
        
        headers = {}
        if self.auth:
            if "token" in self.auth:
                headers["Authorization"] = f"Bearer {self.auth['token']}"
            elif "api_key" in self.auth:
                headers["X-API-Key"] = self.auth['api_key']
        
        self.session = aiohttp.ClientSession(headers=headers)
    
    async def send(self, message: dict) -> dict:
        """Send request via HTTP POST"""
        
        if not self.session:
            raise RuntimeError("Not connected")
        
        async with self.session.post(
            f"{self.url}/messages",
            json=message
        ) as response:
            response.raise_for_status()
            return await response.json()
    
    async def close(self):
        """Close session"""
        
        if self.session:
            await self.session.close()


class WebSocketTransport(Transport):
    """WebSocket transport for bidirectional MCP communication"""
    
    def __init__(self, url: str, auth: Optional[dict] = None):
        self.url = url
        self.auth = auth
        self.ws = None
    
    async def connect(self):
        """Connect to WebSocket"""
        
        import aiohttp
        
        headers = {}
        if self.auth and "token" in self.auth:
            headers["Authorization"] = f"Bearer {self.auth['token']}"
        
        session = aiohttp.ClientSession()
        self.ws = await session.ws_connect(self.url, headers=headers)
    
    async def send(self, message: dict) -> dict:
        """Send message via WebSocket"""
        
        if not self.ws:
            raise RuntimeError("Not connected")
        
        await self.ws.send_json(message)
        
        # Wait for response
        msg = await self.ws.receive()
        return json.loads(msg.data)
    
    async def close(self):
        """Close WebSocket"""
        
        if self.ws:
            await self.ws.close()


# ============================================================================
# MCP CLIENT
# ============================================================================

class MCPClient:
    """
    Model Context Protocol client
    
    Connects to MCP servers and exposes their tools to agents
    """
    
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.transport = self._create_transport()
        self.tools: dict[str, MCPTool] = {}
        self.connected = False
    
    def _create_transport(self) -> Transport:
        """Create appropriate transport based on protocol"""
        
        if self.config.protocol == MCPProtocol.STDIO:
            if not self.config.command:
                raise ValueError("STDIO protocol requires command")
            
            return StdioTransport(
                command=self.config.command,
                args=self.config.args or []
            )
        
        elif self.config.protocol == MCPProtocol.SSE:
            if not self.config.url:
                raise ValueError("SSE protocol requires URL")
            
            return SSETransport(
                url=self.config.url,
                auth=self.config.auth
            )
        
        elif self.config.protocol == MCPProtocol.WEBSOCKET:
            if not self.config.url:
                raise ValueError("WebSocket protocol requires URL")
            
            return WebSocketTransport(
                url=self.config.url,
                auth=self.config.auth
            )
        
        else:
            raise ValueError(f"Unknown protocol: {self.config.protocol}")
    
    async def connect(self):
        """Connect to MCP server and discover tools"""
        
        # Connect transport
        await self.transport.connect()
        
        # Initialize MCP session
        init_response = await self.transport.send({
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "1.0",
                "capabilities": {
                    "tools": {}
                },
                "clientInfo": {
                    "name": "axiom",
                    "version": "1.0.0"
                }
            }
        })
        
        if "error" in init_response:
            raise RuntimeError(f"Failed to initialize: {init_response['error']}")
        
        # List available tools
        tools_response = await self.transport.send({
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {}
        })
        
        if "error" in tools_response:
            raise RuntimeError(f"Failed to list tools: {tools_response['error']}")
        
        # Store tools
        for tool_data in tools_response.get("result", {}).get("tools", []):
            tool = MCPTool(
                name=tool_data["name"],
                description=tool_data.get("description", ""),
                parameters=tool_data.get("inputSchema", {}),
                server=self.config.name
            )
            self.tools[tool.name] = tool
        
        self.connected = True
        
        print(f"✓ Connected to MCP server '{self.config.name}' ({len(self.tools)} tools)")
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: dict
    ) -> ToolResult:
        """Execute tool via MCP protocol"""
        
        if not self.connected:
            raise RuntimeError("Not connected to MCP server")
        
        if tool_name not in self.tools:
            raise ValueError(f"Tool '{tool_name}' not found")
        
        # Call tool
        response = await self.transport.send({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        })
        
        # Check for errors
        if "error" in response:
            return ToolResult(
                output=None,
                is_error=True,
                error_message=response["error"].get("message", "Unknown error"),
                metadata={"server": self.config.name, "tool": tool_name}
            )
        
        # Extract result
        result = response.get("result", {})
        
        return ToolResult(
            output=result.get("content", []),
            is_error=result.get("isError", False),
            metadata={
                "server": self.config.name,
                "tool": tool_name
            }
        )
    
    async def disconnect(self):
        """Disconnect from MCP server"""
        
        if self.connected:
            await self.transport.close()
            self.connected = False


# ============================================================================
# TOOL REGISTRY
# ============================================================================

class ToolRegistry:
    """
    Central registry for all MCP tools
    
    Manages multiple MCP server connections and provides
    unified interface for tool execution
    """
    
    def __init__(self):
        self.servers: dict[str, MCPClient] = {}
        self.tools: dict[str, MCPTool] = {}
    
    async def register_server(
        self,
        config: MCPServerConfig
    ):
        """Register MCP server and discover its tools"""
        
        client = MCPClient(config)
        await client.connect()
        
        # Add all tools from this server to global registry
        for tool_name, tool in client.tools.items():
            qualified_name = f"{config.name}.{tool_name}"
            self.tools[qualified_name] = tool
        
        self.servers[config.name] = client
    
    async def register_multiple(
        self,
        configs: list[MCPServerConfig]
    ):
        """Register multiple servers in parallel"""
        
        await asyncio.gather(*[
            self.register_server(config)
            for config in configs
        ])
    
    async def execute(
        self,
        tool_name: str,
        arguments: dict
    ) -> dict:
        """
        Execute tool by qualified name
        
        Args:
            tool_name: Qualified name (e.g., "github.search_repos")
            arguments: Tool arguments
        
        Returns:
            Tool output
        """
        
        # Parse qualified name
        if "." not in tool_name:
            raise ValueError(f"Tool name must be qualified: server.tool")
        
        server_name, tool_name_only = tool_name.split(".", 1)
        
        if server_name not in self.servers:
            raise ValueError(f"Server not registered: {server_name}")
        
        # Execute via MCP client
        client = self.servers[server_name]
        result = await client.call_tool(tool_name_only, arguments)
        
        return {
            "output": result.output,
            "success": not result.is_error,
            "error": result.error_message if result.is_error else None,
            "metadata": result.metadata
        }
    
    def get_schemas(self) -> list[dict]:
        """
        Get OpenAI-compatible tool schemas for LLM
        
        Returns list of function schemas that can be passed to
        Claude, GPT-4, etc.
        """
        
        return [
            tool.to_openai_function()
            for tool in self.tools.values()
        ]
    
    def get_tools_for_agent(self, tool_specs: list[dict]) -> list[dict]:
        """Get subset of tools for specific agent"""
        
        schemas = []
        for spec in tool_specs:
            qualified_name = f"{spec['server']}.{spec['name']}"
            if qualified_name in self.tools:
                schemas.append(self.tools[qualified_name].to_openai_function())
        
        return schemas
    
    async def disconnect_all(self):
        """Disconnect from all MCP servers"""
        
        await asyncio.gather(*[
            client.disconnect()
            for client in self.servers.values()
        ])


# ============================================================================
# BUILT-IN MCP SERVERS
# ============================================================================

# Example: Simple filesystem MCP server implementation
class FilesystemMCPServer:
    """
    Built-in MCP server for filesystem operations
    
    This is an example of a simple MCP server implementation
    """
    
    def __init__(self):
        self.tools = {
            "read_file": {
                "name": "read_file",
                "description": "Read contents of a file",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to file"
                        }
                    },
                    "required": ["path"]
                }
            },
            "write_file": {
                "name": "write_file",
                "description": "Write contents to a file",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["path", "content"]
                }
            },
            "list_directory": {
                "name": "list_directory",
                "description": "List files in directory",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"}
                    },
                    "required": ["path"]
                }
            }
        }
    
    async def call_tool(self, name: str, arguments: dict) -> dict:
        """Execute tool"""
        
        if name == "read_file":
            with open(arguments["path"], "r") as f:
                return {"content": f.read()}
        
        elif name == "write_file":
            with open(arguments["path"], "w") as f:
                f.write(arguments["content"])
            return {"success": True}
        
        elif name == "list_directory":
            import os
            files = os.listdir(arguments["path"])
            return {"files": files}
        
        else:
            raise ValueError(f"Unknown tool: {name}")


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

async def example_usage():
    """Example of using MCP integration"""
    
    # Create tool registry
    registry = ToolRegistry()
    
    # Register multiple MCP servers
    await registry.register_multiple([
        MCPServerConfig(
            name="filesystem",
            protocol=MCPProtocol.STDIO,
            command="node",
            args=["./mcp-servers/filesystem/index.js"]
        ),
        MCPServerConfig(
            name="github",
            protocol=MCPProtocol.SSE,
            url="https://api.github-mcp.com/v1",
            auth={"token": "ghp_xxx"}
        )
    ])
    
    # Get all available tools
    tools = registry.get_schemas()
    print(f"Available tools: {len(tools)}")
    for tool in tools:
        print(f"  - {tool['function']['name']}")
    
    # Execute a tool
    result = await registry.execute(
        "filesystem.read_file",
        {"path": "/tmp/test.txt"}
    )
    print(f"Result: {result}")
    
    # Disconnect
    await registry.disconnect_all()


if __name__ == "__main__":
    asyncio.run(example_usage())
