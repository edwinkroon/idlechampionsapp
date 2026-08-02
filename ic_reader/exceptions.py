"""Exceptions for read-only Idle Champions memory access."""


class ICReaderError(Exception):
    """Base error for ic_reader."""


class ProcessNotFoundError(ICReaderError):
    """Idle Champions process could not be found."""


class ModuleNotFoundError(ICReaderError):
    """Required module (e.g. GameAssembly.dll) not loaded in the process."""


class MemoryReadError(ICReaderError):
    """ReadProcessMemory failed or returned incomplete data."""


class InvalidPointerChainError(ICReaderError):
    """Pointer chain resolved to null or an invalid address."""


class ConfigError(ICReaderError):
    """Invalid or missing game_offsets configuration."""
