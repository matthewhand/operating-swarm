"""
Web views for creating custom agents and teams with Python code validation
"""
import ast
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from swarm.core import paths
from swarm.core.kind_bases import ALLOWED_BLUEPRINT_BASE_NAMES, base_class_for_kind

# Shared ban list for creator write paths (agent + team swarm saves).
_BANNED_CODE_SNIPPETS = ("__import__", "subprocess", "os.system", "eval(", "exec(")


def _banned_snippet_error(text: str) -> str | None:
    """Substring ban for free-text prompts and source (no AST — text need not be Python)."""
    lowered = text.lower()
    for banned in _BANNED_CODE_SNIPPETS:
        if banned in lowered:
            return (
                f"Saved blueprints may not contain {banned!r} "
                "(unsandboxed exec blocked)."
            )
    return None


def _banned_code_error(code: str) -> str | None:
    """Return an error message if blueprint *source* is unsafe.

    Substring ban list first, then AST sandbox (full Python module only).
    """
    snippet = _banned_snippet_error(code)
    if snippet:
        return snippet
    try:
        from swarm.core.blueprint_sandbox import assert_safe_blueprint_source
        assert_safe_blueprint_source(code)
    except ValueError as exc:
        return str(exc)
    return None


def _user_blueprint_discovery_enabled() -> bool:
    """True when operators opted into scanning get_user_blueprints_dir()."""
    return os.getenv("SWARM_ALLOW_USER_BLUEPRINT_DISCOVERY", "").lower() in (
        "true", "1", "yes", "y", "t",
    )


def _save_discovery_message() -> str:
    """Explain runnability of saved blueprints based on discovery flag."""
    if _user_blueprint_discovery_enabled():
        return (
            "User blueprint discovery is enabled "
            "(SWARM_ALLOW_USER_BLUEPRINT_DISCOVERY); "
            "the blueprint should appear after a reload."
        )
    return (
        "Saved under the user blueprints directory (write-only until discovery "
        "is enabled). Set SWARM_ALLOW_USER_BLUEPRINT_DISCOVERY=true to make "
        "saved blueprints discoverable/runnable."
    )


