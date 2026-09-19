# WP3/WP4/WP6 analysis API

`firelab.study_analysis` and `firelab.exposure` analyze imported solver or
measurement time series. They do not turn the nonreactive transport models into
suppression outcomes. Synthetic values appear only in unit tests and carry
`evidence_type: synthetic_test`.

## Canonical time-series record

```python
record = {
    "case_id": "environment-001-M1-r1",
    "block_id": "environment-001-r1",
    "condition_id": "M1",
    "run_status": "completed",
    "time_s": [0.0, 1.0, 2.0],
    "channels": {
        "hrr_kW": [10.0, 6.0, 0.4],
        "heat_flux_kW_m2": [4.0, 3.0, 1.0],
    },
    "input_energy_J": 120.0,
    "intervention_end_s": 2.0,
    "provenance": {
        "source": "runs/.../manifest.json",
        "evidence_type": "native_unvalidated",
        "solver": "FDS 6.11.1",
    },
}
```

`time_s` must be finite and strictly increasing. Every channel has the same
length. `provenance.source` is mandatory. Input energy may be absent from a
native solver import: HRR, extinction, and exposure remain analyzable, while the
combined energy/outcome summary records `missing: ["input_energy_J"]` and keeps
that record incomplete. It never substitutes zero. Additional `resource` data
uses the ledger contract from `firelab.analysis.compute_synergy`.

## Preregistration

```python
preregistration = {
    "control_id": "C0",
    "tau_s": 60.0,
    "extinction": {
        "hrr_threshold_kW": 1.0,
        "sustain_s": 10.0,
        "reignition_threshold_kW": 2.0,
        "reignition_followup_s": 30.0,
    },
    "source": "configs/metrics.yaml",
    "declared_before_results": True,
}
```

The software applies the supplied values; it does not choose scientific
thresholds. The threshold source and the fact that it was fixed before looking
at outcomes remain the campaign's responsibility.

## WP3: suppression and exposure outcomes

- `analyze_extinction_run(record, criterion)` finds the first observed HRR
  sample beginning a continuously compliant span. It does not interpolate a
  more favorable extinction time.
- A reignition-free result requires the complete preregistered follow-up window.
  Shorter observation returns `unknown_insufficient_followup`.
- `integrate_hrr_decrease(method, control)` uses the union of both observed time
  grids inside their overlap. It interpolates within observations and never
  extrapolates.
- `analyze_study(...)` feeds extinction/censoring outcomes into the existing
  analysis. Its `extinction_statistics` output computes event counts, RMST, and
  paired block contrasts from extinction status alone. Missing heat flux or
  input energy therefore does not erase a valid time-to-extinction endpoint;
  those missing inputs mark only the combined exposure/energy outcome
  incomplete. Fewer than three independent blocks receive an explicit
  precision warning.

## WP4: combinations, order, and resources

`analyze_study(..., synergy_specs=[...])` passes physical exposure-loss records
and the original resource ledgers to `compute_synergy`. That existing gate
requires matched partial doses/schedules for additive synergy and a fixed,
independently selected equal-budget comparator for practical gain. Unvalidated
evidence is rejected by that ranking gate. Each returned item retains
`control_id`, `combination_id`, the partial/equal-budget comparator IDs, and the
exact `analysis_spec`, including when an evidence or resource gate blocks the
calculation. Reports can therefore display the actual gate reason without
guessing which combination it belongs to.

`analyze_order_effects` compares the two directions within common blocks. It
returns paired bootstrap intervals, sign-flip randomization p-values, and a Holm
family-wise adjustment over all eligible pairs. `pareto_front` keeps named
objectives separate and reports rows with missing objectives as incomplete.

## WP6: protected-location analysis and robustness

`firelab.exposure.analyze_exposure_run` accepts criteria such as:

```python
criteria = {
    "temperature_C": {
        "limit": 60.0,
        "direction": "above",
        "source": "preregistered project criterion",
    },
    "visibility_m": {
        "limit": 5.0,
        "direction": "below",
        "source": "preregistered project criterion",
    },
}
```

The first threshold crossing is retained as the observation interval between
adjacent samples. `summarize_exposure` calculates lower/upper RMST bounds and
paired method-minus-control difference bounds without midpoint imputation.
Locations are summarized separately so two sensors in the same paired block
cannot overwrite or masquerade as replicates of one another. For a single
location, `groups` is a convenience alias; multi-location output uses
`locations[location_id]` and leaves `groups` null.
Missing hazard channels are incomplete, not zero. These endpoints are exposure
criteria and are not renamed as human survival time.

`latin_hypercube` generates deterministic continuous designs. `split_cases`
keeps all conditions belonging to a case in one partition.
`evaluate_environment_policy` selects one condition for each exact environment
stratum using training cases only and evaluates that fixed choice on holdout
cases. Unseen strata are `out_of_domain`; absent selected conditions remain
missing rather than being replaced by another method.

## Evidence interpretation

The module permits descriptive processing of `native_unvalidated` records so
solver curves can be inspected. The provenance label remains in every result.
The existing synergy function admits only measured, experimental, or validated
simulation evidence by default, preventing descriptive native runs from being
silently promoted to comparative efficacy claims.
