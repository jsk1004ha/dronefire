import json
import unittest

from firelab.analysis import analyze_outcomes, compute_synergy, generate_matrix


def outcome(
    case_id,
    block_id,
    condition_id,
    *,
    event=False,
    event_time_s=None,
    observation_end_s=10.0,
    loss=100.0,
    energy=20.0,
    status="completed",
    evidence="validated_simulation",
    resource=None,
):
    row = {
        "case_id": case_id,
        "block_id": block_id,
        "condition_id": condition_id,
        "run_status": status,
        "observation_end_s": observation_end_s,
        "event": event,
        "event_time_s": event_time_s,
        "loss_J_m2": loss,
        "input_energy_J": energy,
        "provenance": {"evidence_type": evidence, "source": "unit-test fixture"},
    }
    if resource is not None:
        row["resource"] = resource
    return row


def resources(doses, schedule, budget=20.0):
    return {
        "doses": doses,
        "schedule": schedule,
        "budget": {"electrical_energy_J": budget, "payload_kg": 0.0},
    }


class MatrixTests(unittest.TestCase):
    def test_matrix_has_control_five_singles_ten_simultaneous_and_twenty_sequential(self):
        matrix = generate_matrix()
        self.assertEqual(len(matrix), 36)
        self.assertEqual(sum(row["mode"] == "control" for row in matrix), 1)
        self.assertEqual(sum(row["mode"] == "single" for row in matrix), 5)
        self.assertEqual(sum(row["mode"] == "simultaneous" for row in matrix), 10)
        self.assertEqual(sum(row["mode"] == "sequential" for row in matrix), 20)
        self.assertEqual(len({row["id"] for row in matrix}), 36)
        m5_rows = [row for row in matrix if "M5" in row["methods"]]
        self.assertTrue(all("composite candidate" in row["metadata"]["note"] for row in m5_rows))
        json.dumps(matrix, allow_nan=False)


class OutcomeTests(unittest.TestCase):
    def test_all_administratively_censored_has_rmst_tau(self):
        records = [
            outcome("a", "b1", "M1", loss=90),
            outcome("b", "b2", "M1", loss=110),
        ]
        result = analyze_outcomes(records, tau_s=10, bootstrap_samples=40)
        group = result["groups"]["M1"]
        self.assertEqual(group["counts"]["administrative_censor"], 2)
        self.assertEqual(group["rmst_s"], 10.0)
        self.assertEqual(group["success_rate"], 0.0)
        self.assertEqual(group["rmst_ci95_s"], [10.0, 10.0])

    def test_unobserved_and_numerical_failures_are_separate_and_not_imputed(self):
        records = [
            outcome(
                "a", "b1", "M1", status="incomplete", observation_end_s=3,
                loss=None, energy=None,
            ),
            outcome(
                "b", "b2", "M1", status="numerical_failure", observation_end_s=1,
                loss=None, energy=None,
            ),
        ]
        group = analyze_outcomes(records, 10, bootstrap_samples=10)["groups"]["M1"]
        self.assertEqual(group["counts"]["incomplete"], 1)
        self.assertEqual(group["counts"]["numerical_failure"], 1)
        self.assertEqual(group["counts"]["analysis_eligible"], 0)
        self.assertIsNone(group["rmst_s"])
        self.assertIsNone(group["mean_loss_J_m2"])

    def test_early_non_event_completion_is_incomplete_not_administrative_censor(self):
        row = outcome("a", "b1", "M1", observation_end_s=4)
        group = analyze_outcomes([row], 10, bootstrap_samples=10)["groups"]["M1"]
        self.assertEqual(group["counts"]["incomplete"], 1)
        self.assertEqual(group["counts"]["administrative_censor"], 0)

    def test_pairwise_bootstrap_uses_only_common_blocks(self):
        records = [
            outcome("a1", "b1", "A", event=True, event_time_s=2, loss=40),
            outcome("a2", "b2", "A", event=True, event_time_s=4, loss=60),
            outcome("b1", "b1", "B", event=True, event_time_s=5, loss=70),
            outcome("b3", "b3", "B", event=True, event_time_s=8, loss=90),
        ]
        result = analyze_outcomes(records, 10, bootstrap_samples=40, seed=3)
        pair = result["paired_comparisons"][0]
        self.assertEqual(pair["common_blocks"], 1)
        self.assertEqual(pair["rmst_difference_s"], -3.0)
        self.assertEqual(pair["loss_difference_J_m2"], -30.0)

    def test_invalid_numeric_input_fails_closed(self):
        row = outcome("a", "b1", "M1", loss=float("nan"))
        with self.assertRaisesRegex(ValueError, "finite"):
            analyze_outcomes([row], 10)


