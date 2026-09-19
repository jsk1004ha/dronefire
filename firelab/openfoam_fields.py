"""Export the verified structured Taylor-Green OpenFOAM fields for the web UI.

This is deliberately not a generic OpenFOAM mesh reader.  It accepts ASCII
``polyMesh`` cases only and proves that every polyhedral cell is an axis-aligned
hexahedron occupying exactly one cell of a complete rectilinear Cartesian grid.
Unsupported or binary meshes fail closed.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np


class OpenFOAMFieldError(ValueError):
    """Raised when an OpenFOAM file or mesh cannot be proven compatible."""


_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="strict")
    header = re.search(r"\bformat\s+(\w+)\s*;", raw)
    if not header or header.group(1) != "ascii":
        raise OpenFOAMFieldError(f"only explicit ASCII OpenFOAM files are supported: {path}")
    raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)
    raw = re.sub(r"//.*", "", raw)
    return raw


def _header(text: str, key: str) -> str:
    match = re.search(rf"\b{re.escape(key)}\s+([^;]+);", text)
    if not match:
        raise OpenFOAMFieldError(f"missing OpenFOAM header key: {key}")
    return match.group(1).strip().strip('"')


def _outer_list(text: str, *, anchor: str | None = None) -> tuple[int, str]:
    start = text.find("}") + 1
    if anchor is None:
        match = re.search(r"(?m)^\s*(\d+)\s*\n\s*\(", text[start:])
    else:
        match = re.search(anchor + r"\s*(\d+)\s*\(", text[start:])
    if not match:
        raise OpenFOAMFieldError("OpenFOAM list declaration was not found")
    offset = start + match.end() - 1
    depth = 0
    close = None
    for index in range(offset, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                close = index
                break
    if close is None:
        raise OpenFOAMFieldError("OpenFOAM list is not closed")
    return int(match.group(1)), text[offset + 1 : close]


def _vectors(path: Path, *, expected_class: str, internal: bool = False) -> np.ndarray:
    text = _text(path)
    if _header(text, "class") != expected_class:
        raise OpenFOAMFieldError(f"unexpected field class in {path}")
    if internal:
        count, body = _outer_list(
            text,
            anchor=r"\binternalField\s+nonuniform\s+List<vector>",
        )
    else:
        count, body = _outer_list(text)
    matches = re.findall(rf"\(\s*({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s*\)", body)
    if len(matches) != count:
        raise OpenFOAMFieldError(f"declared vector count {count} differs from parsed count {len(matches)}")
    values = np.asarray(matches, dtype=float)
    if values.shape != (count, 3) or not np.all(np.isfinite(values)):
        raise OpenFOAMFieldError("OpenFOAM vectors are non-finite or malformed")
    return values


def _faces(path: Path) -> list[tuple[int, ...]]:
    text = _text(path)
    if _header(text, "class") != "faceList":
        raise OpenFOAMFieldError("polyMesh faces must use faceList")
    count, body = _outer_list(text)
    result = []
    for declared, values in re.findall(r"(\d+)\s*\(([^()]*)\)", body):
        vertices = tuple(int(value) for value in values.split())
        if len(vertices) != int(declared) or len(vertices) < 3:
            raise OpenFOAMFieldError("face vertex count is inconsistent")
        result.append(vertices)
    if len(result) != count:
        raise OpenFOAMFieldError(f"declared face count {count} differs from parsed count {len(result)}")
    return result


def _labels(path: Path) -> np.ndarray:
    text = _text(path)
    if _header(text, "class") != "labelList":
        raise OpenFOAMFieldError("owner/neighbour must use labelList")
    count, body = _outer_list(text)
    tokens = body.split()
    if len(tokens) != count or any(not re.fullmatch(r"\d+", token) for token in tokens):
        raise OpenFOAMFieldError("label list count or syntax is invalid")
    return np.asarray(tokens, dtype=np.int64)


def _structured_mesh(case: Path) -> dict:
    mesh = case / "constant" / "polyMesh"
    points_path = mesh / "points"
    faces_path = mesh / "faces"
    owner_path = mesh / "owner"
    neighbour_path = mesh / "neighbour"
    for source in (points_path, faces_path, owner_path, neighbour_path):
        if not source.is_file():
            raise OpenFOAMFieldError(f"missing polyMesh source: {source}")
    points = _vectors(points_path, expected_class="vectorField")
    faces = _faces(faces_path)
    owner = _labels(owner_path)
    neighbour = _labels(neighbour_path)
    if len(owner) != len(faces) or len(neighbour) > len(faces):
        raise OpenFOAMFieldError("face ownership counts are inconsistent")
    if np.any(owner < 0) or np.any(neighbour < 0):
        raise OpenFOAMFieldError("negative cell labels are unsupported")
    cell_count = int(max(owner.max(initial=-1), neighbour.max(initial=-1)) + 1)
    cell_vertices = [set() for _ in range(cell_count)]
    for face_index, vertices in enumerate(faces):
        if any(vertex < 0 or vertex >= len(points) for vertex in vertices):
            raise OpenFOAMFieldError("face references a point outside the point list")
        cell_vertices[int(owner[face_index])].update(vertices)
        if face_index < len(neighbour):
            cell_vertices[int(neighbour[face_index])].update(vertices)

    axes_nodes = [np.unique(points[:, axis]) for axis in range(3)]
    if math.prod(len(axis) for axis in axes_nodes) != len(points):
        raise OpenFOAMFieldError("mesh points do not form a complete rectilinear Cartesian product")
    point_tuples = {tuple(row) for row in points.tolist()}
    expected_points = {(x, y, z) for x in axes_nodes[0] for y in axes_nodes[1] for z in axes_nodes[2]}
    if point_tuples != expected_points:
        raise OpenFOAMFieldError("mesh point Cartesian product contains gaps or duplicates")
    expected_cells = math.prod(len(axis) - 1 for axis in axes_nodes)
    if cell_count != expected_cells:
        raise OpenFOAMFieldError(f"cell count {cell_count} does not match rectilinear grid {expected_cells}")

    node_index = [{float(value): index for index, value in enumerate(axis)} for axis in axes_nodes]
    nx, ny, nz = (len(axis) - 1 for axis in axes_nodes)
    slots = np.full(cell_count, -1, dtype=np.int64)
    occupied: set[int] = set()
    for cell, vertices in enumerate(cell_vertices):
        if len(vertices) != 8:
            raise OpenFOAMFieldError("every supported cell must be an eight-vertex hexahedron")
        cell_points = points[sorted(vertices)]
        coordinate_sets = [np.unique(cell_points[:, axis]) for axis in range(3)]
        if any(len(values) != 2 for values in coordinate_sets):
            raise OpenFOAMFieldError("cell is not an axis-aligned rectilinear hexahedron")
        lower = [node_index[axis][float(values[0])] for axis, values in enumerate(coordinate_sets)]
        upper = [node_index[axis][float(values[1])] for axis, values in enumerate(coordinate_sets)]
        if any(hi != lo + 1 for lo, hi in zip(lower, upper)):
            raise OpenFOAMFieldError("cell skips a coordinate interval")
        i, j, k = lower
        slot = k * ny * nx + j * nx + i
        if slot in occupied:
            raise OpenFOAMFieldError("multiple cells occupy one structured-grid slot")
        occupied.add(slot)
        slots[cell] = slot
    if occupied != set(range(cell_count)):
        raise OpenFOAMFieldError("structured-grid cell coverage is incomplete")

    centers = [0.5 * (axis[:-1] + axis[1:]) for axis in axes_nodes]
    return {
        "points": points,
        "cell_count": cell_count,
        "shape_kji": [nz, ny, nx],
        "axes_m": {name: values.tolist() for name, values in zip("xyz", centers)},
        "cell_to_flat_slot": slots,
        "source_files": {
            path.name: {"path": str(path.resolve()), "sha256": _sha256(path)}
            for path in (points_path, faces_path, owner_path, neighbour_path)
        },
    }


def read_openfoam_taylor_green(case_dir: str | os.PathLike[str]) -> dict:
    """Read actual U fields from a proven structured Taylor-Green native case."""
    case = Path(case_dir).resolve(strict=True)
    manifest_path = case / "run_manifest.json"
    if not manifest_path.is_file():
        raise OpenFOAMFieldError("native case has no run_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("solver") != "OpenFOAM icoFoam" or manifest.get("status") != "completed":
        raise OpenFOAMFieldError("case is not a completed Taylor-Green icoFoam run")
    configuration_paths = [
        case / "system" / name
        for name in ("blockMeshDict", "controlDict", "fvSchemes", "fvSolution")
    ] + [case / "constant" / "transportProperties"]
    if any(not path.is_file() for path in configuration_paths):
        raise OpenFOAMFieldError("native case is missing required mesh/solver configuration")
    configuration_sources = {
        path.relative_to(case).as_posix(): {
            "path": str(path.resolve()),
            "sha256": _sha256(path),
        }
        for path in configuration_paths
    }
    mesh = _structured_mesh(case)
    frames = []
    field_sources = []
    for directory in sorted(
        (path for path in case.iterdir() if path.is_dir() and re.fullmatch(_NUMBER, path.name)),
        key=lambda path: float(path.name),
    ):
        field_path = directory / "U"
        if not field_path.is_file():
            continue
        text = _text(field_path)
        if _header(text, "object") != "U":
            raise OpenFOAMFieldError(f"velocity field object is not U: {field_path}")
        dimensions = re.search(r"\bdimensions\s+\[([^]]+)\]\s*;", text)
        if not dimensions or [int(value) for value in dimensions.group(1).split()] != [0, 1, -1, 0, 0, 0, 0]:
            raise OpenFOAMFieldError("U does not declare velocity dimensions")
        vectors = _vectors(field_path, expected_class="volVectorField", internal=True)
        if len(vectors) != mesh["cell_count"]:
            raise OpenFOAMFieldError("U internal field count differs from proven cell count")
        magnitude_by_cell = np.linalg.norm(vectors, axis=1)
        values = np.empty(mesh["cell_count"])
        values[mesh["cell_to_flat_slot"]] = magnitude_by_cell
        source = {"time_s": float(directory.name), "source_path": str(field_path.resolve()), "source_sha256": _sha256(field_path)}
        field_sources.append(source)
        frames.append(
            {
                "time_s": source["time_s"],
                "minimum": float(values.min()),
                "maximum": float(values.max()),
                "values": values.tolist(),
                "provenance": source,
            }
        )
    if not frames:
        raise OpenFOAMFieldError("case contains no readable U time directories")
    if any(b["time_s"] <= a["time_s"] for a, b in zip(frames, frames[1:])):
        raise OpenFOAMFieldError("U time directories are not strictly increasing")
    latest_source = field_sources[-1]
    topology = "volume" if all(size > 1 for size in mesh["shape_kji"]) else "plane"
    fixed_axes = [axis for axis, size in zip("zyx", mesh["shape_kji"]) if size == 1]
    field = {
        "schema_version": "1.0",
        "format": "OpenFOAM ASCII volVectorField magnitude on proven rectilinear polyMesh",
        "quantity": "VELOCITY MAGNITUDE",
        "short_name": "mag(U)",
        "units": "m/s",
        "geometry": {
            "topology": topology,
            "fixed_axes": fixed_axes,
            "sample_location": "OpenFOAM_cell_center",
            "axes_m": mesh["axes_m"],
            "shape_kji": mesh["shape_kji"],
            "flattening_order": "i-fastest, then j, then k",
            "structured_geometry_proof": {
                "cell_count": mesh["cell_count"],
                "all_cells_axis_aligned_hexahedra": True,
                "complete_cartesian_cell_coverage": True,
                "mesh_sources": mesh["source_files"],
            },
        },
        "frames": frames,
        "frame_count": len(frames),
        "provenance": {
            "evidence_type": "native_simulation_output",
            "validation_status": manifest.get("validation_status", "unvalidated"),
            "source_path": latest_source["source_path"],
            "source_sha256": latest_source["source_sha256"],
            "all_field_sources": field_sources,
            "run_manifest_path": str(manifest_path.resolve()),
            "run_manifest_sha256": _sha256(manifest_path),
            "source_case_hash": manifest.get("source_case_hash"),
            "case_configuration_sources": configuration_sources,
            "reader": "firelab.openfoam_fields.read_openfoam_taylor_green",
        },
    }
    return {
        "schema_version": "1.0",
        "kind": "native_openfoam_field_collection",
        "run_directory": str(case),
        "run_status": manifest["status"],
        "solver": manifest["solver"],
        "coordinate_system": "right_handed_cartesian",
        "coordinate_units": "m",
        "resolution": manifest.get("metrics", {}).get("resolution"),
        "fields": [field],
        "field_count": 1,
        "limitations": [
            "Only velocity magnitude is exported; vector direction remains in the native U files.",
            "The one-cell-thick Taylor-Green case is a plane field, not a three-dimensional volume result.",
            "Numerical verification of this benchmark is not fire-suppression or experimental validation.",
        ],
    }


def export_openfoam_taylor_green(
    case_dir: str | os.PathLike[str], output_path: str | os.PathLike[str]
) -> dict:
    result = read_openfoam_taylor_green(case_dir)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )
    return result


def export_openfoam_series(
    convergence_root: str | os.PathLike[str],
    output_dir: str | os.PathLike[str],
    resolutions: Sequence[int] = (20, 40, 80),
) -> list[dict]:
    root = Path(convergence_root)
    destination = Path(output_dir)
    results = []
    for resolution in resolutions:
        if isinstance(resolution, bool) or not isinstance(resolution, int) or resolution < 1:
            raise OpenFOAMFieldError("resolutions must be positive integers")
        result = export_openfoam_taylor_green(
            root / f"mesh_{resolution}",
            destination / f"openfoam_taylor_green_{resolution}.json",
        )
        if result["resolution"] != resolution:
            raise OpenFOAMFieldError("manifest resolution does not match requested dataset")
        results.append(result)
    return results


__all__ = [
    "OpenFOAMFieldError",
    "read_openfoam_taylor_green",
    "export_openfoam_taylor_green",
    "export_openfoam_series",
]
