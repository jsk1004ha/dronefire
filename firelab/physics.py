"""Screening transport models for five remote fire-control concepts.

These models compute delivery fields and resource balances only.  They do not
contain a combustion, extinction, or efficacy correlation and therefore never
return a synthetic suppression result.  All defaults are engineering
assumptions from CONTRACT.md, not measurements or calibration data.
"""

from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np


RHO_AIR = 1.204  # kg/m3, dry air near 293 K (assumed constant)
MU_AIR = 1.81e-5  # Pa s
NU_AIR = MU_AIR / RHO_AIR
RHO_WATER = 997.0  # kg/m3
RHO_PARTICLE = 1800.0  # kg/m3, placeholder passive solid density
SPEED_OF_SOUND = 343.0  # m/s
GRAVITY = 9.80665  # m/s2
STANDARD_PRESSURE = 101325.0  # Pa
MOLAR_MASS_DRY_AIR = 0.0289652  # kg/mol
MOLAR_MASS_WATER = 0.01801528  # kg/mol
LATENT_HEAT_WATER = 2.45e6  # J/kg, screening value near room temperature


DEFAULT_SCENARIO = {
    "duration_s": 4.0,
    "dt_s": 0.02,
    "distance_m": 1.0,
    "crosswind_m_s": 0.2,
    "ambient_K": 293.15,
    "target_radius_m": 0.2,
}

DEFAULT_METHODS: dict[str, dict[str, Any]] = {
    "M1": {"frequency_hz": 60.0, "velocity_rms_m_s": 0.4, "aperture_m": 0.15, "power_W": 80.0, "mass_kg": 0.5},
    "M2": {"exit_velocity_m_s": 8.0, "diameter_m": 0.10, "pulse_duration_s": 0.05, "period_s": 1.0, "power_W": 15.0, "mass_kg": 0.6, "stored_energy_J": 100.0},
    "M3": {"flow_kg_s": 0.005, "diameter_um": 100.0, "exit_velocity_m_s": 5.0, "power_W": 35.0, "mass_kg": 0.5, "payload_kg": 0.1},
    "M4": {"flow_kg_s": 0.001, "diameter_um": 5.0, "exit_velocity_m_s": 2.0, "power_W": 10.0, "mass_kg": 0.4, "payload_kg": 0.05},
    "M5": {"variant": "CV", "charge_density_C_m3": 0.0, "electric_field_V_m": 0.0, "flow_kg_s": 0.001, "diameter_um": 10.0, "exit_velocity_m_s": 8.0, "diameter_m": 0.10, "pulse_duration_s": 0.05, "period_s": 1.0, "power_W": 20.0, "mass_kg": 0.7, "payload_kg": 0.05, "stored_energy_J": 100.0},
}


def _finite_number(value: Any, name: str, low: float, high: float, *, low_open: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number) or number > high or (number <= low if low_open else number < low):
        bracket = "(" if low_open else "["
        raise ValueError(f"{name} must be in {bracket}{low}, {high}]")
    return number


def _inputs(config: dict[str, Any], method_id: str) -> tuple[dict[str, float], dict[str, Any], list[str]]:
    if method_id not in DEFAULT_METHODS:
        raise ValueError("method_id must be one of M1, M2, M3, M4, M5")
    config = config or {}
    scenario_raw = config.get("scenario", {})
    methods_raw = config.get("methods", {})
    if not isinstance(scenario_raw, dict) or not isinstance(methods_raw, dict):
        raise ValueError("scenario and methods must be objects")
    method_raw = methods_raw.get(method_id, {})
    if not isinstance(method_raw, dict):
        raise ValueError(f"methods.{method_id} must be an object")

    bounds = {
        "duration_s": (0.0, 60.0, True), "dt_s": (0.001, 0.5, False),
        "distance_m": (0.01, 20.0, False), "crosswind_m_s": (-20.0, 20.0, False),
        "ambient_K": (250.0, 400.0, False), "target_radius_m": (0.005, 5.0, False),
    }
    scenario: dict[str, float] = {}
    assumed: list[str] = []
    for key, default in DEFAULT_SCENARIO.items():
        if key not in scenario_raw:
            assumed.append(f"scenario.{key}={default}")
        lo, hi, open_lo = bounds[key]
        scenario[key] = _finite_number(scenario_raw.get(key, default), f"scenario.{key}", lo, hi, low_open=open_lo)
    if scenario["dt_s"] > scenario["duration_s"]:
        raise ValueError("scenario.dt_s cannot exceed scenario.duration_s")

    method = dict(DEFAULT_METHODS[method_id])
    for key, default in DEFAULT_METHODS[method_id].items():
        if key not in method_raw:
            assumed.append(f"methods.{method_id}.{key}={default}")
        else:
            method[key] = method_raw[key]
    numeric_limits = {
        "frequency_hz": (1.0, 2000.0), "velocity_rms_m_s": (0.0, 50.0), "aperture_m": (0.005, 5.0),
        "power_W": (0.0, 100000.0), "mass_kg": (0.0, 1000.0), "exit_velocity_m_s": (0.0, 200.0),
        "diameter_m": (0.005, 5.0), "pulse_duration_s": (0.001, 10.0), "period_s": (0.001, 30.0),
        "stored_energy_J": (0.0, 1e8), "flow_kg_s": (0.0, 10.0), "diameter_um": (0.1, 5000.0),
        "payload_kg": (0.0, 1000.0), "charge_density_C_m3": (-10.0, 10.0),
        "electric_field_V_m": (-1e8, 1e8),
    }
    for key in list(method):
        if key in numeric_limits:
            lo, hi = numeric_limits[key]
            method[key] = _finite_number(method[key], f"methods.{method_id}.{key}", lo, hi)
    for optional, default, lo, hi in (
        ("relative_humidity", 0.5, 0.0, 1.0), ("carrier_diameter_m", 0.05, 0.005, 2.0),
        ("circulation_efficiency", 0.35, 0.01, 1.0), ("ehd_length_m", 0.1, 0.001, 2.0),
    ):
        if optional in method_raw:
            method[optional] = _finite_number(method_raw[optional], f"methods.{method_id}.{optional}", lo, hi)
        elif optional in ("relative_humidity", "carrier_diameter_m") and method_id in ("M3", "M4"):
            method[optional] = default
            assumed.append(f"methods.{method_id}.{optional}={default}")
        elif optional == "circulation_efficiency" and method_id in ("M2", "M5"):
            method[optional] = default
            assumed.append(f"methods.{method_id}.{optional}={default}")
        elif optional == "ehd_length_m" and method_id == "M5":
            method[optional] = default
            assumed.append(f"methods.M5.{optional}={default}")
    if method_id in ("M2", "M5") and method["pulse_duration_s"] > method["period_s"]:
        raise ValueError(f"methods.{method_id}.pulse_duration_s cannot exceed period_s")
    return scenario, method, assumed


