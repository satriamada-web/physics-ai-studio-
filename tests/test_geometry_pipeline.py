"""Regression tests for the imported-geometry → volume-mesh → wind/heat path.

Run with: python -m unittest discover -s tests -v
These tests verify the current MVP pipeline; they do not validate a full CFD/FEM model.
"""
import unittest

import numpy as np

from physics.geometry_import import import_surface_mesh
from physics.volume_mesh_3d import create_voxel_volume_mesh
from physics.wind_heat_3d import solve_wind_heat_transport
from physics.domain_3d import create_enclosing_air_domain


CUBE_OBJ = b"""v 0 0 0
v 1 0 0
v 1 1 0
v 0 1 0
v 0 0 1
v 1 0 1
v 1 1 1
v 0 1 1
f 1 3 2
f 1 4 3
f 5 6 7
f 5 7 8
f 1 2 6
f 1 6 5
f 2 3 7
f 2 7 6
f 3 4 8
f 3 8 7
f 4 1 5
f 4 5 8
"""


class GeometryPipelineTests(unittest.TestCase):
    def test_obj_import_reports_closed_unit_cube(self):
        geometry = import_surface_mesh("unit_cube.obj", CUBE_OBJ)
        self.assertEqual(geometry["source_format"], "OBJ")
        self.assertEqual(geometry["vertex_count"], 8)
        self.assertEqual(geometry["face_count"], 12)
        self.assertTrue(geometry["is_watertight"])
        self.assertEqual(geometry["boundary_edge_count"], 0)
        np.testing.assert_allclose(
            [geometry["dimensions_m"][axis] for axis in ("x", "y", "z")],
            [1.0, 1.0, 1.0],
        )

    def test_closed_obj_generates_nonempty_voxel_volume(self):
        geometry = import_surface_mesh("unit_cube.obj", CUBE_OBJ)
        mesh = create_voxel_volume_mesh(
            geometry["vertices"], geometry["faces"], resolution=8
        )
        self.assertGreater(mesh["active_cell_count"], 0)
        self.assertEqual(mesh["inside_mask_zyx"].ndim, 3)
        self.assertTrue(mesh["inside_mask_zyx"].any())
        self.assertGreater(mesh["volume_estimate_m3"], 0.0)
        self.assertGreater(len(mesh["boundary_vertices"]), 0)
        self.assertGreater(len(mesh["boundary_faces"]), 0)
        self.assertEqual(mesh["boundary_faces"].shape[1], 3)
        np.testing.assert_allclose(mesh["boundary_vertices"].min(axis=0), [0.0, 0.0, 0.0])
        np.testing.assert_allclose(mesh["boundary_vertices"].max(axis=0), [1.0, 1.0, 1.0])

    def test_room_air_domain_excludes_obstacle_and_selects_openings(self):
        obstacle = np.zeros((4, 5, 6), dtype=bool)
        obstacle[1:3, 2:4, 2:4] = True
        domain = create_enclosing_air_domain(obstacle, padding_cells=3, flow_axis="x", flow_sign=1)
        self.assertEqual(domain["air_mask_zyx"].shape, (10, 11, 12))
        self.assertFalse(np.any(domain["air_mask_zyx"] & domain["obstacle_mask_zyx"]))
        self.assertGreater(domain["inlet_mask_zyx"].sum(), 0)
        self.assertGreater(domain["outlet_mask_zyx"].sum(), 0)
        self.assertFalse(np.any(domain["inlet_mask_zyx"] & domain["outlet_mask_zyx"]))
        self.assertEqual(domain["flow_axis"], "x")

    def test_room_air_domain_supports_reverse_z_flow(self):
        obstacle = np.ones((3, 3, 3), dtype=bool)
        domain = create_enclosing_air_domain(obstacle, padding_cells=2, flow_axis="z", flow_sign=-1)
        self.assertEqual(domain["inlet_mask_zyx"].shape, (7, 7, 7))
        self.assertTrue(domain["inlet_mask_zyx"][-1].any())
        self.assertTrue(domain["outlet_mask_zyx"][0].any())

    def test_custom_inlet_does_not_heat_the_entire_upstream_wall(self):
        mask = np.ones((4, 4, 4), dtype=bool)
        inlet = np.zeros_like(mask)
        inlet[1, 1, 0] = True
        result = solve_wind_heat_transport(
            mask, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 305.0, 295.0,
            air_conductivity=1e-10, total_time=0.01, snapshot_count=2,
            inlet_mask_zyx=inlet,
        )
        final = result["temperature"]
        self.assertAlmostEqual(final[1, 1, 0], 305.0, places=6)
        upstream_wall = final[:, :, 0].copy()
        upstream_wall[1, 1] = 295.0
        self.assertLess(float(np.max(np.abs(upstream_wall - 295.0))), 0.01)

    def test_wind_heat_solver_uses_imported_volume_mask(self):
        geometry = import_surface_mesh("unit_cube.obj", CUBE_OBJ)
        mesh = create_voxel_volume_mesh(
            geometry["vertices"], geometry["faces"], resolution=8
        )
        result = solve_wind_heat_transport(
            mesh["inside_mask_zyx"],
            mesh["dx"], mesh["dy"], mesh["dz"],
            wind_speed=0.5,
            wind_azimuth_deg=0.0,
            wind_elevation_deg=0.0,
            inlet_temperature=305.0,
            initial_temperature=295.0,
            total_time=0.1,
            snapshot_count=3,
        )
        self.assertGreater(result["steps"], 0)
        self.assertGreater(result["inlet_cell_count"], 0)
        self.assertGreaterEqual(len(result["snapshots"]), 2)
        self.assertTrue(np.isfinite(result["temperature"][mesh["inside_mask_zyx"]]).all())
        self.assertEqual(result["velocity_m_s"][0], 0.5)


if __name__ == "__main__":
    unittest.main()
