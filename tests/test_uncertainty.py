"""Tests for uncertainty quantification module."""
import unittest
from firelab.uncertainty import run_monte_carlo

class TestUncertainty(unittest.TestCase):
    def test_run_monte_carlo_quick(self):
        res = run_monte_carlo(method_id="M3", num_samples=25, seed=123)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["num_samples"], 25)
        self.assertIn("extinction_probability", res)
        self.assertTrue(0.0 <= res["extinction_probability"] <= 1.0)
        self.assertEqual(len(res["ci_95_pct"]), 2)
        self.assertLessEqual(res["ci_95_pct"][0], res["ci_95_pct"][1])
        
        hist = res["histograms"]
        self.assertIn("extinction_time_s", hist)
        self.assertIn("max_position_error_m", hist)
        self.assertIn("mission_energy_Wh", hist)
        
        tornado = res["sensitivity_tornado"]
        self.assertGreater(len(tornado), 0)
        self.assertIn("combined_impact", tornado[0])

if __name__ == "__main__":
    unittest.main()