class BlueprintCodeValidator:
    """Validates generated blueprint code using Python AST parsing and linting"""

    def __init__(self):
        # Kind bases (ADR-005) or low-level BlueprintBase, plus async run().
        # Typing imports (AsyncGenerator, Any) are optional.
        self.required_imports = list(ALLOWED_BLUEPRINT_BASE_NAMES)
        self.required_methods = ['run']
        self.required_attributes = ['metadata']

    def validate_syntax(self, code: str) -> tuple[bool, list[str]]:
        """Validate Python syntax using AST"""
        errors = []
        try:
            ast.parse(code)
            return True, []
        except SyntaxError as e:
            errors.append(f"Syntax Error: {e.msg} at line {e.lineno}")
            return False, errors

    def validate_structure(self, code: str) -> tuple[bool, list[str]]:
        """Validate blueprint structure requirements"""
        errors = []
        warnings = []

        try:
            tree = ast.parse(code)

            # Check for required imports
            imports_found = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.names:
                        for alias in node.names:
                            imports_found.append(alias.name)
                elif isinstance(node, ast.Import) and node.names:
                    for alias in node.names:
                        imports_found.append(alias.name)

            if not any(
                required in found
                for required in self.required_imports
                for found in imports_found
            ):
                errors.append(
                    "Missing required import: ApiKindBase, CliKindBase, "
                    "RemoteKindBase, or BlueprintBase"
                )

            # Check for blueprint class
            blueprint_class = None
            allowed = set(self.required_imports)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for base in node.bases:
                        if isinstance(base, ast.Name) and base.id in allowed:
                            blueprint_class = node
                            break

            if not blueprint_class:
                errors.append(
                    "No class found that inherits from a kind base "
                    "(ApiKindBase / CliKindBase / RemoteKindBase) or BlueprintBase"
                )
                return False, errors

            # Check for required methods
            methods_found = []
            for node in blueprint_class.body:
                if isinstance(node, ast.AsyncFunctionDef):
                    methods_found.append(node.name)

            for required_method in self.required_methods:
                if required_method not in methods_found:
                    errors.append(f"Missing required async method: {required_method}")

            # Check for metadata attribute (plain assign or annotated ClassVar)
            has_metadata = False
            for node in blueprint_class.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == 'metadata':
                            has_metadata = True
                            break
                elif (
                    isinstance(node, ast.AnnAssign)
                    and isinstance(node.target, ast.Name)
                    and node.target.id == 'metadata'
                ):
                    has_metadata = True

            if not has_metadata:
                warnings.append("Missing metadata attribute (recommended)")

            return len(errors) == 0, errors + warnings

        except Exception as e:
            errors.append(f"Structure validation error: {str(e)}")
            return False, errors

    def lint_code(self, code: str) -> tuple[bool, list[str]]:
        """Run flake8 on the code"""
        issues = []
        temp_file = None

        try:
            # Write code to temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_file = f.name

            # Run flake8 (lighter than pylint)
            result = subprocess.run(
                ['flake8', '--select=E,W,F', '--ignore=E501,W503', temp_file],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                for line in result.stdout.split('\n'):
                    if line.strip():
                        # Parse flake8 output: filename:line:col: code message
                        parts = line.split(':', 3)
                        if len(parts) >= 4:
                            issues.append(f"Line {parts[1]}: {parts[3].strip()}")

            return len(issues) == 0, issues

        except subprocess.TimeoutExpired:
            issues.append("Code linting timed out")
            return False, issues
        except FileNotFoundError:
            # flake8 not installed, skip linting
            return True, ["Linting skipped (flake8 not available)"]
        except Exception as e:
            issues.append(f"Linting error: {str(e)}")
            return False, issues
        finally:
            # Always clean up, including on timeout/error paths.
            if temp_file:
                try:
                    Path(temp_file).unlink()
                except OSError:
                    pass

    def validate_blueprint_code(self, code: str) -> dict[str, Any]:
        """Complete validation of blueprint code"""
        results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'syntax_valid': False,
            'structure_valid': False,
            'lint_clean': False
        }

        # 1. Syntax validation
        syntax_ok, syntax_errors = self.validate_syntax(code)
        results['syntax_valid'] = syntax_ok
        if not syntax_ok:
            results['valid'] = False
            results['errors'].extend(syntax_errors)
            return results  # Stop here if syntax is invalid

        # 2. Structure validation
        structure_ok, structure_issues = self.validate_structure(code)
        results['structure_valid'] = structure_ok
        if not structure_ok:
            results['valid'] = False

        # Separate errors and warnings
        for issue in structure_issues:
            if "Missing required" in issue:
                results['errors'].append(issue)
            else:
                results['warnings'].append(issue)

        # 3. Linting
        lint_ok, lint_issues = self.lint_code(code)
        results['lint_clean'] = lint_ok
        if lint_issues:
            results['warnings'].extend(lint_issues)

        return results


