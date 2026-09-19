"""Drone mission dynamics for the fire-control feasibility study.

The model is an engineering screening model, not a flight-safety or fire-
suppression certification.  It integrates translation, quaternion attitude,
body angular velocity, battery energy, and consumable mass.  All built-in
airframe and controller values are assumptions until replaced by measured and
calibrated inputs.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np


_G = 9.80665
_RHO_AIR = 1.225
_MAX_STEPS = 50_000
_MAX_SERIES_ROWS = 1_800

_DRONE_DEFAULTS: dict[str, Any] = {
    "mass_kg": 2.0,
    "battery_Wh": 120.0,
    "rotor_radius_m": 0.12,
    "rotor_count": 4,
    "max_thrust_N": 45.0,
    "max_power_W": 1200.0,
    "hover_efficiency": 0.6,
    "reserve_fraction": 0.2,
    "approach_s": 15.0,
    "return_s": 15.0,
    "avionics_W": 12.0,
    "inertia_kg_m2": [0.04, 0.04, 0.08],
    "ambient_K": 293.15,
    "payload_capacity_kg": 2.0,
    "initial_altitude_m": 2.0,
    "position_kp_s2": 2.4,
    "position_kd_s": 2.8,
    "attitude_kp_Nm": 1.8,
    "attitude_kd_Nms": 0.25,
    "max_torque_Nm": 2.5,
    "tracking_tolerance_m": 1.0,
    "reaction_lever_arm_m": [0.0, 0.0, -0.10],
    "airframe_cg_m": None,
    "device_mount_position_m": None,
    "consumable_position_m": None,
    "drag_coefficient": 1.0,
    "drag_area_m2": 0.12,
}

_SCENARIO_DEFAULTS: dict[str, Any] = {
    "duration_s": 4.0,
    "dt_s": 0.02,
    "distance_m": 1.0,
    "crosswind_m_s": 0.2,
}


def _finite_number(value: Any, name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return result


def _vector3(value: Any, name: str) -> np.ndarray:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise ValueError(f"{name} must contain three finite numbers")
    vector = np.array([_finite_number(item, f"{name}[{index}]") for index, item in enumerate(value)])
    return vector.astype(float)


def _merged_config(config: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(config, Mapping):
        raise ValueError("config must be a mapping")
    drone = dict(_DRONE_DEFAULTS)
    scenario = dict(_SCENARIO_DEFAULTS)
    nested_drone = config.get("drone", {})
    nested_scenario = config.get("scenario", {})
    if not isinstance(nested_drone, Mapping) or not isinstance(nested_scenario, Mapping):
        raise ValueError("config.drone and config.scenario must be mappings")
    drone.update(nested_drone)
    scenario.update(nested_scenario)
    # Direct fields are accepted for small programmatic studies.
    for key in _DRONE_DEFAULTS:
        if key in config:
            drone[key] = config[key]
    for key in _SCENARIO_DEFAULTS:
        if key in config:
            scenario[key] = config[key]

    positive = ("mass_kg", "rotor_radius_m", "hover_efficiency")
    nonnegative = (
        "battery_Wh", "max_thrust_N", "max_power_W", "reserve_fraction",
        "approach_s", "return_s", "avionics_W", "payload_capacity_kg",
        "initial_altitude_m", "position_kp_s2", "position_kd_s",
        "attitude_kp_Nm", "attitude_kd_Nms", "max_torque_Nm",
        "tracking_tolerance_m", "ambient_K",
        "drag_coefficient", "drag_area_m2",
    )
    for key in positive:
        drone[key] = _finite_number(drone[key], f"drone.{key}", minimum=np.finfo(float).tiny)
    for key in nonnegative:
        drone[key] = _finite_number(drone[key], f"drone.{key}", minimum=0.0)
    if drone["reserve_fraction"] > 1.0:
        raise ValueError("drone.reserve_fraction must be <= 1")
    if drone["hover_efficiency"] > 1.0:
        raise ValueError("drone.hover_efficiency must be <= 1")
    rotor_count = _finite_number(drone["rotor_count"], "drone.rotor_count", minimum=1.0)
    if not rotor_count.is_integer():
        raise ValueError("drone.rotor_count must be an integer")
    drone["rotor_count"] = int(rotor_count)
    inertia = _vector3(drone["inertia_kg_m2"], "drone.inertia_kg_m2")
    if np.any(inertia <= 0.0):
        raise ValueError("drone.inertia_kg_m2 values must be positive")
    drone["inertia_kg_m2"] = inertia
    drone["reaction_lever_arm_m"] = _vector3(
        drone["reaction_lever_arm_m"], "drone.reaction_lever_arm_m"
    )
    for key in ("airframe_cg_m", "device_mount_position_m", "consumable_position_m"):
        if drone[key] is not None:
            drone[key] = _vector3(drone[key], f"drone.{key}")
    if drone["device_mount_position_m"] is not None and drone["airframe_cg_m"] is None:
        drone["airframe_cg_m"] = np.zeros(3)
    if drone["consumable_position_m"] is None and drone["device_mount_position_m"] is not None:
        drone["consumable_position_m"] = drone["device_mount_position_m"].copy()

    scenario["duration_s"] = _finite_number(
        scenario["duration_s"], "scenario.duration_s", minimum=np.finfo(float).tiny
    )
    scenario["dt_s"] = _finite_number(
        scenario["dt_s"], "scenario.dt_s", minimum=np.finfo(float).tiny
    )
    scenario["distance_m"] = _finite_number(scenario["distance_m"], "scenario.distance_m", minimum=0.0)
    scenario["crosswind_m_s"] = _finite_number(scenario["crosswind_m_s"], "scenario.crosswind_m_s")
    total = drone["approach_s"] + scenario["duration_s"] + drone["return_s"]
    if math.ceil(total / scenario["dt_s"]) + 3 > _MAX_STEPS:
        raise ValueError(f"mission exceeds the {_MAX_STEPS}-step integration limit")
    return drone, scenario


def _quat_multiply(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    lw, lx, ly, lz = left
    rw, rx, ry, rz = right
    return np.array([
        lw * rw - lx * rx - ly * ry - lz * rz,
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
    ])


def _rotation_matrix(quaternion: np.ndarray) -> np.ndarray:
    w, x, y, z = quaternion
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def _quaternion_from_matrix(rotation: np.ndarray) -> np.ndarray:
    trace = float(np.trace(rotation))
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        quaternion = np.array([
            0.25 * scale,
            (rotation[2, 1] - rotation[1, 2]) / scale,
            (rotation[0, 2] - rotation[2, 0]) / scale,
            (rotation[1, 0] - rotation[0, 1]) / scale,
        ])
    else:
        index = int(np.argmax(np.diag(rotation)))
        j = (index + 1) % 3
        k = (index + 2) % 3
        scale = math.sqrt(max(1.0 + rotation[index, index] - rotation[j, j] - rotation[k, k], 0.0)) * 2.0
        quaternion = np.zeros(4)
        quaternion[index + 1] = 0.25 * scale
        quaternion[0] = (rotation[k, j] - rotation[j, k]) / scale
        quaternion[j + 1] = (rotation[j, index] + rotation[index, j]) / scale
        quaternion[k + 1] = (rotation[k, index] + rotation[index, k]) / scale
    if quaternion[0] < 0.0:
        quaternion = -quaternion
    return quaternion / np.linalg.norm(quaternion)


def _attitude_for_force(force_world: np.ndarray) -> np.ndarray:
    magnitude = float(np.linalg.norm(force_world))
    body_z = force_world / magnitude if magnitude > 1e-12 else np.array([0.0, 0.0, 1.0])
    yaw_x = np.array([1.0, 0.0, 0.0])
    body_y = np.cross(body_z, yaw_x)
    if np.linalg.norm(body_y) < 1e-9:
        body_y = np.array([0.0, 1.0, 0.0])
    body_y /= np.linalg.norm(body_y)
    body_x = np.cross(body_y, body_z)
    return np.column_stack((body_x, body_y, body_z))


def _euler_degrees(rotation: np.ndarray) -> tuple[float, float, float]:
    pitch = math.asin(float(np.clip(-rotation[2, 0], -1.0, 1.0)))
    roll = math.atan2(rotation[2, 1], rotation[2, 2])
    yaw = math.atan2(rotation[1, 0], rotation[0, 0])
    return tuple(math.degrees(value) for value in (roll, pitch, yaw))


def _minimum_jerk(progress: float) -> tuple[float, float, float]:
    progress = float(np.clip(progress, 0.0, 1.0))
    position = 10 * progress**3 - 15 * progress**4 + 6 * progress**5
    velocity = 30 * progress**2 - 60 * progress**3 + 30 * progress**4
    acceleration = 60 * progress - 180 * progress**2 + 120 * progress**3
    return position, velocity, acceleration


def _reference(t: float, drone: Mapping[str, Any], scenario: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    approach = drone["approach_s"]
    actuation_end = approach + scenario["duration_s"]
    distance = scenario["distance_m"]
    if approach > 0.0 and t < approach:
        shape, derivative, second = _minimum_jerk(t / approach)
        x = distance * shape
        vx = distance * derivative / approach
        ax = distance * second / (approach * approach)
    elif t < actuation_end or drone["return_s"] == 0.0:
        x, vx, ax = distance, 0.0, 0.0
    else:
        local = min((t - actuation_end) / drone["return_s"], 1.0)
        shape, derivative, second = _minimum_jerk(local)
        x = distance * (1.0 - shape)
        vx = -distance * derivative / drone["return_s"]
        ax = -distance * second / (drone["return_s"] ** 2)
    return (
        np.array([x, 0.0, drone["initial_altitude_m"]]),
        np.array([vx, 0.0, 0.0]),
        np.array([ax, 0.0, 0.0]),
    )


def _method_inputs(method_result: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(method_result, Mapping):
        raise ValueError("method_result must be a mapping")
    reaction = _vector3(method_result.get("reaction_force_N", [0.0, 0.0, 0.0]), "reaction_force_N")
    frame = method_result.get("reaction_frame", "body")
    if frame not in {"body", "world"}:
        raise ValueError("reaction_frame must be 'body' or 'world'")
    emitted_consumable = _finite_number(method_result.get("consumable_kg", 0.0), "consumable_kg", minimum=0.0)
    loaded_consumable = _finite_number(
        method_result.get("loaded_consumable_kg", emitted_consumable), "loaded_consumable_kg", minimum=0.0
    )
    result = {
        "method_id": str(method_result.get("method_id", "unknown")),
        "reaction_force_N": reaction,
        "reaction_frame": frame,
        "device_power_W": _finite_number(method_result.get("device_power_W", 0.0), "device_power_W", minimum=0.0),
        "device_mass_kg": _finite_number(method_result.get("device_mass_kg", 0.0), "device_mass_kg", minimum=0.0),
        "consumable_kg": emitted_consumable,
        "loaded_consumable_kg": loaded_consumable,
        "pulse_period_s": None,
        "pulse_duration_s": None,
        "pulse_force_N": reaction.copy(),
        "steady_force_N": np.zeros(3),
        "simulated_pulses": None,
        "reaction_series": [],
        "consumable_release": None,
        "nonconsumable_reaction_force_N": reaction.copy(),
        "resource_status": method_result.get("resource_status"),
    }
    release = method_result.get("consumable_release")
    if release is not None:
        if not isinstance(release, Mapping):
            raise ValueError("consumable_release must be a mapping")
        flow = _finite_number(release.get("flow_kg_s"), "consumable_release.flow_kg_s", minimum=0.0)
        release_duration = _finite_number(release.get("duration_s"), "consumable_release.duration_s", minimum=0.0)
        exhaust = _vector3(release.get("exhaust_velocity_m_s"), "consumable_release.exhaust_velocity_m_s")
        if not math.isclose(flow * release_duration, emitted_consumable, rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError("consumable_release integrated mass must equal consumable_kg")
        result["consumable_release"] = {
            "flow_kg_s": flow, "duration_s": release_duration, "exhaust_velocity_m_s": exhaust,
        }
        result["nonconsumable_reaction_force_N"] = _vector3(
            method_result.get("nonconsumable_reaction_force_N"), "nonconsumable_reaction_force_N"
        )
    pulse = method_result.get("reaction_pulse", {})
    if pulse is None:
        pulse = {}
    if not isinstance(pulse, Mapping):
        raise ValueError("reaction_pulse must be a mapping")
    period = pulse.get("period_s", method_result.get("pulse_period_s"))
    duration = pulse.get("pulse_duration_s", pulse.get("duration_s", method_result.get("pulse_duration_s")))
    if period is not None or duration is not None:
        if period is None or duration is None:
            raise ValueError("reaction pulse requires both period_s and duration_s")
        period = _finite_number(period, "reaction_pulse.period_s", minimum=np.finfo(float).tiny)
        duration = _finite_number(duration, "reaction_pulse.duration_s", minimum=0.0)
        if duration > period:
            raise ValueError("reaction pulse duration_s cannot exceed period_s")
        result["pulse_period_s"] = period
        result["pulse_duration_s"] = duration
        steady_force = _vector3(pulse.get("steady_force_N", [0.0, 0.0, 0.0]), "reaction_pulse.steady_force_N")
        if "peak_jet_force_N" in pulse:
            pulse_force = _vector3(pulse["peak_jet_force_N"], "reaction_pulse.peak_jet_force_N")
        elif "peak_force_N" in pulse:
            peak_total = _vector3(pulse["peak_force_N"], "reaction_pulse.peak_force_N")
            pulse_force = peak_total - steady_force
        else:
            pulse_force = reaction - steady_force
        result["pulse_force_N"] = pulse_force
        result["steady_force_N"] = steady_force
        if "simulated_pulses" in pulse:
            simulated_pulses = _finite_number(
                pulse["simulated_pulses"], "reaction_pulse.simulated_pulses", minimum=0.0
            )
            if not simulated_pulses.is_integer():
                raise ValueError("reaction_pulse.simulated_pulses must be an integer")
            result["simulated_pulses"] = int(simulated_pulses)
    raw_series = method_result.get("series", [])
    if not isinstance(raw_series, Sequence) or isinstance(raw_series, (str, bytes)):
        raise ValueError("method_result.series must be a sequence")
    reaction_series: list[tuple[float, np.ndarray]] = []
    for index, row in enumerate(raw_series):
        if not isinstance(row, Mapping) or "reaction_force_N" not in row:
            continue
        time_s = _finite_number(row.get("time_s"), f"series[{index}].time_s", minimum=0.0)
        force = _vector3(row["reaction_force_N"], f"series[{index}].reaction_force_N")
        reaction_series.append((time_s, force))
    reaction_series.sort(key=lambda point: point[0])
    if any(right[0] <= left[0] for left, right in zip(reaction_series, reaction_series[1:])):
        raise ValueError("reaction force series timestamps must be unique")
    result["reaction_series"] = reaction_series
    return result


def _pulse_overlap(
    start_s: float,
    duration_s: float,
    period_s: float,
    on_s: float,
    max_pulses: int | None,
) -> float:
    """Return the fraction of [start, start+duration] occupied by pulses."""
    if duration_s <= 0.0 or on_s <= 0.0:
        return 0.0
    end_s = start_s + duration_s
    first_cycle = math.floor(start_s / period_s)
    last_cycle = math.floor(end_s / period_s)
    overlap = 0.0
    for cycle in range(first_cycle, last_cycle + 1):
        if max_pulses is not None and cycle >= max_pulses:
            continue
        pulse_start = cycle * period_s
        pulse_end = pulse_start + on_s
        overlap += max(0.0, min(end_s, pulse_end) - max(start_s, pulse_start))
    return overlap / duration_s


def _released_mass(local_t: float, dt: float, method: Mapping[str, Any], actuation_duration: float) -> float:
    """Mass scheduled in this interval; legacy inputs retain uniform release."""
    release = method["consumable_release"]
    end = release["duration_s"] if release is not None else actuation_duration
    flow = release["flow_kg_s"] if release is not None else method["consumable_kg"] / actuation_duration
    return flow * max(0.0, min(local_t + dt, end) - max(local_t, 0.0))


def _reaction_at(local_t: float, dt: float, method: Mapping[str, Any]) -> np.ndarray:
    """Average total force over an interval (impulse divided by dt).

    Supplied reaction series already represent the total force. Otherwise the
    steady/pulsed carrier and the finite-duration particle exhaust are added.
    """
    series_points = method["reaction_series"]
    if series_points:
        times = np.array([point[0] for point in series_points])
        forces = np.array([point[1] for point in series_points])
        if dt <= 0.0:
            return np.array([np.interp(local_t, times, forces[:, axis]) for axis in range(3)])
        knots = np.concatenate(([local_t], times[(times > local_t) & (times < local_t + dt)], [local_t + dt]))
        samples = np.column_stack([np.interp(knots, times, forces[:, axis]) for axis in range(3)])
        return np.sum(0.5 * (samples[:-1] + samples[1:]) * np.diff(knots)[:, None], axis=0) / dt
    period = method["pulse_period_s"]
    duration = method["pulse_duration_s"]
    if period is not None:
        active_fraction = _pulse_overlap(local_t, dt, period, duration, method["simulated_pulses"])
        force = method["steady_force_N"] + active_fraction * method["pulse_force_N"]
    else:
        force = method["nonconsumable_reaction_force_N"].copy()
    release = method["consumable_release"]
    if release is not None and dt > 0.0:
        emitted = _released_mass(local_t, dt, method, release["duration_s"])
        force -= release["exhaust_velocity_m_s"] * (emitted / dt)
    return force

def _induced_power(thrust_N: float, drone: Mapping[str, Any]) -> float:
    disk_area = drone["rotor_count"] * math.pi * drone["rotor_radius_m"] ** 2
    ideal = thrust_N ** 1.5 / math.sqrt(2.0 * _RHO_AIR * disk_area) if thrust_N > 0.0 else 0.0
    return ideal / drone["hover_efficiency"]


def _power_limited_thrust(power_W: float, drone: Mapping[str, Any]) -> float:
    if power_W <= 0.0:
        return 0.0
    disk_area = drone["rotor_count"] * math.pi * drone["rotor_radius_m"] ** 2
    ideal_power = power_W * drone["hover_efficiency"]
    return (ideal_power * math.sqrt(2.0 * _RHO_AIR * disk_area)) ** (2.0 / 3.0)


def _advance_lumped_temperature(
    temperature_K: float,
    heat_input_W: float,
    cooling_W_K: float,
    heat_capacity_J_K: float,
    ambient_K: float,
    dt_s: float,
) -> float:
    """Advance ``C dT/dt = Q - H(T-T_ambient)`` exactly for constant inputs."""
    if dt_s <= 0.0:
        return temperature_K
    if cooling_W_K <= 0.0:
        return temperature_K + heat_input_W * dt_s / heat_capacity_J_K
    equilibrium_K = ambient_K + heat_input_W / cooling_W_K
    decay = math.exp(-cooling_W_K * dt_s / heat_capacity_J_K)
    return equilibrium_K + (temperature_K - equilibrium_K) * decay


def _thermal_config(config: Mapping[str, Any], ambient_K: float) -> dict[str, float] | None:
    thermal = config.get("thermal")
    if thermal is None:
        return None
    if not isinstance(thermal, Mapping):
        raise ValueError("thermal must be a mapping")
    required = ("incident_flux_W_m2", "exposed_area_m2", "heat_capacity_J_K", "cooling_W_K", "max_temperature_K")
    if any(key not in thermal for key in required):
        raise ValueError("thermal model requires incident flux, area, heat capacity, cooling, and maximum temperature")
    parsed = {key: _finite_number(thermal[key], f"thermal.{key}", minimum=0.0) for key in required}
    if parsed["heat_capacity_J_K"] <= 0.0 or parsed["max_temperature_K"] < ambient_K:
        raise ValueError("thermal heat capacity must be positive and maximum temperature must exceed ambient")
    parsed["initial_temperature_K"] = _finite_number(
        thermal.get("initial_temperature_K", ambient_K), "thermal.initial_temperature_K", minimum=0.0
    )
    return parsed


def _sensor_config(config: Mapping[str, Any], default_seed: int = 42) -> dict[str, float | int] | None:
    sensor = config.get("sensor")
    if sensor is None:
        return None
    if not isinstance(sensor, Mapping):
        raise ValueError("sensor must be a mapping")
    parsed: dict[str, float | int] = {
        "sample_rate_Hz": _finite_number(sensor.get("sample_rate_Hz", 10.0), "sensor.sample_rate_Hz", minimum=np.finfo(float).tiny),
        "latency_s": _finite_number(sensor.get("latency_s", 0.0), "sensor.latency_s", minimum=0.0),
        "position_error_std_m": _finite_number(sensor.get("position_error_std_m", 0.0), "sensor.position_error_std_m", minimum=0.0),
        "velocity_error_std_m_s": _finite_number(sensor.get("velocity_error_std_m_s", 0.0), "sensor.velocity_error_std_m_s", minimum=0.0),
        "availability_fraction": _finite_number(sensor.get("availability_fraction", 1.0), "sensor.availability_fraction", minimum=0.0),
    }
    if parsed["availability_fraction"] > 1.0:
        raise ValueError("sensor.availability_fraction must be <= 1")
    seed_value = _finite_number(sensor.get("seed", default_seed), "sensor.seed", minimum=0.0)
    if not seed_value.is_integer():
        raise ValueError("sensor.seed must be an integer")
    parsed["seed"] = int(seed_value)
    return parsed


def _center_of_gravity(
    drone: Mapping[str, Any], method: Mapping[str, Any], consumable_kg: float, total_mass_kg: float
) -> np.ndarray | None:
    if drone["device_mount_position_m"] is None:
        return None
    return (
        drone["mass_kg"] * drone["airframe_cg_m"]
        + method["device_mass_kg"] * drone["device_mount_position_m"]
        + consumable_kg * drone["consumable_position_m"]
    ) / total_mass_kg


def simulate_mission(
    config: Mapping[str, Any],
    method_result: Mapping[str, Any],
    controller_enabled: bool = True,
) -> dict[str, Any]:
    """Integrate one approach, actuation, and return mission.

    ``controller_enabled=False`` disables position/velocity disturbance
    feedback while retaining the nominal attitude loop needed to fly the
    prescribed smooth path.  It therefore represents an open-loop trajectory
    with basic attitude stabilization, not a motors-off vehicle.
    """
    if not isinstance(controller_enabled, bool):
        raise ValueError("controller_enabled must be boolean")
    drone, scenario = _merged_config(config)
    method = _method_inputs(method_result)
    thermal = _thermal_config(config, drone["ambient_K"])
    sensor = _sensor_config(config, int(config.get("scenario", {}).get("seed", 42)))

    duration = drone["approach_s"] + scenario["duration_s"] + drone["return_s"]
    dt_nominal = scenario["dt_s"]
    nominal_step_count = int(math.ceil(duration / dt_nominal))
    time_points = [min(index * dt_nominal, duration) for index in range(nominal_step_count + 1)]
    time_points.extend((drone["approach_s"], drone["approach_s"] + scenario["duration_s"]))
    release = method["consumable_release"]
    if release is not None:
        if release["duration_s"] > scenario["duration_s"] + 1e-9:
            raise ValueError("consumable release cannot extend beyond the actuation window")
        time_points.append(drone["approach_s"] + release["duration_s"])
    time_points = sorted({point for point in time_points if 0.0 <= point <= duration})
    step_count = len(time_points) - 1
    payload_initial = method["device_mass_kg"] + method["loaded_consumable_kg"]
    mass = drone["mass_kg"] + payload_initial
    consumable = method["loaded_consumable_kg"]
    battery_J = drone["battery_Wh"] * 3600.0
    remaining_J = battery_J
    reserve_J = battery_J * drone["reserve_fraction"]
    failures: list[str] = []
    conditional_reasons: list[str] = []
    if payload_initial > drone["payload_capacity_kg"] + 1e-12:
        failures.append("payload_capacity_exceeded")
    if method["consumable_kg"] > method["loaded_consumable_kg"] + 1e-12:
        failures.append("consumable_shortfall")
    resource_status = method["resource_status"]
    if resource_status is not None:
        if not isinstance(resource_status, Mapping):
            raise ValueError("resource_status must be a mapping")
        status_value = resource_status.get("status")
        if status_value not in {"sufficient", "insufficient", "not_applicable"}:
            raise ValueError("resource_status.status must be sufficient, insufficient, or not_applicable")
        if status_value == "insufficient":
            failures.append("method_resource_insufficient")
    if battery_J <= 0.0:
        failures.append("battery_depleted")
    if drone["max_power_W"] <= 0.0:
        failures.append("power_unavailable")
    if drone["max_thrust_N"] <= 0.0:
        failures.append("thrust_unavailable")

    position = np.array([0.0, 0.0, drone["initial_altitude_m"]])
    velocity = np.zeros(3)
    quaternion = np.array([1.0, 0.0, 0.0, 0.0])
    omega = np.zeros(3)
    inertia = drone["inertia_kg_m2"]
    rows: list[dict[str, float]] = []
    sample_stride = max(1, math.ceil((step_count + 1) / _MAX_SERIES_ROWS))
    peak_tilt = 0.0
    max_error = 0.0
    peak_power = 0.0
    minimum_thrust_margin = math.inf
    saturation_steps = 0
    energy_used_J = 0.0
    remaining_at_actuation_end: float | None = None
    thermal_temperature = thermal["initial_temperature_K"] if thermal else None
    peak_temperature = thermal_temperature
    peak_relative_wind = 0.0
    peak_drag = 0.0
    reaction_impulse = 0.0
    peak_reaction_force = 0.0
    peak_reaction_torque = 0.0
    electrically_unpowered_s = 0.0
    device_energy_delivered_J = 0.0

    initial_cg = _center_of_gravity(drone, method, consumable, mass)
    final_cg = initial_cg.copy() if initial_cg is not None else None
    sensor_rng = np.random.default_rng(sensor["seed"]) if sensor is not None else None
    sensor_period = 1.0 / sensor["sample_rate_Hz"] if sensor is not None else 0.0
    next_sensor_sample = 0.0
    observed_position = position.copy()
    observed_velocity = velocity.copy()
    state_history: list[tuple[float, np.ndarray, np.ndarray]] = []
    sensor_attempts = 0
    sensor_updates = 0
    max_sensor_position_error = 0.0

    hover_power = _induced_power(mass * _G, drone) + drone["avionics_W"]
    return_energy_estimate = hover_power * drone["return_s"]

    for step in range(step_count + 1):
        t = time_points[step]
        dt = time_points[step + 1] - t if step < step_count else 0.0
        interval_end = t + dt
        actuation_start = drone["approach_s"]
        actuation_end = actuation_start + scenario["duration_s"]
        active_start = max(t, actuation_start)
        active_end = min(interval_end, actuation_end)
        active_dt = max(active_end - active_start, 0.0)
        active_fraction = active_dt / dt if dt > 0.0 else 0.0
        active = active_dt > 0.0
        target_position, target_velocity, target_acceleration = _reference(t, drone, scenario)
        state_history.append((t, position.copy(), velocity.copy()))
        if sensor is not None and t + 1e-12 >= next_sensor_sample:
            sensor_attempts += 1
            delayed_time = max(t - sensor["latency_s"], 0.0)
            delayed = state_history[0]
            for historical in reversed(state_history):
                if historical[0] <= delayed_time + 1e-12:
                    delayed = historical
                    break
            if float(sensor_rng.random()) <= sensor["availability_fraction"]:
                observed_position = delayed[1] + sensor_rng.normal(0.0, sensor["position_error_std_m"], 3)
                observed_velocity = delayed[2] + sensor_rng.normal(0.0, sensor["velocity_error_std_m_s"], 3)
                sensor_updates += 1
            next_sensor_sample += sensor_period
        elif sensor is None:
            observed_position = position
            observed_velocity = velocity
        max_sensor_position_error = max(
            max_sensor_position_error, float(np.linalg.norm(observed_position - position))
        )
        position_error = target_position - observed_position
        velocity_error = target_velocity - observed_velocity
        true_position_error = target_position - position
        correction = np.zeros(3)
        if controller_enabled:
            correction = drone["position_kp_s2"] * position_error + drone["position_kd_s"] * velocity_error
        desired_force = mass * (target_acceleration + correction + np.array([0.0, 0.0, _G]))
        desired_rotation = _attitude_for_force(desired_force)
        rotation = _rotation_matrix(quaternion)
        attitude_matrix_error = 0.5 * (desired_rotation.T @ rotation - rotation.T @ desired_rotation)
        attitude_error = np.array([
            attitude_matrix_error[2, 1], attitude_matrix_error[0, 2], attitude_matrix_error[1, 0]
        ])
        torque = -drone["attitude_kp_Nm"] * attitude_error - drone["attitude_kd_Nms"] * omega
        torque_norm = float(np.linalg.norm(torque))
        if drone["max_torque_Nm"] == 0.0:
            torque.fill(0.0)
        elif torque_norm > drone["max_torque_Nm"]:
            torque *= drone["max_torque_Nm"] / torque_norm

        # The battery is an energy store, so the average bus power in this
        # interval cannot exceed either the power electronics limit or E/dt.
        bus_power_limit = min(
            drone["max_power_W"], remaining_J / dt if dt > 0.0 else 0.0
        )
        requested_avionics_power = drone["avionics_W"]
        requested_device_power = method["device_power_W"] * active_fraction
        avionics_power = min(requested_avionics_power, bus_power_limit)
        power_after_avionics = max(bus_power_limit - avionics_power, 0.0)
        device_power = min(requested_device_power, power_after_avionics)
        available_propulsion_power = max(power_after_avionics - device_power, 0.0)
        if available_propulsion_power <= 0.0:
            # Rotor control cannot apply a moment without propulsion power.
            # External nozzle moments are added separately below.
            torque.fill(0.0)
        if requested_device_power > 0.0:
            device_delivery_fraction = device_power / requested_device_power
        else:
            device_delivery_fraction = 1.0
        device_energy_delivered_J += device_power * dt
        if dt > 0.0 and bus_power_limit <= 0.0:
            electrically_unpowered_s += dt

        reaction_body = np.zeros(3)
        reaction_world = np.zeros(3)
        if active:
            local_t = active_start - actuation_start
            reaction_during_actuation = _reaction_at(local_t, active_dt, method)
            # Average force over the whole integrator interval preserves the
            # exact active-window impulse when a step crosses a phase boundary.
            reaction = reaction_during_actuation * active_fraction * device_delivery_fraction
            if method["reaction_frame"] == "body":
                reaction_body = reaction
                reaction_world = rotation @ reaction
            else:
                reaction_world = reaction
                reaction_body = rotation.T @ reaction
            current_cg = _center_of_gravity(drone, method, consumable, mass)
            if current_cg is None:
                reaction_lever_arm = drone["reaction_lever_arm_m"]
            else:
                reaction_lever_arm = drone["device_mount_position_m"] - current_cg
                final_cg = current_cg.copy()
            reaction_torque = np.cross(reaction_lever_arm, reaction_body)
            torque += reaction_torque
            reaction_impulse += (
                float(np.linalg.norm(reaction_during_actuation))
                * active_dt
                * device_delivery_fraction
            )
            peak_reaction_force = max(
                peak_reaction_force,
                float(np.linalg.norm(reaction_during_actuation)) * device_delivery_fraction,
            )
            peak_reaction_torque = max(
                peak_reaction_torque,
                float(np.linalg.norm(reaction_torque)) / active_fraction if active_fraction > 0.0 else 0.0,
            )

        power_thrust_limit = _power_limited_thrust(available_propulsion_power, drone)
        effective_thrust_limit = min(drone["max_thrust_N"], power_thrust_limit)
        commanded_thrust = max(float(np.dot(desired_force, rotation[:, 2])), 0.0)
        thrust = min(commanded_thrust, effective_thrust_limit)
        if dt > 0.0 and commanded_thrust > effective_thrust_limit + 1e-9:
            saturation_steps += 1
        requested_fixed_power = requested_avionics_power + requested_device_power
        if dt > 0.0 and requested_fixed_power > bus_power_limit + 1e-9 and "power_saturation" not in failures:
            failures.append("power_saturation")
        propulsion_power = _induced_power(thrust, drone)
        power = avionics_power + device_power + propulsion_power
        peak_power = max(peak_power, power)
        if dt > 0.0:
            minimum_thrust_margin = min(minimum_thrust_margin, effective_thrust_limit - mass * _G)

        roll, pitch, yaw = _euler_degrees(rotation)
        tilt = math.degrees(math.acos(float(np.clip(rotation[2, 2], -1.0, 1.0))))
        error = float(np.linalg.norm(true_position_error))
        peak_tilt = max(peak_tilt, tilt)
        max_error = max(max_error, error)

        if step % sample_stride == 0 or step == step_count:
            row: dict[str, float] = {
                "time_s": float(t), "x": float(position[0]), "y": float(position[1]), "z": float(position[2]),
                "roll_deg": float(roll), "pitch_deg": float(pitch), "yaw_deg": float(yaw),
                "power_W": float(power), "remaining_Wh": float(max(remaining_J, 0.0) / 3600.0),
                "target_error_m": error, "target_x": float(target_position[0]),
                "remaining_consumable_kg": float(consumable),
            }
            if thermal_temperature is not None:
                row["temperature_K"] = float(thermal_temperature)
            rows.append(row)

        if step == step_count:
            break

        wind_world = np.array([0.0, scenario["crosswind_m_s"], 0.0])
        relative_wind = wind_world - velocity
        relative_wind_speed = float(np.linalg.norm(relative_wind))
        drag_world = 0.5 * _RHO_AIR * drone["drag_coefficient"] * drone["drag_area_m2"] * relative_wind_speed * relative_wind
        peak_relative_wind = max(peak_relative_wind, relative_wind_speed)
        peak_drag = max(peak_drag, float(np.linalg.norm(drag_world)))
        force_world = thrust * rotation[:, 2] + reaction_world + drag_world - np.array([0.0, 0.0, mass * _G])
        acceleration = force_world / mass
        velocity += acceleration * dt
        position += velocity * dt
        angular_acceleration = (torque - np.cross(omega, inertia * omega)) / inertia
        omega += angular_acceleration * dt
        rotation_angle = float(np.linalg.norm(omega)) * dt
        if rotation_angle > 0.0:
            rotation_axis = omega / np.linalg.norm(omega)
            delta_quaternion = np.array([
                math.cos(0.5 * rotation_angle),
                *(rotation_axis * math.sin(0.5 * rotation_angle)),
            ])
            quaternion = _quat_multiply(quaternion, delta_quaternion)
        quaternion_norm = float(np.linalg.norm(quaternion))
        if not math.isfinite(quaternion_norm) or quaternion_norm < 1e-12:
            raise RuntimeError("non-finite attitude state during integration")
        quaternion /= quaternion_norm

        step_energy = min(power * dt, remaining_J)
        energy_used_J += step_energy
        remaining_J = max(remaining_J - step_energy, 0.0)
        if remaining_J <= 1e-12 and interval_end < duration - 1e-12 and "battery_depleted" not in failures:
            failures.append("battery_depleted")

        if active and method["consumable_kg"] > 0.0:
            consumption = (
                _released_mass(active_start - actuation_start, active_dt, method, scenario["duration_s"])
                * device_delivery_fraction
            )
            consumption = min(consumption, consumable)
            consumable -= consumption
            mass -= consumption

        if thermal_temperature is not None and thermal is not None:
            heat_in = (
                thermal["incident_flux_W_m2"] * thermal["exposed_area_m2"]
                if active
                else 0.0
            )
            thermal_temperature = _advance_lumped_temperature(
                thermal_temperature,
                heat_in,
                thermal["cooling_W_K"],
                thermal["heat_capacity_J_K"],
                drone["ambient_K"],
                dt,
            )
            peak_temperature = max(float(peak_temperature), thermal_temperature)

        next_t = time_points[step + 1]
        if remaining_at_actuation_end is None and next_t >= actuation_end:
            remaining_at_actuation_end = remaining_J

        state = np.concatenate((position, velocity, quaternion, omega))
        if not np.all(np.isfinite(state)):
            raise RuntimeError("non-finite rigid-body state during integration")

    if remaining_at_actuation_end is None:
        remaining_at_actuation_end = remaining_J
    if remaining_J <= 1e-12 and "battery_depleted" not in failures:
        failures.append("battery_depleted")
    evaluated_final_cg = _center_of_gravity(drone, method, consumable, mass)
    if evaluated_final_cg is not None:
        final_cg = evaluated_final_cg
    if remaining_at_actuation_end + 1e-6 < reserve_J + return_energy_estimate:
        failures.append("return_reserve_shortfall")
    if remaining_J + 1e-6 < reserve_J and "return_reserve_shortfall" not in failures:
        failures.append("return_reserve_shortfall")
    if minimum_thrust_margin < 0.0:
        failures.append("hover_thrust_unavailable")
    if max_error > drone["tracking_tolerance_m"]:
        conditional_reasons.append("tracking_tolerance_exceeded")
    if saturation_steps:
        conditional_reasons.append("actuator_saturation_observed")
    if thermal is not None and peak_temperature is not None and peak_temperature > thermal["max_temperature_K"]:
        failures.append("thermal_limit_exceeded")

    failures = list(dict.fromkeys(failures))
    if failures:
        status = "infeasible"
    elif conditional_reasons:
        status = "conditional"
    else:
        status = "feasible_in_model"

    limitations = [
        "Unvalidated assumed airframe, controller, and ideal actuator-disk momentum-theory rotor model; no UAV safety certification.",
        "Rigid-body model omits rotor-resolved wake, ground effect, structural flexibility, and spatially resolved visibility.",
        "Crosswind uses a lumped quadratic drag area; rotor wake is reported only through momentum-theory disk loading and induced velocity.",
        "The inertia tensor is fixed and diagonal even while consumable mass and center of gravity change; this is a screening approximation.",
        "Battery voltage, internal resistance, motor maps, and regenerative power are omitted; stored energy and bus-power limits are enforced directly.",
        "Method reaction is treated as the force on the vehicle in the declared body/world frame; verify sign and mounting geometry.",
        "Physics feasibility is separate from fire-suppression efficacy; suppression success is not inferred.",
    ]
    if thermal is None:
        limitations.append("Thermal safety is unevaluated because calibrated heat-flux and component thermal inputs were not supplied.")
    else:
        limitations.append("The optional lumped thermal model requires independent calibration before use outside screening.")
    if sensor is None:
        limitations.append("Sensor timing, measurement error, and occlusion were not evaluated because no sensor inputs were supplied.")
    else:
        limitations.append("Sensor samples use a seeded delay/error/sample-and-hold screening model, not a calibrated perception stack.")
    if conditional_reasons:
        limitations.append("Conditional model flags: " + ", ".join(conditional_reasons) + ".")

    metrics: dict[str, float | None] = {
        "energy_J": float(energy_used_J),
        "remaining_Wh": float(max(remaining_J, 0.0) / 3600.0),
        "hover_power_W": float(hover_power),
        "peak_tilt_deg": float(peak_tilt),
        "max_position_error_m": float(max_error),
        "peak_power_W": float(peak_power),
        "thrust_margin_N": float(minimum_thrust_margin),
        "mission_duration_s": float(duration),
        "reserve_required_J": float(reserve_J),
        "return_energy_estimate_J": float(return_energy_estimate),
        "actuation_end_remaining_J": float(max(remaining_at_actuation_end, 0.0)),
        "energy_balance_error_J": float(abs(battery_J - remaining_J - energy_used_J)),
        "electrically_unpowered_s": float(electrically_unpowered_s),
        "device_energy_delivered_J": float(device_energy_delivered_J),
        "consumable_used_kg": float(method["loaded_consumable_kg"] - consumable),
        "remaining_consumable_kg": float(consumable),
        "final_mass_kg": float(mass),
        "peak_temperature_K": float(peak_temperature) if peak_temperature is not None else None,
        "peak_relative_wind_m_s": float(peak_relative_wind),
        "peak_drag_N": float(peak_drag),
        "reaction_impulse_Ns": float(reaction_impulse),
        "peak_reaction_force_N": float(peak_reaction_force),
        "peak_reaction_torque_Nm": float(peak_reaction_torque),
        "initial_cg_m": initial_cg.tolist() if initial_cg is not None else None,
        "final_cg_m": final_cg.tolist() if final_cg is not None else None,
        "cg_shift_m": float(np.linalg.norm(final_cg - initial_cg)) if initial_cg is not None and final_cg is not None else None,
        "sensor_updates": int(sensor_updates) if sensor is not None else None,
        "sensor_attempts": int(sensor_attempts) if sensor is not None else None,
        "sensor_update_fraction": float(sensor_updates / sensor_attempts) if sensor is not None and sensor_attempts else None,
        "max_sensor_position_error_m": float(max_sensor_position_error) if sensor is not None else None,
        "rotor_disk_loading_N_m2": float((drone["mass_kg"] + payload_initial) * _G / (drone["rotor_count"] * math.pi * drone["rotor_radius_m"] ** 2)),
        "hover_induced_velocity_m_s": float(math.sqrt((drone["mass_kg"] + payload_initial) * _G / (2.0 * _RHO_AIR * drone["rotor_count"] * math.pi * drone["rotor_radius_m"] ** 2))),
    }
    return {
        "method_id": method["method_id"],
        "status": status,
        "evidence_type": "unvalidated_physics",
        "limitations": limitations,
        "metrics": metrics,
        "series": rows,
        "failures": failures,
    }


def simulate_controls(config: Mapping[str, Any], method_result: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return mass-matched OFF, uncorrected, and corrected comparisons.

    OFF retains both mass and mounting positions. Stored consumable stays in
    its tank rather than being moved into the device point mass; it is not
    emitted or removed from vehicle mass.
    """
    if not isinstance(method_result, Mapping):
        raise ValueError("method_result must be a mapping")
    inactive = dict(method_result)
    device_mass = _finite_number(method_result.get("device_mass_kg", 0.0), "device_mass_kg", minimum=0.0)
    emitted_mass = _finite_number(method_result.get("consumable_kg", 0.0), "consumable_kg", minimum=0.0)
    consumable_mass = _finite_number(
        method_result.get("loaded_consumable_kg", emitted_mass), "loaded_consumable_kg", minimum=0.0
    )
    inactive.update({
        "reaction_force_N": [0.0, 0.0, 0.0],
        "device_power_W": 0.0,
        "device_mass_kg": device_mass,
        "consumable_kg": 0.0,
        "loaded_consumable_kg": consumable_mass,
        "consumable_release": None,
        "nonconsumable_reaction_force_N": [0.0, 0.0, 0.0],
        "series": [],
        "reaction_pulse": {},
        "resource_status": {"status": "not_applicable", "reason": "device inactive in OFF control"},
    })
    return {
        "off": simulate_mission(config, inactive, controller_enabled=False),
        "uncorrected": simulate_mission(config, method_result, controller_enabled=False),
        "corrected": simulate_mission(config, method_result, controller_enabled=True),
    }


__all__ = ["simulate_mission", "simulate_controls"]