class SynergyTests(unittest.TestCase):
    def setUp(self):
        self.combo_resource = resources(
            {"M1": {"electrical_energy_J": 10}, "M2": {"pneumatic_energy_J": 10}},
            {"M1": {"start_s": 0, "duration_s": 1}, "M2": {"start_s": 0, "duration_s": 1}},
        )
        self.m1_partial = resources(
            {"M1": {"electrical_energy_J": 10}},
            {"M1": {"start_s": 0, "duration_s": 1}},
        )
        self.m2_partial = resources(
            {"M2": {"pneumatic_energy_J": 10}},
            {"M2": {"start_s": 0, "duration_s": 1}},
        )
        self.control_resource = resources(
            {"C0": {"input_energy_J": 0}},
            {"C0": {"start_s": 0, "duration_s": 0}},
            budget=0,
        )

    def records(self, combo_loss):
        rows = []
        for block, offset in (("b1", 0), ("b2", 2)):
            rows.extend(
                [
                    outcome(f"c-{block}", block, "C0", loss=100 + offset, energy=0, resource=self.control_resource),
                    outcome(f"p1-{block}", block, "M1_HALF", loss=80 + offset, resource=self.m1_partial),
                    outcome(f"p2-{block}", block, "M2_HALF", loss=70 + offset, resource=self.m2_partial),
                    outcome(f"x-{block}", block, "PAIR", loss=combo_loss + offset, resource=self.combo_resource),
                ]
            )
        return rows

    def calculate(self, rows):
        return compute_synergy(
            rows,
            control_id="C0",
            combination_id="PAIR",
            partial_single_ids={"M1": "M1_HALF", "M2": "M2_HALF"},
            bootstrap_samples=40,
        )

    def test_known_positive_additive_synergy(self):
        result = self.calculate(self.records(combo_loss=40))
        self.assertTrue(result["additive_synergy_J_m2"]["eligible"])
        self.assertEqual(result["additive_synergy_J_m2"]["value"], 10.0)

    def test_known_antagonistic_additive_synergy(self):
        result = self.calculate(self.records(combo_loss=60))
        self.assertEqual(result["additive_synergy_J_m2"]["value"], -10.0)

    def test_schedule_mismatch_blocks_additive_calculation(self):
        rows = self.records(combo_loss=40)
        for row in rows:
            if row["condition_id"] == "M1_HALF":
                row["resource"]["schedule"]["M1"]["start_s"] = 1
        result = self.calculate(rows)
        self.assertFalse(result["additive_synergy_J_m2"]["eligible"])
        self.assertIn("matching_partial_dose", result["additive_synergy_J_m2"]["reason"])

    def test_unequal_budget_blocks_practical_gain(self):
        rows = self.records(combo_loss=40)
        for block in ("b1", "b2"):
            rows.append(outcome(f"f1-{block}", block, "M1_FULL", loss=65, energy=19, resource=self.m1_partial))
            rows.append(outcome(f"f2-{block}", block, "M2_FULL", loss=60, energy=20, resource=self.m2_partial))
        result = compute_synergy(
            rows,
            control_id="C0",
            combination_id="PAIR",
            partial_single_ids={"M1": "M1_HALF", "M2": "M2_HALF"},
            equal_budget_single_ids={"M1": "M1_FULL", "M2": "M2_FULL"},
            preselected_single_id="M1_FULL",
            selection_provenance={
                "source": "preregistered design",
                "independent_of_evaluation": True,
            },
            bootstrap_samples=30,
        )
        gain = result["equal_budget_gain_J_m2"]
        self.assertFalse(gain["eligible"])
        self.assertEqual(gain["reason"], "no_blocks_with_equal_budget_and_resources")

    def test_equal_budget_gain_uses_fixed_preselected_single(self):
        rows = self.records(combo_loss=40)
        for block, m1_loss, m2_loss in (("b1", 50, 90), ("b2", 90, 50)):
            rows.append(outcome(f"f1-{block}", block, "M1_FULL", loss=m1_loss, resource=self.combo_resource))
            rows.append(outcome(f"f2-{block}", block, "M2_FULL", loss=m2_loss, resource=self.combo_resource))
        result = compute_synergy(
            rows,
            control_id="C0",
            combination_id="PAIR",
            partial_single_ids={"M1": "M1_HALF", "M2": "M2_HALF"},
            equal_budget_single_ids={"M1": "M1_FULL", "M2": "M2_FULL"},
            preselected_single_id="M1_FULL",
            selection_provenance={
                "source": "independent training blocks",
                "independent_of_evaluation": True,
            },
            bootstrap_samples=30,
        )
        gain = result["equal_budget_gain_J_m2"]
        self.assertTrue(gain["eligible"])
        self.assertEqual(gain["value"], 29.0)
        self.assertEqual(gain["comparator_condition_id"], "M1_FULL")

    def test_equal_budget_gain_requires_independent_preselection(self):
        result = self.calculate(self.records(combo_loss=40))
        gain = result["equal_budget_gain_J_m2"]
        self.assertFalse(gain["eligible"])
        self.assertEqual(gain["reason"], "preselected_single_id_required")

    def test_missing_partial_method_key_does_not_match_none(self):
        rows = self.records(combo_loss=40)
        for row in rows:
            if row["condition_id"] == "M1_HALF":
                row["resource"] = resources(
                    {"OTHER": {"electrical_energy_J": 10}},
                    {"OTHER": {"start_s": 0, "duration_s": 1}},
                )
        result = self.calculate(rows)
        self.assertFalse(result["additive_synergy_J_m2"]["eligible"])
        self.assertEqual(
            result["additive_synergy_J_m2"]["reason"],
            "no_blocks_with_matching_partial_dose_and_schedule",
        )

    def test_empty_resource_sections_fail_closed(self):
        rows = self.records(combo_loss=40)
        rows[0]["resource"]["doses"] = {}
        result = self.calculate(rows)
        self.assertFalse(result["eligible"])
        self.assertTrue(any("resource.doses cannot be empty" in reason for reason in result["ineligible_reasons"]))

    def test_unvalidated_evidence_is_ineligible(self):
        rows = self.records(combo_loss=40)
        rows[0]["provenance"]["evidence_type"] = "unvalidated_physics"
        result = self.calculate(rows)
        self.assertFalse(result["evidence_gate"]["passed"])
        self.assertIn("evidence_gate_failed", result["ineligible_reasons"])


if __name__ == "__main__":
    unittest.main()
