
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MCPServerConfig(BaseModel):
    """
    Configuration for an MCP (Multi-Agent Control Plane) server.
    """
    name: str = Field("", description="Unique name for the MCP server instance.")
    url: str | None = Field(None, description="URL of the MCP server endpoint, if applicable.")

    # Optional fields that might be part of a server's configuration
    # These are based on common patterns for process/server management.
    command: str | None = Field(None, description="Command to start the server (e.g., 'python', 'npx').")
    args: list[str] = Field(default_factory=list, description="Arguments for the command.")
    env: dict[str, str] = Field(default_factory=dict, description="Environment variables for the server process.")
    cwd: str | None = Field(None, description="Working directory for the server process.")

    # You might also include fields for authentication, type, etc.
    # type: Optional[str] = Field(None, description="Type of the MCP server (e.g., 'filesystem', 'memory', 'custom').")
    # token_env_var: Optional[str] = Field(None, description="Environment variable name holding an auth token for this server.")

    # Allow extra fields if loaded from a more complex config (pydantic v2 style)
    model_config = ConfigDict(extra="allow", hide_input_in_errors=True)

    @classmethod
    def from_named_dict(cls, name: str, data: dict[str, Any] | None) -> "MCPServerConfig":
        """Build from a ``mcpServers`` row whose name is the map key, not a field."""
        payload = dict(data or {})
        payload.setdefault("name", name)
        return cls(**payload)

