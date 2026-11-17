"""MMO account role and character ownership regression tests.

Run: python -m unittest discover -s tests -p 'test_mmo_modes_roles.py'
"""
import tempfile
import unittest

from server.mmo_roles import MMORoles, NO_EDIT, ADMIN, FULL_EDIT
from server.mmo_ownership import MMOOwnership


class MMORoleTests(unittest.TestCase):
    def test_default_denies_and_owner_is_admin(self):
        with tempfile.TemporaryDirectory() as path:
            roles = MMORoles(path, "Expanse Owner")
            self.assertEqual(roles.get("new_player"), NO_EDIT)
            self.assertFalse(roles.can_edit("new_player"))
            self.assertFalse(roles.can_moderate("new_player"))
            self.assertEqual(roles.get("Expanse Owner"), ADMIN)
            self.assertTrue(roles.can_edit("Expanse Owner"))
            self.assertTrue(roles.can_moderate("Expanse Owner"))

    def test_owner_only_grants_revoke_and_persist(self):
        with tempfile.TemporaryDirectory() as path:
            roles = MMORoles(path, "Expanse Owner")
            names = ["PlayerAlpha", "PlayerBeta"]
            with self.assertRaises(PermissionError):
                roles.assign("PlayerAlpha", "PlayerAlpha", ADMIN, names)
            with self.assertRaises(ValueError):
                roles.assign("Expanse Owner", "unregistered", ADMIN, names)
            with self.assertRaises(PermissionError):
                roles.assign("Expanse Owner", "Expanse Owner", NO_EDIT, names)
            self.assertEqual(roles.assign("Expanse Owner", "PlayerAlpha", FULL_EDIT, names), FULL_EDIT)
            self.assertTrue(roles.can_edit("playeralpha"))
            self.assertFalse(roles.can_moderate("playeralpha"))
            self.assertEqual(roles.assign("Expanse Owner", "PlayerBeta", ADMIN, names), ADMIN)
            self.assertTrue(roles.can_moderate("playerbeta"))
            self.assertEqual(roles.assign("Expanse Owner", "PlayerAlpha", NO_EDIT, names), NO_EDIT)
            fresh = MMORoles(path, "Expanse Owner")
            self.assertEqual(fresh.get("PlayerAlpha"), NO_EDIT)
            self.assertEqual(fresh.get("PlayerBeta"), ADMIN)
            self.assertEqual(len(fresh.history()), 3)

    def test_ownership_is_strict_and_persistent(self):
        with tempfile.TemporaryDirectory() as path:
            ownership = MMOOwnership(path)
            ownership.claim("PlayerAlpha", "character-abc")
            self.assertTrue(ownership.owns("playeralpha", "character-abc"))
            self.assertFalse(ownership.owns("PlayerBeta", "character-abc"))
            with self.assertRaises(PermissionError):
                ownership.claim("PlayerBeta", "character-abc")
            fresh = MMOOwnership(path)
            self.assertEqual(fresh.characters("PlayerAlpha"), {"character-abc"})
            self.assertFalse(fresh.release("PlayerBeta", "character-abc"))
            self.assertTrue(fresh.release("PlayerAlpha", "character-abc"))
            self.assertFalse(fresh.owns("PlayerAlpha", "character-abc"))


if __name__ == "__main__":
    unittest.main()
