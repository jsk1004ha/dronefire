"""One-dimensional unipolar electrohydrodynamic transport model.

This module solves electrostatic Poisson coupling and conservative charge
drift-diffusion between planar electrodes.  It intentionally omits corona
generation, plasma chemistry, gas momentum evolution, three-dimensional
geometry and flame interaction.
"""

from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
from typing import Mapping

import numpy as np


EPSILON_0_F_M = 8.8541878128e-12

DEFAULT_CONFIG = {
    "gap_m": 0.1,
    "voltage_V": 10.0,
    "ground_voltage_V": 0.0,
    "relative_permittivity": 1.0,
    "charge_mobility_m2_V_s": 2.0e-4,
    "charge_diffusion_m2_s": 1.0e-5,
    "injected_charge_density_C_m3": 1.0e-10,
    "initial_charge_density_C_m3": 0.0,
    "gas_density_kg_m3": 1.2,
    "cells": 64,
    "duration_s": 0.1,
    "dt_max_s": 1.0e-3,
    "cfl": 0.45,
    "max_saved_frames": 101,
}


class EHDInputError(ValueError):
    """Raised when a model input or numerical invariant is invalid."""


def _config(overrides: Mapping | None) -> dict:
    result = copy.deepcopy(DEFAULT_CONFIG)
    if overrides:
        unknown = set(overrides) - set(result)
        if unknown:
            raise EHDInputError(f"unknown EHD configuration keys: {sorted(unknown)}")
        result.update(overrides)
    integer_keys = {"cells", "max_saved_frames"}
    for key, value in result.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise EHDInputError(f"{key} must be numeric")
        if key in integer_keys and not isinstance(value, int):
            raise EHDInputError(f"{key} must be an integer")
        if not math.isfinite(float(value)):
            raise EHDInputError(f"{key} must be finite")
    if not 0.001 <= result["gap_m"] <= 10.0:
        raise EHDInputError("gap_m must be in [0.001, 10]")
    if not -1.0e6 <= result["voltage_V"] <= 1.0e6 or not -1.0e6 <= result["ground_voltage_V"] <= 1.0e6:
        raise EHDInputError("electrode voltages must be within +/-1 MV")
    if not 0.1 <= result["relative_permittivity"] <= 100.0:
        raise EHDInputError("relative_permittivity must be in [0.1, 100]")
    for key in (
        "charge_mobility_m2_V_s",
        "charge_diffusion_m2_s",
        "injected_charge_density_C_m3",
        "initial_charge_density_C_m3",
        "gas_density_kg_m3",
        "duration_s",
        "dt_max_s",
    ):
        if result[key] < 0:
            raise EHDInputError(f"{key} cannot be negative")
    if result["gas_density_kg_m3"] <= 0 or result["dt_max_s"] <= 0 or result["duration_s"] <= 0:
        raise EHDInputError("gas density, duration and maximum time step must be positive")
    if not 8 <= result["cells"] <= 4096:
        raise EHDInputError("cells must be in [8, 4096]")
    if not 2 <= result["max_saved_frames"] <= 1001:
        raise EHDInputError("max_saved_frames must be in [2, 1001]")
    if not 0 < result["cfl"] <= 0.9:
        raise EHDInputError("cfl must be in (0, 0.9]")
    return result


