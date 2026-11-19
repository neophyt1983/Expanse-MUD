"""Regression: connected rooms in multiroom buildings stay on the local map.

Run: python -m unittest discover -s tests -p 'test_interior_room_visibility.py' -v
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from engine.travel_window import window
from engine.visual_mapping import render_visual


def rooms():
    return {
        "hall": {"id": "hall", "name": "Entry Hall", "exits": {"east": "chamber", "west": "street"},
                 "map_visibility": "discovered", "_visual_style": ("building", "floor", {"id": "old-hall", "name": "Inn"})},
        "chamber": {"id": "chamber", "name": "Side Chamber", "exits": {"west": "hall", "east": "secret"},
                    "map_visibility": "discovered", "_visual_style": ("building", "floor", {"id": "old-chamber", "name": "Inn"})},
        "secret": {"id": "secret", "name": "Hidden Room", "exits": {"west": "chamber"},
                   "map_visibility": "hidden", "_visual_style": ("building", "floor", {"id": "old-chamber", "name": "Inn"})},
        "street": {"id": "street", "name": "Street", "exits": {"east": "hall"},
                   "map_visibility": "discovered", "_visual_style": ("outdoors", "plains", {})},
    }


class InteriorRoomVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.rows = rooms()
        self.positions = {"hall": (0, 0, 0), "chamber": (1, 0, 0),
                          "secret": (2, 0, 0), "street": (-1, 0, 0)}
        self.compiled = (self.rows, self.positions, [])

    def test_local_sight_can_cross_real_door_with_mismatched_building_ids(self):
        world = SimpleNamespace(
            rooms={rid: SimpleNamespace(exits=row["exits"], map_visibility=row["map_visibility"])
                   for rid, row in self.rows.items()},
            rules={}, items={}, room_details={},
        )
        player = SimpleNamespace(location="hall", inventory=[], alive=True)
        with patch("engine.locks.index", return_value={}), patch(
            "engine.geology_impacts.route_sources", return_value=set()
        ), patch("engine.frontiers.path_blocked", return_value=False):
            tiles = window(world, player, self.compiled, [3, 3], require_open=True)
            self.assertIn("chamber", {tile["id"] for tile in tiles})
            self.assertNotIn("secret", {tile["id"] for tile in tiles})
            self.assertNotIn("street", {tile["id"] for tile in tiles})
            player.location = "chamber"
            reverse = window(world, player, self.compiled, [3, 3], require_open=True)
            self.assertIn("hall", {tile["id"] for tile in reverse})
            self.assertNotIn("secret", {tile["id"] for tile in reverse})

    def test_projection_keeps_connected_interior_when_center_changes(self):
        # Only the two already-authorized rooms may be disclosed by the map.
        with patch("engine.geology.descriptor", return_value=None), patch(
            "engine.coordinates.project", return_value=None
        ), patch("engine.route_surfaces.descriptor", return_value=None), patch(
            "engine.facility_landmarks.descriptor", return_value=None
        ):
            for center in ("hall", "chamber"):
                with self.subTest(center=center):
                    visual = render_visual(self.rows, self.positions, center,
                                           {"hall", "chamber"}, visited={"hall", "chamber"})
                    self.assertEqual({tile["id"] for tile in visual["tiles"]}, {"hall", "chamber"})
                    self.assertNotIn("secret", str(visual))
                    self.assertNotIn("street", {tile["id"] for tile in visual["tiles"]})


if __name__ == "__main__":
    unittest.main()
