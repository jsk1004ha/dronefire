import unittest

from firelab.exposure import analyze_exposure_run, integrate_exposure, summarize_exposure


PROVENANCE = {"source": "synthetic unit-test fixture", "evidence_type": "synthetic_test"}
CRITERIA = {
    "temperature_C": {"limit": 60, "direction": "above", "source": "synthetic test threshold"},
    "visibility_m": {"limit": 5, "direction": "below", "source": "synthetic test threshold"},
}


def exposure(condition="C0", block="b1", temperature=None, visibility=None, end=5):
    channels = {
        "temperature_C": temperature or [20, 30, 50, 70, 80, 90][: end + 1],
        "visibility_m": visibility or [20, 15, 10, 4, 3, 2][: end + 1],
        "heat_flux_kW_m2": [2] * (end + 1),
    }
    return {
        "case_id": f"{block}-{condition}",
        "block_id": block,
        "condition_id": condition,
        "location_id": "protected-1",
        "run_status": "completed",
        "time_s": list(range(end + 1)),
        "channels": channels,
        "provenance": dict(PROVENANCE),
    }


class ExposureRunTests(unittest.TestCase):
    def test_crossing_is_interval_censored(self):
        result = analyze_exposure_run(exposure(), CRITERIA, 5)
        self.assertEqual(result["channels"]["temperature_C"]["interval_s"], [2.0, 3.0])
        self.assertEqual(result["channels"]["visibility_m"]["interval_s"], [2.0, 3.0])
        self.assertEqual(result["integrated_heat_exposure_J_m2"], 10000.0)

    def test_missing_channel_is_incomplete_not_zero(self):
        row = exposure()
        row["channels"].pop("visibility_m")
        result = analyze_exposure_run(row, CRITERIA, 5)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["channels"]["visibility_m"]["status"], "incomplete_missing_channel")

    def test_short_followup_is_incomplete(self):
        row = exposure(end=3, temperature=[20, 20, 20, 20], visibility=[20, 20, 20, 20])
        result = analyze_exposure_run(row, CRITERIA, 5)
        self.assertEqual(result["channels"]["temperature_C"]["status"], "incomplete_followup")
        self.assertIsNone(result["integrated_heat_exposure_J_m2"])

    def test_no_crossing_through_tau_is_right_censored(self):
        row = exposure(temperature=[20] * 6, visibility=[20] * 6)
        result = analyze_exposure_run(row, CRITERIA, 5)
        self.assertEqual(result["channels"]["temperature_C"]["interval_s"], [5.0, None])

    def test_integral_does_not_extrapolate(self):
        self.assertIsNone(integrate_exposure([0, 1, 2], [1, 1, 1], 3))


class ExposureSummaryTests(unittest.TestCase):
    def test_rmst_interval_and_paired_difference(self):
        records = []
        for block in ("b1", "b2"):
            records.append(exposure("C0", block))
            records.append(exposure(
                "M1", block,
                temperature=[20, 20, 30, 40, 50, 70],
                visibility=[20, 20, 15, 10, 8, 4],
            ))
        result = summarize_exposure(records, CRITERIA, 5, bootstrap_samples=20, seed=1)
        control = result["groups"]["temperature_C"]["C0"]
        method = result["groups"]["temperature_C"]["M1"]
        self.assertEqual(control["rmst_interval_s"], [2.0, 3.0])
        self.assertEqual(method["rmst_interval_s"], [4.0, 5.0])
        comparison = next(
            item for item in result["paired_rmst_differences"]
            if item["channel"] == "temperature_C" and item["method"] == "M1"
        )
        self.assertEqual(comparison["difference_interval_s"], [1.0, 3.0])

    def test_missing_required_provenance_fails(self):
        row = exposure()
        row["provenance"] = {}
        with self.assertRaisesRegex(ValueError, "provenance"):
            summarize_exposure([row], CRITERIA, 5, bootstrap_samples=5)

    def test_multiple_locations_are_not_overwritten(self):
        first = exposure("C0", "b1")
        second = exposure("C0", "b1")
        second["case_id"] = "other-location"
        second["location_id"] = "protected-2"
        result = summarize_exposure([first, second], CRITERIA, 5, bootstrap_samples=5)
        self.assertEqual(set(result["locations"]), {"protected-1", "protected-2"})
        self.assertIsNone(result["groups"])


if __name__ == "__main__":
    unittest.main()