def _times(scenario: dict[str, float]) -> np.ndarray:
    count = int(math.floor(scenario["duration_s"] / scenario["dt_s"] + 1e-12))
    times = [index * scenario["dt_s"] for index in range(count + 1)]
    if scenario["duration_s"] - times[-1] > 1e-12:
        times.append(scenario["duration_s"])
    else:
        times[-1] = scenario["duration_s"]
    return np.asarray(times, dtype=float)


def _grid(distance: float, target_radius: float) -> np.ndarray:
    xmax = max(1.25 * distance, 0.5)
    width = max(2.5 * target_radius, 0.3)
    x = np.linspace(0.0, xmax, 11)
    y = np.linspace(-width, width, 7)
    z = np.linspace(-width, width, 5)
    return np.asarray(np.meshgrid(x, y, z, indexing="ij")).reshape(3, -1).T


def _clean_float(value: float) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ArithmeticError("model produced a non-finite value")
    return value


def _base_result(method_id: str, model: str, limitations: list[str], method: dict[str, Any], assumed: list[str]) -> dict[str, Any]:
    return {
        "method_id": method_id,
        "status": "computed_transport_only",
        "evidence_type": "unvalidated_physics",
        "model": model,
        "limitations": limitations,
        "assumptions": assumed,
        "metrics": {},
        "series": [],
        "field": {"points": [], "velocity": [], "scalar": [], "scalar_name": None, "unit": None},
        "reaction_force_N": [0.0, 0.0, 0.0],
        "reaction_pulse": None,
        "device_power_W": _clean_float(method["power_W"]),
        "device_mass_kg": _clean_float(method["mass_kg"]),
        "consumable_kg": 0.0,
        "loaded_consumable_kg": 0.0,
        "resource_status": {"status": "not_applicable", "reason": None},
        "suppression": {"status": "insufficient_evidence", "success_rate": None, "extinction_time_s": None},
    }


def _sample_indices(length: int, maximum: int = 201) -> np.ndarray:
    if length <= maximum:
        return np.arange(length)
    return np.unique(np.linspace(0, length - 1, maximum).round().astype(int))


def _simulate_m1(s: dict[str, float], m: dict[str, Any], assumed: list[str]) -> dict[str, Any]:
    result = _base_result("M1", "power-bounded linear acoustic hemisphere with analytic phase RMS", [
        "Linear, lossless air and hemispherical spreading from a baffled aperture are assumed; reflections, absorption, combustion coupling, and source near-field calibration are absent.",
        "Reported velocity is phase-averaged RMS. The vector sign is a display convention because oscillatory velocity has zero cycle mean.",
        "The source acoustic power is capped by device power at an assumed upper-bound electro-acoustic efficiency of one; real transducers require a measured efficiency and radiation impedance.",
        "The mean radiation reaction follows the forward-hemisphere momentum flux; vibration force RMS/peak remain plane-wave-equivalent screening values.",
    ], m, assumed)
    freq, u0, aperture = m["frequency_hz"], m["velocity_rms_m_s"], m["aperture_m"]
    radius = aperture / 2.0
    area = math.pi * radius * radius
    wavelength = SPEED_OF_SOUND / freq
    ka = 2.0 * math.pi * freq * radius / SPEED_OF_SOUND
    rayleigh = radius * radius / wavelength
    requested_power = RHO_AIR * SPEED_OF_SOUND * u0 * u0 * area
    acoustic_power = min(requested_power, m["power_W"])
    source_velocity = math.sqrt(acoustic_power / (RHO_AIR * SPEED_OF_SOUND * area)) if area > 0.0 else 0.0

    def amplitude(x: np.ndarray, radial: np.ndarray) -> np.ndarray:
        distance = np.sqrt(x * x + radial * radial)
        # rho*c*u_rms^2 integrated over the regularized forward hemisphere
        # is bounded by acoustic_power.  The aperture area removes the r=0
        # singularity and recovers source_velocity at the aperture.
        return source_velocity * np.sqrt(area / (area + 2.0 * math.pi * distance * distance))

    target_amp = float(amplitude(np.asarray([s["distance_m"]]), np.asarray([0.0]))[0])
    times = _times(s)
    indices = _sample_indices(len(times))
    result["series"] = [{
        "time_s": _clean_float(times[i]),
        "target_speed_m_s": target_amp,
        "instantaneous_target_velocity_m_s": _clean_float(math.sqrt(2.0) * target_amp * math.sin(2.0 * math.pi * freq * (times[i] - s["distance_m"] / SPEED_OF_SOUND))),
    } for i in indices]
    points = _grid(s["distance_m"], s["target_radius_m"])
    amp = amplitude(points[:, 0], np.hypot(points[:, 1], points[:, 2]))
    velocity = np.column_stack((amp, np.full(len(points), s["crosswind_m_s"]), np.zeros(len(points))))
    pressure_rms = RHO_AIR * SPEED_OF_SOUND * source_velocity
    radiation_reaction = acoustic_power / (2.0 * SPEED_OF_SOUND)
    result["field"] = {"points": points.tolist(), "velocity": velocity.tolist(), "scalar": amp.tolist(), "scalar_name": "oscillatory_velocity_rms", "unit": "m/s"}
    result["metrics"] = {
        "target_velocity_rms_m_s": target_amp,
        "requested_source_velocity_rms_m_s": u0,
        "effective_source_velocity_rms_m_s": source_velocity,
        "source_pressure_rms_Pa": pressure_rms,
        "vibration_force_rms_N": pressure_rms * area,
        "vibration_force_peak_N": math.sqrt(2.0) * pressure_rms * area,
        "source_acoustic_intensity_W_m2": RHO_AIR * SPEED_OF_SOUND * source_velocity * source_velocity,
        "requested_acoustic_power_W": requested_power,
        "source_acoustic_power_W": acoustic_power,
        "acoustic_energy_J": acoustic_power * s["duration_s"],
        "acoustic_power_limited": acoustic_power + 1e-12 < requested_power,
        "mean_radiation_reaction_N": radiation_reaction,
        "wavelength_m": wavelength,
        "ka": ka,
        "rayleigh_distance_m": rayleigh,
        "device_energy_J": m["power_W"] * s["duration_s"],
    }
    result["reaction_force_N"] = [-radiation_reaction, 0.0, 0.0]
    return result


