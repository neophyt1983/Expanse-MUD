"""Forum-local mute controls. All subject lookups use forum numeric IDs."""
from html import escape
from aiohttp import web

SCHEMA = '''
CREATE TABLE IF NOT EXISTS forum_owner (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 user_id INTEGER REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS personal_mutes (
 viewer_id INTEGER NOT NULL REFERENCES users(id),
 subject_id INTEGER NOT NULL REFERENCES users(id),
 PRIMARY KEY(viewer_id, subject_id), CHECK(viewer_id<>subject_id)
);
CREATE INDEX IF NOT EXISTS idx_replies_topic_author ON replies(topic_id,author_id);
CREATE TABLE IF NOT EXISTS posting_mutes (
 subject_id INTEGER PRIMARY KEY REFERENCES users(id),
 created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS posting_mute_audit (
 id INTEGER PRIMARY KEY, actor_id INTEGER NOT NULL REFERENCES users(id),
 action TEXT NOT NULL, changed INTEGER NOT NULL CHECK(changed=1), created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS posting_mute_appeals (
 subject_id INTEGER PRIMARY KEY REFERENCES posting_mutes(subject_id) ON DELETE CASCADE,
 body TEXT NOT NULL, created_at INTEGER NOT NULL
);
'''

def owner(db, user):
    return bool(user and db.execute(
        "SELECT 1 FROM forum_owner o JOIN users u ON u.id=o.user_id "
        "WHERE o.user_id=? AND u.role='admin' AND u.status='active'",(user['id'],)
    ).fetchone())

def muted(db, user):
    return bool(user and db.execute('SELECT 1 FROM posting_mutes WHERE subject_id=?',(user['id'],)).fetchone())

def assert_can_publish(db, user):
    # Serialize before inspecting the restriction and before the public insert.
    db.execute('BEGIN IMMEDIATE')
    if muted(db,user):
        raise web.HTTPForbidden(text='Posting is paused for this forum account. Open Posting status to appeal.')

def controls(user, subject, topic, csrf):
    if not user or user['id']==subject:
        return ''
    return (f'<form method="post" action="/mutes"><input type="hidden" name="csrf" value="{escape(csrf)}">'
            f'<input type="hidden" name="user_id" value="{subject}">'
            f'<input type="hidden" name="topic_id" value="{topic}">'
            '<button name="action" value="mute">Mute for me</button></form>')

def subject(form):
    raw=form.get('user_id','')
    if not isinstance(raw,str) or not raw.isascii() or not raw.isdecimal() or len(raw)>19:
        raise web.HTTPBadRequest()
    ident=int(raw)
    if not 0<ident<=9223372036854775807:
        raise web.HTTPBadRequest()
    return ident
