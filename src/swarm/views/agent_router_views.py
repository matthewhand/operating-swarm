"""
Agent Router API Views

API endpoints for the agent router blueprint that provides:
1. List of agents with metadata for sidebar display
2. Single endpoint for grouped agent inference
3. Routing capabilities between agent personas
"""

import json
from typing import Any

from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from swarm.blueprints.agent_router import AgentRouterBlueprint

# Initialize the agent router blueprint
agent_router = AgentRouterBlueprint()


def get_agent_router_blueprint():
    """Get or create the agent router blueprint instance."""
    return agent_router


@require_http_methods(["GET"])
def list_agents(request):
    """
    List all available agents in the router with their metadata.
    
    Returns:
        JSON: {
            "agents": [
                {
                    "agent_id": "researcher",
                    "name": "Researcher",
                    "specialty": "information gathering and analysis",
                    "color": "#3b82f6",
                    "icon": "🔍",
                    "type": "specialist"
                },
                ...
            ],
            "router": "router",
            "handoff_rules": [...]
        }
    """
    try:
        blueprint = get_agent_router_blueprint()
        agent_info = blueprint.get_agent_info()
        
        return JsonResponse({
            "status": "success",
            "data": agent_info,
            "blueprint_name": "agent_router"
        })
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "error": str(e),
            "blueprint_name": "agent_router"
        }, status=500)


@require_http_methods(["GET"])
def get_routing_options(request):
    """
    Get available routing options and strategies.
    
    Returns:
        JSON: {
            "routing_strategies": [...],
            "agents": [...]
        }
    """
    try:
        blueprint = get_agent_router_blueprint()
        routing_options = blueprint.get_routing_options()
        
        return JsonResponse({
            "status": "success",
            "data": routing_options
        })
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "error": str(e)
        }, status=500)


import concurrent.futures
import asyncio

