import logging
import sys

from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings

from swarm.blueprints.dynamic_team.blueprint_dynamic_team import DynamicTeamBlueprint

# Assuming the discovery functions are correctly located now
from swarm.core.agent_kind import (
    API_AGENT_BLUEPRINT_ID,
    API_AGENT_RAIL_ID,
    resolve_chat_blueprint_id,
)
from swarm.core.blueprint_discovery import (
    apply_blueprint_aliases,
    discover_blueprints,
    merge_community_blueprints,
)
from swarm.core.paths import (
    ensure_swarm_directories_exist,
    get_user_config_dir_for_swarm,
)

logger = logging.getLogger(__name__)

# Bridge module aliasing between 'swarm' and 'src.swarm' imports so globals are shared
try:
    if __name__ == 'swarm.views.utils':
        sys.modules.setdefault('src.swarm.views.utils', sys.modules[__name__])
    elif __name__ == 'src.swarm.views.utils':
        sys.modules.setdefault('swarm.views.utils', sys.modules[__name__])
except Exception:
    pass

# --- Caching ---
# Cache blueprint class/metadata only — never live instances. Instances are
# mutable (agents, params, run state) and must not be shared across requests.
_blueprint_meta_cache = None  # Cache for the {name: class} mapping
_dynamic_registry: dict[str, dict] = {}


def _dynamic_registry_path():
    ensure_swarm_directories_exist()
    return get_user_config_dir_for_swarm() / "teams.json"


def load_dynamic_registry() -> dict[str, dict]:
    global _dynamic_registry
    if _dynamic_registry:
        return _dynamic_registry
    try:
        path = _dynamic_registry_path()
        if path.exists():
            import json
            raw = path.read_text(encoding="utf-8")
            if not raw.strip():
                # Empty file is treated as an empty registry (common after truncate).
                _dynamic_registry = {}
            else:
                _dynamic_registry = json.loads(raw) or {}
        else:
            _dynamic_registry = {}
    except Exception:
        logger.exception("Failed to load dynamic teams registry; using empty registry.")
        _dynamic_registry = {}
    return _dynamic_registry


def save_dynamic_registry() -> None:
    """Persist the in-memory dynamic teams registry to teams.json.

    Raises on I/O or serialization failure so callers can surface errors
    instead of reporting a false success.
    """
    path = _dynamic_registry_path()
    import json
    try:
        path.write_text(json.dumps(_dynamic_registry, indent=2), encoding="utf-8")
    except Exception:
        logger.exception("Failed to persist dynamic teams registry to %s", path)
        raise


def register_dynamic_team(team_id: str, description: str | None = None, llm_profile: str | None = None) -> None:
    """Registers a dynamic team in memory and persists to disk.

    team_id is both the human-facing team name/slug and the model id exposed via /v1/models.
    Raises if the registry cannot be persisted.
    """
    reg = load_dynamic_registry()
    reg[team_id] = {
        "id": team_id,
        "description": description or "Dynamic team",
        "llm_profile": llm_profile or "default",
    }
    global _blueprint_meta_cache
    _blueprint_meta_cache = None  # Force rebuild on next access
    save_dynamic_registry()


def deregister_dynamic_team(team_id: str) -> bool:
    """Removes a dynamic team from the registry. Returns True if removed.

    Raises if the team existed but the registry could not be persisted.
    """
    reg = load_dynamic_registry()
    if team_id in reg:
        reg.pop(team_id, None)
        global _blueprint_meta_cache
        _blueprint_meta_cache = None
        save_dynamic_registry()
        return True
    return False


def reset_dynamic_registry() -> None:
    """Clears all dynamic teams and persists an empty registry.

    Raises if the empty registry cannot be persisted.
    """
    global _dynamic_registry, _blueprint_meta_cache
    _dynamic_registry = {}
    _blueprint_meta_cache = None
    save_dynamic_registry()

