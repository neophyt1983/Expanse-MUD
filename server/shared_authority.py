"""Live authorization at the experimental shared host's command boundary.

The public Render gateway remains closed to MMO play. This module gives the
separate staging host the same account, character and role policy on every
message, without turning a web administrator into a legacy local-host socket.
"""
from __future__ import annotations


# Legacy host controls carry broader authority than the MMO classifications.
# In particular, promotion tokens and checkpoint replacement must never be
# exposed by simply inserting an Admin or Full_Edit socket into host_sockets.
_LOCAL_HOST_VERBS = frozenset({
    "host_auth", "hostmap", "players", "promote", "demote", "announce",
})


def _context(server, socket):
    policy = getattr(server, "mmo_authorizer", None)
    session = getattr(server, "mmo_sessions", {}).get(socket)
    if policy is None or not isinstance(session, str) or not session:
        raise PermissionError("An authenticated shared-world session is required.")
    return policy, session


def _command(packet):
    if not isinstance(packet, dict):
        raise PermissionError("Expected a shared-world command message.")
    command = packet.get("command")
    if not isinstance(command, str) or not command.strip() or len(command) > 4096:
        raise PermissionError("A command of at most 4096 characters is required.")
    command = command.strip()
    if command == "resume" and isinstance(packet.get("player_id"), str):
        command += " " + packet["player_id"]
    return command


def _reject_local_controls(command):
    words = command.casefold().split()
    if words[0] in _LOCAL_HOST_VERBS:
        raise PermissionError("Local host controls are unavailable in shared-world staging.")
    if words[:2] == ["save", "slots"]:
        raise PermissionError("Shared checkpoint replacement and save-slot management are unavailable in staging. Use Save.")


def authorize_packet(server, socket, packet, player_id=None):
    """Authorize the current server-bound actor, never a body-supplied actor.

    Call after syntax parsing, before any command handler or world mutation.
    The connection's session must have been installed by the authenticated
    shared host. Client-supplied account names, roles and tokens are ignored.
    Ownership is checked again on every message and on every resume request.
    """
    policy, session = _context(server, socket)
    account = policy.authorize(session, "play")
    if player_id is not None:
        policy.authorize(session, "resume_character", character_id=player_id)

    command = _command(packet)
    _reject_local_controls(command)
    # Authored shortcuts execute only through the gameplay registry, which has
    # no local-host handlers. Reject a privileged expansion as well so a future
    # change cannot silently turn an innocent-looking alias into host access.
    words = command.split(maxsplit=1)
    expansion = getattr(server.world, "shortcuts", {}).get(words[0].casefold())
    if isinstance(expansion, str) and expansion.strip():
        _reject_local_controls(expansion)
        if expansion.split()[0].casefold() == "dm":
            policy.authorize(session, "dm_console")

    verb = words[0].casefold()
    if verb == "resume":
        target = words[1].strip() if len(words) == 2 else None
        policy.authorize(session, "resume_character", character_id=target)
    elif verb == "dm":
        policy.authorize(session, "dm_console")
    elif verb in ("save", "save_exit"):
        policy.authorize(session, "save_character", character_id=player_id)
    return account


def can_moderate(server, socket):
    """Current Admin permission; no cached role or host-socket escalation."""
    try:
        policy, session = _context(server, socket)
        policy.authorize(session, "dm_console")
    except (PermissionError, ValueError):
        return False
    return True


def can_edit(server, socket):
    """Current editing permission, independent of moderation permission."""
    try:
        policy, session = _context(server, socket)
        policy.authorize(session, "editor_view")
    except (PermissionError, ValueError):
        return False
    return True
