# Internal implementation contract

Python package `firelab`, Python 3.12+, standard library + already available NumPy. No network dependency in UI; local `http.server` backend. Parent owns config, orchestration, HTTP server, source intake, reports and web UI. Separate agents own physics, drone, analytics and native-solver modules/tests respectively. Do not edit another owner's files.

## Shared configuration (JSON)

`scenario`: `duration_s` (4), `dt_s` (0.02), `distance_m` (1), `crosswind_m_s` (0.2), `ambient_K` (293.15), `target_radius_m` (0.2), `seed` (42).

`methods`: dictionaries keyed M1..M5 with physical parameters. Modules accept missing values via documented defaults and mark ALL default engineering values `assumed`, never measured or calibrated. Overrides validated, finite, with bounds. Fields emitted for viewing use metres/seconds/SI.

M1: `frequency_hz` 60, `velocity_rms_m_s` .4, `aperture_m` .15, `power_W` 80, `mass_kg` .5.
M2: `exit_velocity_m_s` 8, `diameter_m` .10, `pulse_duration_s` .05, `period_s` 1, `power_W` 15, `mass_kg` .6, `stored_energy_J` 100.
M3: `flow_kg_s` .005, `diameter_um` 100, `exit_velocity_m_s` 5, `power_W` 35, `mass_kg` .5, `payload_kg` .1.
M4: `flow_kg_s` .001, `diameter_um` 5, `exit_velocity_m_s` 2, `power_W` 10, `mass_kg` .4, `payload_kg` .05.
M5: `variant` 'CV', `charge_density_C_m3` 0, `electric_field_V_m` 0, `flow_kg_s` .001, `diameter_um` 10, `exit_velocity_m_s` 8, `diameter_m` .10, `pulse_duration_s` .05, `period_s` 1, `power_W` 20, `mass_kg` .7, `payload_kg` .05, `stored_energy_J` 100. CV is passive conductive-particle/vortex transport, no fictional EHD force. EHD requires explicit input and marked unvalidated.

`drone`: `mass_kg` 2, `battery_Wh` 120, `rotor_radius_m` .12, `rotor_count` 4, `max_thrust_N` 45, `max_power_W` 1200, `hover_efficiency` .6, `reserve_fraction` .2, `approach_s` 15, `return_s` 15, `avionics_W` 12, `inertia_kg_m2` [.04,.04,.08], `controller_enabled` true, `ambient_K` 293.15. Data provenance is assumed; no actual UAV certification.

## Module APIs

`physics.simulate_method(config, method_id) -> dict` JSON-safe:
`method_id`, `status`, `evidence_type`='unvalidated_physics', `model`, `limitations` list, `metrics` dict of SI scalar values or null, `series` list of objects (time_s, target_speed_m_s, etc.), `field` dict (`points`: list [x,y,z], `velocity`: list [vx,vy,vz], optional `scalar`, `scalar_name`, `unit`), `frames` optional max 12 frames, `reaction_force_N` [x,y,z], `device_power_W`, `device_mass_kg`, `consumable_kg`, `suppression`={'status':'insufficient_evidence','success_rate':null,'extinction_time_s':null}.
Compute real model equations/transport, not method-score rankings. Explicit documented model validity. Use finite and physical checks. Grid <=1000 vectors, output <500KB/method. No arbitrary flame extinction source terms. Pair combinations only through declared budget/physics, not efficiency sums. Parent may integrate independent fields for visual context ONLY with label no coupled physics.

`drone.simulate_mission(config, method_result, controller_enabled=True) -> dict` JSON-safe: `method_id`, `status` (feasible_in_model/conditional/infeasible), `evidence_type`, `limitations`, `metrics` (including energy_J, remaining_Wh, hover_power_W, peak_tilt_deg, max_position_error_m, peak_power_W, thrust_margin_N, mission_duration_s), `series` with time_s, x/y/z, roll_deg/pitch_deg, power_W, remaining_Wh, target_error_m, `failures` list. Use actual integration, actuator limits, impulses/forces, resource accounting and return reserve. Finite values; no performance claims.

`analysis.generate_matrix() -> list[dict]` 36 main conditions + metadata; each has id, methods, mode, order.
`analysis.analyze_outcomes(records, tau_s, bootstrap_samples=500, seed=42) -> dict`. Validated imported run records contain case_id, block_id, method_id/condition_id, run_status, observation_end_s, event(bool), event_time_s/null, loss_J_m2, input_energy_J, provenance. Fail closed on incomplete/invalid inputs; do not create synthetic efficacy. Group summaries with success counts, administrative censoring, RMST, bootstrap CI. Expose separate `synergy(...)` and `resource` helpers if useful; document API.

`native` API is free for agent; return runnable CLI/modules with availability checks, safe FDS case execution, version/hash/native outputs. Parent integrates via documented API. No shell interpolation of client inputs. Native runs may be executed outside HTTP.

## Output and tests

Each module owns meaningful `tests/test_<module>.py`, use unittest (no pytest installed). All public return values JSON serializable without NaN/Inf. Missing physical evidence remains visible; software/numerical verification does not become experimental validation. No claim that analytic transport is native CFD.
