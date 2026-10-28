"""Shared specialization advice rendering for Coach / Specs tabs."""

from __future__ import annotations

from typing import Any, Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from ic_ui import theme as ui_theme
from ic_ui.widgets.advisor_widgets import (
    advisor_card,
    advisor_card_layout,
    advisor_lbl,
    advisor_section,
    advisor_status_dot,
)


def spec_dot_color(kind: str) -> str:
    return {
        "warn": ui_theme.WARN,
        "spec_match": ui_theme.SUCCESS,
        "spec_pending": ui_theme.TEXT_BODY,
        "spec_mismatch": ui_theme.FEAT_MISSING,
        "muted": ui_theme.TEXT_MUTED,
    }.get(kind, ui_theme.TEXT_MUTED)


def spec_label_kind(status: str | None) -> str:
    return {
        "match": "spec_match",
        "matches": "spec_match",
        "pending": "spec_pending",
        "open_tier": "spec_pending",
        "mismatch": "spec_mismatch",
    }.get(status or "", "spec_pending")


def add_spec_dot_line(layout: QVBoxLayout, text: str, *, kind: str) -> None:
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    row.addWidget(
        advisor_status_dot(spec_dot_color(kind)),
        alignment=Qt.AlignmentFlag.AlignVCenter,
    )
    row.addWidget(advisor_lbl(text, kind=kind), stretch=1)
    layout.addLayout(row)


def spec_summary_lines(
    seats,
    *,
    statuses: set[str] | None = None,
) -> list[tuple[str, str]]:
    try:
        from ic_gamedata.party_advisor_specializations import spec_summary_line
    except ImportError:
        spec_summary_line = None

    lines: list[tuple[str, str]] = []
    for seat in sorted(seats, key=lambda item: item.seat):
        if not seat.best_spec:
            continue
        status = getattr(seat, "spec_status", None) or "pending"
        if statuses is not None and status not in statuses:
            continue
        if spec_summary_line is not None:
            text = spec_summary_line(
                seat.hero_name,
                recommended=seat.best_spec,
                current_labels=seat.current_specs,
                status=status,
                is_bud=seat.is_bud,
            )
        else:
            name = seat.hero_name
            if seat.is_bud:
                name += " (BUD)"
            current = ", ".join(seat.current_specs) if seat.current_specs else None
            if status == "mismatch" and current:
                text = f"{name}: {current} → {seat.best_spec}"
            else:
                text = f"{name}: {seat.best_spec}"
        lines.append((text, spec_label_kind(status)))
    return lines


def render_pending_specializations(
    layout: QVBoxLayout,
    pending_items,
    *,
    payload: dict[str, Any] | None = None,
) -> None:
    """Render open in-game specialization dialog cards."""
    if not pending_items:
        card = advisor_card(compact=True)
        lyt = advisor_card_layout(card, compact=True)
        lyt.addWidget(
            advisor_lbl(
                "No open specialization choices for the active party.",
                kind="muted",
            )
        )
        layout.addWidget(card)
        return

    try:
        from ic_gamedata.specialization_advice_text import (
            human_specialization_reason,
        )
        from ic_gamedata.specializations import _active_adventure_context
    except ImportError:
        human_specialization_reason = None
        _active_adventure_context = None

    context = (
        _active_adventure_context(payload or {}) if _active_adventure_context else {}
    )
    for item in pending_items:
        highlight = item.desired_option_index is not None
        card = advisor_card(highlight=highlight)
        lyt = advisor_card_layout(card)
        seat_str = f"slot {item.seat}" if item.seat is not None else "unknown seat"
        lyt.addWidget(advisor_lbl(f"{item.hero_name} · {seat_str}", kind="subtitle"))
        options = " / ".join(option.name for option in item.options)
        if item.desired_option_index is not None:
            chosen = item.options[item.desired_option_index].name
            lyt.addWidget(advisor_lbl(f"Advice: {chosen}", kind="spec_pending"))
        elif item.reason == "insufficient data":
            lyt.addWidget(
                advisor_lbl("Advice: unknown — not enough data", kind="spec_pending")
            )
        else:
            lyt.addWidget(
                advisor_lbl("Advice: no fixed choice yet", kind="spec_pending")
            )
        try:
            from ic_gamedata.specialization_advisor_model import (
                advisor_model_for_hero,
                advisor_model_line_kind,
                format_advisor_model_lines,
            )

            model = advisor_model_for_hero(item.hero_id)
        except ImportError:
            model = None
        if model is not None:
            for line in format_advisor_model_lines(model):
                lyt.addWidget(
                    advisor_lbl(line, kind=advisor_model_line_kind(model, line))
                )
        if human_specialization_reason is not None:
            lyt.addWidget(
                advisor_lbl(
                    f"Why: {human_specialization_reason(item, context)}",
                    kind="body",
                )
            )
        elif item.rationale:
            lyt.addWidget(advisor_lbl(f"Why: {item.rationale}", kind="body"))
        lyt.addWidget(advisor_lbl(f"Open options: {options}", kind="muted"))
        meta_parts: list[str] = []
        if item.data_source_version:
            meta_parts.append(f"dataset {item.data_source_version}")
        if item.rule_source_type:
            meta_parts.append(item.rule_source_type)
        if item.confidence:
            meta_parts.append(f"confidence {item.confidence}/5")
        if meta_parts:
            lyt.addWidget(advisor_lbl(" · ".join(meta_parts), kind="muted"))
        layout.addWidget(card)


