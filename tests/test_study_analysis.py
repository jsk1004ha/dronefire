import unittest

from firelab.study_analysis import (
    analyze_extinction_run,
    analyze_order_effects,
    analyze_study,
    evaluate_environment_policy,
    integrate_hrr_decrease,
    latin_hypercube,
    pareto_front,
    split_cases,
)


PROVENANCE = {"source": "synthetic unit-test fixture", "evidence_type": "synthetic_test"}
CRITERION = {
    "hrr_threshold_kW": 1.0,
    "sustain_s": 2.0,
    "reignition_threshold_kW": 2.0,
    "reignition_followup_s": 3.0,
}


def series(condition="M1", block="b1", hrr=None, heat=None, end=8, **extra):
    time = list(range(end + 1))
    channels = {"hrr_kW": hrr or [10, 8, 0.5, 0.4, 0.3, 0.2, 0.1, 0.1, 0.1][: end + 1]}
    if heat is not None:
        channels["heat_flux_kW_m2"] = heat
    return {
        "case_id": f"{block}-{condition}",
        "block_id": block,
        "condition_id": condition,
        "run_status": "completed",
        "time_s": time,
        "channels": channels,
        "input_energy_J": 10 if condition != "C0" else 0,
        "intervention_end_s": 4,
        "provenance": dict(PROVENANCE),
        **extra,
    }


class ExtinctionTests(unittest.TestCase):
    def test_sustained_extinction_and_no_reignition(self):
        result = analyze_extinction_run(series(), CRITERION)
        self.assertEqual(result["extinction"]["time_s"], 2.0)
        self.assertEqual(result["reignition"]["status"], "not_observed")

    def test_brief_dip_does_not_count(self):
        row = series(hrr=[10, 0.5, 5, 4, 3, 2, 2, 2, 2])
        result = analyze_extinction_run(row, CRITERION)
        self.assertFalse(result["extinction"]["event"])

    def test_reignition_is_unknown_when_followup_is_short(self):
        row = series(end=5, hrr=[10, 8, 0.5, 0.4, 0.3, 0.2])
        result = analyze_extinction_run(row, CRITERION)
        self.assertEqual(result["reignition"]["status"], "unknown_insufficient_followup")

    def test_observed_reignition(self):
        row = series(hrr=[10, 8, 0.5, 0.4, 0.3, 3, 4, 4, 4])
        result = analyze_extinction_run(row, CRITERION)
        self.assertEqual(result["reignition"]["time_s"], 5.0)

    def test_missing_provenance_rejected(self):
        row = series()
        row.pop("provenance")
        with self.assertRaisesRegex(ValueError, "provenance"):
            analyze_extinction_run(row, CRITERION)


class IntegrationTests(unittest.TestCase):
    def test_hrr_integrates_only_common_window(self):
        control = series("C0", hrr=[10] * 9)
        method = series("M1", hrr=[5] * 9)
        result = integrate_hrr_decrease(method, control, start_s=2, end_s=6)
        self.assertEqual(result["window_s"], [2.0, 6.0])
        self.assertEqual(result["decrease_fraction"], 0.5)
        self.assertFalse(result["extrapolated"])

    def test_no_overlap_is_ineligible(self):
        method = series()
        method["time_s"] = [20, 21]
        method["channels"]["hrr_kW"] = [1, 1]
        control = series("C0")
        result = integrate_hrr_decrease(method, control)
        self.assertFalse(result["eligible"])

    def test_pipeline_marks_missing_heat_channel_incomplete(self):
        records = [series("C0"), series("M1")]
        prereg = {"control_id": "C0", "tau_s": 8, "extinction": CRITERION}
        result = analyze_study(records, prereg, bootstrap_samples=10)
        self.assertEqual(result["outcomes"]["groups"]["M1"]["counts"]["incomplete"], 1)
        self.assertIsNotNone(result["extinction_runs"][1]["extinction"]["time_s"])

    def test_pipeline_with_heat_channel_is_eligible(self):
        control = series("C0", hrr=[10] * 9, heat=[4] * 9)
        method = series("M1", heat=[2] * 9)
        result = analyze_study(
            [control, method],
            {"control_id": "C0", "tau_s": 8, "extinction": CRITERION},
            bootstrap_samples=10,
        )
        self.assertEqual(result["outcomes"]["groups"]["M1"]["mean_loss_J_m2"], 16000.0)

    def test_missing_energy_preserves_physics_but_blocks_energy_outcome(self):
        control = series("C0", hrr=[10] * 9, heat=[4] * 9)
        method = series("M1", heat=[2] * 9)
        method.pop("input_energy_J")
        result = analyze_study(
            [control, method],
            {"control_id": "C0", "tau_s": 8, "extinction": CRITERION},
            bootstrap_samples=10,
        )
        self.assertEqual(result["extinction_runs"][1]["status"], "complete")
        self.assertTrue(result["hrr_reductions"][0]["eligible"])
        self.assertEqual(result["outcomes"]["groups"]["M1"]["counts"]["incomplete"], 1)
        self.assertEqual(result["incomplete_outcomes"][0]["missing"], ["input_energy_J"])
        extinction = result["extinction_statistics"]
        self.assertEqual(extinction["groups"]["M1"]["rmst_s"], 2.0)
        self.assertEqual(extinction["groups"]["M1"]["counts"]["events"], 1)
        self.assertFalse(extinction["energy_required"])
        comparison = extinction["paired_comparisons"][0]
        self.assertEqual(comparison["rmst_difference_s"], 6.0)
        self.assertEqual(comparison["precision_warning"], "fewer_than_3_common_blocks")

    def test_synergy_result_retains_combination_identity_when_gate_blocks(self):
        control = series("C0", hrr=[10] * 9, heat=[4] * 9)
        combo = series("PAIR", heat=[1] * 9)
        left = series("M1_HALF", heat=[2] * 9)
        right = series("M2_HALF", heat=[3] * 9)
        result = analyze_study(
            [control, combo, left, right],
            {"control_id": "C0", "tau_s": 8, "extinction": CRITERION},
            synergy_specs=[{
                "control_id": "C0",
                "combination_id": "PAIR",
                "partial_single_ids": {"M1": "M1_HALF", "M2": "M2_HALF"},
            }],
            bootstrap_samples=10,
        )
        synergy = result["synergy"][0]
        self.assertEqual(synergy["combination_id"], "PAIR")
        self.assertEqual(synergy["partial_single_ids"], {"M1": "M1_HALF", "M2": "M2_HALF"})
        self.assertEqual(synergy["analysis_spec"]["control_id"], "C0")


