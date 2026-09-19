"""Read native FDS structured slice fields without inventing missing dimensions.

FDS ``.sf`` files are sequential-unformatted Fortran files.  The layout used
here is the one written by FDS ``DUMP_SLCF``: three 30-byte labels, six
inclusive grid indices, and then pairs of a scalar time record and a REAL*4
field record.  Coordinates and slice metadata come from the companion ``.smv``
file; the binary file itself contains indices, not physical coordinates.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import struct
from pathlib import Path
from typing import BinaryIO, Iterable

import numpy as np


class FieldFormatError(ValueError):
    """Raised when native field metadata or records are inconsistent."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _record(stream: BinaryIO, endian: str, *, allow_eof: bool = False) -> bytes | None:
    marker = stream.read(4)
    if not marker:
        if allow_eof:
            return None
        raise FieldFormatError("unexpected end of Fortran record stream")
    if len(marker) != 4:
        raise FieldFormatError("truncated Fortran record marker")
    length = struct.unpack(endian + "I", marker)[0]
    if length > 512 * 1024 * 1024:
        raise FieldFormatError(f"unreasonable Fortran record length: {length}")
    payload = stream.read(length)
    trailer = stream.read(4)
    if len(payload) != length or len(trailer) != 4:
        raise FieldFormatError("truncated Fortran record")
    if struct.unpack(endian + "I", trailer)[0] != length:
        raise FieldFormatError("Fortran record markers do not match")
    return payload


def _detect_endian(stream: BinaryIO) -> str:
    marker = stream.read(4)
    stream.seek(0)
    if len(marker) != 4:
        raise FieldFormatError("slice file is too short")
    if struct.unpack("<I", marker)[0] == 30:
        return "<"
    if struct.unpack(">I", marker)[0] == 30:
        return ">"
    raise FieldFormatError("unsupported FDS slice record marker (expected 30-byte label)")


def _numbers(line: str) -> list[float]:
    values: list[float] = []
    for token in line.replace(",", " ").split():
        try:
            values.append(float(token))
        except ValueError:
            continue
    return values


def parse_smv(path: str | os.PathLike[str]) -> dict:
    """Parse meshes, physical grid coordinates and structured slice entries."""
    smv = Path(path).resolve(strict=True)
    lines = smv.read_text(encoding="utf-8", errors="strict").splitlines()
    meshes: dict[int, dict] = {}
    slices: list[dict] = []
    current_mesh: int | None = None
    i = 0
    while i < len(lines):
        keyword = lines[i].strip().split(maxsplit=1)[0] if lines[i].strip() else ""
        if keyword == "GRID":
            current_mesh = len(meshes) + 1
            if i + 1 >= len(lines):
                raise FieldFormatError("GRID entry has no dimensions")
            dimensions = [int(value) for value in _numbers(lines[i + 1])[:3]]
            if len(dimensions) != 3 or any(value < 1 for value in dimensions):
                raise FieldFormatError("invalid GRID dimensions")
            meshes[current_mesh] = {
                "mesh_index": current_mesh,
                "name": lines[i].strip()[4:].strip() or f"mesh_{current_mesh}",
                "cell_counts": dimensions,
                "coordinates": {},
            }
            i += 2
            continue
        if keyword in {"TRNX", "TRNY", "TRNZ"}:
            if current_mesh is None:
                raise FieldFormatError(f"{keyword} appears before GRID")
            axis = {"TRNX": "x", "TRNY": "y", "TRNZ": "z"}[keyword]
            count = meshes[current_mesh]["cell_counts"]["xyz".index(axis)] + 1
            start = i + 2  # one transform-parameter line precedes indexed coordinates
            if start + count > len(lines):
                raise FieldFormatError(f"truncated {keyword} coordinates")
            coordinates = []
            for row in lines[start : start + count]:
                values = _numbers(row)
                if len(values) < 2:
                    raise FieldFormatError(f"invalid {keyword} coordinate row")
                coordinates.append(float(values[1]))
            if any(not math.isfinite(v) for v in coordinates) or any(
                b <= a for a, b in zip(coordinates, coordinates[1:])
            ):
                raise FieldFormatError(f"{keyword} coordinates must be finite and increasing")
            meshes[current_mesh]["coordinates"][axis] = coordinates
            i = start + count
            continue
        if keyword == "SLCF":
            header = lines[i].strip()
            header_prefix = header.split("#", 1)[0].split()
            if len(header_prefix) < 2:
                raise FieldFormatError("SLCF entry has no mesh index")
            mesh_index = int(header_prefix[1])
            match = re.search(r"&\s*(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)", header)
            if not match or i + 4 >= len(lines):
                raise FieldFormatError("incomplete structured SLCF entry")
            bounds = [int(value) for value in match.groups()]
            slices.append(
                {
                    "mesh_index": mesh_index,
                    "index_bounds": bounds,
                    "filename": lines[i + 1].strip(),
                    "quantity": lines[i + 2].strip(),
                    "short_name": lines[i + 3].strip(),
                    "units": lines[i + 4].strip(),
                    "structured": "STRUCTURED" in header,
                }
            )
            i += 5
            continue
        i += 1

    if not meshes:
        raise FieldFormatError("SMV file contains no GRID entries")
    for mesh in meshes.values():
        missing = {"x", "y", "z"} - set(mesh["coordinates"])
        if missing:
            raise FieldFormatError(f"mesh {mesh['mesh_index']} lacks coordinates: {sorted(missing)}")
    return {
        "schema_version": "1.0",
        "format": "FDS Smokeview metadata",
        "path": str(smv),
        "sha256": _sha256(smv),
        "coordinate_system": "right_handed_cartesian",
        "coordinate_units": "m",
        "meshes": list(meshes.values()),
        "slices": slices,
    }


