"""#855 slice D — swarm.core.cli package.

Query-surface modules split out of ``swarm.core.cli_catalog`` (the data SoT
and the stable import surface, which rebinds every name below). Explicit
exports per the #855 acceptance criteria.
"""

from swarm.core.cli.models import (  # noqa: F401
    CLI_MODELS,
    LIST_MODELS,
    LIST_MODELS_TIMEOUT,
    MODEL_FLAG,
    MODEL_TRAITS,
    _model_flag_insert_at,
    apply_model,
    cli_traits,
    has_list_models,
    has_native_consensus,
    list_models_argv,
    model_traits,
    native_consensus_flags,
    with_model,
    with_native_consensus,
)
from swarm.core.cli.sessions import (  # noqa: F401
    _cli_agent_entry,
    can_export_transcript,
    can_list_sessions,
    export_capability,
    export_sessions_argv,
    list_capability,
    list_sessions_argv,
    list_sessions_catalog,
    list_sessions_store,
    list_sessions_store_dir,
)

__all__ = [
    "CLI_MODELS",
    "LIST_MODELS",
    "LIST_MODELS_TIMEOUT",
    "MODEL_FLAG",
    "MODEL_TRAITS",
    "_cli_agent_entry",
    "apply_model",
    "can_export_transcript",
    "can_list_sessions",
    "cli_traits",
    "export_capability",
    "export_sessions_argv",
    "has_list_models",
    "has_native_consensus",
    "list_capability",
    "list_models_argv",
    "list_sessions_argv",
    "list_sessions_catalog",
    "list_sessions_store",
    "list_sessions_store_dir",
    "_model_flag_insert_at",
    "model_traits",
    "native_consensus_flags",
    "with_model",
    "with_native_consensus",
]
