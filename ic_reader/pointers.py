"""Pointer chain resolution (Cheat Engine style, 64-bit)."""

from __future__ import annotations

import logging

from ic_reader.exceptions import InvalidPointerChainError
from ic_reader.memory import MemoryReader
from ic_reader.models import PointerChainDef, PointerStep, ValueType

logger = logging.getLogger(__name__)


def resolve_pointer_chain(
    reader: MemoryReader,
    module_base: int,
    chain: PointerChainDef,
    *,
    collect_steps: bool = False,
) -> tuple[int, list[PointerStep]]:
    """
    Resolve a pointer chain to a final address.

    Algorithm (matches common Cheat Engine exports):
      address = module_base + static_offset
      for each offset in chain.offsets:
          address = read_uint64(address + offset)
      return final address (value is read separately at that address)
    """
    steps: list[PointerStep] = []
    address = module_base + chain.static_offset

    if not reader.is_readable_address(address) and chain.static_offset != 0:
        raise InvalidPointerChainError(
            f"Invalid static address 0x{address:X} (module+0x{chain.static_offset:X})"
        )

    if collect_steps:
        steps.append(
            PointerStep(
                step_index=0,
                address_before=module_base,
                offset_applied=chain.static_offset,
                address_after=address,
                read_pointer=False,
                note="module_base + static_offset",
            )
        )

    if not chain.offsets:
        return address, steps

    for idx, offset in enumerate(chain.offsets):
        read_at = address + offset
        if not reader.is_readable_address(read_at):
            raise InvalidPointerChainError(
                f"Cannot read pointer at step {idx + 1}: 0x{read_at:X}"
            )
        before = address
        try:
            next_addr = reader.read_uint64(read_at)
        except Exception as exc:
            raise InvalidPointerChainError(
                f"Pointer read failed at step {idx + 1} (0x{read_at:X}): {exc}"
            ) from exc

        if next_addr == 0 or not reader.is_readable_address(next_addr):
            raise InvalidPointerChainError(
                f"Null/invalid pointer at step {idx + 1}: 0x{next_addr:X}"
            )

        if collect_steps:
            steps.append(
                PointerStep(
                    step_index=idx + 1,
                    address_before=before,
                    offset_applied=offset,
                    address_after=next_addr,
                    read_pointer=True,
                    note=f"deref [0x{read_at:X}] -> 0x{next_addr:X}",
                )
            )
        address = next_addr

    return address, steps


def read_value_at_chain(
    reader: MemoryReader,
    module_base: int,
    chain: PointerChainDef,
    value_type: ValueType,
    *,
    collect_steps: bool = False,
) -> tuple[int | float | str, int, list[PointerStep]]:
    """Resolve chain and read typed value at the final address."""
    final_addr, steps = resolve_pointer_chain(
        reader, module_base, chain, collect_steps=collect_steps
    )
    value = reader.read_typed(final_addr, value_type)
    return value, final_addr, steps
