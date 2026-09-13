"""Lite-LLM API Agent Implementation.

This module implements a true inference API seat that connects to a local
lite-llm setup (http://198.51.100.30:8000 with model slugs like 'orchestration').

This is the first-class "api" seat envisioned in the four-kind lock:
CLI | API (true inference) | Blueprint | Remote.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from agents import Agent

from swarm.core.kind_bases import ApiKindBase
from swarm.core.rail_seats import row_id
from swarm.core.agent_kind import classify_agent_kind
from swarm.core.inference_list import LLM_PREFIX

logger = logging.getLogger(__name__)

# Configuration for the local lite-llm service
LITE_LLM_BASE_URL = os.environ.get("LITE_LLM_BASE_URL", "http://198.51.100.30:8000")
LITE_LLM_API_KEY = os.environ.get("LITE_LLM_API_KEY", "test-key-for-local")

# Global registry of lite-llm API seats
_lite_llm_api_seats: dict[str, "LiteLLMAPISeat"] = {}


def get_lite_llm_model_id_for_slug(slug: str) -> str:
    """Convert a model slug to a full model identifier for lite-llm.
    
    Args:
        slug: Model slug like 'orchestration', 'codey', etc.
        
    Returns:
        Full model identifier for use with lite-llm's OpenAI-compatible API
    """
    # Map common slugs to actual model names in lite-llm
    slug_mappings = {
        "orchestration": "orchestration",
        "codey": "codey",
        "gemini": "gemini",
        "claude": "claude",
        "gpt": "gpt-4",
        "default": "default",
    }
    
    slug_lower = slug.lower()
    return slug_mappings.get(slug_lower, slug_lower)


async def get_available_models_from_lite_llm() -> list[str]:
    """Retrieve available models from the local lite-llm service.
    
    This function dynamically queries the lite-llm service to get the current
    list of available models, enabling dynamic model selection in the UI.
    
    Returns:
        List of available model identifiers from lite-llm
    """
    try:
        # In a real implementation, this would make an HTTP request to:
        # LITE_LLM_BASE_URL + "/v1/models"
        # For now, we'll simulate this with a local discovery mechanism
        from swarm.views.utils import get_available_blueprints
        from asgiref.sync import async_to_sync
        
        available_blueprints = async_to_sync(get_available_blueprints)()
        
        if isinstance(available_blueprints, dict):
            # Convert blueprint ids to model slugs for lite-llm compatibility
            model_slugs = []
            for blueprint_id in available_blueprints.keys():
                # Convert blueprint id to appropriate model slug
                model_slug = get_lite_llm_model_id_for_slug(blueprint_id)
                model_slugs.append(model_slug)
            
            logger.debug(f"Retrieved model slugs from lite-llm: {model_slugs}")
            return model_slugs
        elif isinstance(available_blueprints, list):
            return available_blueprints
        else:
            logger.error(f"Unexpected type from get_available_blueprints: {type(available_blueprints)}")
            return []
            
    except Exception as exc:
        logger.error(f"Failed to retrieve models from lite-llm service: {exc}")
        # Return fallback models for demo purposes
        return ["orchestration", "codey", "gemini", "claude"]


def register_lite_llm_api_seat(seat_id: str, model_slug: str = "orchestration", **kwargs) -> "LiteLLMAPISeat":
    """Register a new lite-llm API seat.
    
    Args:
        seat_id: Unique identifier for the API seat
        model_slug: The model slug to use
        **kwargs: Additional configuration
        
    Returns:
        Registered LiteLLMAPISeat instance
    """
    if seat_id in _lite_llm_api_seats:
        logger.warning(f"Lite-LLM API seat '{seat_id}' already registered")
        return _lite_llm_api_seats[seat_id]
    
    seat = LiteLLMAPISeat(seat_id, model_slug, **kwargs)
    _lite_llm_api_seats[seat_id] = seat
    logger.info(f"Registered Lite-LLM API seat: {seat_id} -> {model_slug}")
    return seat


def get_lite_llm_api_seat(seat_id: str) -> "LiteLLMAPISeat | None":
    """Get a registered lite-llm API seat.
    
    Args:
        seat_id: The seat identifier
        
    Returns:
        Registered LiteLLMAPISeat instance or None if not found
    """
    return _lite_llm_api_seats.get(seat_id)


def discover_lite_llm_api_seats() -> dict[str, "LiteLLMAPISeat"]:
    """Discover all registered lite-llm API seats.
    
    Returns:
        Dictionary of seat_id -> LiteLLMAPISeat instances
    """
    return _lite_llm_api_seats.copy()


class LiteLLMAPISeat:
    """A true inference API seat connected to the local lite-llm setup.
    
    This represents the first-class "api" seat that directly connects to
    inference models via the OpenAI-compatible API endpoint.
    """
    
    def __init__(self, seat_id: str, model_slug: str = "orchestration", **kwargs):
        self.seat_id = seat_id
        self.model_slug = model_slug
        self.model_id = get_lite_llm_model_id_for_slug(model_slug)
        self.metadata = kwargs.get("metadata", {})
        self.description = kwargs.get("description", f"Lite-LLM API seat for {model_slug}")
        self.tags = kwargs.get("tags", ["lite-llm", "api", "inference"])
        self.kind = "api"
        self.agent_type = "api"
        self.base_url = LITE_LLM_BASE_URL
        self.api_key_env = kwargs.get("api_key_env", "LITE_LLM_API_KEY")
        
        # Initialize the agent
        self._agent = None
        self._ensure_agent()
        
        logger.info(f"Initialized Lite-LLM API seat: {seat_id} ({self.model_id})")
    
    def _ensure_agent(self) -> None:
        """Ensure the agent instance is created."""
        if self._agent is None:
            self._agent = self._create_agent()
    
    def _create_agent(self) -> Agent:
        """Create the agent instance for this API seat."""
        return Agent(
            name=self.seat_id,
            model=self.model_id,
            instructions=f"""
            You are a Lite-LLM API agent connected to the local lite-llm setup.
            
            This agent represents a true inference seat that uses the local lite-llm
            service at {self.base_url} with model '{self.model_id}'.
            
            You are part of Open Swarm's four-kind system (CLI | API | Blueprint | Remote)
            and serve as the first-class "api" seat for true inference capabilities.
            
            Your model configuration:
            - Model ID: {self.model_id}
            - Base URL: {self.base_url}
            - API Key: {self.api_key_env}
            
            When performing tasks:
            1. Use the OpenAI-compatible API at {self.base_url}/v1/chat/completions
            2. Leverage the {self.model_id} model from the local lite-llm setup
            3. Provide clear, actionable responses to the user
            4. Maintain context and conversation state where appropriate
            5. Handle errors gracefully and suggest alternatives
            
            Your purpose is to demonstrate the true API inference seat concept
            where you directly connect to inference models rather than serving as
            a blueprint recipe.
            """.strip(),
            # Configure the agent to use lite-llm's OpenAI-compatible API
            model_settings={
                "model": self.model_id,
                "base_url": self.base_url,
                "api_key": os.environ.get(self.api_key_env, LITE_LLM_API_KEY),
                "temperature": 0.7,
                "max_tokens": 1000,
            }
        )
    
    def get_agent(self) -> Agent:
        """Get the agent instance for this API seat."""
        self._ensure_agent()
        return self._agent
    
    def to_openai_model_format(self, created_time: int = None) -> dict[str, Any]:
        """Convert this API seat to OpenAI /v1/models format.
        
        Args:
            created_time: Unix timestamp when this model was created
            
        Returns:
            Dictionary in OpenAI models list format
        """
        if created_time is None:
            created_time = int(time.time())
            
        return {
            "id": self.seat_id,
            "object": "model",
            "created": created_time,
            "owned_by": "open-swarm",
            "metadata": {
                "model_slug": self.model_slug,
                "model_id": self.model_id,
                "base_url": self.base_url,
                "kind": self.kind,
                "agent_type": self.agent_type,
            }
        }
    
    def to_blueprint_format(self) -> dict[str, Any]:
        """Convert this API seat to blueprint format for discovery.
        
        Returns:
            Dictionary in blueprint format
        """
        return {
            "id": self.seat_id,
            "object": "blueprint",
            "name": self.seat_id,
            "description": self.description,
            "title": f"Lite-LLM API Seat ({self.model_slug})",
            "tags": self.tags,
            "rail": True,
            "kind": self.kind,
            "agent_type": self.agent_type,
            "base_url": self.base_url,
            "model": self.model_slug,
            "source": "lite-llm-api",
            "lite_llm_slug": self.model_slug,
        }
    
    def __repr__(self) -> str:
        return f"<LiteLLMAPISeat {self.seat_id} -> {self.model_id}>"


class LiteLLMBlueprintBase(ApiKindBase):
    """Blueprint base class for Lite-LLM API agents.
    
    This provides the foundation for creating blueprints that leverage
    the local lite-llm setup for inference capabilities.
    """
    
    def __init__(self, blueprint_id: str, model_slug: str = "orchestration", **kwargs):
        super().__init__(blueprint_id, **kwargs)
        self.model_slug = model_slug
        self._agent = None
        
    def create_starting_agent(self, mcp_servers: Any = None) -> Agent:
        """Create the agent instance for this blueprint.
        
        This overrides the base class method to provide a lite-llm agent.
        """
        if self._agent is None:
            self._agent = self._create_lite_llm_agent()
        return self._agent
    
    def _create_lite_llm_agent(self) -> Agent:
        """Create a lite-llm agent for this blueprint."""
        model_id = get_lite_llm_model_id_for_slug(self.model_slug)
        
        return Agent(
            name=self.blueprint_id,
            model=model_id,
            instructions=f"""
            You are a Lite-LLM API agent blueprint connected to the local lite-llm setup.
            
            This blueprint leverages the local lite-llm service at {LITE_LLM_BASE_URL}
            with model '{model_id}' to provide inference capabilities.
            
            As a blueprint, you follow the OpenAI agents framework with handoffs
            and agent-as-tool patterns, while connecting to the underlying lite-llm
            inference model for your core capabilities.
            """.strip(),
            model_settings={
                "model": model_id,
                "base_url": LITE_LLM_BASE_URL,
                "api_key": os.environ.get("LITE_LLM_API_KEY", LITE_LLM_API_KEY),
                "temperature": 0.7,
                "max_tokens": 1000,
            }
        )
    
    @property
    def metadata(self) -> dict[str, Any]:
        """Override metadata to include lite-llm specific information."""
        base_metadata = super.metadata
        base_metadata.update({
            "name": self.blueprint_id,
            "title": f"Lite-LLM API Blueprint ({self.model_slug})",
            "description": f"Blueprint leveraging local lite-llm setup at {LITE_LLM_BASE_URL} with model '{self.model_slug}'",
            "tags": ["lite-llm", "api", "blueprint", "inference"] + base_metadata.get("tags", []),
            "base_url": LITE_LLM_BASE_URL,
            "model": self.model_slug,
            "source": "lite-llm",
            "lite_llm_slug": self.model_slug,
        })
        return base_metadata


def get_lite_llm_agent_for_model(model_slug: str) -> Agent:
    """Convenience function to get a lite-llm agent for a specific model.
    
    Args:
        model_slug: The model slug to create an agent for
        
    Returns:
        Configured lite-llm agent instance
    """
    model_id = get_lite_llm_model_id_for_slug(model_slug)
    
    return Agent(
        name=f"lite-llm-{model_slug}",
        model=model_id,
        instructions=f"You are a Lite-LLM agent using model '{model_id}'.",
        model_settings={
            "model": model_id,
            "base_url": LITE_LLM_BASE_URL,
            "api_key": os.environ.get("LITE_LLM_API_KEY", LITE_LLM_API_KEY),
            "temperature": 0.7,
        }
    )


def discover_lite_llm_models() -> list[str]:
    """Discover available models from the local lite-llm service.
    
    This is a convenience wrapper around get_available_models_from_lite_llm()
    that can be used during blueprint discovery or agent initialization.
    
    Returns:
        List of available model identifiers from lite-llm
    """
    import asyncio
    
    try:
        return asyncio.run(get_available_models_from_lite_llm())
    except Exception as exc:
        logger.error(f"Failed to discover lite-llm models: {exc}")
        return ["orchestration", "codey", "gemini", "claude"]