def _ring_velocity(points: np.ndarray, center: np.ndarray, radius: float, core: float, circulation: float, segments: int = 40) -> np.ndarray:
    """Regularized Biot-Savart velocity of a circular filament in the yz plane."""
    theta = (np.arange(segments) + 0.5) * (2.0 * math.pi / segments)
    filament = center + np.column_stack((np.zeros(segments), radius * np.cos(theta), radius * np.sin(theta)))
    dl = np.column_stack((np.zeros(segments), -radius * np.sin(theta), radius * np.cos(theta))) * (2.0 * math.pi / segments)
    displacement = points[:, None, :] - filament[None, :, :]
    denominator = (np.sum(displacement * displacement, axis=2) + core * core) ** 1.5
    return circulation / (4.0 * math.pi) * np.sum(np.cross(dl[None, :, :], displacement) / denominator[:, :, None], axis=1)


def _pneumatic_budget(s: dict[str, float], m: dict[str, Any], *, include_particles: bool = False) -> dict[str, Any]:
    radius = m["diameter_m"] / 2.0
    area = math.pi * radius * radius
    births = np.arange(m["pulse_duration_s"], s["duration_s"] + 1e-12, m["period_s"])
    energy_per_pulse = 0.5 * RHO_AIR * area * m["exit_velocity_m_s"] ** 3 * m["pulse_duration_s"]
    requested_particle_kg = min(m.get("flow_kg_s", 0.0) * s["duration_s"], m.get("payload_kg", 0.0)) if include_particles else 0.0
    particle_energy_per_kg = 0.5 * m["exit_velocity_m_s"] ** 2
    particle_demand = requested_particle_kg * particle_energy_per_kg
    demand = energy_per_pulse * len(births) + particle_demand
    capacity = m["stored_energy_J"]
    affordable = len(births) if energy_per_pulse == 0.0 else min(len(births), int(math.floor((capacity + 1e-12) / energy_per_pulse)))
    remaining = max(capacity - affordable * energy_per_pulse, 0.0)
    affordable_particle_kg = requested_particle_kg if particle_energy_per_kg == 0.0 else min(requested_particle_kg, remaining / particle_energy_per_kg)
    sufficient = affordable == len(births) and affordable_particle_kg >= requested_particle_kg - 1e-12
    return {
        "status": "sufficient" if sufficient else "insufficient",
        "reason": None if sufficient else "Stored pneumatic energy is below the minimum exit-flow kinetic energy required for all requested pulses; simulation truncates unaffordable pulses.",
        "minimum_pneumatic_energy_demand_J": demand,
        "stored_energy_capacity_J": capacity,
        "requested_pulses": int(len(births)),
        "simulated_pulses": int(affordable),
        "energy_per_pulse_J": energy_per_pulse,
        "requested_particle_kg": requested_particle_kg,
        "affordable_particle_kg": affordable_particle_kg,
        "minimum_particle_kinetic_energy_J": particle_demand,
    }


def _ring_parameters(m: dict[str, Any]) -> dict[str, float | bool]:
    radius = m["diameter_m"] / 2.0
    core0 = max(0.12 * radius, 1e-4)
    stroke = m["exit_velocity_m_s"] * m["pulse_duration_s"]
    raw_circulation = m["circulation_efficiency"] * 0.5 * m["exit_velocity_m_s"] * stroke
    log_energy = max(math.log(8.0 * radius / core0) - 1.558, 0.0)
    slug_energy = 0.5 * RHO_AIR * math.pi * radius * radius * m["exit_velocity_m_s"] ** 3 * m["pulse_duration_s"]
    circulation_cap = math.sqrt(2.0 * slug_energy / (RHO_AIR * radius * log_energy)) if radius > 0.0 and log_energy > 0.0 else 0.0
    circulation = min(raw_circulation, circulation_cap)
    ring_energy = 0.5 * RHO_AIR * circulation * circulation * radius * log_energy
    impulse = RHO_AIR * math.pi * circulation * radius * radius
    return {
        "radius": radius,
        "core0": core0,
        "stroke": stroke,
        "formation_number": stroke / (2.0 * radius),
        "raw_circulation": raw_circulation,
        "circulation": circulation,
        "circulation_energy_capped": circulation + 1e-12 < raw_circulation,
        "slug_energy": slug_energy,
        "ring_energy": ring_energy,
        "impulse": impulse,
    }


