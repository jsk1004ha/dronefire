#!/usr/bin/env python3
"""Run the pinned OpenFOAM v2412 mesh-convergence benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from firelab.native import (
    probe_openfoam_runtime,
    run_openfoam_convergence,
    run_openfoam_taylor_green_temporal,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("status")
    run = subparsers.add_parser("convergence")
    run.add_argument("--case", type=Path, default=Path("cases/openfoam/v2412_vortex_box"))
    run.add_argument("--run-root", type=Path, default=Path("runs/openfoam_v2412_vortex_convergence"))
    run.add_argument("--resolutions", type=int, nargs="+", default=[20, 40, 80])
    run.add_argument("--timeout", type=float, default=300)
    temporal = subparsers.add_parser("temporal")
    temporal.add_argument("--case", type=Path, default=Path("cases/openfoam/v2412_taylor_green"))
    temporal.add_argument("--run-root", type=Path, default=Path("runs/openfoam_v2412_taylor_green_temporal"))
    temporal.add_argument("--resolution", type=int, default=80)
    temporal.add_argument("--time-steps", type=float, nargs="+", default=[0.004, 0.002, 0.001])
    temporal.add_argument("--timeout", type=float, default=300)
    arguments = parser.parse_args()
    root = arguments.project_root.resolve()
    if arguments.action == "status":
        result = probe_openfoam_runtime()
    elif arguments.action == "convergence":
        result = run_openfoam_convergence(
            root / arguments.case,
            root / arguments.run_root,
            trusted_root=root,
            resolutions=tuple(arguments.resolutions),
            timeout_s=arguments.timeout,
        )
    else:
        result = run_openfoam_taylor_green_temporal(
            root / arguments.case,
            root / arguments.run_root,
            trusted_root=root,
            resolution=arguments.resolution,
            time_steps_s=tuple(arguments.time_steps),
            timeout_s=arguments.timeout,
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
