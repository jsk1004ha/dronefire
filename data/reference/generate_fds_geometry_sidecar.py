"""Build an audited FDS probe geometry sidecar from source records only.

This utility performs no CFD execution, device control, flight, or flame work.
It refuses to infer a probe-to-DEVC mapping or a coordinate transform.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

SRC_DIR = Path(__file__).parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))
from adapter_contract import (  # noqa: E402
    _clean_fds_id,
    inspect_fds_input,
    inspect_fds_probe_geometry_sidecar,
    read_csv,
    write_csv,
)


SIDECAR_FIELDS = [
    "probe_id", "source_device_id", "support_type", "x_m", "y_m", "z_m",
    "x0_m", "y0_m", "z0_m", "x1_m", "y1_m", "z1_m", "source_geometry_tolerance_m",
    "source_fds_coordinate_frame", "coordinate_frame", "transform_id", "geometry_uncertainty_m",
    "source_fds_sha256", "survey_record_id", "notes",
]


def _index(rows: list[dict[str, str]], key: str, label: str) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        value = row.get(key, "")
        if not value or value in indexed:
            raise ValueError(f"{label}: {key} must be unique and non-empty ({value or '<blank>'})")
        indexed[value] = row
    return indexed


def _approval(value: str | None) -> bool:
    return (value or "").strip().casefold() in {"true", "yes", "approved", "1"}


def build_sidecar(
    fds_input_path: Path,
    probe_export_path: Path,
    mapping_ledger_path: Path,
    survey_geometry_path: Path,
    case_metadata_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Create and validate a sidecar; every output row has a source record."""
    input_report = inspect_fds_input(fds_input_path)
    if input_report["status"] != "ready":
        raise ValueError("FDS input is not parseable enough to establish a device catalogue")
    metadata = json.loads(case_metadata_path.read_text(encoding="utf-8"))
    case_frame = metadata.get("coordinate_frame")
    source_fds_frame = metadata.get("source_fds_coordinate_frame")
    transform_id = metadata.get("transform_id")
    if not case_frame or not source_fds_frame or not transform_id:
        raise ValueError("case metadata requires coordinate_frame, source_fds_coordinate_frame, and transform_id")
    if source_fds_frame != case_frame:
        raise ValueError("this example cannot apply a transform: source_fds_coordinate_frame must equal coordinate_frame")

    _, export_rows = read_csv(probe_export_path)
    probe_ids = {row.get("probe_id", "") for row in export_rows if row.get("probe_id", "")}
    if not probe_ids:
        raise ValueError("probe export has no non-empty probe_id")
    _, mapping_rows = read_csv(mapping_ledger_path)
    mappings = _index(mapping_rows, "probe_id", "mapping ledger")
    _, survey_rows = read_csv(survey_geometry_path)
    survey = _index(survey_rows, "source_device_id", "survey geometry")
    devices = {_clean_fds_id(device.get("id")): device for device in input_report["devices"]}

    missing_mapping = probe_ids - set(mappings)
    if missing_mapping:
        raise ValueError(f"mapping ledger is missing probe_id: {', '.join(sorted(missing_mapping))}")
    sidecar_rows: list[dict[str, str]] = []
    for probe_id in sorted(probe_ids):
        mapping = mappings[probe_id]
        if not _approval(mapping.get("mapping_approved")):
            raise ValueError(f"probe_id={probe_id}: mapping_approved must be true/approved")
        if not mapping.get("mapping_basis") or not mapping.get("mapping_record_id"):
            raise ValueError(f"probe_id={probe_id}: mapping_basis and mapping_record_id are required")
        device_id = _clean_fds_id(mapping.get("source_device_id"))
        device = devices.get(device_id)
        if not device:
            raise ValueError(f"probe_id={probe_id}: source_device_id={device_id or '<blank>'} is not in the FDS input")
        survey_row = survey.get(device_id)
        if not survey_row:
            raise ValueError(f"probe_id={probe_id}: no survey geometry record for source_device_id={device_id}")
        if survey_row.get("support_type") != device.get("support"):
            raise ValueError(f"probe_id={probe_id}: survey support_type does not match FDS support ({device.get('support')})")
        sidecar_rows.append({
            "probe_id": probe_id,
            "source_device_id": device_id,
            "support_type": survey_row.get("support_type", ""),
            "x_m": survey_row.get("x_m", ""), "y_m": survey_row.get("y_m", ""), "z_m": survey_row.get("z_m", ""),
            "x0_m": survey_row.get("x0_m", ""), "y0_m": survey_row.get("y0_m", ""), "z0_m": survey_row.get("z0_m", ""),
            "x1_m": survey_row.get("x1_m", ""), "y1_m": survey_row.get("y1_m", ""), "z1_m": survey_row.get("z1_m", ""),
            "source_geometry_tolerance_m": survey_row.get("source_geometry_tolerance_m", "0.000001"),
            "source_fds_coordinate_frame": source_fds_frame,
            "coordinate_frame": case_frame, "transform_id": transform_id,
            "geometry_uncertainty_m": survey_row.get("geometry_uncertainty_m", ""),
            "source_fds_sha256": input_report["sha256"],
            "survey_record_id": survey_row.get("survey_record_id", ""),
            "notes": f"mapping_basis={mapping['mapping_basis']}; mapping_record_id={mapping['mapping_record_id']}; {survey_row.get('notes', '')}".strip(),
        })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SIDECAR_FIELDS)
        writer.writeheader()
        writer.writerows(sidecar_rows)
    return inspect_fds_probe_geometry_sidecar(output_path, probe_ids, input_report, case_frame, transform_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a validated FDS probe geometry sidecar from source records.")
    parser.add_argument("--fds-input", required=True, type=Path)
    parser.add_argument("--probe-export", required=True, type=Path)
    parser.add_argument("--mapping-ledger", required=True, type=Path)
    parser.add_argument("--survey-geometry", required=True, type=Path)
    parser.add_argument("--case-metadata", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    report = build_sidecar(args.fds_input, args.probe_export, args.mapping_ledger, args.survey_geometry, args.case_metadata, args.output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "ready":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
