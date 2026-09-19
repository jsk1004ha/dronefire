"""Multi-objective Pareto optimization module for drone-based fire suppression.

Formulates and solves multi-objective trade-offs between:
1. Minimizing extinction time / quench time: min(t_ext)
2. Minimizing drone mission energy consumption: min(E_tot)
3. Minimizing 6-DOF flight position error: min(e_max)
4. Maximizing agent delivery mass/energy efficiency: max(eta_target)
"""

from __future__ import annotations

import copy
import math
from typing import Any, Sequence
import numpy as np

from .config import validate_config
from .physics import simulate_method
from .drone import simulate_mission


def evaluate_point(
    method_id: str,
    distance_m: float,
    power_W: float,
    crosswind_m_s: float,
    controller_kp: float = 1.0,
    base_cfg: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Evaluate physics and flight metrics for a specific candidate design point."""
    cfg = validate_config(base_cfg or {})
    cfg.setdefault("scenario", {})["crosswind_m_s"] = float(crosswind_m_s)
    cfg["scenario"]["distance_m"] = float(distance_m)
    
    # Adjust method-specific power/discharge rate if applicable
    m_cfg = cfg.setdefault("methods", {}).setdefault(method_id, {})
    if method_id == "M1":
        m_cfg["electrical_power_W"] = float(power_W)
    elif method_id == "M2":
        m_cfg["pulse_energy_J"] = float(power_W * 0.2)
    elif method_id in ("M3", "M4"):
        m_cfg["discharge_rate_kg_s"] = float(np.clip(power_W * 0.001, 0.01, 0.20))
    elif method_id == "M5":
        m_cfg["electrode_voltage_kV"] = float(np.clip(power_W * 0.2, 5.0, 30.0))
        
    # Scale drone controller gains if requested
    c_cfg = cfg.setdefault("controller", {})
    c_cfg["position_kp"] = float(c_cfg.get("position_kp", 1.2) * controller_kp)
    
    # 1. Physics simulation
    phys = simulate_method(cfg, method_id)
    m = phys.get("metrics") or {}
    rx = phys.get("reaction_pulse") or {}
    
    # Target delivery efficiency
    delivery_eff = m.get("delivery_fraction")
    if delivery_eff is None:
        if method_id == "M1":
            delivery_eff = float(np.clip(m.get("target_velocity_rms_m_s", 0.02) / 0.1, 0.05, 1.0))
        elif method_id in ("M2", "M5"):
            delivery_eff = float(np.clip(m.get("target_arrival_speed_m_s", 0.5) / 2.0, 0.05, 1.0))
        else:
            delivery_eff = 0.5
    delivery_eff = float(np.clip(delivery_eff, 0.01, 1.0))
    
    # Extinction / quench time calculation based on target delivery flux and plume balance
    base_quench_s = 10.0
    flux_factor = m.get("target_velocity_rms_m_s") or m.get("target_arrival_speed_m_s") or 0.5
    attenuation_factor = 1.0 + delivery_eff * (power_W / 40.0)
    quench_time_s = float(np.clip(base_quench_s / max(0.2, (flux_factor / 2.0) * 0.5 + attenuation_factor * 0.5), 1.5, 30.0))
    
    # 2. Drone 6-DOF mission flight simulation
    d_res = simulate_mission(cfg, phys, controller_enabled=True)
    d_metrics = d_res["metrics"]
    
    pos_error_m = float(d_metrics.get("max_position_error_m", 0.1))
    energy_Wh = float(d_metrics.get("total_energy_Wh", 3.0))
    peak_power_W = float(d_metrics.get("peak_power_W", 45.0))
    tilt_deg = float(d_metrics.get("max_tilt_deg", 2.0))
    rf_raw = rx.get("peak_force_N") or phys.get("reaction_force_N") or 0.05
    if isinstance(rf_raw, (list, tuple, np.ndarray)):
        reaction_force_N = float(np.linalg.norm(rf_raw))
    else:
        reaction_force_N = float(rf_raw)
    
    return {
        "method_id": method_id,
        "distance_m": round(float(distance_m), 3),
        "power_W": round(float(power_W), 1),
        "crosswind_m_s": round(float(crosswind_m_s), 2),
        "controller_kp": round(float(controller_kp), 2),
        "objectives": {
            "extinction_time_s": round(quench_time_s, 2),
            "mission_energy_Wh": round(energy_Wh, 3),
            "max_position_error_m": round(pos_error_m, 4),
            "delivery_efficiency_pct": round(delivery_eff * 100.0, 1),
        },
        "auxiliary": {
            "peak_power_W": round(peak_power_W, 1),
            "max_tilt_deg": round(tilt_deg, 2),
            "reaction_force_N": round(reaction_force_N, 4),
            "feasible": bool(d_metrics.get("feasible_in_model", True)),
        }
    }


def find_pareto_front(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Non-dominated sorting to extract the Pareto frontier.
    
    Objectives to MINIMIZE:
    - extinction_time_s
    - mission_energy_Wh
    - max_position_error_m
    Objective to MAXIMIZE:
    - delivery_efficiency_pct (minimized as -delivery_efficiency_pct)
    """
    n = len(candidates)
    if n == 0:
        return []
        
    scores = np.zeros((n, 4))
    for i, c in enumerate(candidates):
        obj = c["objectives"]
        scores[i, 0] = obj["extinction_time_s"]
        scores[i, 1] = obj["mission_energy_Wh"]
        scores[i, 2] = obj["max_position_error_m"]
        scores[i, 3] = -obj["delivery_efficiency_pct"]
        
    is_dominated = np.zeros(n, dtype=bool)
    for i in range(n):
        for j in range(n):
            if i != j:
                # Does j dominate i? (j <= i in all, and j < i in at least one)
                if np.all(scores[j] <= scores[i]) and np.any(scores[j] < scores[i]):
                    is_dominated[i] = True
                    break
                    
    pareto_candidates = [candidates[i] for i in range(n) if not is_dominated[i]]
    return pareto_candidates


def run_optimization(spec: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute multi-objective Pareto exploration over a structured design grid."""
    spec = spec or {}
    methods: Sequence[str] = spec.get("methods", ["M1", "M2", "M3", "M4", "M5"])
    
    # Grid search bounds
    distances = spec.get("distance_range", [0.8, 1.2, 1.6, 2.0, 2.5])
    powers = spec.get("power_range", [20.0, 40.0, 60.0, 80.0, 100.0])
    crosswind = float(spec.get("crosswind_m_s", 1.5))
    kp_values = spec.get("kp_range", [0.9, 1.0, 1.2])
    
    candidates = []
    for method in methods:
        for d in distances:
            for p in powers:
                # Sample 1 or 2 representative kp values to keep evaluation fast
                for kp in kp_values[:2]:
                    pt = evaluate_point(
                        method_id=method,
                        distance_m=d,
                        power_W=p,
                        crosswind_m_s=crosswind,
                        controller_kp=kp,
                        base_cfg=spec.get("base_cfg")
                    )
                    candidates.append(pt)
                    
    pareto_front = find_pareto_front(candidates)
    
    # Identify knee / compromise point (closest to ideal in normalized objective space)
    if pareto_front:
        objs = np.array([
            [c["objectives"]["extinction_time_s"],
             c["objectives"]["mission_energy_Wh"],
             c["objectives"]["max_position_error_m"],
             -c["objectives"]["delivery_efficiency_pct"]]
            for c in pareto_front
        ])
        min_vals = objs.min(axis=0)
        max_vals = objs.max(axis=0)
        ranges = np.where(max_vals - min_vals > 1e-6, max_vals - min_vals, 1.0)
        norm_objs = (objs - min_vals) / ranges
        dist_to_ideal = np.linalg.norm(norm_objs, axis=1)
        best_idx = int(np.argmin(dist_to_ideal))
        knee_point = pareto_front[best_idx]
    else:
        knee_point = None
        
    return {
        "status": "success",
        "methods_evaluated": list(methods),
        "total_evaluated": len(candidates),
        "pareto_front_count": len(pareto_front),
        "pareto_front": pareto_front,
        "knee_point": knee_point,
        "sample_candidates": candidates[:60]  # Subsample for lightweight UI payload
    }
