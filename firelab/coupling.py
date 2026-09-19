"""Validated one-way exchange utilities for rectilinear CFD fields.

The functions here only translate, interpolate and conservatively remap data.
They do not advance either solver and therefore do not establish a validated
two-way coupling.  Mass, momentum and sensible enthalpy remain separate state
variables so an imported enthalpy field cannot silently replace or duplicate a
combustion heat-release source.
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np


class CouplingError(ValueError):
    """Raised when exchange coordinates, units or arrays violate the contract."""


_UNITS = {
    "m": ("length", 1.0, 0.0),
    "cm": ("length", 1.0e-2, 0.0),
    "mm": ("length", 1.0e-3, 0.0),
    "s": ("time", 1.0, 0.0),
    "ms": ("time", 1.0e-3, 0.0),
    "K": ("temperature", 1.0, 0.0),
    "C": ("temperature", 1.0, 273.15),
    "m/s": ("velocity", 1.0, 0.0),
    "kg/m3": ("mass_density", 1.0, 0.0),
    "kg/(m2 s)": ("momentum_density", 1.0, 0.0),
    "J/m3": ("enthalpy_density", 1.0, 0.0),
    "kg/(m3 s)": ("mass_source", 1.0, 0.0),
    "N/m3": ("momentum_source", 1.0, 0.0),
    "W/m3": ("energy_source", 1.0, 0.0),
}


def convert_units(values, from_unit: str, to_unit: str) -> np.ndarray:
    """Convert an array between explicitly supported compatible units."""
    if from_unit not in _UNITS or to_unit not in _UNITS:
        raise CouplingError(f"unsupported unit conversion: {from_unit!r} -> {to_unit!r}")
    source_kind, source_scale, source_offset = _UNITS[from_unit]
    target_kind, target_scale, target_offset = _UNITS[to_unit]
    if source_kind != target_kind:
        raise CouplingError(f"incompatible unit dimensions: {source_kind} and {target_kind}")
    array = np.asarray(values, dtype=float)
    if not np.all(np.isfinite(array)):
        raise CouplingError("unit conversion values must be finite")
    si_values = array * source_scale + source_offset
    return (si_values - target_offset) / target_scale


def _frame(frame: Mapping) -> tuple[np.ndarray, np.ndarray]:
    if frame.get("type") != "right_handed_cartesian" or frame.get("units") != "m":
        raise CouplingError("coordinate frame must be right_handed_cartesian in metres")
    origin = np.asarray(frame.get("origin_m"), dtype=float)
    basis = np.asarray(frame.get("basis"), dtype=float)
    if origin.shape != (3,) or basis.shape != (3, 3) or not np.all(np.isfinite(origin)) or not np.all(np.isfinite(basis)):
        raise CouplingError("coordinate frame origin/basis have invalid shape or values")
    if not np.allclose(basis.T @ basis, np.eye(3), rtol=0.0, atol=1.0e-10):
        raise CouplingError("coordinate frame basis must be orthonormal")
    if not math.isclose(float(np.linalg.det(basis)), 1.0, rel_tol=0.0, abs_tol=1.0e-10):
        raise CouplingError("coordinate frame basis must be right handed")
    return origin, basis


def transform_points(points, source_frame: Mapping, target_frame: Mapping) -> np.ndarray:
    """Transform Cartesian points between explicit rigid coordinate frames."""
    source_origin, source_basis = _frame(source_frame)
    target_origin, target_basis = _frame(target_frame)
    array = np.asarray(points, dtype=float)
    if array.ndim < 1 or array.shape[-1] != 3 or not np.all(np.isfinite(array)):
        raise CouplingError("points must be finite with a final dimension of three")
    world = array @ source_basis.T + source_origin
    return (world - target_origin) @ target_basis


def interpolate_time(times_s: Sequence[float], values, query_time_s: float) -> np.ndarray:
    """Linearly interpolate the first array dimension, rejecting extrapolation."""
    times = np.asarray(times_s, dtype=float)
    array = np.asarray(values, dtype=float)
    if times.ndim != 1 or len(times) < 1 or array.shape[:1] != times.shape:
        raise CouplingError("values first dimension must match the one-dimensional time axis")
    if not np.all(np.isfinite(times)) or not np.all(np.diff(times) > 0) or not np.all(np.isfinite(array)):
        raise CouplingError("times must increase strictly and all data must be finite")
    if not math.isfinite(query_time_s) or query_time_s < times[0] or query_time_s > times[-1]:
        raise CouplingError("time extrapolation is not allowed")
    upper = int(np.searchsorted(times, query_time_s, side="left"))
    if upper < len(times) and times[upper] == query_time_s:
        return array[upper].copy()
    lower = upper - 1
    weight = (query_time_s - times[lower]) / (times[upper] - times[lower])
    return array[lower] * (1.0 - weight) + array[upper] * weight


def _edges(grid: Mapping[str, Sequence[float]]) -> dict[str, np.ndarray]:
    result = {}
    for axis in "xyz":
        values = np.asarray(grid.get(axis), dtype=float)
        if values.ndim != 1 or len(values) < 2 or not np.all(np.isfinite(values)) or not np.all(np.diff(values) > 0):
            raise CouplingError(f"{axis} cell edges must be finite and strictly increasing")
        result[axis] = values
    return result


def _overlap(target: np.ndarray, source: np.ndarray) -> np.ndarray:
    left = np.maximum(target[:-1, None], source[None, :-1])
    right = np.minimum(target[1:, None], source[None, 1:])
    return np.maximum(right - left, 0.0)


def conservative_remap(
    source_values,
    source_edges_m: Mapping[str, Sequence[float]],
    target_edges_m: Mapping[str, Sequence[float]],
    *,
    conservation_atol: float = 1.0e-10,
) -> dict:
    """Map 3-D cell averages using exact rectilinear overlap volumes.

    Target cells must lie completely inside the source domain.  Thus no value is
    extrapolated.  The returned integral comparison is over the target domain;
    it also proves whole-domain conservation when source and target extents are
    identical.
    """
    source_edges = _edges(source_edges_m)
    target_edges = _edges(target_edges_m)
    source = np.asarray(source_values, dtype=float)
    expected_shape = tuple(len(source_edges[axis]) - 1 for axis in "zyx")
    if source.shape != expected_shape or not np.all(np.isfinite(source)):
        raise CouplingError(f"source_values must be finite with shape {expected_shape}")
    for axis in "xyz":
        if target_edges[axis][0] < source_edges[axis][0] or target_edges[axis][-1] > source_edges[axis][-1]:
            raise CouplingError(f"target {axis} extent lies outside source; extrapolation is disabled")

    overlaps = {axis: _overlap(target_edges[axis], source_edges[axis]) for axis in "xyz"}
    target_volume = (
        np.diff(target_edges["z"])[:, None, None]
        * np.diff(target_edges["y"])[None, :, None]
        * np.diff(target_edges["x"])[None, None, :]
    )
    accumulated = np.einsum(
        "ka,jb,ic,abc->kji",
        overlaps["z"],
        overlaps["y"],
        overlaps["x"],
        source,
        optimize=True,
    )
    mapped = accumulated / target_volume
    target_integral = float(np.sum(mapped * target_volume))
    overlap_integral = float(accumulated.sum())
    error = target_integral - overlap_integral
    tolerance = conservation_atol + 1.0e-12 * abs(overlap_integral)
    if abs(error) > tolerance:
        raise CouplingError("conservative remap integral check failed")
    same_domain = all(
        np.isclose(target_edges[a][[0, -1]], source_edges[a][[0, -1]], rtol=0.0, atol=1.0e-12).all()
        for a in "xyz"
    )
    return {
        "values": mapped,
        "source_integral_over_target_domain": overlap_integral,
        "target_integral": target_integral,
        "integral_error": error,
        "whole_source_domain_covered": same_domain,
        "extrapolated": False,
        "mapping": "exact_rectilinear_cell_volume_overlap",
    }


def build_exchange_bundle(
    *,
    time_s: float,
    grid_edges_m: Mapping[str, Sequence[float]],
    mass_density_kg_m3,
    momentum_density_kg_m2_s,
    sensible_enthalpy_density_J_m3,
    metadata: Mapping | None = None,
) -> dict:
    """Validate and package distinct conservative state variables.

    Sensible enthalpy is exchange state, not a volumetric combustion heat-release
    rate.  Metadata asking to replace or duplicate a heat source is rejected.
    """
    if not math.isfinite(time_s):
        raise CouplingError("exchange time must be finite")
    edges = _edges(grid_edges_m)
    shape = tuple(len(edges[axis]) - 1 for axis in "zyx")
    mass = np.asarray(mass_density_kg_m3, dtype=float)
    momentum = np.asarray(momentum_density_kg_m2_s, dtype=float)
    enthalpy = np.asarray(sensible_enthalpy_density_J_m3, dtype=float)
    if mass.shape != shape or enthalpy.shape != shape or momentum.shape != shape + (3,):
        raise CouplingError(f"exchange arrays must use scalar shape {shape} and momentum shape {shape + (3,)}")
    if not np.all(np.isfinite(mass)) or not np.all(np.isfinite(momentum)) or not np.all(np.isfinite(enthalpy)):
        raise CouplingError("exchange arrays must be finite")
    if np.any(mass < 0):
        raise CouplingError("mass density cannot be negative")
    details = dict(metadata or {})
    forbidden = (
        details.get("replace_combustion_heat_source"),
        details.get("includes_combustion_heat_release"),
        details.get("double_count_heat_release"),
    )
    if any(value is True for value in forbidden):
        raise CouplingError("sensible enthalpy exchange cannot replace or duplicate combustion heat release")
    return {
        "schema_version": "1.0",
        "time_s": float(time_s),
        "coordinate_system": "right_handed_cartesian",
        "grid_edges_m": {axis: edges[axis].tolist() for axis in "xyz"},
        "variables": {
            "mass_density": {"units": "kg/m3", "values": mass.tolist()},
            "momentum_density": {"units": "kg/(m2 s)", "component_order": ["x", "y", "z"], "values": momentum.tolist()},
            "sensible_enthalpy_density": {
                "units": "J/m3",
                "semantics": "advected_sensible_enthalpy_state",
                "values": enthalpy.tolist(),
            },
        },
        "source_term_policy": {
            "combustion_heat_release_replaced": False,
            "combustion_heat_release_included": False,
            "consumer_must_not_add_enthalpy_as_heat_release_rate": True,
        },
        "coupling_status": "one_way_exchange_only_unvalidated",
        "two_way_coupling_claimed": False,
        "metadata": details,
    }


def remap_exchange_bundle(bundle: Mapping, target_edges_m: Mapping[str, Sequence[float]]) -> dict:
    """Conservatively remap every exchange component onto one target grid."""
    variables = bundle.get("variables", {})
    source_edges = bundle.get("grid_edges_m", {})
    try:
        mass = np.asarray(variables["mass_density"]["values"], dtype=float)
        momentum = np.asarray(variables["momentum_density"]["values"], dtype=float)
        enthalpy = np.asarray(variables["sensible_enthalpy_density"]["values"], dtype=float)
    except (KeyError, TypeError) as exc:
        raise CouplingError("bundle does not satisfy the exchange variable contract") from exc
    mapped_mass = conservative_remap(mass, source_edges, target_edges_m)
    mapped_momentum = np.stack(
        [conservative_remap(momentum[..., component], source_edges, target_edges_m)["values"] for component in range(3)],
        axis=-1,
    )
    mapped_enthalpy = conservative_remap(enthalpy, source_edges, target_edges_m)
    result = build_exchange_bundle(
        time_s=float(bundle["time_s"]),
        grid_edges_m=target_edges_m,
        mass_density_kg_m3=mapped_mass["values"],
        momentum_density_kg_m2_s=mapped_momentum,
        sensible_enthalpy_density_J_m3=mapped_enthalpy["values"],
        metadata={"remapped_from": bundle.get("metadata", {}), "mapping": "exact_rectilinear_cell_volume_overlap"},
    )
    result["conservation"] = {
        "mass": {k: v for k, v in mapped_mass.items() if k != "values"},
        "sensible_enthalpy": {k: v for k, v in mapped_enthalpy.items() if k != "values"},
    }
    return result


__all__ = [
    "CouplingError",
    "convert_units",
    "transform_points",
    "interpolate_time",
    "conservative_remap",
    "build_exchange_bundle",
    "remap_exchange_bundle",
]
