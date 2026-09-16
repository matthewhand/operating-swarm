"""
Web UI views for Open Swarm Core.
Handles rendering index, blueprint pages, login, and serving config.
"""
import json
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

# Import config loader if needed, or assume config is loaded elsewhere
# Import the function to discover blueprints dynamically
from swarm.core.blueprint_discovery import discover_blueprints
from swarm.core.paths import get_user_config_dir_for_swarm

# Import the setting for the blueprints directory
from swarm.settings import BLUEPRINT_DIRECTORY
from swarm.utils.env_utils import *
from swarm.utils.logger_setup import setup_logger

from .utils import (
    deregister_dynamic_team,
    load_dynamic_registry,
    register_dynamic_team,
    reset_dynamic_registry,
)

logger = setup_logger(__name__)

_DEFAULT_POST_LOGIN_REDIRECT = "/"


def _safe_post_login_redirect(request, next_url: str | None) -> str:
    """Return a same-origin path redirect, else the post-login default.

    Stricter than Django's url_has_allowed_host_and_scheme alone: only relative
    paths that start with a single ``/`` are accepted. Rejects scheme-relative
    (``//evil``), backslash tricks (``\\\\``, ``/\\\\evil``), absolute URLs,
    and bare relative segments (``chatbot/``).
    """
    fallback = _DEFAULT_POST_LOGIN_REDIRECT
    if next_url is None:
        return fallback
    candidate = next_url.strip()
    if not candidate:
        return fallback
    # Header / parser footguns before Django's host/scheme check.
    if any(ch in candidate for ch in ("\\", "\r", "\n", "\t", "\x00")):
        return fallback
    if "://" in candidate or not candidate.startswith("/") or candidate.startswith("//"):
        return fallback
    if not url_has_allowed_host_and_scheme(
        url=candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return fallback
    return candidate


# REQ-106 / #768: root browser/PWA icon files live in assets/brand/ (not dist/).
BRAND_ROOT_FILES = {
    "favicon.ico": "image/x-icon",
    "favicon-16.png": "image/png",
    "favicon-32.png": "image/png",
    "apple-touch-icon.png": "image/png",
    "icon-192.png": "image/png",
    "icon-512.png": "image/png",
    "manifest.json": "application/manifest+json",
    "favicon-minimal.svg": "image/svg+xml",
    "webui-geometric.svg": "image/svg+xml",
}


def brand_dir() -> Path:
    return Path(settings.BASE_DIR).parent / "assets" / "brand"


def brand_root_file(request, filename: str):
    """Serve a checked-in brand raster at a well-known root URL (no collectstatic)."""
    ctype = BRAND_ROOT_FILES.get(filename)
    if not ctype:
        return HttpResponse("Not Found", status=404)
    path = brand_dir() / filename
    if not path.is_file():
        return HttpResponse("Not Found", status=404)
    return asgi_file_response(path, ctype)


def asgi_file_response(path: Path, content_type: str) -> HttpResponse:
    """Buffer a file into HttpResponse.

    Django 4.2 FileResponse.streaming_content is a map(); ASGI/Daphne then
    TypeErrors on async-for and can leave CurrentThreadExecutor dead so later
    requests hang (LAN GET / looks like a hung launch). See issue #425.
    """
    return HttpResponse(path.read_bytes(), content_type=content_type)


def _get_frontend_path():
    """Get the path to the built frontend assets."""
    # Check common build output directories
    frontend_path = Path("webui/frontend/dist")
    if not frontend_path.exists():
        frontend_path = Path("webui/frontend/build")
    return frontend_path if frontend_path.exists() else None

def _ensure_frontend_built():
    """Ensure frontend is built, attempting automatic build if possible."""
    frontend_path = _get_frontend_path()
    if frontend_path:
        return frontend_path

    logger.info("Frontend build not found. Attempting to build automatically...")
    try:
        # Check if npm is available
        subprocess.run(["npm", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        frontend_dir = Path("webui/frontend")
        if not frontend_dir.exists():
            logger.error("Frontend directory not found: webui/frontend")
            return None

        logger.info("Installing frontend dependencies...")
        subprocess.run(
            ["npm", "install", "--no-audit", "--no-fund", "--legacy-peer-deps"],
            cwd=str(frontend_dir),
            stdout=sys.stdout,
            stderr=sys.stderr,
            check=True
        )

        logger.info("Building frontend assets...")
        subprocess.run(
            ["npm", "run", "build"],
            cwd=str(frontend_dir),
            stdout=sys.stdout,
            stderr=sys.stderr,
            check=True
        )

        # Check which build directory was created
        if Path("webui/frontend/dist").exists():
            return Path("webui/frontend/dist")
        elif Path("webui/frontend/build").exists():
            return Path("webui/frontend/build")

    except FileNotFoundError:
        logger.error("Could not find 'npm' executable. Please install Node.js and run 'npm run build' manually in webui/frontend/")
    except Exception as e:
        logger.error(f"Automatic frontend build failed: {e}. Please run 'npm run build' manually in webui/frontend/")

    return None

def spa_chat(request):
    """Serve the React Chat shell at ``/chat`` (first-class, not fallback-only).

    REQ-5d follow-up: ``/chat`` must stay the SPA chat (composer + Connected),
    not bounce to ``/agents``. Looks up ``dist/`` at request time so Chat still
    works if assets appear after process start. Does **not** call
    ``_ensure_frontend_built()`` (that would npm-build in tests).
    """
    frontend_path = _get_frontend_path()
    if frontend_path:
        index_file = frontend_path / "index.html"
        if index_file.exists():
            logger.debug("Serving SPA Chat from %s", index_file)
            return asgi_file_response(index_file, "text/html")
    return HttpResponse("Not Found", status=404)


def index(request):
    """Render the main index page with dynamically discovered blueprint options."""
    # Try to serve static frontend first if available
    frontend_path = _ensure_frontend_built()
    if frontend_path:
        index_file = frontend_path / "index.html"
        if index_file.exists():
            logger.debug("Serving static frontend from " + str(index_file))
            return asgi_file_response(index_file, "text/html")

    # Fallback to Django template rendering
    logger.debug("Rendering index page with Django templates")
    try:
        # Discover blueprints dynamically each time the index is loaded
        # Consider caching this if performance becomes an issue
        discovered_metadata = discover_blueprints(BLUEPRINT_DIRECTORY)
        blueprint_names = list(discovered_metadata.keys())
        logger.debug(f"Rendering index with blueprints: {blueprint_names}")
    except Exception as e:
        logger.error(f"Error discovering blueprints for index page: {e}", exc_info=True)
        blueprint_names = [] # Show empty list on error

    context = {
        "dark_mode": request.session.get('dark_mode', True),
        "enable_admin": is_enable_admin(),
        "blueprints": blueprint_names,  # Use the dynamically discovered list
    }

    # Recent sessions for the landing page (owner-scoped; empty when anonymous).
    try:
        from swarm.auth import explorer_owner_allows
        from swarm.core import responses_store

        recent = [
            s for s in responses_store.list_summaries(limit=50)
            if explorer_owner_allows(s, request)
        ][:5]
        context["recent_sessions"] = recent
    except Exception:
        logger.debug("Could not load recent sessions for index", exc_info=True)
        context["recent_sessions"] = []

    return render(request, "index.html", context)


def custom_login(request):
    """Handle custom login at /accounts/login/, redirecting to 'next' URL on success."""
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            # User authenticated successfully
            login(request, user)
            raw_next = request.POST.get("next") or request.GET.get("next") or _DEFAULT_POST_LOGIN_REDIRECT
            next_url = _safe_post_login_redirect(request, raw_next)
            if next_url != (raw_next or "").strip():
                logger.warning(f"Invalid 'next' URL detected: '{raw_next}'. Falling back to default.")

            logger.info(f"User '{username}' logged in successfully. Redirecting to '{next_url}'.")
            return redirect(next_url)
        else:
            # Authentication failed
            logger.warning(f"Failed login attempt for user '{username}'.")
            # Dev-only 'testuser' auto-login. Honoured ONLY when BOTH
            # ALLOW_TESTUSER_AUTOLOGIN=true AND DJANGO_DEBUG=true.
            # is_testuser_autologin_allowed() raises ImproperlyConfigured if the
            # flag is enabled outside debug mode (refuse, never silently allow).
            if is_testuser_autologin_allowed():
                logger.info("ALLOW_TESTUSER_AUTOLOGIN enabled (debug mode). Attempting 'testuser' auto-login.")
                try:
                    from django.contrib.auth.models import User
                    test_user, created = User.objects.get_or_create(username="testuser")
                    if created:
                        # Never a hardcoded password: per-boot random unless
                        # TESTUSER_PASSWORD is explicitly set in the environment.
                        test_user.set_password(get_testuser_password())
                        test_user.save()
                        logger.info("Created dev-only 'testuser' account.")
                    login(request, test_user, backend='django.contrib.auth.backends.ModelBackend')
                    raw_next = request.POST.get("next") or request.GET.get("next") or _DEFAULT_POST_LOGIN_REDIRECT
                    next_url = _safe_post_login_redirect(request, raw_next)
                    if next_url != (raw_next or "").strip():
                        logger.warning(
                            f"Invalid 'next' URL detected during auto-login: '{raw_next}'. Falling back to default."
                        )
                    logger.info("Auto-logged in as 'testuser' (dev-only convenience). Redirecting.")
                    return redirect(next_url)
                except Exception as auto_login_err:
                     logger.error(f"Error during 'testuser' auto-login attempt: {auto_login_err}")

            # If authentication failed and auto-login didn't happen/failed
            return render(request, "account/login.html", {"error": "Invalid username or password."})

    # If GET request, just render the login form
    return render(request, "account/login.html")

# Default config structure to return if the actual file is missing/invalid
DEFAULT_CONFIG = {
    "llm": {
        "default": {
            "provider": "openai",
            "model": "gpt-4o", # More modern default
            "base_url": "https://api.openai.com/v1", # Standard OpenAI endpoint
            "api_key": "", # API key should usually come from env vars
            "temperature": 0.7
        }
    },
    "mcpServers": {},
    "blueprints": {}
}

def serve_swarm_config(_request):
    """Serve the main swarm configuration file (swarm_config.json) as JSON.

    Unrouted helper retained for direct/unit tests (GET-only).
    """
    # Construct path relative to Django settings.BASE_DIR
    config_path = Path(settings.BASE_DIR) / "swarm_config.json"
    logger.debug(f"Attempting to serve swarm config from: {config_path}")
    try:
        # Use Path object's read_text method for cleaner file reading
        config_content = config_path.read_text(encoding='utf-8')
        config_data = json.loads(config_content)
        logger.debug("Successfully loaded and parsed swarm_config.json")
        return JsonResponse(config_data)
    except FileNotFoundError:
        logger.error(f"Configuration file swarm_config.json not found at {config_path}. Serving default config.")
        return JsonResponse(DEFAULT_CONFIG, status=404) # Return 404 maybe? Or just default?
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from {config_path}: {e}")
        # Return an error response instead of default config on parse error
        return JsonResponse({"error": f"Invalid JSON format in configuration file: {e}"}, status=500)
    except Exception as e:
         logger.error(f"Unexpected error serving swarm config: {e}", exc_info=True)
         return JsonResponse({"error": "An unexpected error occurred."}, status=500)


def _webui_enabled() -> bool:
    return is_enable_webui()


_DEMO_TEAM_ROSTER = {
    "id": "demo-team",
    "object": "team_roster",
    "name": "Demo Team",
    "description": "Example multi-agent roster",
    "members": [
        {"id": "codey", "name": "Codey", "kind": "agent", "role": "coder"},
        {"id": "stewie", "name": "Stewie", "kind": "agent", "role": "ops"},
    ],
}


def team_rosters_json(request):
    """Serve team_rosters.json for the AGENTS sidepane (not /v1/teams/ aliases)."""
    candidates = [
        Path("webui/frontend/public/team_rosters.json"),
        Path("webui/frontend/dist/team_rosters.json"),
        Path("src/swarm/static/team_rosters.json"),
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        return JsonResponse(payload, safe=False)
    return JsonResponse({"object": "list", "data": [_DEMO_TEAM_ROSTER]})


def team_launcher(request):
    """
    Render a minimal Team Launcher UI that allows selecting a blueprint (team),
    entering an instruction, and launching via /v1/chat/completions with stream=true.
    Gated behind ENABLE_WEBUI.
    """
    if not _webui_enabled():
        return HttpResponse("Web UI disabled. Set ENABLE_WEBUI=true to enable.", status=404)

    context = {
        "api_auth_enabled": bool(get_api_auth_token()),
        **_profiles_ctx(),
    }
    return render(request, "teams_launch.html", context)


@login_required
def team_admin(request):
    """Simple admin page to list and add dynamic teams (authenticated).

    Note: deliberately NOT @csrf_exempt — this view mutates state on POST and
    its forms in teams_admin.html include {% csrf_token %}.
    """
    if not _webui_enabled():
        return HttpResponse("Web UI disabled. Set ENABLE_WEBUI=true to enable.", status=404)

    if request.method == "POST":
        action = (request.POST.get("action") or "add").lower()
        if action == "delete":
            team_id = (request.POST.get("team_id") or "").strip()
            if team_id:
                try:
                    deregister_dynamic_team(team_id)
                except Exception as e:
                    teams = list(load_dynamic_registry().values())
                    return render(
                        request,
                        "teams_admin.html",
                        {"error": f"Failed to delete team: {e}", "teams": teams, **_profiles_ctx()},
                    )
            return redirect("teams_admin")
        if action == "reset":
            try:
                reset_dynamic_registry()
            except Exception as e:
                teams = list(load_dynamic_registry().values())
                return render(
                    request,
                    "teams_admin.html",
                    {"error": f"Failed to reset teams: {e}", "teams": teams, **_profiles_ctx()},
                )
            return redirect("teams_admin")

        # Add / Import flow
        if action == "import":
            import_format = (request.POST.get("import_format") or "json").lower()
            import_data = request.POST.get("import_data") or ""
            overwrite = bool(request.POST.get("overwrite"))
            err = None
            added = 0
            updated = 0
            try:
                if import_format == "json":
                    import json
                    payload = json.loads(import_data)
                    if isinstance(payload, dict):
                        for tid, entry in payload.items():
                            if not isinstance(entry, dict):
                                continue
                            team_id = "".join(c.lower() if c.isalnum() else "-" for c in (tid or "")).strip("-")
                            if not team_id:
                                continue
                            exists = team_id in load_dynamic_registry()
                            if exists and not overwrite:
                                continue
                            register_dynamic_team(team_id, description=entry.get("description"), llm_profile=entry.get("llm_profile"))
                            if exists:
                                updated += 1
                            else:
                                added += 1
                    else:
                        err = "JSON must be an object of id → entry."
                else:
                    # CSV format
                    lines = [ln for ln in import_data.splitlines() if ln.strip()]
                    if not lines:
                        err = "CSV is empty."
                    else:
                        # Expect header
                        header = [h.strip() for h in lines[0].split(",")]
                        col_id = header.index("id") if "id" in header else 0
                        col_llm = header.index("llm_profile") if "llm_profile" in header else None
                        col_desc = header.index("description") if "description" in header else None
                        for row in lines[1:]:
                            cols = row.split(",")
                            raw_id = cols[col_id] if len(cols) > col_id else ""
                            team_id = "".join(c.lower() if c.isalnum() else "-" for c in raw_id).strip("-")
                            if not team_id:
                                continue
                            llm_profile = (cols[col_llm] if col_llm is not None and len(cols) > col_llm else None)
                            description = (cols[col_desc] if col_desc is not None and len(cols) > col_desc else None)
                            exists = team_id in load_dynamic_registry()
                            if exists and not overwrite:
                                continue
                            register_dynamic_team(team_id, description=description, llm_profile=llm_profile)
                            if exists:
                                updated += 1
                            else:
                                added += 1
            except Exception as e:
                err = f"Import failed: {e}"
            teams = list(load_dynamic_registry().values())
            ctx = {"teams": teams, **_profiles_ctx()}
            if err:
                ctx["error"] = err
            else:
                ctx["message"] = f"Imported: {added} added, {updated} updated."
            return render(request, "teams_admin.html", ctx)

        # Add flow continues
        team_name = (request.POST.get("team_name") or "").strip()
        llm_profile = (request.POST.get("llm_profile") or "").strip() or None
        description = (request.POST.get("description") or "").strip() or None
        teams_current = list(load_dynamic_registry().values())
        # Basic validation
        if not team_name:
            return render(request, "teams_admin.html", {"error": "Team name is required.", "teams": teams_current, **_profiles_ctx()})
        # Slugify: lowercase alnum and '-'
        slug = "".join(c.lower() if c.isalnum() else "-" for c in team_name).strip("-")
        if not slug:
            return render(request, "teams_admin.html", {"error": "Team name must contain letters or numbers.", "teams": teams_current, **_profiles_ctx()})
        if len(slug) > 64:
            return render(request, "teams_admin.html", {"error": "Team name too long (max 64).", "teams": teams_current, **_profiles_ctx()})
        # Uniqueness vs dynamic registry
        if any(t.get("id") == slug for t in teams_current):
            return render(request, "teams_admin.html", {"error": f"Team '{slug}' already exists.", "teams": teams_current, **_profiles_ctx()})
        # Guard against collisions with statically discovered blueprints.
        # Fail closed: discovery errors must not allow shadowing a static blueprint.
        try:
            discovered = discover_blueprints(BLUEPRINT_DIRECTORY)
        except Exception:
            logger.exception("Blueprint collision check failed; refusing team create.")
            return render(
                request,
                "teams_admin.html",
                {
                    "error": "Unable to verify team name against existing blueprints. Please try again.",
                    "teams": teams_current,
                    **_profiles_ctx(),
                },
            )
        if isinstance(discovered, dict) and slug in discovered:
            return render(
                request,
                "teams_admin.html",
                {
                    "error": f"Name '{slug}' conflicts with an existing blueprint.",
                    "teams": teams_current,
                    **_profiles_ctx(),
                },
            )
        try:
            register_dynamic_team(slug, description=description, llm_profile=llm_profile)
        except Exception as e:
            return render(
                request,
                "teams_admin.html",
                {"error": f"Failed to save team: {e}", "teams": teams_current, **_profiles_ctx()},
            )
        return redirect("teams_admin")

    teams = list(load_dynamic_registry().values())
    return render(
        request,
        "teams_admin.html",
        {"teams": teams, **_profiles_ctx(), **_herdr_members_ctx()},
    )


def _herdr_members_ctx():
    """Persisted Herdr members (kind=herdr) for Teams to pick."""
    try:
        from swarm.models import HerdrAgent

        return {"herdr_agents": list(HerdrAgent.objects.all().order_by("name"))}
    except Exception:
        logger.exception("Error loading Herdr members for Teams")
        return {"herdr_agents": []}


def _profiles_ctx():
    """Builds a context dict containing available LLM profile names for form suggestions."""
    profiles: list[str] = []
    try:
        # Prefer repo-local swarm_config.json for demo simplicity
        import json
        cfg_path = Path(settings.BASE_DIR) / "swarm_config.json"
        paths = [cfg_path]
        # Also include XDG user config swarm_config.json
        xdg_cfg = get_user_config_dir_for_swarm() / "swarm_config.json"
        paths.append(xdg_cfg)
        for path in paths:
            if path.exists():
                data = json.loads(path.read_text())
                llm = data.get("llm", {})
                if isinstance(llm, dict):
                    if "profiles" in llm and isinstance(llm["profiles"], dict):
                        profiles.extend(list(llm["profiles"].keys()))
                    else:
                        profiles.extend(list(llm.keys()))
        # De-duplicate while preserving order
        seen = set()
        ordered = []
        for p in profiles:
            if p not in seen:
                seen.add(p)
                ordered.append(p)
        profiles = ordered
    except Exception:
        profiles = []
    return {"profiles": profiles}


@login_required
def teams_export(request):
    """Export the dynamic team registry as JSON or CSV (authenticated)."""
    reg = load_dynamic_registry()
    fmt = request.GET.get("format", "json").lower()
    if fmt == "csv":
        def _csv_safe(value: str) -> str:
            # Neutralise spreadsheet formula injection (=, +, -, @ prefixes)
            # and strip commas/quotes that would break naive row parsing.
            v = (value or "").replace(",", " ").replace('"', "'")
            if v.startswith(("=", "+", "-", "@")):
                v = "'" + v
            return v

        lines = ["id,llm_profile,description"]
        for k, v in reg.items():
            llm = _csv_safe(v.get("llm_profile") or "")
            desc = _csv_safe(v.get("description") or "")
            lines.append(f"{k},{llm},{desc}")
        body = "\n".join(lines) + "\n"
        resp = HttpResponse(body, content_type="text/csv")
        resp["Content-Disposition"] = "attachment; filename=teams.csv"
        return resp
    # default JSON
    return JsonResponse(reg)


@login_required
def profiles_page(request):
    """Show detected LLM profiles with model/provider/base_url."""
    profiles = []
    try:
        import json
        cfgs = []
        for path in [Path(settings.BASE_DIR) / "swarm_config.json", get_user_config_dir_for_swarm() / "swarm_config.json"]:
            if path.exists():
                cfgs.append(json.loads(path.read_text()))
        seen = set()
        for cfg in cfgs:
            llm = cfg.get("llm", {}) if isinstance(cfg, dict) else {}
            # support both nested profiles and flat mapping
            if "profiles" in llm and isinstance(llm["profiles"], dict):
                iterable = llm["profiles"].items()
            else:
                iterable = llm.items()
            for name, data in iterable:
                if name in seen or not isinstance(data, dict):
                    continue
                seen.add(name)
                profiles.append({
                    "name": name,
                    "provider": data.get("provider"),
                    "model": data.get("model"),
                    "base_url": data.get("base_url"),
                })
    except Exception:
        profiles = []
    return render(request, "profiles.html", {"profiles": profiles})
