"""Conservation and source-boundary regressions from the 2026-09 audit."""
import math
import re
import tempfile
import unittest
from pathlib import Path

import numpy as np

from firelab.drone import _method_inputs, _reaction_at, simulate_controls, simulate_mission
from firelab.physics import RHO_AIR, simulate_method
from firelab.reactive import _method_resource, _pulse_ramp, build_reactive_case, default_reactive_config


def mission_config(dt=.01):
    return {"scenario": {"duration_s": 1., "dt_s": dt, "distance_m": .01, "crosswind_m_s": 0.},
            "drone": {"approach_s": 0., "return_s": 0., "reaction_lever_arm_m": [0., 0., 0.]}}


def ramp_points(lines):
    return np.asarray([(float(t), float(f)) for t, f in
                       re.findall(r"T=([\d.eE+-]+), F=([\d.eE+-]+)", "\n".join(lines))])


class TransportAuditTests(unittest.TestCase):
    def test_short_payload_cannot_borrow_future_electrical_power(self):
        for method in ("M3", "M4"):
            with self.subTest(method=method):
                cfg = mission_config()
                cfg["methods"] = {method: {"flow_kg_s": 1., "payload_kg": .01,
                                          "power_W": 1., "exit_velocity_m_s": 5.}}
                result = simulate_method(cfg, method)
                speed = result["metrics"]["effective_exit_velocity_m_s"]
                power = .5 * RHO_AIR * math.pi * (.05 / 2)**2 * speed**3 + .5 * speed**2
                self.assertLessEqual(power, 1. + 1.e-12)
                self.assertEqual(result["resource_status"]["status"], "insufficient")

    def test_drone_depletes_payload_when_transport_depletes_it(self):
        cfg = mission_config()
        cfg["methods"] = {"M3": {"flow_kg_s": 1., "payload_kg": .01, "power_W": 35.}}
        result = simulate_method(cfg, "M3")
        flight = simulate_mission(cfg, result)
        midway = next(row for row in flight["series"] if abs(row["time_s"] - .5) < 1.e-10)
        self.assertAlmostEqual(midway["remaining_consumable_kg"], 0., places=12)
        expected = result["metrics"]["carrier_air_reaction_N"] + result["consumable_kg"] * 5.
        self.assertAlmostEqual(flight["metrics"]["reaction_impulse_Ns"], expected, places=10)

    def test_m5_particle_impulse_is_not_lost_in_pulsed_force(self):
        cfg = mission_config()
        result = simulate_method(cfg, "M5")
        gas = -result["reaction_pulse"]["peak_jet_force_N"][0] * .05
        expected = gas + result["consumable_kg"] * 8.
        flight = simulate_mission(cfg, result)
        self.assertAlmostEqual(flight["metrics"]["reaction_impulse_Ns"], expected, places=11)

    def test_mass_matched_off_keeps_the_same_initial_cg(self):
        cfg = mission_config(.1)
        cfg["drone"].update(device_mount_position_m=[1., 0., 0.], consumable_position_m=[-1., 0., 0.])
        result = {"method_id": "test", "device_mass_kg": .4, "consumable_kg": .1,
                  "loaded_consumable_kg": .2, "device_power_W": 0., "reaction_force_N": [0., 0., 0.]}
        controls = simulate_controls(cfg, result)
        initial = controls["corrected"]["metrics"]["initial_cg_m"]
        np.testing.assert_allclose(controls["off"]["metrics"]["initial_cg_m"], initial, atol=1.e-13)
        np.testing.assert_allclose(controls["off"]["metrics"]["final_cg_m"], initial, atol=1.e-13)

    def test_linear_force_integrates_exact_impulse_at_multiple_steps(self):
        for dt in (.1, .07, .02):
            with self.subTest(dt=dt):
                cfg = mission_config(dt)
                result = {"method_id": "test", "series": [
                    {"time_s": 0., "reaction_force_N": [0., 0., 0.]},
                    {"time_s": 1., "reaction_force_N": [2., 0., 0.]}]}
                flight = simulate_mission(cfg, result)
                self.assertAlmostEqual(flight["metrics"]["reaction_impulse_Ns"], 1., places=12)

    def test_force_average_integrates_all_internal_knots(self):
        method = _method_inputs({"series": [
            {"time_s": 0., "reaction_force_N": [0., 0., 0.]},
            {"time_s": .25, "reaction_force_N": [2., -2., 0.]},
            {"time_s": .5, "reaction_force_N": [0., 0., 0.]}]})
        np.testing.assert_allclose(_reaction_at(0., .5, method), [1., -1., 0.], atol=1.e-13)

    def test_duplicate_force_timestamps_are_rejected(self):
        with self.assertRaises(ValueError):
            _method_inputs({"series": [
                {"time_s": 0., "reaction_force_N": [0., 0., 0.]},
                {"time_s": 0., "reaction_force_N": [1., 0., 0.]}]})

    def test_d2_study_off_accepts_real_release_profiles(self):
        from firelab.drone_study import _inactive_method
        for mid in ("M3", "M4", "M5"):
            with self.subTest(method=mid):
                cfg = mission_config()
                original = simulate_method(cfg, mid)
                inactive = _inactive_method(original)
                flight = simulate_mission(cfg, inactive)
                self.assertEqual(flight["metrics"]["reaction_impulse_Ns"], 0.)
                self.assertEqual(inactive["device_mass_kg"], original["device_mass_kg"])
                self.assertEqual(inactive["loaded_consumable_kg"], original["loaded_consumable_kg"])

    def test_release_profile_mass_must_match_the_transport_ledger(self):
        result = simulate_method(mission_config(), "M3")
        result["consumable_release"]["flow_kg_s"] *= 2
        with self.assertRaises(ValueError):
            _method_inputs(result)

    def test_release_profile_cannot_extend_beyond_actuation(self):
        cfg = mission_config()
        result = simulate_method(cfg, "M3")
        result["consumable_release"]["flow_kg_s"] /= 2
        result["consumable_release"]["duration_s"] *= 2
        with self.assertRaises(ValueError):
            simulate_mission(cfg, result)

    def test_exhaust_stops_exactly_at_partial_interval_depletion(self):
        method = _method_inputs({
            "consumable_kg": .015,
            "consumable_release": {"flow_kg_s": .1, "duration_s": .15,
                                   "exhaust_velocity_m_s": [2., 0., 0.]},
            "nonconsumable_reaction_force_N": [-.03, 0., 0.],
        })
        np.testing.assert_allclose(_reaction_at(.1, .1, method), [-.13, 0., 0.], atol=1.e-13)
        np.testing.assert_allclose(_reaction_at(.2, .1, method), [-.03, 0., 0.], atol=1.e-13)

    def test_no_bus_power_means_no_emitted_mass_or_exhaust_impulse(self):
        cfg = mission_config()
        cfg["drone"]["max_power_W"] = 0.
        result = simulate_method(cfg, "M3")
        flight = simulate_mission(cfg, result)
        self.assertAlmostEqual(flight["series"][-1]["remaining_consumable_kg"], result["loaded_consumable_kg"])
        self.assertEqual(flight["metrics"]["reaction_impulse_Ns"], 0.)


