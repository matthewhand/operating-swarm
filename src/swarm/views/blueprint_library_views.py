"""
Blueprint Library Views for Open Swarm Core.
Handles blueprint browsing, library management, and custom blueprint creation.
"""
import json
import os
from datetime import datetime, timezone
from typing import Any

from django.conf import settings as dj_settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from swarm.core.kind_bases import base_class_for_kind

from swarm.core.blueprint_discovery import discover_blueprints
from swarm.core.paths import get_user_blueprints_dir, get_user_config_dir_for_swarm
from swarm.core.requirements import evaluate_mcp_compliance, load_active_config
from swarm.settings import BLUEPRINT_DIRECTORY
from swarm.utils.comfyui_client import comfyui_client
from swarm.utils.logger_setup import setup_logger
from swarm.views.agent_creator_views import (
    _safe_agent_blueprint_id,
    _save_discovery_message,
)

logger = setup_logger(__name__)

# Predefined blueprint categories and descriptions
BLUEPRINT_CATEGORIES = {
    "ai_assistants": {
        "name": "AI Assistants",
        "description": "Intelligent agents for various tasks",
        "icon": "🤖"
    },
    "code_helpers": {
        "name": "Code Helpers",
        "description": "Programming and development assistants",
        "icon": "💻"
    },
    "content_creators": {
        "name": "Content Creators",
        "description": "Writing, poetry, and content generation",
        "icon": "✍️"
    },
    "system_tools": {
        "name": "System Tools",
        "description": "System monitoring and management",
        "icon": "🔧"
    },
    "web_services": {
        "name": "Web Services",
        "description": "Web development and API tools",
        "icon": "🌐"
    }
}

# Avatar styles available for generation
AVATAR_STYLES = {
    "professional": "Professional headshot style",
    "cartoon": "Cartoon character style",
    "anime": "Anime character style",
    "realistic": "Realistic portrait style",
    "icon": "Simple icon style"
}

# Blueprint metadata for the library
BLUEPRINT_METADATA = {
    "codey": {
        "name": "Codey",
        "description": "AI-powered coding assistant that helps with programming tasks",
        "category": "code_helpers",
        "tags": ["coding", "programming", "debugging"],
        "author": "Open Swarm Team",
        "version": "1.0.0",
        "difficulty": "beginner"
    },
    "gawd": {
        "name": "GAWD",
        "description": "General AI assistant for various tasks and conversations",
        "category": "ai_assistants",
        "tags": ["general", "conversation", "assistant"],
        "author": "Open Swarm Team",
        "version": "1.0.0",
        "difficulty": "beginner"
    },
    "poets": {
        "name": "Poets",
        "description": "Creative writing and poetry generation assistant",
        "category": "content_creators",
        "tags": ["poetry", "writing", "creative"],
        "author": "Open Swarm Team",
        "version": "1.0.0",
        "difficulty": "beginner"
    },
    "echocraft": {
        "name": "EchoCraft",
        "description": "Message mirroring and UX demonstration tool",
        "category": "ai_assistants",
        "tags": ["demo", "echo", "ux"],
        "author": "Open Swarm Team",
        "version": "1.0.0",
        "difficulty": "beginner"
    },
    "stewie": {
        "name": "Stewie",
        "description": "WordPress content management with agent team coordination",
        "category": "web_services",
        "tags": ["wordpress", "cms", "team"],
        "author": "Open Swarm Team",
        "version": "1.0.0",
        "difficulty": "advanced"
    },
    "mission_improbable": {
        "name": "Mission Improbable",
        "description": "Database-driven mission management system",
        "category": "system_tools",
        "tags": ["database", "missions", "management"],
        "author": "Open Swarm Team",
        "version": "1.0.0",
        "difficulty": "intermediate"
    },
    "zeus": {
        "name": "Zeus",
        "description": "Powerful command-line interface for system operations",
        "category": "system_tools",
        "tags": ["cli", "system", "commands"],
        "author": "Open Swarm Team",
        "version": "1.0.0",
        "difficulty": "intermediate"
    },
    "chatbot": {
        "name": "Chatbot",
        "description": "General conversation and chat assistant",
        "category": "ai_assistants",
        "tags": ["chat", "conversation", "assistant"],
        "author": "Open Swarm Team",
        "version": "1.0.0",
        "difficulty": "beginner"
    },
    "omniplex": {
        "name": "Omniplex",
        "description": "Multi-agent coordination and task management",
        "category": "ai_assistants",
        "tags": ["multi-agent", "coordination", "tasks"],
        "author": "Open Swarm Team",
        "version": "1.0.0",
        "difficulty": "advanced"
    }
}

