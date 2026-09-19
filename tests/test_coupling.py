import unittest

import numpy as np

from firelab.coupling import (
    CouplingError,
    build_exchange_bundle,
    conservative_remap,
    convert_units,
    interpolate_time,
    remap_exchange_bundle,
    transform_points,
)


GRID = {"x": [0, 1, 2], "y": [0, 1, 2], "z": [0, 1, 2]}


class CouplingTests(unittest.TestCase):
    def test_identity_map_is_exact(self):
        source = np.arange(8, dtype=float).reshape(2, 2, 2)
        result = conservative_remap(source, GRID, GRID)
        np.testing.assert_array_equal(result["values"], source)
        self.assertEqual(result["integral_error"], 0.0)
        self.assertTrue(result["whole_source_domain_covered"])
        self.assertFalse(result["extrapolated"])

    def test_coarsening_preserves_integral(self):
        source = np.arange(1, 9, dtype=float).reshape(2, 2, 2)
        coarse = {"x": [0, 2], "y": [0, 2], "z": [0, 2]}
        result = conservative_remap(source, GRID, coarse)
        self.assertAlmostEqual(result["values"][0, 0, 0], source.mean())
        self.assertAlmostEqual(result["target_integral"], float(source.sum()))

    def test_out_of_domain_target_is_rejected(self):
        outside = {"x": [-0.1, 1], "y": [0, 1], "z": [0, 1]}
        with self.assertRaisesRegex(CouplingError, "extrapolation"):
            conservative_remap(np.ones((2, 2, 2)), GRID, outside)

    def test_time_interpolation_and_no_extrapolation(self):
        values = np.array([[0.0, 2.0], [2.0, 4.0]])
        np.testing.assert_allclose(interpolate_time([0, 2], values, 1), [1, 3])
        with self.assertRaisesRegex(CouplingError, "extrapolation"):
            interpolate_time([0, 2], values, 3)

    def test_units_and_right_handed_coordinate_transform(self):
        np.testing.assert_allclose(convert_units([0, 100], "C", "K"), [273.15, 373.15])
        source = {"type": "right_handed_cartesian", "units": "m", "origin_m": [1, 0, 0], "basis": np.eye(3)}
        target = {"type": "right_handed_cartesian", "units": "m", "origin_m": [0, 0, 0], "basis": np.eye(3)}
        np.testing.assert_allclose(transform_points([[0, 2, 3]], source, target), [[1, 2, 3]])

    def test_exchange_separates_state_and_rejects_heat_double_count(self):
        shape = (2, 2, 2)
        bundle = build_exchange_bundle(
            time_s=1.0,
            grid_edges_m=GRID,
            mass_density_kg_m3=np.ones(shape),
            momentum_density_kg_m2_s=np.zeros(shape + (3,)),
            sensible_enthalpy_density_J_m3=np.full(shape, 5.0),
            metadata={"source": "test"},
        )
        self.assertEqual(set(bundle["variables"]), {"mass_density", "momentum_density", "sensible_enthalpy_density"})
        self.assertFalse(bundle["two_way_coupling_claimed"])
        with self.assertRaisesRegex(CouplingError, "heat release"):
            build_exchange_bundle(
                time_s=1.0,
                grid_edges_m=GRID,
                mass_density_kg_m3=np.ones(shape),
                momentum_density_kg_m2_s=np.zeros(shape + (3,)),
                sensible_enthalpy_density_J_m3=np.ones(shape),
                metadata={"replace_combustion_heat_source": True},
            )

    def test_bundle_remap_conserves_all_vector_components(self):
        shape = (2, 2, 2)
        momentum = np.stack([np.ones(shape), np.full(shape, 2), np.full(shape, 3)], axis=-1)
        bundle = build_exchange_bundle(
            time_s=0.0,
            grid_edges_m=GRID,
            mass_density_kg_m3=np.full(shape, 4.0),
            momentum_density_kg_m2_s=momentum,
            sensible_enthalpy_density_J_m3=np.full(shape, 7.0),
        )
        coarse = {"x": [0, 2], "y": [0, 2], "z": [0, 2]}
        mapped = remap_exchange_bundle(bundle, coarse)
        self.assertEqual(mapped["variables"]["mass_density"]["values"], [[[4.0]]])
        self.assertEqual(mapped["variables"]["momentum_density"]["values"], [[[[1.0, 2.0, 3.0]]]])
        self.assertEqual(mapped["variables"]["sensible_enthalpy_density"]["values"], [[[7.0]]])


if __name__ == "__main__":
    unittest.main()
