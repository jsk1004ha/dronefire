"""Preregistered analysis for solver and measured fire-suppression records.

The functions in this module consume observed time series.  They never infer a
suppression response from the transport-only models in :mod:`firelab.physics`.
Every record must carry provenance and all time-domain calculations are limited
to the observed interval; interpolation is allowed only between observations.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from itertools import combinations
import math
from typing import Any

import numpy as np

from .analysis import analyze_outcomes, compute_synergy


def analyze_extinction_run(
    record: Mapping[str, Any], criterion: Mapping[str, Any]
) -> dict[str, Any]:
    """Evaluate sustained HRR extinction and post-intervention reignition.

    ``criterion`` must preregister ``hrr_threshold_kW``, ``sustain_s``,
    ``reignition_threshold_kW`` and ``reignition_followup_s``.  Extinction is
    recorded at the first observed sample beginning a continuously compliant
    span of at least ``sustain_s``.  This conservative rule avoids claiming an
    event between coarse samples.  Reignition is ``unknown`` when follow-up is
    shorter than the preregistered window.
    """

    row = _validate_series_record(record, required_channels=("hrr_kW",))
    cfg = _extinction_criterion(criterion)
    if row["run_status"] != "completed":
        return _incomplete_extinction(row, f"run_status:{row['run_status']}")

    time = row["time_s"]
    hrr = row["channels"]["hrr_kW"]
    extinction_time = _sustained_below(time, hrr, cfg["hrr_threshold_kW"], cfg["sustain_s"])
    if extinction_time is None:
        extinction = {
            "status": "right_censored",
            "event": False,
            "time_s": None,
            "observed_through_s": float(time[-1]),
        }
        reignition = {"status": "not_applicable", "event": None, "time_s": None}
    else:
        extinction = {
            "status": "observed",
            "event": True,
            "time_s": extinction_time,
            "observed_through_s": float(time[-1]),
        }
        start = max(extinction_time, row.get("intervention_end_s", extinction_time))
        window_end = start + cfg["reignition_followup_s"]
        observed = np.flatnonzero((time >= start) & (time <= min(window_end, time[-1])))
        hits = observed[hrr[observed] >= cfg["reignition_threshold_kW"]]
        if len(hits):
            reignition = {
                "status": "observed",
                "event": True,
                "time_s": float(time[int(hits[0])]),
                "window_start_s": start,
                "required_window_end_s": window_end,
            }
        elif time[-1] < window_end:
            reignition = {
                "status": "unknown_insufficient_followup",
                "event": None,
                "time_s": None,
                "window_start_s": start,
                "required_window_end_s": window_end,
                "observed_through_s": float(time[-1]),
            }
        else:
            reignition = {
                "status": "not_observed",
                "event": False,
                "time_s": None,
                "window_start_s": start,
                "required_window_end_s": window_end,
            }

    return {
        "case_id": row["case_id"],
        "block_id": row["block_id"],
        "condition_id": row["condition_id"],
        "status": "complete",
        "criterion": cfg,
        "extinction": extinction,
        "reignition": reignition,
        "provenance": dict(row["provenance"]),
        "limitations": [
            "Extinction is an HRR criterion, not visual flame disappearance.",
            "No behavior is extrapolated past the last observed sample.",
        ],
    }


def integrate_hrr_decrease(
    method_record: Mapping[str, Any],
    control_record: Mapping[str, Any],
    *,
    start_s: float | None = None,
    end_s: float | None = None,
) -> dict[str, Any]:
    """Integrate paired HRR decrease over their shared observed time window."""

    method = _validate_series_record(method_record, required_channels=("hrr_kW",))
    control = _validate_series_record(control_record, required_channels=("hrr_kW",))
    if method["block_id"] != control["block_id"]:
        raise ValueError("method and control records must share block_id")
    if method["run_status"] != "completed" or control["run_status"] != "completed":
        return {
            "eligible": False,
            "reason": "both_runs_must_be_completed",
            "block_id": method["block_id"],
            "decrease_fraction": None,
        }
    lower = max(float(method["time_s"][0]), float(control["time_s"][0]))
    upper = min(float(method["time_s"][-1]), float(control["time_s"][-1]))
    if start_s is not None:
        lower = max(lower, _finite(start_s, "start_s", nonnegative=True))
    if end_s is not None:
        upper = min(upper, _finite(end_s, "end_s", nonnegative=True))
    if upper <= lower:
        return {
            "eligible": False,
            "reason": "no_positive_shared_observation_window",
            "block_id": method["block_id"],
            "decrease_fraction": None,
        }
    knots = _shared_knots(method["time_s"], control["time_s"], lower, upper)
    m = np.interp(knots, method["time_s"], method["channels"]["hrr_kW"])
    c = np.interp(knots, control["time_s"], control["channels"]["hrr_kW"])
    m_int = float(np.trapezoid(m, knots))
    c_int = float(np.trapezoid(c, knots))
    return {
        "eligible": c_int > 0.0,
        "reason": None if c_int > 0.0 else "control_integral_is_zero",
        "block_id": method["block_id"],
        "window_s": [lower, upper],
        "integration": "trapezoid_on_union_of_observed_knots_within_overlap",
        "method_integral_kJ": m_int,
        "control_integral_kJ": c_int,
        "decrease_kJ": c_int - m_int,
        "decrease_fraction": (1.0 - m_int / c_int) if c_int > 0.0 else None,
        "extrapolated": False,
    }


def analyze_study(
    records: Iterable[Mapping[str, Any]],
    preregistration: Mapping[str, Any],
    *,
    synergy_specs: Iterable[Mapping[str, Any]] = (),
    bootstrap_samples: int = 500,
    seed: int = 42,
) -> dict[str, Any]:
    """Run the WP3/WP4 outcome pipeline on genuine imported time series."""

    rows = [_validate_series_record(row, required_channels=("hrr_kW",)) for row in records]
    if not rows:
        raise ValueError("records must not be empty")
    criterion = _extinction_criterion(preregistration.get("extinction", {}))
    tau = _finite(preregistration.get("tau_s"), "preregistration.tau_s", positive=True)
    control_id = _nonempty(preregistration.get("control_id"), "preregistration.control_id")

    extinction = [analyze_extinction_run(row, criterion) for row in rows]
    extinction_statistics = _extinction_statistics(
        rows, extinction, tau, bootstrap_samples, seed
    )
    control_by_block = {
        row["block_id"]: row for row in rows
        if row["condition_id"] == control_id and row["run_status"] == "completed"
    }
    hrr_reductions = []
    outcome_rows = []
    incomplete_outcomes = []
    for row, result in zip(rows, extinction, strict=True):
        reduction = None
        if row["condition_id"] != control_id and row["block_id"] in control_by_block:
            reduction = integrate_hrr_decrease(row, control_by_block[row["block_id"]], end_s=tau)
            hrr_reductions.append({"condition_id": row["condition_id"], **reduction})
        event = result["extinction"].get("event") is True
        completed = row["run_status"] == "completed"
        observed_end = min(float(row["time_s"][-1]), tau)
        loss = _integral_to(row, "heat_flux_kW_m2", tau)
        # Existing outcome analysis requires a physical loss channel.  Missing
        # heat flux stays incomplete; HRR is never relabelled as heat exposure.
        status = row["run_status"]
        missing = []
        if completed and loss is None:
            missing.append("heat_flux_kW_m2_through_tau")
        if completed and row.get("input_energy_J") is None:
            missing.append("input_energy_J")
        if completed and missing:
            status = "incomplete"
            incomplete_outcomes.append({
                "case_id": row["case_id"],
                "condition_id": row["condition_id"],
                "reason": "missing_required_outcome_inputs",
                "missing": missing,
            })
        outcome_rows.append({
            "case_id": row["case_id"],
            "block_id": row["block_id"],
            "condition_id": row["condition_id"],
            "run_status": status,
            "observation_end_s": observed_end,
            "event": event if status == "completed" else False,
            "event_time_s": result["extinction"].get("time_s") if status == "completed" and event else None,
            "loss_J_m2": loss * 1000.0 if loss is not None and status == "completed" else None,
            "input_energy_J": row.get("input_energy_J") if status == "completed" else None,
            "provenance": row["provenance"],
            **({"resource": row["resource"]} if "resource" in row else {}),
        })

    outcomes = analyze_outcomes(outcome_rows, tau, bootstrap_samples, seed)
    synergy = []
    for index, spec in enumerate(synergy_specs):
        kwargs = dict(spec)
        kwargs.setdefault("bootstrap_samples", bootstrap_samples)
        kwargs.setdefault("seed", seed + index)
        computed = compute_synergy(outcome_rows, **kwargs)
        # Keep the result fields at top level for backward compatibility while
        # retaining the exact comparison identity needed by reports.
        computed.update({
            "control_id": kwargs["control_id"],
            "combination_id": kwargs["combination_id"],
            "partial_single_ids": dict(kwargs["partial_single_ids"]),
            "equal_budget_single_ids": (
                dict(kwargs["equal_budget_single_ids"])
                if kwargs.get("equal_budget_single_ids") is not None else None
            ),
            "preselected_single_id": kwargs.get("preselected_single_id"),
            "analysis_spec": {
                key: value for key, value in kwargs.items()
                if key not in {"bootstrap_samples", "seed"}
            },
        })
        synergy.append(computed)
    return {
        "schema_version": "1.0",
        "analysis_scope": "observed_solver_or_measured_time_series",
        "preregistration": dict(preregistration),
        "extinction_runs": extinction,
        "extinction_statistics": extinction_statistics,
        "hrr_reductions": hrr_reductions,
        "outcomes": outcomes,
        "incomplete_outcomes": incomplete_outcomes,
        "synergy": synergy,
        "missing_channel_policy": "incomplete_not_zero",
        "extrapolation": "forbidden",
    }


def _extinction_statistics(
    rows: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    tau: float,
    samples: int,
    seed: int,
) -> dict[str, Any]:
    """RMST/event summaries using only extinction status and observation time.

    Heat exposure and source-energy availability deliberately play no role in
    this estimand.  A completed non-event is eligible only if it was observed
    through ``tau``; early termination remains incomplete.
    """

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row, result in zip(rows, results, strict=True):
        event = result["extinction"].get("event") is True
        event_time = result["extinction"].get("time_s")
        observed_end = float(row["time_s"][-1])
        if row["run_status"] != "completed" or result["status"] != "complete":
            category, observed = "incomplete", None
        elif event and event_time is not None and float(event_time) <= tau:
            category, observed = "event", float(event_time)
        elif observed_end >= tau:
            category, observed = "administrative_censor", tau
        else:
            category, observed = "incomplete", None
        grouped[row["condition_id"]].append({
            "block_id": row["block_id"],
            "category": category,
            "observed_time_s": observed,
        })

    rng = np.random.default_rng(seed + 10_000)
    summaries = {}
    block_values: dict[str, dict[str, list[float]]] = {}
    for condition, items in sorted(grouped.items()):
        eligible = [item for item in items if item["observed_time_s"] is not None]
        by_block: dict[str, list[float]] = defaultdict(list)
        for item in eligible:
            by_block[item["block_id"]].append(float(item["observed_time_s"]))
        block_values[condition] = dict(by_block)
        reps = []
        ids = sorted(by_block)
        if ids:
            for _ in range(samples):
                chosen = [str(value) for value in rng.choice(ids, size=len(ids), replace=True)]
                reps.append(float(np.mean([
                    value for block in chosen for value in by_block[block]
                ])))
        event_count = sum(item["category"] == "event" for item in eligible)
        summaries[condition] = {
            "counts": {
                "total": len(items),
                "eligible": len(eligible),
                "events": event_count,
                "administrative_censor": sum(item["category"] == "administrative_censor" for item in items),
                "incomplete": sum(item["category"] == "incomplete" for item in items),
                "independent_blocks": len(by_block),
            },
            "event_fraction_by_tau": event_count / len(eligible) if eligible else None,
            "rmst_s": float(np.mean([item["observed_time_s"] for item in eligible])) if eligible else None,
            "rmst_ci95_s": _quantile_ci(reps),
            "precision_warning": (
                "fewer_than_3_independent_blocks" if 0 < len(by_block) < 3 else None
            ),
            "estimand_note": (
                "Lower extinction RMST is favorable. Energy and exposure channels are not required; "
                "early incomplete runs are excluded and listed in counts."
            ),
        }

    comparisons = []
    for left, right in combinations(sorted(block_values), 2):
        common = sorted(set(block_values[left]) & set(block_values[right]))
        if not common:
            comparisons.append({
                "left": left, "right": right, "eligible": False,
                "reason": "no_common_complete_blocks", "common_blocks": 0,
                "rmst_difference_s": None, "rmst_difference_ci95_s": None,
            })
            continue

        def difference(selected: Sequence[str]) -> float:
            left_values = [value for block in selected for value in block_values[left][block]]
            right_values = [value for block in selected for value in block_values[right][block]]
            return float(np.mean(left_values) - np.mean(right_values))

        reps = []
        for _ in range(samples):
            selected = [str(value) for value in rng.choice(common, size=len(common), replace=True)]
            reps.append(difference(selected))
        comparisons.append({
            "left": left,
            "right": right,
            "eligible": True,
            "reason": None,
            "common_blocks": len(common),
            "rmst_difference_s": difference(common),
            "rmst_difference_ci95_s": _quantile_ci(reps),
            "precision_warning": (
                "fewer_than_3_common_blocks" if len(common) < 3 else None
            ),
        })
    return {
        "tau_s": tau,
        "bootstrap": {
            "method": "cluster_by_block",
            "samples": samples,
            "seed": seed + 10_000,
        },
        "groups": summaries,
        "paired_comparisons": comparisons,
        "energy_required": False,
        "heat_exposure_required": False,
    }


def analyze_order_effects(
    records: Iterable[Mapping[str, Any]],
    *,
    metric: str,
    bootstrap_samples: int = 500,
    permutation_samples: int = 4096,
    seed: int = 42,
) -> dict[str, Any]:
    """Compare A>B and B>A in paired blocks with Holm-adjusted tests."""

    if bootstrap_samples < 1 or permutation_samples < 1:
        raise ValueError("sample counts must be positive")
    grouped: dict[tuple[str, str], dict[tuple[str, str], dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for index, raw in enumerate(records):
        if not isinstance(raw, Mapping):
            raise TypeError(f"record {index} must be a mapping")
        _require_provenance(raw, f"record {index}")
        block = _nonempty(raw.get("block_id"), f"record {index} block_id")
        order = raw.get("order")
        if not isinstance(order, Sequence) or isinstance(order, (str, bytes)) or len(order) != 2:
            raise ValueError(f"record {index} order must contain exactly two methods")
        first, second = (_nonempty(value, f"record {index} order") for value in order)
        if first == second:
            raise ValueError(f"record {index} order methods must differ")
        value = _finite(raw.get(metric), f"record {index} {metric}")
        pair = tuple(sorted((first, second)))
        direction = (first, second)
        if block in grouped[pair][direction]:
            raise ValueError(f"duplicate order/block: {direction}/{block}")
        grouped[pair][direction][block] = value

    rng = np.random.default_rng(seed)
    results = []
    raw_ps = []
    for pair in sorted(grouped):
        forward, reverse = pair, (pair[1], pair[0])
        left = grouped[pair].get(forward, {})
        right = grouped[pair].get(reverse, {})
        common = sorted(set(left) & set(right))
        if not common:
            results.append({"pair": list(pair), "eligible": False, "reason": "no_common_blocks"})
            continue
        differences = np.asarray([right[b] - left[b] for b in common], dtype=float)
        reps = [float(np.mean(rng.choice(differences, len(differences), replace=True))) for _ in range(bootstrap_samples)]
        signs = rng.choice((-1.0, 1.0), size=(permutation_samples, len(differences)))
        perm = np.abs(np.mean(signs * differences, axis=1))
        p = float((1 + np.sum(perm >= abs(float(np.mean(differences))))) / (permutation_samples + 1))
        raw_ps.append((len(results), p))
        results.append({
            "pair": list(pair),
            "contrast": f"{pair[1]}>{pair[0]} minus {pair[0]}>{pair[1]}",
            "eligible": True,
            "common_blocks": len(common),
            "difference": float(np.mean(differences)),
            "ci95": _quantile_ci(reps),
            "p_value": p,
            "p_value_holm": None,
        })
    _apply_holm(results, raw_ps)
    return {"metric": metric, "tests": results, "multiple_testing": "Holm family-wise adjustment"}


def pareto_front(
    records: Iterable[Mapping[str, Any]], objectives: Mapping[str, str]
) -> dict[str, Any]:
    """Return non-dominated records for explicit min/max objectives."""

    if not objectives or any(direction not in {"min", "max"} for direction in objectives.values()):
        raise ValueError("objectives must map fields to 'min' or 'max'")
    valid, incomplete = [], []
    for index, raw in enumerate(records):
        if not isinstance(raw, Mapping):
            raise TypeError(f"record {index} must be a mapping")
        _require_provenance(raw, f"record {index}")
        try:
            values = {name: _finite(raw.get(name), f"record {index} {name}") for name in objectives}
        except (TypeError, ValueError) as exc:
            incomplete.append({"index": index, "reason": str(exc)})
            continue
        valid.append((index, dict(raw), values))

    def dominates(a: Mapping[str, float], b: Mapping[str, float]) -> bool:
        weak = []
        strict = []
        for name, direction in objectives.items():
            if direction == "min":
                weak.append(a[name] <= b[name]); strict.append(a[name] < b[name])
            else:
                weak.append(a[name] >= b[name]); strict.append(a[name] > b[name])
        return all(weak) and any(strict)

    front = []
    dominated = []
    for index, row, values in valid:
        dominators = [other_index for other_index, _, other in valid if other_index != index and dominates(other, values)]
        item = {"index": index, "record": row, "objective_values": values}
        if dominators:
            dominated.append({**item, "dominated_by_indices": dominators})
        else:
            front.append(item)
    return {"objectives": dict(objectives), "front": front, "dominated": dominated, "incomplete": incomplete}


def latin_hypercube(
    parameters: Mapping[str, Sequence[float]], sample_count: int, seed: int = 42
) -> list[dict[str, float]]:
    """Generate a deterministic continuous LHS design within closed bounds."""

    if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count < 1:
        raise ValueError("sample_count must be a positive integer")
    bounds = []
    for name, pair in parameters.items():
        if not isinstance(name, str) or not name or len(pair) != 2:
            raise ValueError("each parameter must have a non-empty name and two bounds")
        lower = _finite(pair[0], f"{name}.lower")
        upper = _finite(pair[1], f"{name}.upper")
        if upper <= lower:
            raise ValueError(f"{name} upper bound must exceed lower bound")
        bounds.append((name, lower, upper))
    if not bounds:
        raise ValueError("parameters must not be empty")
    rng = np.random.default_rng(seed)
    columns: dict[str, np.ndarray] = {}
    for name, lower, upper in bounds:
        strata = (np.arange(sample_count) + rng.random(sample_count)) / sample_count
        columns[name] = lower + (upper - lower) * strata[rng.permutation(sample_count)]
    return [{name: float(columns[name][i]) for name, _, _ in bounds} for i in range(sample_count)]


def split_cases(
    records: Iterable[Mapping[str, Any]], holdout_fraction: float = 0.25, seed: int = 42
) -> dict[str, Any]:
    """Split complete environment cases without putting one case in both sets."""

    fraction = _finite(holdout_fraction, "holdout_fraction", positive=True)
    if fraction >= 1:
        raise ValueError("holdout_fraction must be < 1")
    rows = [dict(row) for row in records]
    if not rows:
        raise ValueError("records must not be empty")
    for index, row in enumerate(rows):
        _require_provenance(row, f"record {index}")
        row["case_id"] = _nonempty(row.get("case_id"), f"record {index} case_id")
    ids = sorted({row["case_id"] for row in rows})
    if len(ids) < 2:
        raise ValueError("at least two distinct case_id values are required")
    rng = np.random.default_rng(seed)
    shuffled = list(np.asarray(ids, dtype=object)[rng.permutation(len(ids))])
    count = min(len(ids) - 1, max(1, int(round(len(ids) * fraction))))
    holdout_ids = set(str(value) for value in shuffled[:count])
    return {
        "seed": seed,
        "holdout_fraction_requested": fraction,
        "train_case_ids": sorted(set(ids) - holdout_ids),
        "holdout_case_ids": sorted(holdout_ids),
        "train": [row for row in rows if row["case_id"] not in holdout_ids],
        "holdout": [row for row in rows if row["case_id"] in holdout_ids],
    }


def evaluate_environment_policy(
    records: Iterable[Mapping[str, Any]],
    *,
    environment_fields: Sequence[str],
    metric: str,
    direction: str = "min",
    holdout_fraction: float = 0.25,
    seed: int = 42,
) -> dict[str, Any]:
    """Select policies on training cases and evaluate them unchanged on holdout."""

    if direction not in {"min", "max"}:
        raise ValueError("direction must be min or max")
    split = split_cases(records, holdout_fraction, seed)
    train_groups: dict[tuple[Any, ...], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for index, row in enumerate(split["train"]):
        condition = _nonempty(row.get("condition_id"), f"train record {index} condition_id")
        key = _environment_key(row, environment_fields, f"train record {index}")
        train_groups[key][condition].append(_finite(row.get(metric), f"train record {index} {metric}"))
    policy = {}
    for key, candidates in sorted(train_groups.items(), key=lambda item: repr(item[0])):
        means = {condition: float(np.mean(values)) for condition, values in candidates.items()}
        chooser = min if direction == "min" else max
        chosen = chooser(sorted(means), key=lambda condition: means[condition])
        policy[key] = {"condition_id": chosen, "training_mean": means[chosen], "candidates": means}
    evaluated, out_of_domain, missing_policy_condition = [], [], []
    holdout_groups: dict[tuple[str, tuple[Any, ...]], list[float]] = defaultdict(list)
    for index, row in enumerate(split["holdout"]):
        key = _environment_key(row, environment_fields, f"holdout record {index}")
        if key not in policy:
            out_of_domain.append(row["case_id"])
            continue
        condition = _nonempty(row.get("condition_id"), f"holdout record {index} condition_id")
        holdout_groups[(row["case_id"], key, condition)].append(_finite(row.get(metric), f"holdout record {index} {metric}"))
    for case_id in split["holdout_case_ids"]:
        keys = sorted({key for cid, key, _ in holdout_groups if cid == case_id}, key=repr)
        for key in keys:
            selected = policy[key]["condition_id"] if key in policy else None
            values = holdout_groups.get((case_id, key, selected), [])
            if not values:
                missing_policy_condition.append({"case_id": case_id, "environment": list(key), "condition_id": selected})
                continue
            evaluated.append({
                "case_id": case_id,
                "environment": list(key),
                "condition_id": selected,
                "holdout_metric": float(np.mean(values)),
            })
    return {
        "metric": metric,
        "direction": direction,
        "environment_fields": list(environment_fields),
        "train_case_ids": split["train_case_ids"],
        "holdout_case_ids": split["holdout_case_ids"],
        "policy": [{"environment": list(key), **value} for key, value in sorted(policy.items(), key=lambda item: repr(item[0]))],
        "holdout_evaluated": evaluated,
        "holdout_mean": float(np.mean([item["holdout_metric"] for item in evaluated])) if evaluated else None,
        "out_of_domain_case_ids": sorted(set(out_of_domain)),
        "missing_selected_condition": missing_policy_condition,
        "selection_note": "Policy choices use training cases only and are fixed before holdout evaluation.",
    }


def _validate_series_record(record: Mapping[str, Any], required_channels: Sequence[str]) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise TypeError("record must be a mapping")
    row = dict(record)
    for name in ("case_id", "block_id", "condition_id", "run_status"):
        row[name] = _nonempty(row.get(name), name)
    _require_provenance(row, "record")
    if row["run_status"] not in {"completed", "incomplete", "aborted", "numerical_failure", "solver_failure"}:
        raise ValueError("run_status is invalid")
    time = _array(row.get("time_s"), "time_s")
    if len(time) < 2 or np.any(np.diff(time) <= 0):
        raise ValueError("time_s must contain at least two strictly increasing observations")
    if time[0] < 0:
        raise ValueError("time_s must be nonnegative")
    channels = row.get("channels")
    if not isinstance(channels, Mapping):
        raise ValueError("channels must be a mapping")
    clean = {}
    for name, values in channels.items():
        clean[name] = _array(values, f"channels.{name}")
        if len(clean[name]) != len(time):
            raise ValueError(f"channels.{name} length must match time_s")
    missing = [name for name in required_channels if name not in clean]
    if missing:
        raise ValueError("missing required channels: " + ",".join(missing))
    if "input_energy_J" in row and row["input_energy_J"] is not None:
        row["input_energy_J"] = _finite(row["input_energy_J"], "input_energy_J", nonnegative=True)
    else:
        # Native solver imports can establish HRR/extinction without knowing
        # device-side electrical or stored-fluid energy.  Keep those physical
        # observations analyzable, but the combined energy/outcome summary will
        # explicitly mark the record incomplete rather than assuming zero.
        row["input_energy_J"] = None
    if "intervention_end_s" in row:
        row["intervention_end_s"] = _finite(row["intervention_end_s"], "intervention_end_s", nonnegative=True)
    row["time_s"] = time
    row["channels"] = clean
    return row


def _extinction_criterion(value: Mapping[str, Any]) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise ValueError("extinction criterion must be a mapping")
    return {
        "hrr_threshold_kW": _finite(value.get("hrr_threshold_kW"), "hrr_threshold_kW", nonnegative=True),
        "sustain_s": _finite(value.get("sustain_s"), "sustain_s", positive=True),
        "reignition_threshold_kW": _finite(value.get("reignition_threshold_kW"), "reignition_threshold_kW", nonnegative=True),
        "reignition_followup_s": _finite(value.get("reignition_followup_s"), "reignition_followup_s", positive=True),
    }


def _sustained_below(time: np.ndarray, values: np.ndarray, threshold: float, duration: float) -> float | None:
    for index, value in enumerate(values):
        if value > threshold:
            continue
        stop = index
        while stop + 1 < len(values) and values[stop + 1] <= threshold:
            stop += 1
        if time[stop] - time[index] >= duration:
            return float(time[index])
    return None


def _incomplete_extinction(row: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "case_id": row["case_id"], "block_id": row["block_id"],
        "condition_id": row["condition_id"], "status": "incomplete", "reason": reason,
        "extinction": {"status": "unknown", "event": None, "time_s": None},
        "reignition": {"status": "unknown", "event": None, "time_s": None},
        "provenance": dict(row["provenance"]),
    }


def _shared_knots(a: np.ndarray, b: np.ndarray, lower: float, upper: float) -> np.ndarray:
    return np.unique(np.concatenate(([lower, upper], a[(a > lower) & (a < upper)], b[(b > lower) & (b < upper)])))


def _integral_to(row: Mapping[str, Any], channel: str, end_s: float) -> float | None:
    if channel not in row["channels"] or row["time_s"][0] > 0 or row["time_s"][-1] < end_s:
        return None
    knots = np.unique(np.concatenate((row["time_s"][(row["time_s"] >= 0) & (row["time_s"] <= end_s)], [0.0, end_s])))
    values = np.interp(knots, row["time_s"], row["channels"][channel])
    return float(np.trapezoid(values, knots))


def _apply_holm(results: list[dict[str, Any]], indexed_ps: list[tuple[int, float]]) -> None:
    ordered = sorted(indexed_ps, key=lambda item: item[1])
    adjusted = 0.0
    total = len(ordered)
    for rank, (index, p_value) in enumerate(ordered):
        adjusted = max(adjusted, min(1.0, (total - rank) * p_value))
        results[index]["p_value_holm"] = adjusted


def _environment_key(row: Mapping[str, Any], fields: Sequence[str], prefix: str) -> tuple[Any, ...]:
    if not fields:
        raise ValueError("environment_fields must not be empty")
    missing = [field for field in fields if field not in row]
    if missing:
        raise ValueError(f"{prefix} missing environment fields: {','.join(missing)}")
    return tuple(row[field] for field in fields)


def _require_provenance(row: Mapping[str, Any], prefix: str) -> None:
    provenance = row.get("provenance")
    if not isinstance(provenance, Mapping) or not provenance:
        raise ValueError(f"{prefix} provenance must be a non-empty mapping")
    if not isinstance(provenance.get("source"), str) or not provenance["source"].strip():
        raise ValueError(f"{prefix} provenance.source must be a non-empty string")


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


def _finite(value: Any, name: str, *, positive: bool = False, nonnegative: bool = False) -> float:
    if type(value) is bool or not isinstance(value, (int, float, np.integer, np.floating)):
        raise TypeError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if positive and result <= 0:
        raise ValueError(f"{name} must be > 0")
    if nonnegative and result < 0:
        raise ValueError(f"{name} must be >= 0")
    return result


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _quantile_ci(values: Sequence[float]) -> list[float] | None:
    if not values:
        return None
    bounds = np.quantile(np.asarray(values, dtype=float), [0.025, 0.975])
    return [float(bounds[0]), float(bounds[1])]
