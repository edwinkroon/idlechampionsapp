"""Read-only process memory via ReadProcessMemory (ctypes)."""

from __future__ import annotations

import ctypes
import struct
from abc import ABC, abstractmethod

from ic_reader.exceptions import MemoryReadError
from ic_reader.models import ValueType
from ic_reader.process import close_process_handle, open_process_handle

# Minimum plausible user-mode address on 64-bit Windows
MIN_USER_ADDRESS = 0x10000
MAX_USER_ADDRESS = 0x7FFFFFFFFFFF


class MemoryReader(ABC):
    """Abstract read-only memory access."""

    @abstractmethod
    def read_bytes(self, address: int, size: int) -> bytes:
        ...

    @abstractmethod
    def read_uint64(self, address: int) -> int:
        ...

    def read_int32(self, address: int) -> int:
        data = self.read_bytes(address, 4)
        return struct.unpack("<i", data)[0]

    def read_int64(self, address: int) -> int:
        data = self.read_bytes(address, 8)
        return struct.unpack("<q", data)[0]

    def read_float(self, address: int) -> float:
        data = self.read_bytes(address, 4)
        return struct.unpack("<f", data)[0]

    def read_string(self, address: int, max_length: int = 256) -> str:
        raw = self.read_bytes(address, max_length)
        nul = raw.find(b"\x00")
        if nul >= 0:
            raw = raw[:nul]
        return raw.decode("utf-8", errors="replace")

    def read_typed(self, address: int, value_type: ValueType) -> int | float | str:
        if value_type == ValueType.INT32:
            return self.read_int32(address)
        if value_type == ValueType.INT64:
            return self.read_int64(address)
        if value_type == ValueType.FLOAT:
            return self.read_float(address)
        if value_type == ValueType.STRING:
            return self.read_string(address)
        raise MemoryReadError(f"Unsupported value type: {value_type}")

    def is_readable_address(self, address: int) -> bool:
        return MIN_USER_ADDRESS <= address <= MAX_USER_ADDRESS


class Win32MemoryReader(MemoryReader):
    """Live ReadProcessMemory reader."""

    def __init__(self, process_handle: int) -> None:
        self._handle = process_handle
        self._kernel32 = ctypes.windll.kernel32

    @classmethod
    def for_pid(cls, pid: int) -> Win32MemoryReader:
        return cls(open_process_handle(pid))

    def close(self) -> None:
        close_process_handle(self._handle)
        self._handle = 0

    def __enter__(self) -> Win32MemoryReader:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def read_bytes(self, address: int, size: int) -> bytes:
        if size <= 0:
            raise MemoryReadError(f"Invalid read size: {size}")
        buffer = ctypes.create_string_buffer(size)
        bytes_read = ctypes.c_size_t(0)
        ok = self._kernel32.ReadProcessMemory(
            self._handle,
            ctypes.c_void_p(address),
            buffer,
            size,
            ctypes.byref(bytes_read),
        )
        if not ok or bytes_read.value != size:
            err = ctypes.get_last_error()
            raise MemoryReadError(
                f"ReadProcessMemory failed at 0x{address:X} size={size} (error {err})"
            )
        return buffer.raw


class MockMemoryReader(MemoryReader):
    """In-memory fake address space for unit tests."""

    def __init__(self, data: dict[int, bytes] | None = None) -> None:
        self._data: dict[int, bytes] = dict(data or {})

    def write_bytes(self, address: int, data: bytes) -> None:
        self._data[address] = bytes(data)

    def write_uint64(self, address: int, value: int) -> None:
        self.write_bytes(address, struct.pack("<Q", value & 0xFFFFFFFFFFFFFFFF))

    def write_int32(self, address: int, value: int) -> None:
        self.write_bytes(address, struct.pack("<i", value))

    def read_bytes(self, address: int, size: int) -> bytes:
        if address in self._data and len(self._data[address]) >= size:
            return self._data[address][:size]
        # Follow pointer storage: if exact chunk missing, return zeros (tests set explicitly)
        chunk = self._data.get(address, b"\x00" * size)
        if len(chunk) < size:
            chunk = chunk + b"\x00" * (size - len(chunk))
        return chunk[:size]

    def read_uint64(self, address: int) -> int:
        return struct.unpack("<Q", self.read_bytes(address, 8))[0]
