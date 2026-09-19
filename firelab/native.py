"""Safe, reproducible runners for native CFD programs.

This module does not download or install solvers.  It executes only an explicit
local executable against an input file below an explicit trusted root, records
hashes and preserves the solver's native outputs in a run directory.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import posixpath
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


_CHID_RE = re.compile(r"\bCHID\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
_T_END_RE = re.compile(r"\bT_END\s*=\s*([0-9.+\-Ee]+)", re.IGNORECASE)
_TIME_RE = re.compile(
    r"\b(?:Simulation|Scaled\s+Total)\s+Time\s*[:=]?\s*([0-9.+\-Ee]+)",
    re.IGNORECASE,
)
_SUCCESS_MARKERS = (
    "STOP: FDS completed successfully",
    "FDS completed successfully",
    "Simulation completed successfully",
)


class NativeInputError(ValueError):
    """Raised before launch when a native run is not safely specified."""


@dataclass(frozen=True)
class FDSInput:
    path: str
    sha256: str
    chid: str
    t_end_s: float


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _tree_hash(root: Path, *, ignored_names: set[str] | None = None) -> str:
    ignored = ignored_names or set()
    entries: list[dict[str, str]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.name in ignored or any(part in ignored for part in path.relative_to(root).parts):
            continue
        entries.append({"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)})
    return _json_hash(entries)


def _output_inventory(directory: Path, *, excluded: set[str] | None = None) -> dict[str, dict[str, int | str]]:
    skipped = excluded or set()
    return {
        path.relative_to(directory).as_posix(): {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.relative_to(directory).as_posix() not in skipped
    }


def _resolved_below(path: Path, root: Path) -> Path:
    resolved = path.resolve(strict=True)
    trusted = root.resolve(strict=True)
    try:
        resolved.relative_to(trusted)
    except ValueError as exc:
        raise NativeInputError(f"input must be below trusted root: {trusted}") from exc
    return resolved


def inspect_fds_input(
    path: str | os.PathLike[str], *, trusted_root: str | os.PathLike[str] | None = None
) -> FDSInput:
    candidate = Path(path)
    resolved = (
        _resolved_below(candidate, Path(trusted_root))
        if trusted_root is not None
        else candidate.resolve(strict=True)
    )
    if resolved.suffix.lower() != ".fds":
        raise NativeInputError("FDS input must use the .fds extension")
    text = resolved.read_text(encoding="utf-8", errors="strict")
    chid_match = _CHID_RE.search(text)
    end_match = _T_END_RE.search(text)
    if not chid_match or not end_match:
        raise NativeInputError("FDS input must declare HEAD CHID and TIME T_END")
    chid = chid_match.group(1).strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", chid):
        raise NativeInputError("CHID contains unsupported filename characters")
    try:
        t_end_s = float(end_match.group(1))
    except ValueError as exc:
        raise NativeInputError("T_END is not numeric") from exc
    if not math.isfinite(t_end_s) or t_end_s <= 0:
        raise NativeInputError("T_END must be finite and positive")
    return FDSInput(str(resolved), sha256_file(resolved), chid, t_end_s)


def create_fds_derivative(
    source: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    t_end_s: float,
    chid: str,
    trusted_root: str | os.PathLike[str] | None = None,
) -> dict:
    """Create a short case while preserving and hashing the source input."""
    if not math.isfinite(t_end_s) or not 0 < t_end_s <= 60:
        raise NativeInputError("derivative T_END must be in (0, 60] seconds")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", chid):
        raise NativeInputError("CHID contains unsupported filename characters")
    original = inspect_fds_input(source, trusted_root=trusted_root)
    source_text = Path(original.path).read_text(encoding="utf-8")
    changed, count_chid = _CHID_RE.subn(f"CHID='{chid}'", source_text, count=1)
    changed, count_end = _T_END_RE.subn(f"T_END={t_end_s:.9g}", changed, count=1)
    if count_chid != 1 or count_end != 1:
        raise NativeInputError("could not make an unambiguous FDS derivative")

    # Ensure short runs actually emit HRR and DEVC samples without changing
    # the physics of the source case.
    interval = min(0.1, t_end_s / 5.0)
    changed = re.sub(
        r"\bDT_DEVC\s*=\s*[0-9.+\-Ee]+",
        f"DT_DEVC={interval:.9g}",
        changed,
        count=1,
        flags=re.IGNORECASE,
    )
    changed = re.sub(
        r"\bDT_HRR\s*=\s*[0-9.+\-Ee]+",
        f"DT_HRR={interval:.9g}",
        changed,
        count=1,
        flags=re.IGNORECASE,
    )
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(changed, encoding="utf-8", newline="\n")
    derived = inspect_fds_input(target)
    return {
        "source": asdict(original),
        "derivative": asdict(derived),
        "source_preserved_unchanged": sha256_file(original.path) == original.sha256,
    }


def create_fds_restartable_derivative(
    source: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    restart_interval_s: float,
    trusted_root: str | os.PathLike[str] | None = None,
) -> dict:
    """Create an explicitly labelled checkpoint-enabled derivative.

    Adding ``DT_RESTART`` changes the input hash, so this helper never presents
    the resulting case as the unchanged source benchmark.
    """
    if not math.isfinite(restart_interval_s) or restart_interval_s <= 0:
        raise NativeInputError("restart_interval_s must be finite and positive")
    original = inspect_fds_input(source, trusted_root=trusted_root)
    text = Path(original.path).read_text(encoding="utf-8")
    dump = re.search(r"&DUMP\b.*?/", text, flags=re.IGNORECASE | re.DOTALL)
    if dump is None:
        tail = re.search(r"&TAIL\s*/", text, flags=re.IGNORECASE)
        if tail is None:
            raise NativeInputError("FDS input has no DUMP or TAIL namelist")
        changed = text[: tail.start()] + f"&DUMP DT_RESTART={restart_interval_s:.9g} /\n" + text[tail.start() :]
    else:
        block = dump.group(0)
        if re.search(r"\bDT_RESTART\s*=", block, flags=re.IGNORECASE):
            block = re.sub(
                r"\bDT_RESTART\s*=\s*[0-9.+\-Ee]+",
                f"DT_RESTART={restart_interval_s:.9g}",
                block,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            block = block[:-1].rstrip() + f", DT_RESTART={restart_interval_s:.9g} /"
        changed = text[: dump.start()] + block + text[dump.end() :]
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(changed, encoding="utf-8", newline="\n")
    derived = inspect_fds_input(target)
    return {
        "source": asdict(original),
        "derivative": asdict(derived),
        "restart_interval_s": restart_interval_s,
        "source_preserved_unchanged": sha256_file(original.path) == original.sha256,
        "identity_changed": derived.sha256 != original.sha256,
    }


def create_fds_resume_input(
    restartable_input: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    restart_file: str | os.PathLike[str],
    trusted_root: str | os.PathLike[str] | None = None,
) -> dict:
    """Create a restart input only after a matching native checkpoint exists."""
    source = inspect_fds_input(restartable_input, trusted_root=trusted_root)
    checkpoint = Path(restart_file).resolve(strict=True)
    if checkpoint.name != f"{source.chid}.restart":
        raise NativeInputError(f"restart checkpoint must be named {source.chid}.restart")
    text = Path(source.path).read_text(encoding="utf-8")
    if not re.search(r"\bDT_RESTART\s*=", text, flags=re.IGNORECASE):
        raise NativeInputError("input was not configured to write restart checkpoints")
    misc = re.search(r"&MISC\b.*?/", text, flags=re.IGNORECASE | re.DOTALL)
    if misc is None:
        head = re.search(r"&HEAD\b.*?/", text, flags=re.IGNORECASE | re.DOTALL)
        if head is None:
            raise NativeInputError("FDS input has no HEAD namelist")
        changed = text[: head.end()] + "\n&MISC RESTART=.TRUE., APPEND=.TRUE. /" + text[head.end() :]
    else:
        block = misc.group(0)
        for key in ("RESTART", "APPEND"):
            if re.search(rf"\b{key}\s*=", block, flags=re.IGNORECASE):
                block = re.sub(rf"\b{key}\s*=\s*\.(?:TRUE|FALSE)\.", f"{key}=.TRUE.", block, count=1, flags=re.IGNORECASE)
            else:
                block = block[:-1].rstrip() + f", {key}=.TRUE. /"
        changed = text[: misc.start()] + block + text[misc.end() :]
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(changed, encoding="utf-8", newline="\n")
    resumed = inspect_fds_input(target)
    return {
        "source": asdict(source),
        "resume_input": asdict(resumed),
        "checkpoint": {"path": str(checkpoint), "sha256": sha256_file(checkpoint)},
    }


def _wsl_path(path: Path) -> str:
    result = subprocess.run(
        ["wsl.exe", "-e", "wslpath", "-a", str(path.resolve())],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    return result.stdout.strip()


def _runtime_command(
    executable: Path,
    run_dir: Path,
    input_name: str,
    *,
    omp_threads: int = 1,
    wall_timeout_s: float | None = None,
) -> tuple[list[str], dict[str, str]]:
    environment = os.environ.copy()
    if platform.system() == "Windows" and executable.suffix.lower() not in {".exe", ".bat", ".cmd"}:
        exe_wsl = _wsl_path(executable)
        dir_wsl = _wsl_path(run_dir)
        library_wsl = posixpath.join(posixpath.dirname(exe_wsl), "intelmpi", "lib")
        command = [
            "wsl.exe",
            "--cd",
            dir_wsl,
            "-e",
            "env",
            f"LD_LIBRARY_PATH={library_wsl}",
            "I_MPI_FABRICS=shm",
            f"OMP_NUM_THREADS={omp_threads}",
        ]
        if wall_timeout_s is not None:
            command.extend(
                ["timeout", "--signal=TERM", "--kill-after=5s", f"{wall_timeout_s:.3f}s"]
            )
        command.extend([exe_wsl, input_name])
        return command, environment
    lib_dir = executable.parent / "intelmpi" / "lib"
    if lib_dir.is_dir():
        prior = environment.get("LD_LIBRARY_PATH", "")
        environment["LD_LIBRARY_PATH"] = str(lib_dir) + (os.pathsep + prior if prior else "")
        environment["I_MPI_FABRICS"] = "shm"
    environment["OMP_NUM_THREADS"] = str(omp_threads)
    return [str(executable), input_name], environment


def _last_csv_time(path: Path) -> float | None:
    if not path.is_file():
        return None
    last: float | None = None
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
        for row in csv.reader(stream):
            if not row:
                continue
            try:
                value = float(row[0].strip())
            except ValueError:
                continue
            if math.isfinite(value):
                last = value
    return last


def evaluate_fds_outputs(run_dir: str | os.PathLike[str], chid: str, t_end_s: float) -> dict:
    directory = Path(run_dir)
    out_path = directory / f"{chid}.out"
    hrr_path = directory / f"{chid}_hrr.csv"
    devc_path = directory / f"{chid}_devc.csv"
    log_text = ""
    for path in (out_path, directory / "stdout.log", directory / "stderr.log"):
        if path.is_file():
            log_text += path.read_text(encoding="utf-8", errors="replace") + "\n"
    csv_times = [value for value in (_last_csv_time(hrr_path), _last_csv_time(devc_path)) if value is not None]
    text_times = []
    for match in _TIME_RE.finditer(log_text):
        try:
            text_times.append(float(match.group(1)))
        except ValueError:
            pass
    achieved = max(csv_times + text_times) if csv_times or text_times else None
    marker = any(item.lower() in log_text.lower() for item in _SUCCESS_MARKERS)
    tolerance = max(1.0e-6, abs(t_end_s) * 1.0e-6)
    coverage = achieved / t_end_s if achieved is not None else 0.0
    artifacts = {
        "out": out_path.is_file(),
        "hrr_csv": hrr_path.is_file(),
        "devc_csv": devc_path.is_file(),
    }
    return {
        "success_marker": marker,
        "achieved_time_s": achieved,
        "configured_t_end_s": t_end_s,
        "completion_fraction": min(coverage, 1.0),
        "time_covered": achieved is not None and achieved + tolerance >= t_end_s,
        "artifacts": artifacts,
        "required_artifacts_present": all(artifacts.values()),
    }


def _validate_manifest_output_hashes(directory: Path, outputs: object, required: Iterable[str]) -> list[str]:
    reasons: list[str] = []
    if not isinstance(outputs, dict) or not outputs:
        return ["manifest has no output hash inventory"]
    for relative in required:
        record = outputs.get(relative)
        if not isinstance(record, dict):
            reasons.append(f"missing manifest hash entry: {relative}")
            continue
        candidate = (directory / relative).resolve()
        try:
            candidate.relative_to(directory.resolve())
        except ValueError:
            reasons.append(f"output path escapes run directory: {relative}")
            continue
        if not candidate.is_file():
            reasons.append(f"missing cached output: {relative}")
            continue
        if candidate.stat().st_size != record.get("bytes"):
            reasons.append(f"cached output size mismatch: {relative}")
            continue
        if sha256_file(candidate) != record.get("sha256"):
            reasons.append(f"cached output hash mismatch: {relative}")
    return reasons


def validate_fds_cache(run_dir: str | os.PathLike[str], manifest: dict) -> dict:
    """Revalidate a completed FDS cache entry from native files and hashes."""
    directory = Path(run_dir).resolve()
    reasons: list[str] = []
    if manifest.get("status") != "completed":
        reasons.append("manifest status is not completed")
    input_record = manifest.get("input")
    if not isinstance(input_record, dict):
        reasons.append("manifest input record is missing")
        return {"valid": False, "reasons": reasons, "completion": None}
    chid = input_record.get("chid")
    t_end_s = input_record.get("t_end_s")
    if not isinstance(chid, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", chid):
        reasons.append("manifest CHID is invalid")
        return {"valid": False, "reasons": reasons, "completion": None}
    if not isinstance(t_end_s, (int, float)) or not math.isfinite(t_end_s) or t_end_s <= 0:
        reasons.append("manifest T_END is invalid")
        return {"valid": False, "reasons": reasons, "completion": None}
    copied_input = directory / f"{chid}.fds"
    if not copied_input.is_file():
        reasons.append(f"missing cached input: {chid}.fds")
    elif sha256_file(copied_input) != input_record.get("sha256"):
        reasons.append("cached input hash mismatch")
    required = [f"{chid}.fds", f"{chid}.out", f"{chid}_hrr.csv", f"{chid}_devc.csv"]
    reasons.extend(_validate_manifest_output_hashes(directory, manifest.get("outputs"), required))
    completion = evaluate_fds_outputs(directory, chid, float(t_end_s))
    if not completion["success_marker"]:
        reasons.append("cached output has no FDS success marker")
    if not completion["time_covered"]:
        reasons.append("cached output does not cover configured T_END")
    if not completion["required_artifacts_present"]:
        reasons.append("cached output is missing mandatory native artifacts")
    if manifest.get("completion") != completion:
        reasons.append("cached completion record differs from fresh evaluation")
    return {"valid": not reasons, "reasons": reasons, "completion": completion}


def validate_openfoam_cache(run_dir: str | os.PathLike[str], manifest: dict) -> dict:
    """Require a hash inventory and mandatory native fields before cache reuse."""
    directory = Path(run_dir).resolve()
    reasons: list[str] = []
    if manifest.get("status") != "completed":
        reasons.append("manifest status is not completed")
    metrics = manifest.get("metrics")
    if not isinstance(metrics, dict) or not isinstance(metrics.get("final_time_s"), (int, float)):
        reasons.append("manifest final time is missing")
        return {"valid": False, "reasons": reasons}
    final_label = f"{float(metrics['final_time_s']):g}"
    required = ["log.blockMesh", "log.icoFoam", f"{final_label}/U"]
    reasons.extend(_validate_manifest_output_hashes(directory, manifest.get("outputs"), required))
    return {"valid": not reasons, "reasons": reasons}


def probe_fds_runtime(executable: str | os.PathLike[str], *, timeout_s: float = 20) -> dict:
    exe = Path(executable).resolve(strict=True)
    command, environment = _runtime_command(exe, Path.cwd(), "")
    command = command[:-1]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        timeout=timeout_s,
    )
    combined = (result.stdout + "\n" + result.stderr).strip()
    revision = re.search(r"Revision\s*:\s*(.+)", combined)
    mpi = re.search(r"MPI library version\s*:\s*(.+)", combined)
    return {
        "available": "Fire Dynamics Simulator" in combined and revision is not None,
        "executable": str(exe),
        "sha256": sha256_file(exe),
        "revision": revision.group(1).strip() if revision else None,
        "mpi_library": mpi.group(1).strip() if mpi else None,
        "returncode": result.returncode,
        "output": combined,
    }


def run_fds_case(
    input_path: str | os.PathLike[str],
    run_dir: str | os.PathLike[str],
    *,
    executable: str | os.PathLike[str],
    trusted_root: str | os.PathLike[str],
    timeout_s: float,
    omp_threads: int = 4,
) -> dict:
    """Run one trusted local FDS input and write a fail-closed manifest."""
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise NativeInputError("timeout_s must be finite and positive")
    if not isinstance(omp_threads, int) or not 1 <= omp_threads <= (os.cpu_count() or 1):
        raise NativeInputError("omp_threads must be an integer within available CPU count")
    source = inspect_fds_input(input_path, trusted_root=trusted_root)
    exe = Path(executable).resolve(strict=True)
    destination = Path(run_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    runtime = probe_fds_runtime(exe)
    if not runtime["available"]:
        raise NativeInputError("FDS runtime probe failed")
    run_key = _json_hash(
        {
            "runner_schema": "fds-2.0",
            "input_sha256": source.sha256,
            "runtime_sha256": runtime["sha256"],
            "omp_threads": omp_threads,
        }
    )
    manifest_path = destination / "run_manifest.json"
    if manifest_path.is_file():
        prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        if prior.get("run_key") == run_key and prior.get("status") == "completed":
            cache_check = validate_fds_cache(destination, prior)
            if cache_check["valid"]:
                cached = dict(prior)
                cached["cache_hit"] = True
                cached["cache_validation"] = cache_check
                return cached
            raise NativeInputError("invalid FDS cache: " + "; ".join(cache_check["reasons"]))
        checkpoint = destination / f"{source.chid}.restart"
        if not checkpoint.is_file() or not re.search(
            r"\bRESTART\s*=\s*\.TRUE\.", Path(source.path).read_text(encoding="utf-8"), re.IGNORECASE
        ):
            raise NativeInputError(
                "run directory contains an incomplete manifest; use a new directory or a matching restart input"
            )
    case_path = destination / f"{source.chid}.fds"
    if case_path.exists() and sha256_file(case_path) != source.sha256:
        raise NativeInputError(f"run input already exists with different content: {case_path}")
    if not case_path.exists():
        shutil.copy2(source.path, case_path)
    copied = inspect_fds_input(case_path)
    if copied.sha256 != source.sha256:
        raise NativeInputError("copied input hash differs from source")

    command, environment = _runtime_command(
        exe,
        destination,
        case_path.name,
        omp_threads=omp_threads,
        wall_timeout_s=timeout_s,
    )
    started = _utc_now()
    start_clock = time.monotonic()
    timed_out = False
    returncode: int | None = None
    try:
        process = subprocess.run(
            command,
            cwd=destination,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            timeout=timeout_s + 10,
        )
        returncode = process.returncode
        timed_out = returncode == 124
        stdout = process.stdout
        stderr = process.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = (exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = (exc.stderr or b"").decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
    (destination / "stdout.log").write_text(stdout, encoding="utf-8")
    (destination / "stderr.log").write_text(stderr, encoding="utf-8")
    completion = evaluate_fds_outputs(destination, source.chid, source.t_end_s)
    completed = (
        not timed_out
        and returncode == 0
        and completion["success_marker"]
        and completion["time_covered"]
        and completion["required_artifacts_present"]
    )
    manifest = {
        "schema_version": "1.0",
        "solver": "FDS",
        "run_key": run_key,
        "cache_hit": False,
        "status": "completed" if completed else ("timed_out" if timed_out else "failed_or_incomplete"),
        "evidence_type": "native_simulation",
        "validation_status": "unvalidated",
        "started_utc": started,
        "finished_utc": _utc_now(),
        "wall_seconds": time.monotonic() - start_clock,
        "timeout_s": timeout_s,
        "omp_threads": omp_threads,
        "timed_out": timed_out,
        "returncode": returncode,
        "input": asdict(source),
        "runtime": {key: value for key, value in runtime.items() if key != "output"},
        "command": command,
        "completion": completion,
        "outputs": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in sorted(destination.iterdir())
            if path.is_file() and path.name != "run_manifest.json"
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def run_fds_case_wsl_ext4(
    input_path: str | os.PathLike[str],
    run_dir: str | os.PathLike[str],
    *,
    executable: str | os.PathLike[str],
    trusted_root: str | os.PathLike[str],
    timeout_s: float,
    omp_threads: int = 8,
    sync_interval_s: float = 30,
) -> dict:
    """Run FDS on WSL ext4 and mirror native progress to the workspace."""
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise NativeInputError("timeout_s must be finite and positive")
    if not math.isfinite(sync_interval_s) or not 5 <= sync_interval_s <= 60:
        raise NativeInputError("sync_interval_s must be in [5, 60]")
    source = inspect_fds_input(input_path, trusted_root=trusted_root)
    exe = Path(executable).resolve(strict=True)
    runtime = probe_fds_runtime(exe)
    if not runtime["available"]:
        raise NativeInputError("FDS runtime probe failed")
    destination = Path(run_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = destination / "run_manifest.json"
    run_key = _json_hash({"runner_schema": "fds-ext4-1.0", "input_sha256": source.sha256, "runtime_sha256": runtime["sha256"], "omp_threads": omp_threads})
    if manifest_path.is_file():
        prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        if prior.get("run_key") == run_key and prior.get("status") == "completed":
            cache_check = validate_fds_cache(destination, prior)
            if cache_check["valid"]:
                cached = dict(prior)
                cached["cache_hit"] = True
                cached["cache_validation"] = cache_check
                return cached
            raise NativeInputError("invalid FDS cache: " + "; ".join(cache_check["reasons"]))
    if any(destination.iterdir()):
        raise NativeInputError("ext4 run directory must be new and empty, or a matching completed cache entry")
    stage_name = re.sub(r"[^A-Za-z0-9_.-]", "_", destination.name) + "-" + run_key[:12]
    stage = f"/home/js10041530/firelab_runs/{stage_name}"
    source_wsl = _wsl_path(Path(source.path))
    exe_wsl = _wsl_path(exe)
    destination_wsl = _wsl_path(destination)
    library_wsl = posixpath.join(posixpath.dirname(exe_wsl), "intelmpi", "lib")
    prep = f"set -e; install -d /home/js10041530/firelab_runs; rm -rf {shlex_quote(stage)}; install -d {shlex_quote(stage)}; cp {shlex_quote(source_wsl)} {shlex_quote(stage + '/' + source.chid + '.fds')}"
    subprocess.run(["wsl.exe", "-d", "Ubuntu", "--", "bash", "-lc", prep], check=True, timeout=30)
    command_text = (
        f"cd {shlex_quote(stage)}; export LD_LIBRARY_PATH={shlex_quote(library_wsl)}; "
        f"export I_MPI_FABRICS=shm; export OMP_NUM_THREADS={omp_threads}; "
        f"timeout --signal=TERM --kill-after=10s {timeout_s:.3f}s {shlex_quote(exe_wsl)} {shlex_quote(source.chid + '.fds')} >stdout.log 2>stderr.log"
    )
    started = _utc_now()
    start_clock = time.monotonic()
    process = subprocess.Popen(["wsl.exe", "-d", "Ubuntu", "--", "bash", "-lc", command_text])
    base_manifest = {
        "schema_version": "1.0", "solver": "FDS", "run_key": run_key,
        "status": "running", "evidence_type": "native_simulation", "validation_status": "unvalidated",
        "started_utc": started, "timeout_s": timeout_s, "omp_threads": omp_threads,
        "input": asdict(source), "runtime": {key: value for key, value in runtime.items() if key != "output"},
        "execution_backend": "WSL2 ext4", "wsl_stage": stage, "windows_launcher_pid": process.pid,
    }

    def sync_outputs() -> None:
        sync = f"set -e; install -d {shlex_quote(destination_wsl)}; cp -af {shlex_quote(stage + '/.')} {shlex_quote(destination_wsl + '/')}"
        subprocess.run(["wsl.exe", "-d", "Ubuntu", "--", "bash", "-lc", sync], check=True, timeout=120)

    while process.poll() is None:
        try:
            sync_outputs()
            completion = evaluate_fds_outputs(destination, source.chid, source.t_end_s)
            progress = dict(base_manifest)
            progress.update({"wall_seconds": time.monotonic() - start_clock, "completion": completion, "last_sync_utc": _utc_now()})
            manifest_path.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8")
        finally:
            time.sleep(sync_interval_s)
    returncode = process.wait()
    sync_outputs()
    completion = evaluate_fds_outputs(destination, source.chid, source.t_end_s)
    timed_out = returncode == 124
    completed = returncode == 0 and completion["success_marker"] and completion["time_covered"] and completion["required_artifacts_present"]
    manifest = dict(base_manifest)
    manifest.update({
        "status": "completed" if completed else ("timed_out" if timed_out else "failed_or_incomplete"),
        "finished_utc": _utc_now(), "wall_seconds": time.monotonic() - start_clock,
        "timed_out": timed_out, "returncode": returncode, "completion": completion,
        "outputs": _output_inventory(destination, excluded={"run_manifest.json"}),
    })
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def find_bundled_fds(project_root: str | os.PathLike[str]) -> Path | None:
    root = Path(project_root)
    candidates: Iterable[Path] = (
        root / ".tools" / "fds" / "FDS-6.11.1_SMV-6.11.2_lnx" / "bin" / "fds_openmp",
        root / ".tools" / "fds" / "FDS-6.11.1_SMV-6.11.2_win" / "fds.exe",
    )
    return next((path.resolve() for path in candidates if path.is_file()), None)


def probe_openfoam_runtime(wrapper: str = "openfoam2412") -> dict:
    """Probe the pinned OpenCFD package in WSL without shell startup state."""
    command = [
        "wsl.exe", "-d", "Ubuntu", "--", "bash", "-lc",
        f"set -e; {wrapper} bash -lc 'command -v blockMesh; command -v icoFoam'; dpkg-query -W openfoam2412",
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return {
        "available": result.returncode == 0 and any(line.endswith("/blockMesh") for line in lines) and any(line.endswith("/icoFoam") for line in lines),
        "distribution": "OpenCFD",
        "release": "v2412",
        "package_version": lines[-1].split()[-1] if lines else None,
        "wrapper": wrapper,
        "returncode": result.returncode,
        "output": (result.stdout + "\n" + result.stderr).strip(),
    }


def _foam_vectors(path: Path) -> list[tuple[float, float, float]]:
    text = path.read_text(encoding="utf-8", errors="strict")
    match = re.search(r"internalField\s+nonuniform\s+List<vector>\s+\d+\s*\((.*?)\)\s*;", text, re.DOTALL)
    if match is None:
        raise NativeInputError(f"no nonuniform vector internalField in {path}")
    values = []
    for item in re.finditer(r"\(\s*([+\-0-9.eE]+)\s+([+\-0-9.eE]+)\s+([+\-0-9.eE]+)\s*\)", match.group(1)):
        values.append(tuple(float(item.group(index)) for index in (1, 2, 3)))
    if not values:
        raise NativeInputError(f"empty vector internalField in {path}")
    return values


def _openfoam_case_files(source: Path) -> list[Path]:
    required = [
        source / "0" / "U", source / "0" / "p",
        source / "constant" / "transportProperties",
        source / "system" / "blockMeshDict", source / "system" / "controlDict",
        source / "system" / "fvSchemes", source / "system" / "fvSolution",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise NativeInputError(f"OpenFOAM case is incomplete: {missing}")
    return required


def _write_taylor_green_initial(case: Path, resolution: int) -> None:
    length = 2.0 * math.pi
    velocity: list[tuple[float, float, float]] = []
    pressure: list[float] = []
    for j in range(resolution):
        y = (j + 0.5) * length / resolution
        for i in range(resolution):
            x = (i + 0.5) * length / resolution
            velocity.append((math.sin(x) * math.cos(y), -math.cos(x) * math.sin(y), 0.0))
            pressure.append(-0.25 * (math.cos(2.0 * x) + math.cos(2.0 * y)))
    boundary = """boundaryField
{
    xMin { type cyclic; }
    xMax { type cyclic; }
    yMin { type cyclic; }
    yMax { type cyclic; }
    frontAndBack { type empty; }
}
"""
    vector_lines = "\n".join(f"({x:.15g} {y:.15g} {z:.15g})" for x, y, z in velocity)
    scalar_lines = "\n".join(f"{value:.15g}" for value in pressure)
    (case / "0" / "U").write_text(
        "FoamFile { format ascii; class volVectorField; object U; }\n"
        "dimensions [0 1 -1 0 0 0 0];\n"
        f"internalField nonuniform List<vector> {len(velocity)}\n(\n{vector_lines}\n);\n" + boundary,
        encoding="utf-8", newline="\n",
    )
    (case / "0" / "p").write_text(
        "FoamFile { format ascii; class volScalarField; object p; }\n"
        "dimensions [0 2 -2 0 0 0 0];\n"
        f"internalField nonuniform List<scalar> {len(pressure)}\n(\n{scalar_lines}\n);\n" + boundary,
        encoding="utf-8", newline="\n",
    )


def _taylor_green_error(values: list[tuple[float, float, float]], resolution: int, time_s: float, nu: float = 0.01) -> dict:
    if len(values) != resolution * resolution:
        raise NativeInputError("Taylor-Green field cell count does not match the mesh")
    length = 2.0 * math.pi
    amplitude = math.exp(-2.0 * nu * time_s)
    squared_error = 0.0
    squared_reference = 0.0
    index = 0
    for j in range(resolution):
        y = (j + 0.5) * length / resolution
        for i in range(resolution):
            x = (i + 0.5) * length / resolution
            expected = (amplitude * math.sin(x) * math.cos(y), -amplitude * math.cos(x) * math.sin(y), 0.0)
            actual = values[index]
            squared_error += sum((actual[k] - expected[k]) ** 2 for k in range(3))
            squared_reference += sum(expected[k] ** 2 for k in range(3))
            index += 1
    return {
        "analytic_amplitude": amplitude,
        "velocity_l2_error_m_s": math.sqrt(squared_error / len(values)),
        "velocity_relative_l2_percent": math.sqrt(squared_error / squared_reference) * 100.0,
    }


def run_openfoam_convergence(
    base_case: str | os.PathLike[str],
    run_root: str | os.PathLike[str],
    *,
    trusted_root: str | os.PathLike[str],
    resolutions: tuple[int, ...] = (20, 40, 80),
    wrapper: str = "openfoam2412",
    timeout_s: float = 300,
) -> dict:
    """Run the same laminar vortex case on multiple uniform meshes."""
    source = _resolved_below(Path(base_case), Path(trusted_root))
    files = _openfoam_case_files(source)
    if len(resolutions) < 3 or any(not isinstance(value, int) or value < 8 for value in resolutions):
        raise NativeInputError("at least three integer mesh resolutions >= 8 are required")
    if len(set(resolutions)) != len(resolutions):
        raise NativeInputError("mesh resolutions must be unique")
    runtime = probe_openfoam_runtime(wrapper)
    if not runtime["available"]:
        raise NativeInputError("OpenFOAM v2412 runtime probe failed")
    destination_root = Path(run_root).resolve()
    destination_root.mkdir(parents=True, exist_ok=True)
    source_hash = _json_hash([{"path": path.relative_to(source).as_posix(), "sha256": sha256_file(path)} for path in files])
    rows: list[dict] = []
    for resolution in sorted(resolutions):
        destination = destination_root / f"mesh_{resolution}"
        run_key = _json_hash({"runner_schema": "openfoam-1.0", "source": source_hash, "resolution": resolution, "runtime": runtime["package_version"]})
        manifest_path = destination / "run_manifest.json"
        if manifest_path.is_file():
            prior = json.loads(manifest_path.read_text(encoding="utf-8"))
            if prior.get("run_key") == run_key and prior.get("status") == "completed":
                cache_check = validate_openfoam_cache(destination, prior)
                if cache_check["valid"]:
                    row = dict(prior["metrics"])
                    row["cache_hit"] = True
                    rows.append(row)
                    continue
                raise NativeInputError("invalid OpenFOAM cache: " + "; ".join(cache_check["reasons"]))
            raise NativeInputError(f"existing OpenFOAM run does not match cache key: {destination}")
        for path in files:
            target = destination / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        mesh_path = destination / "system" / "blockMeshDict"
        mesh_text = mesh_path.read_text(encoding="utf-8")
        mesh_text, count = re.subn(r"\(\s*40\s+40\s+1\s*\)", f"({resolution} {resolution} 1)", mesh_text, count=1)
        if count != 1:
            raise NativeInputError("base blockMeshDict must contain the canonical (40 40 1) cell tuple")
        mesh_path.write_text(mesh_text, encoding="utf-8", newline="\n")
        is_taylor_green = source.name == "v2412_taylor_green"
        if is_taylor_green:
            _write_taylor_green_initial(destination, resolution)
        wsl_case = _wsl_path(destination)
        command_text = (
            f"set -e; cd {shlex_quote(wsl_case)}; "
            f"timeout {timeout_s:.3f}s {wrapper} blockMesh > log.blockMesh 2>&1; "
            f"timeout {timeout_s:.3f}s {wrapper} icoFoam > log.icoFoam 2>&1; "
            f"timeout {timeout_s:.3f}s {wrapper} postProcess -func vorticity > log.vorticity 2>&1"
        )
        started = _utc_now()
        start_clock = time.monotonic()
        process = subprocess.run(["wsl.exe", "-d", "Ubuntu", "--", "bash", "-lc", command_text], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_s * 3 + 30)
        wall = time.monotonic() - start_clock
        times = sorted((path for path in destination.iterdir() if path.is_dir() and re.fullmatch(r"[0-9.]+", path.name)), key=lambda path: float(path.name))
        if process.returncode != 0 or not times:
            status = "failed_or_incomplete"
            metrics = {"resolution": resolution, "cells": resolution * resolution, "wall_seconds": wall}
        else:
            final = times[-1]
            velocity = _foam_vectors(final / "U")
            vorticity = _foam_vectors(final / "vorticity")
            speed2 = [x*x + y*y + z*z for x, y, z in velocity]
            vortmag = [math.sqrt(x*x + y*y + z*z) for x, y, z in vorticity]
            metrics = {
                "resolution": resolution,
                "cells": len(velocity),
                "final_time_s": float(final.name),
                "mean_kinetic_energy_m2_s2": 0.5 * sum(speed2) / len(speed2),
                "max_speed_m_s": math.sqrt(max(speed2)),
                "mean_vorticity_s_1": sum(vortmag) / len(vortmag),
                "max_vorticity_s_1": max(vortmag),
                "wall_seconds": wall,
                "cache_hit": False,
            }
            if is_taylor_green:
                metrics.update(_taylor_green_error(velocity, resolution, float(final.name)))
            status = "completed"
        manifest = {
            "schema_version": "1.0", "solver": "OpenFOAM icoFoam", "status": status,
            "evidence_type": "native_simulation", "validation_status": "numerically_verified" if status == "completed" else "unvalidated",
            "started_utc": started, "finished_utc": _utc_now(), "run_key": run_key,
            "source_case_hash": source_hash, "runtime": {key: value for key, value in runtime.items() if key != "output"},
            "metrics": metrics,
            "outputs": _output_inventory(destination, excluded={"run_manifest.json"}),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        if status != "completed":
            raise NativeInputError(f"OpenFOAM failed for mesh {resolution}; see {destination}")
        rows.append(metrics)
    rows.sort(key=lambda row: row["resolution"])
    for row in rows:
        row["relative_to_finest_percent"] = {}
        for key in ("mean_kinetic_energy_m2_s2", "max_speed_m_s", "mean_vorticity_s_1", "max_vorticity_s_1"):
            finest = rows[-1][key]
            row["relative_to_finest_percent"][key] = abs(row[key] - finest) / max(abs(finest), 1e-30) * 100.0
    summary = {
        "schema_version": "1.0", "status": "completed", "runtime": {key: value for key, value in runtime.items() if key != "output"},
        "source_case_hash": source_hash, "meshes": rows,
        "medium_fine_difference_percent": rows[-2]["relative_to_finest_percent"],
        "interpretation": (
            "analytic Taylor-Green nonreactive vortex mesh comparison; not drone-wake or suppression validation"
            if source.name == "v2412_taylor_green"
            else "numerical mesh comparison for a nonreactive 2-D cavity; not drone-wake or suppression validation"
        ),
    }
    (destination_root / "convergence.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    with (destination_root / "convergence.csv").open("w", encoding="utf-8", newline="") as stream:
        optional = ["velocity_l2_error_m_s", "velocity_relative_l2_percent"] if source.name == "v2412_taylor_green" else []
        writer = csv.DictWriter(stream, fieldnames=["resolution", "cells", "final_time_s", "mean_kinetic_energy_m2_s2", "max_speed_m_s", "mean_vorticity_s_1", "max_vorticity_s_1", *optional, "wall_seconds"])
        writer.writeheader()
        writer.writerows({key: row[key] for key in writer.fieldnames} for row in rows)
    return summary


def run_openfoam_taylor_green_temporal(
    base_case: str | os.PathLike[str],
    run_root: str | os.PathLike[str],
    *,
    trusted_root: str | os.PathLike[str],
    resolution: int = 80,
    time_steps_s: tuple[float, ...] = (0.004, 0.002, 0.001),
    wrapper: str = "openfoam2412",
    timeout_s: float = 300,
) -> dict:
    """Run fixed-mesh Taylor-Green cases at three or more time steps."""
    source = _resolved_below(Path(base_case), Path(trusted_root))
    if source.name != "v2412_taylor_green":
        raise NativeInputError("temporal convergence requires the Taylor-Green reference case")
    files = _openfoam_case_files(source)
    if resolution < 8 or len(time_steps_s) < 3 or any(not math.isfinite(dt) or dt <= 0 for dt in time_steps_s):
        raise NativeInputError("resolution >= 8 and at least three positive finite time steps are required")
    runtime = probe_openfoam_runtime(wrapper)
    if not runtime["available"]:
        raise NativeInputError("OpenFOAM v2412 runtime probe failed")
    source_hash = _json_hash([{"path": path.relative_to(source).as_posix(), "sha256": sha256_file(path)} for path in files])
    root = Path(run_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for dt in sorted(time_steps_s, reverse=True):
        label = f"dt_{dt:.9g}".replace(".", "p")
        destination = root / label
        run_key = _json_hash({"runner_schema": "openfoam-tg-time-1.0", "source": source_hash, "resolution": resolution, "delta_t_s": dt, "runtime": runtime["package_version"]})
        manifest_path = destination / "run_manifest.json"
        if manifest_path.is_file():
            prior = json.loads(manifest_path.read_text(encoding="utf-8"))
            if prior.get("run_key") == run_key and prior.get("status") == "completed":
                cache_check = validate_openfoam_cache(destination, prior)
                if cache_check["valid"]:
                    cached = dict(prior["metrics"])
                    cached["cache_hit"] = True
                    rows.append(cached)
                    continue
                raise NativeInputError("invalid OpenFOAM cache: " + "; ".join(cache_check["reasons"]))
            raise NativeInputError(f"existing temporal run does not match cache key: {destination}")
        for path in files:
            target = destination / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        mesh_path = destination / "system" / "blockMeshDict"
        mesh_text, mesh_count = re.subn(r"\(\s*40\s+40\s+1\s*\)", f"({resolution} {resolution} 1)", mesh_path.read_text(encoding="utf-8"), count=1)
        if mesh_count != 1:
            raise NativeInputError("canonical Taylor-Green mesh tuple not found")
        mesh_path.write_text(mesh_text, encoding="utf-8", newline="\n")
        control_path = destination / "system" / "controlDict"
        control_text, dt_count = re.subn(r"\bdeltaT\s+[0-9.eE+\-]+\s*;", f"deltaT {dt:.12g};", control_path.read_text(encoding="utf-8"), count=1)
        if dt_count != 1:
            raise NativeInputError("deltaT entry not found in Taylor-Green controlDict")
        control_path.write_text(control_text, encoding="utf-8", newline="\n")
        _write_taylor_green_initial(destination, resolution)
        wsl_case = _wsl_path(destination)
        command_text = (
            f"set -e; cd {shlex_quote(wsl_case)}; "
            f"timeout {timeout_s:.3f}s {wrapper} blockMesh > log.blockMesh 2>&1; "
            f"timeout {timeout_s:.3f}s {wrapper} icoFoam > log.icoFoam 2>&1"
        )
        started = _utc_now()
        start_clock = time.monotonic()
        process = subprocess.run(["wsl.exe", "-d", "Ubuntu", "--", "bash", "-lc", command_text], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_s * 2 + 30)
        wall = time.monotonic() - start_clock
        times = sorted((path for path in destination.iterdir() if path.is_dir() and re.fullmatch(r"[0-9.]+", path.name)), key=lambda path: float(path.name))
        if process.returncode != 0 or not times:
            raise NativeInputError(f"OpenFOAM temporal run failed for dt={dt}; see {destination}")
        final = times[-1]
        velocity = _foam_vectors(final / "U")
        metrics = {
            "resolution": resolution, "cells": len(velocity), "delta_t_s": dt,
            "final_time_s": float(final.name), "wall_seconds": wall, "cache_hit": False,
            **_taylor_green_error(velocity, resolution, float(final.name)),
        }
        manifest = {
            "schema_version": "1.0", "solver": "OpenFOAM icoFoam", "status": "completed",
            "evidence_type": "native_simulation", "validation_status": "numerically_verified",
            "started_utc": started, "finished_utc": _utc_now(), "run_key": run_key,
            "source_case_hash": source_hash, "runtime": {key: value for key, value in runtime.items() if key != "output"},
            "metrics": metrics,
            "outputs": _output_inventory(destination, excluded={"run_manifest.json"}),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        rows.append(metrics)
    rows.sort(key=lambda row: row["delta_t_s"], reverse=True)
    finest_error = rows[-1]["velocity_l2_error_m_s"]
    for row in rows:
        row["l2_error_relative_to_smallest_dt_percent"] = abs(row["velocity_l2_error_m_s"] - finest_error) / max(abs(finest_error), 1e-30) * 100.0
    summary = {
        "schema_version": "1.0", "status": "completed", "runtime": {key: value for key, value in runtime.items() if key != "output"},
        "source_case_hash": source_hash, "resolution": resolution, "time_steps": rows,
        "interpretation": "fixed-mesh time-step comparison against the analytic Taylor-Green velocity field",
    }
    (root / "temporal_convergence.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    with (root / "temporal_convergence.csv").open("w", encoding="utf-8", newline="") as stream:
        fieldnames = ["resolution", "cells", "delta_t_s", "final_time_s", "analytic_amplitude", "velocity_l2_error_m_s", "velocity_relative_l2_percent", "wall_seconds"]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows({key: row[key] for key in fieldnames} for row in rows)
    return summary


def shlex_quote(value: str) -> str:
    """Quote one POSIX shell argument without importing a command shell."""
    return "'" + value.replace("'", "'\"'\"'") + "'"
