"""D0-D5 drone feasibility study orchestration.

This module turns the rigid-body screening model into the matched comparisons
defined in ``implement.md``.  It deliberately keeps flight feasibility and
fire-effect evidence separate: no fire-retention value is inferred from the
transport or flight model.
"""

from __future__ import annotations

import copy
import csv
import json
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any
from pathlib import Path

import numpy as np

from .drone import simulate_controls, simulate_mission


DEFAULT_D5_ASSUMPTIONS: dict[str, Any] = {
    "crosswind_m_s": 3.0,
    "sensor": {
        "sample_rate_Hz": 5.0,
        "latency_s": 0.20,
        "position_error_std_m": 0.10,
        "velocity_error_std_m_s": 0.05,
        "availability_fraction": 0.80,
        "seed": 42,
    },
    "payload_capacity_fraction": 0.90,
    "thermal": {
        "incident_flux_W_m2": 5_000.0,
        "exposed_area_m2": 0.08,
        "heat_capacity_J_K": 4_000.0,
        "cooling_W_K": 8.0,
        "max_temperature_K": 333.15,
        "initial_temperature_K": 293.15,
    },
}

DEFAULT_SWEEP_BOUNDS: dict[str, list[float]] = {
    "crosswind_m_s": [0.0, 1.0, 2.0, 3.0, 5.0],
    "sensor_latency_s": [0.0, 0.10, 0.25, 0.50],
    "payload_capacity_factor": [0.75, 1.0, 1.25, 1.5],
    "max_thrust_factor": [0.90, 1.0, 1.20, 1.50],
    "max_power_factor": [0.90, 1.0, 1.20, 1.50],
    "battery_factor": [0.75, 1.0, 1.25, 1.50],
    "reaction_lever_arm_m": [0.0, 0.10, 0.20, 0.30],
    "incident_flux_W_m2": [1_000.0, 3_000.0, 5_000.0, 10_000.0],
}

_ELIGIBLE_FIRE_EVIDENCE = {"measured", "experimental", "validated_simulation"}
_CONDITIONS = ("D0", "D1", "D2", "D3", "D4")
_G = 9.80665


def _finite(value: Any, name: str, *, minimum: float | None = None) -> float:
    if type(value) is bool or not isinstance(value, (int, float, np.number)):
        raise TypeError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return result