def _ring_speed(radius: float, core: float, circulation: float) -> float:
    """Saffman thin Gaussian-core translation speed."""
    if radius <= 0.0 or circulation <= 0.0:
        return 0.0
    return circulation / (4.0 * math.pi * radius) * max(math.log(8.0 * radius / core) - 0.558, 0.0)


def _ring_travel(age: float, radius: float, core0: float, circulation: float, viscosity: float, max_step: float) -> float:
    """Integrate the viscously decreasing self-speed instead of using U(t)*t."""
    if age <= 0.0:
        return 0.0
    count = max(1, int(math.ceil(age / max(max_step, 1e-6))))
    dt = age / count
    travel = 0.0
    for index in range(count):
        left = index * dt
        right = (index + 1) * dt
        core_left = math.sqrt(core0 * core0 + 4.0 * viscosity * left)
        core_right = math.sqrt(core0 * core0 + 4.0 * viscosity * right)
        travel += 0.5 * (_ring_speed(radius, core_left, circulation) + _ring_speed(radius, core_right, circulation)) * dt
    return travel


def _ring_states(s: dict[str, float], m: dict[str, Any], times: np.ndarray, pulse_limit: int | None = None) -> tuple[list[list[dict[str, Any]]], dict[str, float | bool]]:
    ring = _ring_parameters(m)
    radius = float(ring["radius"])
    core0 = float(ring["core0"])
    circulation = float(ring["circulation"])
    births = np.arange(m["pulse_duration_s"], s["duration_s"] + 1e-12, m["period_s"])
    if pulse_limit is not None:
        births = births[:pulse_limit]
    all_states: list[list[dict[str, Any]]] = []
    for t in times:
        states: list[dict[str, Any]] = []
        for birth in births[births <= t + 1e-12]:
            age = float(t - birth)
            core = math.sqrt(core0 * core0 + 4.0 * NU_AIR * age)
            self_speed = _ring_speed(radius, core, circulation)
            center = np.asarray([_ring_travel(age, radius, core0, circulation, NU_AIR, s["dt_s"]), s["crosswind_m_s"] * age, 0.0])
            states.append({"center": center, "core": core, "circulation": circulation, "speed": self_speed, "age": age})
        all_states.append(states)
    return all_states, ring


def _simulate_m2(s: dict[str, float], m: dict[str, Any], assumed: list[str]) -> dict[str, Any]:
    result = _base_result("M2", "finite-core pulsed vortex rings with regularized Biot-Savart induction", [
        "The slug circulation relation includes an assumed nozzle circulation efficiency; ring formation and viscous core growth are not calibrated.",
        "Rings convect at their thin-ring self-induced speed plus uniform crosswind; walls, turbulence, ring breakdown, and combustion coupling are absent.",
        "Stored pneumatic energy is reported as a capacity and is not silently added to electrical energy.",
    ], m, assumed)
    times = _times(s)
    resource = _pneumatic_budget(s, m)
    states_by_time, ring = _ring_states(s, m, times, resource["simulated_pulses"])
    radius = float(ring["radius"])
    circulation = float(ring["circulation"])
    target = np.asarray([[s["distance_m"], 0.0, 0.0]])
    target_speed: list[float] = []
    for states in states_by_time:
        induced = np.zeros((1, 3))
        for state in states:
            induced += _ring_velocity(target, state["center"], radius, state["core"], state["circulation"])
        target_speed.append(float(np.linalg.norm(induced[0])))
    result["series"] = [{"time_s": _clean_float(times[i]), "target_speed_m_s": _clean_float(target_speed[i]), "active_rings": len(states_by_time[i])} for i in _sample_indices(len(times))]
    points = _grid(s["distance_m"], s["target_radius_m"])
    induced = np.zeros_like(points)
    for state in states_by_time[-1]:
        induced += _ring_velocity(points, state["center"], radius, state["core"], state["circulation"])
    display_velocity = induced + np.asarray([0.0, s["crosswind_m_s"], 0.0])
    area = math.pi * radius * radius
    peak_reaction = RHO_AIR * area * m["exit_velocity_m_s"] ** 2 if resource["simulated_pulses"] > 0 else 0.0
    duty = m["pulse_duration_s"] / m["period_s"]
    result["field"] = {"points": points.tolist(), "velocity": display_velocity.tolist(), "scalar": np.linalg.norm(induced, axis=1).tolist(), "scalar_name": "vortex_induced_speed", "unit": "m/s"}
    result["metrics"] = {
        "circulation_m2_s": circulation,
        "uncapped_slug_circulation_m2_s": ring["raw_circulation"],
        "circulation_energy_capped": ring["circulation_energy_capped"],
        "ring_radius_m": radius,
        "initial_core_radius_m": ring["core0"],
        "formation_number_L_over_D": ring["formation_number"],
        "hydrodynamic_impulse_N_s_per_ring": ring["impulse"],
        "thin_core_kinetic_energy_J_per_ring": ring["ring_energy"],
        "slug_kinetic_energy_J_per_pulse": ring["slug_energy"],
        "peak_target_speed_m_s": max(target_speed, default=0.0),
        "peak_reaction_force_N": peak_reaction,
        "cycle_average_reaction_force_N": peak_reaction * duty,
        "electrical_energy_J": m["power_W"] * s["duration_s"],
        "stored_energy_capacity_J": m["stored_energy_J"],
        "minimum_pneumatic_energy_demand_J": resource["minimum_pneumatic_energy_demand_J"],
        "simulated_pneumatic_energy_J": resource["energy_per_pulse_J"] * resource["simulated_pulses"],
    }
    result["reaction_force_N"] = [-peak_reaction, 0.0, 0.0]
    result["reaction_pulse"] = {
        "peak_force_N": [-peak_reaction, 0.0, 0.0],
        "peak_jet_force_N": [-peak_reaction, 0.0, 0.0],
        "steady_force_N": [0.0, 0.0, 0.0],
        "pulse_duration_s": m["pulse_duration_s"], "period_s": m["period_s"],
        "duty_cycle": duty, "simulated_pulses": resource["simulated_pulses"],
    }
    result["resource_status"] = resource
    if resource["status"] == "insufficient":
        result["limitations"].append(resource["reason"])
    return result