def _slice_geometry(indices: list[int], mesh: dict) -> dict:
    i1, i2, j1, j2, k1, k2 = indices
    bounds = ((i1, i2), (j1, j2), (k1, k2))
    axes = {}
    for name, pair in zip("xyz", bounds):
        values = mesh["coordinates"][name]
        if pair[0] < 0 or pair[1] >= len(values) or pair[1] < pair[0]:
            raise FieldFormatError(f"slice {name} index bounds are outside mesh")
        axes[name] = values[pair[0] : pair[1] + 1]
    shape = [len(axes["z"]), len(axes["y"]), len(axes["x"])]
    varying = sum(size > 1 for size in shape)
    topology = {0: "point", 1: "line", 2: "plane", 3: "volume"}[varying]
    fixed_axes = [name for name in "xyz" if len(axes[name]) == 1]
    return {
        "topology": topology,
        "fixed_axes": fixed_axes,
        "sample_location": "FDS_structured_grid_index",
        "axes_m": axes,
        "shape_kji": shape,
        "flattening_order": "i-fastest, then j, then k",
    }


def read_fds_slice(
    sf_path: str | os.PathLike[str],
    smv_path: str | os.PathLike[str] | None = None,
    *,
    max_frames: int = 10_000,
    max_values: int = 50_000_000,
) -> dict:
    """Read one native FDS ``.sf`` file and attach exact SMV coordinates.

    ``smv_path`` is required for physical coordinates.  It may be omitted only
    to inspect binary labels/indices, in which case geometry is index-based.
    """
    sf = Path(sf_path).resolve(strict=True)
    if sf.suffix.lower() != ".sf":
        raise FieldFormatError("expected an uncompressed .sf slice file")
    metadata = parse_smv(smv_path) if smv_path is not None else None
    with sf.open("rb") as stream:
        endian = _detect_endian(stream)
        labels = []
        for _ in range(3):
            record = _record(stream, endian)
            if record is None or len(record) != 30:
                raise FieldFormatError("invalid FDS slice label record")
            labels.append(record.decode("ascii", errors="strict").rstrip())
        index_record = _record(stream, endian)
        if index_record is None or len(index_record) != 24:
            raise FieldFormatError("invalid FDS slice index record")
        indices = list(struct.unpack(endian + "6i", index_record))
        ni, nj, nk = indices[1] - indices[0] + 1, indices[3] - indices[2] + 1, indices[5] - indices[4] + 1
        value_count = ni * nj * nk
        if min(ni, nj, nk) < 1 or value_count > max_values:
            raise FieldFormatError("invalid or excessive FDS slice dimensions")
        frames: list[dict] = []
        while True:
            time_record = _record(stream, endian, allow_eof=True)
            if time_record is None:
                break
            if len(frames) >= max_frames:
                raise FieldFormatError("slice exceeds configured frame limit")
            if len(time_record) != 4:
                raise FieldFormatError("invalid FDS slice time record")
            time_s = struct.unpack(endian + "f", time_record)[0]
            values_record = _record(stream, endian)
            if values_record is None or len(values_record) != value_count * 4:
                raise FieldFormatError("slice field record size does not match index bounds")
            dtype = np.dtype(endian + "f4")
            values = np.frombuffer(values_record, dtype=dtype).astype(np.float64)
            if not math.isfinite(time_s) or not np.all(np.isfinite(values)):
                raise FieldFormatError("slice contains non-finite time or values")
            frames.append(
                {
                    "time_s": float(time_s),
                    "minimum": float(values.min()),
                    "maximum": float(values.max()),
                    "values": values.tolist(),
                }
            )

    if any(b["time_s"] <= a["time_s"] for a, b in zip(frames, frames[1:])):
        raise FieldFormatError("slice frame times are not strictly increasing")

    entry = None
    mesh = None
    if metadata is not None:
        matches = [item for item in metadata["slices"] if Path(item["filename"]).name == sf.name]
        if len(matches) != 1:
            raise FieldFormatError(f"SMV must reference slice exactly once: {sf.name}")
        entry = matches[0]
        if not entry["structured"]:
            raise FieldFormatError("only structured FDS slices are supported")
        if entry["index_bounds"] != indices:
            raise FieldFormatError("SMV and binary slice index bounds differ")
        mesh = next((item for item in metadata["meshes"] if item["mesh_index"] == entry["mesh_index"]), None)
        if mesh is None:
            raise FieldFormatError("slice references an unknown SMV mesh")
        if [entry["quantity"], entry["short_name"], entry["units"]] != labels:
            raise FieldFormatError("SMV and binary slice labels differ")
        geometry = _slice_geometry(indices, mesh)
    else:
        geometry = {
            "topology": "unknown_without_smv",
            "index_bounds": indices,
            "shape_kji": [nk, nj, ni],
            "flattening_order": "i-fastest, then j, then k",
        }

    return {
        "schema_version": "1.0",
        "format": "FDS sequential-unformatted structured slice",
        "quantity": labels[0],
        "short_name": labels[1],
        "units": labels[2],
        "index_bounds": indices,
        "geometry": geometry,
        "frames": frames,
        "frame_count": len(frames),
        "provenance": {
            "evidence_type": "native_simulation_output",
            "validation_status": "unvalidated",
            "source_path": str(sf),
            "source_sha256": _sha256(sf),
            "smv_path": metadata["path"] if metadata else None,
            "smv_sha256": metadata["sha256"] if metadata else None,
            "reader": "firelab.fields.read_fds_slice",
        },
    }


