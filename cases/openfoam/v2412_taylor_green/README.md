# Taylor-Green vortex numerical benchmark

This OpenCFD OpenFOAM v2412 `icoFoam` case uses the periodic analytic
Taylor-Green vortex on `[0, 2*pi]^2`, `nu=0.01 m2/s`. The native runner writes
the exact cell-centre initial velocity and kinematic pressure, runs three
spatial meshes and three time steps, and compares the final velocity with the
analytic amplitude `exp(-2*nu*t)`. It verifies numerical transport only; it is
not a drone wake, combustion, or fire-suppression validation case.
