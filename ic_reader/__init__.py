"""Read-only Idle Champions memory reader (area/zone state)."""

from ic_reader.exceptions import (
    ConfigError,
    ICReaderError,
    InvalidPointerChainError,
    MemoryReadError,
    ModuleNotFoundError,
    ProcessNotFoundError,
)
from ic_reader.resolver import AreaResolver, create_resolver

__all__ = [
    "AreaResolver",
    "ConfigError",
    "ICReaderError",
    "InvalidPointerChainError",
    "MemoryReadError",
    "ModuleNotFoundError",
    "ProcessNotFoundError",
    "create_resolver",
]

__version__ = "0.1.0"
