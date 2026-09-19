import unittest
from firelab.config import validate_config

class ConfigurationTests(unittest.TestCase):
    def test_no_mutable_default_leak(self):
        first = validate_config()
        first['scenario']['distance_m'] = 2
        self.assertEqual(validate_config()['scenario']['distance_m'], 1)

    def test_reject_nonfinite_bool_unknown(self):
        for obj in [{'scenario': {'distance_m': float('nan')}},
                    {'scenario': {'duration_s': True}}, {'shell': 'anything'},
                    {'methods': {'M5': {'variant': 'magic'}}}]:
            with self.subTest(obj=obj), self.assertRaises(ValueError):
                validate_config(obj)

    def test_duration_bounds_and_pulse(self):
        with self.assertRaises(ValueError):
            validate_config({'methods': {'M2': {'pulse_duration_s': .5, 'period_s': .1}}})
        with self.assertRaises(ValueError):
            validate_config({'scenario': {'duration_s': 10000}})

if __name__ == '__main__':
    unittest.main()
