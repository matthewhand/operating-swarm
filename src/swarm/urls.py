import logging
from pathlib import Path

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, re_path
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import RedirectView
logger = logging.getLogger(__name__)

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from swarm.views.activity_log_api import ActivityLogAPIView
from swarm.views.agent_creator_views import (
    agent_creator_page,
    generate_agent_code,
    save_custom_agent,
    save_team_swarm,
    team_creator_page,
    validate_agent_code,
)
from swarm.views.agent_mcp_api import (
    AgentMcpAPIView,
    AgentMcpToolDetailAPIView,
    AgentMcpToolExecuteAPIView,
    AgentMcpToolsAPIView,
)
from swarm.views.agent_plugin_pack_api import (
    AgentPluginPackAPIView,
    AgentPluginPackImportAPIView,
    AgentPluginsAPIView,
)
from swarm.views.agent_router_page import agent_router_page
from swarm.views.agent_router_views import (
    agent_context_view,
    agent_conversations_view,
    agent_delegations_view,
    assist_draft_view,
    create_designed_agent,
    delegate_agent_view,
    delete_designed_agent,
    generate_agent_quickstarts,
    get_agent_info,
    get_agent_status_view,
    get_routing_options,
    launch_remote_framework,
    list_agents,
    list_cli_catalog,
    list_designed_agents,
    list_llm_profiles,
    list_remote_catalog,
    route_message,
    send_to_agent,
)
from swarm.views.agent_memory_api import (
    AgentMemoriesAPIView,
    AgentMemoryDetailAPIView,
    AgentMemoryImportAPIView,
    AgentMemoryPackAPIView,
)
from swarm.views.agent_sandbox_display_api import AgentSandboxDisplayView
from swarm.views.agent_settings_api import (
    AgentProfileAPIView,
    AgentSettingsAPIView,
    AgentTaskSessionAPIView,
)
from swarm.views.agent_skills_api import (
    AgentPackAPIView,
    AgentPackImportAPIView,
    AgentPackValidateAPIView,
    AgentSkillDetailAPIView,
    AgentSkillsAPIView,
)
from swarm.views.agent_template_api import (
    AgentTemplateAPIView,
    AgentTemplateCreateAPIView,
    AgentTemplateFromGrokAPIView,
    AgentTemplateGrokAPIView,
    AgentTemplateGrokMapperAPIView,
    AgentTemplateImportAPIView,
    AgentTemplateValidateAPIView,
)
from swarm.views.api_views import (
    BlueprintPersonasView,
    BlueprintsListView,
    BlueprintSourceView,
    BlueprintToolsView,
    BlueprintUploadView,
    ChatRetentionStatsView,
    CliAgentCandidatesView,
    CliAgentDriversView,
    CliAgentModelsView,
    CliAgentsView,
    CliAgentTestView,
    ConfigOptionsView,
    CustomBlueprintDetailView,
    CustomBlueprintsView,
    MarketplaceGitHubBlueprintsView,
    MarketplaceGitHubMCPConfigsView,
    SkillDetailView,
    SkillsListView,
    SupportContextView,
)
from swarm.views.api_views import ModelsListView as OpenAIModelsView
from swarm.views.assist_api import ChatAutocompleteAPIView, EnhancePromptAPIView
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
    sdk_docs,
)
from swarm.views.chat_conversations_api import (
    ConversationDirectoryView,
    ConversationHandoffView,
    ConversationMoveTopicView,
)
from swarm.views.chat_persist_views import (
    chat_attachment_content,
    chat_attachment_upload,
    chat_compact,
    chat_context_start,
    chat_context_usage,
    chat_raw_context,
    chat_retention_action,
    chat_summary_toggle_context,
    chat_thread,
)
from swarm.views.chat_views import ChatCompletionsView, HealthCheckView
from swarm.views.cli_runs_api import CliRunStatusAPIView, CliRunTerminateAPIView
from swarm.views.cli_session_hop_api import CliSessionHopAPIView
from swarm.views.seat_capabilities_api import SeatCapabilitiesAPIView
from swarm.views.cli_sessions_api import CliSessionListAPIView, CliSessionSelectAPIView
from swarm.views.config_ownership_api import ConfigOwnershipView, ConfigSectionView
from swarm.views.definition_views import DefinitionDetailView, DefinitionSummarizeView
from swarm.views.diagnostics_views import DiagnosticsView
from swarm.views.fs_browse_api import FsDirectoriesView
from swarm.views.herdr_api import (
    HerdrAgentDetailAPIView,
    HerdrAgentsAPIView,
    HerdrDiscoverAPIView,
    HerdrStatusAPIView,
)
from swarm.views.image_gen_api import AgentAvatarGenerateView, ImageGenSettingsView
from swarm.views.library_api import LibraryAPIView, LibraryDetailAPIView
from swarm.views.org_library_api import (
    OrgLibraryAPIView,
    OrgLibraryDetailAPIView,
    OrgLibraryShareAPIView,
)
from swarm.views.llm_profiles_api import LlmProfilesTestView, LlmProfilesView
from swarm.views.mailbox_acl_api import (
    MailboxAclAgentAPIView,
    MailboxAclRoleAPIView,
    MailboxAclStoreAPIView,
)
from swarm.views.marketplace_api import (
    MarketplaceCatalogView,
    MarketplaceInstallView,
    MarketplacePreviewView,
    MarketplaceScanView,
)
from swarm.views.mcp_plugins_api import (
    McpPluginDetailView,
    McpPluginDiscoverView,
    McpPluginsView,
)
from swarm.views.companies_api import CompanyCollectionView, CompanyDetailView
from swarm.views.company_route_api import CompanyRouteView
from swarm.views.preferences_api import UserPreferencesView
from swarm.views.rate_limits_api import RateLimitsView
from swarm.views.seat_health_api import SeatDoctorView, SeatHealthBatchView, SeatHealthView
from swarm.views.remotes_api import (
    AgentTeamView,
    RemoteDetailView,
    RemoteHealthView,
    RemotePairView,
    RemoteOperateView,
    RemoteProbeCandidateView,
    RemoteRoutinesView,
    RemoteTrueForgeCatalogView,
    RemotesListView,
)
from swarm.views.responses_views import (
    ResponsesCancelView,
    ResponsesDetailView,
    ResponsesView,
)
from swarm.views.roles_api import RolesAPIView
from swarm.views.routines_api import (
    AgentRoutineDetailAPIView,
    AgentRoutineEnableAPIView,
    AgentRoutineFillAPIView,
    AgentRoutineRunNowAPIView,
    AgentRoutinesAPIView,
    AgentRoutinesImportAPIView,
    AgentRoutinesPackAPIView,
    AgentRoutineTestRunAPIView,
    AllRoutinesAPIView,
    GithubRoutineEventsAPIView,
    GithubRoutineMergeAPIView,
    MailboxRoutineMessageAPIView,
    RoutinePackValidateAPIView,
    RoutinePresetsAPIView,
    RoutineToolCatalogAPIView,
)
from swarm.views.runtime_views import BrowserControlView, RuntimeModeView
from swarm.views.sandbox_settings_api import (
    SandboxSettingsTestView,
    SandboxSettingsView,
)
from swarm.views.session_explorer import (
    session_detail,
    session_explorer,
    session_list_api,
)
from swarm.views.settings_views import (
    environment_variables,
    settings_api,
    settings_dashboard,
)
from swarm.views.speech_api import (
    SpeechSettingsView,
    SpeechSpeakView,
    SpeechTranscribeView,
)
from swarm.views.operator_plane_api import (
    OperatorPlaneAPIView,
    OperatorPlaneBudgetChargeAPIView,
    OperatorPlaneBudgetResetAPIView,
    OperatorPlaneBudgetsAPIView,
    OperatorPlaneExportAPIView,
    OperatorPlaneGatesAPIView,
    OperatorPlaneImportAPIView,
    OperatorPlaneTaskCheckoutAPIView,
    OperatorPlaneTaskReleaseAPIView,
)
from swarm.views.suggestions_api import AgentSuggestionsAPIView
from swarm.views.system_views import BuildInfoView, LocalStoreView
from swarm.views.team_rosters_api import (
    TeamAgentsAPIView,
    TeamRosterDetailAPIView,
    TeamRosterTopologyAPIView,
    TeamRostersAPIView,
)
from swarm.views.teams_api import TeamDetailAPIView, TeamsAPIView
from swarm.views.telemetry_api import (
    RequestTelemetryView,
    ThrottleIncidentsView,
)
from swarm.views.test_schedules_api import (
    TestScheduleDetailAPIView,
    TestScheduleRunNowAPIView,
    TestSchedulesAPIView,
    TestScheduleStatusAPIView,
)
from swarm.views.web_views import (
    brand_root_file,
    custom_login,
    custom_logout,
    index,
    profiles_page,
    spa_asset_view,
    spa_chat,
    spa_fallback_view,
    team_admin,
    team_launcher,
    team_rosters_json,
    teams_export,
)
from swarm.views.webui import WebUIView

