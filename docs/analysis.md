# Analysis JSON API

`firelab.analysis` generates the comparison design and analyzes imported run
outcomes. It does not infer suppression performance from the analytic transport
models and does not replace missing values with synthetic outcomes.

## Public functions

```python
generate_matrix() -> list[dict]
analyze_outcomes(records, tau_s, bootstrap_samples=500, seed=42) -> dict
compute_synergy(
    records,
    *,
    control_id,
    combination_id,
    partial_single_ids,
    equal_budget_single_ids=None,
    preselected_single_id=None,
    selection_provenance=None,
    bootstrap_samples=500,
    seed=42,
    eligible_evidence_types=("measured", "experimental", "validated_simulation"),
) -> dict
```

`generate_matrix()` returns 36 main conditions: one C0 control, five singles,
ten unordered simultaneous pairs, and twenty ordered sequential pairs. The
relative `resource_dose` values are design labels. Before simulation or analysis
they must be bound to an SI resource ledger. M5 rows state that M5 is a composite
candidate and require a CV, EHD, or COMBINED variant; the CV variant cannot be
assigned an assumed EHD force.

## Outcome import schema

Each JSON record must contain:

| Field | Type and rule |
|---|---|
| `case_id` | Non-empty string, unique within a condition |
| `block_id` | Non-empty string identifying a shared environment/seed block |
| `condition_id` or `method_id` | Exactly one non-empty grouping key |
| `run_status` | `completed`, `incomplete`, `aborted`, `numerical_failure`, or `solver_failure` |
| `observation_end_s` | Finite number >= 0 |
| `event` | JSON boolean |
| `event_time_s` | Finite seconds >= 0 when `event=true`; otherwise `null` |
| `loss_J_m2` | Finite number >= 0 for completed runs; may be `null` only for failed/incomplete runs |
| `input_energy_J` | Finite number >= 0 for completed runs; may be `null` only for failed/incomplete runs |
| `provenance` | Non-empty object; include `source` and `evidence_type` |

NaN and infinity are rejected. An event time cannot exceed the observation end.
A completed non-event run observed to at least `tau_s` is an administrative
censor. A run stopped before `tau_s` without an event is incomplete and excluded
from RMST and loss estimates. Numerical failures have their own count and are
never converted to non-events or assigned a loss.

The RMST is `mean(min(event_time_s, tau_s))` for complete events and common-horizon
administrative censors. Confidence intervals resample complete `block_id`
clusters, retaining all paired methods in a selected block. Pairwise differences
use only blocks available for both conditions. Intervals capture sampling
variation, not model or measurement bias.

## Non-outcome import template

This is a schema example for a solver failure. It is deliberately not a measured
result and contains no fabricated loss or energy outcome.

```json
{
  "case_id": "replace-with-run-id",
  "block_id": "replace-with-shared-seed-or-environment-id",
  "condition_id": "replace-with-condition-id",
  "run_status": "solver_failure",
  "observation_end_s": 0.0,
  "event": false,
  "event_time_s": null,
  "loss_J_m2": null,
  "input_energy_J": null,
  "provenance": {
    "source": "replace-with-file-or-run-manifest",
    "evidence_type": "unvalidated_physics"
  }
}
```

## Synergy resource extension

`compute_synergy` additionally requires every selected record to contain:

```json
{
  "resource": {
    "doses": {
      "M1": {"electrical_energy_J": 120.0}
    },
    "schedule": {
      "M1": {"start_s": 0.0, "duration_s": 2.0}
    },
    "budget": {
      "electrical_energy_J": 240.0,
      "pneumatic_energy_J": 0.0,
      "payload_kg": 0.0,
      "peak_power_W": 120.0,
      "mounted_mass_kg": 0.5,
      "operation_duration_s": 2.0
    }
  }
}
```

The numbers above illustrate JSON structure only and are not measurements or
recommended settings.

For additive synergy, `partial_single_ids` maps the two method IDs to the
condition IDs containing their partial-dose single runs. Within each block, the
method-specific `doses` and `schedule` objects must exactly match the same method
inside the combination. The calculation is
`Li(ei) + Lj(ej) - Lij(ei,ej) - L0`.

For equal-budget practical gain, `equal_budget_single_ids` may identify the two
full-dose candidates, but `preselected_single_id` must fix exactly one comparator
before the evaluation blocks are examined. `selection_provenance` must include a
non-empty `source` and `"independent_of_evaluation": true`, documenting an
independent training selection or a preregistered choice. The selected single's
entire budget vector and `input_energy_J` must exactly match the combination. The
calculation is `Lselected(E) - Lij(ei,ej)`. Selecting the lower-loss single
separately in each evaluation block is prohibited because it biases the gain.

All three `resource` sections (`doses`, `schedule`, and `budget`) must be
non-empty. A partial single must contain the requested method key in both
`doses` and `schedule`, and may not silently match two missing keys. A control
therefore records an explicit zero-dose control component rather than empty
objects. Missing preselection, selection provenance, conditions, resource
mismatches, non-completed records, and evidence outside the accepted evidence
types produce an explicit ineligible reason and `null` values rather than a
score.
