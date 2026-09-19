"""FDS input generation for *bounded* reactive-fire intervention experiments.

The module deliberately has no fitted suppression multiplier.  It writes a
small propane-gas source and, where FDS has a documented transport
mechanism, lets the native solver determine any HRR response.  A generated
input is therefore evidence of a runnable scenario, never evidence that a
method suppresses a fire.

M1 is an imposed low-Mach periodic blower proxy, not an acoustic-wave model;
M2 is a pulsed blower/nozzle proxy, not a validated vortex-ring source; M3 is
a water-droplet transport case.  FDS has no electrohydrodynamic solver or
generic condensed-aerosol chemical-inhibition model, so M4/M5 are blocked
until the required material/chemistry model is supplied.
"""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping


METHOD_IDS = ("M1", "M2", "M3", "M4", "M5")
SOURCE_METHODS = ("M1", "M2", "M3")
NATIVE_SUPPORTED = frozenset(SOURCE_METHODS)
BLOCKED = {
    "M4": "FDS transports particles, but a published agent composition, reaction/inhibition mechanism, and validation basis are absent.",
    "M5": "FDS has no coupled electrohydrodynamic/electrostatic solver; a conductive-vortex or ion-wind source requires a separately verified model.",
}


def default_reactive_config() -> dict[str, Any]:
    """Return explicit research assumptions for a compact 16 s FDS case.

    These are computational starting values, not equipment prescriptions or
    calibrated fire-suppression settings.  The burner is not changed by an
    intervention; only the native heat/mass/flow coupling can change HRR.
    """
    return {
        "version": 1,
        "note": "FDS 6.11.1 compact reactive research scenario; values are disclosed starting assumptions, not calibrated suppression data.",
        "solver": {"name": "FDS", "target_release": "6.11.1"},
        "case": {
            "duration_s": 16.0,
            "intervention_start_s": 6.0,
            "intervention_end_s": 10.0,
            "post_observation_s": 6.0,
            "mesh_cell_m": 0.05,
            "domain_x_m": [0.0, 1.5],
            "domain_y_m": [-0.6, 0.6],
            "domain_z_m": [0.0, 1.0],
        },
        "burner": {
            "area_m2": 0.04,
            "gas_fuel_mass_flux_kg_m2_s": 0.009,
        },
        "methods": {
            "M1": {
                "frequency_hz": 60.0,
                "velocity_rms_m_s": 0.4,
                "vent_area_m2": 0.01,
                "kind": "mechanically_forced_airflow_envelope",
            },
            "M2": {
                "exit_velocity_m_s": 8.0,
                "pulse_duration_s": 0.05,
                "period_s": 1.0,
                "vent_area_m2": 0.01,
                "kind": "pulsed_nozzle_proxy",
            },
            "M3": {
                "water_flow_kg_s": 0.005,
                "droplet_diameter_um": 100.0,
                "carrier_velocity_m_s": 5.0,
                "vent_area_m2": 0.01,
                "kind": "water_particle_transport",
            },
        },
        "evidence": {
            "published_agent_or_chemistry": {},
            "source_calibration": {},
            "required_schema": {
                "M4": ["agent_name", "composition_mass_fraction", "inhibition_or_reaction_model", "validation_reference"],
                "M5": ["electrode_geometry", "voltage_waveform", "charge_transport_model", "validation_reference"],
            },
        },
    }


