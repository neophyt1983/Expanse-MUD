# Expanse shared implementation direction

Owner direction recorded November 18, 2026. Canonical technical handoff: [asset delivery audit and contract](docs/ASSET-DELIVERY.md). Measured evidence: [baseline JSON](docs/measurements/asset-delivery-baseline-20261118.json).

Online MMO/MUD players join one authoritative world hosted by a player's local computer or Render. Device-side presentation assets can reduce repeated downloads; the host selects their versions and remains authoritative for simulation, accounts, permissions and persistence. Clients should ultimately fetch only missing/changed verified resources. This is a planned capability: current browser media caching is page-memory-only, desktop Qt caching is disabled, and no host-versioned persistent asset protocol has been implemented.

| Work area | Shared assignment / integration contract |
| --- | --- |
| Engine and authored game work / Fix Expanse Code | Define safe public/revealed asset metadata and hash invalidation without embedding authored game rules in the engine. Preserve public pixel projections and hidden editor layers. Keep the shared protocol/fixtures identical across desktop and server. Merge upcoming festival/quest changes without reverting performance or account work. |
| Online host / Import Expanse Context / Render | Supply authenticated scoped manifests and immutable blobs through host adapters; count HTTP and WS outbound traffic. Preserve original imported-world IDs and private worker saves. Collect real service Metrics and workspace Billing before claiming savings. No deployment or paid service change is authorized by this handoff alone. |
| Browser/UI | Introduce hashed application URLs first; then persistent media storage if justified. Retain old WS clients, manual save controls and uncached private APIs. Use a dedicated bounded cache; preserve character IDs, tokens and preferences in existing browser storage. |
| Windows/Linux installed apps | Reuse verified bundled presentation bytes against the same host manifest; keep native cache and dependency downloads separate. Continue updating the existing application in place, preserving saves, user worlds, local accounts, settings, exports and backups. Asset delivery must not execute code or replace the engine. Android requires its own shell/cache audit. |
| MMO, permissions and capacity | Asset caching does not enable shared multiplayer. Keep [shared-world/account-isolation/editor-authorization/persistence/multiplayer gates](MMO-MODES-REVIEW.md). `No_Edit`, `Admin`, `Full_Edit` remain server controlled. [PR #4](https://github.com/neophyt1983/Expanse-MUD/pull/4) documents a capacity target, not tested capacity or MMO availability. |
| Website/community/release notes | Link this handoff and distinguish implemented behavior, proposals and measured production results. Do not advertise persistent asset synchronization or shared MMO as delivered. |

Current audited server baseline is `bbbe023` (the merged interface-quest fix after the 1.9.17 parity update). Desktop package 1.9.17.1 identifies that shared commit and bundles Wild Lands 1.9.15. The separate festival 1.9.18/Wild Lands 1.9.16 handoff is staged and has its own compatibility/deployment prerequisites; inspecting its asset hashes is not authorization to import or deploy it.

Sequence: baseline and real usage → hashed app files/compression → scoped world manifest/binary blobs → bounded browser/native reuse → measured production comparison. Prefer the existing host and client storage before paying for another delivery service. Cache clearing, eviction, update, rollback and account switching must preserve user data. Keep manual gameplay saving.

Each workstream should cite the same protocol revision, tested source commit, asset-manifest revision and evidence in its PR/release notes. Record unresolved compatibility questions against this handoff before changing a shared file. Update this document and its evidence when implementation is delivered; do not treat design text as proof that a feature is running.

Follow-up evidence from engine/game work: [cache behavior, public headers and gameplay packet sizes](docs/ASSET-DELIVERY-FOLLOWUP.md). It reuses this handoff and the canonical measurement tool. No cache or shared-MMO implementation/deployment is implied; actual production billing/session measurements remain required.
