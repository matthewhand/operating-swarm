from pathlib import Path

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import path, re_path
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import RedirectView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from swarm.views.agent_creator_views import (
    agent_creator_page,
    generate_agent_code,
    save_custom_agent,
    save_team_swarm,
    team_creator_page,
    validate_agent_code,
)
from swarm.views.api_views import (
    BlueprintsListView,
    BlueprintPersonasView,
    BlueprintSourceView,
    BlueprintToolsView,
    CliAgentModelsView,
    CliAgentsView,
    ConfigOptionsView,
    SkillDetailView,
    SkillsListView,
    CustomBlueprintDetailView,
    CustomBlueprintsView,
    MarketplaceGitHubBlueprintsView,
    MarketplaceGitHubMCPConfigsView,
    SupportContextView,
)
from swarm.views.definition_views import DefinitionDetailView, DefinitionSummarizeView
from swarm.views.api_views import ModelsListView as OpenAIModelsView
from swarm.views.agent_router_page import agent_router_page
from swarm.views.agent_router_views import (
    agent_context_view,
    agent_conversations_view,
    agent_delegations_view,
    create_designed_agent,
    delete_designed_agent,
    list_designed_agents,
    delegate_agent_view,
    get_agent_info,
    get_agent_status_view,
    generate_agent_quickstarts,
    get_routing_options,
    list_agents,
    list_cli_catalog,
    list_llm_profiles,
    launch_remote_framework,
    list_remote_catalog,
    route_message,
    send_to_agent,
)
from swarm.views.blueprint_library_views import (
    add_blueprint_to_library,
    blueprint_creator,
    blueprint_library,
    blueprint_requirements_status,
    blueprint_source_page,
    check_comfyui_status,
    generate_avatar,
    my_blueprints,
    remove_blueprint_from_library,
)
from swarm.views.chat_views import ChatCompletionsView, HealthCheckView
from swarm.views.runtime_views import BrowserControlView, RuntimeModeView
from swarm.views.herdr_api import (
    HerdrAgentDetailAPIView,
    HerdrAgentsAPIView,
    HerdrDiscoverAPIView,
)
from swarm.views.config_ownership_api import ConfigOwnershipView, ConfigSectionView
from swarm.views.mcp_plugins_api import (
    McpPluginDetailView,
    McpPluginDiscoverView,
    McpPluginsView,
)
from swarm.views.llm_profiles_api import LlmProfilesView
from swarm.views.rate_limits_api import RateLimitsView
from swarm.views.preferences_api import UserPreferencesView
from swarm.views.library_api import LibraryAPIView, LibraryDetailAPIView
from swarm.views.responses_views import (
    ResponsesCancelView,
    ResponsesDetailView,
    ResponsesView,
)
from swarm.views.session_explorer import (
    session_detail,
    session_explorer,
    session_list_api,
)
from swarm.views.chat_persist_views import (
    chat_attachment_upload,
    chat_compact,
    chat_context_start,
    chat_retention_action,
    chat_summary_toggle_context,
    chat_thread,
)
from swarm.views.system_views import LocalStoreView
from swarm.views.settings_views import (
    environment_variables,
    settings_api,
    settings_dashboard,
)
from swarm.views.remotes_api import (
    AgentTeamView,
    RemoteDetailView,
    RemoteHealthView,
    RemoteOperateView,
    RemotesListView,
)
from swarm.views.agent_settings_api import AgentSettingsAPIView, AgentTaskSessionAPIView
from swarm.views.mailbox_acl_api import (
    MailboxAclAgentAPIView,
    MailboxAclRoleAPIView,
    MailboxAclStoreAPIView,
)
from swarm.views.routines_api import (
    AgentRoutineDetailAPIView,
    AgentRoutinesAPIView,
    AgentRoutineTestRunAPIView,
    GithubRoutineMergeAPIView,
)
from swarm.views.cli_runs_api import CliRunStatusAPIView, CliRunTerminateAPIView
from swarm.views.cli_sessions_api import CliSessionListAPIView, CliSessionSelectAPIView
from swarm.views.cli_session_hop_api import CliSessionHopAPIView
from swarm.views.suggestions_api import AgentSuggestionsAPIView
from swarm.views.image_gen_api import AgentAvatarGenerateView, ImageGenSettingsView
from swarm.views.speech_api import SpeechSettingsView, SpeechSpeakView, SpeechTranscribeView
from swarm.views.team_rosters_api import (
    TeamAgentsAPIView,
    TeamRosterDetailAPIView,
    TeamRostersAPIView,
)
from swarm.views.roles_api import RolesAPIView
from swarm.views.teams_api import TeamDetailAPIView, TeamsAPIView
from swarm.views.web_views import (
    asgi_file_response,
    brand_root_file,
    custom_login,
    index,
    profiles_page,
    spa_chat,
    team_admin,
    team_launcher,
    team_rosters_json,
    teams_export,
)
from swarm.views.webui import WebUIView