def default_reactive_conditions() -> list[dict[str, Any]]:
    """Return C0, five singles, ten simultaneous pairs and twenty sequences.

    Pair components use half source amplitude in a shared window. A
    sequential component uses full source amplitude for half the intervention
    window, NOT the full single-method integrated dose.  No cross-method "equal effectiveness" assumption
    is encoded.  `partial_single_id` identifies the matching component for
    later, correctly paired analysis.
    """
    start, full, half = 6.0, 4.0, 2.0
    result = [{
        "id": "C0", "methods": [], "mode": "control", "order": [],
        "dose_fraction": {}, "schedule": {}, "metadata": {"native_baseline": True},
    }]
    for method in METHOD_IDS:
        result.append({
            "id": f"S_{method}", "methods": [method], "mode": "single", "order": [method],
            "dose_fraction": {method: 1.0}, "schedule": {method: {"start_s": start, "duration_s": full}},
            "metadata": {"partial_single_id": f"S_{method}"},
        })
    for left_i, left in enumerate(METHOD_IDS):
        for right in METHOD_IDS[left_i + 1:]:
            pair = f"{left}_{right}"
            result.append({
                "id": f"SIM_{pair}", "methods": [left, right], "mode": "simultaneous", "order": [left, right],
                "dose_fraction": {left: .5, right: .5},
                "schedule": {
                    left: {"start_s": start, "duration_s": full},
                    right: {"start_s": start, "duration_s": full},
                },
                "metadata": {
                    "partial_single_id": {left: f"P_SIM_{pair}_{left}", right: f"P_SIM_{pair}_{right}"},
                    "component_dose_rule": "half configured source amplitude over shared four-second window; integrated resource is reported separately",
                },
            })
            for first, second in ((left, right), (right, left)):
                result.append({
                    "id": f"SEQ_{first}_THEN_{second}", "methods": [first, second], "mode": "sequential", "order": [first, second],
                    "dose_fraction": {first: 1.0, second: 1.0},
                    "schedule": {
                        first: {"start_s": start, "duration_s": half},
                        second: {"start_s": start + half, "duration_s": half},
                    },
                    "metadata": {
                        "partial_single_id": {first: f"P_SEQ_{first}_FIRST", second: f"P_SEQ_{second}_SECOND"},
                        "component_dose_rule": "full configured source amplitude over each two-second sequential window, not full single-method integrated dose",
                    },
                })
    return result


