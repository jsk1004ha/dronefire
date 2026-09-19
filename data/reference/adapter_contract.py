"""Offline, provenance-first Adapter Contract for FDS/OpenFOAM/sensor data.

This module validates whether data may be compared. It never turns missing
geometry, units, native artefacts, or time alignment into inferred facts.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


ERRORS = {
    "E001": "missing quantity or explicit unit",
    "E002": "missing coordinate frame, transform, or point geometry",
    "E003": "missing native time or declared alignment",
    "E004": "missing spatial support",
    "E005": "native mesh/provenance absent",
    "E006": "interpolation metadata absent",
    "E007": "critical channel clipped or missing",
    "E008": "semantic quantity mismatch",
}


FIELD_SPECS: dict[str, tuple[str, str, str]] = {
    "temperature_C": ("temperature", "degC", "temperature_K"),
    "temperature_K": ("temperature", "K", "temperature_K"),
    "T_K": ("temperature", "K", "temperature_K"),
    "pressure_Pa": ("pressure", "Pa", "pressure_Pa"),
    "p_Pa": ("pressure", "Pa", "pressure_Pa"),
    "vorticity_s_1": ("vorticity", "s^-1", "vorticity_s_1"),
    "oxygen_pct": ("oxygen_mole_fraction", "%", "oxygen_mole_fraction"),
    "co_ppm": ("carbon_monoxide", "ppm", "co_ppm"),
    "smoke_obscuration_1_m": ("smoke_obscuration", "1/m", "smoke_obscuration_1_m"),
    "particle_proxy": ("particle_proxy", "1", "particle_proxy"),
    "U_x": ("velocity_x", "m/s", "U_x_m_s"),
    "U_y": ("velocity_y", "m/s", "U_y_m_s"),
    "U_z": ("velocity_z", "m/s", "U_z_m_s"),
    "U_x_m_s": ("velocity_x", "m/s", "U_x_m_s"),
    "U_y_m_s": ("velocity_y", "m/s", "U_y_m_s"),
    "U_z_m_s": ("velocity_z", "m/s", "U_z_m_s"),
}

HEADER_ALIASES = {
    "time": "time_s", "Time": "time_s", "t": "time_s", "T": "temperature_K",
    "x": "x_m", "y": "y_m", "z": "z_m", "X": "x_m", "Y": "y_m", "Z": "z_m",
    "Points:0": "x_m", "Points:1": "y_m", "Points:2": "z_m",
    "U:0": "U_x_m_s", "U:1": "U_y_m_s", "U:2": "U_z_m_s",
    "Ux": "U_x_m_s", "Uy": "U_y_m_s", "Uz": "U_z_m_s",
    "omega": "vorticity_s_1", "pressure": "pressure_Pa",
}


@dataclass
class GateResult:
    stage: int
    name: str
    status: str  # ready|warning|blocked|not-comparable
    errors: list[str]
    detail: str


@dataclass
class ArtifactInspection:
    artifact_id: str
    source_kind: str
    path: str
    sha256: str
    byte_size: int
    columns: list[str]
    native_bundle_status: str
    diagnostics: list[str]


def _fds_parameter(text: str, name: str) -> str | None:
    match = re.search(
        rf"\b{name}\s*=\s*(.+?)(?=,\s*[A-Za-z_][A-Za-z0-9_]*\s*=|\s*/|$)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return match.group(1).strip() if match else None


def inspect_fds_input(path: Path) -> dict[str, Any]:
    """Extract native FDS input metadata without running or modifying the case."""
    text = path.read_text(encoding="utf-8", errors="replace")
    mesh_match = re.search(r"&MESH\b([^/]*)/", text, flags=re.IGNORECASE | re.DOTALL)
    mesh_block = mesh_match.group(1) if mesh_match else ""
    ijk_raw = _fds_parameter(mesh_block, "IJK")
    xb_raw = _fds_parameter(mesh_block, "XB")
    ijk = [int(value) for value in ijk_raw.split(",")] if ijk_raw and len(ijk_raw.split(",")) == 3 else []
    xb = [float(value) for value in xb_raw.split(",")] if xb_raw and len(xb_raw.split(",")) == 6 else []
    devc_blocks = re.findall(r"&DEVC\b([^/]*)/", text, flags=re.IGNORECASE | re.DOTALL)
    devices = []
    for block in devc_blocks:
        device_id = _fds_parameter(block, "ID")
        quantity = _fds_parameter(block, "QUANTITY")
        device_xb = _fds_parameter(block, "XB")
        devices.append({"id": device_id, "quantity": quantity, "xb": device_xb, "support": "line" if device_xb else "unknown"})
    dump_match = re.search(r"&DUMP\b([^/]*)/", text, flags=re.IGNORECASE | re.DOTALL)
    dump_block = dump_match.group(1) if dump_match else ""
    return {
        "path": str(path.resolve()), "sha256": sha256_file(path), "mesh": {"ijk": ijk, "xb_m": xb, "cell_count": ijk[0] * ijk[1] * ijk[2] if ijk else None},
        "time_end_s": as_float(_fds_parameter(text, "T_END")),
        "output_cadence": {"dt_devc_s": as_float(_fds_parameter(dump_block, "DT_DEVC")), "dt_hrr_s": as_float(_fds_parameter(dump_block, "DT_HRR"))},
        "device_count": len(devices), "devices": devices,
        "slice_count": len(re.findall(r"&SLCF\b", text, flags=re.IGNORECASE)),
        "status": "ready" if ijk and xb else "blocked",
        "errors": [] if ijk and xb else ["E005"],
    }


def inspect_fds_output(path: Path) -> dict[str, Any]:
    """Inspect an FDS .out-style text log when supplied; never infer a missing log."""
    path = path.expanduser().resolve()
    if not path.exists():
        return {"path": str(path), "exists": False, "status": "blocked", "errors": ["E005"], "missing": ["fds_output_log"]}
    text = path.read_text(encoding="utf-8", errors="replace")
    time_records = [
        float(value) for value in re.findall(
            r"\b(?:Scaled\s+Simulation\s+Time|Time)\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)",
            text,
            flags=re.IGNORECASE,
        )
    ]
    warnings = len(re.findall(r"\bWARNING\b", text, flags=re.IGNORECASE))
    errors = len(re.findall(r"\bERROR\b", text, flags=re.IGNORECASE))
    completed = bool(re.search(r"STOP:\s*FDS completed successfully", text, flags=re.IGNORECASE))
    return {
        "path": str(path), "exists": True, "sha256": sha256_file(path), "time_records": time_records,
        "max_diagnostic_time_s": max(time_records) if time_records else None,
        "completed_successfully_marker": completed, "warning_count": warnings, "error_count": errors,
        "status": "ready" if errors == 0 and completed else "warning",
        "errors": ["E007"] if errors or not completed else [],
    }


def inspect_fds_run_manifest(path: Path, expected_input_sha256: str | None = None) -> dict[str, Any]:
    """Read runner provenance; this validates only recorded metadata, not physics."""
    path = path.expanduser().resolve()
    if not path.exists():
        return {"path": str(path), "exists": False, "status": "blocked", "errors": ["E005"], "missing": ["run_manifest"]}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    case = manifest.get("case", {})
    source_hash = case.get("source_input_sha256")
    hash_match = expected_input_sha256 is None or source_hash == expected_input_sha256
    completed = manifest.get("status") == "completed" and manifest.get("returncode") == 0
    is_preflight = bool(manifest.get("preflight", {}).get("not_a_full_1800_s_run", False))
    return {
        "path": str(path), "exists": True, "sha256": sha256_file(path), "run_id": manifest.get("run_id"),
        "status": "ready" if completed and hash_match else "blocked", "errors": [] if completed and hash_match else ["E005"],
        "source_input_sha256": source_hash, "source_hash_matches_declared_input": hash_match,
        "time_end_s": as_float(str(case.get("time_end_s"))), "returncode": manifest.get("returncode"),
        "preflight_only": is_preflight,
    }


def _clean_fds_id(value: str | None) -> str:
    return (value or "").strip().strip("'\"")


def _fds_xb_endpoints(value: str | None) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    values = [as_float(part) for part in (value or "").split(",")]
    if len(values) != 6 or any(item is None for item in values):
        return None
    return ((values[0], values[2], values[4]), (values[1], values[3], values[5]))


def _points_match_unordered(
    first: tuple[float, float, float], second: tuple[float, float, float],
    expected_first: tuple[float, float, float], expected_second: tuple[float, float, float], tolerance_m: float,
) -> bool:
    distance = lambda left, right: max(abs(a - b) for a, b in zip(left, right))
    return (distance(first, expected_first) <= tolerance_m and distance(second, expected_second) <= tolerance_m) or (
        distance(first, expected_second) <= tolerance_m and distance(second, expected_first) <= tolerance_m
    )


def inspect_fds_probe_geometry_sidecar(
    path: Path,
    expected_probe_ids: set[str],
    fds_input_report: dict[str, Any],
    expected_frame: str | None,
    expected_transform: str | None,
) -> dict[str, Any]:
    """Validate a human-surveyed CSV crosswalk without inventing probe locations."""
    path = path.expanduser().resolve()
    required = {
        "probe_id", "source_device_id", "support_type", "x_m", "y_m", "z_m",
        "coordinate_frame", "transform_id", "geometry_uncertainty_m", "source_fds_sha256",
    }
    if not path.exists():
        return {"path": str(path), "exists": False, "status": "blocked", "errors": ["E002", "E004"], "missing": ["fds_probe_geometry_sidecar"]}
    headers, rows = read_csv(path)
    missing_columns = sorted(required - set(headers))
    source_devices = {_clean_fds_id(device.get("id")): device for device in fds_input_report.get("devices", [])}
    errors: list[str] = []
    reasons: list[str] = []
    geometry: dict[str, dict[str, Any]] = {}
    observed_ids = {row.get("probe_id", "") for row in rows if row.get("probe_id", "")}
    if missing_columns:
        errors.extend(["E002", "E004"])
        reasons.append(f"missing columns: {', '.join(missing_columns)}")
    if expected_probe_ids - observed_ids:
        errors.extend(["E002", "E004"])
        reasons.append(f"unmapped probe_id: {', '.join(sorted(expected_probe_ids - observed_ids))}")
    if len(observed_ids) != len(rows):
        errors.append("E002")
        reasons.append("duplicate or blank probe_id")
    for row in rows:
        probe_id = row.get("probe_id", "")
        source_device_id = _clean_fds_id(row.get("source_device_id"))
        coordinates = [as_float(row.get(axis)) for axis in ("x_m", "y_m", "z_m")]
        uncertainty = as_float(row.get("geometry_uncertainty_m"))
        source_device = source_devices.get(source_device_id, {})
        expected_support = source_device.get("support")
        reported_support = row.get("support_type")
        line_geometry_valid = True
        if expected_support == "line":
            sidecar_start = tuple(as_float(row.get(axis)) for axis in ("x0_m", "y0_m", "z0_m"))
            sidecar_end = tuple(as_float(row.get(axis)) for axis in ("x1_m", "y1_m", "z1_m"))
            source_endpoints = _fds_xb_endpoints(source_device.get("xb"))
            line_tolerance_m = as_float(row.get("source_geometry_tolerance_m")) or 1e-6
            line_geometry_valid = (
                row.get("source_fds_coordinate_frame") in (None, "", expected_frame)
                and all(value is not None for value in sidecar_start + sidecar_end)
                and source_endpoints is not None
                and _points_match_unordered(sidecar_start, sidecar_end, source_endpoints[0], source_endpoints[1], line_tolerance_m)
            )
        row_is_valid = (
            probe_id in expected_probe_ids and source_device_id in source_devices
            and (expected_support in (None, "unknown") or reported_support == expected_support)
            and all(value is not None for value in coordinates) and uncertainty is not None and uncertainty >= 0
            and row.get("coordinate_frame") == expected_frame and row.get("transform_id") == expected_transform
            and row.get("source_fds_sha256") == fds_input_report.get("sha256")
            and line_geometry_valid
        )
        if not row_is_valid:
            errors.extend(["E002", "E004"])
            reasons.append(f"invalid geometry record for probe_id={probe_id or '<blank>'}")
            continue
        geometry[probe_id] = {
            "x_m": coordinates[0], "y_m": coordinates[1], "z_m": coordinates[2],
            "support_type": reported_support, "source_device_id": source_device_id,
            "geometry_uncertainty_m": uncertainty,
        }
    errors = sorted(set(errors))
    return {
        "path": str(path), "exists": True, "sha256": sha256_file(path), "status": "ready" if not errors else "blocked",
        "errors": errors, "reasons": reasons, "expected_probe_ids": sorted(expected_probe_ids),
        "source_device_ids": sorted(source_devices), "probe_geometry": geometry,
    }


def inspect_coordinate_transform_registry(path: Path, expected_frame: str | None, expected_transform: str | None) -> dict[str, Any]:
    """Validate survey control-point evidence for a declared, versioned transform."""
    path = path.expanduser().resolve()
    required = {
        "control_point_id", "source_frame", "target_frame", "transform_id", "x_source_m", "y_source_m", "z_source_m",
        "x_target_m", "y_target_m", "z_target_m", "residual_m", "source_record_id",
    }
    if not path.exists():
        return {"path": str(path), "exists": False, "status": "blocked", "errors": ["E002"], "missing": ["coordinate_transform_registry"]}
    headers, rows = read_csv(path)
    reasons: list[str] = []
    errors: list[str] = []
    if missing_columns := sorted(required - set(headers)):
        errors.append("E002")
        reasons.append(f"missing columns: {', '.join(missing_columns)}")
    control_ids = [row.get("control_point_id", "") for row in rows]
    if len(set(control_ids)) < 6 or len(set(control_ids)) != len(control_ids):
        errors.append("E002")
        reasons.append("at least six unique control points are required")
    for row in rows:
        coordinates = [as_float(row.get(name)) for name in ("x_source_m", "y_source_m", "z_source_m", "x_target_m", "y_target_m", "z_target_m")]
        valid = (
            row.get("source_frame") and row.get("target_frame") == expected_frame and row.get("transform_id") == expected_transform
            and row.get("source_record_id") and all(value is not None for value in coordinates)
            and (as_float(row.get("residual_m")) is not None and as_float(row.get("residual_m")) >= 0)
        )
        if not valid:
            errors.append("E002")
            reasons.append(f"invalid transform record for control_point_id={row.get('control_point_id') or '<blank>'}")
    errors = sorted(set(errors))
    return {
        "path": str(path), "exists": True, "sha256": sha256_file(path), "status": "ready" if not errors else "blocked",
        "errors": errors, "reasons": reasons, "control_point_count": len(set(control_ids)),
    }


def inspect_time_alignment_ledger(path: Path, expected_clock_ids: set[str]) -> dict[str, Any]:
    """Validate explicit time-base transformations; no offset/drift values are inferred."""
    path = path.expanduser().resolve()
    required = {
        "clock_id", "native_time_basis", "analysis_time_basis", "reference_event_id", "offset_s",
        "drift_s_per_s", "fit_residual_s", "method", "source_file_sha256",
    }
    if not path.exists():
        return {"path": str(path), "exists": False, "status": "blocked", "errors": ["E003"], "missing": ["time_alignment_ledger"]}
    headers, rows = read_csv(path)
    reasons: list[str] = []
    errors: list[str] = []
    if missing_columns := sorted(required - set(headers)):
        errors.append("E003")
        reasons.append(f"missing columns: {', '.join(missing_columns)}")
    observed_clock_ids = {row.get("clock_id", "") for row in rows if row.get("clock_id", "")}
    if expected_clock_ids - observed_clock_ids:
        errors.append("E003")
        reasons.append(f"unmapped clock_id: {', '.join(sorted(expected_clock_ids - observed_clock_ids))}")
    for row in rows:
        finite_values = [as_float(row.get(name)) for name in ("offset_s", "drift_s_per_s", "fit_residual_s")]
        valid = all(row.get(name) for name in ("clock_id", "native_time_basis", "analysis_time_basis", "reference_event_id", "method", "source_file_sha256")) and all(value is not None for value in finite_values)
        if not valid:
            errors.append("E003")
            reasons.append(f"invalid time ledger record for clock_id={row.get('clock_id') or '<blank>'}")
    errors = sorted(set(errors))
    return {
        "path": str(path), "exists": True, "sha256": sha256_file(path), "status": "ready" if not errors else "blocked",
        "errors": errors, "reasons": reasons, "expected_clock_ids": sorted(expected_clock_ids),
        "observed_clock_ids": sorted(observed_clock_ids),
    }


def inspect_openfoam_case(case_dir: Path) -> dict[str, Any]:
    """Inspect a native OpenFOAM directory; no solver execution occurs."""
    case_dir = case_dir.resolve()
    poly_mesh = case_dir / "constant" / "polyMesh"
    control_dict = case_dir / "system" / "controlDict"
    sample_dict = case_dir / "system" / "sampleDict"
    time_dirs = sorted([path for path in case_dir.iterdir() if path.is_dir() and re.fullmatch(r"\d+(?:\.\d+)?", path.name)]) if case_dir.exists() else []
    fields = sorted({field.name for time_dir in time_dirs for field in time_dir.iterdir() if field.is_file() and field.name in {"U", "p", "T"}})
    logs = sorted(path.name for path in case_dir.glob("log.*")) if case_dir.exists() else []
    required = {"polyMesh": poly_mesh.is_dir(), "controlDict": control_dict.is_file(), "sampleDict": sample_dict.is_file(), "fields": bool(fields), "solver_log": bool(logs)}
    missing = [name for name, present in required.items() if not present]
    return {
        "path": str(case_dir), "exists": case_dir.exists(), "required": required, "time_directories": [path.name for path in time_dirs],
        "fields": fields, "solver_logs": logs, "status": "ready" if not missing else "blocked",
        "errors": [] if not missing else ["E005", "E006"], "missing": missing,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"{path}: CSV header is missing")
        headers = [header.strip() for header in reader.fieldnames]
        rows = [
            {(key.strip() if key else ""): (value.strip() if isinstance(value, str) else value) for key, value in row.items()}
            for row in reader
        ]
        return headers, rows


def as_float(value: str | None) -> float | None:
    try:
        parsed = float(value) if value not in (None, "") else None
        return parsed if parsed is not None and math.isfinite(parsed) else None
    except ValueError:
        return None


def canonical_header(header: str) -> str:
    return HEADER_ALIASES.get(header, header)


def convert_value(canonical_field: str, value: float) -> tuple[float, str, str]:
    quantity, source_unit, target_field = FIELD_SPECS[canonical_field]
    if canonical_field == "temperature_C":
        return value + 273.15, "K", "K = degC + 273.15"
    if canonical_field == "oxygen_pct":
        return value / 100.0, "mole_fraction", "mole_fraction = pct / 100"
    return value, source_unit, "identity"


def inspect_artifact(spec: dict[str, Any]) -> ArtifactInspection:
    path = Path(spec["path"]).expanduser().resolve()
    columns, _ = read_csv(path)
    source_kind = spec["source_kind"]
    native_required = bool(spec.get("native_bundle_required", False))
    native_bundle = spec.get("native_bundle", {})
    native_ok = all(native_bundle.get(key) for key in spec.get("native_required_keys", []))
    status = "ready" if not native_required or native_ok else "missing"
    diagnostics = []
    if not native_ok and native_required:
        diagnostics.append("native bundle metadata is incomplete")
    if not any(canonical_header(column) == "time_s" for column in columns):
        diagnostics.append("time column is absent")
    return ArtifactInspection(
        artifact_id=spec["artifact_id"], source_kind=source_kind, path=str(path),
        sha256=sha256_file(path), byte_size=path.stat().st_size, columns=columns,
        native_bundle_status=status, diagnostics=diagnostics,
    )


def _geometry_for(row: dict[str, str], spec: dict[str, Any]) -> tuple[float | None, float | None, float | None, str | None]:
    x, y, z = as_float(row.get("x_m")), as_float(row.get("y_m")), as_float(row.get("z_m"))
    if None not in (x, y, z):
        return x, y, z, "point"
    probe_id = row.get("probe_id")
    geometry = spec.get("probe_geometry", {}).get(probe_id or "")
    if geometry and all(key in geometry for key in ("x_m", "y_m", "z_m")):
        return float(geometry["x_m"]), float(geometry["y_m"]), float(geometry["z_m"]), geometry.get("support_type", "point")
    return None, None, None, None


def canonicalize(spec: dict[str, Any], inspection: ArtifactInspection, case: dict[str, Any]) -> list[dict[str, Any]]:
    headers, raw_rows = read_csv(Path(spec["path"]))
    normalized_rows: list[dict[str, Any]] = []
    explicit_header_map = spec.get("header_map", {})
    declared_units = spec.get("declared_units", {})
    mapping = {header: explicit_header_map.get(header, canonical_header(header)) for header in headers}
    for row_index, raw in enumerate(raw_rows):
        row = {mapping[key]: value for key, value in raw.items()}
        time_s = as_float(row.get("time_s"))
        x, y, z, support_type = _geometry_for(row, spec)
        for original_column, raw_value in raw.items():
            column = mapping[original_column]
            if column not in FIELD_SPECS:
                continue
            value = as_float(raw_value)
            if value is None:
                continue
            converted, target_unit, formula = convert_value(column, value)
            quality = "valid"
            expected_source_unit = FIELD_SPECS[column][1]
            explicit_unit = declared_units.get(original_column)
            if spec.get("require_declared_units", False) and not explicit_unit:
                quality = "unit-fail"
            elif explicit_unit and explicit_unit != expected_source_unit:
                quality = "unit-fail"
            if time_s is None:
                quality = "sync-fail"
            if support_type is None:
                quality = "support-fail"
            normalized_rows.append({
                "project_id": case["project_id"], "case_id": case["case_id"], "run_id": case["run_id"],
                "artifact_id": inspection.artifact_id, "source_file_sha256": inspection.sha256,
                "sample_id": f"{inspection.artifact_id}:{row_index}:{row.get('probe_id', 'row')}",
                "quantity": FIELD_SPECS[column][0], "field_id": FIELD_SPECS[column][2],
                "raw_column": original_column, "scalar_value": converted, "unit": target_unit,
                "unit_conversion": formula, "native_time_s": time_s, "analysis_time_s": time_s,
                "time_basis": case.get("time_basis"), "coordinate_frame": case.get("coordinate_frame"),
                "transform_id": case.get("transform_id"), "x_m": x, "y_m": y, "z_m": z,
                "support_type": support_type, "support_id": row.get("probe_id") if support_type else None,
                "processing_status": "raw", "quality_flag": quality,
                "solver_name": case.get("solver_name"), "solver_version": case.get("solver_version"),
                "mesh_id": case.get("mesh_id"), "native_bundle_status": inspection.native_bundle_status,
            })
    return normalized_rows


def gate_results(left: ArtifactInspection, right: ArtifactInspection, left_rows: list[dict[str, Any]], right_rows: list[dict[str, Any]], tolerance_s: float) -> list[GateResult]:
    lineage = GateResult(1, "lineage & integrity", "ready", [], f"{left.sha256[:12]}… ↔ {right.sha256[:12]}…")
    unit_fail = sum(row.get("quality_flag") == "unit-fail" for row in left_rows + right_rows)
    schema = GateResult(2, "schema & unit", "ready" if left_rows and right_rows and not unit_fail else "blocked", ["E001"] if unit_fail or not left_rows or not right_rows else [], f"canonical rows: {len(left_rows)} / {len(right_rows)}")
    coordinate_ready = all(row["support_type"] and row["coordinate_frame"] and row["transform_id"] for row in left_rows + right_rows)
    coordinate = GateResult(3, "coordinate & spatial support", "ready" if coordinate_ready else "blocked", [] if coordinate_ready else ["E002", "E004"], "all rows require declared frame, transform, and support")
    left_times = sorted({row["analysis_time_s"] for row in left_rows if row["analysis_time_s"] is not None})
    right_times = sorted({row["analysis_time_s"] for row in right_rows if row["analysis_time_s"] is not None})
    paired_fraction = 0.0 if not left_times else sum(min(abs(time - other) for other in right_times) <= tolerance_s for time in left_times) / len(left_times) if right_times else 0.0
    time_status = "ready" if paired_fraction == 1 else "warning" if paired_fraction > 0 else "blocked"
    time = GateResult(4, "time support", time_status, [] if paired_fraction else ["E003"], f"{paired_fraction:.0%} of left export times pair within ±{tolerance_s}s")
    common = sorted(set(row["field_id"] for row in left_rows) & set(row["field_id"] for row in right_rows))
    comparable = coordinate.status == "ready" and time.status == "ready" and bool(common)
    qoi = GateResult(5, "QoI pairing", "ready" if comparable else "blocked", [] if comparable else ["E008"], f"common canonical fields: {', '.join(common) or 'none'}")
    return [lineage, schema, coordinate, time, qoi]


def build_pairs(left_rows: list[dict[str, Any]], right_rows: list[dict[str, Any]], gates: Iterable[GateResult], tolerance_s: float) -> list[dict[str, Any]]:
    if any(gate.status != "ready" for gate in gates):
        return [{"pair_id": "PAIR-HELD", "comparable_flag": False, "noncomparable_reason": "one or more Adapter Contract gates are not ready"}]
    pairs: list[dict[str, Any]] = []
    right_by_field = defaultdict(list)
    for row in right_rows:
        right_by_field[row["field_id"]].append(row)
    for row in left_rows:
        candidates = right_by_field[row["field_id"]]
        if not candidates:
            continue
        candidate = min(candidates, key=lambda item: abs(item["analysis_time_s"] - row["analysis_time_s"]))
        if abs(candidate["analysis_time_s"] - row["analysis_time_s"]) <= tolerance_s:
            pairs.append({"pair_id": f"PAIR-{len(pairs)+1:04d}", "field_id": row["field_id"], "left_sample_id": row["sample_id"], "right_sample_id": candidate["sample_id"], "time_difference_s": abs(candidate["analysis_time_s"] - row["analysis_time_s"]), "comparable_flag": True, "noncomparable_reason": ""})
    return pairs or [{"pair_id": "PAIR-HELD", "comparable_flag": False, "noncomparable_reason": "no matching pair after field/time rules"}]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row}) if rows else ["empty"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(config_path: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    output_dir = Path(config["output_dir"]).expanduser().resolve()
    case = config["case"]
    left_spec, right_spec = (dict(spec) for spec in config["artifacts"])
    left_spec["native_bundle"] = dict(left_spec.get("native_bundle", {}))
    native_checks = config.get("native_artifact_checks", {})
    native_report: dict[str, Any] = {}
    fds_input_report: dict[str, Any] | None = None
    if native_checks.get("fds_input_path"):
        fds_input_report = inspect_fds_input(Path(native_checks["fds_input_path"]))
        native_report["fds_input"] = fds_input_report
    if native_checks.get("fds_probe_geometry_sidecar_path"):
        _, left_raw_rows = read_csv(Path(left_spec["path"]))
        expected_ids = {row.get("probe_id", "") for row in left_raw_rows if row.get("probe_id", "")}
        geometry_report = inspect_fds_probe_geometry_sidecar(
            Path(native_checks["fds_probe_geometry_sidecar_path"]), expected_ids, fds_input_report or {},
            case.get("coordinate_frame"), case.get("transform_id"),
        )
        native_report["fds_probe_geometry"] = geometry_report
        if geometry_report["status"] == "ready":
            left_spec["probe_geometry"] = geometry_report["probe_geometry"]
            left_spec["native_bundle"]["device_geometry_sidecar"] = True
    if native_checks.get("coordinate_transform_registry_path"):
        native_report["coordinate_transform"] = inspect_coordinate_transform_registry(
            Path(native_checks["coordinate_transform_registry_path"]), case.get("coordinate_frame"), case.get("transform_id"),
        )
    if native_checks.get("time_alignment_ledger_path"):
        native_report["time_alignment"] = inspect_time_alignment_ledger(
            Path(native_checks["time_alignment_ledger_path"]), set(native_checks.get("expected_clock_ids", [])),
        )
    left_inspection, right_inspection = inspect_artifact(left_spec), inspect_artifact(right_spec)
    left_rows = canonicalize(left_spec, left_inspection, {**case, "solver_name": left_spec.get("solver_name"), "solver_version": left_spec.get("solver_version"), "mesh_id": left_spec.get("mesh_id")})
    right_rows = canonicalize(right_spec, right_inspection, {**case, "solver_name": right_spec.get("solver_name"), "solver_version": right_spec.get("solver_version"), "mesh_id": right_spec.get("mesh_id")})
    gates = gate_results(left_inspection, right_inspection, left_rows, right_rows, config["time_alignment"]["tolerance_s"])
    if native_report.get("coordinate_transform", {}).get("status") == "blocked":
        gates[2] = GateResult(3, "coordinate & spatial support", "blocked", ["E002", "E004"], "transform registry is incomplete; no spatial pairing")
    if native_report.get("time_alignment", {}).get("status") == "blocked":
        gates[3] = GateResult(4, "time support", "blocked", ["E003"], "time alignment ledger is incomplete; no temporal pairing")
    common_fields = sorted(set(row["field_id"] for row in left_rows) & set(row["field_id"] for row in right_rows))
    if gates[2].status != "ready" or gates[3].status != "ready" or not common_fields:
        gates[4] = GateResult(5, "QoI pairing", "blocked", ["E008"], f"common canonical fields: {', '.join(common_fields) or 'none'}")
    pairs = build_pairs(left_rows, right_rows, gates, config["time_alignment"]["tolerance_s"])
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "canonical_left.csv", left_rows)
    write_csv(output_dir / "canonical_right.csv", right_rows)
    write_csv(output_dir / "pairing_registry.csv", pairs)
    (output_dir / "artifact_inventory.json").write_text(json.dumps([asdict(left_inspection), asdict(right_inspection)], ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "gate_report.json").write_text(json.dumps([asdict(gate) for gate in gates], ensure_ascii=False, indent=2), encoding="utf-8")
    if native_checks.get("fds_output_path"):
        output_report = inspect_fds_output(Path(native_checks["fds_output_path"]))
        required_time_s = as_float(str(native_checks.get("fds_output_required_time_s", "")))
        if required_time_s is not None and (output_report.get("max_diagnostic_time_s") is None or output_report["max_diagnostic_time_s"] < required_time_s):
            output_report["status"] = "blocked"
            output_report["errors"] = sorted(set(output_report.get("errors", []) + ["E003"]))
            output_report["time_coverage_requirement_s"] = required_time_s
            output_report["time_coverage_satisfied"] = False
        native_report["fds_output"] = output_report
    if native_checks.get("fds_run_manifest_path"):
        native_report["fds_run_manifest"] = inspect_fds_run_manifest(
            Path(native_checks["fds_run_manifest_path"]), (fds_input_report or {}).get("sha256"),
        )
    if native_checks.get("openfoam_case_path"):
        native_report["openfoam_case"] = inspect_openfoam_case(Path(native_checks["openfoam_case_path"]))
    if native_report:
        (output_dir / "native_artifact_report.json").write_text(json.dumps(native_report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"output_dir": str(output_dir), "gates": [asdict(gate) for gate in gates], "pairs": pairs, "native_artifact_report": native_report}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the five-stage FDS/OpenFOAM Adapter Contract.")
    parser.add_argument("--config", required=True, type=Path, help="JSON configuration file")
    args = parser.parse_args()
    result = run(args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
