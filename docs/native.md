# Native solver execution

## Verified FDS path

The workspace contains the official FireModels release bundle for FDS 6.11.1
under `.tools/fds`. The release page and NIST download page both identify the
current pairing as FDS 6.11.1 / Smokeview 6.11.2. The downloaded Linux installer
matched the publisher's SHA-256 before its embedded archive was extracted. No
system package, shell startup file, or global install location was changed.

Runtime and input identity are recorded in `.tools/native_runtime_manifest.json`.
The source benchmark is immutable by convention:

- `cases/fds/source/Steckler_010.fds`
- SHA-256 `778cfa34368802a92cf9ad4750d418f8d3bd0aaa981776883cd985cd42c0e938`
- CHID `Steckler_010`, configured end time 1800 s

The runner copies a trusted local input into a dedicated run directory, invokes
FDS with an explicit argument list, and writes `run_manifest.json`. On WSL it
sets Intel MPI to shared-memory transport because the default fabric provider is
not available. A run is `completed` only when all of these are true:

1. the process exits with code 0 and no timeout;
2. the FDS success marker is present;
3. native CSV time reaches the input's configured `T_END`;
4. the CHID-matched `.out`, `_hrr.csv`, and `_devc.csv` all exist.

A success-looking log alone cannot pass the gate. Native computation is marked
`unvalidated`; solver completion does not establish experimental validity.

## Commands

From the project root in PowerShell:

```powershell
python scripts/native_fds.py status
python scripts/native_fds.py derive cases/fds/source/Steckler_010.fds cases/fds/steckler_smoke/Steckler_010_smoke.fds --t-end 1 --chid Steckler_010_smoke
python scripts/native_fds.py run cases/fds/steckler_smoke/Steckler_010_smoke.fds runs/fds_steckler_smoke_1s_actual --timeout 240 --omp-threads 4
```

The full baseline uses the unchanged source and a distinct output directory:

```powershell
python scripts/native_fds.py run cases/fds/source/Steckler_010.fds runs/fds_steckler_full --timeout 900 --omp-threads 8
```

For long Windows-hosted runs, execute on the WSL ext4 filesystem and mirror
progress back to a unique workspace directory every 30 seconds:

```powershell
python scripts/native_fds.py run-ext4 cases/fds/source/Steckler_010.fds runs/fds_steckler_full_ext4_omp8 --timeout 10800 --omp-threads 8 --sync-interval 30
```

The runner writes `status: running` before waiting, records a content-derived
run key, and never reuses an incomplete directory as a clean run. Completed
runs with the same input, executable, and thread count are cache candidates.
`validate_fds_cache(run_dir, manifest)` then recomputes the copied-input and
mandatory `.out`, HRR, and DEVC sizes and SHA-256 hashes, re-evaluates the FDS
success/time/artifact gates, and compares the fresh completion record with the
manifest. A deleted, changed, truncated, or unhashed output invalidates the
cache instead of returning a hit. OpenFOAM cache reuse applies the same stored
hash requirement to native logs and the final velocity field; older manifests
without an output inventory are explicitly invalidated. Resume
is available only for inputs that were explicitly changed to write a matching
`CHID.restart` checkpoint:

```powershell
python scripts/native_fds.py checkpoint input.fds checkpointed.fds --interval 60
python scripts/native_fds.py resume-input checkpointed.fds resume.fds --restart-file CHID.restart
```

The checkpointed and resume inputs have new hashes and are labelled as
derivatives. A timed-out original input without `DT_RESTART` cannot be resumed.

If the 1800 s model does not finish before the wall-time limit, the manifest
remains `timed_out` with a measured completion fraction. It must not be reported
as a completed baseline.

## Executed evidence (2026-09-18/19)

- `runs/fds_steckler_smoke_1s_actual/run_manifest.json`: completed in
  7.466 wall seconds using four OpenMP threads. Native time reached 1.0/1.0 s;
  the FDS success marker and CHID-matched `.out`, HRR, and DEVC outputs are all
  present. This is a runtime smoke derivative, not the 1800 s baseline.
- `runs/fds_steckler_full/run_manifest.json`: the unchanged source ran for the
  full 900.023 s wall limit using eight OpenMP threads and reached 180/1800 s
  (10.0%). The native `.out`, HRR, and DEVC files are preserved, but there is no
  success marker and the configured time was not covered. Its status is
  `timed_out`; it is not a completed or validated baseline.
- A 20 s derivative benchmark on WSL ext4 completed in 168.84 wall seconds
  with one OpenMP thread and 87.86 seconds with eight threads. Sixteen threads
  were slower and the trial was stopped. The selected eight-thread projection
  for the unchanged 1800 s case is roughly 2.2 hours before load variation.
- `runs/fds_steckler_full_ext4_omp8/run_manifest.json` is the live manifest for
  the one authorized unchanged 1800 s run. It started with a 10,800 s wall
  limit and remains `running` until the native time, success marker, and
  required output gates all pass. Do not cite it as completed while that status
  remains.

## OpenFOAM v2412 verified benchmark

The official OpenCFD repository was configured with its published
`add-debian-repo.sh`, and `openfoam2412-default` package `2412.260127-1` was
installed in Ubuntu 24.04 WSL2. The initially supplied cavity case now passes
the toolchain preflight, but its short transient is not used for convergence.

`cases/openfoam/v2412_taylor_green` implements the periodic analytic
Taylor-Green vortex with `nu=0.01 m2/s`. The runner writes exact cell-centre
initial velocity and kinematic pressure, runs native `blockMesh` and `icoFoam`,
and compares the final velocity with `exp(-2*nu*t)`.

```powershell
python scripts/native_openfoam.py status
python scripts/native_openfoam.py convergence --case cases/openfoam/v2412_taylor_green --run-root runs/openfoam_v2412_taylor_green_spatial --resolutions 20 40 80
python scripts/native_openfoam.py temporal --case cases/openfoam/v2412_taylor_green --run-root runs/openfoam_v2412_taylor_green_temporal --resolution 80 --time-steps 0.004 0.002 0.001
```

Fresh native results:

- Spatial relative velocity L2 error: 0.6560% (20x20), 0.2231% (40x40),
  0.04552% (80x80). The 40x40 to 80x80 differences in mean kinetic energy,
  maximum speed, mean vorticity, and maximum vorticity are all below 0.8%.
- At fixed 80x80, relative velocity L2 error is 0.04762%, 0.04689%, and
  0.04552% for `dt=0.004`, `0.002`, and `0.001 s` respectively.
- Machine-readable evidence is in
  `runs/openfoam_v2412_taylor_green_spatial/convergence.{json,csv}` and
  `runs/openfoam_v2412_taylor_green_temporal/temporal_convergence.{json,csv}`.

This establishes the installed OpenFOAM numerical transport path against an
analytic nonreactive benchmark. It does not validate a rotor wake, combustion,
particles, EHD, or fire suppression.

## References

- NIST downloads: https://pages.nist.gov/fds/downloads.html
- Official release: https://github.com/firemodels/fds/releases/tag/FDS-6.11.1
- OpenFOAM v2412 tutorial tree: https://develop.openfoam.com/Development/openfoam/-/tree/OpenFOAM-v2412/tutorials/incompressible/icoFoam
- OpenCFD Linux package instructions: https://www.openfoam.com/download/openfoam-installation-on-linux
- OpenFOAM v2412 release: https://www.openfoam.com/news/main-news/openfoam-v2412