def _round_jet_velocity(points: np.ndarray, exit_velocity: float, diameter: float, crosswind: float) -> np.ndarray:
    x = np.maximum(points[:, 0], 0.0)
    spread = diameter / 2.0 + 0.10 * x
    centerline = exit_velocity * diameter / (diameter + 0.20 * x)
    radial = np.hypot(points[:, 1], points[:, 2])
    axial = centerline * np.exp(-0.5 * (radial / np.maximum(spread, 1e-6)) ** 2)
    return np.column_stack((axial, np.full(len(points), crosswind), np.zeros(len(points))))


def _water_evaporation_coefficient(temperature_K: float, relative_humidity: float) -> tuple[float, dict[str, float]]:
    """Return the isothermal Maxwell d^2 coefficient from vapor diffusion.

    Buck's saturation-pressure fit is only used inside its meteorological
    range.  The input temperature is clipped for this screening closure and
    the reported temperature lets callers identify out-of-range use.
    """
    closure_temperature = min(max(temperature_K, 253.15), 323.15)
    temperature_C = closure_temperature - 273.15
    saturation_pressure = 611.21 * math.exp((18.678 - temperature_C / 234.5) * temperature_C / (257.14 + temperature_C))
    saturation_mole_fraction = min(saturation_pressure / STANDARD_PRESSURE, 0.95)

    def mass_fraction(mole_fraction: float) -> float:
        numerator = mole_fraction * MOLAR_MASS_WATER
        return numerator / (numerator + (1.0 - mole_fraction) * MOLAR_MASS_DRY_AIR)

    surface_fraction = mass_fraction(saturation_mole_fraction)
    ambient_fraction = mass_fraction(relative_humidity * saturation_mole_fraction)
    vapor_diffusivity = 2.5e-5 * (closure_temperature / 293.15) ** 1.8
    coefficient = 8.0 * RHO_AIR * vapor_diffusivity / RHO_WATER * math.log((1.0 - ambient_fraction) / (1.0 - surface_fraction))
    return max(coefficient, 0.0), {
        "evaporation_closure_temperature_K": closure_temperature,
        "water_saturation_pressure_Pa": saturation_pressure,
        "surface_water_mass_fraction": surface_fraction,
        "ambient_water_mass_fraction": ambient_fraction,
        "water_vapor_diffusivity_m2_s": vapor_diffusivity,
    }