def _tridiagonal(lower: np.ndarray, diagonal: np.ndarray, upper: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    n = len(diagonal)
    if n == 0:
        return np.empty(0)
    c = upper.astype(float, copy=True)
    d = rhs.astype(float, copy=True)
    b = diagonal.astype(float, copy=True)
    for i in range(1, n):
        if abs(b[i - 1]) < 1.0e-300:
            raise EHDInputError("singular Poisson system")
        factor = lower[i - 1] / b[i - 1]
        b[i] -= factor * c[i - 1]
        d[i] -= factor * d[i - 1]
    solution = np.empty(n)
    solution[-1] = d[-1] / b[-1]
    for i in range(n - 2, -1, -1):
        solution[i] = (d[i] - c[i] * solution[i + 1]) / b[i]
    return solution


def _solve_poisson(
    charge_cells_C_m3: np.ndarray,
    dx_m: float,
    left_voltage_V: float,
    right_voltage_V: float,
    permittivity_F_m: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return node potential and cell electric field for cell-average charge."""
    charge = np.asarray(charge_cells_C_m3, dtype=float)
    if charge.ndim != 1 or len(charge) < 2 or not np.all(np.isfinite(charge)):
        raise EHDInputError("charge density must be a finite one-dimensional array")
    if dx_m <= 0 or permittivity_F_m <= 0:
        raise EHDInputError("dx and permittivity must be positive")
    n_internal = len(charge) - 1
    charge_nodes = 0.5 * (charge[:-1] + charge[1:])
    rhs = -(dx_m * dx_m / permittivity_F_m) * charge_nodes
    rhs[0] -= left_voltage_V
    rhs[-1] -= right_voltage_V
    internal = _tridiagonal(
        np.ones(n_internal - 1),
        np.full(n_internal, -2.0),
        np.ones(n_internal - 1),
        rhs,
    )
    potential = np.concatenate(([left_voltage_V], internal, [right_voltage_V]))
    electric_field = -np.diff(potential) / dx_m
    return potential, electric_field


def _face_flux(
    charge: np.ndarray,
    electric_cells: np.ndarray,
    dx: float,
    mobility: float,
    diffusion: float,
    injected_charge: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(charge)
    electric_faces = np.empty(n + 1)
    electric_faces[0] = electric_cells[0]
    electric_faces[-1] = electric_cells[-1]
    electric_faces[1:-1] = 0.5 * (electric_cells[:-1] + electric_cells[1:])
    drift_velocity = mobility * electric_faces
    flux = np.empty(n + 1)

    # Fixed charge-density injection boundary at x=0.  At x=L, inward drift
    # sees zero exterior charge while outward drift uses the last cell.
    flux[0] = drift_velocity[0] * (injected_charge if drift_velocity[0] >= 0 else charge[0])
    flux[0] -= diffusion * (charge[0] - injected_charge) / (0.5 * dx)
    for face in range(1, n):
        upstream = charge[face - 1] if drift_velocity[face] >= 0 else charge[face]
        flux[face] = drift_velocity[face] * upstream - diffusion * (charge[face] - charge[face - 1]) / dx
    flux[-1] = drift_velocity[-1] * (charge[-1] if drift_velocity[-1] >= 0 else 0.0)
    # Zero diffusive gradient at the collecting/outflow electrode.
    conduction = mobility * np.maximum(charge, 0.0) * electric_cells
    return flux, conduction, electric_faces


def simulate_ehd(config: Mapping | None = None) -> dict:
    """Run the conservative 1-D planar Poisson/drift-diffusion model."""
    cfg = _config(config)
    n = cfg["cells"]
    gap = cfg["gap_m"]
    dx = gap / n
    nodes = np.linspace(0.0, gap, n + 1)
    centers = 0.5 * (nodes[:-1] + nodes[1:])
    permittivity = EPSILON_0_F_M * cfg["relative_permittivity"]
    charge = np.full(n, cfg["initial_charge_density_C_m3"], dtype=float)
    initial_charge = float(charge.sum() * dx)
    boundary_charge_entered = 0.0
    time_s = 0.0
    step = 0
    minimum_dt = math.inf
    maximum_cfl = 0.0
    frames: list[dict] = []
    save_interval = cfg["duration_s"] / (cfg["max_saved_frames"] - 1)
    next_save_time = save_interval

    def diagnostics(current_time: float, potential: np.ndarray, electric: np.ndarray, flux: np.ndarray, conduction: np.ndarray) -> dict:
        force_density = charge * electric
        force_per_area = float(np.sum(force_density) * dx)
        conduction_power = float(np.sum(conduction * electric) * dx)
        return {
            "time_s": float(current_time),
            "total_charge_C_m2": float(charge.sum() * dx),
            "left_current_density_A_m2": float(flux[0]),
            "right_current_density_A_m2": float(flux[-1]),
            "mean_conduction_current_density_A_m2": float(conduction.mean()),
            "conduction_power_W_m2": conduction_power,
            "electric_force_N_m2": force_per_area,
            "electric_force_acceleration_scale_m_s2": force_per_area / (cfg["gas_density_kg_m3"] * gap),
            "minimum_charge_density_C_m3": float(charge.min()),
            "maximum_charge_density_C_m3": float(charge.max()),
            "peak_electric_field_V_m": float(np.max(np.abs(electric))),
            "left_potential_V": float(potential[0]),
            "right_potential_V": float(potential[-1]),
        }

    while time_s < cfg["duration_s"] - 1.0e-15:
        potential, electric = _solve_poisson(
            charge,
            dx,
            cfg["voltage_V"],
            cfg["ground_voltage_V"],
            permittivity,
        )
        flux, conduction, _ = _face_flux(
            charge,
            electric,
            dx,
            cfg["charge_mobility_m2_V_s"],
            cfg["charge_diffusion_m2_s"],
            cfg["injected_charge_density_C_m3"],
        )
        if step == 0:
            frames.append(diagnostics(time_s, potential, electric, flux, conduction))
        max_drift = float(np.max(np.abs(cfg["charge_mobility_m2_V_s"] * electric)))
        stability_rate = max_drift + 4.0 * cfg["charge_diffusion_m2_s"] / dx
        stable_dt = cfg["cfl"] * dx / stability_rate if stability_rate > 0 else cfg["dt_max_s"]
        dt = min(cfg["dt_max_s"], stable_dt, cfg["duration_s"] - time_s)
        if not math.isfinite(dt) or dt <= 0:
            raise EHDInputError("computed time step is invalid")
        maximum_cfl = max(maximum_cfl, dt * stability_rate / dx)
        minimum_dt = min(minimum_dt, dt)
        updated = charge - (dt / dx) * (flux[1:] - flux[:-1])
        scale = max(float(charge.max()), cfg["injected_charge_density_C_m3"], 1.0e-30)
        if float(updated.min()) < -1.0e-12 * scale:
            raise EHDInputError("charge positivity was lost despite the stability bound")
        updated = np.maximum(updated, 0.0)
        boundary_charge_entered += dt * (float(flux[0]) - float(flux[-1]))
        charge = updated
        time_s += dt
        step += 1
        if time_s + 1.0e-15 >= next_save_time or time_s >= cfg["duration_s"] - 1.0e-15:
            potential, electric = _solve_poisson(
                charge, dx, cfg["voltage_V"], cfg["ground_voltage_V"], permittivity
            )
            flux, conduction, _ = _face_flux(
                charge,
                electric,
                dx,
                cfg["charge_mobility_m2_V_s"],
                cfg["charge_diffusion_m2_s"],
                cfg["injected_charge_density_C_m3"],
            )
            frames.append(diagnostics(time_s, potential, electric, flux, conduction))
            while next_save_time <= time_s + 1.0e-15:
                next_save_time += save_interval

    potential, electric = _solve_poisson(
        charge, dx, cfg["voltage_V"], cfg["ground_voltage_V"], permittivity
    )
    flux, conduction, _ = _face_flux(
        charge,
        electric,
        dx,
        cfg["charge_mobility_m2_V_s"],
        cfg["charge_diffusion_m2_s"],
        cfg["injected_charge_density_C_m3"],
    )
    final_charge = float(charge.sum() * dx)
    ledger_residual = final_charge - initial_charge - boundary_charge_entered
    ledger_scale = max(abs(final_charge), abs(initial_charge), abs(boundary_charge_entered), 1.0e-30)
    final_force = float(np.sum(charge * electric) * dx)
    return {
        "schema_version": "1.0",
        "model": "1D planar unipolar Poisson charge drift-diffusion",
        "status": "computed_numerical_model_only",
        "validation_status": "unvalidated_hypothetical_parameters",
        "config": cfg,
        "equations": {
            "poisson": "d2(phi)/dx2 = -q/epsilon",
            "electric_field": "E = -d(phi)/dx",
            "charge_conservation": "dq/dt + dJ/dx = 0",
            "charge_flux": "J = mobility*q*E - diffusion*dq/dx",
            "electric_body_force": "f = q*E",
        },
        "grid": {
            "node_x_m": nodes.tolist(),
            "cell_center_x_m": centers.tolist(),
            "dx_m": dx,
        },
        "numerics": {
            "poisson": "second-order centered finite difference, direct tridiagonal solve",
            "charge": "conservative finite volume, upwind drift, centered diffusion, explicit Euler",
            "steps": step,
            "minimum_dt_s": minimum_dt,
            "maximum_combined_cfl": maximum_cfl,
            "positivity_preserved": bool(np.all(charge >= 0)),
        },
        "charge_ledger": {
            "initial_charge_C_m2": initial_charge,
            "net_boundary_charge_entered_C_m2": boundary_charge_entered,
            "final_charge_C_m2": final_charge,
            "residual_C_m2": ledger_residual,
            "relative_residual": abs(ledger_residual) / ledger_scale,
        },
        "metrics": {
            "electric_force_N_m2": final_force,
            "electric_force_acceleration_scale_m_s2": final_force / (cfg["gas_density_kg_m3"] * gap),
            "mean_conduction_current_density_A_m2": float(conduction.mean()),
            "conduction_power_W_m2": float(np.sum(conduction * electric) * dx),
            "peak_electric_field_V_m": float(np.max(np.abs(electric))),
            "minimum_charge_density_C_m3": float(charge.min()),
            "maximum_charge_density_C_m3": float(charge.max()),
        },
        "profiles": {
            "potential_node_V": potential.tolist(),
            "electric_field_cell_V_m": electric.tolist(),
            "charge_density_cell_C_m3": charge.tolist(),
            "electric_force_density_cell_N_m3": (charge * electric).tolist(),
            "conduction_current_density_cell_A_m2": conduction.tolist(),
        },
        "series": frames,
        "limitations": [
            "No corona onset, ionization, recombination, plasma chemistry or electrode sheath model.",
            "No gas-flow momentum solve; integrated qE divided by gas mass is a force-only acceleration scale, not a velocity prediction or rigorous upper bound.",
            "One-dimensional planar geometry does not represent a wire, needle, vortex, drone, or flame.",
            "Default 10 V parameters are a hypothetical numerical verification case, not measured M5 calibration.",
        ],
    }


def verification(output_dir: str | os.PathLike[str] | None = None) -> dict:
    """Run analytical, conservation, grid and time-refinement checks."""
    gap = 0.1
    voltage = 10.0
    epsilon = EPSILON_0_F_M

    zero_charge = np.zeros(64)
    phi_zero, _ = _solve_poisson(zero_charge, gap / 64, voltage, 0.0, epsilon)
    x_zero = np.linspace(0.0, gap, 65)
    exact_zero = voltage * (1.0 - x_zero / gap)
    charge_free_error = float(np.max(np.abs(phi_zero - exact_zero)))

    constant_charge = 1.0e-10
    phi_constant, _ = _solve_poisson(np.full(64, constant_charge), gap / 64, voltage, 0.0, epsilon)
    exact_constant = voltage * (1.0 - x_zero / gap) + constant_charge * x_zero * (gap - x_zero) / (2.0 * epsilon)
    constant_charge_error = float(np.max(np.abs(phi_constant - exact_constant)))

    spatial_errors = []
    rho0 = 1.0e-10
    wave = math.pi / gap
    for cells in (16, 32, 64, 128):
        dx = gap / cells
        centers = (np.arange(cells) + 0.5) * dx
        charge = rho0 * (1.0 + np.sin(wave * centers))
        phi, _ = _solve_poisson(charge, dx, voltage, 0.0, epsilon)
        x = np.linspace(0.0, gap, cells + 1)
        exact = (
            voltage
            + (rho0 * gap / (2.0 * epsilon) - voltage / gap) * x
            - rho0 * x * x / (2.0 * epsilon)
            + rho0 * np.sin(wave * x) / (epsilon * wave * wave)
        )
        spatial_errors.append(float(np.sqrt(np.mean((phi - exact) ** 2))))
    spatial_orders = [math.log(a / b, 2.0) for a, b in zip(spatial_errors, spatial_errors[1:])]

    temporal_profiles = []
    for dt in (0.01, 0.005, 0.00125):
        run = simulate_ehd(
            {
                "cells": 128,
                "duration_s": 0.2,
                "dt_max_s": dt,
                "charge_diffusion_m2_s": 0.0,
                "injected_charge_density_C_m3": 1.0e-12,
                "max_saved_frames": 2,
            }
        )
        temporal_profiles.append(np.asarray(run["profiles"]["charge_density_cell_C_m3"]))
    temporal_errors = [
        float(np.mean(np.abs(temporal_profiles[0] - temporal_profiles[2]))),
        float(np.mean(np.abs(temporal_profiles[1] - temporal_profiles[2]))),
    ]
    temporal_order = math.log(temporal_errors[0] / temporal_errors[1], 2.0) if temporal_errors[1] > 0 else math.inf

    ledger_run = simulate_ehd(
        {
            "duration_s": 0.05,
            "injected_charge_density_C_m3": 1.0e-10,
            "initial_charge_density_C_m3": 2.0e-11,
        }
    )
    ledger_error = ledger_run["charge_ledger"]["relative_residual"]
    checks = {
        "charge_free_linear_potential": charge_free_error < 1.0e-11,
        "constant_charge_poisson_solution": constant_charge_error < 1.0e-10,
        "second_order_spatial_convergence": min(spatial_orders[-2:]) > 1.8,
        "time_refinement_reduces_error": temporal_errors[1] < temporal_errors[0],
        "charge_conservation": ledger_error < 1.0e-11,
        "positivity": ledger_run["numerics"]["positivity_preserved"],
    }
    result = {
        "schema_version": "1.0",
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "charge_free_max_abs_potential_error_V": charge_free_error,
        "constant_charge_max_abs_potential_error_V": constant_charge_error,
        "spatial_refinement": {"cells": [16, 32, 64, 128], "l2_error_V": spatial_errors, "observed_orders": spatial_orders},
        "temporal_refinement": {"dt_max_s": [0.01, 0.005, 0.00125], "l1_errors_vs_finest_C_m3": temporal_errors, "observed_order": temporal_order},
        "charge_ledger_relative_residual": ledger_error,
        "scope": "numerical verification only; no M5 device or fire-suppression validation",
    }
    if output_dir is not None:
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        (target / "ehd_verification.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )
    return result


__all__ = ["EPSILON_0_F_M", "DEFAULT_CONFIG", "EHDInputError", "simulate_ehd", "verification"]
