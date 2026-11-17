# Expanse secure accounts 1.9.17 — staging and review

**DRAFT / NOT READY TO MERGE.** This branch begins at production `main` commit `05859fa12018a75f33fed933ab3500d48c071d35`, which currently identifies as `2026-11-16-visible-magic-1.9.15`.

## Verified against GitHub (November 16, 2026)

- `render_server.py` Git blob SHA: `b5968fdd2c833266a0ce3834e4e8eb9d26282ec4`; this **exactly matches** the released 1.9.15 render-server code.
- `server/public_access.py` and `server/player_accounts.py` do not yet exist on production `main`.
- `engine/build_info.py` identifies build `2026-11-16-visible-magic-1.9.15`.
- The 1.9.17 account kit, based on cumulative 1.9.16 public play, is available in the ongoing ChatGPT Expanse Web Presence & Monetization conversation. No account code has been uploaded to this branch yet.

## Files needed from Expanse-Render-Account-Update-1.9.17.zip

Copy the **contents** of `github-upload/`, not the enclosing folder, into this *review branch*:

1. `render_server.py` — cumulative 1.9.15 → 1.9.16 public play → 1.9.17 registered accounts
2. `server/public_access.py` — legacy passwordless guest compatibility and recovery rotation
3. `server/player_accounts.py` — new persistent username/password, recovery tokens and optional verified-email reset
4. `engine/build_info.py` — expected secure-accounts build label

The kit also contains `tests/test_public_play.py`, `tests/test_account_registration.py`, a read-only checksum verifier, the admin checklist, and security notes. Upload test files to the branch for CI/review if desired.

## Review and launch gates

- [ ] Independently review all account/security code; do not treat local checks as production security certification.
- [ ] Test with the **actual GitHub checkout**, current engine, existing world imports and persisted accounts.
- [ ] Protect player data: preserve `EXPANSE_DATA_DIR`, persistent disk, game entries, saves, world template hash and legacy guest accounts.
- [ ] Confirm `EXPANSE_OWNER_NAME` and `EXPANSE_OWNER_PASSWORD` exist in Render Environment; no secrets in GitHub.
- [ ] Verify startup, owner permissions, password hashing, new registrations, returning login, account disabling, recovery-code rotation, optional email verification/reset, and mobile behavior.
- [ ] Confirm no gameplay autosave was introduced; saving remains manual only.
- [ ] Run resource/load tests; registered account quota is **not** concurrent game capacity.
- [ ] Keep production registration closed until operational checks pass: `EXPANSE_ACCOUNT_REGISTRATION=0` (when the new code is present). Set `1` only after verification.
- [ ] Only merge when an owner has verified data backup and authorized a controlled Render deployment.

## External services

- Website: `https://expansemud.com` (Fastmail static site). Update `index.html` separately, *after* registration works.
- Game: existing `https://expanse-mud.onrender.com/` until a custom hostname is installed and verified.
- Forum: `https://expansemud.discourse.group/`; confirm the hosted-plan status as the trial ends.
- Patreon: `https://www.patreon.com/ExpanseMUD`; finish rebranding without deleting existing supporter obligations.

**Important:** This file is a staging guide only. No game/login implementation has yet been committed to this review branch. Do **not** merge this branch into main as-is.