def _particle_transport(
    s: dict[str, float], m: dict[str, Any], *, evaporating: bool,
    air_velocity: Callable[[np.ndarray, float], np.ndarray], density: float,
) -> tuple[dict[str, float], list[dict[str, float]], list[dict[str, Any]], np.ndarray]:
    times = _times(s)
    diameter0 = m["diameter_um"] * 1e-6
    payload = m["payload_kg"]
    emitted = delivered = evaporated = deposited = escaped = 0.0
    parcels: list[dict[str, Any]] = []
    series: list[dict[str, float]] = []
    # Isothermal Maxwell d^2 law.  Heat transfer and Stefan-flow corrections
    # are intentionally not solved by this reduced transport model.
    humidity = m.get("relative_humidity", 0.5)
    evaporation_k, evaporation_state = _water_evaporation_coefficient(s["ambient_K"], humidity) if evaporating else (0.0, {})
    peak_reynolds = 0.0
    peak_drag_coefficient = 0.0

    for step, t in enumerate(times):
        dt = 0.0 if step == 0 else float(t - times[step - 1])
        if step > 0 and emitted < payload and m["flow_kg_s"] > 0.0:
            parcel_mass = min(m["flow_kg_s"] * dt, payload - emitted)
            if parcel_mass > 0.0:
                parcels.append({"p": np.asarray([0.0, 0.0, 0.0]), "v": np.asarray([m["exit_velocity_m_s"], 0.0, 0.0]), "m": parcel_mass, "d": diameter0})
                emitted += parcel_mass
        survivors: list[dict[str, Any]] = []
        for parcel in parcels:
            old_p = parcel["p"].copy()
            d = parcel["d"]
            if evaporating and d > 0.0:
                new_d2 = max(d * d - evaporation_k * dt, 0.0)
                new_d = math.sqrt(new_d2)
                new_mass = parcel["m"] * (new_d / d) ** 3 if d > 0.0 else 0.0
                evaporated += parcel["m"] - new_mass
                parcel["m"], parcel["d"] = new_mass, new_d
                if new_mass <= 1e-18:
                    continue
            air = air_velocity(parcel["p"][None, :], float(t))[0]
            old_velocity = parcel["v"].copy()
            relative = float(np.linalg.norm(old_velocity - air))
            reynolds = RHO_AIR * relative * max(parcel["d"], 1e-12) / MU_AIR
            correction = 1.0 + 0.15 * reynolds ** 0.687 if reynolds < 1000.0 else max(0.44 * reynolds / 24.0, 1.0)
            drag_coefficient = 24.0 * correction / max(reynolds, 1e-12)
            peak_reynolds = max(peak_reynolds, reynolds)
            peak_drag_coefficient = max(peak_drag_coefficient, drag_coefficient if reynolds > 1e-9 else 0.0)
            tau = density * parcel["d"] ** 2 / (18.0 * MU_AIR * correction)
            relax = math.exp(-dt / max(tau, 1e-9))
            gravity = np.asarray([0.0, 0.0, -GRAVITY * max(1.0 - RHO_AIR / density, 0.0)])
            terminal_velocity = air + tau * gravity
            parcel["v"] = terminal_velocity + (old_velocity - terminal_velocity) * relax
            parcel["p"] = old_p + terminal_velocity * dt + (old_velocity - terminal_velocity) * tau * (1.0 - relax)
            crossed = old_p[0] < s["distance_m"] <= parcel["p"][0]
            if crossed:
                fraction = (s["distance_m"] - old_p[0]) / max(parcel["p"][0] - old_p[0], 1e-12)
                yz = old_p[1:] + fraction * (parcel["p"][1:] - old_p[1:])
                if float(np.linalg.norm(yz)) <= s["target_radius_m"]:
                    delivered += parcel["m"]
                    continue
            if parcel["p"][2] < -max(2.5 * s["target_radius_m"], 0.3):
                deposited += parcel["m"]
                continue
            if parcel["p"][0] > max(1.5 * s["distance_m"], 0.75) or abs(parcel["p"][1]) > max(3.0 * s["target_radius_m"], 0.5):
                escaped += parcel["m"]
                continue
            survivors.append(parcel)
        parcels = survivors
        airborne = sum(float(p["m"]) for p in parcels)
        series.append({
            "time_s": float(t), "emitted_kg": emitted, "delivered_kg": delivered,
            "evaporated_kg": evaporated, "deposited_kg": deposited,
            "escaped_kg": escaped, "airborne_kg": airborne,
        })
    airborne = sum(float(p["m"]) for p in parcels)
    balance_error = emitted - (delivered + evaporated + deposited + escaped + airborne)
    metrics = {
        "emitted_kg": emitted, "delivered_kg": delivered, "evaporated_kg": evaporated,
        "deposited_kg": deposited, "escaped_kg": escaped, "airborne_kg": airborne,
        "mass_balance_error_kg": balance_error,
        "delivery_fraction": delivered / emitted if emitted > 0.0 else 0.0,
        "evaporation_d2_coefficient_m2_s": evaporation_k,
        "evaporation_latent_heat_demand_J": evaporated * LATENT_HEAT_WATER,
        "peak_particle_reynolds_number": peak_reynolds,
        "peak_schiller_naumann_drag_coefficient": peak_drag_coefficient,
    }
    metrics.update(evaporation_state)
    return metrics, [series[i] for i in _sample_indices(len(series))], parcels, times


def _particle_scalar(points: np.ndarray, parcels: list[dict[str, Any]], width: float) -> np.ndarray:
    scalar = np.zeros(len(points))
    norm = (2.0 * math.pi) ** 1.5 * width ** 3
    for parcel in parcels:
        d2 = np.sum((points - parcel["p"]) ** 2, axis=1)
        scalar += parcel["m"] * np.exp(-0.5 * d2 / (width * width)) / norm
    return scalar


