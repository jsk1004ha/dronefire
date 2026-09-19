import unittest
from firelab.acoustics import plane_wave


class AcousticTests(unittest.TestCase):
    def test_plane_wave_second_order(self):
        coarse, fine = plane_wave(64), plane_wave(128)
        self.assertGreater(coarse['relative_L2']/fine['relative_L2'],3.7)
        self.assertLess(fine['relative_L2'],.002)
        self.assertAlmostEqual(fine['pressure_rms_Pa'],fine['expected_pressure_rms_Pa'],places=4)

    def test_unstable_CFL_rejected(self):
        with self.assertRaises(ValueError):
            plane_wave(courant=1.1)
