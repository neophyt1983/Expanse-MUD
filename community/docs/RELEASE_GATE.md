# ExpanseMUD community production release gate

The standalone community is independent of Expanse Single Player and the gated shared MMO.

## Required before launch

**Fail-closed default:** Web registration is disabled unless the explicit staging override is set. Never set `EXPANSE_COMMUNITY_ALLOW_REGISTRATION` on a public Render service before every requirement below is met.

1. **Data recovery and deletion:** build encrypted off-site database export/restore, validate with actual restore drills, retention and deletion policies, backups after migrations.
2. **Account recovery:** verified email (using configured SMTP secret), password reset with expiring single-use token, session revocation on reset, account deletion/export. Do not add game credential sharing or automatic account linking.
3. **Abuse:** bot resistance, per-account and per-IP persistent rate limits, verified signup or moderated invites, spam queues, reports, thread locking, banning, consistent appeal mechanism.
4. **Security:** authenticated permission checks for every mutation, CSRF on every session-changing endpoint, Origin/Host checks behind Render TLS, password hash audit, session expiration, secure cookie attributes, HTML escaping, SQL parameterization, no arbitrary file uploads, security headers, automated dependency updates, privacy/security audit.
5. **Operations:** manual first deployment, domain/TLS, public read health, tests for restart persistence, failed deployment rollback and outage communication, snapshots/backups separate from game data, actual costs and capacity monitoring.
6. **Accessibility:** keyboard navigation, forms, contrast, mobile layout, announcements readable without Javascript, screen-reader labels.
7. **Content:** initial official introduction, clear game status and latest release, community guidelines, wiki source review, verified imported Discourse material with consent.
8. **Separation:** never open the MMO gate by adding forum code; don't access or mutate game saves, world templates, credentials, authorization tables or multiplayer sessions.

## Prototype checks (already tested)

- Public read; registered users cannot post prior to admin approval.
- Non-admin user cannot create official announcements or moderate topics.
- CSRF mismatch rejects authenticated writes.
- HTML from members is escaped; RSS output XML-escapes user text.
- Topics/replies persist after new DB connections; locks prevent further replies.
- Members can report; admins can close reports/suspend accounts; suspended sessions revoked.
- Wiki Markdown renderer rejects unsafe URI schemes.

**Prototype tests do not replace a security audit or browser/device testing.**