class AgentPersonaGenerator:
    """Generates agent persona code based on user specifications"""

    def generate_agent_code(self, agent_spec: dict[str, Any]) -> str:
        """Emit a BlueprintBase async-generator template (AsyncOpenAI streaming)."""
        class_name = self._sanitize_class_name(agent_spec.get("name", "CustomAgent"))
        name = agent_spec.get("name", "Custom Agent")
        description = agent_spec.get("description", "A custom AI agent")
        personality = agent_spec.get("personality", "helpful and professional")
        expertise = agent_spec.get("expertise", ["general assistance"])
        if isinstance(expertise, list):
            expertise_str = ", ".join(expertise)
            expertise_list = expertise
        else:
            expertise_str = str(expertise)
            expertise_list = [str(expertise)]
        communication_style = agent_spec.get(
            "communication_style", "clear and concise"
        )
        instructions = agent_spec.get(
            "instructions", "Help the user with their request."
        )
        tags = agent_spec.get("tags", ["custom", "user-generated"])
        blueprint_id = name.lower().replace(" ", "_")
        persona_body = (
            f"Personality: {personality}\n"
            f"Expertise: {expertise_str}\n"
            f"Communication Style: {communication_style}\n\n"
            f"Instructions: {instructions}"
        )

        # ADR-005 §4: this template's run() is an AsyncOpenAI streaming
        # implementation, i.e. an API-kind harness — default to ApiKindBase.
        # An explicit spec kind must stay consistent with that body.
        base_class = base_class_for_kind(agent_spec.get("kind") or "api")

        return f'''#!/usr/bin/env python3
"""
{description}
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any, ClassVar

from openai import AsyncOpenAI

from swarm.core.kind_bases import {base_class}


class {class_name}({base_class}):
    """
    {description}
    """

    metadata: ClassVar[dict[str, Any]] = {{
        "name": {repr(name)},
        "description": {repr(description)},
        "version": "1.0.0",
        "author": "User Generated",
        "tags": {repr(tags)},
        "persona": {{
            "personality": {repr(personality)},
            "expertise": {repr(expertise_list)},
            "communication_style": {repr(communication_style)},
        }},
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
                f"You are {{self.metadata.get('name')}}, "
                f"{{self.metadata.get('description')}}\\n\\n"
                + {repr(persona_body)}
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

    def _sanitize_class_name(self, name: str) -> str:
        """Convert name to valid Python class name"""
        import re
        clean_name = re.sub(r"[^a-zA-Z0-9\s]", "", name)
        words = clean_name.split()
        return "".join(word.capitalize() for word in words) + "Blueprint"



# Global instances
validator = BlueprintCodeValidator()
agent_generator = AgentPersonaGenerator()


@login_required
def agent_creator_page(request):
    """Render the agent creator interface"""
    if request.method == 'GET':
        from swarm.core.blueprint_spec import BLUEPRINT_INTERFACE, BLUEPRINT_ONE_LINER

        context = {
            'page_title': 'Agent Creator',
            'blueprint_one_liner': BLUEPRINT_ONE_LINER,
            'blueprint_interface': BLUEPRINT_INTERFACE,
            'form_data': {
                'personality_options': [
                    'helpful and professional', 'creative and enthusiastic',
                    'analytical and precise', 'friendly and casual', 'expert and authoritative'
                ],
                'expertise_options': [
                    'coding', 'writing', 'analysis', 'research', 'design',
                    'mathematics', 'science', 'business', 'education', 'general'
                ],
                'communication_options': [
                    'clear and concise', 'detailed and thorough', 'casual and conversational',
                    'formal and structured', 'creative and expressive'
                ]
            }
        }
        return render(request, 'agent_creator.html', context)


@login_required
@require_http_methods(["POST"])
def generate_agent_code(request):
    """Generate agent code from form data (authenticated operator session)."""
    try:
        data = json.loads(request.body)

        # Validate required fields
        required_fields = ['name', 'description', 'instructions']
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }, status=400)

        generated_code = agent_generator.generate_agent_code(data)
        if data.get("assist") and not os.environ.get("PYTEST_CURRENT_TEST"):
            from swarm.core.llm_assist import generate_blueprint_class

            tags = data.get("tags") or ["custom"]
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            draft = generate_blueprint_class(
                name=data.get("name") or "CustomAgent",
                description=data.get("description") or "",
                requirements=data.get("instructions") or "",
                tags=list(tags),
            )
            if draft:
                check = validator.validate_blueprint_code(draft)
                if check.get("valid"):
                    generated_code = draft

        # Validate the generated code
        validation_result = validator.validate_blueprint_code(generated_code)

        return JsonResponse({
            'success': True,
            'code': generated_code,
            'validation': validation_result
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Code generation failed: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def validate_agent_code(request):
    """Validate user-provided agent code via AST only — never exec."""
    try:
        data = json.loads(request.body)
        code = data.get('code', '')

        if not code:
            return JsonResponse({
                'success': False,
                'error': 'No code provided'
            }, status=400)

        # Validate the code
        validation_result = validator.validate_blueprint_code(code)

        return JsonResponse({
            'success': True,
            'validation': validation_result
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Validation failed: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def save_custom_agent(request):
    """Save a custom agent blueprint (write-only; not executed on save).

    Generated code is **not** imported/exec'd on this path. Discovery of
    user-written blueprints requires ``SWARM_ALLOW_USER_BLUEPRINT_DISCOVERY``
    (see settings._blueprint_extra_dirs) so the default ship path never
    exec_module untrusted creator output.
    """
    try:
        data = json.loads(request.body)
        code = data.get('code', '')
        agent_name = data.get('name', '')

        if not code or not agent_name:
            return JsonResponse({
                'success': False,
                'error': 'Missing code or agent name'
            }, status=400)

        # Validate the code first (AST/structure only — no exec)
        validation_result = validator.validate_blueprint_code(code)
        if not validation_result['valid']:
            return JsonResponse({
                'success': False,
                'error': 'Code validation failed',
                'validation': validation_result
            }, status=400)

        banned = _banned_code_error(code)
        if banned:
            return JsonResponse({'success': False, 'error': banned}, status=400)

        # Save under XDG/user data dir so discovery (when enabled) can find it.
        # Must slugify: raw lower/space-replace allowed path traversal (../…).
        blueprint_id = _safe_agent_blueprint_id(agent_name)
        user_blueprints_dir = paths.get_user_blueprints_dir()
        root = user_blueprints_dir.resolve()
        agent_dir = (user_blueprints_dir / blueprint_id).resolve()
        if agent_dir != root and root not in agent_dir.parents:
            return JsonResponse({
                'success': False,
                'error': 'Invalid agent name.',
            }, status=400)
        agent_dir.mkdir(parents=True, exist_ok=True)

        # Write the blueprint file
        blueprint_file = agent_dir / f'blueprint_{blueprint_id}.py'
        blueprint_file.write_text(code)
        abs_path = str(blueprint_file.resolve())

        # Create README
        readme_content = f"""# {agent_name}

Custom agent blueprint created via the Agent Creator.

## Description
{data.get('description', 'Custom AI agent')}

## Usage
```bash
swarm-cli launch {blueprint_id}
```
"""
        readme_file = agent_dir / 'README.md'
        readme_file.write_text(readme_content)

        return JsonResponse({
            'success': True,
            'message': (
                f'Agent "{agent_name}" saved successfully. '
                f'{_save_discovery_message()}'
            ),
            'path': abs_path,
            'blueprint_id': blueprint_id,
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Save failed: {str(e)}'
        }, status=500)


@login_required
def team_creator_page(request):
    """Render the team creator interface"""
    if request.method == 'GET':
        context = {
            'page_title': 'Team Creator',
            'existing_agents': _get_available_agents(),
            'profiles': _get_llm_profiles(),
        }
        return render(request, 'team_creator.html', context)


def _get_available_agents():
    """Get list of available agents for team creation"""
    # This would scan for existing blueprints
    agents = []

    # Add built-in agents
    builtin_agents = [
        {'name': 'codey', 'description': 'Code analysis and generation'},
        {'name': 'jeeves', 'description': 'General purpose assistant'},
        {'name': 'chatbot', 'description': 'Conversational agent'}
    ]
    agents.extend(builtin_agents)

    # Add user-created agents from the XDG/user data blueprints dir
    user_blueprints_dir = paths.get_user_blueprints_dir()
    if user_blueprints_dir.exists():
        for agent_dir in user_blueprints_dir.iterdir():
            if agent_dir.is_dir():
                agents.append({
                    'name': agent_dir.name,
                    'description': f'Custom agent: {agent_dir.name}'
                })

    return agents


def _get_llm_profiles() -> list[str]:
    """Return available LLM profile names from local swarm_config.json files."""
    profiles: list[str] = []
    try:
        cfg_paths = []
        cfg_paths.append(Path("swarm_config.json"))
        cfg_paths.append(paths.get_user_config_dir_for_swarm() / "swarm_config.json")
        for cfg_path in cfg_paths:
            if not cfg_path.exists():
                continue
            data = json.loads(cfg_path.read_text())
            llm = data.get("llm", {})
            if isinstance(llm, dict):
                if "profiles" in llm and isinstance(llm["profiles"], dict):
                    profiles.extend(list(llm["profiles"].keys()))
                else:
                    profiles.extend(list(llm.keys()))
        # de-dup while preserving order
        seen = set()
        unique = []
        for p in profiles:
            if p not in seen:
                seen.add(p)
                unique.append(p)
        profiles = unique
    except Exception:
        profiles = []
    return profiles


def _slugify(name: str) -> str:
    slug = "".join(c.lower() if c.isalnum() else "-" for c in name.strip())
    slug = "-".join(filter(None, slug.split("-")))
    return slug or "swarm"


def _safe_agent_blueprint_id(name: str) -> str:
    """Single path-segment id for agent saves (spaces→_; no traversal).

    Mirrors historical ``lower().replace(' ', '_')`` for normal names while
    stripping ``/``, ``\\``, ``..``, and other non-alnum so the write stays
    under ``get_user_blueprints_dir()``.
    """
    slug = "".join(c.lower() if c.isalnum() else "_" for c in name.strip())
    slug = "_".join(filter(None, slug.split("_")))
    return slug or "agent"


def _pascal_case(name: str) -> str:
    parts = [p for p in "".join(ch if ch.isalnum() else " " for ch in name).split() if p]
    return "".join(p.capitalize() for p in parts) or "Swarm"


def _render_swarm_blueprint_code(team: dict[str, Any]) -> str:
    """Render a multi-bot swarm blueprint with per-bot system prompts, tools, and model profiles."""
    team_name = team["name"]
    description = team.get("description") or f"Swarm team: {team_name}"
    coordinator_name = team.get("coordinator_name") or team["agents"][0]["name"]
    class_name = f"{_pascal_case(team_name)}SwarmBlueprint"
    blueprint_id = _slugify(team_name)

    from swarm.core.agent_roles import ROLE_GATE, ROLE_SKEPTIC, normalize_agent_role
    from swarm.core.classifier_verdict import ensure_classifier_instructions

    agents = []
    for agent in team["agents"]:
        role = normalize_agent_role(agent.get("role"))
        instructions = agent.get("system_prompt") or agent.get("instructions") or f"You are {agent['name']}."
        if role == ROLE_GATE:
            instructions = ensure_classifier_instructions(instructions, "gate")
        if role == ROLE_SKEPTIC:
            instructions = ensure_classifier_instructions(instructions, "skeptic")
        agents.append({
            "name": agent["name"],
            "role": role,
            "description": agent.get("description") or f"{agent['name']} agent",
            "instructions": instructions,
            "model_profile": agent.get("model_profile") or "default",
            "tools": agent.get("tools") or [],
        })

    all_tools = set()
    for agent in agents:
        for tool in agent.get("tools", []):
            all_tools.add(tool)

    tool_defs: list[str] = []
    tool_map_lines: list[str] = []
    if "read_file" in all_tools:
        tool_defs.append(
            "@function_tool\n"
            "def read_file(path: str) -> str:\n"
            "    try:\n"
            "        with open(path, 'r', encoding='utf-8') as f:\n"
            "            return f.read()\n"
            "    except Exception as e:\n"
            "        return f\"ERROR: {e}\"\n"
        )
        tool_map_lines.append("    \"read_file\": read_file,")
    if "write_file" in all_tools:
        tool_defs.append(
            "@function_tool\n"
            "def write_file(path: str, content: str) -> str:\n"
            "    try:\n"
            "        with open(path, 'w', encoding='utf-8') as f:\n"
            "            f.write(content)\n"
            "        return \"OK: file written\"\n"
            "    except Exception as e:\n"
            "        return f\"ERROR: {e}\"\n"
        )
        tool_map_lines.append("    \"write_file\": write_file,")
    if "list_files" in all_tools:
        tool_defs.append(
            "@function_tool\n"
            "def list_files(directory: str = '.') -> str:\n"
            "    try:\n"
            "        import os\n"
            "        return \"\\n\".join(os.listdir(directory))\n"
            "    except Exception as e:\n"
            "        return f\"ERROR: {e}\"\n"
        )
        tool_map_lines.append("    \"list_files\": list_files,")
    if "execute_shell_command" in all_tools:
        tool_defs.append(
            "@function_tool\n"
            "def execute_shell_command(command: str) -> str:\n"
            "    try:\n"
            "        import os, subprocess, shlex\n"
            "        timeout = int(os.getenv(\"SWARM_COMMAND_TIMEOUT\", \"60\"))\n"
            "        result = subprocess.run(shlex.split(command), shell=False, capture_output=True, text=True, timeout=timeout)\n"
            "        output = f\"Exit Code: {result.returncode}\\n\"\n"
            "        if result.stdout:\n"
            "            output += \"STDOUT:\\n\" + result.stdout + \"\\n\"\n"
            "        if result.stderr:\n"
            "            output += \"STDERR:\\n\" + result.stderr + \"\\n\"\n"
            "        return output.strip()\n"
            "    except subprocess.TimeoutExpired:\n"
            "        return \"Error: Command timed out.\"\n"
            "    except Exception as e:\n"
            "        return f\"ERROR: {e}\"\n"
        )
        tool_map_lines.append("    \"execute_shell_command\": execute_shell_command,")

    tool_map = "\n".join(tool_map_lines) if tool_map_lines else "    # No tools configured"
    agent_specs_literal = repr(agents)

    lines: list[str] = []
    lines.append("# Auto-generated by Swarm Web UI")
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from collections.abc import AsyncGenerator")
    lines.append("from typing import Any")
    lines.append("")
    lines.append("from agents import Agent, Runner, function_tool")
    lines.append("")
    # ADR-005 §4: emit a kind base by default (team payload carries no kind
    # yet, so this resolves through the BlueprintBase fallback).
    base_class = base_class_for_kind(team.get("kind"))
    lines.append("from swarm.core.agent_roles import find_role_agent, normalize_agent_role")
    lines.append(f"from swarm.core.kind_bases import {base_class}")
    lines.append("from swarm.core.classifier_verdict import attach_classifier_tools")
    lines.append("from swarm.core.skeptic import attach_skeptic_as_tool, run_with_skeptic")
    lines.append("from swarm.core.suggestions import attach_suggestions_as_tool")
    lines.append("from swarm.core.tool_gate import attach_gate_as_tool, wrap_tools_with_gate")
    lines.append("")
    if tool_defs:
        lines.extend(tool_defs)
    lines.append("")
    lines.append("TOOLS_REGISTRY = {")
    lines.append(tool_map)
    lines.append("}")
    lines.append("")
    lines.append(f"AGENT_SPECS = {agent_specs_literal}")
    lines.append("")
    lines.append(f"class {class_name}({base_class}):")
    lines.append("    \"\"\"")
    lines.append(f"    {description}")
    lines.append("    \"\"\"")
    lines.append("")
    lines.append("    metadata = {")
    lines.append(f"        \"name\": {repr(team_name)},")
    lines.append(f"        \"description\": {repr(description)},")
    lines.append("        \"version\": \"1.0.0\",")
    lines.append("        \"author\": \"Creator\",")
    lines.append("        \"tags\": [\"swarm\"],")
    lines.append("        \"role\": \"default\",")
    lines.append("        \"agents\": [{\"name\": spec[\"name\"], \"role\": spec.get(\"role\") or \"default\"} for spec in AGENT_SPECS],")
    lines.append("        \"gate_agent\": next((spec[\"name\"] for spec in AGENT_SPECS if spec.get(\"role\") in (\"gate\", \"tool_gate\")), None),")
    lines.append("        \"skeptic_agent\": next((spec[\"name\"] for spec in AGENT_SPECS if spec.get(\"role\") == \"skeptic\"), None),")
    lines.append("        \"suggestions_agent\": next((spec[\"name\"] for spec in AGENT_SPECS if spec.get(\"role\") == \"suggestions\"), None),")
    lines.append(f"        \"coordinator\": {repr(coordinator_name)},")
    lines.append("    }")
    lines.append("")
    lines.append("    def __init__(self, blueprint_id: str = None, config_path: str = None, **kwargs: Any):")
    lines.append(f"        super().__init__(blueprint_id or {repr(blueprint_id)}, config_path=config_path, **kwargs)")
    lines.append("        self._agents = {}")
    lines.append("")
    lines.append("    def _build_agents(self) -> dict[str, Agent]:")
    lines.append("        agents = {}")
    lines.append("        for spec in AGENT_SPECS:")
    lines.append("            name = spec.get(\"name\")")
    lines.append("            instructions = spec.get(\"instructions\") or \"\"")
    lines.append("            model_profile = spec.get(\"model_profile\") or \"default\"")
    lines.append("            tool_names = spec.get(\"tools\") or []")
    lines.append("            tools = [TOOLS_REGISTRY[t] for t in tool_names if t in TOOLS_REGISTRY]")
    lines.append("            model_instance = self._get_model_instance(model_profile)")
    lines.append("            role = normalize_agent_role(spec.get(\"role\"))")
    lines.append("            agents[name] = Agent(")
    lines.append("                name=name,")
    lines.append("                model=model_instance,")
    lines.append("                instructions=instructions,")
    lines.append("                tools=tools,")
    lines.append("                mcp_servers=[],")
    lines.append("            )")
    lines.append("            agents[name].role = role")
    lines.append("            if role in (\"gate\", \"skeptic\"):")
    lines.append("                attach_classifier_tools(agents[name], role)")
    lines.append("        return agents")
    lines.append("")
    lines.append("    def elicit_tool_approval(self, tool_name, arguments):")
    lines.append("        return self.request_approval(\"tool\", f\"{tool_name}\", arguments)")
    lines.append("")
    lines.append("    def create_starting_agent(self, mcp_servers):")
    lines.append("        if not self._agents:")
    lines.append("            self._agents = self._build_agents()")
    lines.append(f"        coordinator_name = {repr(coordinator_name)}")
    lines.append("        coordinator = self._agents.get(coordinator_name) or next(iter(self._agents.values()))")
    lines.append("        gate = find_role_agent(self._agents, \"gate\")")
    lines.append("        skeptic = find_role_agent(self._agents, \"skeptic\")")
    lines.append("        team_tools = []")
    lines.append("        for name, agent in self._agents.items():")
    lines.append("            if name == coordinator.name:")
    lines.append("                continue")
    lines.append("            if getattr(agent, \"role\", \"default\") in (\"gate\", \"skeptic\", \"suggestions\"):")
    lines.append("                continue")
    lines.append("            team_tools.append(agent.as_tool(tool_name=name, tool_description=f\"Delegate to {name}.\"))")
    lines.append("        if team_tools:")
    lines.append("            coordinator.tools = list(coordinator.tools) + team_tools")
    lines.append("        # Unwired gate: wrap_tools_with_gate is a no-op and never elicits.")
    lines.append("        coordinator.tools = wrap_tools_with_gate(")
    lines.append("            list(coordinator.tools or []),")
    lines.append("            gate=gate,")
    lines.append("            elicit_fn=self.elicit_tool_approval,")
    lines.append("        )")
    lines.append("        attach_gate_as_tool(coordinator, gate)")
    lines.append("        attach_skeptic_as_tool(coordinator, skeptic)")
    lines.append("        suggestions = find_role_agent(self._agents, \"suggestions\")")
    lines.append("        attach_suggestions_as_tool(coordinator, suggestions)")
    lines.append("        return coordinator")
    lines.append("")
    lines.append("    async def run(self, messages: list[dict[str, Any]], **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:")
    lines.append("        user_message = messages[-1].get(\"content\", \"\") if messages else \"\"")
    lines.append("        agent = self.create_starting_agent([])")
    lines.append("        skeptic = find_role_agent(self._agents, \"skeptic\")")
    lines.append("        try:")
    lines.append("            async def _run(current, prompt):")
    lines.append("                result = await Runner.run(current, prompt)")
    lines.append("                return getattr(result, \"final_output\", str(result))")
    lines.append("            outcome = await run_with_skeptic(")
    lines.append("                agent=agent,")
    lines.append("                prompt=user_message,")
    lines.append("                skeptic=skeptic,")
    lines.append("                run_fn=_run,")
    lines.append("            )")
    lines.append("            content = outcome.output")
    lines.append("            yield {\"messages\": [{\"role\": \"assistant\", \"content\": content}]}")
    lines.append("        except Exception as e:")
    lines.append("            yield {\"messages\": [{\"role\": \"assistant\", \"content\": f\"[Swarm Error] {e}\"}]}")
    lines.append("")
    return "\n".join(lines)


@login_required
@require_http_methods(["POST"])
def save_team_swarm(request):
    """Persist a multi-bot swarm blueprint from the Team Creator UI.

    Authenticated write-only path: generated code is not exec'd on save.
    User blueprint discovery remains opt-in via SWARM_ALLOW_USER_BLUEPRINT_DISCOVERY.
    """
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"success": False, "error": "Invalid JSON payload."}, status=400)

    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    coordinator_name = (data.get("coordinator_name") or "").strip()
    agents = data.get("agents") or []
    overwrite = bool(data.get("overwrite"))

    if not name:
        return JsonResponse({"success": False, "error": "Swarm name is required."}, status=400)
    if not description:
        return JsonResponse({"success": False, "error": "Swarm description is required."}, status=400)
    if not isinstance(agents, list) or len(agents) < 2:
        return JsonResponse({"success": False, "error": "Provide at least two bot definitions."}, status=400)

    cleaned_agents = []
    seen = set()
    for agent in agents:
        bot_name = (agent.get("name") or "").strip()
        if not bot_name:
            continue
        if bot_name.lower() in seen:
            return JsonResponse({"success": False, "error": f"Duplicate bot name: {bot_name}"}, status=400)
        seen.add(bot_name.lower())
        # Refuse dangerous patterns in free-text prompts that end up in source.
        for field in ("system_prompt", "instructions", "description", "role"):
            val = agent.get(field) or ""
            if isinstance(val, str):
                banned = _banned_snippet_error(val)
                if banned:
                    return JsonResponse({"success": False, "error": banned}, status=400)
        from swarm.core.agent_roles import normalize_agent_role

        cleaned_agents.append({
            "name": bot_name,
            "role": normalize_agent_role(agent.get("role")),
            "description": (agent.get("description") or f"{bot_name} bot").strip(),
            "system_prompt": (agent.get("system_prompt") or agent.get("instructions") or f"You are {bot_name}.").strip(),
            "model_profile": (agent.get("model_profile") or "default").strip(),
            "tools": [t for t in (agent.get("tools") or []) if isinstance(t, str) and t],
        })

    if len(cleaned_agents) < 2:
        return JsonResponse({"success": False, "error": "Provide at least two valid bot definitions."}, status=400)

    blueprint_id = _slugify(name)
    coordinator_name = coordinator_name or cleaned_agents[0]["name"]

    team = {
        "name": name,
        "description": description,
        "coordinator_name": coordinator_name,
        "agents": cleaned_agents,
    }

    code = _render_swarm_blueprint_code(team)
    banned = _banned_code_error(code)
    if banned:
        return JsonResponse({"success": False, "error": banned}, status=400)

    user_blueprints_dir = paths.get_user_blueprints_dir()
    swarm_dir = user_blueprints_dir / blueprint_id
    swarm_dir.mkdir(parents=True, exist_ok=True)
    blueprint_path = swarm_dir / f"blueprint_{blueprint_id}.py"
    if blueprint_path.exists() and not overwrite:
        return JsonResponse(
            {"success": False, "error": f"Blueprint already exists: {blueprint_path.resolve()}"},
            status=409,
        )

    blueprint_path.write_text(code, encoding="utf-8")
    abs_path = str(blueprint_path.resolve())

    readme_path = swarm_dir / "README.md"
    if not readme_path.exists() or overwrite:
        readme_path.write_text(
            f"# {name}\n\n{description}\n\nGenerated by Web UI.\n",
            encoding="utf-8"
        )

    return JsonResponse({
        "success": True,
        "message": (
            f"Swarm '{name}' saved successfully. "
            f"{_save_discovery_message()}"
        ),
        "blueprint_id": blueprint_id,
        "path": abs_path,
        "code": code,
    })
