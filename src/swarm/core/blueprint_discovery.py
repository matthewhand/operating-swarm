import importlib
import importlib.util
import inspect
import logging
import re
import sys
from pathlib import Path
from typing import Any, TypedDict

logger = logging.getLogger(__name__)

# Programmatic model-id / alias form (dir names, dynamic-team, hybrid-consensus).
# Rejects display names ("Chuck's Angels") and class names ("ChatbotBlueprint").
_MODEL_ID_RE = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")

try:
    from swarm.core.blueprint_base import BlueprintBase
except ImportError:
    logger.error("Failed to import BlueprintBase from swarm.core.blueprint_base. Ensure it is correctly placed.", exc_info=True)
    # To prevent further issues, we should probably raise an error or exit
    # if BlueprintBase is critical and not found. For now, discovery will likely fail.
    class BlueprintBase: pass # Minimal placeholder to allow type hints, but discovery will be broken.


class BlueprintMetadata(TypedDict, total=False):
    """Structure for metadata extracted from a blueprint."""
    name: str
    version: str | None
    description: str | None
    author: str | None
    abbreviation: str | None
    # Optional extended fields commonly used by blueprints
    required_mcp_servers: list[str] | None
    env_vars: list[str] | None
    tool_requirements: dict[str, str] | None  # capability -> "mandatory"|"optional"
    deprecated: bool | None
    status: str | None
    role: str | None
    navbar_items: list[dict[str, Any]] | None
    # Add other common metadata fields here if needed for typing

class DiscoveredBlueprintInfo(TypedDict):
    """Structure for the information returned by discover_blueprints for each blueprint."""
    class_type: type[BlueprintBase]
    metadata: BlueprintMetadata


class BlueprintLoadError(Exception):
    """Custom exception for errors during blueprint loading."""
    pass