# Prefer the AllowAny variant if it's present in URL mappings elsewhere; for tests,
# wire the open variant to avoid auth blocking. If needed, switch to ProtectedModelsView.
urlpatterns = [
    path("admin/", admin.site.urls),
    path("", index, name="index"),  # Root path for web UI
    # REQ-106 / #768 bee marks — root URLs browsers and the SPA head request.
    # Registered before the SPA catch-all so /favicon.ico is not index.html.
    path("favicon.ico", brand_root_file, {"filename": "favicon.ico"}, name="brand-favicon"),
    path("favicon-16.png", brand_root_file, {"filename": "favicon-16.png"}, name="brand-favicon-16"),
    path("favicon-32.png", brand_root_file, {"filename": "favicon-32.png"}, name="brand-favicon-32"),
    path("apple-touch-icon.png", brand_root_file, {"filename": "apple-touch-icon.png"}, name="brand-apple-touch-icon"),
    path("icon-192.png", brand_root_file, {"filename": "icon-192.png"}, name="brand-icon-192"),
    path("icon-512.png", brand_root_file, {"filename": "icon-512.png"}, name="brand-icon-512"),
    path("manifest.json", brand_root_file, {"filename": "manifest.json"}, name="brand-manifest"),
    path("favicon-minimal.svg", brand_root_file, {"filename": "favicon-minimal.svg"}, name="brand-favicon-minimal"),
    path("webui-geometric.svg", brand_root_file, {"filename": "webui-geometric.svg"}, name="brand-webui-geometric"),
    # First-class SPA Chat (composer + Connected). Agent Router is /agents.
    path("chat", spa_chat, name="spa_chat"),
    path("chat/", spa_chat, name="spa_chat_slash"),
    path("agents", agent_router_page, name="spa_agents"),
    path("agents/", agent_router_page, name="spa_agents_slash"),
    # Lightweight liveness probe (no auth) — used by the Fly health check.
    path("health", HealthCheckView.as_view(), name="health"),
    path("health/", HealthCheckView.as_view()),
    # REQ-45: runtime banner (where the *app* runs) + browser-control catalog.
    # AllowAny, no secrets / host paths. Slash twins like /health and /v1/models.
    path("v1/runtime", RuntimeModeView.as_view(), name="runtime-mode-no-slash"),
    path("v1/runtime/", RuntimeModeView.as_view(), name="runtime-mode"),
    path("v1/browser-control", BrowserControlView.as_view(), name="browser-control-no-slash"),
    path("v1/browser-control/", BrowserControlView.as_view(), name="browser-control"),
    # Session Explorer web UI (browse stateful /v1/responses sessions + delegation timelines)
    path("sessions/", session_explorer, name="session-explorer"),
    path("sessions/<str:response_id>/", session_detail, name="session-detail"),
    path("api/sessions/", session_list_api, name="session-list-api"),
    # Authentication. Two aliases for the same view:
    # - accounts/login/ matches Django's default LOGIN_URL ('/accounts/login/')
    #   and is the canonical 'login' name used by auth machinery.
    # - login/ matches this project's settings.LOGIN_URL ('/login/') and the
    #   'custom_login' name referenced by templates/account/login.html.
    path("accounts/login/", custom_login, name="login"),
    path("login/", custom_login, name="custom_login"),
    path("v1/models", OpenAIModelsView.as_view(), name="models-list-no-slash"),
    path("v1/models/", OpenAIModelsView.as_view(), name="models-list"),
    path("v1/blueprints", BlueprintsListView.as_view(), name="blueprints-list-no-slash"),
    path("v1/blueprints/", BlueprintsListView.as_view(), name="blueprints-list"),
    # Slash + no-slash twins (same pattern as /v1/responses and /v1/chat/completions).
    path("v1/blueprints/<str:blueprint_id>/source", BlueprintSourceView.as_view(), name="blueprint-source"),
    path("v1/blueprints/<str:blueprint_id>/source/", BlueprintSourceView.as_view(), name="blueprint-source-slash"),
    path("v1/blueprints/<str:blueprint_id>/personas", BlueprintPersonasView.as_view(), name="blueprint-personas"),
    path(
        "v1/blueprints/<str:blueprint_id>/personas/",
        BlueprintPersonasView.as_view(),
        name="blueprint-personas-slash",
    ),
    path("v1/blueprints/<str:blueprint_id>/tools", BlueprintToolsView.as_view(), name="blueprint-tools"),
    path("v1/blueprints/<str:blueprint_id>/tools/", BlueprintToolsView.as_view(), name="blueprint-tools-slash"),
    path(
        "v1/definitions/<str:kind>/<str:definition_id>/summarize",
        DefinitionSummarizeView.as_view(),
        name="definition-summarize",
    ),
    path(
        "v1/definitions/<str:kind>/<str:definition_id>/summarize/",
        DefinitionSummarizeView.as_view(),
        name="definition-summarize-slash",
    ),
    path(
        "v1/definitions/<str:kind>/<str:definition_id>",
        DefinitionDetailView.as_view(),
        name="definition-detail",
    ),
    path(
        "v1/definitions/<str:kind>/<str:definition_id>/",
        DefinitionDetailView.as_view(),
        name="definition-detail-slash",
    ),
    path("v1/cli-agents", CliAgentsView.as_view(), name="cli-agents-api-no-slash"),
    path("v1/cli-agents/", CliAgentsView.as_view(), name="cli-agents-api"),
    path("v1/cli-agents/runs", CliRunStatusAPIView.as_view(), name="cli-runs-status-no-slash"),
    path("v1/cli-agents/runs/", CliRunStatusAPIView.as_view(), name="cli-runs-status"),
    path(
        "v1/cli-agents/runs/terminate",
        CliRunTerminateAPIView.as_view(),
        name="cli-runs-terminate-no-slash",
    ),
    path(
        "v1/cli-agents/runs/terminate/",
        CliRunTerminateAPIView.as_view(),
        name="cli-runs-terminate",
    ),
    path("v1/cli-sessions", CliSessionListAPIView.as_view(), name="cli-sessions-list-no-slash"),
    path("v1/cli-sessions/", CliSessionListAPIView.as_view(), name="cli-sessions-list"),
    path("v1/cli-sessions/select", CliSessionSelectAPIView.as_view(), name="cli-sessions-select-no-slash"),
    path("v1/cli-sessions/select/", CliSessionSelectAPIView.as_view(), name="cli-sessions-select"),
    path("v1/cli-sessions/hop", CliSessionHopAPIView.as_view(), name="cli-sessions-hop-no-slash"),
    path("v1/cli-sessions/hop/", CliSessionHopAPIView.as_view(), name="cli-sessions-hop"),
    path("v1/llm-profiles", LlmProfilesView.as_view(), name="llm-profiles-api-no-slash"),
    path("v1/llm-profiles/", LlmProfilesView.as_view(), name="llm-profiles-api"),
    path("v1/rate-limits", RateLimitsView.as_view(), name="rate-limits-api-no-slash"),
    path("v1/rate-limits/", RateLimitsView.as_view(), name="rate-limits-api"),
    path("v1/config-ownership", ConfigOwnershipView.as_view(), name="config-ownership-api-no-slash"),
    path("v1/config-ownership/", ConfigOwnershipView.as_view(), name="config-ownership-api"),
    path(
        "v1/config/sections/<str:section>",
        ConfigSectionView.as_view(),
        name="config-section-api-no-slash",
    ),
    path(
        "v1/config/sections/<str:section>/",
        ConfigSectionView.as_view(),
        name="config-section-api",
    ),
    path("v1/preferences", UserPreferencesView.as_view(), name="user-preferences-api-no-slash"),
    path("v1/preferences/", UserPreferencesView.as_view(), name="user-preferences-api"),
    path("v1/mcp-plugins", McpPluginsView.as_view(), name="mcp-plugins-api-no-slash"),
    path("v1/mcp-plugins/", McpPluginsView.as_view(), name="mcp-plugins-api"),
    path(
        "v1/mcp-plugins/discover",
        McpPluginDiscoverView.as_view(),
        name="mcp-plugins-discover-no-slash",
    ),
    path(
        "v1/mcp-plugins/discover/",
        McpPluginDiscoverView.as_view(),
        name="mcp-plugins-discover",
    ),
    path(
        "v1/mcp-plugins/<str:name>",
        McpPluginDetailView.as_view(),
        name="mcp-plugins-detail-no-slash",
    ),
    path(
        "v1/mcp-plugins/<str:name>/",
        McpPluginDetailView.as_view(),
        name="mcp-plugins-detail",
    ),
    # Live list-models probes (REQ-44). More specific "models" routes first.
    path("v1/cli-agents/models", CliAgentModelsView.as_view(), name="cli-agent-models-all-no-slash"),
    path("v1/cli-agents/models/", CliAgentModelsView.as_view(), name="cli-agent-models-all"),
    path("v1/cli-agents/<str:cli>/models", CliAgentModelsView.as_view(), name="cli-agent-models-no-slash"),
    path("v1/cli-agents/<str:cli>/models/", CliAgentModelsView.as_view(), name="cli-agent-models"),
    path("v1/config-options", ConfigOptionsView.as_view(), name="config-options-api-no-slash"),
    path("v1/config-options/", ConfigOptionsView.as_view(), name="config-options-api"),
    path("v1/skills", SkillsListView.as_view(), name="skills-api-no-slash"),
    path("v1/skills/", SkillsListView.as_view(), name="skills-api"),
    path("v1/skills/<str:name>", SkillDetailView.as_view(), name="skill-detail-api-no-slash"),
    path("v1/skills/<str:name>/", SkillDetailView.as_view(), name="skill-detail-api"),
    path("v1/support/context", SupportContextView.as_view(), name="support-context-no-slash"),
    path("v1/support/context/", SupportContextView.as_view(), name="support-context"),
    path("v1/blueprints/custom/", CustomBlueprintsView.as_view(), name="custom-blueprints"),
    path("v1/blueprints/custom/<str:blueprint_id>/", CustomBlueprintDetailView.as_view(), name="custom-blueprint-detail"),
    # GitHub-topics marketplace discovery (returns empty list if disabled)
    path("marketplace/github/blueprints/", MarketplaceGitHubBlueprintsView.as_view(), name="marketplace-github-blueprints"),
    path("marketplace/github/mcp-configs/", MarketplaceGitHubMCPConfigsView.as_view(), name="marketplace-github-mcp-configs"),
    # Slash + no-slash twins (same pattern as /v1/responses and /v1/blueprints).
    # csrf_exempt on as_view() so ASGI/Daphne keeps the flag (DRF session CSRF
    # still applies to cookie clients; Bearer is exempt — Issue #136).
    path("v1/chat/completions", csrf_exempt(ChatCompletionsView.as_view()), name="chat_completions"),
    path("v1/chat/completions/", csrf_exempt(ChatCompletionsView.as_view()), name="chat_completions_slash"),
    # OpenAI Responses API (MVP) — normalizes `input`/`instructions` to messages
    # and reuses the same blueprint-resolution + run path as chat completions.
    # Slash + no-slash twins (same pattern as /v1/blueprints and /v1/teams).
    path("v1/responses", ResponsesView.as_view(), name="responses"),
    path("v1/responses/", ResponsesView.as_view(), name="responses-slash"),
    path("v1/responses/<str:response_id>/cancel", ResponsesCancelView.as_view(), name="responses-cancel"),
    path("v1/responses/<str:response_id>/cancel/", ResponsesCancelView.as_view(), name="responses-cancel-slash"),
    path("v1/responses/<str:response_id>", ResponsesDetailView.as_view(), name="responses-detail"),
    path("v1/responses/<str:response_id>/", ResponsesDetailView.as_view(), name="responses-detail-slash"),
    # OpenAPI schema + interactive docs (drf-spectacular).
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/schema/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
    # Static roster file for the AGENTS sidepane (REQ-23). Composition CRUD is
    # /v1/team-rosters/ below — not LLM-alias /v1/teams/.
    path("team_rosters.json", team_rosters_json, name="team-rosters-json"),
    # JSON Teams API (REST counterpart to the server-rendered /teams/ page)
    path("v1/teams", TeamsAPIView.as_view(), name="teams-api-no-slash"),
    path("v1/teams/", TeamsAPIView.as_view(), name="teams-api"),
    path("v1/teams/<str:team_id>/", TeamDetailAPIView.as_view(), name="teams-api-detail"),
    # Composition rosters (REQ-20 / REQ-28). Not teams.json LLM aliases.
    path("v1/team-rosters", TeamRostersAPIView.as_view(), name="team-rosters-api-no-slash"),
    path("v1/team-rosters/", TeamRostersAPIView.as_view(), name="team-rosters-api"),
    path("v1/team-rosters/<str:roster_id>/", TeamRosterDetailAPIView.as_view(), name="team-rosters-api-detail"),
    path("v1/team-agents", TeamAgentsAPIView.as_view(), name="team-agents-api-no-slash"),
    path("v1/team-agents/", TeamAgentsAPIView.as_view(), name="team-agents-api"),
    path("v1/roles", RolesAPIView.as_view(), name="roles-api-no-slash"),
    path("v1/roles/", RolesAPIView.as_view(), name="roles-api"),
    # Remote harnesses (Hermes / OpenMausBot / Rakazo) — config + health + operate
    path("v1/remotes", RemotesListView.as_view(), name="remotes-list-no-slash"),
    path("v1/remotes/", RemotesListView.as_view(), name="remotes-list"),
    path("v1/remotes/<str:remote_id>", RemoteDetailView.as_view(), name="remotes-detail-no-slash"),
    path("v1/remotes/<str:remote_id>/", RemoteDetailView.as_view(), name="remotes-detail"),
    path("v1/remotes/<str:remote_id>/health", RemoteHealthView.as_view(), name="remotes-health-no-slash"),
    path("v1/remotes/<str:remote_id>/health/", RemoteHealthView.as_view(), name="remotes-health"),
    path("v1/remotes/<str:remote_id>/operate", RemoteOperateView.as_view(), name="remotes-operate-no-slash"),
    path("v1/remotes/<str:remote_id>/operate/", RemoteOperateView.as_view(), name="remotes-operate"),
    # Handoff Team (API/CLI/remote members) — not /v1/teams/ Profiles aliases.
    path("v1/agent-team", AgentTeamView.as_view(), name="agent-team-no-slash"),
    path("v1/agent-team/", AgentTeamView.as_view(), name="agent-team"),
    # JSON Blueprint Library API (REST counterpart to /blueprint-library/)
    path("v1/library", LibraryAPIView.as_view(), name="library-api-no-slash"),
    path("v1/library/", LibraryAPIView.as_view(), name="library-api"),
    path("v1/library/<str:blueprint_name>/", LibraryDetailAPIView.as_view(), name="library-api-detail"),
    # Agent Router API (SPA /agents chat uses these)
    path("v1/agents/", list_agents, name="list_agents"),
    path("v1/agents/routing-options/", get_routing_options, name="get_routing_options"),
    path("v1/agents/route/", route_message, name="route_message"),
    path("v1/agents/conversations/", agent_conversations_view, name="agent_conversations"),
    path("v1/agents/delegations/", agent_delegations_view, name="agent_delegations"),
    path("v1/agents/cli-catalog/", list_cli_catalog, name="list_cli_catalog"),
    path("v1/agents/llm-profiles/", list_llm_profiles, name="list_llm_profiles"),
    path("v1/agents/remote-catalog/", list_remote_catalog, name="list_remote_catalog"),
    path("v1/agents/remote-launch/", launch_remote_framework, name="launch_remote_framework"),
    path("v1/agents/quickstarts/", generate_agent_quickstarts, name="generate_agent_quickstarts"),
    path("v1/agents/design/", create_designed_agent, name="create_designed_agent"),
    path("v1/agents/designs/", list_designed_agents, name="list_designed_agents"),
    path("v1/agents/design/<str:agent_id>/", delete_designed_agent, name="delete_designed_agent"),
    path("v1/agents/<str:agent_id>/", get_agent_info, name="get_agent_info"),
    path("v1/agents/<str:agent_id>/send/", send_to_agent, name="send_to_agent"),
    path("v1/agents/<str:agent_id>/status/", get_agent_status_view, name="get_agent_status"),
    path("v1/agents/<str:agent_id>/delegate/", delegate_agent_view, name="delegate_agent"),
    path("v1/agents/<str:agent_id>/context/", agent_context_view, name="agent_context"),
    # Herdr members (REQ-21): name + optional --remote. Empty remote = localhost.
    path("v1/herdr-agents", HerdrAgentsAPIView.as_view(), name="herdr-agents-api-no-slash"),
    path("v1/herdr-agents/", HerdrAgentsAPIView.as_view(), name="herdr-agents-api"),
    path("v1/herdr-agents/discover", HerdrDiscoverAPIView.as_view(), name="herdr-agents-discover-no-slash"),
    path("v1/herdr-agents/discover/", HerdrDiscoverAPIView.as_view(), name="herdr-agents-discover"),
    path("v1/herdr-agents/<str:agent_id>", HerdrAgentDetailAPIView.as_view(), name="herdr-agents-api-detail-no-slash"),
    path("v1/herdr-agents/<str:agent_id>/", HerdrAgentDetailAPIView.as_view(), name="herdr-agents-api-detail"),
    # REQ-162: peer-mailbox ACL (whitelist XOR blacklist; Support allow-all).
    path("v1/mailbox-acl", MailboxAclStoreAPIView.as_view(), name="mailbox-acl-store-no-slash"),
    path("v1/mailbox-acl/", MailboxAclStoreAPIView.as_view(), name="mailbox-acl-store"),
    path(
        "v1/mailbox-acl/agents/<str:agent_id>",
        MailboxAclAgentAPIView.as_view(),
        name="mailbox-acl-agent-no-slash",
    ),
    path(
        "v1/mailbox-acl/agents/<str:agent_id>/",
        MailboxAclAgentAPIView.as_view(),
        name="mailbox-acl-agent",
    ),
    path(
        "v1/mailbox-acl/roles/<str:role>",
        MailboxAclRoleAPIView.as_view(),
        name="mailbox-acl-role-no-slash",
    ),
    path(
        "v1/mailbox-acl/roles/<str:role>/",
        MailboxAclRoleAPIView.as_view(),
        name="mailbox-acl-role",
    ),
    # REQ-65: agent-scoped settings (new chat per task). Not global Settings.
    path("v1/agents/<str:agent_id>/settings", AgentSettingsAPIView.as_view(), name="agent-settings-api-no-slash"),
    path("v1/agents/<str:agent_id>/settings/", AgentSettingsAPIView.as_view(), name="agent-settings-api"),
    path("v1/agents/<str:agent_id>/suggestions", AgentSuggestionsAPIView.as_view(), name="agent-suggestions-api-no-slash"),
    path("v1/agents/<str:agent_id>/suggestions/", AgentSuggestionsAPIView.as_view(), name="agent-suggestions-api"),
    path("v1/agents/<str:agent_id>/sessions", AgentTaskSessionAPIView.as_view(), name="agent-task-session-api-no-slash"),
    path("v1/agents/<str:agent_id>/sessions/", AgentTaskSessionAPIView.as_view(), name="agent-task-session-api"),
    # REQ-80: agent-scoped Routines (PR-merge trigger, Test run, history).
    path("v1/agents/<str:agent_id>/routines", AgentRoutinesAPIView.as_view(), name="agent-routines-api-no-slash"),
    path("v1/agents/<str:agent_id>/routines/", AgentRoutinesAPIView.as_view(), name="agent-routines-api"),
    path(
        "v1/agents/<str:agent_id>/routines/<str:routine_id>",
        AgentRoutineDetailAPIView.as_view(),
        name="agent-routine-detail-api-no-slash",
    ),
    path(
        "v1/agents/<str:agent_id>/routines/<str:routine_id>/",
        AgentRoutineDetailAPIView.as_view(),
        name="agent-routine-detail-api",
    ),
    path(
        "v1/agents/<str:agent_id>/routines/<str:routine_id>/test-run",
        AgentRoutineTestRunAPIView.as_view(),
        name="agent-routine-test-run-api-no-slash",
    ),
    path(
        "v1/agents/<str:agent_id>/routines/<str:routine_id>/test-run/",
        AgentRoutineTestRunAPIView.as_view(),
        name="agent-routine-test-run-api",
    ),
    path("v1/routines/github-merge", GithubRoutineMergeAPIView.as_view(), name="routines-github-merge-api-no-slash"),
    path("v1/routines/github-merge/", GithubRoutineMergeAPIView.as_view(), name="routines-github-merge-api"),
    path(
        "v1/agents/<str:agent_id>/avatar/generate",
        AgentAvatarGenerateView.as_view(),
        name="agent-avatar-generate-no-slash",
    ),
    path(
        "v1/agents/<str:agent_id>/avatar/generate/",
        AgentAvatarGenerateView.as_view(),
        name="agent-avatar-generate",
    ),
    path("v1/image-gen", ImageGenSettingsView.as_view(), name="image-gen-settings-no-slash"),
    path("v1/image-gen/", ImageGenSettingsView.as_view(), name="image-gen-settings"),
    path("v1/speech", SpeechSettingsView.as_view(), name="speech-settings-no-slash"),
    path("v1/speech/", SpeechSettingsView.as_view(), name="speech-settings"),
    path("v1/speech/transcribe", SpeechTranscribeView.as_view(), name="speech-transcribe-no-slash"),
    path("v1/speech/transcribe/", SpeechTranscribeView.as_view(), name="speech-transcribe"),
    path("v1/speech/speak", SpeechSpeakView.as_view(), name="speech-speak-no-slash"),
    path("v1/speech/speak/", SpeechSpeakView.as_view(), name="speech-speak"),
    # Settings System section — local store facts (REQ-56). Read-only.
    path("v1/system", LocalStoreView.as_view(), name="system-local-store-no-slash"),
    path("v1/system/", LocalStoreView.as_view(), name="system-local-store"),
    path("teams/launch", team_launcher, name="teams_launch_no_slash"),
    path("teams/launch/", team_launcher, name="teams_launch"),
    path("teams/", team_admin, name="teams_admin"),
    path("teams/export", teams_export, name="teams_export"),
    path("profiles/", profiles_page, name="profiles_page"),
    # Agent/Team Creator endpoints
    path("agent-creator/", agent_creator_page, name="agent_creator"),
    path("agent-creator/generate/", generate_agent_code, name="generate_agent_code"),
    path("agent-creator/validate/", validate_agent_code, name="validate_agent_code"),
    path("agent-creator/save/", save_custom_agent, name="save_custom_agent"),
    path("team-creator/", team_creator_page, name="team_creator"),
    path("team-creator/save/", save_team_swarm, name="save_team_swarm"),
    # Agent Creator Pro was unwired clickware (generate/validate/save 404).
    # Keep the path as a soft redirect to the canonical creator.
    path(
        "agent-creator-pro/",
        RedirectView.as_view(url="/agent-creator/", permanent=False, query_string=True),
        name="agent_creator_pro",
    ),
    # Settings Management endpoints
    path("settings/", settings_dashboard, name="settings_dashboard"),
    path("settings/api/", settings_api, name="settings_api"),
    path("settings/environment/", environment_variables, name="environment_variables"),
    path("settings/chats/action/", chat_retention_action, name="chat_retention_action"),
    # Per-agent chat restore (session cookie). Not shown in Chat chrome.
    path("chat/thread/", chat_thread, name="chat_thread"),
    # REQ-38: composer file upload (sqlite metadata + local bytes).
    path("v1/chat/attachments", chat_attachment_upload, name="chat-attachments-no-slash"),
    path("v1/chat/attachments/", chat_attachment_upload, name="chat-attachments"),
    # REQ-37: compact the backlog into a nested sqlite summary (raw JSON stays).
    path("chat/compact/", chat_compact, name="chat_compact"),
    path("chat/context-start/", chat_context_start, name="chat_context_start"),
    # #214: tick/untick whether a summary (and its span) feeds model context.
    path(
        "chat/summary/toggle-context/",
        chat_summary_toggle_context,
        name="chat_summary_toggle_context",
    ),
    # Blueprint Library endpoints
    path("blueprint-library/", blueprint_library, name="blueprint_library"),
    path("blueprint-library/creator/", blueprint_creator, name="blueprint_creator"),
    path(
        "blueprint-library/<str:blueprint_name>/source/",
        blueprint_source_page,
        name="blueprint_source",
    ),
    path("blueprint-library/my-blueprints/", my_blueprints, name="my_blueprints"),
    path("blueprint-library/requirements/", blueprint_requirements_status, name="blueprint_requirements_status"),
    path("blueprint-library/add/<str:blueprint_name>/", add_blueprint_to_library, name="add_blueprint_to_library"),
    path("blueprint-library/remove/<str:blueprint_name>/", remove_blueprint_from_library, name="remove_blueprint_from_library"),
    # Avatar generation endpoints
    path("blueprint-library/generate-avatar/<str:blueprint_name>/", generate_avatar, name="generate_avatar"),
    path("blueprint-library/comfyui-status/", check_comfyui_status, name="check_comfyui_status"),

    # Web UI endpoint
    path("webui/", WebUIView.as_view(), name="webui"),
]

