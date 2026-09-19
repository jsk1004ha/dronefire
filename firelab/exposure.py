"""Protected-location exposure analysis with explicit censoring.

This module evaluates only channels present in imported solver or measurement
records.  Missing hazards remain incomplete, and threshold times are reported
as observation intervals rather than interpolated pseudo-measurements.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
import math
from typing import Any

import numpy as np


def analyze_exposure_run(
    record: Mapping[str, Any], criteria: Mapping[str, Mapping[str, Any]], tau_s: float
) -> dict[str, Any]:
    """Evaluate preregistered protected-location criteria for one record."""

    row = _validate_record(record)
    tau = _finite(tau_s, "tau_s", positive=True)
    if not criteria:
        raise ValueError("criteria must not be empty")
    outputs: dict[str, Any] = {}
    for channel, raw in criteria.items():
        cfg = _criterion(raw, channel)
        if channel not in row["channels"]:
            outputs[channel] = {
                "status": "incomplete_missing_channel",
                "event": None,
                "interval_s": None,
                "criterion": cfg,
            }
            continue
        if row["run_status"] != "completed":
            outputs[channel] = {
                "status": "incomplete_run",
                "event": None,
                "interval_s": None,
                "criterion": cfg,
            }
            continue
        outputs[channel] = _threshold_interval(
            row["time_s"], row["channels"][channel], cfg, tau
        )
        outputs[channel]["criterion"] = cfg

    heat = None
    if "heat_flux_kW_m2" in row["channels"] and row["run_status"] == "completed":
        heat = integrate_exposure(
            row["time_s"], row["channels"]["heat_flux_kW_m2"], tau
        )
    missing = [channel for channel, result in outputs.items() if result["status"].startswith("incomplete")]
    return {
        "case_id": row["case_id"],
        "block_id": row["block_id"],
        "condition_id": row["condition_id"],
        "location_id": row["location_id"],
        "status": "incomplete" if missing else "complete",
        "missing_channels": missing,
        "channels": outputs,
        "integrated_heat_exposure_J_m2": heat,
        "provenance": dict(row["provenance"]),
        "interpretation": "Threshold time is an exposure endpoint, not human survival time.",
    }


def integrate_exposure(
    time_s: Sequence[float], values_kW_m2: Sequence[float], tau_s: float
) -> float | None:
    """Integrate to ``tau_s`` only when the full interval was observed."""

    time = _array(time_s, "time_s")
    values = _array(values_kW_m2, "values_kW_m2")
    tau = _finite(tau_s, "tau_s", positive=True)
    if len(time) != len(values) or len(time) < 2 or np.any(np.diff(time) <= 0):
        raise ValueError("time/value arrays must match and time must strictly increase")
    if time[0] > 0 or time[-1] < tau:
        return None
    knots = np.unique(np.concatenate((time[(time >= 0) & (time <= tau)], [0.0, tau])))
    samples = np.interp(knots, time, values)
    return float(np.trapezoid(samples, knots) * 1000.0)


def summarize_exposure(
    records: Iterable[Mapping[str, Any]],
    criteria: Mapping[str, Mapping[str, Any]],
    tau_s: float,
    *,
    control_id: str = "C0",
    bootstrap_samples: int = 500,
    seed: int = 42,
) -> dict[str, Any]:
    """Summarize interval-censored threshold times and paired RMST bounds."""

    if bootstrap_samples < 1:
        raise ValueError("bootstrap_samples must be positive")
    tau = _finite(tau_s, "tau_s", positive=True)
    control = _nonempty(control_id, "control_id")
    runs = [analyze_exposure_run(row, criteria, tau) for row in records]
    if not runs:
        raise ValueError("records must not be empty")
    groups: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for run in runs:
        groups[run["location_id"]][run["condition_id"]].append(run)

    locations: dict[str, Any] = {}
    comparisons: list[dict[str, Any]] = []
    rng = np.random.default_rng(seed)
    for location_id, location_groups in sorted(groups.items()):
        summaries: dict[str, Any] = {}
        for channel in criteria:
            summaries[channel] = {}
            for condition, items in sorted(location_groups.items()):
                bounds = [_rmst_bounds(item["channels"][channel], tau) for item in items]
                eligible = [value for value in bounds if value is not None]
                by_block = {}
                for item, bound in zip(items, bounds, strict=True):
                    if bound is None:
                        continue
                    if item["block_id"] in by_block:
                        raise ValueError(
                            f"duplicate condition/location/block: {condition}/{location_id}/{item['block_id']}"
                        )
                    by_block[item["block_id"]] = bound
                reps = _bootstrap_bounds(list(by_block.values()), bootstrap_samples, rng)
                summaries[channel][condition] = {
                    "total_runs": len(items),
                    "eligible_runs": len(eligible),
                    "event_count": sum(item["channels"][channel].get("event") is True for item in items),
                    "right_censored_count": sum(item["channels"][channel]["status"] == "right_censored" for item in items),
                    "incomplete_count": sum(item["channels"][channel]["status"].startswith("incomplete") for item in items),
                    "rmst_interval_s": _mean_interval(eligible),
                    "rmst_lower_ci95_s": _ci([value[0] for value in reps]),
                    "rmst_upper_ci95_s": _ci([value[1] for value in reps]),
                    "by_block": by_block,
                }
            if control in summaries[channel]:
                for condition in sorted(summaries[channel]):
                    if condition == control:
                        continue
                    comparison = _paired_difference(
                        channel, condition, summaries[channel][condition]["by_block"],
                        control, summaries[channel][control]["by_block"],
                        bootstrap_samples, rng,
                    )
                    comparison["location_id"] = location_id
                    comparisons.append(comparison)
        locations[location_id] = summaries
    # Remove internal block maps from public summaries after paired calculations.
    for location_summary in locations.values():
        for channel_groups in location_summary.values():
            for summary in channel_groups.values():
                summary.pop("by_block", None)
    single_location_groups = next(iter(locations.values())) if len(locations) == 1 else None
    return {
        "schema_version": "1.0",
        "tau_s": tau,
        "runs": runs,
        "locations": locations,
        "groups": single_location_groups,
        "paired_rmst_differences": comparisons,
        "censoring": "interval bounds retained; no midpoint imputation",
        "missing_channel_policy": "incomplete_not_zero",
        "interpretation": "Positive method-minus-control time means later exposure-limit crossing within tau; it is not survival time.",
    }


def _threshold_interval(
    time: np.ndarray, values: np.ndarray, cfg: Mapping[str, Any], tau: float
) -> dict[str, Any]:
    observed_end = min(float(time[-1]), tau)
    if time[0] > 0:
        return {"status": "incomplete_initial_interval", "event": None, "interval_s": None}
    test = np.greater_equal if cfg["direction"] == "above" else np.less_equal
    hit = test(values, cfg["limit"])
    eligible = np.flatnonzero((time <= tau) & hit)
    if len(eligible):
        index = int(eligible[0])
        if index == 0:
            interval = [0.0, 0.0]
        else:
            interval = [float(time[index - 1]), float(time[index])]
        return {
            "status": "observed_interval",
            "event": True,
            "interval_s": interval,
            "observed_through_s": observed_end,
        }
    if time[-1] >= tau:
        return {
            "status": "right_censored",
            "event": False,
            "interval_s": [tau, None],
            "observed_through_s": tau,
        }
    return {
        "status": "incomplete_followup",
        "event": None,
        "interval_s": [float(time[-1]), None],
        "observed_through_s": float(time[-1]),
    }


def _rmst_bounds(result: Mapping[str, Any], tau: float) -> tuple[float, float] | None:
    if result["status"] == "observed_interval":
        lower, upper = result["interval_s"]
        return min(float(lower), tau), min(float(upper), tau)
    if result["status"] == "right_censored":
        return tau, tau
    return None


def _paired_difference(
    channel: str,
    method_id: str,
    method: Mapping[str, tuple[float, float]],
    control_id: str,
    control: Mapping[str, tuple[float, float]],
    samples: int,
    rng: np.random.Generator,
) -> dict[str, Any]:
    common = sorted(set(method) & set(control))
    if not common:
        return {
            "channel": channel, "method": method_id, "control": control_id,
            "eligible": False, "reason": "no_common_blocks", "common_blocks": 0,
            "difference_interval_s": None,
        }
    values = [
        (method[block][0] - control[block][1], method[block][1] - control[block][0])
        for block in common
    ]
    reps = []
    for _ in range(samples):
        selected = rng.integers(0, len(values), size=len(values))
        reps.append(tuple(float(np.mean([values[i][side] for i in selected])) for side in (0, 1)))
    return {
        "channel": channel,
        "method": method_id,
        "control": control_id,
        "eligible": True,
        "reason": None,
        "common_blocks": len(common),
        "difference_interval_s": _mean_interval(values),
        "difference_lower_ci95_s": _ci([value[0] for value in reps]),
        "difference_upper_ci95_s": _ci([value[1] for value in reps]),
    }


def _bootstrap_bounds(
    values: list[tuple[float, float]], samples: int, rng: np.random.Generator
) -> list[tuple[float, float]]:
    if not values:
        return []
    output = []
    for _ in range(samples):
        chosen = rng.integers(0, len(values), size=len(values))
        output.append(tuple(float(np.mean([values[index][side] for index in chosen])) for side in (0, 1)))
    return output


def _mean_interval(values: Sequence[tuple[float, float]]) -> list[float] | None:
    if not values:
        return None
    return [float(np.mean([value[0] for value in values])), float(np.mean([value[1] for value in values]))]


def _validate_record(record: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise TypeError("record must be a mapping")
    row = dict(record)
    for field in ("case_id", "block_id", "condition_id", "location_id", "run_status"):
        row[field] = _nonempty(row.get(field), field)
    if row["run_status"] not in {"completed", "incomplete", "aborted", "numerical_failure", "solver_failure"}:
        raise ValueError("run_status is invalid")
    provenance = row.get("provenance")
    if not isinstance(provenance, Mapping) or not provenance:
        raise ValueError("provenance must be a non-empty mapping")
    if not isinstance(provenance.get("source"), str) or not provenance["source"].strip():
        raise ValueError("provenance.source must be a non-empty string")
    time = _array(row.get("time_s"), "time_s")
    if len(time) < 2 or time[0] < 0 or np.any(np.diff(time) <= 0):
        raise ValueError("time_s must be nonnegative and strictly increasing")
    channels = row.get("channels")
    if not isinstance(channels, Mapping):
        raise ValueError("channels must be a mapping")
    clean = {}
    for name, values in channels.items():
        clean[name] = _array(values, f"channels.{name}")
        if len(clean[name]) != len(time):
            raise ValueError(f"channels.{name} length must match time_s")
    row["time_s"] = time
    row["channels"] = clean
    return row


def _criterion(value: Mapping[str, Any], channel: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"criterion {channel} must be a mapping")
    direction = value.get("direction")
    if direction not in {"above", "below"}:
        raise ValueError(f"criterion {channel} direction must be above or below")
    source = value.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError(f"criterion {channel} requires source")
    return {
        "limit": _finite(value.get("limit"), f"criterion {channel} limit"),
        "direction": direction,
        "source": source.strip(),
    }


def _array(value: Any, name: str) -> np.ndarray:
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{name} must be a numeric sequence")
    try:
        result = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} must be a numeric sequence") from exc
    if result.ndim != 1 or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be a finite one-dimensional sequence")
    return result


def _finite(value: Any, name: str, *, positive: bool = False) -> float:
    if type(value) is bool or not isinstance(value, (int, float, np.integer, np.floating)):
        raise TypeError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if positive and result <= 0:
        raise ValueError(f"{name} must be > 0")
    return result


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _ci(values: Sequence[float]) -> list[float] | None:
    if not values:
        return None
    result = np.quantile(np.asarray(values, dtype=float), [0.025, 0.975])
    return [float(result[0]), float(result[1])]
