# Expanse — Solo/MMO and permissions (staging)

Related owner direction: [shared host authority and asset delivery coordination](EXPANSE-COORDINATION.md). Asset caching is a separate workstream and does not satisfy or bypass the MMO release gate below.

**This branch is NOT READY FOR PRODUCTION. Do not merge or deploy as MMO.**

## Confirmed existing architecture

- Render `render_server.py` currently starts a separate `private_game.py` process for each (account, imported world).
- `private_game.py` constructs `GameServer(mode='single')` and permits only one playing socket. Distinct accounts are private, **not** a shared MMO.
- The game engine `GameServer(mode='host')` supports multiple sockets, chat, trades, and character ownership hooks. It does not by itself provide a public authenticated MMO launcher.
- Online authentication and ordinary registration are already in 1.9.17; preserve their databases, identity keys and saves.

## Changes on this branch (safe first milestone)

1. Server-rendered home screen presents **Single Player** and **MMO** with honest availability.
2. Single Player continues using the established `/enter` and private worker model.
3. An MMO request is rejected with 503 while shared hosting is unimplemented. The UI must never mislabel a private worker as MMO.
4. `server/mmo_roles.py`: SQLite-backed `No_Edit`, `Admin`, `Full_Edit` classifications; default `No_Edit`; only configured owner can alter assignments; owner always treated as `Admin` by this registry.
5. Owner-only `/mmo/roles` controls and a role-change audit trail. A role change grants **no current editor/DM access**, because MMO is not running.
6. `server/mmo_ownership.py`: future MMO-only account → character claim registry; not yet attached to game-server resume/create/delete flows.
7. Unit tests for default denial, owner-only assignment, persistence, audit, and character ownership.

## Intended role rights (not yet implemented in a shared runtime)

| Role | MMO play | MMO editor | MMO moderation |
|---|---|---|---|
| No_Edit | Yes | No | No |
| Admin | Yes | Yes, authorized shared-world edits | Yes |
| Full_Edit | Yes | Yes, full authorized editing | No |

**No_Edit must be the default for all accounts.** The browser must never choose its effective role. The server must check permissions for every editor API, save/export/import, mutation endpoint, WebSocket command and DM action. UI hiding alone is insufficient.

## Required second milestone to actually enable MMO

1. Create one dedicated shared-world worker (`GameServer(mode='host')`) and multiple independent network sockets, with clear player capacity and lifecycle.
2. Authenticate each inbound MMO websocket in the Render gateway, then pass an authenticated **server-side** identity to the shared host; do not trust a browser-supplied username, role or character identifier.
3. Enforce the MMO ownership registry before character creation, resume, saves, loads, deletions, trades and session transfer; migrate/claim existing characters explicitly, never automatically map two accounts to one character.
4. Route all MMO requests to the shared worker but continue routing solo requests to each account's private worker. Preserve offline solo availability.
5. Integrate role checks with the actual Creator/editor route, editor APIs, DM commands, moderation, exports and live-world mutation. `Admin` may moderate, `Full_Edit` may edit without moderation, `No_Edit` may do neither. Separate safe drafts from live changes.
6. Design and verify shared-world persistence (including the user's explicit manual-save preference), database locking, process restart behavior and preservation of existing saves.
7. Cross-client integration tests: two accounts simultaneously in one world, separate characters, one sees the other, chat/trade, movement updates, logout isolation, privilege denial for forged editor requests, role revocation mid-session, save/load and restart recovery.
8. Verify performance and load on actual Render resources. The old `EXPANSE_MAX_ACTIVE_GAMES` setting caps private game processes, **not** the shared world's concurrent-player capacity.

Until all checks pass, MMO remains unavailable and existing single-player access is preserved. Keep this pull request draft.