# Serve avatar images in development
if settings.DEBUG:
    urlpatterns += static(settings.AVATAR_URL_PREFIX, document_root=settings.AVATAR_STORAGE_PATH)

# Optional MCP server (django-mcp-server) when enabled
import os

if os.getenv('ENABLE_MCP_SERVER', '').lower() in ('true', '1', 'yes'):
    try:
        from django.urls import include
        urlpatterns += [
            path('mcp/', include('mcp_server.urls')),
        ]
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning(
            "ENABLE_MCP_SERVER is set but the '/mcp/' mount was skipped: could not "
            "import 'mcp_server.urls' (%s). Install the MCP server package with "
            "`pip install django-mcp-server` (provides the 'mcp_server' module). "
            "See docs/mcp_server_mode.md.",
            exc,
        )

# Canonical product UI is Django (trailing-slash). Bare SPA-style paths that used
# to dual-mount the React shell now redirect so users never hit two different UIs
# for the same concept (e.g. /teams vs /teams/).
urlpatterns += [
    path(
        "teams",
        RedirectView.as_view(url="/teams/launch/", permanent=False, query_string=True),
        name="spa_teams_to_django",
    ),
    path(
        "blueprints",
        RedirectView.as_view(url="/blueprint-library/", permanent=False, query_string=True),
        name="spa_blueprints_to_django",
    ),
    path(
        "settings",
        RedirectView.as_view(url="/settings/", permanent=False, query_string=True),
        name="spa_settings_to_django",
    ),
    # Bare /agent-creator (no slash) used to hit an empty SPA shell; canonical
    # creator is Django at /agent-creator/.
    path(
        "agent-creator",
        RedirectView.as_view(url="/agent-creator/", permanent=False, query_string=True),
        name="spa_agent_creator_to_django",
    ),
]

