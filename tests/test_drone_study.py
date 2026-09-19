import json
import tempfile
import unittest
from pathlib import Path

from firelab.drone import simulate_mission
from firelab.drone_study import run_drone_study, write_drone_study_exports


def compact_config():
    return {
        "scenario": {"duration_s": 0.2, "dt_s": 0.02, "distance_m": 0.2, "crosswind_m_s": 0.0, "seed": 7},
        "drone": {
            "approach_s": 0.1,
            "return_s": 0.1,
            "battery_Wh": 20.0,
            "payload_capacity_kg": 2.0,
            "tracking_tolerance_m": 10.0,
        },
    }


def method():
    return {
        "method_id": "M3",
        "reaction_force_N": [-2.0, 0.0, 0.0],
        "device_power_W": 35.0,
        "device_mass_kg": 0.5,
        "consumable_kg": 0.02,
        "loaded_consumable_kg": 0.10,
        "material_ids": ["water:test-batch"],
        "metrics": {"simulated_pneumatic_energy_J": 0.0},
    }


def matched_losses(*, mismatch=False, weak=False):
    values = {"D0": 100.0, "D1": 60.0, "D2": 110.0, "D3": 80.0, "D4": 70.0}
    records = []
    for condition, loss in values.items():
        match = {
            "distance_m": 0.2,
            "start_time_s": 0.0,
            "observation_window_s": 0.2,
            "budget": {"electrical_energy_J": 7.0},
            "material_ids": ["water:test-batch"],
        }
        if mismatch and condition == "D4":
            match["material_ids"] = ["water:other-batch"]
        records.append({
            "method_id": "M3",
            "block_id": "B1",
            "condition_id": condition,
            "loss_J_m2": loss,
            "match": match,
            "provenance": {"evidence_type": "unvalidated_physics" if weak else "experimental"},
        })
    return records


class DroneStudyTests(unittest.TestCase):
    def test_generates_d0_d5_and_keeps_fire_effect_null_without_import(self):
        result = run_drone_study(compact_config(), [method()])
        study = result["methods"]["M3"]
        self.assertEqual(set(study["conditions"]), {"D0", "D1", "D2", "D3", "D4"})
        self.assertEqual(set(study["D5"]), {"crosswind", "sensor_degraded", "payload_high", "thermal_screen", "combined"})
        self.assertIsNone(study["conditions"]["D1"]["fire_loss_J_m2"])
        self.assertFalse(study["fire_retention"]["eligible"])
        self.assertEqual(study["thermal_assessment_status"], "insufficient_evidence")
        self.assertEqual(study["practical_effectiveness_status"], "insufficient_evidence")
        self.assertEqual(study["wake"]["validation_status"], "unvalidated_analytical_screening")
        self.assertIsNone(study["wake"]["local_velocity_field"])
        self.assertIsInstance(json.dumps(result, allow_nan=False), str)

    def test_matched_imported_losses_compute_retention_and_net_effect(self):
        result = run_drone_study(compact_config(), [method()], matched_losses())
        retention = result["methods"]["M3"]["fire_retention"]
        self.assertTrue(retention["eligible"])
        self.assertAlmostEqual(retention["R_D3"], 0.75)
        self.assertAlmostEqual(retention["R_D4"], 1.0)
        self.assertAlmostEqual(retention["net_D3_J_m2"], 20.0)
        self.assertAlmostEqual(retention["net_D4_J_m2"], 30.0)
        self.assertEqual(retention["ci95"]["R_D4"], [1.0, 1.0])

    def test_budget_or_material_mismatch_and_weak_evidence_are_rejected(self):
        mismatch = run_drone_study(compact_config(), [method()], matched_losses(mismatch=True))
        self.assertFalse(mismatch["methods"]["M3"]["fire_retention"]["eligible"])
        self.assertIn("budget_or_material_mismatch", mismatch["methods"]["M3"]["fire_retention"]["reason"])
        weak = run_drone_study(compact_config(), [method()], matched_losses(weak=True))
        self.assertEqual(weak["methods"]["M3"]["fire_retention"]["reason"], "evidence_gate_failed")

    def test_sensor_error_is_seeded_and_mount_geometry_updates_cg_and_torque(self):
        config = compact_config()
        config["sensor"] = {
            "sample_rate_Hz": 5.0,
            "latency_s": 0.1,
            "position_error_std_m": 0.05,
            "velocity_error_std_m_s": 0.02,
            "availability_fraction": 0.75,
            "seed": 123,
        }
        config["drone"].update({
            "airframe_cg_m": [0.0, 0.0, 0.0],
            "device_mount_position_m": [0.2, 0.0, -0.1],
            "consumable_position_m": [0.2, 0.0, -0.1],
        })
        first = simulate_mission(config, method(), controller_enabled=True)
        second = simulate_mission(config, method(), controller_enabled=True)
        self.assertEqual(first["metrics"]["sensor_updates"], second["metrics"]["sensor_updates"])
        self.assertEqual(first["metrics"]["max_sensor_position_error_m"], second["metrics"]["max_sensor_position_error_m"])
        self.assertGreater(first["metrics"]["peak_reaction_torque_Nm"], 0.0)
        self.assertIsNotNone(first["metrics"]["initial_cg_m"])
        self.assertGreater(first["metrics"]["cg_shift_m"], 0.0)

    def test_requirements_include_actual_sweep_outputs(self):
        result = run_drone_study(compact_config(), [method()])
        requirements = result["methods"]["M3"]["requirements"]
        for factor in (
            "crosswind_m_s", "sensor_latency_s", "payload_capacity_kg", "max_thrust_N",
            "max_power_W", "battery_Wh", "reaction_lever_arm_m", "incident_flux_W_m2",
        ):
            self.assertGreaterEqual(len(requirements[factor]), 4)
            self.assertIn("status", requirements[factor][0])
        self.assertGreater(requirements["analytical_requirements"][0]["payload_required_kg"], 0.0)

    def test_exports_json_and_flat_csv_arrays(self):
        result = run_drone_study(compact_config(), [method()])
        with tempfile.TemporaryDirectory() as directory:
            paths = write_drone_study_exports(result, directory)
            self.assertEqual(set(paths), {"json", "feasibility_csv", "mission_series_csv", "requirements_csv"})
            for path in paths.values():
                self.assertTrue(Path(path).is_file())
                self.assertGreater(Path(path).stat().st_size, 20)


if __name__ == "__main__":
    unittest.main()