# --- Blueprint Metadata Loading ---
def _load_all_blueprint_metadata_sync():
    """Synchronous helper to perform blueprint discovery."""
    global _blueprint_meta_cache
    logger.info("Discovering blueprint classes (sync)...")
    blueprint_classes = discover_blueprints(settings.BLUEPRINT_DIRECTORY)
    blueprint_classes = merge_community_blueprints(
        blueprint_classes, getattr(settings, "BLUEPRINT_EXTRA_DIRS", None)
    )
    blueprint_classes = apply_blueprint_aliases(blueprint_classes)

    # Rail API seat is not a package; advertise the same recipe websocket uses
    # so GET /v1/models lists ``api_agent`` and POST model=api_agent resolves.
    if (
        API_AGENT_BLUEPRINT_ID in blueprint_classes
        and API_AGENT_RAIL_ID not in blueprint_classes
    ):
        info = dict(blueprint_classes[API_AGENT_BLUEPRINT_ID])
        meta = dict(info.get("metadata") or {})
        meta = {**meta, "name": API_AGENT_RAIL_ID}
        info["metadata"] = meta
        blueprint_classes[API_AGENT_RAIL_ID] = info

    # Merge dynamic teams as blueprints
    dyn = load_dynamic_registry()
    for team_id, meta in dyn.items():
        blueprint_classes[team_id] = {
            "class_type": DynamicTeamBlueprint,
            "metadata": {
                "name": team_id,
                "description": meta.get("description", "Dynamic team"),
                "abbreviation": None,
                "tags": ["team", "dynamic"],
            },
        }
    logger.info(f"Found blueprint classes: {list(blueprint_classes.keys())}")
    _blueprint_meta_cache = blueprint_classes
    return blueprint_classes

def get_available_blueprints_sync():
    """Sync blueprint metadata map — safe inside an already-running event loop.

    Prefer this from sync helpers invoked by async chat turns. The
    ``@sync_to_async`` wrapper below must be *awaited* (or driven via
    ``async_to_sync`` only from a thread with no running loop).
    """
    global _blueprint_meta_cache
    if _blueprint_meta_cache is None:
        _load_all_blueprint_metadata_sync()
    return _blueprint_meta_cache


@sync_to_async
def get_available_blueprints():
     """Asynchronously retrieves available blueprint classes."""
     return get_available_blueprints_sync()

# --- Blueprint Instance Loading ---
# Removed _load_blueprint_class_sync

async def get_blueprint_instance(blueprint_id: str, params: dict = None):
    """Asynchronously gets a fresh instance of a specific blueprint.

    Always instantiates per call so concurrent requests never share mutable
    blueprint state.
    """
    logger.debug(f"Getting instance for blueprint: {blueprint_id} with params: {params}")

    available_blueprint_classes = await get_available_blueprints()
    blueprint_id = resolve_chat_blueprint_id(blueprint_id)

    if not isinstance(available_blueprint_classes, dict) or blueprint_id not in available_blueprint_classes:
        logger.error(f"Blueprint ID '{blueprint_id}' not found in available blueprint classes.")
        return None

    blueprint_info = available_blueprint_classes[blueprint_id]
    blueprint_class = blueprint_info['class_type']

    try:
        # Instantiate without params; blueprints that need them use set_params.
        instance = blueprint_class(blueprint_id=blueprint_id)
        # If it's a dynamic team blueprint and llm_profile is specified in registry, set it
        try:
            reg = load_dynamic_registry()
            team_info = reg.get(blueprint_id)
            if team_info and team_info.get("llm_profile") and hasattr(instance, "llm_profile_name"):
                instance.llm_profile_name = team_info["llm_profile"]
        except Exception:
            pass
        logger.info(f"Successfully instantiated blueprint: {blueprint_id}")
        if hasattr(instance, 'set_params') and callable(instance.set_params):
             instance.set_params(params)

        return instance
    except Exception as e:
        # Catch potential TypeError during instantiation too
        logger.error(f"Failed to instantiate blueprint class '{blueprint_id}': {e}", exc_info=True)
        return None

# --- Model Access Validation ---
def validate_model_access(user, model_name):
     """Synchronous permission check."""
     logger.debug(f"Validating access for user '{user}' to model '{model_name}'...")
     try:
         # Never async_to_sync(@sync_to_async) here: chat views already call this
         # via sync_to_async, and nested thread_sensitive scheduling deadlocks
         # the single ASGI worker (agent_router / poets prove hangs).
         available = get_available_blueprints_sync()
         is_available = resolve_chat_blueprint_id(model_name) in available
         logger.debug(f"Model '{model_name}' availability: {is_available}")
         return is_available
     except Exception as e:
         logger.error(f"Error checking model availability during validation: {e}", exc_info=True)
         return False
