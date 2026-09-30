"""Translate a TeamAI git layout into Operating Swarm skills and reviewer seats.

TeamAI (``teamai-cli`` + ``teamai-template``) is a packaging layout, not a seat
kind. This module reads that layout and emits OS primitives:

* ``skills/**/SKILL.md`` → Agent Skills (file copy only; nothing is executed)
* ``rules/`` → one shared baseline skill (``teamai-baseline``)
* ``agents/*.md`` → reviewer specs on the skeptic / gate / engineer roles
* ``mcp/mcp.yaml`` → server names and env-var *names* (values are dropped)
* ``models/models.yaml`` → model ids kept only when they belong to the API
  namespace

Hooks are ignored. ``.env`` files are not read. No network calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from swarm.core.model_namespace import model_valid_for_provider
from swarm.core.paths import get_project_root_dir
from swarm.core.skills import SKILL_FILE, parse_skill_md

PACK_DIRNAME = "teamai"
BASELINE_SKILL_NAME = "teamai-baseline"
TEAM_PACK_ID = "teamai-reviewers"
MAX_SKILL_FILES = 32
MAX_SKILL_FILE_BYTES = 256 * 1024
MAX_INSTRUCTION_CHARS = 64_000
PERSONALITY_INSTRUCTION_LIMIT = 8000
# Vendored agents name Claude Code tools (Read/Grep/Glob/Bash) and tell the
# model to run git, npm, and psql. This seat does not get those tools.
_NO_UPSTREAM_TOOLS = (
    "Operating Swarm does not attach the upstream Read, Grep, Glob, or Bash "
    "tools on this seat. Do not run shell, git, npm, or psql. Review only "
    "the material in this conversation."
)

# Reference-template reviewers → existing OS roles. teamai-cli stays a
# packaging tool; these three are ordinary API blueprints.
REVIEWER_ROLES: dict[str, str] = {
    "code-reviewer": "skeptic",
    "security-reviewer": "gate",
    "database-reviewer": "engineer",
}

REVIEWER_BLUEPRINT_IDS: dict[str, str] = {
    "code-reviewer": "code_reviewer",
    "security-reviewer": "security_reviewer",
    "database-reviewer": "database_reviewer",
}

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
_PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_ENV_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")


class TeamAiImportError(ValueError):
    """The path is not a readable TeamAI layout."""


@dataclass
class SkillSource:
    name: str
    description: str
    relative_dir: str


@dataclass
class ReviewerSpec:
    name: str
    role: str
    description: str
    instructions: str
    source: str
    blueprint_id: str
    dropped_model: str = ""
    kept_model: str = ""


@dataclass
class TeamAiPlan:
    """In-memory translation. Applying it copies files; it does not run them."""

    skills: list[SkillSource] = field(default_factory=list)
    baseline_markdown: str = ""
    reviewers: list[ReviewerSpec] = field(default_factory=list)
    team_pack: dict[str, Any] = field(default_factory=dict)
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    kept_model_pins: list[str] = field(default_factory=list)
    dropped_model_pins: list[str] = field(default_factory=list)
    required_env: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "skills": [
                {"name": s.name, "description": s.description, "path": s.relative_dir}
                for s in self.skills
            ],
            "baseline_skill": BASELINE_SKILL_NAME if self.baseline_markdown else "",
            "reviewers": [
                {
                    "name": r.name,
                    "role": r.role,
                    "description": r.description,
                    "source": r.source,
                    "blueprint_id": r.blueprint_id,
                    "dropped_model": r.dropped_model,
                    "kept_model": r.kept_model,
                }
                for r in self.reviewers
            ],
            "team_pack": self.team_pack,
            "mcp_servers": self.mcp_servers,
            "kept_model_pins": list(self.kept_model_pins),
            "dropped_model_pins": list(self.dropped_model_pins),
            "required_env": list(self.required_env),
            "skipped": list(self.skipped),
            "warnings": list(self.warnings),
        }


def bundled_pack_root() -> Path:
    """Vendored rules, agents, and license notices (not a seat install)."""
    return Path(get_project_root_dir()) / "packs" / PACK_DIRNAME


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER_RE.match(text.lstrip("\ufeff"))
    if not match:
        return {}, text.strip()
    loaded = yaml.safe_load(match.group(1)) or {}
    if not isinstance(loaded, dict):
        loaded = {}
    return loaded, (match.group(2) or "").strip()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _read_text(path: Path, root: Path) -> str | None:
    """Read a regular file inside ``root``. Symlinks and outsiders are skipped."""
    if path.is_symlink() or not path.is_file():
        return None
    if not _inside(path, root):
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) > MAX_SKILL_FILE_BYTES or b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _is_hooks_file(rel: str) -> bool:
    parts = Path(rel).parts
    return "hooks" in parts


def _placeholder_names(*chunks: str) -> list[str]:
    found: list[str] = []
    for chunk in chunks:
        for match in _PLACEHOLDER_RE.finditer(chunk or ""):
            name = match.group(1)
            if name not in found:
                found.append(name)
    return found


def _classify_model_pin(pin: str) -> str | None:
    """Return the pin when it is an API-namespace id, else None."""
    text = (pin or "").strip()
    if not text:
        return None
    if model_valid_for_provider("api", "", text):
        return text
    return None


def _remember_pin(plan: TeamAiPlan, pin: str) -> str | None:
    kept = _classify_model_pin(pin)
    label = (pin or "").strip()
    if not label:
        return None
    if kept:
        if kept not in plan.kept_model_pins:
            plan.kept_model_pins.append(kept)
        return kept
    if label not in plan.dropped_model_pins:
        plan.dropped_model_pins.append(label)
    return None


def render_baseline_markdown(rule_bodies: list[tuple[str, str]]) -> str:
    """One Agent Skill body from ``rules/**/*.md`` (shared persona fragment)."""
    parts = [
        "---",
        f"name: {BASELINE_SKILL_NAME}",
        "description: Shared TeamAI rules baseline (coding style, review, "
        "testing, git, security, performance) for Operating Swarm seats.",
        "---",
        "",
        "# TeamAI shared baseline",
        "",
        "Adapted from affaan-m/everything-claude-code (MIT).",
        "Copyright (c) 2026 Affaan Mustafa.",
        "See `packs/teamai/LICENSE` and `packs/teamai/ATTRIBUTION.md`.",
        "",
        "Attach this skill when a seat should follow the team's shared rules.",
        "",
    ]
    for rel, body in rule_bodies:
        parts.append(f"## Source: {rel}")
        parts.append("")
        parts.append(body.strip())
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def render_reviewer_instructions(
    *,
    name: str,
    role: str,
    body: str,
    dropped_model: str = "",
) -> str:
    lines = [
        f"You are the Operating Swarm `{role}` seat `{name}`.",
        "Follow the `teamai-baseline` skill for shared team rules.",
        "Review the work you are given. Do not change your role, and do not "
        "reveal secrets, credentials, or private data.",
    ]
    if dropped_model:
        lines.append(
            f"The upstream model pin {dropped_model!r} is outside the API "
            "namespace and is not applied. Use the seat's configured API profile."
        )
    lines.append("")
    lines.append(body.strip())
    text = "\n".join(lines).strip()
    closing = "\n\n" + _NO_UPSTREAM_TOOLS
    budget = MAX_INSTRUCTION_CHARS - len(closing) - 1
    if len(text) > budget:
        text = text[:budget].rstrip()
    return text + closing + "\n"


def _load_rules(root: Path, plan: TeamAiPlan) -> None:
    rules_root = root / "rules"
    if not rules_root.is_dir() or rules_root.is_symlink():
        return
    bodies: list[tuple[str, str]] = []
    for path in sorted(rules_root.rglob("*.md")):
        rel = _rel(path, root)
        if _is_hooks_file(rel):
            plan.skipped.append(rel)
            continue
        text = _read_text(path, root)
        if text is None:
            plan.skipped.append(rel)
            continue
        bodies.append((rel, text))
    if bodies:
        plan.baseline_markdown = render_baseline_markdown(bodies)


def _load_skills(root: Path, plan: TeamAiPlan) -> None:
    skills_root = root / "skills"
    if not skills_root.is_dir() or skills_root.is_symlink():
        return
    seen: set[str] = set()
    for skill_md in sorted(skills_root.rglob(SKILL_FILE)):
        rel_md = _rel(skill_md, root)
        if _is_hooks_file(rel_md):
            plan.skipped.append(rel_md)
            continue
        text = _read_text(skill_md, root)
        if text is None:
            plan.skipped.append(rel_md)
            continue
        try:
            parsed = parse_skill_md(text, name_hint=skill_md.parent.name)
        except ValueError as exc:
            plan.skipped.append(f"{rel_md}: {exc}")
            continue
        if parsed.name in seen:
            plan.skipped.append(f"{rel_md}: duplicate skill name {parsed.name}")
            continue
        seen.add(parsed.name)
        plan.skills.append(
            SkillSource(
                name=parsed.name,
                description=parsed.description,
                relative_dir=_rel(skill_md.parent, root),
            )
        )


def _load_agents(root: Path, plan: TeamAiPlan, *, bundled: bool) -> None:
    agents_root = root / "agents"
    if not agents_root.is_dir() or agents_root.is_symlink():
        return
    for path in sorted(agents_root.glob("*.md")):
        rel = _rel(path, root)
        text = _read_text(path, root)
        if text is None:
            plan.skipped.append(rel)
            continue
        meta, body = _split_frontmatter(text)
        if not body:
            plan.skipped.append(f"{rel}: empty agent body")
            continue
        name = str(meta.get("name") or path.stem).strip()
        role = REVIEWER_ROLES.get(name, "default")
        raw_pin = str(meta.get("model") or "").strip()
        kept = _remember_pin(plan, raw_pin) if raw_pin else None
        dropped = raw_pin if raw_pin and not kept else ""
        blueprint_id = REVIEWER_BLUEPRINT_IDS.get(name, "")
        if bundled and blueprint_id:
            source = f"blueprint:{blueprint_id}"
        else:
            source = f"personality:{name}"
            blueprint_id = blueprint_id or name.replace("-", "_")
        description = str(meta.get("description") or "").strip()
        instructions = render_reviewer_instructions(
            name=name,
            role=role,
            body=body,
            dropped_model=dropped,
        )
        plan.reviewers.append(
            ReviewerSpec(
                name=name,
                role=role,
                description=description[:280],
                instructions=instructions,
                source=source,
                blueprint_id=blueprint_id,
                dropped_model=dropped,
                kept_model=kept or "",
            )
        )


def _env_names_from_mapping(raw: Any) -> tuple[list[str], bool]:
    """Env-var names from an ``env:`` map. Values are never returned.

    A non-empty value with no ``${VAR}`` placeholder counts as a discarded
    literal. Header maps must not use this helper — header names are not env
    vars.
    """
    names: list[str] = []
    leaked = False
    if not isinstance(raw, dict):
        return names, leaked
    for key, value in raw.items():
        value_text = value if isinstance(value, str) else ""
        placeholders = _placeholder_names(value_text)
        for name in placeholders:
            if name not in names:
                names.append(name)
        key_text = str(key or "").strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key_text) and key_text not in names:
            names.append(key_text)
        if value_text and not placeholders:
            leaked = True
    return names, leaked


def _header_env_names(raw: Any) -> tuple[list[str], bool]:
    """Placeholder names referenced by header values. Header names are dropped."""
    names: list[str] = []
    leaked = False
    if not isinstance(raw, dict):
        return names, leaked
    for value in raw.values():
        value_text = value if isinstance(value, str) else ""
        placeholders = _placeholder_names(value_text)
        if value_text and not placeholders:
            leaked = True
        for name in placeholders:
            if name not in names:
                names.append(name)
    return names, leaked


def _load_mcp(root: Path, plan: TeamAiPlan) -> None:
    for ignored in ("mcp.json", ".mcp.json"):
        if (root / ignored).is_file():
            plan.warnings.append(
                f"Ignored {ignored}. Expected mcp/mcp.yaml, and secret values "
                "are never imported."
            )
    mcp_root = root / "mcp"
    if not mcp_root.is_dir() or mcp_root.is_symlink():
        return
    files = [mcp_root / "mcp.yaml"]
    files.extend(sorted(p for p in mcp_root.glob("*/mcp.yaml")))
    for path in files:
        if not path.is_file():
            continue
        text = _read_text(path, root)
        if text is None:
            plan.skipped.append(_rel(path, root))
            continue
        try:
            loaded = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            plan.skipped.append(f"{_rel(path, root)}: {exc}")
            continue
        servers = loaded.get("servers") if isinstance(loaded, dict) else None
        if not isinstance(servers, list):
            plan.skipped.append(f"{_rel(path, root)}: no servers list")
            continue
        for row in servers:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            transport = str(row.get("transport") or "").strip()
            names, leaked = _env_names_from_mapping(row.get("env"))
            header_names, header_leak = _header_env_names(row.get("headers"))
            for item in header_names:
                if item not in names:
                    names.append(item)
            for item in _placeholder_names(
                str(row.get("url") or ""),
                str(row.get("command") or ""),
            ):
                if item not in names:
                    names.append(item)
            if leaked or header_leak:
                plan.warnings.append(
                    f"Discarded literal MCP values for server {name!r}."
                )
            plan.mcp_servers.append(
                {
                    "name": name,
                    "transport": transport,
                    "required_env": names,
                    "installed": False,
                }
            )
            for item in names:
                if item not in plan.required_env:
                    plan.required_env.append(item)


def _load_models(root: Path, plan: TeamAiPlan) -> None:
    models_root = root / "models"
    if not models_root.is_dir() or models_root.is_symlink():
        return
    files = [models_root / "models.yaml"]
    files.extend(sorted(p for p in models_root.glob("*/models.yaml")))
    for path in files:
        if not path.is_file():
            continue
        text = _read_text(path, root)
        if text is None:
            plan.skipped.append(_rel(path, root))
            continue
        try:
            loaded = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            plan.skipped.append(f"{_rel(path, root)}: {exc}")
            continue
        profiles = loaded.get("profiles") if isinstance(loaded, dict) else None
        if not isinstance(profiles, list):
            plan.skipped.append(f"{_rel(path, root)}: no profiles list")
            continue
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            for name in _placeholder_names(str(profile.get("api_key") or "")):
                if name not in plan.required_env:
                    plan.required_env.append(name)
            if profile.get("api_key") and not _placeholder_names(
                str(profile.get("api_key") or "")
            ):
                plan.warnings.append(
                    "Discarded a literal model api_key. Only ${VAR} names are kept."
                )
            groups = profile.get("model_groups") or []
            if not isinstance(groups, list):
                continue
            for group in groups:
                if not isinstance(group, dict):
                    continue
                models = group.get("models") or []
                if not isinstance(models, list):
                    continue
                for model in models:
                    _remember_pin(plan, str(model or ""))


def _iter_notice_files(root: Path) -> list[Path]:
    """Top-level env/hook files plus ``env/`` and ``hooks/``. Not a full-repo walk."""
    found: list[Path] = []
    try:
        children = list(root.iterdir())
    except OSError:
        return found
    for path in children:
        lowered = path.name.lower()
        if path.name in {".env", "hooks"} or "env" in lowered:
            found.append(path)
    for folder in ("env", "hooks"):
        base = root / folder
        if base.is_dir() and not base.is_symlink():
            found.extend(sorted(base.rglob("*")))
    return found


def _note_ignored_secrets(root: Path, plan: TeamAiPlan) -> None:
    seen: set[str] = set()
    for path in _iter_notice_files(root):
        if not path.is_file() or path.is_symlink() or not _inside(path, root):
            continue
        rel = _rel(path, root)
        if rel in seen:
            continue
        seen.add(rel)
        name = path.name
        ignored_env = name == ".env" or (
            name.endswith(".env") and "example" not in name
        )
        if ignored_env:
            plan.warnings.append(f"Ignored {rel} (env values are not imported).")
            continue
        if "example" in name and "env" in name.lower():
            text = _read_text(path, root)
            if not text:
                continue
            for line in text.splitlines():
                match = _ENV_KEY_RE.match(line.strip())
                if match and match.group(1) not in plan.required_env:
                    plan.required_env.append(match.group(1))
        if _is_hooks_file(rel) and path.suffix != ".md":
            plan.skipped.append(rel)


def _team_pack(plan: TeamAiPlan) -> dict[str, Any]:
    members = []
    for reviewer in plan.reviewers:
        member: dict[str, str] = {
            "id": reviewer.name,
            "name": reviewer.name.replace("-", " ").title(),
            "kind": "api",
            "role": reviewer.role,
            "source": reviewer.source,
        }
        if reviewer.description:
            member["description"] = reviewer.description[:280]
        members.append(member)
    return {
        "id": TEAM_PACK_ID,
        "name": "TeamAI Reviewers",
        "members": members,
        "wires": {"handoff": True, "as_tool": True},
    }


def translate_teamai_repo(root: str | Path) -> TeamAiPlan:
    """Read a TeamAI directory. Raises ``TeamAiImportError`` when it is not one.

    Does not copy files, install MCP servers, or execute hooks.
    """
    path = Path(root)
    if path.is_symlink() or not path.is_dir():
        raise TeamAiImportError(f"Not a TeamAI directory: {root}")
    markers = ("skills", "rules", "agents")
    if not any((path / name).is_dir() for name in markers):
        raise TeamAiImportError(
            "Not a TeamAI layout (expected skills/, rules/, or agents/)."
        )
    plan = TeamAiPlan()
    bundled = path.resolve() == bundled_pack_root().resolve()
    _load_skills(path, plan)
    _load_rules(path, plan)
    _load_agents(path, plan, bundled=bundled)
    _load_mcp(path, plan)
    _load_models(path, plan)
    _note_ignored_secrets(path, plan)
    if plan.baseline_markdown:
        try:
            parse_skill_md(plan.baseline_markdown, name_hint=BASELINE_SKILL_NAME)
        except ValueError as exc:
            raise TeamAiImportError(f"baseline skill is invalid: {exc}") from exc
    if not plan.skills and not plan.baseline_markdown and not plan.reviewers:
        raise TeamAiImportError("TeamAI layout contained no skills, rules, or agents.")
    plan.team_pack = _team_pack(plan)
    return plan


def reviewer_instructions(agent_name: str, *, root: Path | None = None) -> str:
    """Instructions for a bundled reviewer blueprint. Honest error if missing."""
    pack = root or bundled_pack_root()
    path = pack / "agents" / f"{agent_name}.md"
    text = _read_text(path, pack)
    if text is None:
        raise TeamAiImportError(
            f"Bundled reviewer {agent_name!r} is missing ({path.name})."
        )
    meta, body = _split_frontmatter(text)
    if not body:
        raise TeamAiImportError(f"Bundled reviewer {agent_name!r} has an empty body.")
    role = REVIEWER_ROLES.get(agent_name, "default")
    raw_pin = str(meta.get("model") or "").strip()
    kept = _classify_model_pin(raw_pin) if raw_pin else None
    return render_reviewer_instructions(
        name=agent_name,
        role=role,
        body=body,
        dropped_model=raw_pin if raw_pin and not kept else "",
    )


def reviewer_model_profile(agent_name: str, *, root: Path | None = None) -> str | None:
    """API-namespace model pin for a bundled reviewer, or None when dropped."""
    pack = root or bundled_pack_root()
    path = pack / "agents" / f"{agent_name}.md"
    text = _read_text(path, pack)
    if text is None:
        return None
    meta, _body = _split_frontmatter(text)
    kept = _classify_model_pin(str(meta.get("model") or ""))
    if kept and kept.lower() != "default":
        return kept
    return None


def build_reviewer_agent(
    blueprint: Any, agent_name: str, mcp_servers: list[Any] | None
):
    """openai-agents ``Agent`` for a bundled reviewer. Called on a live turn."""
    from agents import Agent

    profile = reviewer_model_profile(agent_name) or blueprint.llm_profile_name
    return Agent(
        name=REVIEWER_BLUEPRINT_IDS.get(agent_name, agent_name),
        instructions=reviewer_instructions(agent_name),
        model=blueprint._get_model_instance(profile),
        mcp_servers=list(mcp_servers or []),
    )


def _copy_tree(src_dir: Path, dest_dir: Path, root: Path) -> tuple[list[str], int]:
    """Copy regular files. Symlinks are skipped. The mode is not executable.

    ``SKILL.md`` is copied first so the file cap cannot drop the skill body.
    The second value is how many eligible files the cap left behind.
    """
    written: list[str] = []
    dest_dir.mkdir(parents=True, exist_ok=True)
    eligible: list[Path] = []
    for path in sorted(src_dir.rglob("*")):
        if not path.is_file() or path.is_symlink() or not _inside(path, root):
            continue
        rel = path.relative_to(src_dir)
        if any(part.startswith(".") for part in rel.parts):
            continue
        eligible.append(path)
    eligible.sort(key=lambda path: (path.name != SKILL_FILE, path.as_posix()))
    dropped = 0
    for path in eligible:
        if len(written) >= MAX_SKILL_FILES:
            dropped += 1
            continue
        text = _read_text(path, root)
        if text is None:
            continue
        rel = path.relative_to(src_dir)
        target = dest_dir.joinpath(*rel.parts)
        try:
            target.resolve().relative_to(dest_dir.resolve())
        except ValueError:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        written.append(rel.as_posix())
    return written, dropped


def apply_teamai_plan(
    plan: TeamAiPlan,
    *,
    source: str | Path,
    skills_dest: str | Path,
    seed_personalities: bool = False,
) -> dict[str, Any]:
    """Copy skills into ``skills_dest``. Does not execute files or install MCP.

    Personality designs are written only when ``seed_personalities`` is true,
    and only for reviewers that are not bundled blueprint seats.
    """
    root = Path(source)
    dest_root = Path(skills_dest)
    dest_root.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []
    for skill in plan.skills:
        src_dir = root / skill.relative_dir
        if not src_dir.is_dir() or src_dir.is_symlink():
            continue
        written, dropped = _copy_tree(src_dir, dest_root / skill.name, root)
        if dropped:
            plan.warnings.append(
                f"Copied {len(written)} files for skill {skill.name!r} and "
                f"left {dropped} behind the {MAX_SKILL_FILES}-file cap."
            )
        if (
            SKILL_FILE not in {Path(name).name for name in written}
            and not (dest_root / skill.name / SKILL_FILE).is_file()
        ):
            continue
        installed.append(skill.name)
    if plan.baseline_markdown:
        baseline = dest_root / BASELINE_SKILL_NAME
        baseline.mkdir(parents=True, exist_ok=True)
        (baseline / SKILL_FILE).write_text(plan.baseline_markdown, encoding="utf-8")
        installed.append(BASELINE_SKILL_NAME)
    for notice in (
        "LICENSE",
        "LICENSE-mattpocock",
        "ATTRIBUTION.md",
        "UPSTREAM_ATTRIBUTION.md",
    ):
        src = root / notice
        text = _read_text(src, root) if src.is_file() else None
        if text is None and notice == "LICENSE-mattpocock":
            # Upstream keeps this notice beside the skill dirs, not at the root,
            # and a root LICENSE (ECC) must not hide it.
            alt = root / "skills" / "mattpocock" / "LICENSE"
            text = _read_text(alt, root) if alt.is_file() else None
        if text is not None:
            (dest_root / notice).write_text(text, encoding="utf-8")
    personalities: list[str] = []
    if seed_personalities:
        from swarm.core.router_designs import upsert_design

        for reviewer in plan.reviewers:
            if reviewer.source.startswith("blueprint:"):
                continue
            instructions = reviewer.instructions
            if len(instructions) > PERSONALITY_INSTRUCTION_LIMIT:
                notice = (
                    "\n\n[truncated to the personality instruction limit]\n\n"
                    + _NO_UPSTREAM_TOOLS
                    + "\n"
                )
                keep = PERSONALITY_INSTRUCTION_LIMIT - len(notice)
                instructions = instructions[:keep].rstrip() + notice
            try:
                spec = upsert_design(
                    {
                        "kind": "personality",
                        "name": reviewer.name.replace("-", " ").title(),
                        "agent_id": reviewer.name,
                        "description": reviewer.description,
                        "instructions": instructions,
                        "specialty": f"TeamAI {reviewer.role} reviewer",
                    }
                )
            except ValueError as exc:
                plan.warnings.append(f"Did not seed personality {reviewer.name}: {exc}")
                continue
            personalities.append(str(spec.get("agent_id") or reviewer.name))
    return {
        "installed_skills": installed,
        "personalities": personalities,
        "mcp_installed": False,
        "team_pack": plan.team_pack,
        "warnings": list(plan.warnings),
    }
