# OpenFOAM Taylor–Green native field export

## Supported evidence

`firelab.openfoam_fields` exports velocity magnitude from the completed native
OpenFOAM v2412 Taylor–Green convergence cases under
`runs/openfoam_v2412_taylor_green_spatial`. The source cases contain actual
`icoFoam` `U` fields at times 0 and 0.2 s for 20×20×1, 40×40×1, and 80×80×1
meshes.

The reader intentionally supports only this proven class of mesh. OpenFOAM's
`polyMesh` can represent arbitrary polyhedra, so point counts alone cannot
justify reshaping a field into a Cartesian array. The exporter reads the ASCII
`points`, `faces`, `owner`, and `neighbour` files and requires all of the
following:

- every mesh point occurs exactly once in a complete Cartesian product of the
  x, y, and z coordinate axes;
- every cell has exactly eight unique vertices;
- every cell spans one adjacent interval on each axis;
- each structured grid slot contains exactly one cell;
- the calculated Cartesian cell count exactly equals the owner/neighbour cell
  count;
- each `U` internal field has that exact cell count and declares velocity
  dimensions `[0 1 -1 0 0 0 0]`.

Binary files, missing connectivity, arbitrary polyhedra, skewed cells, gaps,
duplicates, inconsistent counts, unsupported field classes, and non-finite
values are rejected. The connectivity interpretation follows OpenCFD's official
[polyMesh description](https://www.openfoam.com/documentation/user-guide/4-mesh-generation-and-conversion/4.1-mesh-description),
and parsing follows its official
[input/output format](https://www.openfoam.com/documentation/user-guide/2-openfoam-cases/2-2-basic-inputoutput-file-format).

## Output schema

```python
from firelab.openfoam_fields import export_openfoam_series

export_openfoam_series(
    "runs/openfoam_v2412_taylor_green_spatial",
    "reports/fields",
)
```

Each JSON collection uses the same UI-facing keys as the FDS field export:
`geometry.axes_m`, `geometry.shape_kji`, `frames[].time_s`,
`frames[].values`, `quantity`, `units`, and SHA-256 provenance. Cell values are
reordered by proven cell connectivity into `i-fastest, then j, then k` order.
The displayed scalar is `mag(U)` in m/s; the original vector components remain
in each native `U` file and are listed in per-frame provenance.

All three cases have one cell through z and are therefore labelled `plane`.
They are not presented as three-dimensional volume fields. Their native
Taylor–Green numerical verification does not validate fire suppression or a
physical drone device.
