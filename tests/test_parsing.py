"""Tests for ic_gamedata.parsing."""

from __future__ import annotations

import unittest

from ic_gamedata.parsing import parse_int, parse_number


class TestParsing(unittest.TestCase):
    def test_parse_number_rejects_bool(self) -> None:
        self.assertIsNone(parse_number(True))
        self.assertIsNone(parse_number(False))

    def test_parse_number_accepts_numeric_types(self) -> None:
        self.assertEqual(parse_number(42), 42.0)
        self.assertEqual(parse_number(3.5), 3.5)

    def test_parse_number_parses_strings(self) -> None:
        self.assertEqual(parse_number("123.5"), 123.5)
        self.assertEqual(parse_number("  7  "), 7.0)
        self.assertIsNone(parse_number(""))
        self.assertIsNone(parse_number("abc"))

    def test_parse_int_truncates_floats(self) -> None:
        self.assertEqual(parse_int(12.9), 12)
        self.assertEqual(parse_int("99.0"), 99)

    def test_parse_int_rejects_bool_and_none(self) -> None:
        self.assertIsNone(parse_int(None))
        self.assertIsNone(parse_int(True))


if __name__ == "__main__":
    unittest.main()