def _formation_hero_ids(report) -> set[int]:
    formation_ids = {
        seat.hero_id
        for seat in (report.seat_report.seats if report.seat_report else ())
        if seat.hero_id
    }
    if formation_ids:
        return formation_ids
    return {
        ins.hero_id
        for ins in (report.specialization_insights or ())
        if getattr(ins, "status", None) != "bench_suggestion"
        and getattr(ins, "seat", None) is not None
    }


def _formation_pending(pending_items, formation_ids: set[int]):
    return [
        item
        for item in (pending_items or ())
        if not formation_ids or item.hero_id in formation_ids
    ]


def collect_mismatch_lines(
    report,
    *,
    max_lines: int | None = None,
) -> list[tuple[str, str]]:
    """Mismatch / open-tier / pending-spec lines from seats + insights."""
    formation_ids = _formation_hero_ids(report)
    insights = tuple(
        ins
        for ins in (report.specialization_insights or ())
        if getattr(ins, "status", None) != "bench_suggestion"
        and (not formation_ids or ins.hero_id in formation_ids)
    )
    actionable = {"mismatch", "open_tier"}
    insight_action_ids = {
        ins.hero_id for ins in insights if getattr(ins, "status", None) in actionable
    }

    formation_seats = []
    if report.seat_report and report.seat_report.seats:
        formation_seats = [
            seat
            for seat in report.seat_report.seats
            if not formation_ids or seat.hero_id in formation_ids
        ]

    lines: list[tuple[str, str]] = []
    for insight in insights:
        if getattr(insight, "status", None) not in actionable:
            continue
        seat_str = f"slot {insight.seat}" if insight.seat is not None else "bench"
        headline = getattr(insight, "headline", None) or insight.hero_name
        detail = getattr(insight, "detail", None) or ""
        text = f"{headline} · {seat_str}"
        if detail:
            text = f"{text}: {detail}"
        lines.append((text, spec_label_kind(insight.status)))

    seat_action_seats = [
        s for s in formation_seats if s.hero_id not in insight_action_ids
    ]
    lines.extend(spec_summary_lines(seat_action_seats, statuses={"mismatch"}))
    lines.extend(spec_summary_lines(seat_action_seats, statuses={"pending"}))
    if max_lines is not None:
        return lines[:max_lines]
    return lines


def render_mismatch_summary(
    layout: QVBoxLayout,
    report,
    *,
    section_title: str | None = "Action needed",
    max_lines: int | None = None,
) -> bool:
    """Compact mismatch / open-tier list from seats + insights. Returns True if rendered."""
    lines = collect_mismatch_lines(report, max_lines=max_lines)
    if not lines:
        return False
    if section_title:
        advisor_section(layout, section_title)
    card = advisor_card(compact=True)
    lyt = advisor_card_layout(card, compact=True)
    for line, kind in lines:
        add_spec_dot_line(lyt, line, kind=kind)
    layout.addWidget(card)
    return True


def render_compact_specializations_section(
    layout: QVBoxLayout,
    report,
    pending_items: Iterable[Any] | None,
    *,
    payload: dict[str, Any] | None = None,
) -> None:
    """Coach-tab Specializations block: open choices + short mismatch list."""
    formation_ids = _formation_hero_ids(report)
    formation_pending = _formation_pending(pending_items, formation_ids)
    mismatch_lines = collect_mismatch_lines(report, max_lines=12)
    advisor_section(layout, "Specializations")
    if not formation_pending and not mismatch_lines:
        card = advisor_card(compact=True)
        lyt = advisor_card_layout(card, compact=True)
        lyt.addWidget(
            advisor_lbl(
                "No open specialization choices; nothing flagged as mismatch.",
                kind="muted",
            )
        )
        layout.addWidget(card)
        return

    if formation_pending:
        render_pending_specializations(
            layout,
            formation_pending,
            payload=payload,
        )
    if mismatch_lines:
        advisor_section(layout, "Needs attention")
        card = advisor_card(compact=True)
        lyt = advisor_card_layout(card, compact=True)
        for line, kind in mismatch_lines:
            add_spec_dot_line(lyt, line, kind=kind)
        layout.addWidget(card)