# Prefer the AllowAny variant if it's present in URL mappings elsewhere; for tests,
# wire the open variant to avoid auth blocking. If needed, switch to ProtectedModelsView.
# Social sign-in (/oauth/<backend>/login|callback|complete). Registered ahead
# of the SPA catch-all so an /oauth/... path can never be swallowed by it, and
# only when the `oauth` extra is installed -- a barebones deploy has no
# social_django and must still boot. Callbacks need SECURE_PROXY_SSL_HEADER
# (settings) so redirect_uri is https behind Fly's TLS-terminating proxy.
SOCIAL_URLPATTERNS: list = []
_SOCIAL_URLS_MOUNTED = False
if settings.SOCIAL_AUTH_AVAILABLE:
    try:
        from django.urls import include, path as _path

        # include() is required, not optional: social_django declares
        # app_name="social", and splicing its raw urlpatterns into the root
        # list drops that namespace, so reverse('social:begin') fails.
        # Mounted at /oauth/ to match the provider callback URLs registered in
        # the GitHub / Google developer consoles.
        SOCIAL_URLPATTERNS = [_path("oauth/", include("social_django.urls", namespace="social"))]
        _SOCIAL_URLS_MOUNTED = True
    except Exception:  # pragma: no cover - a partial install must not 500 the site
        # The site must stay usable, but it must also not advertise sign-in:
        # with the namespace unmounted, {% url 'social:begin' %} raises
        # NoReverseMatch and /login/ returns 500 -- i.e. unloginable, not
        # merely degraded. social_urlpatterns_mounted() lets the login view
        # fall back to password-only instead.
        logger.exception("social_django is installed but its URLs could not be loaded")


def social_urlpatterns_mounted() -> bool:
    """Whether the /oauth/ namespace actually resolved.

    Read by web_views._oauth_providers() so a partial social-auth install
    degrades to password-only rather than 500-ing the login page.
    """
    return _SOCIAL_URLS_MOUNTED

