import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from firelab.ehd import EHDInputError, simulate_ehd, verification


class EHDTests(unittest.TestCase):
    def test_default_run_is_finite_positive_and_charge_conservative(self):
        result = simulate_ehd()
        self.assertEqual(result["status"], "computed_numerical_model_only")
        self.assertTrue(result["numerics"]["positivity_preserved"])
        self.assertLess(result["charge_ledger"]["relative_residual"], 1.0e-12)
        self.assertTrue(np.isfinite(result["profiles"]["potential_node_V"]).all())
        self.assertFalse(result.get("suppression_verified", False))

        fast_steps = simulate_ehd(
            {"voltage_V": 100_000.0, "duration_s": 0.002, "dt_max_s": 0.001, "max_saved_frames": 5}
        )
        self.assertLessEqual(len(fast_steps["series"]), 5)

    def test_charge_free_solution_is_linear_and_has_no_force(self):
        result = simulate_ehd(
            {
                "injected_charge_density_C_m3": 0.0,
                "initial_charge_density_C_m3": 0.0,
                "duration_s": 0.01,
            }
        )
        potential = np.asarray(result["profiles"]["potential_node_V"])
        x = np.asarray(result["grid"]["node_x_m"])
        np.testing.assert_allclose(potential, 10.0 * (1.0 - x / 0.1), atol=1.0e-11, rtol=0.0)
        self.assertAlmostEqual(result["metrics"]["electric_force_N_m2"], 0.0)
        self.assertAlmostEqual(result["metrics"]["electric_force_acceleration_scale_m_s2"], 0.0)
        self.assertNotIn("gas_acceleration_upper_bound_m_s2", result["metrics"])

    def test_charge_ledger_matches_boundary_flux_with_diffusion(self):
        result = simulate_ehd(
            {
                "injected_charge_density_C_m3": 2.0e-10,
                "initial_charge_density_C_m3": 1.0e-11,
                "charge_diffusion_m2_s": 2.0e-5,
                "duration_s": 0.05,
            }
        )
        ledger = result["charge_ledger"]
        self.assertAlmostEqual(
            ledger["final_charge_C_m2"] - ledger["initial_charge_C_m2"],
            ledger["net_boundary_charge_entered_C_m2"],
            delta=1.0e-24,
        )

    def test_voltage_reversal_changes_force_direction(self):
        positive = simulate_ehd(
            {
                "initial_charge_density_C_m3": 1.0e-12,
                "injected_charge_density_C_m3": 1.0e-12,
                "charge_diffusion_m2_s": 0.0,
                "duration_s": 0.001,
            }
        )
        negative = simulate_ehd(
            {
                "voltage_V": -10.0,
                "initial_charge_density_C_m3": 1.0e-12,
                "injected_charge_density_C_m3": 1.0e-12,
                "charge_diffusion_m2_s": 0.0,
                "duration_s": 0.001,
            }
        )
        self.assertGreater(positive["metrics"]["electric_force_N_m2"], 0)
        self.assertLess(negative["metrics"]["electric_force_N_m2"], 0)

    def test_unknown_nonfinite_and_excessive_inputs_fail_closed(self):
        for config in ({"unknown": 1}, {"voltage_V": float("nan")}, {"cells": 7}):
            with self.subTest(config=config), self.assertRaises(EHDInputError):
                simulate_ehd(config)

    def test_verification_proves_analytic_conservation_and_refinement_gates(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = verification(temporary)
            self.assertEqual(result["status"], "passed")
            self.assertTrue(all(result["checks"].values()))
            self.assertGreater(min(result["spatial_refinement"]["observed_orders"][-2:]), 1.8)
            errors = result["temporal_refinement"]["l1_errors_vs_finest_C_m3"]
            self.assertLess(errors[1], errors[0])
            saved = json.loads((Path(temporary) / "ehd_verification.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "passed")


if __name__ == "__main__":
    unittest.main()