def _deep_merge(target: dict[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in patch.items():
        if key not in target:
            raise ValueError(f"unknown reactive configuration key: {key}")
        if isinstance(target[key], dict):
            if not isinstance(value, Mapping):
                raise ValueError(f"{key} must be an object")
            _deep_merge(target[key], value)
        else:
            target[key] = value
    return target


def _number(value: Any, label: str, *, low: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < low:
        raise ValueError(f"{label} must be a finite number >= {low}")
    return float(value)


def _normalise_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    result = default_reactive_config()
    if config:
        _deep_merge(result, config)
    case = result["case"]
    duration = _number(case["duration_s"], "case.duration_s", low=.2)
    start = _number(case["intervention_start_s"], "case.intervention_start_s")
    end = _number(case["intervention_end_s"], "case.intervention_end_s")
    if not 0 <= start < end <= duration:
        raise ValueError("intervention window must be within duration")
    if abs((duration - end) - _number(case["post_observation_s"], "case.post_observation_s")) > 1.0e-9:
        raise ValueError("duration_s must equal intervention_end_s + post_observation_s")
    mesh = _number(case["mesh_cell_m"], "case.mesh_cell_m", low=.01)
    if mesh > .05:
        raise ValueError("mesh_cell_m must be <= 0.05 m so every 0.1 m source patch has at least two cells")
    burner = result["burner"]
    for key in ("area_m2", "gas_fuel_mass_flux_kg_m2_s"):
        _number(burner[key], f"burner.{key}")
    for method, fields in result["methods"].items():
        for key, value in fields.items():
            if key != "kind":
                _number(value, f"methods.{method}.{key}")
    if burner["area_m2"] <= 0.0:
        raise ValueError("burner.area_m2 must be positive and resolved by the mesh")
    for method in SOURCE_METHODS:
        # The partitioned xmin boundary contains fixed 0.1 m x 0.1 m patches.
        if not math.isclose(result["methods"][method]["vent_area_m2"], .01, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"methods.{method}.vent_area_m2 must equal the fixed native patch area 0.01 m2")
    pulse = result["methods"]["M2"]
    if not 0.0 < pulse["pulse_duration_s"] <= pulse["period_s"]:
        raise ValueError("M2 requires 0 < pulse_duration_s <= period_s")
    return result


def _condition_lookup(condition: Mapping[str, Any] | str) -> dict[str, Any]:
    if isinstance(condition, str):
        for candidate in default_reactive_conditions():
            if candidate["id"] == condition:
                return candidate
        raise ValueError(f"unknown reactive condition: {condition}")
    if not isinstance(condition, Mapping):
        raise ValueError("condition must be a condition object or id")
    return deepcopy(dict(condition))


def _normalise_condition(config: dict[str, Any], condition: Mapping[str, Any] | str) -> dict[str, Any]:
    item = _condition_lookup(condition)
    needed = {"id", "methods", "mode", "order", "dose_fraction", "schedule", "metadata"}
    absent = needed - set(item)
    if absent:
        raise ValueError(f"condition missing keys: {sorted(absent)}")
    if not isinstance(item["id"], str) or not item["id"]:
        raise ValueError("condition id must be a nonempty string")
    methods = list(item["methods"])
    if len(methods) != len(set(methods)) or any(method not in METHOD_IDS for method in methods):
        raise ValueError("condition methods must be unique M1..M5 identifiers")
    if item["mode"] not in {"control", "single", "simultaneous", "sequential"}:
        raise ValueError("unsupported condition mode")
    if list(item["order"]) != methods and item["mode"] != "control":
        raise ValueError("order must list each condition method once")
    if item["mode"] == "control" and methods:
        raise ValueError("control condition cannot include methods")
    start = config["case"]["intervention_start_s"]
    end = config["case"]["intervention_end_s"]
    for method in methods:
        fraction = _number(item["dose_fraction"].get(method), f"dose_fraction.{method}")
        if fraction <= 0 or fraction > 1:
            raise ValueError("dose fractions must be in (0, 1]")
        spec = item["schedule"].get(method)
        if not isinstance(spec, Mapping):
            raise ValueError(f"schedule missing {method}")
        event_start = _number(spec.get("start_s"), f"schedule.{method}.start_s")
        event_duration = _number(spec.get("duration_s"), f"schedule.{method}.duration_s", low=.001)
        if event_start < start or event_start + event_duration > end + 1.0e-9:
            raise ValueError(f"{method} schedule must be inside intervention window")
    return item


def _pulse_count(duration: float, period: float) -> int:
    if period <= 0.0:
        raise ValueError("pulse period must be positive")
    count = int(math.ceil(max(0.0, duration / period - 1e-12)))
    if count > 100000:
        raise ValueError("native ramp is limited to 100000 pulses")
    return count


def _ramp_points(start: float, duration: float, *, cycles: int | None = None,
                 period: float | None = None, pulse_width: float | None = None) -> list[tuple[float, float]]:
    """Bounded trapezoids: ramps rise and fall INSIDE each on interval."""
    if not math.isfinite(start) or not math.isfinite(duration) or start < 0.0 or duration <= 0.0:
        raise ValueError("ramp start must be nonnegative and duration positive, both finite")
    if cycles is not None:
        if type(cycles) is not int or not 0 <= cycles <= 100000:
            raise ValueError("cycles must be an integer in [0, 100000]")
        if period is None or not math.isfinite(period) or period <= 0.0:
            raise ValueError("pulsed ramp needs a finite positive period")
        width = pulse_width if pulse_width is not None else period * .5
        if not math.isfinite(width) or not 0.0 < width <= period:
            raise ValueError("pulse width must be in (0, period]")
        intervals = [(start + index * period, min(start + duration, start + index * period + width))
                     for index in range(cycles) if index * period < duration]
    else:
        intervals = [(start, start + duration)]
    # Adjacent on windows with 100% duty form one continuous activation.
    merged: list[tuple[float, float]] = []
    for on, off in intervals:
        if merged and on <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(off, merged[-1][1]))
        else:
            merged.append((on, off))
    points = [(0.0, 0.0)]
    for on, off in merged:
        epsilon = min(.001, (off - on) / 20.0)
        if not on < on + epsilon < off - epsilon < off:
            raise ValueError("pulse is below floating-point time resolution")
        for point in ((on, 0.0), (on + epsilon, 1.0), (off - epsilon, 1.0), (off, 0.0)):
            if point == points[-1]:
                continue
            points.append(point)
    if points[-1][0] < start + duration:
        points.append((start + duration, 0.0))
    return points


def _pulse_ramp(identifier: str, start: float, duration: float, *, cycles: int | None = None,
                period: float | None = None, pulse_width: float | None = None) -> list[str]:
    points = _ramp_points(start, duration, cycles=cycles, period=period, pulse_width=pulse_width)
    # Six significant digits can collapse distinct sub-millisecond points.
    return [f"&RAMP ID='{identifier}', T={time_s:.17g}, F={value:.17g} /" for time_s, value in points]


def _method_resource(config: dict[str, Any], method: str, duration: float, fraction: float) -> dict[str, float | str]:
    spec = config["methods"].get(method)
    if spec is None:
        return {"method_id": method, "status": "needs_model"}
    extra = {}
    if method == "M2":
        extra = {"cycles": _pulse_count(duration, spec["period_s"]),
                 "period": spec["period_s"], "pulse_width": spec["pulse_duration_s"]}
    points = _ramp_points(0.0, duration, **extra)
    on_time = sum((b[0] - a[0]) * (a[1] + b[1]) * .5 for a, b in zip(points, points[1:]))
    result = {"method_id": method, "status": "proxy", "input_energy_J": None,
              "ramp_integral_s": on_time, "source_amplitude_fraction": fraction}
    if method == "M1":
        result["air_volume_m3"] = math.sqrt(2.0) * spec["velocity_rms_m_s"] * spec["vent_area_m2"] * on_time * fraction
    elif method == "M2":
        result.update(air_volume_m3=spec["exit_velocity_m_s"] * spec["vent_area_m2"] * on_time * fraction,
                      pulse_count=extra["cycles"])
    elif method == "M3":
        result.update(status="native_particle_transport", water_mass_kg=spec["water_flow_kg_s"] * on_time * fraction)
    else:
        return {"method_id": method, "status": "needs_model"}
    return result

def capabilities(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return method-by-method native capability gates without fabricating efficacy."""
    cfg = _normalise_config(config)
    evidence = cfg["evidence"]
    result: dict[str, Any] = {}
    for method in METHOD_IDS:
        if method in NATIVE_SUPPORTED:
            result[method] = {
                "status": "ready",
                "native_mechanism": cfg["methods"][method]["kind"],
                "claim_boundary": {
                    "M1": "FDS low-Mach mechanically forced-airflow envelope; it does not resolve a 60 Hz acoustic pressure wave, oscillatory source field, or source calibration.",
                    "M2": "FDS pulsed nozzle flow; a vortex ring must be diagnosed from native flow output and separately validated.",
                    "M3": "FDS droplet/evaporation/heat-transfer transport; water-to-fuel suppression response remains mesh and fuel-model dependent.",
                }[method],
                "requires": ["native HRR output", "native DEVC output", "mesh sensitivity", "experimental validation"],
            }
        else:
            required = evidence["required_schema"][method]
            supplied = evidence["published_agent_or_chemistry"].get(method, {})
            missing = [key for key in required if key not in supplied]
            result[method] = {
                "status": "needs_model",
                "reason": BLOCKED[method],
                "required_schema": required,
                "missing": missing,
            }
    return result


def _render_input(config: dict[str, Any], condition: dict[str, Any], chid: str) -> tuple[str, list[dict[str, Any]]]:
    case, burner = config["case"], config["burner"]
    dx = case["mesh_cell_m"]
    x0, x1 = case["domain_x_m"]
    y0, y1 = case["domain_y_m"]
    z0, z1 = case["domain_z_m"]
    ijk = (round((x1 - x0) / dx), round((y1 - y0) / dx), round((z1 - z0) / dx))
    if min(ijk) < 4 or any(abs(actual * dx - length) > 1.0e-9 for actual, length in zip(ijk, (x1-x0, y1-y0, z1-z0))):
        raise ValueError("domain extents must be exact multiples of mesh_cell_m")
    # This compact benchmark deliberately uses fixed physical coordinates.  Do
    # not silently shift or clip the source patches when a caller changes the
    # domain; require enough room and alignment to resolve their geometry.
    if x0 > 0 or x1 < 1.5 or y0 > -.6 or y1 < .6 or z0 != 0 or z1 < 1.0:
        raise ValueError("domain must contain the fixed [0,1.5] x [-.6,.6] x [0,1] compact benchmark")
    burner_side = math.sqrt(burner["area_m2"])
    bx0, bx1 = .75 - burner_side / 2, .75 + burner_side / 2
    by0, by1 = -burner_side / 2, burner_side / 2
    if not x0 <= bx0 < bx1 <= x1 or not y0 <= by0 < by1 <= y1:
        raise ValueError("burner must lie inside the native domain")
    fixed_coordinates = ((x0, (bx0, bx1)), (y0, (-.5, -.4, -.2, -.1, .1, .2, by0, by1)), (z0, (.2, .3)))
    for origin, coordinates in fixed_coordinates:
        for coordinate in coordinates:
            if abs((coordinate - origin) / dx - round((coordinate - origin) / dx)) > 1.0e-9:
                raise ValueError("mesh_cell_m and domain origin must align with fixed burner/source coordinates")
    lines = [
        f"&HEAD CHID='{chid}', TITLE='Reactive intervention research case {condition['id']}' /",
        f"&MESH IJK={ijk[0]},{ijk[1]},{ijk[2]}, XB={x0:.6g},{x1:.6g},{y0:.6g},{y1:.6g},{z0:.6g},{z1:.6g} /",
        f"&TIME T_END={case['duration_s']:.6g} /",
        "&DUMP DT_HRR=0.1, DT_DEVC=0.1, DT_SLCF=0.25, NFRAMES=100 /",
        "&MISC TMPA=20., SUPPRESSION=.TRUE. /",
        "&COMB EXTINCTION_MODEL='EXTINCTION 2' /",
        "&REAC ID='PROPANE_REAC', FUEL='PROPANE', SOOT_YIELD=0.01 /",
        # A source of propane gas gives the compact case a real, pre-existing
        # reacting flame without an artificial intervention-time HRR curve.
        # It is not a condensed-fuel water-suppression validation case.
        f"&SURF ID='FUEL_GAS', MASS_FLUX={burner['gas_fuel_mass_flux_kg_m2_s']:.6g}, SPEC_ID='PROPANE' /",
        "&SPEC ID='PROPANE' /",
        f"&VENT XB={bx0:.6g},{bx1:.6g},{by0:.6g},{by1:.6g},0.,0., SURF_ID='FUEL_GAS' /",
        # The xmin face is intentionally partitioned: no OPEN vent overlaps a
        # fixed source patch.  Every condition declares all three patches, so
        # C0 and intervention cases share source geometry and an inactive
        # source is genuinely zero-flow rather than hidden by a larger OPEN.
        f"&VENT XB={x0:.6g},{x0:.6g},{y0:.6g},{y1:.6g},{z0:.6g},0.2, SURF_ID='OPEN' /",
        f"&VENT XB={x0:.6g},{x0:.6g},{y0:.6g},{y1:.6g},0.3,{z1:.6g}, SURF_ID='OPEN' /",
        f"&VENT XB={x0:.6g},{x0:.6g},{y0:.6g},-0.5,0.2,0.3, SURF_ID='OPEN' /",
        f"&VENT XB={x0:.6g},{x0:.6g},-0.4,-0.2,0.2,0.3, SURF_ID='OPEN' /",
        f"&VENT XB={x0:.6g},{x0:.6g},-0.1,0.1,0.2,0.3, SURF_ID='OPEN' /",
        f"&VENT XB={x0:.6g},{x0:.6g},0.2,{y1:.6g},0.2,0.3, SURF_ID='OPEN' /",
        f"&VENT XB={x1:.6g},{x1:.6g},{y0:.6g},{y1:.6g},{z0:.6g},{z1:.6g}, SURF_ID='OPEN' /",
        f"&VENT XB={x0:.6g},{x1:.6g},{y0:.6g},{y0:.6g},{z0:.6g},{z1:.6g}, SURF_ID='OPEN' /",
        f"&VENT XB={x0:.6g},{x1:.6g},{y1:.6g},{y1:.6g},{z0:.6g},{z1:.6g}, SURF_ID='OPEN' /",
        f"&VENT XB={x0:.6g},{x1:.6g},{y0:.6g},{y1:.6g},{z1:.6g},{z1:.6g}, SURF_ID='OPEN' /",
        "&DEVC ID='TARGET_Q', XYZ=0.75,0.,0.0201, IOR=3, QUANTITY='GAUGE HEAT FLUX' /",
        "&DEVC ID='TARGET_T', XYZ=0.75,0.,0.25, QUANTITY='TEMPERATURE' /",
        "&DEVC ID='TARGET_O2', XYZ=0.75,0.,0.25, QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN' /",
        f"&DEVC ID='SOURCE_M1_U', XYZ={x0 + dx/2:.6g},-0.45,0.25, QUANTITY='U-VELOCITY' /",
        f"&DEVC ID='SOURCE_M2_U', XYZ={x0 + dx/2:.6g},-0.15,0.25, QUANTITY='U-VELOCITY' /",
        f"&DEVC ID='SOURCE_M3_U', XYZ={x0 + dx/2:.6g},0.15,0.25, QUANTITY='U-VELOCITY' /",
        f"&DEVC ID='SOURCE_M3_DVF', XYZ={x0 + dx/2:.6g},0.15,0.25, QUANTITY='DROPLET VOLUME FRACTION', PART_ID='WATER_SOURCE' /",
        "&SLCF PBY=0., QUANTITY='TEMPERATURE' /",
        "&SLCF PBY=0., QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN' /",
    ]
    resources: list[dict[str, Any]] = []
    active = set(condition["methods"])
    y_slots = {"M1": -.45, "M2": -.15, "M3": .15}
    for method in condition["methods"]:
        schedule = condition["schedule"][method]
        resources.append(_method_resource(config, method, float(schedule["duration_s"]), float(condition["dose_fraction"][method])))
    # FDS needs the particle class declared before the device that observes it.
    m3 = config["methods"]["M3"]
    lines.extend([
        f"&PART ID='WATER_SOURCE', SPEC_ID='WATER VAPOR', DIAMETER={m3['droplet_diameter_um']:.6g}, SAMPLING_FACTOR=10 /",
        "&SPEC ID='WATER VAPOR' /",
    ])
    for method in SOURCE_METHODS:
        ramp = f"R_{method}_{condition['id']}".replace("-", "_")
        if method not in active:
            lines.extend([f"&RAMP ID='{ramp}', T=0., F=0. /", f"&RAMP ID='{ramp}', T={case['duration_s']:.6g}, F=0. /"])
            fraction = 0.0
        else:
            schedule = condition["schedule"][method]
            start, duration = float(schedule["start_s"]), float(schedule["duration_s"])
            fraction = float(condition["dose_fraction"][method])
            if method == "M2":
                m = config["methods"][method]
                pulses = _pulse_count(duration, m["period_s"])
                lines.extend(_pulse_ramp(ramp, start, duration, cycles=pulses, period=m["period_s"], pulse_width=m["pulse_duration_s"]))
            else:
                lines.extend(_pulse_ramp(ramp, start, duration))
        y_center = y_slots[method]
        if method == "M1":
            m = config["methods"][method]
            lines.append(f"&SURF ID='SRC_{method}', VEL=-{m['velocity_rms_m_s'] * math.sqrt(2) * fraction:.17g}, RAMP_V='{ramp}' /")
        elif method == "M2":
            m = config["methods"][method]
            lines.append(f"&SURF ID='SRC_{method}', VEL=-{m['exit_velocity_m_s'] * fraction:.17g}, RAMP_V='{ramp}' /")
        else:
            particle_flux = m3["water_flow_kg_s"] * fraction / m3["vent_area_m2"]
            lines.append(f"&SURF ID='SRC_{method}', VEL=-{m3['carrier_velocity_m_s']:.6g}, RAMP_V='{ramp}', PART_ID='WATER_SOURCE', PARTICLE_MASS_FLUX={particle_flux:.17g}, RAMP_PART='{ramp}' /")
        lines.append(f"&VENT XB={x0:.6g},{x0:.6g},{y_center-.05:.6g},{y_center+.05:.6g},0.2,0.3, SURF_ID='SRC_{method}' /")
    lines.extend(["&TAIL /", ""])
    return "\n".join(lines), resources


def build_reactive_case(config: Mapping[str, Any] | None, condition: Mapping[str, Any] | str, output_dir: str | Path) -> dict[str, Any]:
    """Build one FDS input and its evidence gate below *output_dir*.

    `status='ready'` means that all requested components have an FDS input
    representation.  It does *not* mean suppression is validated.  A blocked
    M4/M5 condition receives `needs_model` and no input path, preventing a
    native runner from silently substituting an arbitrary decay curve.
    """
    cfg = _normalise_config(config)
    item = _normalise_condition(cfg, condition)
    caps = capabilities(cfg)
    unsupported = [method for method in item["methods"] if caps[method]["status"] != "ready"]
    base = Path(output_dir).resolve()
    base.mkdir(parents=True, exist_ok=True)
    physical_scope = {
        "burner": "Constant propane mass-flux source; intervention does not change source mass flux or fuel properties. It establishes a reacting-flame gate but does not validate condensed-fuel extinguishment.",
        "native_response": "HRR, temperature, oxygen and water/flow effects must be read from FDS output; this generator creates no outcome score or forced HRR reduction.",
        "method_capabilities": {method: caps[method] for method in item["methods"]},
    }
    payload: dict[str, Any] = {
        "condition_id": item["id"], "condition": item, "status": "needs_model" if unsupported else "ready",
        "unsupported_methods": unsupported, "physical_scope": physical_scope,
        "resource": [_method_resource(cfg, method, float(item["schedule"][method]["duration_s"]), float(item["dose_fraction"][method])) for method in item["methods"]],
        "resource_summary": {"input_energy_J": 0.0 if not item["methods"] else None, "rule": "input energy for powered source proxies is unknown; only no-intervention C0 is zero"},
        "observations": {
            "heat_flux_kW_m2": "TARGET_Q", "temperature_C": "TARGET_T",
            "oxygen_volume_fraction": "TARGET_O2", "hrr_kW": "HRR",
            "source_m1_u_m_s": "SOURCE_M1_U", "source_m2_u_m_s": "SOURCE_M2_U",
            "source_m3_u_m_s": "SOURCE_M3_U", "source_m3_droplet_volume_fraction": "SOURCE_M3_DVF",
        },
        "intervention_activation": {
            "status": "unverified",
            "active_methods": [method for method in item["methods"] if method in NATIVE_SUPPORTED],
            "method_windows_s": {
                method: [item["schedule"][method]["start_s"], item["schedule"][method]["start_s"] + item["schedule"][method]["duration_s"]]
                for method in item["methods"] if method in NATIVE_SUPPORTED
            },
            "required_channels": {
                "M1": ["source_m1_u_m_s"], "M2": ["source_m2_u_m_s"],
                "M3": ["source_m3_u_m_s", "source_m3_droplet_volume_fraction"],
            },
            "off_channels": ["source_m1_u_m_s", "source_m2_u_m_s", "source_m3_u_m_s", "source_m3_droplet_volume_fraction"],
            "thresholds": {
                "M1": {"source_m1_u_m_s": {"value": .05, "unit": "m/s", "comparison": "abs_gte"}},
                "M2": {"source_m2_u_m_s": {"value": .2, "unit": "m/s", "comparison": "abs_gte"}},
                "M3": {
                    "source_m3_u_m_s": {"value": .1, "unit": "m/s", "comparison": "abs_gte"},
                    # FDS 6.11.1 writes this DEVC's unit header as empty; keep
                    # that exact observed unit rather than inventing "1".
                    "source_m3_droplet_volume_fraction": {"value": 1.0e-12, "unit": "", "comparison": "gte"},
                },
            },
            "proof": None,
            "reason": "Input generation alone cannot prove that FDS accepted and activated a source; compare source diagnostics within the declared intervention window after a completed native run.",
        },
        "observation_contract": {
            "hrr_csv": "<CHID>_hrr.csv", "device_csv": "<CHID>_devc.csv",
            "fields": ["TEMPERATURE", "VOLUME FRACTION OXYGEN"],
            "intervention_start_s": cfg["case"]["intervention_start_s"],
            "intervention_end_s": cfg["case"]["intervention_end_s"],
            "preregistered_validity_gate": {
                "name": "pre_intervention_burning",
                "window_s": [cfg["case"]["intervention_start_s"] - 1.0, cfg["case"]["intervention_start_s"]],
                "quantity": "HRR", "minimum_samples": 2, "minimum_hrr_kW": .01,
                "failure_action": "mark run invalid for extinction; never count a never-ignited run as extinguished",
            },
            "preregistered_extinction_gate": {
                "requires_valid_pre_intervention_burning": True,
                "quantity": "HRR", "maximum_hrr_kW": .1, "minimum_hold_s": 1.0,
                "failure_action": "record no extinction event; native simulation remains unvalidated until mesh sensitivity and experimental comparison",
            },
            "unsupported_channels": {"carbon_monoxide_volume_fraction": "No CO_YIELD is set because no fuel-specific CO-yield evidence was provided; CO is not assumed zero."},
            "required_native_metrics": ["time-resolved HRR", "flame temperature", "oxygen volume fraction", "source diagnostics", "completion marker"],
        },
        "config": cfg,
    }
    if unsupported:
        payload["input_path"] = None
        payload["input_sha256"] = None
        (base / "needs_model.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        return payload
    safe_id = "".join(char if char.isalnum() or char in "_-" else "_" for char in item["id"])
    chid = f"reactive_{safe_id}".lower()
    text, resources = _render_input(cfg, item, chid)
    input_path = base / f"{chid}.fds"
    input_path.write_text(text, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(input_path.read_bytes()).hexdigest()
    payload.update({"input_path": str(input_path), "input_sha256": digest, "chid": chid, "resource": resources})
    (base / "case_manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return payload