def _path_is_under(path: Path, root: Path) -> bool:
    """Return True if *path* is *root* or a descendant of *root*."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _should_sandbox_blueprint_dir(blueprint_dir: Path, sandboxed: bool | None) -> bool:
    """Decide whether to run the AST sandbox before exec_module.

    Explicit ``sandboxed=True/False`` wins.  When *None*, auto-detect the user
    blueprints directory (community/extra roots pass sandboxed=True from merge).
    """
    from swarm.core.blueprint_sandbox import sandbox_enabled

    if not sandbox_enabled():
        return False
    if sandboxed is True:
        return True
    if sandboxed is False:
        return False
    try:
        from swarm.core.paths import get_user_blueprints_dir
        return _path_is_under(blueprint_dir, get_user_blueprints_dir())
    except Exception:
        return False


# This function was defined but not used in the original discover_blueprints.
# It might be useful if blueprint names from directories need canonicalization.
# def _get_blueprint_name_from_dir(dir_name: str) -> str:
#     """Converts directory name (e.g., 'blueprint_my_agent') to blueprint name (e.g., 'my_agent')."""
def discover_blueprints(blueprint_dir: str, namespace: str | None = None, *, sandboxed: bool | None = None) -> dict[str, DiscoveredBlueprintInfo]:
    """
    Discovers blueprints by looking for Python files within subdirectories
    of the given blueprint directory. Extracts metadata including name, version,
    description (with docstring fallback), and abbreviation.
    Supports `deprecated: true` and `status` in bp.metadata for incomplete bps
    (see audit_status.json; future: skip in list or warn in CLI/UI). CI hint: gate on no "incomplete" in prod lists.

    Args:
        blueprint_dir: The path to the directory containing blueprint subdirectories.
        namespace: Optional synthetic module namespace (community packs).
        sandboxed: When True, run AST safety checks before exec_module.
            When None (default), auto-enable for the user blueprints dir.
            Disabled entirely when SWARM_USER_BLUEPRINT_SANDBOX is false.

    Returns:
        A dictionary mapping blueprint directory names (as keys) to
        DiscoveredBlueprintInfo objects containing the blueprint class and its metadata.
    """
    logger.info(f"Starting blueprint discovery in directory: {blueprint_dir}")
    blueprints: dict[str, DiscoveredBlueprintInfo] = {}
    base_dir = Path(blueprint_dir).resolve()
    apply_sandbox = _should_sandbox_blueprint_dir(base_dir, sandboxed)
    if apply_sandbox:
        logger.debug("AST sandbox enabled for blueprint discovery in %s", base_dir)

    if not base_dir.is_dir():
        logger.error(f"Blueprint directory not found or is not a directory: {base_dir}")
        return blueprints

    for subdir in base_dir.iterdir():
        if not subdir.is_dir() or subdir.name.startswith('.') or subdir.name == "__pycache__":
            continue

        # Use directory name as the primary identifier/key for the blueprint
        blueprint_key_name = subdir.name
        logger.debug(f"Processing potential blueprint '{blueprint_key_name}' in directory: {subdir.name}")

        # Standard search: blueprint_{blueprint_key_name}.py or {blueprint_key_name}.py
        # (Adjusted to prioritize {blueprint_key_name}.py as per common practice,
        # then blueprint_{blueprint_key_name}.py if that's a convention)

        # Attempt 1: {blueprint_key_name}.py (e.g., codey.py in codey/ directory)
        py_file_path = subdir / f"{blueprint_key_name}.py"
        py_file_name = py_file_path.name

        if not py_file_path.is_file():
            # Attempt 2: blueprint_{blueprint_key_name}.py (e.g., blueprint_codey.py in codey/ directory)
            py_file_path = subdir / f"blueprint_{blueprint_key_name}.py"
            py_file_name = py_file_path.name
            if not py_file_path.is_file():
                # Special handling for stubs like messenger (no py impl - mark properly)
                if blueprint_key_name == "messenger":
                    logger.info(f"Recognized stub blueprint dir without py: {blueprint_key_name}")
                    stub_meta: BlueprintMetadata = {
                        'name': 'messenger',
                        'abbreviation': 'msg',
                        'description': 'Messenger UI template/theme only (stub; no Python implementation)',
                        'version': None,
                        'author': None,
                        'required_mcp_servers': [],
                        'env_vars': [],
                    }
                    # Use minimal class stub for type
                    class _MessengerStub(BlueprintBase):
                        metadata = stub_meta
                        def run(self, *a, **k): return; yield  # type: ignore
                    _MessengerStub.__module__ = "swarm.blueprints.messenger.blueprint_messenger"
                    blueprints[blueprint_key_name] = DiscoveredBlueprintInfo(
                        class_type=_MessengerStub,
                        metadata=stub_meta
                    )
                    continue
                logger.warning(f"Skipping directory '{subdir.name}': No suitable main Python file "
                               f"('{blueprint_key_name}.py' or 'blueprint_{blueprint_key_name}.py') found.")
                continue

        logger.debug(f"Found blueprint file: {py_file_name} in {subdir}")

        # Construct module import path, using namespace if provided (for community blueprints)
        if namespace:
            module_import_path = f"{namespace}.{subdir.name}.{py_file_path.stem}"
        else:
            module_import_path = f"{base_dir.parent.name}.{base_dir.name}.{subdir.name}.{py_file_path.stem}"

        try:
            # Ensure the parent of 'swarm' (e.g., 'src') is in sys.path if not already.
            # This helps Python find the 'swarm' package.
            # If blueprint_dir is 'src/swarm/blueprints', then base_dir.parent.parent is 'src'.
            project_src_dir = str(base_dir.parent.parent)
            if project_src_dir not in sys.path:
                logger.debug(f"Adding '{project_src_dir}' to sys.path for module import.")
                sys.path.insert(0, project_src_dir)

            module_spec = importlib.util.spec_from_file_location(module_import_path, py_file_path)

            if module_spec and module_spec.loader:
                if apply_sandbox:
                    from swarm.core.blueprint_sandbox import (
                        assert_safe_blueprint_source,
                    )
                    try:
                        source_text = py_file_path.read_text(encoding="utf-8")
                        assert_safe_blueprint_source(source_text)
                    except ValueError as sandbox_err:
                        logger.warning(
                            "Skipping unsafe user blueprint %s: %s",
                            py_file_path,
                            sandbox_err,
                        )
                        continue
                    except OSError as read_err:
                        logger.warning(
                            "Skipping blueprint %s (could not read for sandbox): %s",
                            py_file_path,
                            read_err,
                        )
                        continue
                module = importlib.util.module_from_spec(module_spec)
                # Register module before execution to handle circular imports within blueprint
                sys.modules[module_import_path] = module
                module_spec.loader.exec_module(module)
                logger.debug(f"Successfully loaded module: {module_import_path}")

                found_bp_class_details = None
                seen_class_ids: set[int] = set()
                for member_name, member_obj in inspect.getmembers(module):
                    if inspect.isclass(member_obj) and \
                       issubclass(member_obj, BlueprintBase) and \
                       member_obj is not BlueprintBase and \
                       member_obj.__module__ == module_import_path: # Ensure class is defined in this module

                        # Skip re-exports / legacy aliases of the same class object
                        # (e.g. CliFusionBlueprint = MoABlueprint).
                        cid = id(member_obj)
                        if cid in seen_class_ids:
                            continue
                        seen_class_ids.add(cid)

                        if found_bp_class_details:
                            logger.warning(f"Multiple BlueprintBase subclasses found in {py_file_name}. "
                                           f"Using the first one found: '{found_bp_class_details['metadata']['name']}'. "
                                           f"Previously found: '{member_name}'.")
                            continue # Stick with the first one

                        logger.debug(f"Found Blueprint class '{member_name}' in module '{module_import_path}'")

                        # Extract metadata
                        class_metadata_attr = getattr(member_obj, 'metadata', {})
                        if not isinstance(class_metadata_attr, dict):
                            logger.warning(f"Blueprint class '{member_name}' has a 'metadata' attribute that is not a dict. "
                                           f"Type: {type(class_metadata_attr)}. Skipping metadata extraction for this field.")
                            class_metadata_attr = {}

                        # Description: from metadata, fallback to class docstring
                        description = class_metadata_attr.get('description')
                        if not description:
                            docstring = inspect.getdoc(member_obj)
                            if docstring:
                                description = docstring.strip()
                                logger.debug(f"Using class docstring for description of '{member_name}'.")

                        # Start with the full metadata dict to preserve any
                        # additional fields (e.g., required_mcp_servers, env_vars).
                        # Then apply safe fallbacks/overrides for common keys.
                        full_meta: dict[str, Any] = dict(class_metadata_attr)
                        full_meta.setdefault('name', blueprint_key_name)
                        if description and not full_meta.get('description'):
                            full_meta['description'] = description

                        if full_meta.get('navbar_items') is None and hasattr(member_obj, 'get_navbar_items'):
                            try:
                                items = member_obj.get_navbar_items()
                                if items:
                                    full_meta['navbar_items'] = items
                            except TypeError:
                                try:
                                    items = member_obj.get_navbar_items(None)
                                    if items:
                                        full_meta['navbar_items'] = items
                                except Exception:
                                    pass

                        # Narrow to a TypedDict view for return typing, but keep extra keys
                        current_blueprint_metadata: BlueprintMetadata = {
                            'name': full_meta.get('name'),
                            'version': full_meta.get('version'),
                            'description': full_meta.get('description'),
                            'author': full_meta.get('author'),
                            'abbreviation': full_meta.get('abbreviation'),
                            'required_mcp_servers': full_meta.get('required_mcp_servers'),
                            'env_vars': full_meta.get('env_vars'),
                            'tool_requirements': full_meta.get('tool_requirements'),
                            'deprecated': full_meta.get('deprecated'),
                            'status': full_meta.get('status'),
                            'role': full_meta.get('role'),
                            'navbar_items': full_meta.get('navbar_items'),
                        }

                        found_bp_class_details = DiscoveredBlueprintInfo(
                            class_type=member_obj,
                            metadata=current_blueprint_metadata
                        )
                        # Storing by blueprint_key_name (directory name)
                        blueprints[blueprint_key_name] = found_bp_class_details
                        # Also register metadata aliases (e.g. moa → mixture_of_agents, cli_fusion)
                        aliases = full_meta.get("aliases") or []
                        if isinstance(aliases, (list, tuple, set, frozenset)):
                            for alias in aliases:
                                key = str(alias).strip()
                                if not key or key in blueprints:
                                    continue
                                if not _MODEL_ID_RE.fullmatch(key):
                                    logger.debug(
                                        "Skipping non-slug alias %r for %r",
                                        key,
                                        blueprint_key_name,
                                    )
                                    continue
                                blueprints[key] = found_bp_class_details
                                logger.debug(
                                    "Registered blueprint alias %r → %r",
                                    key,
                                    blueprint_key_name,
                                )
                        # metadata["name"] is often a display/class label; only
                        # promote it to a model id when it is a programmatic slug.
                        meta_name = str(full_meta.get("name") or "").strip()
                        if (
                            meta_name
                            and meta_name not in blueprints
                            and _MODEL_ID_RE.fullmatch(meta_name)
                        ):
                            blueprints[meta_name] = found_bp_class_details
                        elif meta_name and meta_name not in blueprints:
                            logger.debug(
                                "Skipping non-slug metadata name %r as model id for %r",
                                meta_name,
                                blueprint_key_name,
                            )

                if not found_bp_class_details:
                    logger.warning(f"No BlueprintBase subclass found directly defined in module: {module_import_path}")
            else:
                logger.warning(f"Could not create module spec for {py_file_path}")

        except Exception as e:
            logger.error(f"Error processing blueprint file '{py_file_path}': {e}", exc_info=True)
            # Clean up sys.modules if import failed partway
            if module_import_path in sys.modules:
                del sys.modules[module_import_path]

    logger.info(f"Blueprint discovery complete. Found {len(blueprints)} blueprints: {list(blueprints.keys())}")
    return blueprints

if __name__ == '__main__':
    # Example Usage (assuming you have a 'blueprints' directory structured correctly)
    # Create a dummy BlueprintBase and a dummy blueprint for testing
    logging.basicConfig(level=logging.DEBUG)

    # Create dummy structure for testing
    Path("src/swarm/blueprints/example_bp").mkdir(parents=True, exist_ok=True)

    # Dummy swarm.core.blueprint_base
    Path("src/swarm/core").mkdir(parents=True, exist_ok=True)
    with open("src/swarm/core/blueprint_base.py", "w") as f:
        f.write("from abc import ABC, abstractmethod\n")
        f.write("class BlueprintBase(ABC):\n")
        f.write("    metadata = {}\n") # Ensure metadata attr exists for getattr
        f.write("    @abstractmethod\n")
        f.write("    def run(self):\n")
        f.write("        pass\n")

    # Dummy blueprint file: src/swarm/blueprints/example_bp/example_bp.py
    with open("src/swarm/blueprints/example_bp/example_bp.py", "w") as f:
        f.write("from swarm.core.blueprint_base import BlueprintBase\n")
        f.write("class MyExampleBlueprint(BlueprintBase):\n")
        f.write("    \"\"\"This is an example blueprint's docstring.\"\"\"\n")
        f.write("    metadata = {\n")
        f.write("        'name': 'ExampleBP',\n")
        f.write("        'version': '1.0.1',\n")
        # No description in metadata to test docstring fallback
        f.write("        'author': 'Test Author',\n")
        f.write("        'abbreviation': 'exbp'\n")
        f.write("    }\n")
        f.write("    def run(self):\n")
        f.write("        print('ExampleBP running')\n")

    # Test discovery (assuming 'src' is in PYTHONPATH or script is run from project root)
    # The script assumes blueprint_dir is relative to where Python resolves 'swarm.blueprints'
    # For this test, let's point to 'src/swarm/blueprints'
    discovered = discover_blueprints("src/swarm/blueprints")
    for name, info in discovered.items():
        print(f"\nDiscovered Blueprint Key: {name}")
        print(f"  Class: {info['class_type'].__name__}")
        print("  Metadata:")
        for meta_key, meta_val in info['metadata'].items():
            print(f"    {meta_key}: {meta_val}")

    # Cleanup dummy files
    # import shutil
    # shutil.rmtree("src/swarm/blueprints/example_bp")
    # Path("src/swarm/core/blueprint_base.py").unlink()
    # Potentially rmdir for src/swarm/core and src/swarm/blueprints if they were created solely for this

def merge_community_blueprints(
    base: dict[str, DiscoveredBlueprintInfo],
    extra_dirs: "list[str] | None" = None,
) -> dict[str, DiscoveredBlueprintInfo]:
    """Merge external/community blueprint roots into an already-discovered dict."""
    merged = dict(base)
    for index, directory in enumerate(extra_dirs or []):
        if not directory or not Path(directory).is_dir():
            continue
        try:
            found = discover_blueprints(
                directory,
                namespace=f"swarm_community_{index}",
                sandboxed=True,
            )
        except Exception:
            logger.exception("Failed discovering community blueprints in %s", directory)
            continue
        for name, info in found.items():
            if name in merged:
                logger.warning(
                    "Community blueprint %r in %s collides with a bundled blueprint; ignoring it.",
                    name, directory,
                )
                continue
            merged[name] = info
    return merged


BLUEPRINT_ALIASES: dict[str, str] = {
    "swarm_ensemble": "cli_fusion",
    "swarm_map": "cli_map",
    "swarm_recurse": "cli_recurse",
    "swarm_pipeline": "cli_pipeline",
    "swarm_roundtable": "cli_roundtable",
    "swarm_planner": "cli_planner",
    "swarm_orchestrator": "cli_orchestrator",
}


def apply_blueprint_aliases(
    blueprints: dict[str, DiscoveredBlueprintInfo],
) -> dict[str, DiscoveredBlueprintInfo]:
    """Register canonical ``swarm_*`` aliases for discovered ``cli_*`` patterns."""
    for alias, target in BLUEPRINT_ALIASES.items():
        if alias in blueprints or target not in blueprints:
            continue
        info = dict(blueprints[target])
        meta = dict(info.get("metadata") or {})
        meta["name"] = alias
        info["metadata"] = meta
        blueprints[alias] = info
    return blueprints


def discover_all_blueprints(
    blueprint_dir: str,
    extra_dirs: "list[str] | None" = None,
) -> dict[str, DiscoveredBlueprintInfo]:
    """Discover bundled + community blueprints and apply aliases."""
    base = discover_blueprints(blueprint_dir)
    merged = merge_community_blueprints(base, extra_dirs)
    return apply_blueprint_aliases(merged)
