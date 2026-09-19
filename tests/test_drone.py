import json
import math
import unittest

from firelab.drone import simulate_controls, simulate_mission


def method(**overrides):
    result = {
        "method_id": "M2",
        "reaction_force_N": [0.0, 0.0, 0.0],
        "device_power_W": 15.0,
        "device_mass_kg": 0.6,
        "consumable_kg": 0.0,
    }
    result.update(overrides)
    return result


class DroneMissionTests(unittest.TestCase):
    def test_no_battery_disables_rotor_moment_but_keeps_external_moment(self):
        config={'scenario':{'duration_s':0.3,'dt_s':0.01,'distance_m':0.0},
                'drone':{'approach_s':0.0,'return_s':0.0,'battery_Wh':0.0}}
        load=method(device_power_W=0.0,reaction_force_N=[2.0,0.0,0.0])
        powered_gains=simulate_mission(config,load)
        zero_gains=simulate_mission({**config,'drone':{**config['drone'],
                                   'attitude_kp_Nm':0.0,'attitude_kd_Nms':0.0}},load)
        self.assertAlmostEqual(powered_gains['series'][-1]['pitch_deg'],
                               zero_gains['series'][-1]['pitch_deg'],places=10)
        self.assertGreater(abs(powered_gains['series'][-1]['pitch_deg']),0.01)

    def test_hover_symmetry_and_json_safety(self):
        config = {
            "scenario": {"duration_s": 1.0, "dt_s": 0.02, "distance_m": 0.0, "crosswind_m_s": 0.0},
            "drone": {"approach_s": 0.5, "return_s": 0.5},
        }
        result = simulate_mission(config, method(device_mass_kg=0.0, device_power_W=0.0))
        self.assertEqual(result["status"], "feasible_in_model")
        self.assertLess(result["metrics"]["max_position_error_m"], 1e-6)
        self.assertLess(result["metrics"]["peak_tilt_deg"], 1e-6)
        self.assertAlmostEqual(result["series"][-1]["x"], 0.0, places=7)
        self.assertIsInstance(json.dumps(result, allow_nan=False), str)

    def test_zero_resources_are_reported_infeasible(self):
        config = {
            "scenario": {"duration_s": 0.4, "dt_s": 0.02},
            "drone": {
                "approach_s": 0.2,
                "return_s": 0.2,
                "battery_Wh": 0.0,
                "max_power_W": 0.0,
                "payload_capacity_kg": 0.0,
            },
        }
        result = simulate_mission(config, method())
        self.assertEqual(result["status"], "infeasible")
        self.assertIn("battery_depleted", result["failures"])
        self.assertIn("power_unavailable", result["failures"])
        self.assertIn("payload_capacity_exceeded", result["failures"])

    def test_recoil_feedback_reduces_tracking_error(self):
        config = {
            "scenario": {"duration_s": 3.0, "dt_s": 0.01, "distance_m": 0.0},
            "drone": {"approach_s": 0.5, "return_s": 0.5, "tracking_tolerance_m": 10.0},
        }
        comparison = simulate_controls(
            config,
            method(reaction_force_N=[4.0, 0.0, 0.0], reaction_pulse={"period_s": 0.4, "duration_s": 0.2}),
        )
        controlled = comparison["corrected"]["metrics"]["max_position_error_m"]
        open_loop = comparison["uncorrected"]["metrics"]["max_position_error_m"]
        self.assertLess(controlled, open_loop)
        self.assertGreater(open_loop, 0.1)

    def test_off_control_keeps_starting_payload_without_using_device(self):
        config = {
            "scenario": {"duration_s": 0.6, "dt_s": 0.02, "distance_m": 0.0},
            "drone": {"approach_s": 0.2, "return_s": 0.2},
        }
        comparison = simulate_controls(
            config,
            method(device_mass_kg=0.4, consumable_kg=0.2, device_power_W=100.0, reaction_force_N=[2.0, 0.0, 0.0]),
        )
        off = comparison["off"]
        active = comparison["uncorrected"]
        self.assertEqual(set(comparison), {"off", "uncorrected", "corrected"})
        self.assertAlmostEqual(off["metrics"]["final_mass_kg"], 2.6, places=7)
        self.assertAlmostEqual(active["metrics"]["final_mass_kg"], 2.4, places=7)
        self.assertEqual(off["metrics"]["consumable_used_kg"], 0.0)
        self.assertLess(off["metrics"]["peak_power_W"], active["metrics"]["peak_power_W"])
        self.assertLess(off["metrics"]["max_position_error_m"], active["metrics"]["max_position_error_m"])

    def test_energy_and_consumable_conservation_with_reserve(self):
        config = {
            "scenario": {"duration_s": 1.0, "dt_s": 0.01, "distance_m": 0.0},
            "drone": {"approach_s": 0.5, "return_s": 0.5, "battery_Wh": 50.0, "reserve_fraction": 0.2},
        }
        result = simulate_mission(config, method(consumable_kg=0.2, device_mass_kg=0.1))
        metrics = result["metrics"]
        initial_J = 50.0 * 3600.0
        self.assertAlmostEqual(initial_J - metrics["remaining_Wh"] * 3600.0, metrics["energy_J"], places=5)
        self.assertLess(metrics["energy_balance_error_J"], 1e-7)
        self.assertAlmostEqual(metrics["consumable_used_kg"], 0.2, places=6)
        self.assertAlmostEqual(metrics["final_mass_kg"], 2.1, places=6)
        self.assertGreaterEqual(metrics["actuation_end_remaining_J"], metrics["reserve_required_J"])

    def test_loaded_payload_keeps_unused_ballast(self):
        config = {
            "scenario": {"duration_s": 0.5, "dt_s": 0.01, "distance_m": 0.0},
            "drone": {"approach_s": 0.2, "return_s": 0.2},
        }
        result = simulate_mission(
            config,
            method(device_mass_kg=0.1, consumable_kg=0.2, loaded_consumable_kg=0.5),
        )
        self.assertAlmostEqual(result["metrics"]["consumable_used_kg"], 0.2, places=7)
        self.assertAlmostEqual(result["metrics"]["remaining_consumable_kg"], 0.3, places=7)
        self.assertAlmostEqual(result["metrics"]["final_mass_kg"], 2.4, places=7)

    def test_pulse_overlap_preserves_impulse_across_nondividing_time_step(self):
        config = {
            "scenario": {"duration_s": 1.0, "dt_s": 0.02, "distance_m": 0.0, "crosswind_m_s": 0.0},
            "drone": {"approach_s": 0.2, "return_s": 0.2, "tracking_tolerance_m": 10.0},
        }
        result = simulate_mission(
            config,
            method(
                reaction_force_N=[4.0, 0.0, 0.0],
                reaction_pulse={
                    "peak_force_N": [4.0, 0.0, 0.0],
                    "peak_jet_force_N": [4.0, 0.0, 0.0],
                    "steady_force_N": [0.0, 0.0, 0.0],
                    "period_s": 0.1,
                    "pulse_duration_s": 0.05,
                },
            ),
        )
        self.assertAlmostEqual(result["metrics"]["reaction_impulse_Ns"], 2.0, places=7)

    def test_insufficient_method_resource_blocks_feasibility(self):
        result = simulate_mission(
            {"scenario": {"duration_s": 0.2, "dt_s": 0.02}, "drone": {"approach_s": 0.1, "return_s": 0.1}},
            method(resource_status={"status": "insufficient", "reason": "stored gas energy below demand"}),
        )
        self.assertEqual(result["status"], "infeasible")
        self.assertIn("method_resource_insufficient", result["failures"])

    def test_available_pulse_count_limits_recoil(self):
        config = {
            "scenario": {"duration_s": 1.0, "dt_s": 0.02, "distance_m": 0.0, "crosswind_m_s": 0.0},
            "drone": {"approach_s": 0.2, "return_s": 0.2, "tracking_tolerance_m": 10.0},
        }
        result = simulate_mission(
            config,
            method(
                reaction_force_N=[4.0, 0.0, 0.0],
                reaction_pulse={
                    "peak_jet_force_N": [4.0, 0.0, 0.0],
                    "steady_force_N": [0.0, 0.0, 0.0],
                    "period_s": 0.1,
                    "pulse_duration_s": 0.05,
                    "simulated_pulses": 1,
                },
                resource_status={"status": "insufficient", "reason": "one pulse available"},
            ),
        )
        self.assertAlmostEqual(result["metrics"]["reaction_impulse_Ns"], 0.2, places=7)

    def test_return_reserve_shortfall(self):
        config = {
            "scenario": {"duration_s": 1.0, "dt_s": 0.02, "distance_m": 0.0},
            "drone": {"approach_s": 1.0, "return_s": 2.0, "battery_Wh": 0.08, "reserve_fraction": 0.2},
        }
        result = simulate_mission(config, method(device_mass_kg=0.0, device_power_W=0.0))
        self.assertEqual(result["status"], "infeasible")
        self.assertIn("return_reserve_shortfall", result["failures"])

    def test_nonfinite_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            simulate_mission({"drone": {"battery_Wh": math.inf}}, method())
        with self.assertRaises(ValueError):
            simulate_mission({}, method(reaction_force_N=[0.0, math.nan, 0.0]))
        with self.assertRaises(ValueError):
            simulate_mission({}, method(device_power_W=float("nan")))

    def test_actuator_disk_efficiency_cannot_exceed_unity(self):
        with self.assertRaisesRegex(ValueError, "hover_efficiency must be <= 1"):
            simulate_mission({"drone": {"hover_efficiency": 1.01}}, method())

    def test_battery_energy_is_clamped_and_vehicle_becomes_unpowered(self):
        result = simulate_mission(
            {
                "scenario": {"duration_s": 0.5, "dt_s": 0.02, "distance_m": 0.0},
                "drone": {
                    "approach_s": 0.0,
                    "return_s": 0.5,
                    "battery_Wh": 0.001,
                    "reserve_fraction": 0.0,
                },
            },
            method(device_mass_kg=0.0, device_power_W=0.0),
        )
        self.assertIn("battery_depleted", result["failures"])
        self.assertAlmostEqual(result["metrics"]["energy_J"], 3.6, places=10)
        self.assertEqual(result["metrics"]["remaining_Wh"], 0.0)
        self.assertLess(result["metrics"]["energy_balance_error_J"], 1e-10)
        self.assertGreater(result["metrics"]["electrically_unpowered_s"], 0.5)

    def test_zero_torque_limit_really_disables_control_torque(self):
        base = {
            "scenario": {"duration_s": 0.3, "dt_s": 0.01, "distance_m": 0.0},
            "drone": {
                "approach_s": 0.0,
                "return_s": 0.0,
                "max_torque_Nm": 0.0,
                "tracking_tolerance_m": 10.0,
            },
        }
        uncontrolled_gains = {
            **base,
            "drone": {**base["drone"], "attitude_kp_Nm": 0.0, "attitude_kd_Nms": 0.0},
        }
        forcing = method(
            device_power_W=0.0,
            reaction_force_N=[2.0, 0.0, 0.0],
            device_mass_kg=0.0,
        )
        limited = simulate_mission(base, forcing)
        zero_gain = simulate_mission(uncontrolled_gains, forcing)
        self.assertAlmostEqual(
            limited["series"][-1]["pitch_deg"],
            zero_gain["series"][-1]["pitch_deg"],
            places=10,
        )

    def test_exact_lumped_thermal_update_cannot_overshoot_ambient(self):
        ambient = 293.15
        result = simulate_mission(
            {
                "scenario": {"duration_s": 2.0, "dt_s": 2.0, "distance_m": 0.0},
                "drone": {"approach_s": 0.0, "return_s": 0.0, "ambient_K": ambient},
                "thermal": {
                    "incident_flux_W_m2": 0.0,
                    "exposed_area_m2": 1.0,
                    "heat_capacity_J_K": 1.0,
                    "cooling_W_K": 100.0,
                    "max_temperature_K": 500.0,
                    "initial_temperature_K": 400.0,
                },
            },
            method(device_mass_kg=0.0, device_power_W=0.0),
        )
        final_temperature = result["series"][-1]["temperature_K"]
        expected = ambient + (400.0 - ambient) * math.exp(-200.0)
        self.assertGreaterEqual(final_temperature, ambient)
        self.assertAlmostEqual(final_temperature, expected, places=12)

    def test_nondividing_phase_boundaries_preserve_mass_and_impulse(self):
        result = simulate_mission(
            {
                "scenario": {"duration_s": 0.37, "dt_s": 0.2, "distance_m": 0.0},
                "drone": {"approach_s": 0.15, "return_s": 0.11, "tracking_tolerance_m": 10.0},
            },
            method(
                device_power_W=0.0,
                device_mass_kg=0.0,
                reaction_force_N=[2.0, 0.0, 0.0],
                consumable_kg=0.1,
            ),
        )
        self.assertAlmostEqual(result["metrics"]["reaction_impulse_Ns"], 0.74, places=12)
        self.assertAlmostEqual(result["metrics"]["consumable_used_kg"], 0.1, places=12)
        self.assertAlmostEqual(result["metrics"]["final_mass_kg"], 2.0, places=12)


if __name__ == "__main__":
    unittest.main()
