"""Herdr CLI client (REQ-21) and remotes kind (REQ-64 / REQ-100).

Operating Swarm drives Herdr as a **member kind=herdr** without owning the TUI.
This package wraps the official ``herdr`` CLI only — it does **not** speak the
unix-socket protocol, and it is **not** Hermes, OMB, or Rakazo.

**Local Herdr** talks to Herdr already on this host (no SSH; no ``--remote``).
**Remote Herdr** is SSH-shaped: SSH to the Herdr host, then use Herdr there.
That is not an HTTP remote like OpenMousBot / Hermes / Rakazo.

Cloud CI and unit tests must mock the CLI and stub SSH. Do not point tests
at a live TUI (especially a WORKING grok pane). Proven on-host shape:
``herdr agent prompt w3:p1 HERDR_PING_OK`` → ``type: agent_prompted``.
"""

from swarm.herdr.client import (
    AGENT_PROMPTED,
    MEMBER_KIND,
    WAIT_UNTIL_STATES,
    WAIT_UNTIL_STOPPED,
    HerdrBlockedError,
    HerdrClient,
    HerdrCLIError,
    HerdrError,
    extract_prompt_type,
    extract_state_change_seq,
    members_from_agent_list,
    members_from_workspace_list,
)
from swarm.herdr.remote import (
    API_KEY_ENV,
    BASE_URL_ENV,
    HEALTH_PATH,
    HERDR_HTTP_REMOTE_REFUSED,
    HERDR_MODE_LOCAL,
    HERDR_MODE_SSH,
    HERDR_NOT_CONFIGURED,
    HERDR_SSH_NOT_CONFIGURED,
    HOP_MODEL,
    KIND_ID,
    LIST_PATH,
    SSH_HOST_ENV,
    SSH_USER_ENV,
    cli_remote_from_base,
    herdr_client_from_spec,
    is_localhost_base,
    members_from_http_list,
    not_configured_message,
    resolve_herdr_mode,
    ssh_target_from_spec,
    uses_local_http_health,
)
from swarm.herdr.status import (
    HERDR_AGENT_STATUSES,
    SEAT_STATUSES,
    UNKNOWN_STATUS,
    HerdrPaneStatus,
    HerdrSeatStatus,
    normalize_agent_status,
    pane_id_of,
    pane_statuses,
    statuses_by_target,
)
from swarm.herdr.ssh import (
    SSH_NOT_CONFIGURED,
    SSHError,
    SSHNotConfiguredError,
    SSHTarget,
    SSHTransport,
    looks_like_key_material,
    remote_command_from_ssh_argv,
    require_ssh_target,
    stub_ssh_transport,
)

__all__ = [
    "AGENT_PROMPTED",
    "API_KEY_ENV",
    "BASE_URL_ENV",
    "HEALTH_PATH",
    "HERDR_HTTP_REMOTE_REFUSED",
    "HERDR_MODE_LOCAL",
    "HERDR_MODE_SSH",
    "HERDR_NOT_CONFIGURED",
    "HERDR_SSH_NOT_CONFIGURED",
    "HOP_MODEL",
    "HERDR_AGENT_STATUSES",
    "KIND_ID",
    "LIST_PATH",
    "MEMBER_KIND",
    "SEAT_STATUSES",
    "SSH_HOST_ENV",
    "SSH_NOT_CONFIGURED",
    "SSH_USER_ENV",
    "UNKNOWN_STATUS",
    "WAIT_UNTIL_STATES",
    "WAIT_UNTIL_STOPPED",
    "HerdrBlockedError",
    "HerdrCLIError",
    "HerdrClient",
    "HerdrError",
    "HerdrPaneStatus",
    "HerdrSeatStatus",
    "SSHError",
    "SSHNotConfiguredError",
    "SSHTarget",
    "SSHTransport",
    "cli_remote_from_base",
    "extract_prompt_type",
    "extract_state_change_seq",
    "herdr_client_from_spec",
    "is_localhost_base",
    "looks_like_key_material",
    "members_from_agent_list",
    "members_from_http_list",
    "members_from_workspace_list",
    "normalize_agent_status",
    "not_configured_message",
    "pane_id_of",
    "pane_statuses",
    "remote_command_from_ssh_argv",
    "require_ssh_target",
    "resolve_herdr_mode",
    "ssh_target_from_spec",
    "statuses_by_target",
    "stub_ssh_transport",
    "uses_local_http_health",
]