def _run_sync(coro):
    """Run an async coroutine synchronously and return the result."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
        
    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()
    else:
        return asyncio.run(coro)


@csrf_exempt
@require_http_methods(["POST"])
def route_message(request):
    """
    Route a message to the appropriate agent based on routing strategy.
    
    Request body:
        {
            "message": "The user message to process",
            "routing_strategy": "auto_route|direct|router|consensus",
            "target_agent": "agent_id (for direct strategy)",
            "agent_ids": ["researcher", "analyst"], // optional for consensus
            "context": {}, // optional context
            "stream": false,
            "params": {}
        }
    
    Returns:
        JSON: {
            "status": "success",
            "agent": "agent_name",
            "response": "agent response",
            "routing_decision": {"strategy": "...", "target_agent": "..."},
            "consensus_data": {...} // optional
        }
    """
    routing_strategy = "auto_route"
    target_agent = None
    try:
        # Parse request body
        body = json.loads(request.body)
        message = body.get("message", "")
        routing_strategy = body.get("routing_strategy", "auto_route")
        target_agent = body.get("target_agent")
        stream_val = body.get("stream", False)
        stream_param = request.GET.get("stream", "").lower() in ("true", "1")
        if isinstance(stream_val, str):
            stream_body = stream_val.lower() in ("true", "1")
        else:
            stream_body = bool(stream_val)
        stream = stream_body or stream_param
        params = dict(body.get("params", {}))
        
        if not message:
            return JsonResponse({
                "status": "error",
                "error": "Message is required"
            }, status=400)

        from swarm.core.session_modes import apply_session_mode, normalize_session_mode

        session_mode = normalize_session_mode(
            params.get("session_mode") or body.get("session_mode")
        )
        params["session_mode"] = session_mode
        message = apply_session_mode(message, session_mode)
            
        blueprint = get_agent_router_blueprint()
        
        # Configure params for the blueprint
        params["routing_strategy"] = routing_strategy
        if body.get("agent_ids"):
            params["agent_ids"] = body.get("agent_ids")
        if body.get("context"):
            params["context"] = body.get("context")
            
        if routing_strategy == "direct" and target_agent:
            params["target_agent"] = target_agent
            
        blueprint.set_params(params)
            
        # Prepare messages
        messages = [{"role": "user", "content": message}]
        if body.get("context"):
            messages.insert(0, {"role": "system", "content": f"Context: {json.dumps(body['context'])}"})
        
        # Determine routing summary based on strategy
        if routing_strategy == "consensus":
            selected_agent = "Consensus Panel"
        elif routing_strategy == "direct" and target_agent:
            selected_agent = target_agent
        elif routing_strategy == "auto_route":
            selected_agent = blueprint.route_message(message)
        else:
            selected_agent = "router"

        # Stream response via SSE. Collect on a sync iterator — Django's
        # StreamingHttpResponse wraps content in map() and cannot async-for
        # an async generator (wedges Daphne's thread pool / WebSockets).
        if stream:
            async def collect_sse():
                lines: list[str] = []
                try:
                    async for chunk in blueprint.run(messages, stream=True):
                        if isinstance(chunk, dict):
                            content = chunk.get("content", "")
                            agent = chunk.get("agent", selected_agent)
                            chunk_data = {"content": content, "agent": agent}
                            if "consensus_data" in chunk:
                                chunk_data["consensus_data"] = chunk["consensus_data"]
                            if "role" in chunk:
                                chunk_data["role"] = chunk["role"]
                        elif isinstance(chunk, str):
                            chunk_data = {"content": chunk, "agent": selected_agent}
                        else:
                            chunk_data = {"content": str(chunk), "agent": selected_agent}
                        lines.append(f"data: {json.dumps(chunk_data)}\n\n")
                    lines.append("data: [DONE]\n\n")
                except Exception as e:
                    err_data = {"error": str(e), "agent": selected_agent}
                    lines.append(f"data: {json.dumps(err_data)}\n\n")
                    lines.append("data: [DONE]\n\n")
                return lines

            payloads = _run_sync(collect_sse())

            def event_stream():
                for line in payloads:
                    yield line

            return StreamingHttpResponse(event_stream(), content_type="text/event-stream")
            
        # Run the blueprint non-streaming
        async def collect_responses():
            res = []
            async for chunk in blueprint.run(messages, stream=stream):
                res.append(chunk)
            return res

        collected_responses = _run_sync(collect_responses())
        
        # Prepare response
        response_data = {
            "status": "success",
            "routing_decision": {
                "strategy": routing_strategy,
                "target_agent": selected_agent,
                "message": f"Routed to {selected_agent} using {routing_strategy} strategy"
            },
            "responses": collected_responses
        }
        
        if collected_responses:
            for item in collected_responses:
                if isinstance(item, dict) and "consensus_data" in item:
                    response_data["consensus_data"] = item["consensus_data"]
            first_resp = collected_responses[0]
            if isinstance(first_resp, dict):
                from swarm.core.model_text import is_usable_model_text, sanitize_model_text

                raw = first_resp.get("content", "") or ""
                cleaned = sanitize_model_text(raw)
                if not is_usable_model_text(cleaned):
                    cleaned = (
                        cleaned
                        or "The model returned no usable text "
                        "(empty, stubs, or leaked control sequences)."
                    )
                response_data["response"] = cleaned
                response_data["agent"] = first_resp.get("agent", selected_agent)
            
        return JsonResponse(response_data)
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "error": "Invalid JSON in request body"
        }, status=400)
    except Exception as e:
        return JsonResponse({
            "status": "error", 
            "error": str(e),
            "routing_decision": {"strategy": routing_strategy, "target_agent": target_agent or "unknown"}
        }, status=500)


@require_http_methods(["GET"])
def get_agent_info(request, agent_id):
    """
    Get detailed information about a specific agent.
    
    Args:
        agent_id: The ID of the agent to get info about
        
    Returns:
        JSON: {
            "status": "success",
            "agent": {
                "agent_id": "...",
                "name": "...",
                "specialty": "...",
                "color": "...",
                "icon": "...",
                "type": "..."
            }
        }
    """
    try:
        blueprint = get_agent_router_blueprint()
        agents = blueprint.list_agents()
        
        # Find the agent by ID
        agent_info = None
        for agent in agents:
            if agent["agent_id"] == agent_id:
                agent_info = agent
                break
                
        if not agent_info:
            return JsonResponse({
                "status": "error",
                "error": f"Agent '{agent_id}' not found"
            }, status=404)
            
        return JsonResponse({
            "status": "success",
            "agent": agent_info
        })
        
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "error": str(e)
        }, status=500)


@csrf_exempt  
@require_http_methods(["POST"])
def send_to_agent(request, agent_id):
    """
    Send a message directly to a specific agent.
    
    Args:
        agent_id: The ID of the target agent
        
    Request body:
        {
            "message": "The message to send",
            "context": "Optional context",
            "stream": false
        }
        
    Returns:
        JSON: {
            "status": "success",
            "agent": "...",
            "response": "...",
            "agent_id": "..."
        }
    """
    try:
        # Parse request body
        body = json.loads(request.body)
        message = body.get("message", "")
        context = body.get("context", "")
        stream = body.get("stream", False)
        
        if not message:
            return JsonResponse({
                "status": "error", 
                "error": "Message is required"
            }, status=400)
            
        blueprint = get_agent_router_blueprint()
        
        # Check if agent exists
        agents = blueprint.list_agents()
        agent_exists = any(agent["agent_id"] == agent_id for agent in agents)
        
        if not agent_exists:
            return JsonResponse({
                "status": "error",
                "error": f"Agent '{agent_id}' not found"
            }, status=404)
            
        # Set params to target this specific agent
        params = {"routing_strategy": "direct", "target_agent": agent_id}
        if context:
            params["context"] = context
            
        blueprint.set_params(params)
        
        # Prepare messages
        messages = [{"role": "user", "content": message}]
        if context:
            messages.insert(0, {"role": "system", "content": f"Context: {context}"})
            
        # Run the blueprint
        collected_responses = []
        
        async def collect_responses():
            import asyncio
            async for chunk in blueprint.run(messages, stream=stream):
                collected_responses.append(chunk)
                
        # Run async function synchronously
        from swarm.core.async_utils import run_coro_sync
        run_coro_sync(collect_responses())
        
        if not collected_responses:
            return JsonResponse({
                "status": "error",
                "error": "No response from agent"
            }, status=500)
            
        # Prepare response
        response_data = {
            "status": "success",
            "agent_id": agent_id,
            "agent": next((a["name"] for a in agents if a["agent_id"] == agent_id), "Unknown"),
            "responses": collected_responses
        }
        
        if collected_responses and len(collected_responses) == 1:
            response_data["response"] = collected_responses[0].get("content", "")
            
        return JsonResponse(response_data)
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error", 
            "error": "Invalid JSON in request body"
        }, status=400)
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "error": str(e),
            "agent_id": agent_id
        }, status=500)


@require_http_methods(["GET"])
def get_agent_status_view(request, agent_id):
    """Get operational status and context for an agent."""
    try:
        blueprint = get_agent_router_blueprint()
        status_info = _run_sync(blueprint.get_agent_status(agent_id))
        return JsonResponse({
            "status": "success",
            "data": status_info
        })
    except KeyError:
        return JsonResponse({
            "status": "error",
            "error": f"Agent '{agent_id}' not found"
        }, status=404)
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "error": str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def delegate_agent_view(request, agent_id):
    """
    Delegate a task to target agent_id from another agent.
    
    Request body:
        {
            "from_agent": "router|researcher|...",
            "message": "Task description",
            "context": {}
        }
    """
    try:
        body = json.loads(request.body)
        from_agent = body.get("from_agent", "router")
        message = body.get("message", "")
        context = body.get("context", {})

        if not message:
            return JsonResponse({
                "status": "error",
                "error": "Message is required for delegation"
            }, status=400)

        blueprint = get_agent_router_blueprint()
        result = _run_sync(blueprint.delegate_to_agent(
            from_agent=from_agent,
            to_agent=agent_id,
            message=message,
            context=context
        ))
        return JsonResponse({
            "status": "success",
            "data": result
        })
    except KeyError as e:
        return JsonResponse({
            "status": "error",
            "error": str(e)
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "error": "Invalid JSON in request body"
        }, status=400)
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "error": str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def agent_conversations_view(request):
    """List or initiate conversations with agents."""
    blueprint = get_agent_router_blueprint()
    if request.method == "GET":
        return JsonResponse({
            "status": "success",
            "conversations": blueprint.list_conversations()
        })
    
    try:
        body = json.loads(request.body)
        agent_id = body.get("agent_id")
        message = body.get("message", "")
        if not agent_id or not message:
            return JsonResponse({
                "status": "error",
                "error": "agent_id and message are required"
            }, status=400)

        conv = _run_sync(blueprint.start_conversation(agent_id, message))
        return JsonResponse({
            "status": "success",
            "conversation": conv
        })
    except KeyError as e:
        return JsonResponse({
            "status": "error",
            "error": str(e)
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "error": "Invalid JSON in request body"
        }, status=400)
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "error": str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def agent_context_view(request, agent_id):
    """Get or update context for a specific agent."""
    blueprint = get_agent_router_blueprint()
    try:
        if request.method == "GET":
            ctx = _run_sync(blueprint.get_agent_context(agent_id))
            return JsonResponse({
                "status": "success",
                "agent_id": agent_id,
                "context": ctx
            })
        
        body = json.loads(request.body)
        context_data = body.get("context", {})
        _run_sync(blueprint.set_agent_context(agent_id, context_data))
        return JsonResponse({
            "status": "success",
            "agent_id": agent_id,
            "message": "Context updated successfully"
        })
    except KeyError:
        return JsonResponse({
            "status": "error",
            "error": f"Agent '{agent_id}' not found"
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "error": "Invalid JSON in request body"
        }, status=400)
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "error": str(e)
        }, status=500)


@require_http_methods(["GET"])
def agent_delegations_view(request):
    """List inter-agent delegation events for communication popups and audit timelines."""
    blueprint = get_agent_router_blueprint()
    return JsonResponse({
        "status": "success",
        "delegations": blueprint.get_delegations()
    })


@csrf_exempt
@require_http_methods(["POST"])
def generate_agent_quickstarts(request):
    """Rewrite the four onboarding pills for an agent via the default LLM."""
    from swarm.core.llm_assist import generate_quickstarts

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        body = {}
    name = str((body or {}).get("name") or "").strip()[:80]
    system_prompt = str((body or {}).get("system_prompt") or (body or {}).get("purpose") or "").strip()[:4000]
    items = generate_quickstarts(name or "this agent", system_prompt)
    return JsonResponse({"status": "success", "quickstarts": items})


@require_http_methods(["GET"])
def list_remote_catalog(request):
    """Remote agentic frameworks that can sit on the team like any other agent."""
    from swarm.core.remote_teams import catalog_frameworks

    return JsonResponse({"status": "success", "frameworks": catalog_frameworks()})


@csrf_exempt
@require_http_methods(["POST"])
def launch_remote_framework(request):
    """Start a local remote framework (currently DeepSeek Harness via ollama launch dsh)."""
    from swarm.core.remote_teams import launch_dsh, normalize_framework

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        body = {}
    fid = normalize_framework(str((body or {}).get("framework") or "dsh")) or "dsh"
    if fid != "dsh":
        return JsonResponse(
            {"status": "error", "error": f"no launcher for framework {fid}"},
            status=400,
        )
    result = launch_dsh()
    status = 200 if result.get("ok") else 503
    return JsonResponse({"status": "success" if result.get("ok") else "error", **result}, status=status)


@require_http_methods(["GET"])
def list_llm_profiles(request):
    """Named LLM profiles from the #776 swarm_config SoT (never secrets)."""
    from swarm.core.remotes import load_raw_config
    from swarm.settings import ENABLE_API_AUTH
    from swarm.utils.env_utils import get_default_llm

    profiles = []
    seen = set()
    default_name = get_default_llm() or ""
    try:
        cfg, _path = load_raw_config()
        llm = cfg.get("llm") if isinstance(cfg, dict) else {}
        if not isinstance(llm, dict):
            llm = {}
        settings = cfg.get("settings") if isinstance(cfg.get("settings"), dict) else {}
        if not default_name:
            default_name = str(settings.get("default_llm_profile") or "")
        iterable = llm.get("profiles") if isinstance(llm.get("profiles"), dict) else llm
        if not isinstance(iterable, dict):
            iterable = {}
        for name, data in iterable.items():
            if name in seen or name == "profiles" or not isinstance(data, dict):
                continue
            if not data.get("provider") and not data.get("model"):
                continue
            seen.add(name)
            profiles.append({
                "name": name,
                "provider": data.get("provider") or "litellm",
                "model": data.get("model") or name,
                "base_url": data.get("base_url") or "",
                "description": data.get("description") or "",
            })
    except Exception:
        profiles = []
    if not default_name and profiles:
        default_name = next((p["name"] for p in profiles if p["name"] in ("auxiliary", "default")), profiles[0]["name"])
    return JsonResponse({
        "status": "success",
        "default": default_name,
        "profiles": profiles,
        "auth_required": bool(ENABLE_API_AUTH),
    })


