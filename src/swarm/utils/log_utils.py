import logging
import os  # Added for os.getenv
import sys
from enum import Enum  # Added for LogFormat


# Define LogFormat enum here as it's not in swarm.settings
class LogFormat(str, Enum):
    VERBOSE = '[{levelname}] {asctime} - {name}:{lineno} - {message}'
    SIMPLE = '[{levelname}] {message}'
    RICH = "%(message)s" # For compatibility if Rich is used by the handler
    # Add other formats if needed

# Cache for initialized loggers to avoid adding handlers multiple times
_initialized_loggers = set()

# Helper to get settings from environment with defaults
def get_env_log_level() -> str:
    from swarm.utils.env_utils import get_swarm_log_level

    return get_swarm_log_level()

def get_env_log_format() -> LogFormat:
    format_str = os.getenv('SWARM_LOG_FORMAT', 'VERBOSE').upper()
    try:
        return LogFormat[format_str]
    except KeyError:
        # print(f"Warning: Invalid SWARM_LOG_FORMAT '{format_str}'. Defaulting to VERBOSE.", file=sys.stderr)
        return LogFormat.VERBOSE

def setup_logging(logger_name: str | None = None, level: str | int | None = None, force_reconfigure: bool = False) -> logging.Logger:
    """
    Configures and returns a logger instance. Ensures handlers are not duplicated
    and prevents propagation to avoid duplicate messages from parent loggers.

    Args:
        logger_name: Name of the logger. If None, configures the root logger.
        level: Logging level (e.g., 'DEBUG', 'INFO', logging.DEBUG). Defaults to SWARM_LOG_LEVEL env var.
        force_reconfigure: If True, remove existing handlers before adding new ones.

    Returns:
        Configured logger instance.
    """
    effective_level_str = level if level is not None else get_env_log_level()
    log_level_val = logging.getLevelName(str(effective_level_str).upper()) if isinstance(effective_level_str, str) else effective_level_str

    logger = logging.getLogger(logger_name)
    logger_id = logger_name if logger_name is not None else "root"

    if logger_id in _initialized_loggers and not force_reconfigure:
        if logger.level != log_level_val:
             logger.setLevel(log_level_val)
        return logger

    if force_reconfigure or logger_id not in _initialized_loggers:
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        if logger_name is None: # Root logger
             root_logger = logging.getLogger()
             for handler in root_logger.handlers[:]:
                  root_logger.removeHandler(handler)

    logger.setLevel(log_level_val)

    if logger_name is not None:
        logger.propagate = False
    else: # Root logger
        # Django's default LOGGING setup might add handlers to root.
        # We want to ensure our intended handler is present if no other handlers are.
        # If Django's LOGGING dict already configures root, this might be redundant or conflict.
        # For now, let's assume this setup_logging is the primary configurator for these loggers.
        logger.propagate = False # Typically, you don't want root to propagate if you're managing it here.

    if not logger.handlers: # Add handler only if none exist
        handler = logging.StreamHandler(sys.stdout) # Changed from sys.stderr to sys.stdout
        log_format_enum_val = get_env_log_format()

        # Use style='{' for format strings that use {}
        formatter_style = '{' if '{' in log_format_enum_val.value else '%'

        formatter = logging.Formatter(log_format_enum_val.value, style=formatter_style)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    _initialized_loggers.add(logger_id)

    # Example of setting specific levels for noisy loggers, can be expanded
    # logging.getLogger('some_noisy_library').setLevel(logging.WARNING)

    return logger

# Default logger for general use within the swarm package, configured by this utility
# This replaces the direct import from swarm.core.log_utils
logger = setup_logging("swarm")

