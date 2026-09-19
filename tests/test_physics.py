import json
import math
import unittest

from firelab.physics import simulate_method


class PhysicsContractTests(unittest.TestCase):
    def test_all_methods_follow_json_contract_without_claiming_suppression(self):
        for method_id in ("M1", "M2", "M3", "M4", "M5"):
            with self.subTest(method_id=method_id):
                result = simulate_method({}, method_id)
                json.dumps(result, allow_nan=False)
                self.assertEqual(result["method_id"], method_id)
                self.assertEqual(result["evidence_type"], "unvalidated_physics")
                self.assertEqual(result["suppression"]["status"], "insufficient_evidence")
                self.assertIsNone(result["suppression"]["success_rate"])
                self.assertIsNone(result["suppression"]["extinction_time_s"])
                self.assertLessEqual(len(result["field"]["points"]), 1000)
                self.assertEqual(len(result["field"]["points"]), len(result["field"]["velocity"]))
                self.assertTrue(result["series"])

    def test_acoustic_rms_decays_with_distance_and_preserves_phase_average(self):
        near = simulate_method({"scenario": {"distance_m": 0.25}}, "M1")
        far = simulate_method({"scenario": {"distance_m": 2.0}}, "M1")
        self.assertGreater(near["metrics"]["target_velocity_rms_m_s"], far["metrics"]["target_velocity_rms_m_s"])
        rms = near["metrics"]["target_velocity_rms_m_s"]
        instantaneous = [row["instantaneous_target_velocity_m_s"] for row in near["series"]]
        # Sampled instantaneous values remain bounded by the analytic sqrt(2)*RMS peak.
        self.assertLessEqual(max(abs(v) for v in instantaneous), math.sqrt(2.0) * rms * (1.0 + 1e-12))
        self.assertIn("RMS", " ".join(near["limitations"]))
        self.assertLess(near["reaction_force_N"][0], 0.0)
        self.assertAlmostEqual(
            -near["reaction_force_N"][0],
            near["metrics"]["source_acoustic_power_W"] / (2.0 * 343.0), places=12,
        )
        self.assertGreater(near["metrics"]["vibration_force_rms_N"], 0.0)
        self.assertAlmostEqual(
            near["metrics"]["vibration_force_peak_N"],
            math.sqrt(2.0) * near["metrics"]["vibration_force_rms_N"], places=12,
        )

    def test_acoustic_power_is_bounded_by_device_energy(self):
        result = simulate_method({"methods": {"M1": {"power_W": 0.01, "velocity_rms_m_s": 10.0}}}, "M1")
        metrics = result["metrics"]
        self.assertTrue(metrics["acoustic_power_limited"])
        self.assertLessEqual(metrics["source_acoustic_power_W"], result["device_power_W"])
        self.assertLessEqual(metrics["acoustic_energy_J"], metrics["device_energy_J"])

    def test_vortex_crosswind_deflects_ring_and_reduces_on_axis_peak(self):
        calm = simulate_method({"scenario": {"crosswind_m_s": 0.0, "distance_m": 0.7}}, "M2")
        windy = simulate_method({"scenario": {"crosswind_m_s": 2.0, "distance_m": 0.7}}, "M2")
        self.assertGreater(calm["metrics"]["peak_target_speed_m_s"], windy["metrics"]["peak_target_speed_m_s"])
        self.assertGreater(calm["metrics"]["circulation_m2_s"], 0.0)
        self.assertLessEqual(
            calm["metrics"]["thin_core_kinetic_energy_J_per_ring"],
            calm["metrics"]["slug_kinetic_energy_J_per_pulse"] + 1e-12,
        )
        self.assertAlmostEqual(
            calm["metrics"]["hydrodynamic_impulse_N_s_per_ring"],
            1.204 * math.pi * calm["metrics"]["circulation_m2_s"] * calm["metrics"]["ring_radius_m"] ** 2,
            places=12,
        )
        self.assertLess(calm["reaction_force_N"][0], 0.0)
        self.assertEqual(calm["reaction_force_N"], calm["reaction_pulse"]["peak_force_N"])
        self.assertGreater(
            calm["metrics"]["peak_reaction_force_N"],
            calm["metrics"]["cycle_average_reaction_force_N"],
        )
        self.assertEqual(calm["reaction_pulse"]["steady_force_N"], [0.0, 0.0, 0.0])

    def test_pneumatic_capacity_truncates_unaffordable_vortex_pulses(self):
        result = simulate_method({"methods": {"M2": {"stored_energy_J": 0.0}}}, "M2")
        resource = result["resource_status"]
        self.assertEqual(resource["status"], "insufficient")
        self.assertGreater(resource["requested_pulses"], 0)
        self.assertEqual(resource["simulated_pulses"], 0)
        self.assertGreater(resource["minimum_pneumatic_energy_demand_J"], 0.0)
        self.assertEqual(result["reaction_force_N"], [0.0, 0.0, 0.0])
        self.assertEqual(result["metrics"]["peak_target_speed_m_s"], 0.0)

    def test_water_mass_balance_and_energy_are_conservative(self):
        result = simulate_method({}, "M3")
        metrics = result["metrics"]
        accounted = sum(metrics[k] for k in ("delivered_kg", "evaporated_kg", "deposited_kg", "escaped_kg", "airborne_kg"))
        self.assertAlmostEqual(metrics["emitted_kg"], accounted, places=12)
        self.assertAlmostEqual(metrics["mass_balance_error_kg"], 0.0, places=12)
        self.assertAlmostEqual(metrics["injected_kinetic_energy_J"], 0.5 * metrics["emitted_kg"] * 5.0**2, places=12)
        self.assertAlmostEqual(result["consumable_kg"], metrics["emitted_kg"], places=12)
        self.assertEqual(result["loaded_consumable_kg"], 0.1)
        self.assertLessEqual(metrics["total_ideal_kinetic_energy_J"], metrics["device_energy_J"] + 1e-12)
        self.assertGreaterEqual(metrics["evaporation_latent_heat_demand_J"], 0.0)
        self.assertAlmostEqual(-result['reaction_force_N'][0],
                               metrics['carrier_air_reaction_N']+metrics['mean_particle_reaction_N'])

    def test_particle_and_carrier_exit_speed_is_bounded_when_energy_is_unavailable(self):
        result = simulate_method({"methods": {"M3": {"power_W": 0.0}}}, "M3")
        self.assertEqual(result["resource_status"]["status"], "insufficient")
        self.assertEqual(result["metrics"]["effective_exit_velocity_m_s"], 0.0)
        self.assertEqual(result["metrics"]["injected_kinetic_energy_J"], 0.0)
        self.assertEqual(result["metrics"]["carrier_air_kinetic_energy_J"], 0.0)

    def test_crosswind_changes_water_delivery(self):
        calm = simulate_method({"scenario": {"crosswind_m_s": 0.0}}, "M3")
        windy = simulate_method({"scenario": {"crosswind_m_s": 4.0}}, "M3")
        self.assertGreater(calm["metrics"]["delivered_kg"], windy["metrics"]["delivered_kg"])

    def test_passive_aerosol_conserves_mass_and_has_no_evaporation(self):
        result = simulate_method({}, "M4")
        metrics = result["metrics"]
        self.assertEqual(metrics["evaporated_kg"], 0.0)
        self.assertAlmostEqual(metrics["mass_balance_error_kg"], 0.0, places=12)
        self.assertIn("chemically passive", " ".join(result["limitations"]))
        self.assertEqual(result["loaded_consumable_kg"], 0.05)

    def test_zero_flow_is_finite_and_zero_consumable(self):
        result = simulate_method({"methods": {"M3": {"flow_kg_s": 0.0}}}, "M3")
        json.dumps(result, allow_nan=False)
        self.assertEqual(result["consumable_kg"], 0.0)
        self.assertEqual(result["metrics"]["delivery_fraction"], 0.0)
        self.assertEqual(result["metrics"]["mass_balance_error_kg"], 0.0)

    def test_noninteger_duration_uses_final_partial_timestep(self):
        duration = 0.105
        flow = 0.005
        result = simulate_method({
            "scenario": {"duration_s": duration, "dt_s": 0.02},
            "methods": {"M3": {"flow_kg_s": flow, "payload_kg": 1.0}},
        }, "M3")
        self.assertAlmostEqual(result["series"][-1]["time_s"], duration, places=12)
        self.assertAlmostEqual(result["metrics"]["emitted_kg"], flow * duration, places=12)

    def test_m5_cv_does_not_invent_electric_force(self):
        result = simulate_method({}, "M5")
        self.assertEqual(result["metrics"]["ehd_body_acceleration_m_s2"], 0.0)
        self.assertEqual(result["metrics"]["ehd_velocity_increment_m_s"], 0.0)
        self.assertIn("zero default electric inputs", " ".join(result["limitations"]))
        self.assertEqual(result["loaded_consumable_kg"], 0.05)
        self.assertEqual(result["reaction_pulse"]["steady_force_N"], [0.0, 0.0, 0.0])

    def test_m5_pneumatic_capacity_limits_both_rings_and_particle_launch(self):
        result = simulate_method({"methods": {"M5": {"stored_energy_J": 0.0}}}, "M5")
        self.assertEqual(result["resource_status"]["status"], "insufficient")
        self.assertEqual(result["resource_status"]["simulated_pulses"], 0)
        self.assertEqual(result["consumable_kg"], 0.0)
        self.assertEqual(result["metrics"]["simulated_pneumatic_energy_J"], 0.0)
        self.assertEqual(result["reaction_pulse"]["peak_jet_force_N"], [0.0, 0.0, 0.0])
        # Full cartridge still contributes to takeoff mass even though none can be launched.
        self.assertEqual(result["loaded_consumable_kg"], 0.05)

    def test_m5_ehd_requires_fields_and_uses_supplied_body_force(self):
        with self.assertRaisesRegex(ValueError, "requires nonzero"):
            simulate_method({"methods": {"M5": {"variant": "EHD"}}}, "M5")
        result = simulate_method({"methods": {"M5": {
            "variant": "EHD", "charge_density_C_m3": 1e-6, "electric_field_V_m": 2e5,
        }}}, "M5")
        self.assertGreater(result["metrics"]["ehd_body_acceleration_m_s2"], 0.0)
        self.assertGreater(result["metrics"]["ehd_velocity_increment_m_s"], 0.0)
        self.assertIn("unvalidated", " ".join(result["limitations"]))
        self.assertLess(result["reaction_pulse"]["steady_force_N"][0], 0.0)
        self.assertLess(
            result["reaction_pulse"]["peak_force_N"][0],
            result["reaction_pulse"]["peak_jet_force_N"][0],
        )

    def test_invalid_inputs_fail_closed(self):
        for config, method_id in (
            ({"scenario": {"dt_s": 0.0}}, "M1"),
            ({"methods": {"M2": {"pulse_duration_s": 2.0, "period_s": 1.0}}}, "M2"),
            ({"methods": {"M3": {"diameter_um": float("nan")}}}, "M3"),
        ):
            with self.subTest(config=config, method_id=method_id):
                with self.assertRaises(ValueError):
                    simulate_method(config, method_id)


if __name__ == "__main__":
    unittest.main()