class NativeSourceAuditTests(unittest.TestCase):
    def test_fixed_native_patch_rejects_mismatched_or_zero_area(self):
        for method in ("M1", "M2", "M3"):
            for area in (0., .02):
                with self.subTest(method=method, area=area), tempfile.TemporaryDirectory() as tmp:
                    with self.assertRaises(ValueError):
                        build_reactive_case({"methods": {method: {"vent_area_m2": area}}}, f"S_{method}", tmp)

    def test_burner_cannot_be_zero_unresolved_or_outside_domain(self):
        for area in (0., .03, 9.):
            with self.subTest(area=area), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ValueError):
                    build_reactive_case({"burner": {"area_m2": area}}, "C0", tmp)

    def test_native_pulse_never_leaks_past_its_declared_window(self):
        points = ramp_points(_pulse_ramp("test", 6., .05, cycles=1, period=1., pulse_width=.05))
        self.assertLessEqual(points[-1, 0], 6.05)
        self.assertEqual(points[-1, 1], 0.)

    def test_short_native_pulses_have_unique_serialized_times(self):
        points = ramp_points(_pulse_ramp("test", 6., .001, cycles=2, period=.0005, pulse_width=.0002))
        self.assertTrue(np.all(np.diff(points[:, 0]) > 0.))
        self.assertLessEqual(points[-1, 0], 6.001)
        self.assertTrue(np.all((points[:, 1] >= 0.) & (points[:, 1] <= 1.)))

    def test_native_resource_matches_the_actual_ramp_integral(self):
        cfg = default_reactive_config()
        for method in ("M1", "M2", "M3"):
            for duration in (.02, 1.02, 2.):
                with self.subTest(method=method, duration=duration):
                    spec = cfg["methods"][method]
                    extra = ({"period": spec["period_s"], "pulse_width": spec["pulse_duration_s"],
                              "cycles": math.ceil(duration / spec["period_s"])} if method == "M2" else {})
                    points = ramp_points(_pulse_ramp("test", 6., duration, **extra))
                    integral = float(np.trapezoid(points[:, 1], points[:, 0]))
                    resource = _method_resource(cfg, method, duration, .5)
                    if method == "M3":
                        self.assertAlmostEqual(resource["water_mass_kg"], spec["water_flow_kg_s"] * .5 * integral, places=12)
                    else:
                        speed = spec["exit_velocity_m_s"] if method == "M2" else math.sqrt(2) * spec["velocity_rms_m_s"]
                        self.assertAlmostEqual(resource["air_volume_m3"], speed * spec["vent_area_m2"] * .5 * integral, places=12)

    def test_native_pulse_configuration_requires_positive_period_and_valid_width(self):
        for patch in ({"period_s": 0.}, {"pulse_duration_s": 0.}, {"pulse_duration_s": 2.}):
            with self.subTest(patch=patch), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ValueError):
                    build_reactive_case({"methods": {"M2": patch}}, "S_M2", tmp)

    def test_complete_generated_input_matches_manifest_resource(self):
        for mid in ("M1", "M2", "M3"):
            with self.subTest(method=mid), tempfile.TemporaryDirectory() as tmp:
                from firelab.reactive import default_reactive_conditions
                item = next(row for row in default_reactive_conditions() if row["id"] == f"S_{mid}")
                item["schedule"][mid] = {"start_s": 6.123, "duration_s": 1.02}
                manifest = build_reactive_case(None, item, tmp)
                text = Path(manifest["input_path"]).read_text()
                points = ramp_points([line for line in text.splitlines() if f"&RAMP ID='R_{mid}_S_{mid}'" in line])
                integral = float(np.trapezoid(points[:, 1], points[:, 0]))
                source = next(line for line in text.splitlines() if line.startswith(f"&SURF ID='SRC_{mid}'"))
                resource = manifest["resource"][0]
                if mid == "M3":
                    flux = float(re.search(r"PARTICLE_MASS_FLUX=([\d.eE+-]+)", source)[1])
                    self.assertAlmostEqual(resource["water_mass_kg"], flux * .01 * integral, places=12)
                else:
                    speed = -float(re.search(r"VEL=([\d.eE+-]+)", source)[1])
                    self.assertAlmostEqual(resource["air_volume_m3"], speed * .01 * integral, places=12)
                if mid == "M2":
                    self.assertEqual(resource["pulse_count"], 2)

    def test_contiguous_pulses_are_one_continuous_window(self):
        points = ramp_points(_pulse_ramp("test", 0., .3, cycles=3, period=.1, pulse_width=.1))
        self.assertTrue(np.all(np.diff(points[:, 0]) > 0.))
        self.assertFalse(any(0. < t < .3 and f == 0. for t, f in points))

    def test_zero_cycles_does_not_silently_turn_source_on(self):
        points = ramp_points(_pulse_ramp("test", 6., 1., cycles=0, period=1., pulse_width=.05))
        self.assertTrue(np.all(points[:, 1] == 0.))


if __name__ == "__main__":
    unittest.main()
