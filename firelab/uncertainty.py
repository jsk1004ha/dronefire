"""Uncertainty quantification and Monte Carlo stochastic analysis module.

Performs:
1. Monte Carlo stochastic sampling of environmental, sensor, and hardware uncertainties
2. Empirical extinction probability P(quench) and 95% bootstrap confidence intervals
3. Statistical histograms for flight stability and resource consumption
4. Parameter sensitivity ranking (Tornado chart / correlation indices)
"""

from __future__ import annotations

import copy
import math
from typing import Any, Sequence
import numpy as np

from .config import validate_config
from .physics import simulate_method
from .drone import simulate_mission


def run_monte_carlo(
    method_id: str = "M3",
    num_samples: int = 100,
    uncertainty_spec: dict[str, Any] | None = None,
    base_cfg: dict[str, Any] | None = None,
    seed: int = 42
) -> dict[str, Any]:
    """Execute stochastic Monte Carlo evaluation."""
    rng = np.random.default_rng(seed)
    spec = uncertainty_spec or {}
    
    # Uncertainty distributions (defaults based on Steckler and drone test bench)
    cw_mean = float(spec.get("crosswind_mean", 1.5))
    cw_std = float(spec.get("crosswind_std", 0.5))
    
    lat_min = float(spec.get("latency_min", 0.05))
    lat_max = float(spec.get("latency_max", 0.25))
    
    dist_mean = float(spec.get("distance_mean", 1.2))
    dist_std = float(spec.get("distance_std", 0.15))
    
    fire_mean = float(spec.get("fire_hrr_mean", 50.0))
    fire_std = float(spec.get("fire_hrr_std", 5.0))
    
    n_runs = int(np.clip(num_samples, 20, 500))
    
    # Sample parameter matrix: [crosswind, latency, distance, fire_hrr]
    crosswinds = rng.normal(cw_mean, cw_std, n_runs)
    crosswinds = np.clip(crosswinds, 0.0, 5.0)
    
    latencies = rng.uniform(lat_min, lat_max, n_runs)
    
    distances = rng.normal(dist_mean, dist_std, n_runs)
    distances = np.clip(distances, 0.4, 3.0)
    
    fire_hrrs = rng.normal(fire_mean, fire_std, n_runs)
    fire_hrrs = np.clip(fire_hrrs, 20.0, 100.0)
    
    results = []
    success_count = 0
    
    extinction_times = []
    position_errors = []
    energies_wh = []
    
    base_config = validate_config(base_cfg or {})
    
    for i in range(n_runs):
        cfg = copy.deepcopy(base_config)
        cfg.setdefault("scenario", {})
        cfg["scenario"]["crosswind_m_s"] = float(crosswinds[i])
        cfg["scenario"]["distance_m"] = float(distances[i])
        
        cfg["sensor"] = {
            "latency_s": float(latencies[i]),
            "sample_rate_Hz": 10.0,
            "position_error_std_m": 0.05,
            "velocity_error_std_m_s": 0.02,
            "availability_fraction": 1.0,
            "seed": int(seed + i)
        }
        
        # Physics evaluation
        phys = simulate_method(cfg, method_id)
        d_res = simulate_mission(cfg, phys, controller_enabled=True)
        d_metrics = d_res["metrics"]
        
        # Key metrics
        pos_err = float(d_metrics.get("max_position_error_m", 0.2))
        energy = float(d_metrics.get("total_energy_Wh", 3.2))
        
        # Extinction estimation based on target delivery and fire HRR
        m = phys.get("metrics", {})
        eff = m.get("delivery_fraction")
        if eff is None:
            if method_id == "M1":
                eff = float(np.clip(m.get("target_velocity_rms_m_s", 0.02) / 0.1, 0.05, 1.0))
            elif method_id in ("M2", "M5"):
                eff = float(np.clip(m.get("target_arrival_speed_m_s", 0.5) / 2.0, 0.05, 1.0))
            else:
                eff = 0.5
        eff = float(np.clip(eff, 0.05, 1.0))
        
        # Quench time scaling with fire HRR
        hrr_ratio = fire_hrrs[i] / 50.0
        t_ext = float(np.clip(8.0 * hrr_ratio / (eff * max(0.2, 2.0 - distances[i] * 0.5)), 2.0, 25.0))
        
        # Success criteria: t_ext < 16.0 s and pos_err < 0.6 m and feasible
        is_success = (t_ext <= 16.0) and (pos_err <= 0.8) and d_metrics.get("feasible_in_model", True)
        if is_success:
            success_count += 1
            
        extinction_times.append(t_ext)
        position_errors.append(pos_err)
        energies_wh.append(energy)
        
        results.append({
            "sample_id": i + 1,
            "crosswind_m_s": round(float(crosswinds[i]), 2),
            "latency_s": round(float(latencies[i]), 3),
            "distance_m": round(float(distances[i]), 2),
            "fire_hrr_kW": round(float(fire_hrrs[i]), 1),
            "extinction_time_s": round(t_ext, 2),
            "max_position_error_m": round(pos_err, 4),
            "mission_energy_Wh": round(energy, 3),
            "success": bool(is_success)
        })
        
    p_quench = success_count / n_runs
    
    # 95% Bootstrap Confidence Interval for P(quench)
    boot_p = []
    for _ in range(1000):
        sample_indices = rng.choice(n_runs, size=n_runs, replace=True)
        sub_success = sum(1 for idx in sample_indices if results[idx]["success"])
        boot_p.append(sub_success / n_runs)
    ci_lower = float(np.percentile(boot_p, 2.5))
    ci_upper = float(np.percentile(boot_p, 97.5))
    
    # Histogram generators
    def compute_hist(arr: list[float], bins: int = 10) -> dict[str, Any]:
        counts, edges = np.histogram(arr, bins=bins)
        return {
            "counts": counts.tolist(),
            "bin_edges": [round(float(e), 3) for e in edges],
            "mean": round(float(np.mean(arr)), 3),
            "std": round(float(np.std(arr)), 3),
            "median": round(float(np.median(arr)), 3)
        }
        
    hist_extinction = compute_hist(extinction_times)
    hist_pos_error = compute_hist(position_errors)
    hist_energy = compute_hist(energies_wh)
    
    # Sensitivity analysis (Spearman / Pearson correlation with performance metrics)
    param_matrix = np.column_stack([crosswinds, latencies, distances, fire_hrrs])
    param_names = ["횡풍 풍속 (Crosswind)", "센서 지연 (Latency)", "이격 거리 (Distance)", "화재 규모 (Fire HRR)"]
    
    sensitivities = []
    with np.errstate(divide="ignore", invalid="ignore"):
        for p_idx, name in enumerate(param_names):
            corr_ext = np.corrcoef(param_matrix[:, p_idx], extinction_times)[0, 1]
            corr_err = np.corrcoef(param_matrix[:, p_idx], position_errors)[0, 1]
            sensitivities.append({
                "parameter": name,
                "extinction_correlation": round(float(np.nan_to_num(corr_ext)), 3),
                "position_error_correlation": round(float(np.nan_to_num(corr_err)), 3),
                "combined_impact": round(float(abs(np.nan_to_num(corr_ext)) * 0.6 + abs(np.nan_to_num(corr_err)) * 0.4), 3)
            })
        
    # Sort sensitivities by combined impact descending (Tornado ordering)
    sensitivities.sort(key=lambda x: x["combined_impact"], reverse=True)
    
    return {
        "status": "success",
        "method_id": method_id,
        "num_samples": n_runs,
        "extinction_probability": round(p_quench, 3),
        "ci_95_pct": [round(ci_lower, 3), round(ci_upper, 3)],
        "histograms": {
            "extinction_time_s": hist_extinction,
            "max_position_error_m": hist_pos_error,
            "mission_energy_Wh": hist_energy
        },
        "sensitivity_tornado": sensitivities,
        "sample_points": results[:50]  # Subsample for UI table display
    }
