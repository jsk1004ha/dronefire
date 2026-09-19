"""Tests for multi-objective optimization module."""
import unittest
from firelab.optimizer import evaluate_point, find_pareto_front, run_optimization

class TestOptimizer(unittest.TestCase):
    def test_evaluate_point_m1(self):
        res = evaluate_point("M1", distance_m=1.0, power_W=50.0, crosswind_m_s=0.5)
        self.assertEqual(res["method_id"], "M1")
        self.assertIn("extinction_time_s", res["objectives"])
        self.assertIn("mission_energy_Wh", res["objectives"])
        self.assertIn("max_position_error_m", res["objectives"])
        self.assertIn("delivery_efficiency_pct", res["objectives"])
        self.assertGreater(res["objectives"]["extinction_time_s"], 0)
        self.assertGreater(res["objectives"]["mission_energy_Wh"], 0)
        
    def test_pareto_front_filtering(self):
        candidates = [
            {"objectives": {"extinction_time_s": 5.0, "mission_energy_Wh": 10.0, "max_position_error_m": 0.2, "delivery_efficiency_pct": 80.0}},
            {"objectives": {"extinction_time_s": 8.0, "mission_energy_Wh": 15.0, "max_position_error_m": 0.4, "delivery_efficiency_pct": 60.0}}, # dominated by #1
            {"objectives": {"extinction_time_s": 3.0, "mission_energy_Wh": 20.0, "max_position_error_m": 0.3, "delivery_efficiency_pct": 75.0}}, # trade-off
        ]
        front = find_pareto_front(candidates)
        self.assertEqual(len(front), 2)
        self.assertEqual(front[0]["objectives"]["extinction_time_s"], 5.0)
        self.assertEqual(front[1]["objectives"]["extinction_time_s"], 3.0)
        
    def test_run_optimization_quick(self):
        spec = {
            "methods": ["M1", "M3"],
            "distance_range": [1.0, 1.5],
            "power_range": [30.0, 60.0],
            "crosswind_m_s": 1.0,
            "kp_range": [1.0]
        }
        res = run_optimization(spec)
        self.assertEqual(res["status"], "success")
        self.assertGreater(res["total_evaluated"], 0)
        self.assertGreater(res["pareto_front_count"], 0)
        self.assertIsNotNone(res["knee_point"])

if __name__ == "__main__":
    unittest.main()