urlpatterns = [
    *SOCIAL_URLPATTERNS,
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
    # Body is status plus the resolved config root (#1434): a directory path,
    # not a secret. Do not describe this route as free of host paths.
    path("health", HealthCheckView.as_view(), name="health"),
    path("health/", HealthCheckView.as_view()),
    # REQ-45: runtime banner (where the *app* runs) + browser-control catalog.
    # AllowAny, no secrets / host paths. Slash twins like /v1/models.
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
    # Session sign-out. There was no logout route at all, so an OAuth session
    # could never be ended from the UI. Must be POST-capable: GET logout is
    # CSRF-exposable (a third-party <img> could sign the user out).
    path("accounts/logout/", custom_logout, name="logout"),
    path("v1/models", OpenAIModelsView.as_view(), name="models-list-no-slash"),
    path("v1/models/", OpenAIModelsView.as_view(), name="models-list"),
    path("v1/blueprints", BlueprintsListView.as_view(), name="blueprints-list-no-slash"),
    path("v1/blueprints/", BlueprintsListView.as_view(), name="blueprints-list"),
    # Slash + no-slash twins (same pattern as /v1/responses and /v1/chat/completions).
    path("v1/blueprints/<str:blueprint_id>/source", BlueprintSourceView.as_view(), name="blueprint-source"),
    path("v1/blueprints/<str:blueprint_id>/source/", BlueprintSourceView.as_view(), name="blueprint-source-slash"),
    # #537: format is a proposal endpoint on the same view (POST method).
    path("v1/blueprints/<str:blueprint_id>/source/format", BlueprintSourceView.as_view(), name="blueprint-source-format"),
    path("v1/blueprints/<str:blueprint_id>/source/format/", BlueprintSourceView.as_view(), name="blueprint-source-format-slash"),
    # REQ-919: upload creates a user-dir recipe from a .py or zip/tar archive.
    path("v1/blueprints/upload", BlueprintUploadView.as_view(), name="blueprint-upload"),
    path("v1/blueprints/upload/", BlueprintUploadView.as_view(), name="blueprint-upload-slash"),
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
    path("v1/cli-agents/candidates", CliAgentCandidatesView.as_view(), name="cli-candidates-no-slash"),
    path("v1/cli-agents/candidates/", CliAgentCandidatesView.as_view(), name="cli-candidates"),
    path("v1/cli-agents/test", CliAgentTestView.as_view(), name="cli-test-no-slash"),
    path("v1/cli-agents/test/", CliAgentTestView.as_view(), name="cli-test"),
    path("v1/cli-agents/drivers", CliAgentDriversView.as_view(), name="cli-drivers-no-slash"),
    path("v1/cli-agents/drivers/", CliAgentDriversView.as_view(), name="cli-drivers"),
    path("v1/chat/retention/stats", ChatRetentionStatsView.as_view(), name="chat-retention-stats-no-slash"),
    path("v1/chat/retention/stats/", ChatRetentionStatsView.as_view(), name="chat-retention-stats"),
    path("v1/chat/retention/action", chat_retention_action, name="chat-retention-action-v1-no-slash"),
    path("v1/chat/retention/action/", chat_retention_action, name="chat-retention-action-v1"),
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
    path("v1/capabilities/seats", SeatCapabilitiesAPIView.as_view(), name="capabilities-seats-no-slash"),
    path("v1/capabilities/seats/", SeatCapabilitiesAPIView.as_view(), name="capabilities-seats"),
    path("v1/llm-profiles/test", LlmProfilesTestView.as_view(), name="llm-profiles-test-no-slash"),
    path("v1/llm-profiles/test/", LlmProfilesTestView.as_view(), name="llm-profiles-test"),
    path("v1/llm-profiles", LlmProfilesView.as_view(), name="llm-profiles-api-no-slash"),
    path("v1/llm-profiles/", LlmProfilesView.as_view(), name="llm-profiles-api"),
    path("v1/settings/sandbox", SandboxSettingsView.as_view(), name="sandbox-settings-no-slash"),
    path("v1/settings/sandbox/", SandboxSettingsView.as_view(), name="sandbox-settings"),
    path("v1/settings/sandbox/test", SandboxSettingsTestView.as_view(), name="sandbox-settings-test-no-slash"),
    path("v1/settings/sandbox/test/", SandboxSettingsTestView.as_view(), name="sandbox-settings-test"),
    path("v1/marketplace", MarketplaceScanView.as_view(), name="marketplace-api-no-slash"),
    path("v1/marketplace/", MarketplaceScanView.as_view(), name="marketplace-api"),
    path(
        "v1/marketplace/catalog",
        MarketplaceCatalogView.as_view(),
        name="marketplace-catalog-no-slash",
    ),
    path(
        "v1/marketplace/catalog/",
        MarketplaceCatalogView.as_view(),
        name="marketplace-catalog",
    ),
    path(
        "v1/marketplace/preview",
        MarketplacePreviewView.as_view(),
        name="marketplace-preview-no-slash",
    ),
    path(
        "v1/marketplace/preview/",
        MarketplacePreviewView.as_view(),
        name="marketplace-preview",
    ),
    path(
        "v1/marketplace/install",
        MarketplaceInstallView.as_view(),
        name="marketplace-install-no-slash",
    ),
    path(
        "v1/marketplace/install/",
        MarketplaceInstallView.as_view(),
        name="marketplace-install",
    ),
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
    # #1315: Company model policy. #1317 requires Company on new-bot create.
    path("v1/companies", CompanyCollectionView.as_view(), name="companies-api-no-slash"),
    path("v1/companies/", CompanyCollectionView.as_view(), name="companies-api"),
    path("v1/company-route", CompanyRouteView.as_view(), name="company-route-no-slash"),
    path("v1/company-route/", CompanyRouteView.as_view(), name="company-route"),
    path(
        "v1/companies/<str:company_id>",
        CompanyDetailView.as_view(),
        name="companies-api-detail-no-slash",
    ),
    path(
        "v1/companies/<str:company_id>/",
        CompanyDetailView.as_view(),
        name="companies-api-detail",
    ),
    # #1314: operator activity log (append-only ActivityEvent; detail redacted)
    path("v1/activity", ActivityLogAPIView.as_view(), name="activity-log-api-no-slash"),
    path("v1/activity/", ActivityLogAPIView.as_view(), name="activity-log-api"),
    # #800: 429 burst diagnostics
    path("v1/telemetry/requests/", RequestTelemetryView.as_view(), name="telemetry-requests"),
    path("v1/telemetry/throttles/", ThrottleIncidentsView.as_view(), name="telemetry-throttles"),
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
    # #1256: confined host directory browser for the agent Folder picker.
    path("v1/fs/directories", FsDirectoriesView.as_view(), name="fs-directories-no-slash"),
    path("v1/fs/directories/", FsDirectoriesView.as_view(), name="fs-directories"),
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
    path("v1/team-rosters/<str:roster_id>/topology/", TeamRosterTopologyAPIView.as_view(), name="team-rosters-api-topology"),
    path("v1/team-rosters/<str:roster_id>/", TeamRosterDetailAPIView.as_view(), name="team-rosters-api-detail"),
    path("v1/team-agents", TeamAgentsAPIView.as_view(), name="team-agents-api-no-slash"),
    path("v1/team-agents/", TeamAgentsAPIView.as_view(), name="team-agents-api"),
    # Operator control plane (#1360). Not a seat kind and not teams.json.
    path("v1/operator-plane", OperatorPlaneAPIView.as_view(), name="operator-plane-no-slash"),
    path("v1/operator-plane/", OperatorPlaneAPIView.as_view(), name="operator-plane"),
    path(
        "v1/operator-plane/budgets",
        OperatorPlaneBudgetsAPIView.as_view(),
        name="operator-plane-budgets-no-slash",
    ),
    path(
        "v1/operator-plane/budgets/",
        OperatorPlaneBudgetsAPIView.as_view(),
        name="operator-plane-budgets",
    ),
    path(
        "v1/operator-plane/budgets/charge",
        OperatorPlaneBudgetChargeAPIView.as_view(),
        name="operator-plane-budgets-charge-no-slash",
    ),
    path(
        "v1/operator-plane/budgets/charge/",
        OperatorPlaneBudgetChargeAPIView.as_view(),
        name="operator-plane-budgets-charge",
    ),
    path(
        "v1/operator-plane/budgets/reset",
        OperatorPlaneBudgetResetAPIView.as_view(),
        name="operator-plane-budgets-reset-no-slash",
    ),
    path(
        "v1/operator-plane/budgets/reset/",
        OperatorPlaneBudgetResetAPIView.as_view(),
        name="operator-plane-budgets-reset",
    ),
    path(
        "v1/operator-plane/tasks/checkout",
        OperatorPlaneTaskCheckoutAPIView.as_view(),
        name="operator-plane-task-checkout-no-slash",
    ),
    path(
        "v1/operator-plane/tasks/checkout/",
        OperatorPlaneTaskCheckoutAPIView.as_view(),
        name="operator-plane-task-checkout",
    ),
    path(
        "v1/operator-plane/tasks/release",
        OperatorPlaneTaskReleaseAPIView.as_view(),
        name="operator-plane-task-release-no-slash",
    ),
    path(
        "v1/operator-plane/tasks/release/",
        OperatorPlaneTaskReleaseAPIView.as_view(),
        name="operator-plane-task-release",
    ),
    path(
        "v1/operator-plane/gates",
        OperatorPlaneGatesAPIView.as_view(),
        name="operator-plane-gates-no-slash",
    ),
    path(
        "v1/operator-plane/gates/",
        OperatorPlaneGatesAPIView.as_view(),
        name="operator-plane-gates",
    ),
    path(
        "v1/operator-plane/org/export",
        OperatorPlaneExportAPIView.as_view(),
        name="operator-plane-org-export-no-slash",
    ),
    path(
        "v1/operator-plane/org/export/",
        OperatorPlaneExportAPIView.as_view(),
        name="operator-plane-org-export",
    ),
    path(
        "v1/operator-plane/org/import",
        OperatorPlaneImportAPIView.as_view(),
        name="operator-plane-org-import-no-slash",
    ),
    path(
        "v1/operator-plane/org/import/",
        OperatorPlaneImportAPIView.as_view(),
        name="operator-plane-org-import",
    ),
    path("v1/roles", RolesAPIView.as_view(), name="roles-api-no-slash"),
    path("v1/roles/", RolesAPIView.as_view(), name="roles-api"),
    path("v1/roles/<str:role_id>", RolesAPIView.as_view(), name="roles-api-detail-no-slash"),
    path("v1/roles/<str:role_id>/", RolesAPIView.as_view(), name="roles-api-detail"),
    # Remote harnesses (Hermes / OpenMausBot / Rakazo) — config + health + operate
    path("v1/remotes", RemotesListView.as_view(), name="remotes-list-no-slash"),
    path("v1/remotes/", RemotesListView.as_view(), name="remotes-list"),
    path("v1/remotes/test", RemoteProbeCandidateView.as_view(), name="remotes-test-candidate-no-slash"),
    path("v1/remotes/test/", RemoteProbeCandidateView.as_view(), name="remotes-test-candidate"),
    path("v1/remotes/<str:remote_id>", RemoteDetailView.as_view(), name="remotes-detail-no-slash"),
    path("v1/remotes/<str:remote_id>/", RemoteDetailView.as_view(), name="remotes-detail"),
    path("v1/remotes/<str:remote_id>/pair", RemotePairView.as_view(), name="remotes-pair-no-slash"),
    path("v1/remotes/<str:remote_id>/pair/", RemotePairView.as_view(), name="remotes-pair"),
    path("v1/remotes/<str:remote_id>/health", RemoteHealthView.as_view(), name="remotes-health-no-slash"),
    path("v1/remotes/<str:remote_id>/health/", RemoteHealthView.as_view(), name="remotes-health"),
    # Seat health across all three seat kinds (#1658). The batch route is
    # registered before the per-seat one so "v1/seats/health" is not read as
    # kind="health" with a missing seat id.
    path("v1/seats/health", SeatHealthBatchView.as_view(), name="seats-health-no-slash"),
    path("v1/seats/health/", SeatHealthBatchView.as_view(), name="seats-health"),
    # Before the <kind>/<seat_id> pattern for readability only: the shapes cannot
    # collide (3 vs 4 segments), but a reader should see the literal routes first.
    path("v1/seats/doctor", SeatDoctorView.as_view(), name="seats-doctor-no-slash"),
    path("v1/seats/doctor/", SeatDoctorView.as_view(), name="seats-doctor"),
    path(
        "v1/seats/<str:kind>/<str:seat_id>/health",
        SeatHealthView.as_view(),
        name="seat-health-no-slash",
    ),
    path(
        "v1/seats/<str:kind>/<str:seat_id>/health/",
        SeatHealthView.as_view(),
        name="seat-health",
    ),
    path("v1/remotes/<str:remote_id>/operate", RemoteOperateView.as_view(), name="remotes-operate-no-slash"),
    path("v1/remotes/<str:remote_id>/operate/", RemoteOperateView.as_view(), name="remotes-operate"),
    path("v1/remotes/<str:remote_id>/routines", RemoteRoutinesView.as_view(), name="remotes-routines-no-slash"),
    path("v1/remotes/<str:remote_id>/routines/", RemoteRoutinesView.as_view(), name="remotes-routines"),
    # #1358 — TrueForge-only agents + sessions for the navbar pickers.
    path("v1/remotes/<str:remote_id>/trueforge", RemoteTrueForgeCatalogView.as_view(), name="remotes-trueforge-catalog-no-slash"),
    path("v1/remotes/<str:remote_id>/trueforge/", RemoteTrueForgeCatalogView.as_view(), name="remotes-trueforge-catalog"),
    # Handoff Team (API/CLI/remote members) — not /v1/teams/ Profiles aliases.
    path("v1/agent-team", AgentTeamView.as_view(), name="agent-team-no-slash"),
    path("v1/agent-team/", AgentTeamView.as_view(), name="agent-team"),
    # JSON Blueprint Library API (REST counterpart to /blueprint-library/)
    path("v1/library", LibraryAPIView.as_view(), name="library-api-no-slash"),
    path("v1/library/", LibraryAPIView.as_view(), name="library-api"),
    path("v1/library/<str:blueprint_name>/", LibraryDetailAPIView.as_view(), name="library-api-detail"),
    # #1311 — org-shared bot library, preset bots, whole-team share
    path("v1/org-library", OrgLibraryAPIView.as_view(), name="org-library-api-no-slash"),
    path("v1/org-library/", OrgLibraryAPIView.as_view(), name="org-library-api"),
    path("v1/org-library/<str:bot_id>/share", OrgLibraryShareAPIView.as_view(), name="org-library-share-no-slash"),
    path("v1/org-library/<str:bot_id>/share/", OrgLibraryShareAPIView.as_view(), name="org-library-share"),
    path("v1/org-library/<str:bot_id>", OrgLibraryDetailAPIView.as_view(), name="org-library-detail-no-slash"),
    path("v1/org-library/<str:bot_id>/", OrgLibraryDetailAPIView.as_view(), name="org-library-detail"),
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
    # #932: AI-drafted system instructions for the agent popup's overlay writer.
    path("v1/agents/assist-draft/", assist_draft_view, name="assist-draft"),
    # #720: honest sandbox display payload for the computer pane.
    path(
        "v1/agents/<str:agent_id>/sandbox-display/",
        AgentSandboxDisplayView.as_view(),
        name="agent-sandbox-display",
    ),
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
    # #1728: before the `<str:agent_id>` detail route, or "status" binds as a
    # HerdrAgent name lookup and the query surface 404s.
    path("v1/herdr-agents/status", HerdrStatusAPIView.as_view(), name="herdr-agents-status-no-slash"),
    path("v1/herdr-agents/status/", HerdrStatusAPIView.as_view(), name="herdr-agents-status"),
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
    path("v1/agents/<str:agent_id>/profile", AgentProfileAPIView.as_view(), name="agent-profile-api-no-slash"),
    path("v1/agents/<str:agent_id>/profile/", AgentProfileAPIView.as_view(), name="agent-profile-api"),
    path("v1/agents/<str:agent_id>/mcp", AgentMcpAPIView.as_view(), name="agent-mcp-api-no-slash"),
    path("v1/agents/<str:agent_id>/mcp/", AgentMcpAPIView.as_view(), name="agent-mcp-api"),
    path("v1/agents/<str:agent_id>/mcp/tools", AgentMcpToolsAPIView.as_view(), name="agent-mcp-tools-api-no-slash"),
    path("v1/agents/<str:agent_id>/mcp/tools/", AgentMcpToolsAPIView.as_view(), name="agent-mcp-tools-api"),
    path(
        "v1/agents/<str:agent_id>/mcp/tools/<str:tool_name>",
        AgentMcpToolDetailAPIView.as_view(),
        name="agent-mcp-tool-detail-api-no-slash",
    ),
    path(
        "v1/agents/<str:agent_id>/mcp/tools/<str:tool_name>/",
        AgentMcpToolDetailAPIView.as_view(),
        name="agent-mcp-tool-detail-api",
    ),
    path(
        "v1/agents/<str:agent_id>/mcp/tools/<str:tool_name>/execute",
        AgentMcpToolExecuteAPIView.as_view(),
        name="agent-mcp-tool-execute-api-no-slash",
    ),
    path(
        "v1/agents/<str:agent_id>/mcp/tools/<str:tool_name>/execute/",
        AgentMcpToolExecuteAPIView.as_view(),
        name="agent-mcp-tool-execute-api",
    ),
    path(
        "v1/agents/<str:agent_id>/plugins/pack",
        AgentPluginPackAPIView.as_view(),
        name="agent-plugin-pack-api-no-slash",
    ),
    path(
        "v1/agents/<str:agent_id>/plugins/pack/",
        AgentPluginPackAPIView.as_view(),
        name="agent-plugin-pack-api",
    ),
    path(
        "v1/agents/<str:agent_id>/plugins/import",
        AgentPluginPackImportAPIView.as_view(),
        name="agent-plugin-pack-import-api-no-slash",
    ),
    path(
        "v1/agents/<str:agent_id>/plugins/import/",
        AgentPluginPackImportAPIView.as_view(),
        name="agent-plugin-pack-import-api",
    ),
    path(
        "v1/agents/<str:agent_id>/plugins",
        AgentPluginsAPIView.as_view(),
        name="agent-plugins-api-no-slash",
    ),
    path(
        "v1/agents/<str:agent_id>/plugins/",
        AgentPluginsAPIView.as_view(),
        name="agent-plugins-api",
    ),
    path("v1/agents/<str:agent_id>/suggestions", AgentSuggestionsAPIView.as_view(), name="agent-suggestions-api-no-slash"),
    path("v1/agents/<str:agent_id>/suggestions/", AgentSuggestionsAPIView.as_view(), name="agent-suggestions-api"),
    path("v1/agents/<str:agent_id>/sessions", AgentTaskSessionAPIView.as_view(), name="agent-task-session-api-no-slash"),
    path("v1/agents/<str:agent_id>/sessions/", AgentTaskSessionAPIView.as_view(), name="agent-task-session-api"),
    # #1681: the conversation directory. A projection over the canonical
    # ChatConversation rows, so there is no second chat registry behind it.
    path("v1/conversations/", ConversationDirectoryView.as_view(), name="conversation-directory-api"),
    path(
        "v1/conversations/<str:conversation_id>/handoff/",
        ConversationHandoffView.as_view(),
        name="conversation-handoff-api",
    ),
    path(
        "v1/conversations/<str:conversation_id>/move/",
        ConversationMoveTopicView.as_view(),
        name="conversation-move-topic-api",
    ),
    # #1390: agent-scoped memories (profile/log pack; episode/note stay local).
    path("v1/agents/<str:agent_id>/memories", AgentMemoriesAPIView.as_view(), name="agent-memories-api-no-slash"),
    path("v1/agents/<str:agent_id>/memories/", AgentMemoriesAPIView.as_view(), name="agent-memories-api"),
    path(
        "v1/agents/<str:agent_id>/memories/pack",
        AgentMemoryPackAPIView.as_view(),
        name="agent-memory-pack-api-no-slash",
    ),
    path(
        "v1/agents/<str:agent_id>/memories/pack/",
        AgentMemoryPackAPIView.as_view(),
        name="agent-memory-pack-api",
    ),
    path(
        "v1/agents/<str:agent_id>/memories/import",
        AgentMemoryImportAPIView.as_view(),
        name="agent-memory-import-api-no-slash",
    ),
    path(
        "v1/agents/<str:agent_id>/memories/import/",
        AgentMemoryImportAPIView.as_view(),
        name="agent-memory-import-api",
    ),
    path(
        "v1/agents/<str:agent_id>/memories/<str:memory_id>",
        AgentMemoryDetailAPIView.as_view(),
        name="agent-memory-detail-api-no-slash",
    ),
    path(
        "v1/agents/<str:agent_id>/memories/<str:memory_id>/",
        AgentMemoryDetailAPIView.as_view(),
        name="agent-memory-detail-api",
    ),
    # #1392: per-agent skills CRUD + pack (prose only; gettingStarted.skill).
    path("v1/agents/<str:agent_id>/skills", AgentSkillsAPIView.as_view(), name="agent-skills-api-no-slash"),
    path("v1/agents/<str:agent_id>/skills/", AgentSkillsAPIView.as_view(), name="agent-skills-api"),
    path(
        "v1/agents/<str:agent_id>/skills/<str:name>",
        AgentSkillDetailAPIView.as_view(),
        name="agent-skill-detail-api-no-slash",
    ),
    path(
        "v1/agents/<str:agent_id>/skills/<str:name>/",
        AgentSkillDetailAPIView.as_view(),
        name="agent-skill-detail-api",
    ),
    path("v1/agents/<str:agent_id>/pack", AgentPackAPIView.as_view(), name="agent-pack-api-no-slash"),
    path("v1/agents/<str:agent_id>/pack/", AgentPackAPIView.as_view(), name="agent-pack-api"),
    path(
        "v1/agents/<str:agent_id>/pack/import",
        AgentPackImportAPIView.as_view(),
        name="agent-pack-import-api-no-slash",
    ),
    path(
        "v1/agents/<str:agent_id>/pack/import/",
        AgentPackImportAPIView.as_view(),
        name="agent-pack-import-api",
    ),
    path("v1/agent-packs/validate", AgentPackValidateAPIView.as_view(), name="agent-pack-validate-api-no-slash"),
    path("v1/agent-packs/validate/", AgentPackValidateAPIView.as_view(), name="agent-pack-validate-api"),
    # #1398: template pack (profile/memory/skills/routines/plugins; file Grok mapper).
    path(
        "v1/agents/<str:agent_id>/template/import",
        AgentTemplateImportAPIView.as_view(),
        name="agent-template-import-api-no-slash",
    ),
    path(
        "v1/agents/<str:agent_id>/template/import/",
        AgentTemplateImportAPIView.as_view(),
        name="agent-template-import-api",
    ),
    path(
        "v1/agents/<str:agent_id>/template/grok",
        AgentTemplateGrokAPIView.as_view(),
        name="agent-template-grok-api-no-slash",
    ),
    path(
        "v1/agents/<str:agent_id>/template/grok/",
        AgentTemplateGrokAPIView.as_view(),
        name="agent-template-grok-api",
    ),
    path("v1/agents/<str:agent_id>/template", AgentTemplateAPIView.as_view(), name="agent-template-api-no-slash"),
    path("v1/agents/<str:agent_id>/template/", AgentTemplateAPIView.as_view(), name="agent-template-api"),
    path(
        "v1/agent-templates/validate",
        AgentTemplateValidateAPIView.as_view(),
        name="agent-template-validate-api-no-slash",
    ),
    path(
        "v1/agent-templates/validate/",
        AgentTemplateValidateAPIView.as_view(),
        name="agent-template-validate-api",
    ),
    path(
        "v1/agent-templates/from-grok",
        AgentTemplateFromGrokAPIView.as_view(),
        name="agent-template-from-grok-api-no-slash",
    ),
    path(
        "v1/agent-templates/from-grok/",
        AgentTemplateFromGrokAPIView.as_view(),
        name="agent-template-from-grok-api",
    ),
    path(
        "v1/agent-templates/import",
        AgentTemplateCreateAPIView.as_view(),
        name="agent-template-create-api-no-slash",
    ),
    path(
        "v1/agent-templates/import/",
        AgentTemplateCreateAPIView.as_view(),
        name="agent-template-create-api",
    ),
    path(
        "v1/agent-templates/grok-mapper",
        AgentTemplateGrokMapperAPIView.as_view(),
        name="agent-template-grok-mapper-api-no-slash",
    ),
    path(
        "v1/agent-templates/grok-mapper/",
        AgentTemplateGrokMapperAPIView.as_view(),
        name="agent-template-grok-mapper-api",
    ),
    # REQ-80: agent-scoped Routines (PR-merge trigger, Test run, history).
    path("v1/agents/<str:agent_id>/routines", AgentRoutinesAPIView.as_view(), name="agent-routines-api-no-slash"),
    path("v1/agents/<str:agent_id>/routines/", AgentRoutinesAPIView.as_view(), name="agent-routines-api"),
    # #1394: pack/import must win over <routine_id> (otherwise "pack" is a row id).
    path(
        "v1/agents/<str:agent_id>/routines/pack",
        AgentRoutinesPackAPIView.as_view(),
        name="agent-routines-pack-api-no-slash",
    ),
    path(
        "v1/agents/<str:agent_id>/routines/pack/",
        AgentRoutinesPackAPIView.as_view(),
        name="agent-routines-pack-api",
    ),
    path(
        "v1/agents/<str:agent_id>/routines/import",
        AgentRoutinesImportAPIView.as_view(),
        name="agent-routines-import-api-no-slash",
    ),
    path(
        "v1/agents/<str:agent_id>/routines/import/",
        AgentRoutinesImportAPIView.as_view(),
        name="agent-routines-import-api",
    ),
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
    path(
        "v1/agents/<str:agent_id>/routines/<str:routine_id>/run-now",
        AgentRoutineRunNowAPIView.as_view(),
        name="agent-routine-run-now-api-no-slash",
    ),
    path(
        "v1/agents/<str:agent_id>/routines/<str:routine_id>/run-now/",
        AgentRoutineRunNowAPIView.as_view(),
        name="agent-routine-run-now-api",
    ),
    path(
        "v1/agents/<str:agent_id>/routines/<str:routine_id>/fill",
        AgentRoutineFillAPIView.as_view(),
        name="agent-routine-fill-api-no-slash",
    ),
    path(
        "v1/agents/<str:agent_id>/routines/<str:routine_id>/fill/",
        AgentRoutineFillAPIView.as_view(),
        name="agent-routine-fill-api",
    ),
    path(
        "v1/agents/<str:agent_id>/routines/<str:routine_id>/enable",
        AgentRoutineEnableAPIView.as_view(),
        name="agent-routine-enable-api-no-slash",
    ),
    path(
        "v1/agents/<str:agent_id>/routines/<str:routine_id>/enable/",
        AgentRoutineEnableAPIView.as_view(),
        name="agent-routine-enable-api",
    ),
    path("v1/routines", AllRoutinesAPIView.as_view(), name="routines-list-all-no-slash"),
    path("v1/routines/", AllRoutinesAPIView.as_view(), name="routines-list-all"),
    path("v1/routines/presets", RoutinePresetsAPIView.as_view(), name="routines-presets-no-slash"),
    path("v1/routines/presets/", RoutinePresetsAPIView.as_view(), name="routines-presets"),
    path(
        "v1/routines/packs/validate",
        RoutinePackValidateAPIView.as_view(),
        name="routines-pack-validate-no-slash",
    ),
    path(
        "v1/routines/packs/validate/",
        RoutinePackValidateAPIView.as_view(),
        name="routines-pack-validate",
    ),
    path("v1/routines/tool-catalog", RoutineToolCatalogAPIView.as_view(), name="routines-tool-catalog-no-slash"),
    path("v1/routines/tool-catalog/", RoutineToolCatalogAPIView.as_view(), name="routines-tool-catalog"),
    path("v1/routines/github-merge", GithubRoutineMergeAPIView.as_view(), name="routines-github-merge-api-no-slash"),
    path("v1/routines/github-merge/", GithubRoutineMergeAPIView.as_view(), name="routines-github-merge-api"),
    path(
        "v1/routines/events/github",
        csrf_exempt(GithubRoutineEventsAPIView.as_view()),
        name="routines-github-events-api-no-slash",
    ),
    path(
        "v1/routines/events/github/",
        csrf_exempt(GithubRoutineEventsAPIView.as_view()),
        name="routines-github-events-api",
    ),
    path(
        "v1/routines/mailbox-message",
        MailboxRoutineMessageAPIView.as_view(),
        name="routines-mailbox-message-api-no-slash",
    ),
    path(
        "v1/routines/mailbox-message/",
        MailboxRoutineMessageAPIView.as_view(),
        name="routines-mailbox-message-api",
    ),
    path("v1/test-schedules/status", TestScheduleStatusAPIView.as_view(), name="test-schedules-status-no-slash"),
    path("v1/test-schedules/status/", TestScheduleStatusAPIView.as_view(), name="test-schedules-status"),
    path("v1/test-schedules", TestSchedulesAPIView.as_view(), name="test-schedules-api-no-slash"),
    path("v1/test-schedules/", TestSchedulesAPIView.as_view(), name="test-schedules-api"),
    path(
        "v1/test-schedules/<str:schedule_id>/run-now",
        TestScheduleRunNowAPIView.as_view(),
        name="test-schedule-run-now-api-no-slash",
    ),
    path(
        "v1/test-schedules/<str:schedule_id>/run-now/",
        TestScheduleRunNowAPIView.as_view(),
        name="test-schedule-run-now-api",
    ),
    path(
        "v1/test-schedules/<str:schedule_id>",
        TestScheduleDetailAPIView.as_view(),
        name="test-schedule-detail-api-no-slash",
    ),
    path(
        "v1/test-schedules/<str:schedule_id>/",
        TestScheduleDetailAPIView.as_view(),
        name="test-schedule-detail-api",
    ),
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
    # Which install profile this process booted with (extras active, and any
    # required module that failed to import). Read-only.
    path("v1/system/build/", BuildInfoView.as_view(), name="system-build"),
    # #905: read-only diagnostics bundle for the WebUI (#906 palette, #907 modal).
    # Slash-only: the no-slash twin would steal the base operationId in the
    # OpenAPI schema (spectacular dedupes alphabetically); APPEND_SLASH covers it.
    path("v1/diagnostics/", DiagnosticsView.as_view(), name="diagnostics"),
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
    # #224: read-only "what the model sees" payload for the generations panel.
    path("chat/raw-context/", chat_raw_context, name="chat_raw_context"),
    # #215: per-seat context-window usage (messages + summaries + overhead).
    path("chat/context-usage/", chat_context_usage, name="chat_context_usage"),
    # REQ-38: composer file upload (sqlite metadata + local bytes).
    path("v1/chat/attachments", chat_attachment_upload, name="chat-attachments-no-slash"),
    path("v1/chat/attachments/", chat_attachment_upload, name="chat-attachments"),
    path(
        "v1/chat/attachments/<uuid:attachment_id>/content",
        chat_attachment_content,
        name="chat-attachment-content-no-slash",
    ),
    path(
        "v1/chat/attachments/<uuid:attachment_id>/content/",
        chat_attachment_content,
        name="chat-attachment-content",
    ),
    # #858: enhance user prompt via tiny model
    path("v1/assist/enhance-prompt", EnhancePromptAPIView.as_view(), name="assist-enhance-prompt-no-slash"),
    path("v1/assist/enhance-prompt/", EnhancePromptAPIView.as_view(), name="assist-enhance-prompt"),
    # #860: inline ghost text autocompletion
    path("v1/chat/autocomplete", ChatAutocompleteAPIView.as_view(), name="chat-autocomplete-no-slash"),
    path("v1/chat/autocomplete/", ChatAutocompleteAPIView.as_view(), name="chat-autocomplete"),
    # REQ-37 / #859: compact the backlog into a nested sqlite summary (raw JSON stays).
    path("chat/compact/", chat_compact, name="chat_compact"),
    path("v1/chat/compact", chat_compact, name="v1-chat-compact-no-slash"),
    path("v1/chat/compact/", chat_compact, name="v1-chat-compact"),
    path("chat/context-start/", chat_context_start, name="chat_context_start"),
    # #214: tick/untick whether a summary (and its span) feeds model context.
    path(
        "chat/summary/toggle-context/",
        chat_summary_toggle_context,
        name="chat_summary_toggle_context",
    ),
    # Blueprint Library endpoints
    path("blueprint-library/", blueprint_library, name="blueprint_library"),
    # REQ-921 / #540: browsable Blueprint SDK reference, linked from the Definition pane.
    path("sdk-docs/", sdk_docs, name="sdk_docs"),
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
    path(
        "sessions",
        RedirectView.as_view(url="/sessions/", permanent=False, query_string=True),
        name="spa_sessions_to_django",
    ),
    path(
        "login",
        RedirectView.as_view(url="/login/", permanent=False, query_string=True),
        name="spa_login_to_django",
    ),
    path(
        "blueprint-library",
        RedirectView.as_view(url="/blueprint-library/", permanent=False, query_string=True),
        name="spa_blueprint_library_to_django",
    ),
    path(
        "profiles",
        RedirectView.as_view(url="/profiles/", permanent=False, query_string=True),
        name="spa_profiles_to_django",
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
    # #714: the asset/catch-all views moved to web_views (request-time
    # frontend lookup + explicit cache contract). Registration unchanged.
    urlpatterns += [
        re_path(r'^assets/(?P<path>.*)$', spa_asset_view),
        re_path(r'^(?!api/|admin/|static/|assets/|mcp/|marketplace/|v1/|teams/|blueprint-library/|agent-creator/|settings/|accounts/|login/|profiles/|sessions/|webui/|chat/|agents/|django_chat).*$', spa_fallback_view),
    ]
