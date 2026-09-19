"""Strict analysis of imported fire-suppression runs.

This module never manufactures efficacy values.  Invalid records raise an
exception; numerical failures and incomplete observations are counted and
excluded from estimands that they cannot support.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from itertools import combinations
import math
from typing import Any

import numpy as np


METHODS = ("M1", "M2", "M3", "M4", "M5")
_FAILURE_STATUSES = {"numerical_failure", "solver_failure"}
_INCOMPLETE_STATUSES = {"incomplete", "aborted"}
_COMPLETE_STATUS = "completed"
_DEFAULT_EVIDENCE = {"measured", "experimental", "validated_simulation"}


def generate_matrix() -> list[dict[str, Any]]:
    """Return the 36-condition main design before environments/repeats.

    Resource values are relative dose labels, not measured physical inputs.
    They exist so importers can bind a condition to an explicit resource
    ledger instead of silently treating every method as full-dose.
    """

    matrix: list[dict[str, Any]] = [
        {
            "id": "C0",
            "methods": [],
            "mode": "control",
            "order": [],
            "resource_dose": {},
            "metadata": {
                "main_design": True,
                "dose_basis": "relative_design_label",
                "note": "No suppression input; sham/device-only runs are supplemental.",
            },
        }
    ]
    for method in METHODS:
        matrix.append(
            {
                "id": method,
                "methods": [method],
                "mode": "single",
                "order": [method],
                "resource_dose": {method: 1.0},
                "metadata": _matrix_metadata(method),
            }
        )
    for left, right in combinations(METHODS, 2):
        matrix.append(
            {
                "id": f"{left}+{right}:SIM",
                "methods": [left, right],
                "mode": "simultaneous",
                "order": [left, right],
                "resource_dose": {left: 1.0, right: 1.0},
                "metadata": _matrix_metadata(left, right),
            }
        )
    for left, right in combinations(METHODS, 2):
        for first, second in ((left, right), (right, left)):
            matrix.append(
                {
                    "id": f"{first}>{second}:SEQ",
                    "methods": [first, second],
                    "mode": "sequential",
                    "order": [first, second],
                    "resource_dose": {first: 1.0, second: 1.0},
                    "metadata": {
                        **_matrix_metadata(first, second),
                        "schedule_required": [
                            "stage_duration_s",
                            "transition_delay_s",
                        ],
                    },
                }
            )
    assert len(matrix) == 36
    return matrix


def _matrix_metadata(*methods: str) -> dict[str, Any]:
    note = "Dose values are design labels; bind them to an SI resource ledger before running."
    if "M5" in methods:
        note += (
            " M5 is a composite candidate: record variant CV, EHD, or COMBINED; "
            "CV must not receive an assumed electrohydrodynamic force."
        )
    return {
        "main_design": True,
        "dose_basis": "relative_design_label",
        "resource_ledger_required": True,
        "note": note,
    }


def analyze_outcomes(
    records: Iterable[Mapping[str, Any]],
    tau_s: float,
    bootstrap_samples: int = 500,
    seed: int = 42,
) -> dict[str, Any]:
    """Validate and summarize imported runs at a common analysis horizon.

    The cluster bootstrap resamples ``block_id`` values, preserving all
    methods/runs within each sampled block.  Pairwise contrasts use only
    common blocks and therefore retain the planned pairing.
    """

    tau = _finite_number(tau_s, "tau_s", positive=True)
    if isinstance(bootstrap_samples, bool) or not isinstance(bootstrap_samples, int):
        raise TypeError("bootstrap_samples must be an integer")
    if bootstrap_samples < 1:
        raise ValueError("bootstrap_samples must be at least 1")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")

    validated = [_validate_record(record, index) for index, record in enumerate(records)]
    if not validated:
        raise ValueError("records must contain at least one imported run")
    seen: set[tuple[str, str]] = set()
    for record in validated:
        key = (record["case_id"], record["group_id"])
        if key in seen:
            raise ValueError(f"duplicate case/group record: {key!r}")
        seen.add(key)

    classified = [_classify(record, tau) for record in validated]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in classified:
        groups[item["record"]["group_id"]].append(item)

    rng = np.random.default_rng(seed)
    summaries = {
        group_id: _summarize_group(items, tau, bootstrap_samples, rng)
        for group_id, items in sorted(groups.items())
    }
    comparisons: list[dict[str, Any]] = []
    for left, right in combinations(sorted(groups), 2):
        comparisons.append(
            _paired_comparison(
                left,
                groups[left],
                right,
                groups[right],
                bootstrap_samples,
                rng,
            )
        )

    return {
        "schema_version": "1.0",
        "tau_s": tau,
        "bootstrap": {
            "method": "paired_cluster_by_block",
            "samples": bootstrap_samples,
            "seed": seed,
            "ci_level": 0.95,
            "limitations": "Sampling intervals do not include model or measurement bias.",
        },
        "groups": summaries,
        "paired_comparisons": comparisons,
    }


def _validate_record(record: Mapping[str, Any], index: int) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise TypeError(f"record {index} must be a mapping")
    required = {
        "case_id",
        "block_id",
        "run_status",
        "observation_end_s",
        "event",
        "event_time_s",
        "loss_J_m2",
        "input_energy_J",
        "provenance",
    }
    missing = sorted(required - set(record))
    if missing:
        raise ValueError(f"record {index} missing fields: {', '.join(missing)}")
    has_condition = "condition_id" in record
    has_method = "method_id" in record
    if has_condition == has_method:
        raise ValueError(f"record {index} must contain exactly one of condition_id or method_id")

    output = dict(record)
    for field in ("case_id", "block_id", "run_status"):
        output[field] = _nonempty_string(output[field], f"record {index} {field}")
    group_field = "condition_id" if has_condition else "method_id"
    output[group_field] = _nonempty_string(output[group_field], f"record {index} {group_field}")
    output["group_id"] = output[group_field]
    status = output["run_status"]
    allowed = {_COMPLETE_STATUS} | _FAILURE_STATUSES | _INCOMPLETE_STATUSES
    if status not in allowed:
        raise ValueError(f"record {index} run_status must be one of {sorted(allowed)}")
    output["observation_end_s"] = _finite_number(
        output["observation_end_s"], f"record {index} observation_end_s", nonnegative=True
    )
    if type(output["event"]) is not bool:
        raise TypeError(f"record {index} event must be bool")
    if not isinstance(output["provenance"], Mapping) or not output["provenance"]:
        raise ValueError(f"record {index} provenance must be a non-empty mapping")

    if status == _COMPLETE_STATUS:
        output["loss_J_m2"] = _finite_number(
            output["loss_J_m2"], f"record {index} loss_J_m2", nonnegative=True
        )
        output["input_energy_J"] = _finite_number(
            output["input_energy_J"], f"record {index} input_energy_J", nonnegative=True
        )
        if output["event"]:
            output["event_time_s"] = _finite_number(
                output["event_time_s"], f"record {index} event_time_s", nonnegative=True
            )
            if output["event_time_s"] > output["observation_end_s"]:
                raise ValueError(f"record {index} event_time_s exceeds observation_end_s")
        elif output["event_time_s"] is not None:
            raise ValueError(f"record {index} event_time_s must be null when event is false")
    else:
        if output["event"] or output["event_time_s"] is not None:
            raise ValueError(f"record {index} failed/incomplete run cannot declare an event")
        for field in ("loss_J_m2", "input_energy_J"):
            value = output[field]
            if value is not None:
                output[field] = _finite_number(
                    value, f"record {index} {field}", nonnegative=True
                )
    return output


def _classify(record: dict[str, Any], tau: float) -> dict[str, Any]:
    status = record["run_status"]
    if status in _FAILURE_STATUSES:
        category = "numerical_failure"
        observed = None
    elif status in _INCOMPLETE_STATUSES:
        category = "incomplete"
        observed = None
    elif record["event"] and record["event_time_s"] <= tau:
        category = "event"
        observed = record["event_time_s"]
    elif record["observation_end_s"] >= tau:
        category = "administrative_censor"
        observed = tau
    else:
        category = "incomplete"
        observed = None
    return {"record": record, "category": category, "observed_time_s": observed}


def _summarize_group(
    items: list[dict[str, Any]],
    tau: float,
    samples: int,
    rng: np.random.Generator,
) -> dict[str, Any]:
    counts = {name: sum(item["category"] == name for item in items) for name in (
        "event", "administrative_censor", "incomplete", "numerical_failure"
    )}
    eligible = [item for item in items if item["observed_time_s"] is not None]
    success_rate = counts["event"] / len(eligible) if eligible else None
    rmst = _mean_or_none([item["observed_time_s"] for item in eligible])
    losses = [item["record"]["loss_J_m2"] for item in eligible]
    energies = [item["record"]["input_energy_J"] for item in eligible]

    replicates = _cluster_bootstrap_metrics(eligible, samples, rng)
    return {
        "counts": {
            "total_imported": len(items),
            "analysis_eligible": len(eligible),
            **counts,
        },
        "success_rate": success_rate,
        "success_rate_ci95": _ci([row[0] for row in replicates]),
        "rmst_s": rmst,
        "rmst_ci95_s": _ci([row[1] for row in replicates]),
        "mean_loss_J_m2": _mean_or_none(losses),
        "mean_loss_ci95_J_m2": _ci([row[2] for row in replicates]),
        "mean_input_energy_J": _mean_or_none(energies),
        "mean_input_energy_ci95_J": _ci([row[3] for row in replicates]),
        "estimand_note": (
            f"RMST is mean min(event time, {tau} s) among complete event or "
            "administratively censored runs; incomplete and numerical failures are excluded."
        ),
    }


def _cluster_bootstrap_metrics(
    eligible: list[dict[str, Any]], samples: int, rng: np.random.Generator
) -> list[tuple[float, float, float, float]]:
    if not eligible:
        return []
    by_block: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in eligible:
        by_block[item["record"]["block_id"]].append(item)
    block_ids = sorted(by_block)
    results = []
    for _ in range(samples):
        selected = rng.choice(block_ids, size=len(block_ids), replace=True)
        sample_items = [item for block in selected for item in by_block[str(block)]]
        results.append(
            (
                sum(item["category"] == "event" for item in sample_items) / len(sample_items),
                float(np.mean([item["observed_time_s"] for item in sample_items])),
                float(np.mean([item["record"]["loss_J_m2"] for item in sample_items])),
                float(np.mean([item["record"]["input_energy_J"] for item in sample_items])),
            )
        )
    return results


def _paired_comparison(
    left_id: str,
    left_items: list[dict[str, Any]],
    right_id: str,
    right_items: list[dict[str, Any]],
    samples: int,
    rng: np.random.Generator,
) -> dict[str, Any]:
    left = _eligible_by_block(left_items)
    right = _eligible_by_block(right_items)
    common = sorted(set(left) & set(right))
    if not common:
        return {
            "left": left_id,
            "right": right_id,
            "eligible": False,
            "reason": "no_common_complete_blocks",
            "common_blocks": 0,
            "rmst_difference_s": None,
            "rmst_difference_ci95_s": None,
            "loss_difference_J_m2": None,
            "loss_difference_ci95_J_m2": None,
        }

    def difference(block_ids: Sequence[str], field: str) -> float:
        left_values = [value for block in block_ids for value in left[block][field]]
        right_values = [value for block in block_ids for value in right[block][field]]
        return float(np.mean(left_values) - np.mean(right_values))

    rmst_reps: list[float] = []
    loss_reps: list[float] = []
    for _ in range(samples):
        selected = [str(value) for value in rng.choice(common, size=len(common), replace=True)]
        rmst_reps.append(difference(selected, "time"))
        loss_reps.append(difference(selected, "loss"))
    return {
        "left": left_id,
        "right": right_id,
        "eligible": True,
        "reason": None,
        "common_blocks": len(common),
        "rmst_difference_s": difference(common, "time"),
        "rmst_difference_ci95_s": _ci(rmst_reps),
        "loss_difference_J_m2": difference(common, "loss"),
        "loss_difference_ci95_J_m2": _ci(loss_reps),
    }


def _eligible_by_block(items: list[dict[str, Any]]) -> dict[str, dict[str, list[float]]]:
    output: dict[str, dict[str, list[float]]] = {}
    for item in items:
        if item["observed_time_s"] is None:
            continue
        block = item["record"]["block_id"]
        bucket = output.setdefault(block, {"time": [], "loss": []})
        bucket["time"].append(item["observed_time_s"])
        bucket["loss"].append(item["record"]["loss_J_m2"])
    return output


def compute_synergy(
    records: Iterable[Mapping[str, Any]],
    *,
    control_id: str,
    combination_id: str,
    partial_single_ids: Mapping[str, str],
    equal_budget_single_ids: Mapping[str, str] | None = None,
    preselected_single_id: str | None = None,
    selection_provenance: Mapping[str, Any] | None = None,
    bootstrap_samples: int = 500,
    seed: int = 42,
    eligible_evidence_types: Iterable[str] = _DEFAULT_EVIDENCE,
) -> dict[str, Any]:
    """Compute additive synergy and, when supported, equal-budget gain.

    Records must be completed and include ``resource`` with ``doses``,
    ``schedule``, and ``budget`` mappings.  Additive synergy uses exact
    per-method dose/schedule matches. Equal-budget gain uses one comparator
    selected independently of the evaluation blocks; choosing the best single
    separately inside each evaluation block is intentionally prohibited. The
    fixed single and combination must have exactly equal budget vectors.
    Calculations are paired by ``block_id``.
    """

    if len(partial_single_ids) != 2:
        raise ValueError("partial_single_ids must map exactly two method IDs to condition IDs")
    if bootstrap_samples < 1:
        raise ValueError("bootstrap_samples must be at least 1")
    accepted = set(eligible_evidence_types)
    if not accepted:
        raise ValueError("eligible_evidence_types cannot be empty")
    rows = [_validate_record(row, index) for index, row in enumerate(records)]
    needed = {control_id, combination_id, *partial_single_ids.values()}
    if equal_budget_single_ids is not None:
        if set(equal_budget_single_ids) != set(partial_single_ids):
            raise ValueError("equal_budget_single_ids must use the same two method keys")
        if preselected_single_id is not None and preselected_single_id not in equal_budget_single_ids.values():
            raise ValueError("preselected_single_id must be one of equal_budget_single_ids")
    if preselected_single_id is not None:
        preselected_single_id = _nonempty_string(preselected_single_id, "preselected_single_id")
        needed.add(preselected_single_id)
    selected = [row for row in rows if row["group_id"] in needed]
    reasons: list[str] = []
    absent = sorted(needed - {row["group_id"] for row in selected})
    if absent:
        reasons.append("missing_conditions:" + ",".join(absent))
    unusable = [row for row in selected if row["run_status"] != _COMPLETE_STATUS]
    if unusable:
        reasons.append("noncompleted_records_present")
    weak = [row for row in selected if _evidence_type(row) not in accepted]
    if weak:
        reasons.append("evidence_gate_failed")
    for row in selected:
        try:
            _validate_resource(row)
        except (TypeError, ValueError) as exc:
            reasons.append(f"invalid_resource:{row['group_id']}:{exc}")
    if reasons:
        return _ineligible_synergy(reasons)

    by_condition_block = _one_per_condition_block(selected)
    additive_blocks: list[tuple[str, float]] = []
    methods = tuple(sorted(partial_single_ids))
    common = set(by_condition_block[control_id]) & set(by_condition_block[combination_id])
    for condition in partial_single_ids.values():
        common &= set(by_condition_block[condition])
    dose_mismatch = False
    for block in sorted(common):
        combo = by_condition_block[combination_id][block]
        singles = {
            method: by_condition_block[condition][block]
            for method, condition in partial_single_ids.items()
        }
        if not all(_partial_resource_matches(combo, single, method) for method, single in singles.items()):
            dose_mismatch = True
            continue
        value = (
            singles[methods[0]]["loss_J_m2"]
            + singles[methods[1]]["loss_J_m2"]
            - combo["loss_J_m2"]
            - by_condition_block[control_id][block]["loss_J_m2"]
        )
        additive_blocks.append((block, float(value)))

    additive_reason = None
    if not additive_blocks:
        additive_reason = "no_blocks_with_matching_partial_dose_and_schedule"
    elif dose_mismatch:
        additive_reason = "some_blocks_excluded_for_partial_dose_or_schedule_mismatch"
    additive = _paired_scalar_result(additive_blocks, bootstrap_samples, seed, additive_reason)

    budget_result: dict[str, Any]
    if preselected_single_id is None:
        budget_result = {"eligible": False, "reason": "preselected_single_id_required", "value": None, "ci95": None, "blocks": 0, "selection_provenance": None}
    elif not _valid_selection_provenance(selection_provenance):
        budget_result = {"eligible": False, "reason": "independent_selection_provenance_required", "value": None, "ci95": None, "blocks": 0, "selection_provenance": None}
    else:
        budget_common = set(by_condition_block[combination_id]) & set(by_condition_block[preselected_single_id])
        values: list[tuple[str, float]] = []
        mismatch = False
        for block in sorted(budget_common):
            combo = by_condition_block[combination_id][block]
            single = by_condition_block[preselected_single_id][block]
            if not _equal_budget(combo, single):
                mismatch = True
                continue
            values.append((block, float(single["loss_J_m2"] - combo["loss_J_m2"])))
        reason = None
        if not values:
            reason = "no_blocks_with_equal_budget_and_resources"
        elif mismatch:
            reason = "some_blocks_excluded_for_budget_mismatch"
        budget_result = _paired_scalar_result(values, bootstrap_samples, seed + 1, reason)
        budget_result["comparator_condition_id"] = preselected_single_id
        budget_result["selection_provenance"] = dict(selection_provenance)

    return {
        "eligible": additive["eligible"] or budget_result["eligible"],
        "evidence_gate": {"passed": True, "eligible_types": sorted(accepted)},
        "additive_synergy_J_m2": additive,
        "equal_budget_gain_J_m2": budget_result,
        "interpretation": "Positive values indicate lower loss than the stated comparator; they do not establish experimental causality.",
    }


def _evidence_type(record: Mapping[str, Any]) -> Any:
    return record["provenance"].get("evidence_type")


def _validate_resource(record: Mapping[str, Any]) -> None:
    resource = record.get("resource")
    if not isinstance(resource, Mapping):
        raise ValueError("resource mapping required")
    for key in ("doses", "schedule", "budget"):
        if not isinstance(resource.get(key), Mapping):
            raise ValueError(f"resource.{key} mapping required")
        if not resource[key]:
            raise ValueError(f"resource.{key} cannot be empty")
    _validate_numeric_tree(resource["doses"], "resource.doses")
    _validate_numeric_tree(resource["schedule"], "resource.schedule")
    _validate_numeric_tree(resource["budget"], "resource.budget")


def _validate_numeric_tree(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"{path} keys must be non-empty strings")
            _validate_numeric_tree(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_numeric_tree(child, f"{path}[{index}]")
    elif isinstance(value, str) or value is None or type(value) is bool:
        return
    else:
        _finite_number(value, path, nonnegative=True)


def _one_per_condition_block(records: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    output: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in records:
        condition = row["group_id"]
        block = row["block_id"]
        if block in output[condition]:
            raise ValueError(f"synergy requires one record per condition/block: {condition}/{block}")
        output[condition][block] = row
    return output


def _partial_resource_matches(combo: Mapping[str, Any], single: Mapping[str, Any], method: str) -> bool:
    combo_resource = combo["resource"]
    single_resource = single["resource"]
    return (
        method in combo_resource["doses"]
        and method in single_resource["doses"]
        and method in combo_resource["schedule"]
        and method in single_resource["schedule"]
        and set(single_resource["doses"]) == {method}
        and set(single_resource["schedule"]) == {method}
        and combo_resource["doses"][method] == single_resource["doses"][method]
        and combo_resource["schedule"][method] == single_resource["schedule"][method]
    )


def _equal_budget(combo: Mapping[str, Any], single: Mapping[str, Any]) -> bool:
    return (
        combo["resource"]["budget"] == single["resource"]["budget"]
        and combo["input_energy_J"] == single["input_energy_J"]
    )


def _valid_selection_provenance(value: Mapping[str, Any] | None) -> bool:
    if not (
        isinstance(value, Mapping)
        and isinstance(value.get("source"), str)
        and value["source"].strip()
        and value.get("independent_of_evaluation") is True
    ):
        return False
    try:
        _validate_numeric_tree(value, "selection_provenance")
    except (TypeError, ValueError):
        return False
    return True


def _paired_scalar_result(
    values: list[tuple[str, float]], samples: int, seed: int, note: str | None
) -> dict[str, Any]:
    if not values:
        return {"eligible": False, "reason": note, "value": None, "ci95": None, "blocks": 0}
    data = np.asarray([value for _, value in values], dtype=float)
    rng = np.random.default_rng(seed)
    reps = [float(np.mean(rng.choice(data, size=len(data), replace=True))) for _ in range(samples)]
    return {
        "eligible": True,
        "reason": note,
        "value": float(np.mean(data)),
        "ci95": _ci(reps),
        "blocks": len(values),
    }


def _ineligible_synergy(reasons: list[str]) -> dict[str, Any]:
    empty = {"eligible": False, "reason": ";".join(dict.fromkeys(reasons)), "value": None, "ci95": None, "blocks": 0}
    return {
        "eligible": False,
        "evidence_gate": {"passed": "evidence_gate_failed" not in reasons},
        "ineligible_reasons": list(dict.fromkeys(reasons)),
        "additive_synergy_J_m2": dict(empty),
        "equal_budget_gain_J_m2": dict(empty),
        "interpretation": None,
    }


def _finite_number(
    value: Any,
    name: str,
    *,
    positive: bool = False,
    nonnegative: bool = False,
) -> float:
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


def _nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _mean_or_none(values: Sequence[float]) -> float | None:
    return float(np.mean(values)) if values else None


def _ci(values: Sequence[float]) -> list[float] | None:
    if not values:
        return None
    bounds = np.quantile(np.asarray(values, dtype=float), [0.025, 0.975])
    return [float(bounds[0]), float(bounds[1])]
