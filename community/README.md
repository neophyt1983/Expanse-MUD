# ExpanseMUD Community — forum + wiki (staging prototype)

**Status: NOT DEPLOYED, NOT PRODUCTION-READY.** No Render service has been created, no charges authorized, no game account/save/world data touched, and no Fastmail website files overwritten by this package.

A custom ExpanseMUD community, designed to be substantially cheaper than a hosted Discourse subscription while preserving the independent game website and the existing authoritative game server.

## Architecture

| Destination | Hosting | Implementation |
| --- | --- | --- |
| `https://expansemud.com/` | Existing Fastmail static website | Current game homepage (unchanged by this prototype) |
| `https://expansemud.com/wiki/` | Existing Fastmail static website | Versioned wiki Markdown built to self-contained HTML |
| `https://expansemud.com/status/` | Existing Fastmail static website | Manual emergency status page independent of Render |
| `https://community.expansemud.com/` | **Proposed separate paid Render web service** | Python/aiohttp forum and SQLite on a **separate** persistent disk |
| GitHub | Existing `neophyt1983/Expanse-MUD` | Source, wiki edits, review history, CI candidates |

**No credentials or sessions are shared between the game and community.** No MMO changes or service deployment are part of this package. The official news page can also publish an RSS feed at `/news.rss`.

## Implemented in this prototype

- Publicly readable, server-rendered category pages and discussion threads.
- Staff-only **Official News & Server Status**; topics can be pinned or locked by the administrator.
- Categories for help, discussion, feedback, bug reports and Creator Workshop.
- Community registration requests with manual approval, separate account database, password hashing, HttpOnly cookies and CSRF protection for authenticated writes.
- Member replies, topic reports, staff moderation and member suspension.
- Plain-text posts rendered as escaped HTML (no untrusted HTML or rich uploads).
- RSS feed for staff announcements.
- GitHub-maintained Markdown wiki, static HTML build, manually updated Fastmail emergency status page.
- Regression tests for member authorization, posts, escaping, persistence, reports and wiki rendering.

## Not yet implemented / blocking public launch

- Reliable email verification, password recovery, notification delivery and account deletion.
- Robust distributed spam protection and moderation audit/appeal workflow.
- Safe user editing/deleting of their own posts, export/retention policies, full accessibility audit.
- Independent off-site database backups and restore drills. Render's disk snapshots alone are not sufficient.
- External penetration testing and concurrency/load testing at the selected Render plan.
- Persistent notification preferences and optional community game-account linking, which would require explicit consent and strict authority boundaries.
- Discourse import tooling; obtain and verify an authorized export first.

See `docs/RELEASE_GATE.md`. **Do not deploy publicly before the release gate passes.**

## Run the local prototype (no purchase needed)

With Python 3.13+:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
export EXPANSE_COMMUNITY_ADMIN_USER=owner
export EXPANSE_COMMUNITY_ADMIN_PASSWORD='choose-a-unique-long-staging-password'
export EXPANSE_COMMUNITY_DATA_DIR="$PWD/.community-data"
python app.py
```

Open `http://127.0.0.1:10000/` locally. The live application defaults to Secure HttpOnly cookies. The included tests create a separate local test application with `secure=False` for the HTTP test client only.

To run regression tests:

```bash
python -m unittest discover -s tests -v
```

Do not reuse Expanse game passwords when testing the forum.

## Build the wiki for Fastmail

```bash
python wiki/build.py
```

The resulting folders under `dist/` are `wiki/`, `assets/`, and `status/`. **After review and when ready to publish**, upload these **three folders** into the *existing* Fastmail `web/ExpanseMUD/` directory without deleting the main website's `index.html`, installer files, game assets, or `emotes/` folder. GitHub is the source of truth for wiki text; Fastmail holds only generated pages. This prototype does not include an automatic uploader.

## Proposed Render deployment (not performed)

The low-cost option is a **separate** 0.5 CPU/512 MB (`0.5c-512mb`) paid web service, starting near $7/mo, plus ~1 GB persistent disk (`$0.25/GB/mo`), subject to the live plan and additional usage. Free web service local storage is ephemeral and should not hold community posts.

- Repository `neophyt1983/Expanse-MUD`; set `rootDir=community` if using this mono-repository.
- Build command: `pip install -r requirements.txt`.
- Start command: `python app.py`.
- Health path: `/healthz`; manual deploys until verified.
- Persistent disk mount: `/var/data/expanse-community` (1 GB initially).
- Secret settings (never commit values): `EXPANSE_COMMUNITY_DATA_DIR=/var/data/expanse-community`, `EXPANSE_COMMUNITY_ADMIN_USER`, `EXPANSE_COMMUNITY_ADMIN_PASSWORD`.
- Only after service verification, configure `community.expansemud.com` as a custom domain and create the corresponding CNAME in Fastmail DNS as Render instructs.
- Obtain an automated encrypted off-site backup/restore procedure before public registration.

The separate service protects the game from community traffic. Even a separate Render forum may be down during a Render-wide incident, so the Fastmail `status/` page is an independent fallback.

## Development policy

Only actual in-game content can be presented as gameplay. Community emoji/icon assets created in the established game style must be labeled *channel artwork*, not screenshots of implemented mechanics. New features and shared MMO access must be labeled as development until verified.

**I am the artist. AI is the brush. The game is the canvas.**