@require_http_methods(["GET"])
def list_cli_catalog(request):
    """Catalog CLIs the designer can attach to a simple (non-openai-agents) agent."""
    from swarm.core.cli_catalog import CLI_MODELS, CATALOG, MODEL_FLAG, catalog_names, installed_catalog_clis

    installed = set(installed_catalog_clis())
    clis = []
    for name in catalog_names():
        exe = CATALOG[name]["cmd"][0]
        clis.append({
            "name": name,
            "executable": exe,
            "installed": name in installed,
            "model_flag": MODEL_FLAG.get(name) or "",
            "models": list(CLI_MODELS.get(name) or []),
        })
    return JsonResponse({"status": "success", "clis": clis})


@require_http_methods(["GET"])
def list_designed_agents(request):
    """Fast rail feed of designer-created agents.

    Reads the designs file directly (no blueprint init), so the sidebar can
    list designed agents without paying the slow /v1/agents/ startup.
    """
    from swarm.core.router_designs import load_designs

    designs = load_designs()
    return JsonResponse({"object": "list", "data": designs})


@csrf_exempt
@require_http_methods(["POST"])
def create_designed_agent(request):
    """Create a Swarm agent: personality, openai-agents swarm, or CLI."""
    from swarm.core.router_designs import upsert_design

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "error": "Invalid JSON"}, status=400)
    try:
        spec = upsert_design(body)
    except ValueError as exc:
        return JsonResponse({"status": "error", "error": str(exc)}, status=400)
    blueprint = get_agent_router_blueprint()
    if spec.get("kind") == "remote":
        cfg = dict(blueprint._config or {}) if isinstance(blueprint._config, dict) else {}
        fid = spec.get("framework") or spec.get("agent_id")
        if fid:
            teams = dict(cfg.get("remote_teams") or {})
            entry = dict(teams.get(fid) or {})
            if spec.get("base_url"):
                entry["base_url"] = spec["base_url"]
            if spec.get("model"):
                entry["model"] = spec["model"]
            if spec.get("target"):
                entry["target"] = spec["target"]
            if spec.get("name"):
                entry["name"] = spec["name"]
            teams[fid] = entry
            cfg["remote_teams"] = teams
            blueprint._config = cfg
    blueprint.load_designed_agents()
    return JsonResponse({"status": "success", "agent": spec}, status=201)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_designed_agent(request, agent_id: str):
    """Remove a designer-created agent. Built-in agents cannot be deleted."""
    from swarm.core.router_designs import RESERVED_IDS, delete_design

    if agent_id in RESERVED_IDS:
        return JsonResponse(
            {"status": "error", "error": "Built-in agents cannot be deleted"},
            status=400,
        )
    if not delete_design(agent_id):
        return JsonResponse({"status": "error", "error": "Agent not found"}, status=404)
    blueprint = get_agent_router_blueprint()
    blueprint.load_designed_agents()
    return JsonResponse({"status": "success", "agent_id": agent_id})