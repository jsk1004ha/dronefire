# One-dimensional EHD verification model

## Purpose and boundary

`firelab.ehd` is a numerical model of unipolar charge transport between two
parallel planar electrodes. It provides an independently testable electrical
submodel for the M5 research scenario. It is not a model of a complete ionic
wind device, corona source, conductive-aerosol vortex, drone, flame, or fire
suppression process.

The default case uses a 10 V potential difference across 0.1 m. These values
are intentionally mild hypothetical verification inputs. They are not measured
M5 parameters and must not be cited as device calibration.

## Equations

For constant permittivity and no prescribed gas velocity, the model solves

```text
d2(phi)/dx2 = -q/epsilon
E = -d(phi)/dx
dq/dt + dJ/dx = 0
J = mobility*q*E - diffusion*dq/dx
f_e = q*E
```

Here `q` is free-charge density in C/m3. The equations are the planar subset of
the standard Poisson and charge-transport model used for unipolar-injection
electrohydrodynamics. A public primary reference that states the Poisson,
charge-conservation, drift, convection, diffusion and `qE` force terms is
[Zhou et al., Heliyon 9 (2023), e12812](https://doi.org/10.1016/j.heliyon.2023.e12812).
The present model omits the reference model's fluid convection term because it
does not solve gas momentum.

Potential is fixed at both electrodes. The left boundary prescribes charge
density for inward drift and diffusion. The right boundary permits advective
outflow and uses zero diffusive gradient. There is no ion generation or
recombination inside the domain.

## Numerics and diagnostics

- Potential: second-order centered finite differences and a direct
  tridiagonal solve.
- Charge: cell-centred conservative finite volume, upwind electric drift,
  centered diffusion, and explicit Euler time advancement.
- Stability: every step satisfies a conservative combined drift/diffusion
  bound `dt <= CFL*dx/(max(abs(mobility*E)) + 4*D/dx)` with `CFL <= 0.9`.
- Positivity: a materially negative charge density stops the run; tiny floating
  point undershoots are clipped to zero.
- Charge ledger: change in domain charge per electrode area is compared with
  the time-integrated left-minus-right boundary current.
- Electrical diagnostics: `qE` force density, integrated force per area,
  conduction current, conduction power, and peak electric field.

The reported gas acceleration is only `integral(qE dx)/(rho_gas*gap)`, a
uniform-mass upper-bound diagnostic. No Navier–Stokes momentum response, drag,
turbulence, rotor flow, wall jet, or vortex formation is calculated.

## Use

```python
from firelab.ehd import simulate_ehd, verification

run = simulate_ehd()
checks = verification("reports/verification")
```

`verification()` covers:

1. the exact charge-free linear potential;
2. the exact constant-charge planar Poisson solution;
3. second-order spatial convergence for a smooth manufactured charge field;
4. reduction of transient drift error under time-step refinement;
5. conservative boundary/domain charge accounting and positivity.

Passing these checks establishes numerical consistency for this limited 1-D
model. It does not validate corona physics, ionic-wind thrust, a three-
dimensional electrode, M5 hardware, interaction with aerosol or flame, or fire
suppression efficacy.
