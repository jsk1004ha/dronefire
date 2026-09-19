#!/usr/bin/env python3
"""Create and run reproducible local FDS cases."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from firelab.native import (
    create_fds_derivative,
    create_fds_restartable_derivative,
    create_fds_resume_input,
    find_bundled_fds,
    probe_fds_runtime,
    run_fds_case,
    run_fds_case_wsl_ext4,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("status")
    derive = subparsers.add_parser("derive")
    derive.add_argument("source", type=Path)
    derive.add_argument("destination", type=Path)
    derive.add_argument("--t-end", type=float, required=True)
    derive.add_argument("--chid", required=True)
    checkpoint = subparsers.add_parser("checkpoint")
    checkpoint.add_argument("source", type=Path)
    checkpoint.add_argument("destination", type=Path)
    checkpoint.add_argument("--interval", type=float, required=True)
    resume = subparsers.add_parser("resume-input")
    resume.add_argument("source", type=Path)
    resume.add_argument("destination", type=Path)
    resume.add_argument("--restart-file", type=Path, required=True)
    run = subparsers.add_parser("run")
    run.add_argument("input", type=Path)
    run.add_argument("run_dir", type=Path)
    run.add_argument("--timeout", type=float, required=True)
    run.add_argument("--omp-threads", type=int, default=4)
    ext4 = subparsers.add_parser("run-ext4")
    ext4.add_argument("input", type=Path)
    ext4.add_argument("run_dir", type=Path)
    ext4.add_argument("--timeout", type=float, required=True)
    ext4.add_argument("--omp-threads", type=int, default=8)
    ext4.add_argument("--sync-interval", type=float, default=30)
    arguments = parser.parse_args()
    root = arguments.project_root.resolve()
    executable = find_bundled_fds(root)
    if arguments.action == "status":
        result = {"available": False, "reason": "bundled runtime not found"} if executable is None else probe_fds_runtime(executable)
    elif arguments.action == "derive":
        result = create_fds_derivative(
            arguments.source,
            arguments.destination,
            t_end_s=arguments.t_end,
            chid=arguments.chid,
            trusted_root=root,
        )
    elif arguments.action == "checkpoint":
        result = create_fds_restartable_derivative(
            arguments.source, arguments.destination,
            restart_interval_s=arguments.interval, trusted_root=root,
        )
    elif arguments.action == "resume-input":
        result = create_fds_resume_input(
            arguments.source, arguments.destination,
            restart_file=arguments.restart_file, trusted_root=root,
        )
    elif arguments.action == "run":
        if executable is None:
            raise SystemExit("bundled FDS runtime not found; see docs/native.md")
        result = run_fds_case(
            arguments.input,
            arguments.run_dir,
            executable=executable,
            trusted_root=root,
            timeout_s=arguments.timeout,
            omp_threads=arguments.omp_threads,
        )
    else:
        if executable is None:
            raise SystemExit("bundled FDS runtime not found; see docs/native.md")
        result = run_fds_case_wsl_ext4(
            arguments.input,
            arguments.run_dir,
            executable=executable,
            trusted_root=root,
            timeout_s=arguments.timeout,
            omp_threads=arguments.omp_threads,
            sync_interval_s=arguments.sync_interval,
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