# SPA Fallback for React Router - must be last (home `/` and experimental routes).
def _get_frontend_path():
    """Get the path to the built frontend assets."""
    frontend_path = Path("webui/frontend/dist")
    if not frontend_path.exists():
        frontend_path = Path("webui/frontend/build")
    return frontend_path if frontend_path.exists() else None

frontend_path = _get_frontend_path()
if frontend_path and frontend_path.exists():
    import mimetypes

    def spa_asset(request, path):
        root = (frontend_path / "assets").resolve()
        target = (root / path).resolve()
        if not str(target).startswith(str(root)) or not target.is_file():
            return HttpResponse("Not Found", status=404)
        ctype, _ = mimetypes.guess_type(str(target))
        return asgi_file_response(target, ctype or "application/octet-stream")

    # SPA fallback - serve index.html for all non-API, non-admin, non-static routes
    # (the catch-all regex below has no capture group, so path must default)
    def spa_fallback(request, path=""):
        index_file = frontend_path / "index.html"
        if index_file.exists():
            return asgi_file_response(index_file, "text/html")
        return HttpResponse("Not Found", status=404)

    urlpatterns += [
        re_path(r'^assets/(?P<path>.*)$', spa_asset),
        re_path(r'^(?!api/|admin/|static/|assets/|mcp/|marketplace/|v1/|teams/|blueprint-library/|agent-creator/|settings/|accounts/|login/|profiles/|sessions/|webui/|chat/|agents/|django_chat).*$', spa_fallback),
    ]
