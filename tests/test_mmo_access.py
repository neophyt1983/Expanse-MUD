"""Contract tests for the shared MMO gateway authorization boundary.

Run: python -m unittest discover -s tests -p 'test_mmo_access.py'
No network or production state required.
"""
import tempfile
import unittest

from server.mmo_access import MMOAuthorizer
from server.mmo_ownership import MMOOwnership
from server.mmo_roles import MMORoles, ADMIN, FULL_EDIT, NO_EDIT


class MMOAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.roles = MMORoles(self.tmp.name, "EMUD")
        self.ownership = MMOOwnership(self.tmp.name)
        # This mapping deliberately models an authoritative session lookup.
        self.sessions = {
            "session-owner": "EMUD",
            "session-alpha": "PlayerAlpha",
            "session-beta": "PlayerBeta",
        }
        self.policy = MMOAuthorizer(self.sessions.get, self.roles, self.ownership, owner="EMUD")
        self.registered = ["PlayerAlpha", "PlayerBeta"]

    def test_default_player_and_unknown_operations_are_denied(self):
        self.assertEqual(self.policy.authorize("session-alpha", "play"), "playeralpha")
        self.assertEqual(self.policy.authorize("session-alpha", "create_character"), "playeralpha")
        for action in ("world_mutation", "editor_import", "kick_player", "dm_console",
                       "assign_role", "not_a_known_command"):
            with self.subTest(action=action), self.assertRaises(PermissionError):
                self.policy.authorize("session-alpha", action)

    def test_identity_is_required_and_revocation_is_immediate(self):
        for token in ("", "not-a-session", None, "PlayerAlpha"):
            with self.subTest(token=token), self.assertRaises(PermissionError):
                self.policy.authorize(token, "play")
        self.sessions.pop("session-alpha")
        with self.assertRaises(PermissionError):
            self.policy.authorize("session-alpha", "play")

    def test_owner_only_role_assignment_and_live_downgrades(self):
        self.roles.assign("EMUD", "PlayerAlpha", FULL_EDIT, self.registered)
        self.assertEqual(self.policy.authorize("session-alpha", "editor_draft"), "playeralpha")
        with self.assertRaises(PermissionError):
            self.policy.authorize("session-alpha", "kick_player")
        self.roles.assign("EMUD", "PlayerAlpha", ADMIN, self.registered)
        self.assertEqual(self.policy.authorize("session-alpha", "kick_player"), "playeralpha")
        with self.assertRaises(PermissionError):
            self.policy.authorize("session-alpha", "assign_role")
        self.assertEqual(self.policy.authorize("session-owner", "assign_role"), "emud")
        self.roles.assign("EMUD", "PlayerAlpha", NO_EDIT, self.registered)
        for action in ("kick_player", "editor_view", "world_mutation"):
            with self.subTest(action=action), self.assertRaises(PermissionError):
                self.policy.authorize("session-alpha", action)

    def test_cross_account_character_access_is_denied_even_to_admin(self):
        self.policy.claim_created("session-alpha", "character-alpha")
        for action in ("resume_character", "save_character", "load_character",
                       "delete_character", "trade_character", "transfer_character"):
            with self.subTest(action=action):
                self.assertEqual(self.policy.authorize(
                    "session-alpha", action, character_id="character-alpha"), "playeralpha")
                with self.assertRaises(PermissionError):
                    self.policy.authorize("session-beta", action, character_id="character-alpha")
                with self.assertRaises(PermissionError):
                    self.policy.authorize("session-owner", action, character_id="character-alpha")
        with self.assertRaises(PermissionError):
            self.policy.authorize("session-alpha", "save_character")
        with self.assertRaises(PermissionError):
            self.policy.claim_created("session-beta", "character-alpha")

    def test_grants_persist_but_roles_never_bypass_ownership(self):
        self.policy.claim_created("session-alpha", "character-alpha")
        self.roles.assign("EMUD", "PlayerBeta", FULL_EDIT, self.registered)
        self.assertEqual(self.policy.authorize("session-beta", "editor_export"), "playerbeta")
        with self.assertRaises(PermissionError):
            self.policy.authorize("session-beta", "resume_character",
                                  character_id="character-alpha")


if __name__ == "__main__":
    unittest.main()
