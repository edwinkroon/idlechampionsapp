"""Rolling rates, gem estimation, and sample metrics for session stats."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ic_gamedata.log_parser import PartySnapshot

# Rates are normalized to a 15-minute period (kwartier).
RATE_PERIOD_SEC = 900.0
# Rolling window grows from 3 minutes up to 15 minutes as more samples are available.
ROLLING_MIN_WINDOW_SEC = 180.0  # 3 minutes — minimum before showing a rolling rate
ROLLING_MAX_WINDOW_SEC = 900.0  # 15 minutes — cap once enough history exists
MAX_SAMPLES_PER_PARTY = 720
DEFAULT_GEMS_PER_BOSS = 7.0
# Bosses typically every 5 areas; used when API gem counters stall before a rate is learned.
DEFAULT_GEMS_PER_AREA = DEFAULT_GEMS_PER_BOSS / 5.0
MIN_GEMS_PER_AREA = 0.01


def _initial_gems_per_area(party: PartySnapshot) -> float | None:
    if party.gems_this_reset is None or party.current_area is None or party.current_area <= 1:
        return None
    rate = party.gems_this_reset / party.current_area
    return rate if rate >= MIN_GEMS_PER_AREA else None


def _resolve_gems_per_area(
    gems_per_area: float | None,
    *,
    gems: int | None,
    area: int | None,
) -> float | None:
    """Prefer learned rate; fall back to gems/area or a default so estimates keep moving."""
    if gems_per_area is not None and gems_per_area >= MIN_GEMS_PER_AREA:
        return gems_per_area
    if gems is not None and gems > 0 and area is not None and area > 1:
        rate = gems / area
        if rate >= MIN_GEMS_PER_AREA:
            return rate
    if gems is not None and gems > 0:
        return DEFAULT_GEMS_PER_AREA
    return None


def _update_gem_rates(
    *,
    gems_per_boss: float | None,
    gems_per_area: float | None,
    anchor_gems: int | None,
    anchor_area: int | None,
    new_gems: int,
    new_area: int | None,
    prev_boss: int | None,
    new_boss: int | None,
) -> tuple[float | None, float | None]:
    updated_boss = gems_per_boss
    updated_area = gems_per_area

    if (
        anchor_gems is not None
        and anchor_area is not None
        and new_area is not None
        and new_gems > anchor_gems
        and new_area > anchor_area
    ):
        updated_area = (new_gems - anchor_gems) / (new_area - anchor_area)

    if (
        new_boss is not None
        and prev_boss is not None
        and new_boss > prev_boss
        and anchor_gems is not None
        and new_gems > anchor_gems
    ):
        delta_boss = new_boss - prev_boss
        if delta_boss > 0:
            updated_boss = (new_gems - anchor_gems) / delta_boss

    return updated_boss, updated_area


def _delta(current: int | float | None, baseline: int | float | None) -> float | None:
    if current is None or baseline is None:
        return None
    diff = float(current) - float(baseline)
    return diff if diff >= 0 else None


def _rate_per_period(delta: float | None, elapsed_sec: float) -> float | None:
    """Normalize a delta to RATE_PERIOD_SEC (per kwartier)."""
    if delta is None or elapsed_sec <= 0:
        return None
    return delta * RATE_PERIOD_SEC / elapsed_sec


@dataclass(frozen=True)
class _MetricSample:
    timestamp: float
    gems: int | None
    area: int | None
    gold: float | None
    boss_kills: int | None = None


def _effective_window_sec(usable: list[_MetricSample]) -> float | None:
    """
    Window length for rate calculation.

    Starts at 3 minutes when that much data exists, then grows with session
    length until capped at 15 minutes.
    """
    if len(usable) < 2:
        return None
    available = usable[-1].timestamp - usable[0].timestamp
    if available < ROLLING_MIN_WINDOW_SEC:
        return None
    return min(available, ROLLING_MAX_WINDOW_SEC)


def rolling_window_span(samples: list[_MetricSample]) -> float | None:
    """Actual time span used for the rolling rate (seconds), or None if warming up."""
    usable = samples
    window = _effective_window_sec(usable)
    if window is None:
        return None
    newest = usable[-1]
    cutoff = newest.timestamp - window
    oldest = usable[0]
    for sample in usable:
        if sample.timestamp >= cutoff:
            oldest = sample
            break
    span = newest.timestamp - oldest.timestamp
    return span if span >= ROLLING_MIN_WINDOW_SEC else None


def rolling_rate(
    samples: list[_MetricSample],
    *,
    field_name: str,
) -> float | None:
    """
    Gems/areas per kwartier over an adaptive rolling window (3 min → 15 min).

    Uses oldest sample within the effective window vs newest — stable for bursty
    boss-gem income while smoothing further as more history accumulates.
    """
    window = _effective_window_sec(samples)
    if window is None:
        return None

    newest = samples[-1]
    newest_val = getattr(newest, field_name)
    if newest_val is None:
        return None

    cutoff = newest.timestamp - window
    oldest = samples[0]
    for sample in samples:
        if sample.timestamp >= cutoff:
            oldest = sample
            break

    oldest_val = getattr(oldest, field_name)
    if oldest_val is None:
        return None

    span = newest.timestamp - oldest.timestamp
    if span < ROLLING_MIN_WINDOW_SEC:
        return None

    delta = float(newest_val) - float(oldest_val)
    if delta < 0:
        return None
    return delta * RATE_PERIOD_SEC / span


def _estimate_gems_from_area(
    *,
    api_gems: int | None,
    anchor_gems: int | None,
    anchor_area: int | None,
    current_area: int | None,
    gems_per_area: float | None,
) -> int | None:
    if (
        anchor_gems is None
        or anchor_area is None
        or current_area is None
        or current_area <= anchor_area
        or gems_per_area is None
    ):
        return api_gems
    estimated = int(round(anchor_gems + (current_area - anchor_area) * gems_per_area))
    if api_gems is None:
        return estimated
    return max(api_gems, estimated)


def _extrapolate_gems(
    previous: PartySnapshot,
    current: PartySnapshot,
    *,
    gems_per_boss: float | None,
    gems_per_area: float | None,
    anchor_gems: int | None,
    anchor_area: int | None,
) -> tuple[int | None, float | None, float | None, int | None, int | None, bool]:
    """
    Return (effective_gems, gems_per_boss, gems_per_area, anchor_gems, anchor_area, is_estimated).

    The game API often updates current_area live but only syncs this_reset_gems_earned
    periodically. Estimate live gems from area progress using a learned gems/area rate.
    """
    api_gems = current.gems_this_reset
    prev_effective = previous.gems_this_reset
    prev_area = previous.current_area
    curr_area = current.current_area
    boss = current.boss_kills_this_reset
    prev_boss = previous.boss_kills_this_reset

    if api_gems is not None and prev_effective is not None and api_gems > prev_effective:
        gems_per_boss, gems_per_area = _update_gem_rates(
            gems_per_boss=gems_per_boss,
            gems_per_area=gems_per_area,
            anchor_gems=anchor_gems,
            anchor_area=anchor_area,
            new_gems=api_gems,
            new_area=curr_area,
            prev_boss=prev_boss,
            new_boss=boss,
        )
        return api_gems, gems_per_boss, gems_per_area, api_gems, curr_area, False

    estimated = api_gems if api_gems is not None else prev_effective
    is_estimated = False

    # Prefer the highest known gem count as the estimation floor (estimated or API).
    floor_gems = estimated
    if prev_effective is not None and (floor_gems is None or prev_effective > floor_gems):
        floor_gems = prev_effective

    rate = _resolve_gems_per_area(
        gems_per_area,
        gems=anchor_gems if anchor_gems is not None else api_gems,
        area=anchor_area if anchor_area is not None else curr_area,
    )
    if rate is not None and gems_per_area is None:
        gems_per_area = rate

    if (
        boss is not None
        and prev_boss is not None
        and boss > prev_boss
        and floor_gems is not None
    ):
        delta_boss = boss - prev_boss
        boss_rate = gems_per_boss if gems_per_boss is not None else DEFAULT_GEMS_PER_BOSS
        boss_est = int(round(floor_gems + delta_boss * boss_rate))
        if estimated is None or boss_est > estimated:
            estimated = boss_est
            is_estimated = True

    # Anchor-based estimate — stable even when memory area and API area diverge.
    area_est = _estimate_gems_from_area(
        api_gems=api_gems,
        anchor_gems=anchor_gems,
        anchor_area=anchor_area,
        current_area=curr_area,
        gems_per_area=rate,
    )
    if area_est is not None and (estimated is None or area_est > estimated):
        if api_gems is None or area_est > api_gems:
            estimated = area_est
            is_estimated = True

    # Never decrease below a previously shown estimate while the API counter is stalled,
    # but only within the same run (area still advancing / not after a reset drop).
    same_run = (
        curr_area is None
        or prev_area is None
        or curr_area + 2 >= prev_area
    )
    if (
        same_run
        and floor_gems is not None
        and (api_gems is None or api_gems <= floor_gems)
        and (estimated is None or floor_gems > estimated)
        and (api_gems is None or api_gems > 0 or floor_gems == 0)
    ):
        # If API reports 0 gems while we still think we have thousands, trust the API
        # only when area also dropped (handled by reset); otherwise keep floor.
        if api_gems is not None and api_gems == 0 and floor_gems > 0:
            pass
        else:
            estimated = floor_gems
            if api_gems is None or floor_gems > api_gems:
                is_estimated = True

    if (
        estimated is not None
        and prev_effective is not None
        and curr_area is not None
        and prev_area is not None
        and curr_area > prev_area
        and rate is not None
        and (api_gems is None or api_gems <= prev_effective)
    ):
        step_est = int(round(prev_effective + (curr_area - prev_area) * rate))
        if step_est > estimated:
            estimated = step_est
            is_estimated = True

    if estimated is not None and api_gems is not None:
        estimated = max(estimated, api_gems)
        if estimated > api_gems:
            is_estimated = True
        elif estimated == api_gems:
            is_estimated = False

    return estimated, gems_per_boss, gems_per_area, anchor_gems, anchor_area, is_estimated


def _party_with_effective_gems(party: PartySnapshot, *, gems: int | None) -> PartySnapshot:
    if gems is None or gems == party.gems_this_reset:
        return party
    return replace(party, gems_this_reset=gems)
