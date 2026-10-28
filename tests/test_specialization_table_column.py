"""Tests for Specialisatie(s) readable-table column labels and contract."""

from __future__ import annotations

import unittest

from ic_gamedata.formation_ai_advice.labels import (
    ADVICE_TABLE_HEADER_EXAMPLE,
    format_specializations_table_cell,
    specialization_choice_display,
)
from ic_gamedata.formation_ai_advice.reply_contract import (
    build_static_answer_contract,
    reply_format_pointer_nl,
)


class SpecializationChoiceDisplayTests(unittest.TestCase):
    def test_new_advice(self) -> None:
        self.assertEqual(
            specialization_choice_display(
                "War Domain",
                advised_option_id=29,
                current_option_id=30,
            ),
            "War Domain (advies)",
        )

    def test_active_same_as_advice(self) -> None:
        self.assertEqual(
            specialization_choice_display(
                "War Domain",
                advised_option_id=29,
                current_option_id=29,
            ),
            "War Domain (actief)",
        )

    def test_keep_current_without_new_advice(self) -> None:
        self.assertEqual(
            specialization_choice_display(
                "Life Domain",
                current_option_id=30,
            ),
            "Life Domain (behouden)",
        )

    def test_none_selected_none_advised(self) -> None:
        self.assertEqual(
            specialization_choice_display(None),
            "Nog te kiezen — geen nieuw advies",
        )

    def test_advised_not_unlocked_with_level(self) -> None:
        self.assertEqual(
            specialization_choice_display(
                "Secret Lord of Luskan",
                advised_option_id=58,
                selection_status="not_unlocked",
                required_level=150,
            ),
            "Secret Lord of Luskan (advies vanaf lvl 150)",
        )

    def test_advised_not_unlocked_without_level(self) -> None:
        self.assertEqual(
            specialization_choice_display(
                "Secret Lord of Luskan",
                advised_option_id=58,
                selection_status="not_unlocked",
            ),
            "Secret Lord of Luskan (advies na ontgrendeling)",
        )

    def test_unresolvable_name_marked_unknown(self) -> None:
        self.assertEqual(
            specialization_choice_display(
                None,
                advised_option_id=99,
            ),
            "Onbekend (advies)",
        )
        self.assertEqual(
            specialization_choice_display(
                "  ",
                current_option_id=12,
            ),
            "Onbekend (behouden)",
        )

    def test_multi_group_cell_uses_keuze_prefix(self) -> None:
        cell = format_specializations_table_cell(
            [
                specialization_choice_display(
                    "War Domain",
                    advised_option_id=29,
                    current_option_id=30,
                ),
                specialization_choice_display(
                    "Life Domain",
                    current_option_id=975,
                ),
            ]
        )
        self.assertEqual(
            cell,
            "Keuze 1: War Domain (advies); Keuze 2: Life Domain (behouden)",
        )

    def test_single_group_omits_keuze_prefix(self) -> None:
        cell = format_specializations_table_cell(
            [specialization_choice_display("War Domain", advised_option_id=29)]
        )
        self.assertEqual(cell, "War Domain (advies)")
        self.assertNotIn("Keuze", cell)


class AnswerContractSpecializationColumnTests(unittest.TestCase):
    def test_display_vs_import_has_three_columns(self) -> None:
        contract = build_static_answer_contract()
        display = contract["display_vs_import"]
        self.assertEqual(
            display["table_columns"],
            ["Plek", "Champion", "Specialisatie(s)"],
        )
        self.assertIn("specialization_cell", display)
        self.assertEqual(
            display["specialization_status_labels"]["new_advice"],
            "Naam (advies)",
        )
        self.assertEqual(
            display["specialization_status_labels"]["same_as_current"],
            "Naam (actief)",
        )
        self.assertEqual(
            display["specialization_status_labels"]["keep_current"],
            "Naam (behouden)",
        )
        self.assertIn("ADVICE_REQUEST", display["current_selection_source"])
        self.assertIn("geen specialisatienamen", display["placements_exclude"])

    def test_reply_pointer_mentions_column_without_rule_dump(self) -> None:
        pointer = reply_format_pointer_nl()
        self.assertIn("| Plek | Champion | Specialisatie(s) |", pointer)
        self.assertIn(ADVICE_TABLE_HEADER_EXAMPLE.splitlines()[0], pointer)
        self.assertIn("display_vs_import", pointer)
        # Hot path stays a short pointer; filling rules live on BASE contract.
        self.assertLessEqual(len(pointer.encode("utf-8")), 900)


if __name__ == "__main__":
    unittest.main()
