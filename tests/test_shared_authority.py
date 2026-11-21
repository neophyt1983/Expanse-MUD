"""Shared command admission checks; no production accounts or save paths."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from server.mmo_access import MMOAuthorizer
from server.mmo_ownership import MMOOwnership
from server.mmo_roles import MMORoles, ADMIN, FULL_EDIT, NO_EDIT
from server.shared_authority import authorize_packet, can_edit, can_moderate


class SharedAuthorityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="expanse-shared-authority-")
        self.addCleanup(temporary.cleanup)
        self.roles = MMORoles(Path(temporary.name), "Owner")
        self.ownership = MMOOwnership(Path(temporary.name))
        self.tokens = {"alpha-session": "Alpha", "beta-session": "Beta", "owner-session": "Owner"}
        policy = MMOAuthorizer(self.tokens.get, self.roles, self.ownership, owner="Owner")
        self.alpha, self.beta, self.owner = object(), object(), object()
        self.server = SimpleNamespace(
            mmo_authorizer=policy,
            mmo_sessions={self.alpha: "alpha-session", self.beta: "beta-session", self.owner: "owner-session"},
            host_sockets=set(), world=SimpleNamespace(shortcuts={}),
        )
        self.ownership.claim("Alpha", "alpha-character")
        self.ownership.claim("Beta", "beta-character")

    def role(self, account, role):
        self.roles.assign("Owner", account, role, ("Alpha", "Beta"))

    def packet(self, command, socket=None, player="alpha-character", **body):
        return authorize_packet(self.server, self.alpha if socket is None else socket,
                                dict(command=command, **body), player)

    def test_identity_and_bound_actor_are_checked_for_every_message(self):
        self.assertEqual("alpha", self.packet("look"))
        with self.assertRaises(PermissionError):
            self.packet("look", player="beta-character", account="Alpha", role=ADMIN)
        self.tokens.pop("alpha-session")
        with self.assertRaises(PermissionError):
            self.packet("look")
        self.assertFalse(can_edit(self.server, self.alpha))
        self.assertFalse(can_moderate(self.server, self.alpha))

    def test_character_resume_cannot_use_another_account_or_forged_body(self):
        self.assertEqual("alpha", self.packet("resume alpha-character", player=None))
        self.assertEqual("alpha", self.packet("resume", player=None, player_id="alpha-character"))
        for command, body in (("resume beta-character", {}),
                              ("resume", {"player_id": "beta-character"}),
                              ("resume", {})):
            with self.subTest(command=command, body=body), self.assertRaises(PermissionError):
                self.packet(command, player=None, account="Alpha", auth_token="forged", **body)
        self.assertEqual("alpha", self.packet("look", player_id="beta-character"),
                         "Gameplay remains bound to the server's actor; body IDs do not select actors.")

    def test_admin_cannot_resume_or_save_another_accounts_character(self):
        self.role("Alpha", ADMIN)
        for command, player in (("resume beta-character", None),
                                ("save", "beta-character"),
                                ("save_exit", "beta-character")):
            with self.subTest(command=command), self.assertRaises(PermissionError):
                self.packet(command, player=player)

    def test_owner_lookup_uses_the_persisted_registry_and_validates_identifiers(self):
        self.assertEqual("alpha", self.ownership.owner("alpha-character"))
        self.assertEqual("beta", MMOOwnership(self.ownership.path.parent).owner("beta-character"))
        for target in (None, {}, "", "invalid character", "not-claimed"):
            with self.subTest(target=target):
                self.assertIsNone(self.ownership.owner(target))

    def test_live_downgrade_and_full_edit_never_grant_moderation(self):
        self.role("Alpha", FULL_EDIT)
        self.assertTrue(can_edit(self.server, self.alpha))
        self.assertFalse(can_moderate(self.server, self.alpha))
        with self.assertRaises(PermissionError):
            self.packet("dm", operation="roster")
        self.role("Alpha", ADMIN)
        self.assertTrue(can_moderate(self.server, self.alpha))
        self.assertEqual("alpha", self.packet("dm", operation="roster"))
        self.role("Alpha", NO_EDIT)
        self.assertFalse(can_edit(self.server, self.alpha))
        with self.assertRaises(PermissionError):
            self.packet("dm", operation="commit", token="old-preview")
        self.assertEqual(set(), self.server.host_sockets)

    def test_legacy_host_controls_and_checkpoint_management_are_closed_for_every_role(self):
        for role in (NO_EDIT, FULL_EDIT, ADMIN):
            self.role("Alpha", role)
            for command in ("host_auth", "HOSTMAP", "players", "promote beta-character",
                            "demote beta-character", "announce hello", "save slots", "save   slots"):
                with self.subTest(role=role, command=command), self.assertRaises(PermissionError):
                    self.packet(command, control_token="client-supplied")
        with self.assertRaises(PermissionError):
            self.packet("host_auth", self.owner, None)

    def test_shortcuts_cannot_smuggle_legacy_controls_or_moderation(self):
        self.server.world.shortcuts.update({"ordinary": "promote beta-character", "console": "dm"})
        for command in ("ordinary", "console"):
            with self.subTest(command=command), self.assertRaises(PermissionError):
                self.packet(command)
        self.server.world.shortcuts["outside"] = "go out"
        self.assertEqual("alpha", self.packet("outside"))

    def test_missing_context_and_malformed_messages_fail_closed(self):
        for packet in (None, [], {}, {"command": None}, {"command": " "}, {"command": "x" * 4097}):
            with self.subTest(packet=packet), self.assertRaises(PermissionError):
                authorize_packet(self.server, self.alpha, packet, "alpha-character")
        self.server.mmo_sessions.pop(self.alpha)
        with self.assertRaises(PermissionError):
            self.packet("look")
        self.assertFalse(can_moderate(self.server, object()))


if __name__ == "__main__":
    unittest.main()
