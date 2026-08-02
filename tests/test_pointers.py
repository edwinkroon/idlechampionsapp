"""Unit tests for pointer chain resolution (mock memory)."""

from __future__ import annotations

import unittest

from ic_reader.exceptions import InvalidPointerChainError
from ic_reader.memory import MockMemoryReader
from ic_reader.models import PointerChainDef, ValueType
from ic_reader.pointers import read_value_at_chain, resolve_pointer_chain


class TestPointerChain(unittest.TestCase):
    def setUp(self) -> None:
        self.reader = MockMemoryReader()
        self.module_base = 0x10000000

    def test_single_hop_int32(self) -> None:
        """module+static -> ptr -> int32 at final."""
        static = 0x1000
        ptr_storage = self.module_base + static
        target = 0x20000000
        value_addr = target
        self.reader.write_uint64(ptr_storage, target)
        self.reader.write_int32(value_addr, 42)

        chain = PointerChainDef(
            module="GameAssembly.dll",
            static_offset=static,
            offsets=(0x0,),
        )
        value, final, steps = read_value_at_chain(
            self.reader,
            self.module_base,
            chain,
            ValueType.INT32,
            collect_steps=True,
        )
        self.assertEqual(42, value)
        self.assertEqual(value_addr, final)
        self.assertGreaterEqual(len(steps), 1)

    def test_multi_hop_chain(self) -> None:
        static = 0x2000
        level1 = self.module_base + static
        obj_a = 0x30000000
        obj_b = 0x40000000
        self.reader.write_uint64(level1 + 0x0, obj_a)
        self.reader.write_uint64(obj_a + 0x18, obj_b)
        self.reader.write_int32(obj_b, 7)

        chain = PointerChainDef(
            module="GameAssembly.dll",
            static_offset=static,
            offsets=(0x0, 0x18),
        )
        value, final, _ = read_value_at_chain(
            self.reader,
            self.module_base,
            chain,
            ValueType.INT32,
        )
        self.assertEqual(7, value)
        self.assertEqual(obj_b, final)

    def test_null_pointer_raises(self) -> None:
        static = 0x3000
        self.reader.write_uint64(self.module_base + static, 0)
        chain = PointerChainDef(
            module="GameAssembly.dll",
            static_offset=static,
            offsets=(0x10,),
        )
        with self.assertRaises(InvalidPointerChainError):
            resolve_pointer_chain(self.reader, self.module_base, chain)

    def test_static_only_address(self) -> None:
        addr = self.module_base + 0x5000
        self.reader.write_int32(addr, 99)
        chain = PointerChainDef(
            module="GameAssembly.dll",
            static_offset=0x5000,
            offsets=(),
        )
        final, _ = resolve_pointer_chain(self.reader, self.module_base, chain)
        self.assertEqual(addr, final)
        self.assertEqual(99, self.reader.read_int32(final))


if __name__ == "__main__":
    unittest.main()
