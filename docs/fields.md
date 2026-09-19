# Native field ingestion and conservative exchange

## Scope

`firelab.fields` reads the native structured slice files produced by FDS. It
does not reconstruct a volume from one plane. Every field is labelled as a
point, line, plane, or volume from the number of varying native grid axes.

The binary reader follows the FDS writer contract in the official
[`DUMP_SLCF` source](https://github.com/firemodels/fds/blob/master/Source/dump.f90):

1. three 30-character Fortran sequential records for long label, short label,
   and units;
2. one record containing inclusive `I1,I2,J1,J2,K1,K2` indices;
3. repeated `REAL*4 time` and `REAL*4 field(I,J,K)` record pairs, with `I`
   varying fastest.

Physical coordinates are read from the companion Smokeview `.smv` `TRNX`,
`TRNY`, and `TRNZ` sections. The reader verifies that binary labels and index
bounds match the corresponding `SLCF` entry. Record markers, record sizes,
monotonic frame times, finite values, coordinate order, hashes, and frame/value
limits are checked before export. FDS's official `fds2ascii` utility is the
independent reference implementation for consuming these files:
[`fds2ascii.f90`](https://github.com/firemodels/fds/blob/master/Utilities/fds2ascii/fds2ascii.f90).

```python
from firelab.fields import export_fds_fields, read_fds_slice

collection = export_fds_fields("runs/fds_steckler_smoke_1s_actual")
field = read_fds_slice(
    "runs/fds_steckler_smoke_1s_actual/Steckler_010_smoke_1_1.sf",
    "runs/fds_steckler_smoke_1s_actual/Steckler_010_smoke.smv",
)
```

Each frame contains native time, minimum, maximum, and flattened values. Its
geometry provides exact axis coordinates, `shape_kji`, and the explicit
`i-fastest, then j, then k` ordering. The exported provenance includes SHA-256
hashes of both `.sf` and `.smv` sources. The `validation_status` remains
`unvalidated`: successful native parsing does not validate the fire model.

## Conservative rectilinear mapping

`firelab.coupling.conservative_remap` treats inputs as cell averages. For a
target cell `T` and source cells `S`, it computes

`q_T = sum_S(q_S * volume(T intersect S)) / volume(T)`.

The overlap is evaluated exactly as the product of one-dimensional rectilinear
overlap lengths. Target cells outside the source extent are rejected, so no
extrapolation occurs. The function returns both the source integral over the
target domain and the target integral; tests require their difference to be
within a strict floating-point tolerance. When both domains have identical
extents, this is a whole-domain conservation check.

Time interpolation is linear and only permitted inside the supplied time
interval. Coordinate transforms require explicit orthonormal, right-handed
Cartesian bases in metres. Unit conversion is allow-listed and rejects
dimensionally incompatible units.

## Exchange contract

`build_exchange_bundle` keeps these cell-average state variables distinct:

- mass density: `kg/m3`;
- momentum density, component order x/y/z: `kg/(m2 s)`;
- sensible enthalpy density: `J/m3`.

Sensible enthalpy is state carried into a receiving solver. It is not a
volumetric heat-release rate. The builder rejects metadata that asks it to
replace, include, or double-count a combustion heat source. Every bundle is
marked `one_way_exchange_only_unvalidated`; these data utilities do not claim
time-synchronized two-way FDS/OpenFOAM coupling.

Relevant primary references are the
[FDS Technical Reference Guide and User Guide](https://pages.nist.gov/fds/manuals.html)
and the official [FDS source repository](https://github.com/firemodels/fds).