class ComparisonTests(unittest.TestCase):
    def test_order_effect_and_holm_adjustment(self):
        records = []
        for block, left, right in (("b1", 8, 5), ("b2", 7, 4), ("b3", 9, 5)):
            records += [
                {"block_id": block, "order": ["M1", "M2"], "loss": left, "provenance": PROVENANCE},
                {"block_id": block, "order": ["M2", "M1"], "loss": right, "provenance": PROVENANCE},
            ]
        result = analyze_order_effects(records, metric="loss", bootstrap_samples=20, permutation_samples=100, seed=1)
        test = result["tests"][0]
        self.assertTrue(test["eligible"])
        self.assertLess(test["difference"], 0)
        self.assertIsNotNone(test["p_value_holm"])

    def test_pareto_front_and_incomplete_rows(self):
        records = [
            {"id": "a", "loss": 1, "energy": 10, "provenance": PROVENANCE},
            {"id": "b", "loss": 2, "energy": 20, "provenance": PROVENANCE},
            {"id": "c", "loss": None, "energy": 5, "provenance": PROVENANCE},
        ]
        result = pareto_front(records, {"loss": "min", "energy": "min"})
        self.assertEqual([row["record"]["id"] for row in result["front"]], ["a"])
        self.assertEqual(len(result["incomplete"]), 1)


class DesignTests(unittest.TestCase):
    def test_lhs_is_deterministic_and_one_sample_per_stratum(self):
        a = latin_hypercube({"wind": [0, 1]}, 8, seed=7)
        b = latin_hypercube({"wind": [0, 1]}, 8, seed=7)
        self.assertEqual(a, b)
        strata = sorted(int(row["wind"] * 8) for row in a)
        self.assertEqual(strata, list(range(8)))

    def test_case_split_has_no_leakage(self):
        records = [
            {"case_id": f"c{i}", "condition_id": condition, "provenance": PROVENANCE}
            for i in range(8) for condition in ("M1", "M2")
        ]
        split = split_cases(records, 0.25, seed=3)
        self.assertFalse(set(split["train_case_ids"]) & set(split["holdout_case_ids"]))

    def test_policy_is_frozen_from_training_cases(self):
        records = []
        for case in range(12):
            for condition, value in (("M1", 1.0), ("M2", 5.0)):
                records.append({
                    "case_id": f"c{case}", "condition_id": condition,
                    "wind_bin": "low", "loss": value + case / 100,
                    "provenance": PROVENANCE,
                })
        result = evaluate_environment_policy(
            records, environment_fields=["wind_bin"], metric="loss",
            holdout_fraction=0.25, seed=2,
        )
        self.assertEqual(result["policy"][0]["condition_id"], "M1")
        self.assertTrue(result["holdout_evaluated"])
        self.assertFalse(result["missing_selected_condition"])


if __name__ == "__main__":
    unittest.main()