def export_fds_fields(
    run_dir: str | os.PathLike[str],
    output_path: str | os.PathLike[str] | None = None,
) -> dict:
    """Read all structured slices referenced by the sole SMV file in a run."""
    directory = Path(run_dir).resolve(strict=True)
    smv_files = sorted(directory.glob("*.smv"))
    if len(smv_files) != 1:
        raise FieldFormatError("run directory must contain exactly one .smv file")
    metadata = parse_smv(smv_files[0])
    fields = []
    for entry in metadata["slices"]:
        source = directory / Path(entry["filename"]).name
        if not source.is_file() or source.suffix.lower() != ".sf":
            continue
        fields.append(read_fds_slice(source, smv_files[0]))
    result = {
        "schema_version": "1.0",
        "kind": "native_fds_field_collection",
        "run_directory": str(directory),
        "coordinate_system": metadata["coordinate_system"],
        "coordinate_units": metadata["coordinate_units"],
        "fields": fields,
        "field_count": len(fields),
        "limitations": [
            "FDS slices retain their native point, line, plane, or volume topology.",
            "A plane slice is not evidence of a three-dimensional volume field.",
            "Native solver output is computational evidence and is not experimental validation.",
        ],
    }
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    return result


__all__: Iterable[str] = (
    "FieldFormatError",
    "parse_smv",
    "read_fds_slice",
    "export_fds_fields",
)