def _merge(base: Mapping[str, Any], update: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(base))
    for key, value in update.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _method_map(method_results: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    if isinstance(method_results, Mapping):
        values = []
        for method_id, raw in method_results.items():
            if not isinstance(raw, Mapping):
                raise TypeError(f"method_results[{method_id}] must be a mapping")
            row = dict(raw)
            row.setdefault("method_id", str(method_id))
            values.append(row)
    elif isinstance(method_results, Sequence) and not isinstance(method_results, (str, bytes)):
        values = [dict(row) for row in method_results]
    else:
        raise TypeError("method_results must be a mapping or sequence")
    output: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(values):
        method_id = row.get("method_id")
        if not isinstance(method_id, str) or not method_id:
            raise ValueError(f"method result {index} needs a non-empty method_id")
        if method_id in output:
            raise ValueError(f"duplicate method_id: {method_id}")
        output[method_id] = row
    if not output:
        raise ValueError("method_results cannot be empty")
    return output


def _resource_ledger(config: Mapping[str, Any], method: Mapping[str, Any]) -> dict[str, Any]:
    scenario = config.get("scenario", {})
    duration = _finite(scenario.get("duration_s", 4.0), "scenario.duration_s", minimum=0.0)
    metrics = method.get("metrics", {}) if isinstance(method.get("metrics", {}), Mapping) else {}
    material_ids = method.get("material_ids", [])
    if isinstance(material_ids, str):
        material_ids = [material_ids]
    if not isinstance(material_ids, Sequence):
        raise TypeError("method_result.material_ids must be a string or sequence")
    material_ids = [str(item) for item in material_ids if str(item)]
    loaded = _finite(method.get("loaded_consumable_kg", method.get("consumable_kg", 0.0)), "loaded_consumable_kg", minimum=0.0)
    identity_status = "declared" if material_ids or loaded == 0.0 else "missing_for_consumable"
    return {
        "budget": {
            "electrical_energy_J": _finite(method.get("device_power_W", 0.0), "device_power_W", minimum=0.0) * duration,
            "pneumatic_energy_J": _finite(metrics.get("simulated_pneumatic_energy_J", 0.0), "pneumatic_energy_J", minimum=0.0),
            "loaded_consumable_kg": loaded,
            "maximum_device_power_W": _finite(method.get("device_power_W", 0.0), "device_power_W", minimum=0.0),
            "device_mass_kg": _finite(method.get("device_mass_kg", 0.0), "device_mass_kg", minimum=0.0),
            "actuation_duration_s": duration,
        },
        "material_ids": material_ids,
        "material_identity_status": identity_status,
    }


def _inactive_method(method: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(method)
    device_mass = _finite(method.get("device_mass_kg", 0.0), "device_mass_kg", minimum=0.0)
    loaded = _finite(method.get("loaded_consumable_kg", method.get("consumable_kg", 0.0)), "loaded_consumable_kg", minimum=0.0)
    result.update({
        "reaction_force_N": [0.0, 0.0, 0.0],
        "reaction_pulse": {},
        "series": [],
        "device_power_W": 0.0,
        "device_mass_kg": device_mass + loaded,
        "consumable_kg": 0.0,
        "loaded_consumable_kg": 0.0,
        "resource_status": {"status": "not_applicable", "reason": "D2 device OFF"},
    })
    return result


def _condition_record(condition: str, mission: Mapping[str, Any] | None, ledger: Mapping[str, Any], note: str) -> dict[str, Any]:
    return {
        "condition_id": condition,
        "flight": copy.deepcopy(dict(mission)) if mission is not None else None,
        "resource": copy.deepcopy(dict(ledger)),
        "fire_loss_J_m2": None,
        "fire_effect_status": "not_computed_without_imported_matched_loss",
        "note": note,
    }


def _ideal_wake(mission: Mapping[str, Any]) -> dict[str, Any]:
    metrics = mission["metrics"]
    induced = metrics["hover_induced_velocity_m_s"]
    return {
        "model": "ideal_hover_actuator_disk_momentum_theory",
        "validation_status": "unvalidated_analytical_screening",
        "disk_loading_N_m2": metrics["rotor_disk_loading_N_m2"],
        "induced_velocity_at_disk_m_s": induced,
        "ideal_far_wake_velocity_m_s": 2.0 * induced,
        "local_velocity_field": None,
        "reason_local_field_unavailable": "rotor-resolved or measured wake field not supplied",
    }


def _d5_configs(config: Mapping[str, Any], method: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    study = config.get("drone_study", {})
    if not isinstance(study, Mapping):
        raise TypeError("config.drone_study must be a mapping")
    assumptions = _merge(DEFAULT_D5_ASSUMPTIONS, study.get("d5_assumptions", {}))
    crosswind = _merge(config, {"scenario": {"crosswind_m_s": assumptions["crosswind_m_s"]}})
    sensor = _merge(config, {"sensor": assumptions["sensor"]})

    drone = config.get("drone", {})
    capacity = _finite(drone.get("payload_capacity_kg", 2.0), "drone.payload_capacity_kg", minimum=0.0)
    fraction = _finite(assumptions["payload_capacity_fraction"], "payload_capacity_fraction", minimum=0.0)
    target_payload = capacity * fraction
    payload_now = _finite(method.get("device_mass_kg", 0.0), "device_mass_kg", minimum=0.0) + _finite(
        method.get("loaded_consumable_kg", method.get("consumable_kg", 0.0)), "loaded_consumable_kg", minimum=0.0
    )
    payload_method = dict(method)
    payload_method["device_mass_kg"] = _finite(method.get("device_mass_kg", 0.0), "device_mass_kg", minimum=0.0) + max(target_payload - payload_now, 0.0)

    thermal = _merge(config, {"thermal": assumptions["thermal"]})
    combined = _merge(crosswind, {"sensor": assumptions["sensor"], "thermal": assumptions["thermal"]})
    return {
        "crosswind": {"config": crosswind, "method": dict(method)},
        "sensor_degraded": {"config": sensor, "method": dict(method)},
        "payload_high": {"config": dict(config), "method": payload_method},
        "thermal_screen": {"config": thermal, "method": dict(method)},
        "combined": {"config": combined, "method": payload_method},
    }


def _sweep(config: Mapping[str, Any], method: Mapping[str, Any], nominal: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    study = config.get("drone_study", {})
    bounds = _merge(DEFAULT_SWEEP_BOUNDS, study.get("sweep_bounds", {}) if isinstance(study, Mapping) else {})
    drone = config.get("drone", {})
    payload = _finite(method.get("device_mass_kg", 0.0), "device_mass_kg", minimum=0.0) + _finite(
        method.get("loaded_consumable_kg", method.get("consumable_kg", 0.0)), "loaded_consumable_kg", minimum=0.0
    )
    nominal_thrust = _finite(drone.get("max_thrust_N", 45.0), "max_thrust_N", minimum=0.0)
    nominal_power = _finite(drone.get("max_power_W", 1200.0), "max_power_W", minimum=0.0)
    nominal_battery = _finite(drone.get("battery_Wh", 120.0), "battery_Wh", minimum=0.0)
    base_sensor = DEFAULT_D5_ASSUMPTIONS["sensor"]
    base_thermal = DEFAULT_D5_ASSUMPTIONS["thermal"]
    specifications = {
        "crosswind_m_s": [(value, {"scenario": {"crosswind_m_s": value}}, method) for value in bounds["crosswind_m_s"]],
        "sensor_latency_s": [(value, {"sensor": _merge(base_sensor, {"latency_s": value})}, method) for value in bounds["sensor_latency_s"]],
        "payload_capacity_kg": [(payload * value, {"drone": {"payload_capacity_kg": payload * value}}, method) for value in bounds["payload_capacity_factor"]],
        "max_thrust_N": [(nominal_thrust * value, {"drone": {"max_thrust_N": nominal_thrust * value}}, method) for value in bounds["max_thrust_factor"]],
        "max_power_W": [(nominal_power * value, {"drone": {"max_power_W": nominal_power * value}}, method) for value in bounds["max_power_factor"]],
        "battery_Wh": [(nominal_battery * value, {"drone": {"battery_Wh": nominal_battery * value}}, method) for value in bounds["battery_factor"]],
        "reaction_lever_arm_m": [(value, {"drone": {"reaction_lever_arm_m": [0.0, 0.0, -value]}}, method) for value in bounds["reaction_lever_arm_m"]],
        "incident_flux_W_m2": [(value, {"thermal": _merge(base_thermal, {"incident_flux_W_m2": value})}, method) for value in bounds["incident_flux_W_m2"]],
    }
    output: dict[str, list[dict[str, Any]]] = {}
    for factor, settings in specifications.items():
        rows = []
        for value, override, selected_method in settings:
            result = simulate_mission(_merge(config, override), selected_method, controller_enabled=True)
            rows.append({
                "value": float(value),
                "status": result["status"],
                "failures": result["failures"],
                "max_position_error_m": result["metrics"]["max_position_error_m"],
                "remaining_Wh": result["metrics"]["remaining_Wh"],
                "peak_temperature_K": result["metrics"]["peak_temperature_K"],
                "thrust_margin_N": result["metrics"]["thrust_margin_N"],
            })
        output[factor] = rows
    output["analytical_requirements"] = [{
        "payload_required_kg": payload,
        "hover_thrust_lower_bound_N": nominal["metrics"]["final_mass_kg"] * _G,
        "observed_peak_power_W": nominal["metrics"]["peak_power_W"],
        "observed_energy_Wh": nominal["metrics"]["energy_J"] / 3600.0,
        "basis": "unvalidated rigid-body and actuator-disk screening run",
    }]
    return output


def _matched_fire_retention(records: Iterable[Mapping[str, Any]] | None, method_id: str) -> dict[str, Any]:
    empty = {
        "eligible": False,
        "reason": "no_imported_loss_records",
        "blocks": 0,
        "R_D3": None,
        "R_D4": None,
        "net_D3_J_m2": None,
        "net_D4_J_m2": None,
        "block_results": [],
    }
    if records is None:
        return empty
    selected: list[dict[str, Any]] = []
    for index, raw in enumerate(records):
        if not isinstance(raw, Mapping):
            raise TypeError(f"imported_losses[{index}] must be a mapping")
        if raw.get("method_id") != method_id:
            continue
        row = dict(raw)
        for key in ("block_id", "condition_id", "match", "provenance"):
            if key not in row:
                raise ValueError(f"imported loss {index} missing {key}")
        if row["condition_id"] not in _CONDITIONS:
            raise ValueError(f"imported loss {index} condition_id must be D0-D4")
        row["loss_J_m2"] = _finite(row.get("loss_J_m2"), f"imported loss {index} loss_J_m2", minimum=0.0)
        if not isinstance(row["match"], Mapping) or not isinstance(row["provenance"], Mapping):
            raise TypeError(f"imported loss {index} match and provenance must be mappings")
        selected.append(row)
    if not selected:
        return empty
    if any(row["provenance"].get("evidence_type") not in _ELIGIBLE_FIRE_EVIDENCE for row in selected):
        return {**empty, "reason": "evidence_gate_failed"}

    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in selected:
        block = str(row["block_id"])
        if row["condition_id"] in grouped[block]:
            raise ValueError(f"duplicate imported loss for {method_id}/{block}/{row['condition_id']}")
        grouped[block][row["condition_id"]] = row

    results = []
    exclusions: list[str] = []
    for block, conditions in sorted(grouped.items()):
        if set(conditions) != set(_CONDITIONS):
            exclusions.append(f"{block}:missing_conditions")
            continue
        common_fields = ("distance_m", "start_time_s", "observation_window_s")
        if any(any(row["match"].get(field) != conditions["D0"]["match"].get(field) for field in common_fields) for row in conditions.values()):
            exclusions.append(f"{block}:geometry_or_time_mismatch")
            continue
        comparison_fields = ("budget", "material_ids")
        reference = conditions["D1"]["match"]
        if any(any(conditions[name]["match"].get(field) != reference.get(field) for field in comparison_fields) for name in ("D2", "D3", "D4")):
            exclusions.append(f"{block}:budget_or_material_mismatch")
            continue
        d0, d1, d2, d3, d4 = (conditions[name]["loss_J_m2"] for name in _CONDITIONS)
        denominator = d0 - d1
        if denominator <= 0.0:
            r3 = r4 = None
            reason = "nonpositive_fixed_device_benefit"
        else:
            r3 = (d2 - d3) / denominator
            r4 = (d2 - d4) / denominator
            reason = None
        results.append({
            "block_id": block,
            "R_D3": r3,
            "R_D4": r4,
            "net_D3_J_m2": d0 - d3,
            "net_D4_J_m2": d0 - d4,
            "reason": reason,
        })
    eligible = [row for row in results if row["R_D3"] is not None]
    if not results:
        return {**empty, "reason": ";".join(exclusions) or "no_complete_matched_blocks"}
    def paired_ci(field: str, rows: list[dict[str, Any]]) -> list[float] | None:
        values = np.asarray([row[field] for row in rows if row[field] is not None], dtype=float)
        if not len(values):
            return None
        rng = np.random.default_rng(42)
        replicates = [float(np.mean(rng.choice(values, size=len(values), replace=True))) for _ in range(500)]
        bounds = np.quantile(np.asarray(replicates), [0.025, 0.975])
        return [float(bounds[0]), float(bounds[1])]

    return {
        "eligible": bool(eligible),
        "reason": None if eligible else "no_positive_fixed_device_benefit",
        "blocks": len(results),
        "R_D3": float(np.mean([row["R_D3"] for row in eligible])) if eligible else None,
        "R_D4": float(np.mean([row["R_D4"] for row in eligible])) if eligible else None,
        "net_D3_J_m2": float(np.mean([row["net_D3_J_m2"] for row in results])),
        "net_D4_J_m2": float(np.mean([row["net_D4_J_m2"] for row in results])),
        "ci95": {
            "R_D3": paired_ci("R_D3", eligible),
            "R_D4": paired_ci("R_D4", eligible),
            "net_D3_J_m2": paired_ci("net_D3_J_m2", results),
            "net_D4_J_m2": paired_ci("net_D4_J_m2", results),
        },
        "ci_method": "paired block bootstrap, 500 replicates, seed 42",
        "block_results": results,
        "excluded": exclusions,
    }


def run_drone_study(
    config: Mapping[str, Any],
    method_results: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    imported_losses: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run D0-D5 flight comparisons, stress cases, and requirement sweeps.

    ``imported_losses`` is optional and is the only source used for fire-effect
    retention.  The flight model never fabricates D0-D4 heat-loss values.
    """
    if not isinstance(config, Mapping):
        raise TypeError("config must be a mapping")
    methods = _method_map(method_results)
    imported = list(imported_losses) if imported_losses is not None else None
    output: dict[str, Any] = {
        "study_id": "WP5_D0_D5",
        "evidence_type": "unvalidated_physics",
        "assumption_basis": {
            "D5": copy.deepcopy(DEFAULT_D5_ASSUMPTIONS),
            "sweeps": copy.deepcopy(DEFAULT_SWEEP_BOUNDS),
            "origin": "declared screening assumptions; replace with measured airframe, sensor, thermal, and environment limits",
        },
        "methods": {},
        "limitations": [
            "D0 and D1 are comparison definitions, not fabricated fire simulations.",
            "Rotor wake is ideal actuator-disk momentum theory; no rotor-resolved CFD field is claimed.",
            "Sensor, thermal, crosswind, payload, CG, and reaction results are screening calculations until calibrated.",
            "Fire-effect retention remains null unless complete matched imported D0-D4 loss records pass the evidence gate.",
        ],
    }
    for method_id, method in methods.items():
        ledger = _resource_ledger(config, method)
        controls = simulate_controls(config, method)
        d2 = simulate_mission(config, _inactive_method(method), controller_enabled=True)
        conditions = {
            "D0": _condition_record("D0", None, {"budget": {}, "material_ids": [], "material_identity_status": "not_applicable"}, "same fire without device or drone; external fire solver/experiment required"),
            "D1": _condition_record("D1", None, ledger, "fixed-device transport result only; no suppression loss inferred"),
            "D2": _condition_record("D2", d2, ledger, "mass-matched mounted device OFF with corrected flight"),
            "D3": _condition_record("D3", controls["uncorrected"], ledger, "device ON with nominal attitude loop and no disturbance position correction"),
            "D4": _condition_record("D4", controls["corrected"], ledger, "device ON with position and attitude correction"),
        }
        conditions["D1"]["transport"] = copy.deepcopy(method)
        d5 = {}
        for scenario_id, specification in _d5_configs(config, method).items():
            mission = simulate_mission(specification["config"], specification["method"], controller_enabled=True)
            d5[scenario_id] = {
                "condition_id": "D5",
                "scenario_id": scenario_id,
                "flight": mission,
                "assumption_status": "declared_screening_assumption",
                "fire_loss_J_m2": None,
            }
        thermal_status = "evaluated_with_explicit_inputs" if config.get("thermal") is not None else "insufficient_evidence"
        output["methods"][method_id] = {
            "conditions": conditions,
            "D5": d5,
            "wake": _ideal_wake(controls["corrected"]),
            "thermal_assessment_status": thermal_status,
            "practical_effectiveness_status": "insufficient_evidence",
            "practical_effectiveness_reason": (
                "airframe, rotor-wake, sensor, component thermal, and fire-effect inputs have not all been independently measured and validated"
            ),
            "requirements": _sweep(config, method, controls["corrected"]),
            "fire_retention": _matched_fire_retention(imported, method_id),
        }
    return output


def write_drone_study_exports(result: Mapping[str, Any], output_dir: str | Path) -> dict[str, str]:
    """Write the JSON result plus flat feasibility, mission, and sweep CSVs."""
    if not isinstance(result, Mapping) or not isinstance(result.get("methods"), Mapping):
        raise ValueError("result must be a run_drone_study output")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "drone_study.json"
    feasibility_path = destination / "drone_feasibility.csv"
    series_path = destination / "drone_mission_series.csv"
    requirements_path = destination / "drone_requirements.csv"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")

    feasibility_rows = []
    series_rows = []
    requirement_rows = []
    for method_id, study in result["methods"].items():
        missions: list[tuple[str, str, Mapping[str, Any]]] = []
        for condition_id, condition in study["conditions"].items():
            if condition.get("flight") is not None:
                missions.append((condition_id, "nominal", condition["flight"]))
        for scenario_id, condition in study["D5"].items():
            missions.append(("D5", scenario_id, condition["flight"]))
        for condition_id, scenario_id, mission in missions:
            metrics = mission["metrics"]
            feasibility_rows.append({
                "method_id": method_id,
                "condition_id": condition_id,
                "scenario_id": scenario_id,
                "status": mission["status"],
                "failures": "|".join(mission["failures"]),
                "energy_J": metrics["energy_J"],
                "remaining_Wh": metrics["remaining_Wh"],
                "max_position_error_m": metrics["max_position_error_m"],
                "peak_power_W": metrics["peak_power_W"],
                "thrust_margin_N": metrics["thrust_margin_N"],
                "peak_temperature_K": metrics["peak_temperature_K"],
                "peak_reaction_torque_Nm": metrics["peak_reaction_torque_Nm"],
            })
            for row in mission["series"]:
                series_rows.append({"method_id": method_id, "condition_id": condition_id, "scenario_id": scenario_id, **row})
        for factor, rows in study["requirements"].items():
            if factor == "analytical_requirements":
                continue
            for row in rows:
                requirement_rows.append({
                    "method_id": method_id,
                    "factor": factor,
                    "value": row["value"],
                    "status": row["status"],
                    "failures": "|".join(row["failures"]),
                    "max_position_error_m": row["max_position_error_m"],
                    "remaining_Wh": row["remaining_Wh"],
                    "peak_temperature_K": row["peak_temperature_K"],
                    "thrust_margin_N": row["thrust_margin_N"],
                })

    def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
        fields = list(rows[0]) if rows else ["method_id"]
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    write_csv(feasibility_path, feasibility_rows)
    write_csv(series_path, series_rows)
    write_csv(requirements_path, requirement_rows)
    return {
        "json": str(json_path),
        "feasibility_csv": str(feasibility_path),
        "mission_series_csv": str(series_path),
        "requirements_csv": str(requirements_path),
    }


__all__ = [
    "DEFAULT_D5_ASSUMPTIONS",
    "DEFAULT_SWEEP_BOUNDS",
    "run_drone_study",
    "write_drone_study_exports",
]
