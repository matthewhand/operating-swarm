"""
MCP Client Module

Manages connections and interactions with MCP servers using the MCP Python SDK.
Redirects MCP server stderr to log files unless debug mode is enabled.
"""

import asyncio
import logging
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

from mcp import ClientSession, StdioServerParameters  # type: ignore
from mcp.client.stdio import stdio_client  # type: ignore

from swarm.types import Tool
from swarm.utils.env_utils import build_mcp_stdio_env

from .cache_utils import get_cache

logger = logging.getLogger(__name__)

class MCPClient:
    """
    Manages connections and interactions with MCP servers using the MCP Python SDK.
    """

    def __init__(self, server_config: dict[str, Any], timeout: int = 15, debug: bool = False):
        """
        Initialize the MCPClient with server configuration.

        Args:
            server_config (dict): Configuration dictionary for the MCP server.
            timeout (int): Timeout for operations in seconds.
            debug (bool): If True, MCP server stderr goes to console; otherwise, to log file.
        """
        self.command = server_config.get("command", "npx")
        self.args = server_config.get("args", [])
        # Essentials + configured env only — never inherit full parent os.environ
        # (that leaked API keys/tokens into every stdio MCP child).
        self.env = build_mcp_stdio_env(server_config.get("env") or {})
        self.timeout = timeout
        self.debug = debug
        self._tool_cache: dict[str, Tool] = {}

        # Initialize cache using the helper
        self.cache = get_cache()

        logger.info(f"Initialized MCPClient with command={self.command}, args={self.args}, debug={self.debug}")

    @contextmanager
    def _redirect_stderr(self):
        import os
        import sys
        if not self.debug:
            old_stderr = sys.stderr
            sys.stderr = open(os.devnull, "w")
            try:
                yield
            finally:
                sys.stderr.close()
                sys.stderr = old_stderr
        else:
            yield

    async def list_tools(self) -> list[Tool]:
        """
        Discover tools from the MCP server and cache their schemas.

        Returns:
            List[Tool]: A list of discovered tools with schemas.
        """
        logger.debug(f"Entering list_tools for command={self.command}, args={self.args}")

        # Attempt to retrieve tools from cache
        args_string = "_".join(self.args)
        cache_key = f"mcp_tools_{self.command}_{args_string}"
        cached_tools = self.cache.get(cache_key)

        if cached_tools:
            logger.debug("Retrieved tools from cache")
            tools = []
            for tool_data in cached_tools:
                tool_name = tool_data["name"]
                tool = Tool(
                    name=tool_name,
                    description=tool_data["description"],
                    input_schema=tool_data.get("input_schema", {}),
                    func=self._create_tool_callable(tool_name),
                )
                tools.append(tool)
            logger.debug(f"Returning {len(tools)} cached tools")
            return tools

        server_params = StdioServerParameters(command=self.command, args=self.args, env=self.env)
        logger.debug("Opening stdio_client connection")
        async with stdio_client(server_params) as (read, write):
            logger.debug("Opening ClientSession")
            async with ClientSession(read, write) as session:
                try:
                    logger.info("Initializing session for tool discovery")
                    await asyncio.wait_for(session.initialize(), timeout=self.timeout)
                    logger.info("Initializing session for tool discovery")
                    await asyncio.wait_for(session.initialize(), timeout=self.timeout)
                    logger.info("Capabilities initialized. Entering tool discovery.")
                    logger.info("Requesting tool list from MCP server...")
                    tools_response = await asyncio.wait_for(session.list_tools(), timeout=self.timeout)
                    logger.debug("Tool list received from MCP server")

                    serialized_tools = [
                        {
                            'name': tool.name,
                            'description': tool.description,
                            'input_schema': tool.inputSchema,
                        }
                        for tool in tools_response.tools
                    ]

                    self.cache.set(cache_key, serialized_tools, 3600)
                    logger.debug(f"Cached {len(serialized_tools)} tools.")

                    tools = []
                    for tool in tools_response.tools:
                        input_schema = tool.inputSchema or {}
                        cached_tool = Tool(
                            name=tool.name,
                            description=tool.description,
                            input_schema=input_schema,
                            func=self._create_tool_callable(tool.name),
                        )
                        self._tool_cache[tool.name] = cached_tool
                        tools.append(cached_tool)
                        logger.debug(f"Discovered tool: {tool.name} with schema: {input_schema}")

                    logger.debug(f"Returning {len(tools)} tools from MCP server")
                    return tools

                except asyncio.TimeoutError:
                    logger.error(f"Timeout after {self.timeout}s waiting for tool list")
                    raise RuntimeError("Tool list request timed out")
                except Exception as e:
                    logger.error(f"Error listing tools: {e}")
                    raise RuntimeError("Failed to list tools") from e

    async def _do_list_resources(self) -> Any:
        server_params = StdioServerParameters(command=self.command, args=self.args, env=self.env)
        logger.debug("Opening stdio_client connection for resources")
        async with stdio_client(server_params) as (read, write):
            logger.debug("Opening ClientSession for resources")
            async with ClientSession(read, write) as session:
                logger.info("Requesting resource list from MCP server...")
                with self._redirect_stderr():
                    # Ensure we initialize the session before listing resources
                    logger.debug("Initializing session before listing resources")
                    await asyncio.wait_for(session.initialize(), timeout=self.timeout)
                    resources_response = await asyncio.wait_for(session.list_resources(), timeout=self.timeout)
                logger.debug("Resource list received from MCP server")
                return resources_response

    def _create_tool_callable(self, tool_name: str) -> Callable[..., Any]:
        """
        Dynamically create a callable function for the specified tool.
        """
        async def dynamic_tool_func(**kwargs) -> Any:
            logger.debug(f"Creating tool callable for '{tool_name}'")
            server_params = StdioServerParameters(command=self.command, args=self.args, env=self.env)
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    try:
                        logger.debug(f"Initializing session for tool '{tool_name}'")
                        await asyncio.wait_for(session.initialize(), timeout=self.timeout)
                        if tool_name in self._tool_cache:
                            tool = self._tool_cache[tool_name]
                            self._validate_input_schema(tool.input_schema, kwargs)
                        logger.info(f"Calling tool '{tool_name}' with arguments: {kwargs}")
                        result = await asyncio.wait_for(session.call_tool(tool_name, kwargs), timeout=self.timeout)
                        logger.info(f"Tool '{tool_name}' executed successfully: {result}")
                        return result
                    except asyncio.TimeoutError:
                        logger.error(f"Timeout after {self.timeout}s executing tool '{tool_name}'")
                        raise RuntimeError(f"Tool '{tool_name}' execution timed out")
                    except Exception as e:
                        logger.error(f"Failed to execute tool '{tool_name}': {e}")
                        raise RuntimeError(f"Tool execution failed: {e}") from e

        return dynamic_tool_func

    def _validate_input_schema(self, schema: dict[str, Any], kwargs: dict[str, Any]):
        """
        Validate the provided arguments against the input schema.
        """
        if not schema:
            logger.debug("No input schema available for validation. Skipping.")
            return

        required_params = schema.get("required", [])
        for param in required_params:
            if param not in kwargs:
                raise ValueError(f"Missing required parameter: '{param}'")

        logger.debug(f"Validated input against schema: {schema} with arguments: {kwargs}")

    async def list_resources(self) -> Any:
        """
        Discover resources from the MCP server using the internal method with enforced timeout.
        """
        return await asyncio.wait_for(self._do_list_resources(), timeout=self.timeout)

    async def get_resource(self, resource_uri: str) -> Any:
        """
        Retrieve a specific resource from the MCP server.

        Args:
            resource_uri (str): The URI of the resource to retrieve.

        Returns:
            Any: The resource retrieval response.
        """
        server_params = StdioServerParameters(command=self.command, args=self.args, env=self.env)
        logger.debug("Opening stdio_client connection for resource retrieval")
        async with stdio_client(server_params) as (read, write):
            logger.debug("Opening ClientSession for resource retrieval")
            async with ClientSession(read, write) as session:
                try:
                    logger.debug(f"Initializing session for resource retrieval of {resource_uri}")
                    await asyncio.wait_for(session.initialize(), timeout=self.timeout)
                    logger.info(f"Retrieving resource '{resource_uri}' from MCP server")
                    response = await asyncio.wait_for(session.read_resource(resource_uri), timeout=self.timeout)
                    logger.info(f"Resource '{resource_uri}' retrieved successfully")
                    return response
                except asyncio.TimeoutError:
                    logger.error(f"Timeout retrieving resource '{resource_uri}' after {self.timeout}s")
                    raise RuntimeError(f"Resource '{resource_uri}' retrieval timed out")
                except Exception as e:
                    logger.error(f"Failed to retrieve resource '{resource_uri}': {e}")
                    raise RuntimeError(f"Resource retrieval failed: {e}") from e