def get_user_blueprint_library() -> dict[str, Any]:
    """Get the user's personal blueprint library."""
    user_config_dir = get_user_config_dir_for_swarm()
    library_file = user_config_dir / "blueprint_library.json"

    if library_file.exists():
        try:
            with open(library_file) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading blueprint library: {e}")

    return {"installed": [], "custom": []}

def save_user_blueprint_library(library: dict[str, Any]) -> bool:
    """Save the user's blueprint library."""
    try:
        user_config_dir = get_user_config_dir_for_swarm()
        library_file = user_config_dir / "blueprint_library.json"

        # Ensure directory exists
        library_file.parent.mkdir(parents=True, exist_ok=True)

        with open(library_file, 'w') as f:
            json.dump(library, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving blueprint library: {e}")
        return False

@login_required
@require_GET
def blueprint_source_page(request, blueprint_name):
    """Pretty-printed blueprint source (Python highlighted), not the raw JSON API."""
    from swarm.views.api_views import load_blueprint_source, prism_language

    file_name = request.GET.get("file")
    payload, code = load_blueprint_source(blueprint_name, file_name)
    if code == 404:
        return render(
            request,
            "blueprint_source.html",
            {"error": (payload or {}).get("error") or "blueprint not found", "id": blueprint_name},
            status=404,
        )
    return render(request, "blueprint_source.html", {
        **payload,
        "prism_lang": prism_language(payload.get("selected")),
    })


@login_required
def blueprint_library(request):
    """Main blueprint library page - browse and manage blueprints (authenticated)."""
    try:
        # Get available blueprints
        discovered_metadata = discover_blueprints(BLUEPRINT_DIRECTORY)
        available_blueprints = list(discovered_metadata.keys())

        # Get user's library
        user_library = get_user_blueprint_library()
        installed_blueprints = user_library.get("installed", [])
        custom_blueprints = user_library.get("custom", [])

        # Prepare blueprint data with metadata
        blueprint_data = []
        for bp_name in available_blueprints:
            metadata = BLUEPRINT_METADATA.get(bp_name, {
                "name": bp_name.replace("_", " ").title(),
                "description": f"Blueprint for {bp_name}",
                "category": "ai_assistants",
                "tags": [],
                "author": "Open Swarm Team",
                "version": "1.0.0",
                "difficulty": "beginner"
            })

            blueprint_data.append({
                "id": bp_name,
                "name": metadata["name"],
                "description": metadata["description"],
                "category": metadata["category"],
                "category_info": BLUEPRINT_CATEGORIES.get(metadata["category"], {}),
                "tags": metadata["tags"],
                "author": metadata["author"],
                "version": metadata["version"],
                "difficulty": metadata["difficulty"],
                "installed": bp_name in installed_blueprints,
                "available": True
            })

        # Group by category
        blueprints_by_category = {}
        for bp in blueprint_data:
            category = bp["category"]
            if category not in blueprints_by_category:
                blueprints_by_category[category] = []
            blueprints_by_category[category].append(bp)

        context = {
            "blueprints_by_category": blueprints_by_category,
            "categories": BLUEPRINT_CATEGORIES,
            # total_available is the blueprint count; the template used to show
            # blueprints_by_category|length here, which is the CATEGORY count.
            "total_available": len(blueprint_data),
            "category_count": len(blueprints_by_category),
            "installed_count": len(installed_blueprints),
            "custom_count": len(custom_blueprints),
            "dark_mode": request.session.get('dark_mode', True),
            "github_marketplace_enabled": getattr(dj_settings, 'ENABLE_GITHUB_MARKETPLACE', False),
        }

        return render(request, "blueprint_library.html", context)

    except Exception as e:
        logger.error(f"Error loading blueprint library: {e}")
        return HttpResponse("Error loading blueprint library", status=500)

@login_required
def blueprint_requirements_status(_request):
    """Return JSON with MCP requirements vs current configuration per blueprint."""
    try:
        discovered = discover_blueprints(BLUEPRINT_DIRECTORY)
        config = load_active_config()
        mcp_config = config.get("mcpServers", {}) if isinstance(config, dict) else {}

        results = []
        for key, info in discovered.items():
            metadata = info.get("metadata", {})
            required = metadata.get("required_mcp_servers") or []
            env_vars = metadata.get("env_vars") or []
            compliance = evaluate_mcp_compliance(required, mcp_config, blueprint_env_vars=env_vars)
            results.append({
                "id": key,
                "name": metadata.get("name", key),
                "required_mcp_servers": required,
                "env_vars": env_vars,
                "compliance": compliance,
            })

        return JsonResponse({"blueprints": results})
    except Exception as e:
        logger.error(f"Error generating blueprint requirements status: {e}", exc_info=True)
        return JsonResponse({"error": "Internal server error"}, status=500)

@login_required
def add_blueprint_to_library(request, blueprint_name):
    """Add a blueprint to the user's library (authenticated)."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        # Verify blueprint exists
        discovered_metadata = discover_blueprints(BLUEPRINT_DIRECTORY)
        if blueprint_name not in discovered_metadata:
            return JsonResponse({"error": "Blueprint not found"}, status=404)

        # Get current library
        library = get_user_blueprint_library()

        # Add to installed if not already there
        if blueprint_name not in library["installed"]:
            library["installed"].append(blueprint_name)

            # Save library
            if save_user_blueprint_library(library):
                return JsonResponse({
                    "success": True,
                    "message": f"Blueprint '{blueprint_name}' added to library"
                })
            else:
                return JsonResponse({"error": "Failed to save library"}, status=500)
        else:
            return JsonResponse({
                "success": True,
                "message": f"Blueprint '{blueprint_name}' already in library"
            })

    except Exception as e:
        logger.error(f"Error adding blueprint to library: {e}")
        return JsonResponse({"error": "Internal server error"}, status=500)

@login_required
def remove_blueprint_from_library(request, blueprint_name):
    """Remove a blueprint from the user's library (authenticated)."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        # Get current library
        library = get_user_blueprint_library()

        # Remove from installed
        if blueprint_name in library["installed"]:
            library["installed"].remove(blueprint_name)

            # Save library
            if save_user_blueprint_library(library):
                return JsonResponse({
                    "success": True,
                    "message": f"Blueprint '{blueprint_name}' removed from library"
                })
            else:
                return JsonResponse({"error": "Failed to save library"}, status=500)
        else:
            return JsonResponse({
                "success": True,
                "message": f"Blueprint '{blueprint_name}' not in library"
            })

    except Exception as e:
        logger.error(f"Error removing blueprint from library: {e}")
        return JsonResponse({"error": "Internal server error"}, status=500)

@login_required
def blueprint_creator(request):
    """LLM-powered blueprint creator form (authenticated)."""
    if request.method == "GET":
        from swarm.core.blueprint_spec import BLUEPRINT_INTERFACE, BLUEPRINT_ONE_LINER

        context = {
            "categories": BLUEPRINT_CATEGORIES,
            "dark_mode": request.session.get('dark_mode', True),
            "blueprint_one_liner": BLUEPRINT_ONE_LINER,
            "blueprint_interface": BLUEPRINT_INTERFACE,
        }
        return render(request, "blueprint_creator.html", context)

    elif request.method == "POST":
        try:
            # Get form data
            blueprint_name = request.POST.get("blueprint_name", "").strip()
            description = request.POST.get("description", "").strip()
            category = request.POST.get("category", "ai_assistants")
            tags = request.POST.get("tags", "").strip()
            requirements = request.POST.get("requirements", "").strip()

            # Validate required fields
            if not blueprint_name or not description:
                return JsonResponse({
                    "error": "Blueprint name and description are required"
                }, status=400)

            assist = bool(requirements) and not os.environ.get("PYTEST_CURRENT_TEST")
            blueprint_code = generate_blueprint_code(
                blueprint_name, description, category, tags, requirements, assist=assist,
                kind=(request.POST.get("kind") or "api").strip() or None,
            )

            # Generate avatar if requested and ComfyUI is available
            avatar_path = None
            avatar_style = request.POST.get("avatar_style", "professional")
            generate_avatar = request.POST.get("generate_avatar", "false").lower() == "true"

            if generate_avatar and comfyui_client.is_available():
                avatar_path = comfyui_client.generate_avatar(
                    blueprint_name, description, category, avatar_style
                )

            # Persist under XDG user blueprints (discoverable when enabled) and
            # keep the JSON library catalog for My Blueprints UI.
            blueprint_id = _safe_agent_blueprint_id(blueprint_name)
            user_blueprints_dir = get_user_blueprints_dir()
            root = user_blueprints_dir.resolve()
            bp_dir = (user_blueprints_dir / blueprint_id).resolve()
            if bp_dir != root and root not in bp_dir.parents:
                return JsonResponse({"error": "Invalid blueprint name."}, status=400)
            bp_dir.mkdir(parents=True, exist_ok=True)
            blueprint_file = bp_dir / f"blueprint_{blueprint_id}.py"
            blueprint_file.write_text(blueprint_code)
            abs_path = str(blueprint_file.resolve())

            library = get_user_blueprint_library()

            custom_blueprint = {
                "id": blueprint_id,
                "name": blueprint_name,
                "description": description,
                "category": category,
                "tags": [tag.strip() for tag in tags.split(",") if tag.strip()],
                "requirements": requirements,
                "code": blueprint_code,
                "path": abs_path,
                "avatar_path": avatar_path,
                "avatar_style": avatar_style if avatar_path else None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "author": "User Generated"
            }

            library["custom"].append(custom_blueprint)

            if save_user_blueprint_library(library):
                return JsonResponse({
                    "success": True,
                    "message": (
                        f"Blueprint '{blueprint_name}' created successfully. "
                        f"{_save_discovery_message()}"
                    ),
                    "blueprint": custom_blueprint,
                    "path": abs_path,
                    "blueprint_id": blueprint_id,
                })
            else:
                return JsonResponse({"error": "Failed to save blueprint"}, status=500)

        except Exception as e:
            logger.error(f"Error creating blueprint: {e}")
            return JsonResponse({"error": "Internal server error"}, status=500)

@login_required
def generate_avatar(request, blueprint_name):
    """Generate an avatar for an existing blueprint (authenticated)."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        # Get form data
        avatar_style = request.POST.get("avatar_style", "professional")

        # Get blueprint metadata
        metadata = BLUEPRINT_METADATA.get(blueprint_name)
        if not metadata:
            return JsonResponse({"error": "Blueprint not found"}, status=404)

        # Generate avatar
        avatar_path = comfyui_client.generate_avatar(
            metadata["name"],
            metadata["description"],
            metadata["category"],
            avatar_style
        )

        if avatar_path:
            return JsonResponse({
                "success": True,
                "message": f"Avatar generated successfully for {blueprint_name}",
                "avatar_path": avatar_path
            })
        else:
            return JsonResponse({
                "error": "Failed to generate avatar. Check ComfyUI configuration."
            }, status=500)

    except Exception as e:
        logger.error(f"Error generating avatar: {e}")
        return JsonResponse({"error": "Internal server error"}, status=500)

@login_required
def check_comfyui_status(_request):
    """Check if ComfyUI is available for avatar generation."""
    try:
        is_available = comfyui_client.is_available()
        return JsonResponse({
            "available": is_available,
            "enabled": comfyui_client.enabled,
            "styles": AVATAR_STYLES
        })
    except Exception as e:
        logger.error(f"Error checking ComfyUI status: {e}")
        return JsonResponse({
            "available": False,
            "enabled": False,
            "styles": AVATAR_STYLES
        })

def generate_blueprint_code(
    name: str,
    description: str,
    category: str,
    tags: list[str] | str,
    _requirements: str,
    assist: bool = False,
    kind: str | None = "api",
) -> str:
    """Emit a blueprint module. Optionally draft `run()` via the default LLM.

    The static template subclasses a kind base resolved via
    ``base_class_for_kind`` (ADR-005 §4: emit a kind base by default).
    """
    if isinstance(tags, str):
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    else:
        tag_list = [str(t).strip() for t in tags if str(t).strip()]
    if assist and (_requirements or "").strip():
        from swarm.core.llm_assist import generate_blueprint_class
        from swarm.views.agent_creator_views import validator as blueprint_validator

        draft = generate_blueprint_class(
            name=name,
            description=description,
            requirements=_requirements,
            category=category,
            tags=tag_list,
        )
        if draft:
            check = blueprint_validator.validate_blueprint_code(draft)
            if check.get("valid"):
                return draft
    class_name = f'{name.replace(" ", "")}Blueprint'
    blueprint_id = name.lower().replace(" ", "_")
    req_note = (_requirements or "").strip()
    req_literal = repr(
        ("\nRequirements:\n" + req_note) if req_note else ""
    ).replace("{", "{{").replace("}", "}}")
    base_class = base_class_for_kind(kind)

    return f'''#!/usr/bin/env python3
"""
{name} Blueprint
{description}

Generated by Open Swarm Blueprint Creator
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any, ClassVar

from openai import AsyncOpenAI

from swarm.core.kind_bases import {base_class}


class {class_name}({base_class}):
    """{description}"""

    metadata: ClassVar[dict[str, Any]] = {{
        "name": {repr(name)},
        "description": {repr(description)},
        "category": {repr(category)},
        "tags": {repr(tag_list)},
        "author": "User Generated",
        "version": "1.0.0",
    }}

    def __init__(
        self,
        blueprint_id: str | None = None,
        config_path: str | None = None,
        **kwargs: Any,
    ):
        super().__init__(
            blueprint_id or {repr(blueprint_id)},
            config_path=config_path,
            **kwargs,
        )

    async def run(
        self, messages: list[dict[str, Any]], **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield OpenAI-style message chunks for /v1/chat/completions."""
        user_message = messages[-1].get("content", "") if messages else ""
        system = {{
            "role": "system",
            "content": (
                f"You are {{self.metadata.get('name')}}. "
                f"{{self.metadata.get('description')}}"
                + {req_literal}
            ),
        }}
        llm_messages = [system, *messages] if messages else [system]

        try:
            profile = self.get_llm_profile(self.llm_profile_name)
            base_url = profile.get("base_url") or os.getenv("LITELLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
            api_key = (
                profile.get("api_key")
                or os.getenv("LITELLM_API_KEY")
                or os.getenv("OPENAI_API_KEY")
                or "ollama"
            )
            model_name = (
                profile.get("model")
                or os.getenv("LITELLM_MODEL")
                or os.getenv("DEFAULT_LLM")
                or os.getenv("OPENAI_MODEL")
            )
            if not model_name:
                raise RuntimeError(
                    "No model configured. Set llm profile model or LITELLM_MODEL/DEFAULT_LLM."
                )

            client_kwargs: dict[str, Any] = {{"api_key": api_key}}
            if base_url:
                client_kwargs["base_url"] = base_url
            client = AsyncOpenAI(**client_kwargs)
            stream = await client.chat.completions.create(
                model=model_name,
                messages=llm_messages,
                stream=True,
            )
            yielded = False
            async for chunk in stream:
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                delta = getattr(choices[0], "delta", None)
                content = getattr(delta, "content", None) if delta is not None else None
                if content:
                    yielded = True
                    yield {{
                        "messages": [{{
                            "role": "assistant",
                            "content": content,
                        }}]
                    }}
            if yielded:
                return
            raise RuntimeError("LLM stream returned no content")
        except Exception as exc:
            yield {{
                "messages": [{{
                    "role": "assistant",
                    "content": (
                        f"[{{self.metadata.get('name')}}] WARNING: LLM call failed "
                        f"({{exc}}); falling back to echo.\\n\\n"
                        f"{{self.metadata.get('description')}}\\n\\n"
                        f"You said: {{user_message}}"
                    ),
                }}]
            }}
'''

@login_required
def my_blueprints(request):
    """Show user's installed and custom blueprints (authenticated)."""
    try:
        library = get_user_blueprint_library()
        installed = library.get("installed", [])
        custom = library.get("custom", [])

        # Get metadata for installed blueprints
        installed_data = []
        for bp_name in installed:
            metadata = BLUEPRINT_METADATA.get(bp_name, {
                "name": bp_name.replace("_", " ").title(),
                "description": f"Blueprint for {bp_name}",
                "category": "ai_assistants"
            })
            installed_data.append({
                "id": bp_name,
                "name": metadata["name"],
                "description": metadata["description"],
                "category": metadata["category"],
                "category_info": BLUEPRINT_CATEGORIES.get(metadata["category"], {}),
                "type": "installed"
            })

        # Normalize created_at for display: older records stored a filesystem
        # path (a leak); new ones store an ISO timestamp. Show a friendly date
        # for valid timestamps and nothing for anything else (never a raw path).
        for bp in custom:
            raw = bp.get("created_at")
            display = None
            if isinstance(raw, str):
                try:
                    display = datetime.fromisoformat(raw).strftime("%b %d, %Y")
                except ValueError:
                    display = None
            bp["created_display"] = display

        # Compute stat counts in the view: the template can't reliably add two
        # |length values (the old `|length|add:custom|length` chain produced 0),
        # which is why "Total" rendered 0 even with custom blueprints present.
        installed_count = len(installed_data)
        custom_count = len(custom)
        context = {
            "installed_blueprints": installed_data,
            "custom_blueprints": custom,
            "installed_count": installed_count,
            "custom_count": custom_count,
            "total_count": installed_count + custom_count,
            "categories": BLUEPRINT_CATEGORIES,
            "dark_mode": request.session.get('dark_mode', True),
        }

        return render(request, "my_blueprints.html", context)

    except Exception as e:
        logger.error(f"Error loading my blueprints: {e}")
        return HttpResponse("Error loading blueprints", status=500)
