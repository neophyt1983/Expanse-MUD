# Migration plan — Discourse to Expanse Community

The original community is located at `https://expansemud.discourse.group/`. Do not delete it or cancel the account until content and legal retention have been reviewed.

1. From the authorized Discourse administrator account, obtain an official forum data export/backup using options the hosting plan actually provides. Verify it includes the intended public announcements, categories, discussions and user attribution. Never paste or commit credentials or private member information into GitHub.
2. Inventory posts for ownership and privacy. Public posts are not automatic consent to publish private account/email metadata on a new service. Plan the migration of topics separately from the migration of accounts.
3. Preserve original external URLs or publish a clear redirect/link notice at the old forum where permitted. Do not break the official website's community link until the new domain works.
4. Create the new categories. Publish an official announcement explaining why the forum is moving, where the wiki lives, and how new registration works.
5. Import or manually republish owner-authored announcements first; import other people's content only under an appropriate migration policy.
6. Test public reading, creation, replies, moderation, forum data persistence, notifications and backup restore. Verify static `/status/` still works when the community service is deliberately offline.
7. Only after successful migration and checking any billing obligations, discontinue paid Discourse hosting.

**No Discourse export, login, deletion or cancellation has been performed.**