def _simulate_m3_or_m4(s: dict[str, float], m: dict[str, Any], assumed: list[str], method_id: str) -> dict[str, Any]:
    water = method_id == "M3"
    label = "evaporating monodisperse water parcel transport" if water else "passive monodisperse aerosol parcel transport"
    limitations = [
        "A dilute monodisperse parcel model and assumed round carrier jet are used; breakup, collision, turbulence dispersion, walls, and combustion coupling are absent.",
        "Target delivery is geometric interception by a circular plane, not extinguishing performance.",
    ]
    if water:
        limitations.append("Evaporation uses a bounded Maxwell d-squared law coefficient derived from assumed ambient temperature and humidity; latent heat feedback is not solved.")
    else:
        limitations.append("Particles are chemically passive. Agent composition, radical inhibition, hot-generator effects, toxicity, and fire suppression are not modeled.")
    result = _base_result(method_id, label, limitations, m, assumed)
    carrier_diameter = m["carrier_diameter_m"]
    requested_mass = min(m["flow_kg_s"] * s["duration_s"], m["payload_kg"])
    device_energy = m["power_W"] * s["duration_s"]
    carrier_area = math.pi * (carrier_diameter / 2.0) ** 2

    def ideal_kinetic_energy(exit_velocity: float) -> float:
        carrier = 0.5 * RHO_AIR * carrier_area * exit_velocity ** 3 * s["duration_s"]
        particles = 0.5 * requested_mass * exit_velocity ** 2
        return carrier + particles

    requested_velocity = m["exit_velocity_m_s"]
    requested_energy = ideal_kinetic_energy(requested_velocity)
    effective_velocity = requested_velocity
    if requested_energy > device_energy + 1e-12 and requested_velocity > 0.0:
        lower, upper = 0.0, requested_velocity
        for _ in range(64):
            midpoint = 0.5 * (lower + upper)
            if ideal_kinetic_energy(midpoint) <= device_energy:
                lower = midpoint
            else:
                upper = midpoint
        effective_velocity = lower

    transport_method = dict(m)
    transport_method["exit_velocity_m_s"] = effective_velocity
    air_fn = lambda p, _t: _round_jet_velocity(p, effective_velocity, carrier_diameter, s["crosswind_m_s"])
    metrics, series, parcels, _ = _particle_transport(s, transport_method, evaporating=water, air_velocity=air_fn, density=RHO_WATER if water else RHO_PARTICLE)
    points = _grid(s["distance_m"], s["target_radius_m"])
    velocity = air_fn(points, s["duration_s"])
    concentration = _particle_scalar(points, parcels, max(carrier_diameter / 2.0, 0.025))
    actual_duration = metrics["emitted_kg"] / m["flow_kg_s"] if m["flow_kg_s"] > 0.0 else 0.0
    reaction = m["flow_kg_s"] * effective_velocity * min(actual_duration / s["duration_s"], 1.0)
    carrier_reaction = RHO_AIR * carrier_area * effective_velocity ** 2
    metrics["carrier_air_reaction_N"] = carrier_reaction
    metrics["mean_particle_reaction_N"] = reaction
    metrics["device_energy_J"] = device_energy
    metrics["requested_launch_mass_kg"] = requested_mass
    metrics["requested_exit_velocity_m_s"] = requested_velocity
    metrics["effective_exit_velocity_m_s"] = effective_velocity
    metrics["requested_ideal_kinetic_energy_J"] = requested_energy
    metrics["carrier_air_kinetic_energy_J"] = 0.5 * RHO_AIR * carrier_area * effective_velocity ** 3 * s["duration_s"]
    metrics["injected_kinetic_energy_J"] = 0.5 * metrics["emitted_kg"] * effective_velocity ** 2
    metrics["total_ideal_kinetic_energy_J"] = metrics["carrier_air_kinetic_energy_J"] + metrics["injected_kinetic_energy_J"]
    result["metrics"] = metrics
    result["series"] = series
    result["field"] = {"points": points.tolist(), "velocity": velocity.tolist(), "scalar": concentration.tolist(), "scalar_name": "airborne_water_concentration" if water else "passive_particle_concentration", "unit": "kg/m3"}
    result["reaction_force_N"] = [-(reaction + carrier_reaction), 0.0, 0.0]
    result["consumable_kg"] = metrics["emitted_kg"]
    result["loaded_consumable_kg"] = m["payload_kg"]
    sufficient = effective_velocity >= requested_velocity - 1e-12
    result["resource_status"] = {
        "status": "sufficient" if sufficient else "insufficient",
        "reason": None if sufficient else "Device energy is below the ideal carrier-air plus particle exit kinetic energy; the effective exit velocity is reduced without assuming an unreported pressure reservoir.",
        "requested_particle_kg": requested_mass,
        "requested_exit_velocity_m_s": requested_velocity,
        "effective_exit_velocity_m_s": effective_velocity,
        "minimum_ideal_kinetic_energy_J": requested_energy,
        "device_energy_capacity_J": device_energy,
    }
    if not sufficient:
        result["limitations"].append(result["resource_status"]["reason"])
    if water and s["ambient_K"] > 323.15:
        result["limitations"].append("The Buck saturation-pressure closure is capped at 323.15 K; high-temperature fire-plume evaporation requires coupled droplet heat and mass transfer.")
    return result


