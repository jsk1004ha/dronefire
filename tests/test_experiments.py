import unittest
from firelab.experiments import build_design, resource_ledger


class ExperimentTests(unittest.TestCase):
    def test_all_pairs_have_exact_partial_controls(self):
        design = build_design(6, 4, .4)
        by_id = {row['id']: row for row in design}
        self.assertEqual(sum(r['metadata']['main_design'] for r in design), 36)
        self.assertEqual(len(by_id), len(design))
        self.assertGreater(len(design), 36)
        for row in design[6:36]:
            for mid, cid in row['partial_controls'].items():
                self.assertEqual(row['schedule'][mid], by_id[cid]['schedule'][mid])
                self.assertEqual(row['dose_fraction'][mid], by_id[cid]['dose_fraction'][mid])
        for row in design[16:36]:
            first, second = row['methods']
            self.assertAlmostEqual(row['schedule'][second]['start_s'] + row['schedule'][second]['duration_s'], 10)

    def test_no_shared_component_or_material_doublecount(self):
        a = {'component_id': 'tank', 'mass_kg': 1., 'pneumatic_energy_J': 100.}
        b = {'component_id': 'mist', 'consumables_kg': {'water': .1}}
        c = {'component_id': 'aerosol', 'consumables_kg': {'agent_unknown': .1}}
        result = resource_ledger([a, a, b, c])
        self.assertEqual(result['pneumatic_energy_J'], 100)
        self.assertEqual(len(result['consumables_kg']), 2)
        with self.assertRaises(ValueError):
            resource_ledger([a, {**a, 'mass_kg': 2}])

    def test_invalid_timing(self):
        with self.assertRaises(ValueError):
            build_design(duration_s=4, transition_delay_s=4)
