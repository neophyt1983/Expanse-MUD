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
3. A public MMO request is rejected with 503 while production shared-host integration remains incomplete. The UI must never mislabel a private worker as MMO.
4. `server/mmo_roles.py`: SQLite-backed `No_Edit`, `Admin`, `Full_Edit` classifications; default `No_Edit`; only configured owner can alter assignments; owner always treated as `Admin` by this registry.
5. Owner-only `/mmo/roles` controls and a role-change audit trail. A role change grants **no public MMO editor/DM access** while that runtime is closed. The isolated staging service below uses a separate role store.
6. `server/mmo_ownership.py`: account → character claim registry. It is now connected to the isolated local staging runtime's supported character flows; it is not attached to public Render MMO routing. Unsupported operations remain closed.
7. Unit tests for default denial, owner-only assignment, persistence, audit, and character ownership.

## Local staging milestone — November 18, 2026

`python -m server.shared_staging` supplies a dedicated, opt-in, loopback-only shared host using the existing `GameServer(mode='host')`. It copies/imports a world into a new marked staging directory, uses separate configured test accounts, roles, ownership and checkpoint storage, and refuses a second writer. It never imports production accounts, migrates solo characters or changes the public `/enter` gate. See [the step-by-step local trial and rollout runbook](docs/SHARED-HOST-ROLLOUT.md).

The staging boundary resolves identity from a server-issued session on every protected request/message and checks the bound character's ownership. Role changes are read live. Admin can use the guarded local DM operations; Full_Edit cannot moderate. Creator, live-world editing/publication, exports/imports and unsupported application-control endpoints remain closed for every staging role until their own safe integration exists. The role policy is not evidence that those features are implemented.

**Latest owner save direction:** MMO automatically checkpoints on exit, disconnect, revoked session or idle timeout. The staging idle timeout defaults to 15 minutes and is configurable with `--idle-timeout` in seconds. Legacy discard/quit requests in this shared runtime save instead of discarding shared progress. Existing Single Player retains manual **Save / Save & quit**. The generic host engine's lower-level disconnect behavior is unchanged unless the MMO runtime opts into its save policy. Forced process termination is not a clean player exit or proof of a successful checkpoint.

Policy, ownership, shared checkpoint and real network integration tests accompany this staging work. Their final results, target-runtime CI and unresolved limits must be recorded against the candidate commit; this milestone alone does not certify the release gate, Render capacity, physical devices or full authored-world play. **No public MMO activation or live deployment is part of this milestone.**

## Intended completed role rights

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
6. Verify coherent shared-world persistence with MMO automatic exit/disconnect/session-timeout checkpoints, database locking, restart recovery and failure handling. Preserve Single Player's manual-save behavior and all existing saves. Saving one shared player must not produce an inconsistent world/character checkpoint or silently discard another player's authoritative state.
7. Cross-client integration tests: two accounts simultaneously in one world, separate characters, one sees the other, chat/trade, movement updates, logout isolation, privilege denial for forged editor requests, role revocation mid-session, save/load and restart recovery.
8. Verify performance and load on actual Render resources. The old `EXPANSE_MAX_ACTIVE_GAMES` setting caps private game processes, **not** the shared world's concurrent-player capacity.

Until all checks pass, MMO remains unavailable and existing single-player access is preserved. Keep this pull request draft.
