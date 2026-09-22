import logging as _mem_logger
from typing import Any, Protocol, runtime_checkable

from .base import BaseMemory
from .langmem_memory import LangmemMemory
from .mem0_memory import Mem0Memory
from .papr_memory import PaprMemory

_mem_log = _mem_logger.getLogger(__name__)


@runtime_checkable
class MemoryBackend(Protocol):
    """Structural protocol for memory backends — any class with add/search qualifies."""
    def add(self, messages: Any, user_id: str = "default", metadata: dict | None = None) -> None: ...
    def search(self, query: str, user_id: str = "default", limit: int | None = None) -> list[str]: ...


def get_memory_backend(config: dict | str | None = None, options: dict | None = None) -> BaseMemory | None:
    """Factory: instantiate a memory backend from a config dict or backend name string."""
    if not config:
        return None
    if isinstance(config, str):
        backend_name = config
    else:
        backend_name = config.get('backend', '')
    if not backend_name or backend_name.lower() in ('none', ''):
        return None
    name = backend_name.lower().strip()
    try:
        if name == 'mem0':
            return Mem0Memory(config if isinstance(config, dict) else {})
        elif name == 'langmem':
            return LangmemMemory(config if isinstance(config, dict) else {})
        elif name == 'papr':
            return PaprMemory(config if isinstance(config, dict) else {})
    except ImportError as e:
        _mem_log.warning("Memory backend '%s' is not available (missing dependency): %s", name, e)
        return None
    except Exception as e:
        _mem_log.warning("Failed to instantiate memory backend '%s': %s", name, e)
        return None
    return None


__all__ = [
    "BaseMemory",
    "LangmemMemory",
    "Mem0Memory",
    "MemoryBackend",
    "PaprMemory",
    "get_memory_backend",
]
