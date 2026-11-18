"""Fail-closed authorization policy for a future authenticated shared Expanse host.

This module does NOT enable MMO routing. The public gateway must derive a current
session identity and call authorize before entering any shared-world operation.
Browser-provided account names, roles and character identifiers are never authority.
"""
from __future__ import annotations

from collections.abc import Callable

from server.accounts import name_key
from server.mmo_roles import ADMIN, FULL_EDIT, NO_EDIT


# Operations are intentionally enumerated. New operations must be reviewed.
PLAY = frozenset({"play", "create_character", "list_characters"})
OWNED = frozenset({
    "resume_character", "load_character", "save_character",
    "delete_character", "trade_character", "transfer_character",
})
EDITOR = frozenset({
    "editor_view", "editor_draft", "editor_export",
    "editor_import", "world_mutation",
})
MODERATION = frozenset({
    "dm_console", "kick_player", "ban_player", "moderate_chat",
})
OWNER_ONLY = frozenset({"assign_role", "revoke_role", "view_role_audit"})
KNOWN_ACTIONS = PLAY | OWNED | EDITOR | MODERATION | OWNER_ONLY


class MMOAuthorizer:
    """Server-side access policy, evaluated against current session and role.

    identity_from_session(session) must return the authenticated account name
    (or None) by looking up a *server-issued* session. Do not pass a client-
    supplied name as a session. Call on each request or WebSocket message so
    session revocation and role downgrades take effect immediately.
    """

    def __init__(self, identity_from_session: Callable, roles, ownership, owner: str = ""):
        if not callable(identity_from_session):
            raise TypeError("A server-side session resolver is required.")
        self.identity_from_session = identity_from_session
        self.roles = roles
        self.ownership = ownership
        self.owner = name_key(owner) if owner else ""

    def account(self, session: str) -> str:
        if not isinstance(session, str) or not session:
            raise PermissionError("An authenticated MMO session is required.")
        name = self.identity_from_session(session)
        if not isinstance(name, str) or not name:
            raise PermissionError("MMO session is invalid or expired.")
        try:
            return name_key(name)
        except ValueError:
            raise PermissionError("MMO account identity is invalid.") from None

    def authorize(self, session: str, action: str, *, character_id: str | None = None) -> str:
        """Return the canonical account after all checks; otherwise deny.

        This only authorizes an operation. Callers must enforce actual creation,
        save, trade, and world-edit semantics, and must not infer character
        ownership from an arbitrary client-provided identifier.
        """
        account = self.account(session)
        if not isinstance(action, str) or action not in KNOWN_ACTIONS:
            raise PermissionError("Unknown MMO operation.")
        # Fetch the current role; never trust a role attached to a WebSocket.
        role = self.roles.get(account)
        if role not in (NO_EDIT, ADMIN, FULL_EDIT):
            raise PermissionError("Invalid MMO classification.")
        if action in OWNER_ONLY and account != self.owner:
            raise PermissionError("Only the configured owner can manage MMO roles.")
        if action in MODERATION and role != ADMIN:
            raise PermissionError("MMO moderation requires Admin classification.")
        if action in EDITOR and role not in (ADMIN, FULL_EDIT):
            raise PermissionError("MMO editing requires an authorized editor.")
        if action in OWNED:
            if not isinstance(character_id, str) or not self.ownership.owns(account, character_id):
                raise PermissionError("This character does not belong to the signed-in account.")
        return account

    def claim_created(self, session: str, character_id: str) -> str:
        """Bind a just-created character to the authenticated account.

        Call only after successful authoritative host-side character creation.
        This method is NOT proof that a caller may create a given player_id.
        """
        account = self.authorize(session, "create_character")
        self.ownership.claim(account, character_id)
        return account