def _simulate_m5(s: dict[str, float], m: dict[str, Any], assumed: list[str]) -> dict[str, Any]:
    variant = str(m.get("variant", "CV")).upper()
    if variant not in {"CV", "EHD", "COMBINED"}:
        raise ValueError("methods.M5.variant must be CV, EHD, or COMBINED")
    explicit_ehd = variant in {"EHD", "COMBINED"} and abs(m["charge_density_C_m3"]) > 0.0 and abs(m["electric_field_V_m"]) > 0.0
    if variant in {"EHD", "COMBINED"} and not explicit_ehd:
        raise ValueError("M5 EHD/COMBINED requires nonzero charge_density_C_m3 and electric_field_V_m")
    limitations = [
        "Conductive particles are chemically passive because composition and inhibition chemistry are unavailable.",
        "The vortex transport uses the same uncalibrated finite-core ring assumptions as M2; particle loading does not feed back on the air field.",
        "No effectiveness bonus or extinction criterion is assigned to conductivity.",
    ]
    if explicit_ehd:
        limitations.append("EHD body acceleration qE/rho uses user-supplied uniform fields over an assumed length; electrodes, charge transport, breakdown, mobility, and field coupling are unvalidated.")
    else:
        limitations.append("CV mode applies no electric force; zero default electric inputs cannot create ion wind.")
    result = _base_result("M5", f"passive conductive-particle transport in finite-core vortex rings ({variant})", limitations, m, assumed)
    times = _times(s)
    resource = _pneumatic_budget(s, m, include_particles=True)
    states_by_time, ring = _ring_states(s, m, times, resource["simulated_pulses"])
    radius = float(ring["radius"])
    circulation = float(ring["circulation"])
    ehd_accel = m["charge_density_C_m3"] * m["electric_field_V_m"] / RHO_AIR if explicit_ehd else 0.0
    ehd_delta_u_unbounded = math.copysign(math.sqrt(2.0 * abs(ehd_accel) * m["ehd_length_m"]), ehd_accel) if ehd_accel != 0.0 else 0.0
    area = math.pi * radius * radius
    ehd_force = m["charge_density_C_m3"] * m["electric_field_V_m"] * area * m["ehd_length_m"] if explicit_ehd else 0.0
    power_speed_cap = m["power_W"] / abs(ehd_force) if ehd_force != 0.0 else math.inf
    ehd_delta_u = math.copysign(min(abs(ehd_delta_u_unbounded), power_speed_cap), ehd_delta_u_unbounded)
    ehd_mechanical_power = abs(ehd_force * ehd_delta_u)

    def air_fn(points: np.ndarray, t: float) -> np.ndarray:
        index = min(max(int(np.searchsorted(times, t, side="right") - 1), 0), len(states_by_time) - 1)
        velocity = np.column_stack((np.zeros(len(points)), np.full(len(points), s["crosswind_m_s"]), np.zeros(len(points))))
        for state in states_by_time[index]:
            velocity += _ring_velocity(points, state["center"], radius, state["core"], state["circulation"], segments=24)
        if explicit_ehd:
            region = (points[:, 0] >= 0.0) & (points[:, 0] <= m["ehd_length_m"])
            velocity[region, 0] += ehd_delta_u
        return velocity

    transport_method = dict(m)
    transport_method["payload_kg"] = min(m["payload_kg"], resource["affordable_particle_kg"])
    metrics, series, parcels, _ = _particle_transport(s, transport_method, evaporating=False, air_velocity=air_fn, density=RHO_PARTICLE)
    points = _grid(s["distance_m"], s["target_radius_m"])
    velocity = air_fn(points, s["duration_s"])
    concentration = _particle_scalar(points, parcels, max(radius / 2.0, 0.025))
    duty = m["pulse_duration_s"] / m["period_s"]
    peak_jet_reaction = RHO_AIR * area * m["exit_velocity_m_s"] ** 2 if resource["simulated_pulses"] > 0 else 0.0
    metrics.update({
        "circulation_m2_s": circulation,
        "uncapped_slug_circulation_m2_s": ring["raw_circulation"],
        "circulation_energy_capped": ring["circulation_energy_capped"],
        "formation_number_L_over_D": ring["formation_number"],
        "hydrodynamic_impulse_N_s_per_ring": ring["impulse"],
        "thin_core_kinetic_energy_J_per_ring": ring["ring_energy"],
        "ehd_body_acceleration_m_s2": ehd_accel,
        "ehd_unbounded_velocity_increment_m_s": ehd_delta_u_unbounded,
        "ehd_velocity_increment_m_s": ehd_delta_u,
        "ehd_velocity_power_capped": abs(ehd_delta_u) + 1e-12 < abs(ehd_delta_u_unbounded),
        "ehd_force_N": ehd_force,
        "ehd_mechanical_power_W": ehd_mechanical_power,
        "electrical_energy_J": m["power_W"] * s["duration_s"],
        "stored_energy_capacity_J": m["stored_energy_J"],
        "minimum_pneumatic_energy_demand_J": resource["minimum_pneumatic_energy_demand_J"],
        "simulated_pneumatic_energy_J": resource["energy_per_pulse_J"] * resource["simulated_pulses"] + 0.5 * metrics["emitted_kg"] * m["exit_velocity_m_s"] ** 2,
        "injected_particle_kinetic_energy_J": 0.5 * metrics["emitted_kg"] * m["exit_velocity_m_s"] ** 2,
    })
    result["metrics"] = metrics
    result["series"] = series
    result["field"] = {"points": points.tolist(), "velocity": velocity.tolist(), "scalar": concentration.tolist(), "scalar_name": "passive_conductive_particle_concentration", "unit": "kg/m3"}
    particle_reaction = metrics["emitted_kg"] * m["exit_velocity_m_s"] / s["duration_s"]
    metrics["mean_particle_reaction_N"] = particle_reaction
    result["reaction_force_N"] = [-(peak_jet_reaction + ehd_force + particle_reaction), 0.0, 0.0]
    result["reaction_pulse"] = {
        "peak_force_N": [-(peak_jet_reaction + ehd_force + particle_reaction), 0.0, 0.0],
        "peak_jet_force_N": [-peak_jet_reaction, 0.0, 0.0],
        "steady_force_N": [-ehd_force, 0.0, 0.0],
        "pulse_duration_s": m["pulse_duration_s"], "period_s": m["period_s"],
        "duty_cycle": duty, "simulated_pulses": resource["simulated_pulses"],
    }
    result["resource_status"] = resource
    if resource["status"] == "insufficient":
        result["limitations"].append(resource["reason"])
    result["consumable_kg"] = metrics["emitted_kg"]
    result["loaded_consumable_kg"] = m["payload_kg"]
    return result


def simulate_method(config: dict[str, Any] | None, method_id: str) -> dict[str, Any]:
    """Simulate one delivery method and return a finite JSON-safe result.

    Raises ``ValueError`` for malformed or physically out-of-range inputs.
    Successful computation does not imply experimental validation or fire
    suppression: ``suppression`` is always explicitly insufficient evidence.
    """
    if config is not None and not isinstance(config, dict):
        raise ValueError("config must be an object")
    scenario, method, assumed = _inputs(config or {}, method_id)
    if method_id == "M1":
        result = _simulate_m1(scenario, method, assumed)
    elif method_id == "M2":
        result = _simulate_m2(scenario, method, assumed)
    elif method_id in ("M3", "M4"):
        result = _simulate_m3_or_m4(scenario, method, assumed, method_id)
    else:
        result = _simulate_m5(scenario, method, assumed)
    # Strict final traversal catches accidental NaN/Inf and NumPy scalar leakage.
    def normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(k): normalize(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [normalize(v) for v in value]
        if isinstance(value, (np.floating, float)):
            return _clean_float(float(value))
        if isinstance(value, (np.integer, int)) and not isinstance(value, bool):
            return int(value)
        if value is None or isinstance(value, (str, bool)):
            return value
        raise TypeError(f"non-JSON result type: {type(value).__name__}")
    return normalize(result)


__all__ = ["simulate_method"]
