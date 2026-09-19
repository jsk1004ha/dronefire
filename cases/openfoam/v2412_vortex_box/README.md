# OpenFOAM v2412 vortex preflight

This is a small 2-D lid-driven cavity used to verify the native OpenFOAM path
and resolve a coherent vortex before any drone-wake model is attempted. It is
not a drone wake, fire, suppression, or validation case.

- Distribution contract: OpenCFD OpenFOAM `v2412`.
- Solver contract: `icoFoam`, which exists in the official v2412 tutorial tree.
- Mesh: 40 x 40 x 1 cells; front/back are `empty`.
- Physics: incompressible laminar Newtonian flow, `nu = 1e-5 m2/s`.
- Availability on 2026-09-19: OpenCFD OpenFOAM v2412 package
  `2412.260127-1` is installed in Ubuntu 24.04 WSL2. This cavity preflight ran
  through `blockMesh`, `icoFoam`, and vorticity post-processing. Its short
  transient is intentionally not used as a convergence claim. The analytic
  Taylor-Green benchmark under `../v2412_taylor_green` supplies the verified
  spatial and temporal comparisons.

When that exact distribution is installed, run from this directory:

```sh
blockMesh
icoFoam
postProcess -func vorticity
```

Passing this preflight only verifies the OpenFOAM toolchain and vortex
transport. A drone wake needs measured or declared rotor forcing, 3-D mesh
sensitivity, turbulence-model checks, and hold-out validation.
