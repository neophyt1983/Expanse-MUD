# Website and game integration — only AFTER the community works

## Website

On `expansemud.com` add links:

- Community forum → `https://community.expansemud.com/`
- Official news → `https://community.expansemud.com/c/news`
- Expanse wiki → `https://expansemud.com/wiki/`
- Emergency status → `https://expansemud.com/status/`
- RSS official news → `https://community.expansemud.com/news.rss`

Keep all current installer and emote download paths unchanged. Do not show an untested placeholder link on the live site.

## Game client

External links can be added to the Help/Community interface after security review. Use explicit browser opening for forum/wiki/status, not embedded untrusted HTML or automatic sending of in-game account credentials. Keep the MMO and game authorization gates unchanged.

## Search/read strategy

The public wiki is static HTML generated from GitHub-owned Markdown. Changes should be reviewed and rebuilt. In-browser wiki editing and revision approval is a later phase, not included in the current prototype.