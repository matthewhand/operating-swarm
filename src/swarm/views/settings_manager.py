"""
Settings Manager for Operating Swarm
Handles collection and management of all configuration settings
"""
from typing import Any

from django.conf import settings

# Package reader. Tests patch this symbol. No-arg discovery, validate, env
# substitution — the same function the provider rate limiter calls.
from swarm.core.config_loader import load_config
from swarm.utils.env_utils import (
    get_anthropic_api_key,
    get_django_csrf_trusted_origins,
    get_django_log_level,
    get_log_level,
    get_loglevel,
    get_ollama_base_url,
    get_openai_api_key,
    get_swarm_command_timeout,
    get_swarm_debug,
    get_swarm_log_level,
    is_enable_admin,
    is_enable_webui,
)


class SettingsManager:
    """Comprehensive settings management for Operating Swarm"""

    def __init__(self):
        self.settings_groups = {
            'django': {
                'title': 'Django Framework',
                'description': 'Core Django application settings',
                'icon': '🌐',
                'settings': {}
            },
            'swarm_core': {
                'title': 'Swarm Core',
                'description': 'Core Operating Swarm functionality settings',
                'icon': '🚀',
                'settings': {}
            },
            'authentication': {
                'title': 'Authentication & Security',
                'description': 'API authentication and security settings',
                'icon': '🔐',
                'settings': {}
            },
            'llm_providers': {
                'title': 'LLM Providers',
                'description': 'Language model provider configurations',
                'icon': '🧠',
                'settings': {}
            },
            'blueprints': {
                'title': 'Blueprints & Agents',
                'description': 'Blueprint and agent configuration settings',
                'icon': '🤖',
                'settings': {}
            },
            'mcp_servers': {
                'title': 'MCP Servers',
                'description': 'Model Context Protocol server configurations',
                'icon': '🔌',
                'settings': {}
            },
            'remotes': {
                'title': 'Remote Harnesses',
                'description': (
                    'Hermes, OpenMausBot, Rakazo, and nested open-swarm as Team members '
                    '(handoff/as_tool). Persist base URL + auth. Not the /teams/ '
                    'profile-alias registry.'
                ),
                'icon': '🛰️',
                'settings': {}
            },
            'database': {
                'title': 'Database',
                'description': 'Database connection and configuration',
                'icon': '🗄️',
                'settings': {}
            },
            'logging': {
                'title': 'Logging & Debugging',
                'description': 'Logging levels and debug settings',
                'icon': '📝',
                'settings': {}
            },
            'performance': {
                'title': 'Performance & Limits',
                'description': 'Performance tuning and resource limits',
                'icon': '⚡',
                'settings': {}
            },
            'ui_features': {
                'title': 'UI Features',
                'description': 'Web interface feature toggles',
                'icon': '🎨',
                'settings': {}
            },
            'chat_persistence': {
                'title': 'Chat persistence',
                'description': 'Per-agent JSON chat threads and Settings-only retention',
                'icon': '💬',
                'settings': {}
            }
        }

    def collect_all_settings(self) -> dict[str, Any]:
        """Collect all settings from various sources"""

        # Django settings
        self._collect_django_settings()

        # Swarm core settings
        self._collect_swarm_core_settings()

        # Authentication settings
        self._collect_auth_settings()

        # LLM provider settings
        self._collect_llm_settings()

        # Blueprint settings
        self._collect_blueprint_settings()

        # MCP server settings
        self._collect_mcp_settings()

        # Remote harnesses (Hermes / OMB / Rakazo / nested swarm)
        self._collect_remotes_settings()

        # Database settings
        self._collect_database_settings()

        # Logging settings
        self._collect_logging_settings()

        # Performance settings
        self._collect_performance_settings()

        # UI feature settings
        self._collect_ui_settings()

        # Per-agent chat JSON store + retention
        self._collect_chat_persistence_settings()

        return self.settings_groups

    def _collect_django_settings(self):
        """Collect Django framework settings"""
        django_settings = {
            'DEBUG': {
                'value': getattr(settings, 'DEBUG', False),
                'env_var': 'DJANGO_DEBUG',
                'type': 'boolean',
                'description': 'Enable Django debug mode',
                'category': 'development',
                'sensitive': False
            },
            'SECRET_KEY': {
                'value': '***HIDDEN***' if getattr(settings, 'SECRET_KEY', None) else None,
                'env_var': 'DJANGO_SECRET_KEY',
                'type': 'string',
                'description': 'Django secret key for cryptographic signing',
                'category': 'security',
                'sensitive': True
            },
            'ALLOWED_HOSTS': {
                'value': getattr(settings, 'ALLOWED_HOSTS', []),
                'env_var': 'DJANGO_ALLOWED_HOSTS',
                'type': 'list',
                'description': 'List of allowed hostnames for this Django site',
                'category': 'security',
                'sensitive': False
            },
            'TIME_ZONE': {
                'value': getattr(settings, 'TIME_ZONE', 'UTC'),
                'env_var': None,
                'type': 'string',
                'description': 'Default timezone for the application',
                'category': 'localization',
                'sensitive': False
            },
            'LANGUAGE_CODE': {
                'value': getattr(settings, 'LANGUAGE_CODE', 'en-us'),
                'env_var': None,
                'type': 'string',
                'description': 'Default language code',
                'category': 'localization',
                'sensitive': False
            }
        }
        self.settings_groups['django']['settings'] = django_settings

    def _collect_swarm_core_settings(self):
        """Collect Swarm core settings"""
        swarm_settings = {
            'SWARM_CONFIG_PATH': {
                'value': getattr(settings, 'SWARM_CONFIG_PATH', None),
                'env_var': 'SWARM_CONFIG_PATH',
                'type': 'path',
                'description': 'Path to the main swarm configuration file',
                'category': 'core',
                'sensitive': False
            },
            'BLUEPRINT_DIRECTORY': {
                'value': getattr(settings, 'BLUEPRINT_DIRECTORY', None),
                'env_var': 'BLUEPRINT_DIRECTORY',
                'type': 'path',
                'description': 'Directory containing blueprint definitions',
                'category': 'core',
                'sensitive': False
            },
            'BASE_DIR': {
                'value': str(getattr(settings, 'BASE_DIR', '')),
                'env_var': None,
                'type': 'path',
                'description': 'Base directory of the Django application',
                'category': 'core',
                'sensitive': False
            }
        }
        self.settings_groups['swarm_core']['settings'] = swarm_settings

    def _collect_auth_settings(self):
        """Collect authentication and security settings"""
        auth_settings = {
            'ENABLE_API_AUTH': {
                'value': getattr(settings, 'ENABLE_API_AUTH', False),
                'env_var': 'API_AUTH_TOKEN',
                'type': 'boolean',
                'description': 'Enable API token authentication',
                'category': 'authentication',
                'sensitive': False
            },
            'SWARM_API_KEY': {
                'value': '***SET***' if getattr(settings, 'SWARM_API_KEY', None) else 'Not Set',
                'env_var': 'API_AUTH_TOKEN',
                'type': 'string',
                'description': 'API authentication token',
                'category': 'authentication',
                'sensitive': True
            },
            'CSRF_TRUSTED_ORIGINS': {
                # Prefer environment variable so tests with patched env behave predictably
                'value': (
                    ','.join(get_django_csrf_trusted_origins())
                ),
                'env_var': 'DJANGO_CSRF_TRUSTED_ORIGINS',
                'type': 'list',
                'description': 'Trusted origins for CSRF protection',
                'category': 'security',
                'sensitive': False
            },
            'LOGIN_URL': {
                'value': getattr(settings, 'LOGIN_URL', '/login/'),
                'env_var': None,
                'type': 'string',
                'description': 'URL for user login',
                'category': 'authentication',
                'sensitive': False
            }
        }
        # Normalize CSRF_TRUSTED_ORIGINS value into a list or 'Not Set'
        csrf_val = auth_settings['CSRF_TRUSTED_ORIGINS']['value']
        if csrf_val:
            auth_settings['CSRF_TRUSTED_ORIGINS']['value'] = [s for s in csrf_val.split(',') if s]
        else:
            auth_settings['CSRF_TRUSTED_ORIGINS']['value'] = []

        self.settings_groups['authentication']['settings'] = auth_settings

    def _collect_llm_settings(self):
        """Collect LLM provider settings from swarm_config.json"""
        try:
            config = load_config()
            llm_config = config.get('llm', {})
            profiles_config = config.get('profiles', {})

            llm_settings = {}

            # LLM providers — mark sensitive when api keys present (API redacts value).
            for provider, config_data in llm_config.items():
                sensitive = False
                if isinstance(config_data, dict):
                    sensitive = any(
                        k.lower() in ("api_key", "apikey", "token", "secret", "password")
                        or "key" in k.lower()
                        for k in config_data
                    )
                else:
                    sensitive = "api_key" in str(config_data).lower()
                llm_settings[f'LLM_{provider.upper()}'] = {
                    'value': config_data,
                    'env_var': None,
                    'type': 'object',
                    'description': f'Configuration for {provider} LLM provider',
                    'category': 'provider',
                    'sensitive': sensitive,
                }

            # LLM profiles often embed api_key / base_url secrets — always treat as sensitive.
            for profile, profile_data in profiles_config.items():
                llm_settings[f'PROFILE_{profile.upper()}'] = {
                    'value': profile_data,
                    'env_var': None,
                    'type': 'object',
                    'description': f'LLM profile configuration for {profile}',
                    'category': 'profile',
                    'sensitive': True,
                }

            settings_block = config.get("settings") if isinstance(config.get("settings"), dict) else {}
            llm_settings["DEFAULT_LLM_PROFILE"] = {
                "value": settings_block.get("default_llm_profile") or settings_block.get("default_llm") or "default",
                "env_var": "DEFAULT_LLM",
                "type": "string",
                "description": (
                    "SPA Settings default inference profile "
                    "(settings.default_llm_profile). Chat / server default uses this."
                ),
                "category": "profile",
                "sensitive": False,
            }
            llm_settings["OVERRIDE_PER_TASK"] = {
                "value": bool(settings_block.get("override_per_task", False)),
                "env_var": None,
                "type": "boolean",
                "description": "When true, map task classes to profiles instead of using Default for everything.",
                "category": "profile",
                "sensitive": False,
            }
            llm_settings["TASK_LLM_PROFILES"] = {
                "value": settings_block.get("task_llm_profiles") or {},
                "env_var": None,
                "type": "object",
                "description": (
                    "Task class → model id map (orchestration / auxiliary / delegation). "
                    "Roles are task classes, not required model ids."
                ),
                "category": "profile",
                "sensitive": False,
            }

            # Environment variables for common LLM providers
            env_llm_settings = {
                'OPENAI_API_KEY': {
                    'value': '***SET***' if get_openai_api_key() else 'Not Set',
                    'env_var': 'OPENAI_API_KEY',
                    'type': 'string',
                    'description': 'OpenAI API key',
                    'category': 'api_key',
                    'sensitive': True
                },
                'ANTHROPIC_API_KEY': {
                    'value': '***SET***' if get_anthropic_api_key() else 'Not Set',
                    'env_var': 'ANTHROPIC_API_KEY',
                    'type': 'string',
                    'description': 'Anthropic API key',
                    'category': 'api_key',
                    'sensitive': True
                },
                'OLLAMA_BASE_URL': {
                    'value': get_ollama_base_url() or 'Not Set',
                    'env_var': 'OLLAMA_BASE_URL',
                    'type': 'string',
                    'description': 'Ollama server base URL',
                    'category': 'endpoint',
                    'sensitive': False
                }
            }

            llm_settings.update(env_llm_settings)

        except Exception as e:
            llm_settings = {
                'CONFIG_ERROR': {
                    'value': f'Error loading LLM config: {str(e)}',
                    'env_var': None,
                    'type': 'error',
                    'description': 'LLM configuration loading error',
                    'category': 'error',
                    'sensitive': False
                }
            }

        self.settings_groups['llm_providers']['settings'] = llm_settings

    def _collect_blueprint_settings(self):
        """Collect blueprint-related settings"""
        try:
            config = load_config()
            blueprint_config = config.get('blueprints', {})

            blueprint_settings = {
                'BLUEPRINT_DEFAULTS': {
                    'value': blueprint_config.get('defaults', {}),
                    'env_var': None,
                    'type': 'object',
                    'description': 'Default settings for all blueprints',
                    'category': 'defaults',
                    'sensitive': False
                },
                'ENABLED_BLUEPRINTS': {
                    'value': blueprint_config.get('enabled', []),
                    'env_var': None,
                    'type': 'list',
                    'description': 'List of enabled blueprints',
                    'category': 'enabled',
                    'sensitive': False
                }
            }

            # Add environment variables related to blueprints
            env_blueprint_settings = {
                'SWARM_DEBUG': {
                    'value': get_swarm_debug() or 'Not Set',
                    'env_var': 'SWARM_DEBUG',
                    'type': 'string',
                    'description': 'Enable Swarm debug mode',
                    'category': 'debug',
                    'sensitive': False
                },
                'SWARM_COMMAND_TIMEOUT': {
                    'value': str(get_swarm_command_timeout()),
                    'env_var': 'SWARM_COMMAND_TIMEOUT',
                    'type': 'integer',
                    'description': 'Timeout for blueprint command execution (seconds)',
                    'category': 'performance',
                    'sensitive': False
                }
            }

            blueprint_settings.update(env_blueprint_settings)

        except Exception as e:
            blueprint_settings = {
                'CONFIG_ERROR': {
                    'value': f'Error loading blueprint config: {str(e)}',
                    'env_var': None,
                    'type': 'error',
                    'description': 'Blueprint configuration loading error',
                    'category': 'error',
                    'sensitive': False
                }
            }

        self.settings_groups['blueprints']['settings'] = blueprint_settings

    def _collect_mcp_settings(self):
        """Collect MCP server settings"""
        try:
            config = load_config()
            mcp_config = config.get('mcpServers', {})

            mcp_settings = {}

            for server_name, server_config in mcp_config.items():
                # MCP configs almost always carry env tokens/keys — mark sensitive so
                # dashboard/API redaction never treats them as plain metadata.
                sensitive = True
                if isinstance(server_config, dict):
                    env = server_config.get("env") or {}
                    headers = server_config.get("headers") or {}
                    if not env and not headers:
                        # No credential surfaces — still recurse-redact nested dicts.
                        sensitive = False
                mcp_settings[f'MCP_{server_name.upper()}'] = {
                    'value': server_config,
                    'env_var': None,
                    'type': 'object',
                    'description': f'MCP server configuration for {server_name}',
                    'category': 'server',
                    'sensitive': sensitive,
                }

            if not mcp_settings:
                mcp_settings['NO_MCP_SERVERS'] = {
                    'value': 'No MCP servers configured',
                    'env_var': None,
                    'type': 'info',
                    'description': 'No MCP servers are currently configured',
                    'category': 'info',
                    'sensitive': False
                }

        except Exception as e:
            mcp_settings = {
                'CONFIG_ERROR': {
                    'value': f'Error loading MCP config: {str(e)}',
                    'env_var': None,
                    'type': 'error',
                    'description': 'MCP configuration loading error',
                    'category': 'error',
                    'sensitive': False
                }
            }

        self.settings_groups['mcp_servers']['settings'] = mcp_settings

    def _collect_remotes_settings(self):
        """Collect Hermes / OMB / Rakazo / nested-swarm harness settings (secrets redacted)."""
        try:
            from swarm.core import remotes as remotes_core

            remote_settings: dict[str, Any] = {}
            placed = remotes_core.load_placed_members()
            remote_settings["TEAM_MEMBERS"] = {
                "value": placed,
                "env_var": None,
                "type": "list",
                "description": (
                    "Remotes placed in the handoff Team (see/talk via as_tool). "
                    "Not /teams/ LLM-profile aliases (Profiles). "
                    "PATCH /v1/agent-team/ or swarm-cli remotes place|unplace."
                ),
                "category": "remote",
                "sensitive": False,
            }
            for spec in remotes_core.load_all_remotes().values():
                pub = spec.public_dict()
                remote_settings[spec.id.upper()] = {
                    "value": {
                        "kind": pub.get("kind") or spec.id,
                        "configured": pub.get("configured", False),
                        "base_url": pub["base_url"],
                        "ui_url": pub["ui_url"],
                        "api_key_env": pub.get("api_key_env") or "",
                        "session_cookie_env": pub.get("session_cookie_env") or "",
                        "api_key": "redacted" if pub["api_key_set"] else "Not Set",
                        "cookie": "redacted" if pub["cookie_set"] else "Not Set",
                        "host_label": pub["host_label"],
                        "source": pub["source"],
                    },
                    "env_var": {
                        "hermes": "HERMES_BASE_URL / HERMES_API_KEY",
                        "omb": "OMB_BASE_URL / OMB_API_KEY",
                        "rakazo": "RAKAZO_BASE_URL / RAKAZO_API_KEY / RAKAZO_SESSION_COOKIE",
                        "swarm": "SWARM_REMOTE_BASE_URL / SWARM_REMOTE_API_KEY",
                    }.get(spec.id),
                    "type": "object",
                    "description": spec.notes,
                    "category": "remote",
                    "sensitive": True,
                }
        except Exception as e:
            remote_settings = {
                "CONFIG_ERROR": {
                    "value": f"Error loading remotes: {e}",
                    "env_var": None,
                    "type": "error",
                    "description": "Remote harness configuration loading error",
                    "category": "error",
                    "sensitive": False,
                }
            }
        self.settings_groups["remotes"]["settings"] = remote_settings

    def _collect_database_settings(self):
        """Collect database settings"""
        db_config = getattr(settings, 'DATABASES', {}).get('default', {})

        database_settings = {
            'ENGINE': {
                'value': db_config.get('ENGINE', 'Not Set'),
                'env_var': None,
                'type': 'string',
                'description': 'Database engine',
                'category': 'connection',
                'sensitive': False
            },
            'NAME': {
                'value': db_config.get('NAME', 'Not Set'),
                'env_var': 'DJANGO_DB_NAME',
                'type': 'string',
                'description': 'Database name or file path',
                'category': 'connection',
                'sensitive': False
            },
            'TEST_NAME': {
                'value': db_config.get('TEST', {}).get('NAME', 'Not Set'),
                'env_var': 'DJANGO_TEST_DB_NAME',
                'type': 'string',
                'description': 'Test database name or file path',
                'category': 'testing',
                'sensitive': False
            }
        }

        self.settings_groups['database']['settings'] = database_settings

    def _collect_logging_settings(self):
        """Collect logging and debug settings"""
        logging_settings = {
            'DJANGO_LOG_LEVEL': {
                'value': get_django_log_level(),
                'env_var': 'DJANGO_LOG_LEVEL',
                'type': 'string',
                'description': 'Django logging level',
                'category': 'level',
                'sensitive': False
            },
            'SWARM_LOG_LEVEL': {
                'value': get_swarm_log_level(),
                'env_var': 'SWARM_LOG_LEVEL',
                'type': 'string',
                'description': 'Swarm logging level',
                'category': 'level',
                'sensitive': False
            },
            'LOG_LEVEL': {
                'value': get_log_level() or 'Not Set',
                'env_var': 'LOG_LEVEL',
                'type': 'string',
                'description': 'General log level',
                'category': 'level',
                'sensitive': False
            },
            'LOGLEVEL': {
                'value': get_loglevel() or 'Not Set',
                'env_var': 'LOGLEVEL',
                'type': 'string',
                'description': 'Alternative log level variable',
                'category': 'level',
                'sensitive': False
            }
        }

        self.settings_groups['logging']['settings'] = logging_settings

    def _collect_performance_settings(self):
        """Collect performance and resource limit settings"""
        performance_settings = {
            'REDIS_HOST': {
                'value': getattr(settings, 'REDIS_HOST', 'localhost'),
                'env_var': 'REDIS_HOST',
                'type': 'string',
                'description': 'Redis server hostname',
                'category': 'redis',
                'sensitive': False
            },
            'REDIS_PORT': {
                'value': getattr(settings, 'REDIS_PORT', 6379),
                'env_var': 'REDIS_PORT',
                'type': 'integer',
                'description': 'Redis server port',
                'category': 'redis',
                'sensitive': False
            },
            'SWARM_COMMAND_TIMEOUT': {
                'value': str(get_swarm_command_timeout()),
                'env_var': 'SWARM_COMMAND_TIMEOUT',
                'type': 'integer',
                'description': 'Command execution timeout in seconds',
                'category': 'limits',
                'sensitive': False
            }
        }

        self.settings_groups['performance']['settings'] = performance_settings

    def _collect_ui_settings(self):
        """Collect UI feature toggle settings"""
        ui_settings = {
            'ENABLE_WEBUI': {
                'value': 'true' if is_enable_webui() else 'false',
                'env_var': 'ENABLE_WEBUI',
                'type': 'boolean',
                'description': 'Enable web user interface',
                'category': 'features',
                'sensitive': False
            },
            'ENABLE_ADMIN': {
                'value': 'true' if is_enable_admin() else 'false',
                'env_var': 'ENABLE_ADMIN',
                'type': 'boolean',
                'description': 'Enable Django admin interface',
                'category': 'features',
                'sensitive': False
            }
        }

        self.settings_groups['ui_features']['settings'] = ui_settings

    def _collect_chat_persistence_settings(self):
        """Collect chat retention settings. History is the Django database."""
        from swarm.core import chat_store

        chat_settings = {
            'SWARM_CHAT_DIR': {
                'value': str(chat_store.store_dir()),
                'env_var': chat_store.ENV_CHAT_DIR,
                'type': 'path',
                'description': (
                    'Directory for the derived per-agent JSON cache '
                    '(active/<user>/<agent>.json and trash/). '
                    'Canonical chat history is the Django database. '
                    'Unset uses $SWARM_USER_DATA_DIR/chats or the user data directory.'
                ),
                'category': 'storage',
                'sensitive': False,
            },
            'SWARM_CHAT_MAX_AGE_DAYS': {
                'value': str(chat_store.get_max_age_days()),
                'env_var': chat_store.ENV_CHAT_MAX_AGE_DAYS,
                'type': 'integer',
                'description': (
                    'Auto-move inactive agent chats to trash after this many days '
                    f'(default {chat_store.DEFAULT_MAX_AGE_DAYS}). Set 0 to disable. '
                    'Trash is the database. Never hard-deletes; Empty trash on this page is manual.'
                ),
                'category': 'retention',
                'sensitive': False,
            },
        }
        self.settings_groups['chat_persistence']['settings'] = chat_settings


# Global settings manager instance
settings_manager = SettingsManager()
