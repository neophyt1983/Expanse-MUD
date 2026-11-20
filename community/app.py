"""ExpanseMUD community forum MVP — independent of the game service.

STAGING ONLY: requires moderation, recovery, accessibility, privacy and durability
review before publishing to the public. No game credentials, saves or worlds read.
"""
from __future__ import annotations
import json

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
from html import escape
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

from aiohttp import ClientSession, ClientTimeout, ClientError, web

ROOT = Path(__file__).resolve().parent
STYLESHEET = ROOT / 'static' / 'style.css'
POST_MAX = 8000
REPLY_MAX = 4000
SESSION_AGE = 60 * 60 * 24 * 7
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_\-]{2,23}$')
PAGESIZE = 25
STARTER_GUIDES = [('creators', 'Build and test a two-room adventure', 'Make a copy of your world before editing. Create two rooms with distinct names, connect them with opposite exits, and start a new adventure from the copy. Walk through both exits. If the return trip fails, inspect the exit on the second room. Record the world version when sharing your creation.'), ('news', 'How to check game and forum availability', 'Open the status lights on the website. Game and Forum are checked separately. If the game fails to load, record the time and whether sign-in appeared. A green forum light means the forum answered its health check.'), ('help', 'Keep your place on the explored map', 'Open the explored atlas and choose Lock map. Walk a few rooms, then drag the map to inspect another location. Choose Follow player to center your character again. Search for a known room to inspect its location.'), ('discussion', 'Explore Dawnwatch from the Gilded Tankard', 'Start at the Dawnwatch Gilded Tankard and inspect the room description and exits. Visit a neighboring room, then open your atlas and look for your current-location marker. Compare the places you have visited with locations you have only learned about.'), ('suggestions', 'Describe a change you would like to play', 'Start with the task you were trying to complete. Describe what happened, the change you want, and one example of how a player would use it. Include whether you were playing online or using a desktop installation.'), ('bugs', 'Collect the details for a reproducible bug report', 'Record the engine and world versions, your device, the room, and whether you loaded a save. List the shortest sequence that produces the problem. Include the expected and actual results. For a map issue, capture the same view before and after the action.')]

SECTIONS = (
    ('news', 'Official News & Server Status', 'Confirmed maintenance, outages, releases and development announcements', 1),
    ('help', 'Questions & Help', 'Help for players, installation, commands and game mechanics', 0),
    ('discussion', 'The Tavern', 'Conversations about Expanse, its world, inhabitants and adventures', 0),
    ('suggestions', 'Suggestions & Feedback', 'Constructive ideas and requests for future development', 0),
    ('bugs', 'Bug Reports', 'Reproducible problems, affected versions and steps to investigate', 0),
    ('creators', 'Creator Workshop', 'World building, editor questions, and shared creations', 0),
)


def utc() -> int:
    return int(time.time())


def label_time(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime('%d %b %Y, %H:%M UTC')


def slug(text: str) -> str:
    result = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:80]
    return result or 'topic'


def password_digest(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 350_000)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode('ascii')).hexdigest()


_emotes = json.loads(Path(__file__).with_name('emotes.json').read_text(encoding='utf-8'))
_emote_labels = dict(_emotes['entries'])
_symbols = _emotes['symbols']
_emote_token = re.compile(r':([a-zA-Z_]+):|(?<!\u200d)([' + re.escape(''.join(_symbols))
                          + r'])[\ufe0e\ufe0f]?[\U0001f3fb-\U0001f3ff]?(?![\u200d\ufe0e\ufe0f\U0001f3fb-\U0001f3ff])')


def text_html(text: str) -> str:
    parts = []
    start = 0
    for match in _emote_token.finditer(text):
        name = match[1].lower() if match[1] else _symbols[match[2]]
        if name not in _emote_labels:
            continue
        parts.append(escape(text[start:match.start()]))
        label = escape(_emote_labels[name], quote=True)
        parts.append(f'<span class="expanse-emote e-{name}" role="img" aria-label="{label}" title="{label}"></span>')
        start = match.end()
    parts.append(escape(text[start:]))
    return '<p>' + ''.join(parts).replace('\n\n', '</p><p>').replace('\n', '<br>') + '</p>'


def valid_text(value: str, limit: int, field: str) -> str:
    text = value.strip()
    if len(text) < 2 or len(text) > limit:
        raise ValueError(f'{field} must contain 2–{limit} characters.')
    return text


class Store:
    def __init__(self, filename: Path):
        self.filename = filename
        filename.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.filename, timeout=8)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute('PRAGMA busy_timeout = 8000')
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init(self):
        with self.db() as db:
            db.execute('PRAGMA journal_mode = WAL')
            db.executescript('''
              CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                salt BLOB NOT NULL,
                verifier BLOB NOT NULL,
                role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('member','admin')),
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','active','suspended')),
                created_at INTEGER NOT NULL
              );
              CREATE TABLE IF NOT EXISTS verification_codes (
                digest TEXT PRIMARY KEY, email TEXT NOT NULL, expires INTEGER NOT NULL
              );
              CREATE TABLE IF NOT EXISTS verified_members (
                email TEXT PRIMARY KEY, user_id INTEGER UNIQUE NOT NULL REFERENCES users(id)
              );
              CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                csrf TEXT NOT NULL, expires_at INTEGER NOT NULL
              );
              CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                official INTEGER NOT NULL DEFAULT 0,
                position INTEGER NOT NULL
              );
              CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY,
                category_id INTEGER NOT NULL REFERENCES categories(id),
                author_id INTEGER NOT NULL REFERENCES users(id),
                title TEXT NOT NULL, body TEXT NOT NULL,
                pinned INTEGER NOT NULL DEFAULT 0, locked INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
              );
              CREATE TABLE IF NOT EXISTS replies (
                id INTEGER PRIMARY KEY,
                topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
                author_id INTEGER NOT NULL REFERENCES users(id),
                body TEXT NOT NULL, created_at INTEGER NOT NULL
              );
              CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY,
                reporter_id INTEGER NOT NULL REFERENCES users(id),
                topic_id INTEGER NOT NULL REFERENCES topics(id),
                reason TEXT NOT NULL,
                handled INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
              );
              CREATE INDEX IF NOT EXISTS idx_topics_cat_recent ON topics(category_id, pinned DESC, updated_at DESC);
              CREATE INDEX IF NOT EXISTS idx_replies_topic ON replies(topic_id, created_at);
            ''')
            for idx, (ident, title, description, official) in enumerate(SECTIONS):
                db.execute('INSERT OR IGNORE INTO categories(slug,title,description,official,position) VALUES(?,?,?,?,?)',
                           (ident,title,description,official,idx))

            # The reserved byline contains a space, so it cannot be registered by a player.
            byline = 'Expanse Guides'
            db.execute("INSERT OR IGNORE INTO users(username,salt,verifier,status,created_at) VALUES(?,randomblob(16),randomblob(32),'suspended',?)",(byline,utc()))
            author = db.execute('SELECT id FROM users WHERE username=?',(byline,)).fetchone()['id']
            db.execute("UPDATE users SET status='suspended' WHERE id=? AND status!='suspended'", (author,))
            for slug,title,body in STARTER_GUIDES:
                db.execute("""INSERT INTO topics(category_id,author_id,title,body,pinned,created_at,updated_at)
                    SELECT c.id,?,?,?,1,?,? FROM categories c WHERE c.slug=?
                    AND NOT EXISTS (SELECT 1 FROM topics WHERE category_id=c.id AND author_id=? AND title=?)""",
                    (author,title,body,utc(),utc(),slug,author,title))

    def bootstrap_admin(self, username: str, password: str):
        if not NAME.fullmatch(username) or not 12 <= len(password) <= 128:
            raise ValueError('Admin username or password does not meet the minimum requirements.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            admins = db.execute("SELECT id,username,salt,verifier FROM users WHERE role='admin' ORDER BY id").fetchall()
            owner = db.execute('SELECT id,role FROM users WHERE username=?', (username,)).fetchone()
            if owner and owner['role'] != 'admin':
                raise ValueError('Admin username conflicts with an existing account.')
            if admins:
                if owner:
                    admin = next(row for row in admins if row['id'] == owner['id'])
                elif len(admins) == 1:
                    admin = admins[0]
                else:
                    raise ValueError('Multiple forum administrators exist. Select an existing administrator.')
                if admin['username'] == username and hmac.compare_digest(admin['verifier'], password_digest(password, admin['salt'])):
                    return
                salt = secrets.token_bytes(16)
                db.execute('UPDATE users SET username=?,salt=?,verifier=? WHERE id=?',
                           (username, salt, password_digest(password,salt), admin['id']))
                db.execute('DELETE FROM sessions WHERE user_id=?', (admin['id'],))
                return
            salt = secrets.token_bytes(16)
            db.execute('INSERT INTO users(username,salt,verifier,role,status,created_at) VALUES(?,?,?,?,?,?)',
                       (username,salt,password_digest(password,salt),'admin','active',utc()))

    def member_for_token(self, raw: str | None):
        if not raw:
            return None
        with self.db() as db:
            row = db.execute('''SELECT u.id,u.username,u.role,u.status,s.csrf,s.token_hash
                                FROM sessions s JOIN users u ON u.id=s.user_id
                                WHERE s.token_hash=? AND s.expires_at>? AND u.status='active' ''',
                             (hash_token(raw),utc())).fetchone()
            return dict(row) if row else None


class Forum:
    def __init__(self, store: Store, secure: bool = True, registration_enabled: bool = False):
        self.store = store
        self.secure = secure
        self.email_signup = os.environ.get('EXPANSE_COMMUNITY_REGISTRATION_MODE') == 'email'
        directory = os.environ.get('EXPANSE_COMMUNITY_DATA_DIR')
        persistent = bool(directory and os.path.ismount(directory))
        self.registration_enabled = registration_enabled or (persistent and (
            os.environ.get('EXPANSE_COMMUNITY_REGISTRATION_MODE') == 'manual' or self.email_signup and bool(
            os.environ.get('RESEND_API_KEY') and os.environ.get('EXPANSE_COMMUNITY_MAIL_FROM')
            )))
        self.failed = {}

    def member(self, req):
        if 'expanse_member' not in req:
            req['expanse_member'] = self.store.member_for_token(req.cookies.get('expanse_forum'))
        return req['expanse_member']

    def require_member(self, req):
        user = self.member(req)
        if not user:
            raise web.HTTPForbidden(text='Sign in with an approved community account.')
        return user

    def csrf(self, req, user):
        supplied = req.get('expanse_form_csrf')
        if not supplied or not hmac.compare_digest(str(supplied), user['csrf']):
            raise web.HTTPForbidden(text='Invalid form token. Reload the page and retry.')

    async def post_data(self, req):
        if req.content_length is not None and req.content_length > 12_000:
            raise web.HTTPRequestEntityTooLarge(max_size=12_000, actual_size=req.content_length)
        form = await req.post()
        req['expanse_form_csrf'] = str(form.get('csrf',''))
        return form

    def nav(self, user):
        session_links = ('<a href="/admin">Moderate</a> ' if user and user['role']=='admin' else '')
        if user:
            session_links += ('<span class="signed-in">' + escape(user['username']) + '</span>'
                + '<form method="post" action="/logout"><input type="hidden" name="csrf" value="'
                + escape(user['csrf']) + '"><button type="submit" class="plain">Sign out</button></form>')
        else:
            session_links += '<a href="/login">Sign in</a>' + (' <a href="/register">Register</a>' if self.registration_enabled else '')
        return ('''<header class="mast"><div><a class="wordmark" href="/">EXPANSE <span>COMMUNITY</span></a>
         <div class="subtitle">A living world. A place to talk about it.</div></div>
         <nav aria-label="Site"><a href="/">Forum</a><a href="https://expansemud.com/wiki/">Wiki</a>
         <a href="https://expansemud.com/">Game</a>'''+session_links+'''</nav></header>''')

    def page(self, title, content, user=None, *, status=200):
        doc = '''<!doctype html><html lang="en"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <meta name="color-scheme" content="dark"><title>'''+escape(title)+''' · Expanse Community</title>
        <link rel="stylesheet" href="/style.css"><link rel="stylesheet" href="/emotes.css"></head><body><div class="shell">'''+self.nav(user)+'''
        <main id="main">'''+('<p class="note">Read-only preview. Browse the guides below. Player registration and posting are closed.</p>' if not self.registration_enabled and not user else '')+content+'''</main><footer>Official Expanse community · Independent, creator-directed and AI-assisted.
        <a href="https://expansemud.com/">expansemud.com</a></footer></div></body></html>'''
        return web.Response(text=doc, content_type='text/html', status=status,
                            headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
                                     'Referrer-Policy':'same-origin','X-Frame-Options':'DENY',
                                     'Content-Security-Policy':"default-src 'self'; style-src 'self'; img-src 'self' data:; script-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"})

    def message(self, req, title, paragraph, status=200):
        return self.page(title, '<div class="panel"><h1>'+escape(title)+'</h1><p>'+escape(paragraph)+'</p><a href="/">Return to categories</a></div>',
                         self.member(req),status=status)

    async def home(self, req):
        user=self.member(req)
        parts=['''<div class="hero"><p class="eyebrow">EXPANSEMUD / COMMUNITY</p>
          <h1>News, discoveries and conversations.</h1><p>Official service notices, game help, development ideas and player conversations.
          The shared MMO is still in development; this forum does not enable multiplayer.</p></div>''']
        with self.store.db() as db:
            categories=db.execute('SELECT * FROM categories ORDER BY position').fetchall()
            for cat in categories:
                topics=db.execute('''SELECT t.id,t.title,t.updated_at,t.pinned, u.username FROM topics t
                                     JOIN users u ON u.id=t.author_id WHERE t.category_id=?
                                     ORDER BY t.pinned DESC,t.updated_at DESC LIMIT 3''',(cat['id'],)).fetchall()
                parts.append('<section class="category panel"><div><h2><a href="/c/'+escape(cat['slug'])+'">'+escape(cat['title'])+'</a></h2>'
                             +'<p>'+escape(cat['description'])+'</p></div>')
                if topics:
                    parts.append('<div class="latest"><h3>Recent topics</h3><ul>')
                    for topic in topics:
                        parts.append('<li><a href="/t/'+str(topic['id'])+'">'+escape(topic['title'])+'</a> <small>'+escape(topic['username'])+'</small></li>')
                    parts.append('</ul></div>')
                parts.append('</section>')
        if not user and self.registration_enabled and not self.email_signup:
            parts.append('<p class="note">Reading is public. New community accounts require staff approval before posting.</p>')
        return self.page('Community Forum',''.join(parts),user)

    async def category(self,req):
        user=self.member(req);key=req.match_info['slug']
        try: offset=max(0,min(2000,int(req.query.get('offset','0'))))
        except ValueError: offset=0
        with self.store.db() as db:
            cat=db.execute('SELECT * FROM categories WHERE slug=?',(key,)).fetchone()
            if not cat: raise web.HTTPNotFound()
            topics=db.execute('''SELECT t.*,u.username,(SELECT COUNT(*) FROM replies r WHERE r.topic_id=t.id) AS replies
                                 FROM topics t JOIN users u ON u.id=t.author_id WHERE t.category_id=?
                                 ORDER BY pinned DESC,updated_at DESC LIMIT ? OFFSET ?''',(cat['id'],PAGESIZE,offset)).fetchall()
        parts=['<div class="section-heading"><div><p class="eyebrow">FORUM</p><h1>'+escape(cat['title'])+'</h1><p>'+escape(cat['description'])+'</p></div>']
        if user and (not cat['official'] or user['role']=='admin'):
            parts.append('<a class="button" href="/new?category='+quote(key)+'">New topic</a>')
        parts.append('</div><div class="panel topic-list">')
        if not topics: parts.append('<p>No topics yet.</p>')
        for topic in topics:
            parts.append('<article class="topic-row"><div><a href="/t/'+str(topic['id'])+'">'
                         + ('<span class="pin">Pinned</span> ' if topic['pinned'] else '')
                         +escape(topic['title'])+'</a><small>By '+escape(topic['username'])+' · '+label_time(topic['updated_at'])+'</small></div>'
                         +'<span>'+str(topic['replies'])+' replies</span></article>')
        parts.append('</div>')
        if len(topics)==PAGESIZE:parts.append('<a class="button" href="?offset='+str(offset+PAGESIZE)+'">Older topics</a>')
        return self.page(cat['title'],''.join(parts),user)

    async def topic(self,req):
        user=self.member(req);tid=int(req.match_info['id'])
        with self.store.db() as db:
            t=db.execute('''SELECT t.*,u.username,c.slug AS category_slug,c.title AS category_title
                            FROM topics t JOIN users u ON u.id=t.author_id
                            JOIN categories c ON c.id=t.category_id WHERE t.id=?''',(tid,)).fetchone()
            if not t:raise web.HTTPNotFound()
            replies=db.execute('SELECT r.*,u.username FROM replies r JOIN users u ON u.id=r.author_id WHERE topic_id=? ORDER BY created_at,id LIMIT 250',(tid,)).fetchall()
        parts=['<p class="eyebrow"><a href="/c/'+escape(t['category_slug'])+'">'+escape(t['category_title'])+'</a></p>'
               '<article class="panel post"><h1>'+escape(t['title'])+'</h1><p class="byline">'
               +escape(t['username'])+' · '+label_time(t['created_at'])+'</p>'+text_html(t['body'])+'</article>']
        if t['locked']:parts.append('<p class="note">This topic is closed to replies.</p>')
        for reply in replies:
            parts.append('<article class="panel reply"><p class="byline">'+escape(reply['username'])+' · '+label_time(reply['created_at'])+'</p>'
                         +text_html(reply['body'])+'</article>')
        if user and not t['locked']:
            parts.append('<section class="panel"><h2>Write a reply</h2><form method="post" action="/reply">'
                         '<input type="hidden" name="topic_id" value="'+str(tid)+'"><input type="hidden" name="csrf" value="'+escape(user['csrf'])+'">'
                         '<label for="body">Your reply</label><textarea id="body" name="body" maxlength="4000" required></textarea>'
                         '<button type="submit">Post reply</button></form></section>')
        if user and user['role']=='admin':
            parts.append('<div class="panel"><h2>Moderator actions</h2><form method="post" action="/moderate">'
                         '<input type="hidden" name="topic_id" value="'+str(tid)+'"><input type="hidden" name="csrf" value="'+escape(user['csrf'])+'">'
                         '<button name="action" value="'+('unpin' if t['pinned'] else 'pin')+'">'+('Unpin' if t['pinned'] else 'Pin')+'</button> '
                         '<button name="action" value="'+('unlock' if t['locked'] else 'lock')+'">'+('Unlock' if t['locked'] else 'Lock')+'</button></form></div>')
        if user:
            parts.append('<details class="panel"><summary>Report this topic</summary><form method="post" action="/report">'
                         '<input type="hidden" name="topic_id" value="'+str(tid)+'"><input type="hidden" name="csrf" value="'+escape(user['csrf'])+'">'
                         '<label for="reason">Reason for staff review</label><textarea id="reason" name="reason" maxlength="1000" required></textarea>'
                         '<button type="submit">Send report</button></form></details>')
        return self.page(t['title'],''.join(parts),user)

    async def new(self,req):
        user=self.require_member(req);cat=req.query.get('category','discussion')
        with self.store.db() as db:
            cats=db.execute('SELECT slug,title,official FROM categories ORDER BY position').fetchall()
        options=''.join('<option value="'+escape(c['slug'])+'" '+('selected' if cat==c['slug'] else '')+'>'+escape(c['title'])+'</option>'
                        for c in cats if not c['official'] or user['role']=='admin')
        return self.page('New topic','''<div class="panel compose"><h1>Start a conversation</h1><form method="post" action="/new">
          <input type="hidden" name="csrf" value="'''+escape(user['csrf'])+'''"><label for="category">Category</label><select id="category" name="category">'''+options+'''</select>
          <label for="title">Title</label><input id="title" name="title" minlength="4" maxlength="120" required>
          <label for="body">Message</label><textarea id="body" name="body" maxlength="8000" required></textarea>
          <p class="note">Be constructive and protect other people's privacy. Do not post passwords, recovery codes or personal data.</p>
          <button type="submit">Publish topic</button></form></div>''',user)

    async def post_new(self,req):
        user=self.require_member(req);form=await self.post_data(req);self.csrf(req,user)
        try:title=valid_text(str(form.get('title','')),120,'Title');body=valid_text(str(form.get('body','')),POST_MAX,'Message')
        except ValueError as exc:return self.message(req,'Invalid topic',str(exc),400)
        with self.store.db() as db:
            cat=db.execute('SELECT * FROM categories WHERE slug=?',(form.get('category',''),)).fetchone()
            if not cat:raise web.HTTPBadRequest(text='Choose a category.')
            if cat['official'] and user['role']!='admin':raise web.HTTPForbidden(text='Only staff can announce official news.')
            if user['role']!='admin' and db.execute('SELECT count(*) FROM topics WHERE author_id=? AND created_at>?',(user['id'],utc()-60)).fetchone()[0]:
                raise web.HTTPTooManyRequests(text='Please allow a minute between topics.')
            cur=db.execute('INSERT INTO topics(category_id,author_id,title,body,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                           (cat['id'],user['id'],title,body,utc(),utc()))
            tid=cur.lastrowid
        raise web.HTTPSeeOther('/t/'+str(tid))

    async def post_reply(self,req):
        user=self.require_member(req);form=await self.post_data(req);self.csrf(req,user)
        try:tid=int(form.get('topic_id','0'));body=valid_text(str(form.get('body','')),REPLY_MAX,'Reply')
        except (ValueError,TypeError):raise web.HTTPBadRequest(text='Invalid reply.')
        with self.store.db() as db:
            topic=db.execute('SELECT locked FROM topics WHERE id=?',(tid,)).fetchone()
            if not topic:raise web.HTTPNotFound()
            if topic['locked']:raise web.HTTPForbidden(text='Topic locked.')
            if user['role']!='admin' and db.execute('SELECT count(*) FROM replies WHERE author_id=? AND created_at>?',(user['id'],utc()-15)).fetchone()[0]:
                raise web.HTTPTooManyRequests(text='Please wait between replies.')
            db.execute('INSERT INTO replies(topic_id,author_id,body,created_at) VALUES(?,?,?,?)',
                       (tid,user['id'],body,utc()))
            db.execute('UPDATE topics SET updated_at=? WHERE id=?',(utc(),tid))
        raise web.HTTPSeeOther('/t/'+str(tid))

    async def register(self,req):
        if not self.registration_enabled:
            return self.message(req, 'Registration closed', 'Community accounts are not open while security and recovery safeguards are being completed.', 503)
        return self.page('Create account', self.registration_form(), self.member(req))

    def registration_form(self):
        if self.email_signup:
            return ('<section class="panel compose"><h2>Create a forum account</h2>'
                    '<form action="/verify-email" method="post"><label for="signup-email">Email address</label>'
                    '<input id="signup-email" type="email" name="email" autocomplete="email" required>'
                    '<button>Send verification code</button></form></section>')
        return self.credentials_form()

    def credentials_form(self, email_input=''):
        return '''<div class="panel compose"><h2>Create a forum account</h2>
         <p>'''+('Enter the code from your email to activate your account.' if email_input else 'Registration requests require staff approval.')+'''
         Community accounts are separate from Expanse game accounts.</p>
         <form method="post" action="/register">'''+email_input+'''<label for="new-username">Username</label>
         <input id="new-username" name="username" minlength="3" maxlength="24" pattern="[A-Za-z0-9][A-Za-z0-9_\\-]{2,23}" autocomplete="username" required>
         <label for="new-password">Password (12 or more characters)</label>
         <input id="new-password" type="password" name="password" minlength="12" maxlength="128" autocomplete="new-password" required>
         <button type="submit">Create account</button></form><p class="note">Account recovery by email is planned but not available in this staging version.
         Avoid reusing a password from your game account.</p></div>'''

    async def verify_email(self, req):
        if not self.registration_enabled or not self.email_signup:
            raise web.HTTPServiceUnavailable()
        self.limit('send-code:'+str(req.remote), 3, 300)
        email = str((await self.post_data(req)).get('email','')).strip().lower()
        if len(email)>254 or not re.fullmatch(r'[^@,;<>\s]+@[^@,;<>\s]+\.[^@,;<>\s]+',email):
            raise web.HTTPBadRequest(text='Enter a valid email address.')
        code = secrets.token_urlsafe(18)
        digest = hash_token(code)
        with self.store.db() as db:
            db.execute('DELETE FROM verification_codes WHERE expires<=?',(utc(),))
            if db.execute('SELECT 1 FROM verification_codes WHERE email=? AND expires>?',(email,utc()+840)).fetchone():
                raise web.HTTPTooManyRequests(text='Wait a minute before requesting another code.')
            db.execute('INSERT INTO verification_codes VALUES(?,?,?)',(digest,email,utc()+900))
        try:
            async with ClientSession(timeout=ClientTimeout(total=15)) as client:
                async with client.post('https://api.resend.com/emails',
                        headers={'Authorization':'Bearer '+os.environ['RESEND_API_KEY']},
                        json={'from':os.environ['EXPANSE_COMMUNITY_MAIL_FROM'],'to':[email],
                              'subject':'Your Expanse forum verification code',
                              'text':'Your code is '+code+' and expires in 15 minutes. If you did not request it, ignore this email.'}) as response:
                    response.raise_for_status()
        except (ClientError,TimeoutError):
            with self.store.db() as db:
                db.execute('DELETE FROM verification_codes WHERE digest=?',(digest,))
            raise web.HTTPServiceUnavailable(text='Email delivery is unavailable. Please try again.')
        fields = ('<label for="code">Verification code</label>'
                  '<input id="code" name="code" autocomplete="one-time-code" required>')
        return self.page('Verify your email', self.credentials_form(fields))

    def limit(self,key,max_attempts=6,period=60):
        now=utc();bucket=[t for t in self.failed.get(key,[]) if t>now-period]
        if len(bucket)>=max_attempts:raise web.HTTPTooManyRequests(text='Too many attempts. Try later.')
        bucket.append(now);self.failed[key]=bucket

    async def post_register(self,req):
        if not self.registration_enabled:
            raise web.HTTPServiceUnavailable(text='Community registration is closed until the release gate passes.')
        self.limit('register:'+str(req.remote),3,300)
        form=await self.post_data(req);username=str(form.get('username','')).strip();password=str(form.get('password',''))
        if not NAME.fullmatch(username) or not 12<=len(password)<=128:
            return self.message(req,'Invalid registration','Choose a 3–24 character username and a password of at least 12 characters.',400)
        salt=secrets.token_bytes(16)
        try:
            with self.store.db() as db:
                if self.email_signup:
                    db.execute('BEGIN IMMEDIATE')
                    digest = hash_token(str(form.get('code','')).strip())
                    row = db.execute('SELECT email FROM verification_codes WHERE digest=? AND expires>?',(digest,utc())).fetchone()
                    if row is None:
                        raise web.HTTPBadRequest(text='Verification code is invalid or expired.')
                    member = db.execute("INSERT INTO users(username,salt,verifier,status,created_at) VALUES(?,?,?,'active',?)",
                                        (username,salt,password_digest(password,salt),utc()))
                    db.execute('INSERT INTO verified_members VALUES(?,?)',(row['email'],member.lastrowid))
                    db.execute('DELETE FROM verification_codes WHERE email=?',(row['email'],))
                    return self.page('Account created','<h1>Account created</h1><a href="/login">Sign in to the forum</a>')
                db.execute('INSERT INTO users(username,salt,verifier,created_at) VALUES(?,?,?,?)',
                           (username,salt,password_digest(password,salt),utc()))
        except sqlite3.IntegrityError:
            return self.message(req,'Name unavailable','Please choose a different community username.',409)
        return self.message(req,'Registration received','An administrator must approve your account before you can sign in and post.')

    async def login(self,req):
        signup = self.registration_form() if self.registration_enabled else '<p>New player registration is currently closed.</p>'
        return self.page('Sign in','''<div class="panel compose"><h1>Community sign in</h1><form method="post" action="/login">
         <label for="username">Username</label><input id="username" name="username" autocomplete="username" required>
         <label for="password">Password</label><input type="password" id="password" name="password" autocomplete="current-password" required>
         <button type="submit">Sign in</button></form><p class="note">These are separate community credentials. This prototype does not reset passwords by email.</p></div>'''+signup,self.member(req))

    async def post_login(self,req):
        self.limit('login:'+str(req.remote),8,120)
        form=await self.post_data(req);username=str(form.get('username','')).strip();password=str(form.get('password',''))
        row=None
        with self.store.db() as db:
            row=db.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
            if row:
                check=password_digest(password,row['salt'])
            else:
                check=password_digest(password,b'\x00'*16)
            if not row or not hmac.compare_digest(row['verifier'],check) or row['status']!='active':
                return self.message(req,'Could not sign in','Credentials or account approval not valid.',403)
            raw=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(28)
            db.execute('INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES(?,?,?,?)',
                       (hash_token(raw),row['id'],csrf,utc()+SESSION_AGE))
        resp=web.HTTPSeeOther('/')
        resp.set_cookie('expanse_forum',raw,max_age=SESSION_AGE,httponly=True,secure=self.secure,samesite='Lax',path='/')
        raise resp

    async def logout(self,req):
        user=self.require_member(req);await self.post_data(req);self.csrf(req,user)
        raw=req.cookies.get('expanse_forum')
        with self.store.db() as db:
            db.execute('DELETE FROM sessions WHERE token_hash=?',(hash_token(raw),))
        resp=web.HTTPSeeOther('/')
        resp.del_cookie('expanse_forum',path='/');raise resp

    async def admin(self,req):
        user=self.require_member(req)
        if user['role']!='admin':raise web.HTTPForbidden()
        with self.store.db() as db:
            accounts=db.execute("SELECT * FROM users WHERE role='member' AND username!='Expanse Guides' ORDER BY status,created_at DESC LIMIT 100").fetchall()
            reports=db.execute('''SELECT r.*,u.username,t.title FROM reports r JOIN users u ON u.id=r.reporter_id
                                  JOIN topics t ON t.id=r.topic_id WHERE handled=0 ORDER BY r.created_at DESC LIMIT 100''').fetchall()
        parts=['<h1>Community moderation</h1><div class="panel"><h2>Forum members</h2>']
        if not accounts: parts.append('<p>No player accounts to review.</p>')
        for row in accounts:
            buttons = []
            if row['status'] != 'active':
                label = 'Restore' if row['status'] == 'suspended' else 'Approve'
                buttons.append('<button name="action" value="approve">'+label+'</button>')
            if row['status'] != 'suspended':
                buttons.append('<button name="action" value="suspend">Suspend</button>')
            parts.append('<form method="post" action="/admin/member" class="admin-row"><input type="hidden" name="csrf" value="'+escape(user['csrf'])+'">'
                         '<input type="hidden" name="user_id" value="'+str(row['id'])+'"><span>'+escape(row['username'])+' ('+escape(row['status'])+')</span> '
                         + ' '.join(buttons) + '</form>')
        parts.append('</div><div class="panel"><h2>Unresolved reports</h2>')
        if not reports: parts.append('<p>No unresolved reports.</p>')
        for row in reports:
            parts.append('<form method="post" action="/admin/report" class="admin-row"><input type="hidden" name="csrf" value="'+escape(user['csrf'])+'">'
                         '<input type="hidden" name="report_id" value="'+str(row['id'])+'"><span>'+escape(row['username'])+' reported '
                         '<a href="/t/'+str(row['topic_id'])+'">'+escape(row['title'])+'</a>: '+escape(row['reason'])+'</span>'
                         '<button name="action" value="close">Mark reviewed</button></form>')
        parts.append('</div>')
        return self.page('Moderation',''.join(parts),user)

    async def admin_member(self,req):
        user=self.require_member(req);form=await self.post_data(req);self.csrf(req,user)
        if user['role']!='admin':raise web.HTTPForbidden()
        try:member_id=int(form.get('user_id','0'))
        except ValueError:raise web.HTTPBadRequest()
        action=str(form.get('action',''))
        if action not in ('approve','suspend'):raise web.HTTPBadRequest()
        with self.store.db() as db:
            updated = db.execute("UPDATE users SET status=? WHERE id=? AND role='member' AND username!='Expanse Guides'",('active' if action=='approve' else 'suspended',member_id))
            if not updated.rowcount: raise web.HTTPNotFound()
            if action=='suspend':db.execute('DELETE FROM sessions WHERE user_id=?',(member_id,))
        raise web.HTTPSeeOther('/admin')

    async def admin_report(self,req):
        user=self.require_member(req);form=await self.post_data(req);self.csrf(req,user)
        if user['role']!='admin':raise web.HTTPForbidden()
        try: report_id=int(form.get('report_id','0'))
        except ValueError:raise web.HTTPBadRequest()
        if form.get('action')!='close':raise web.HTTPBadRequest()
        with self.store.db() as db:db.execute('UPDATE reports SET handled=1 WHERE id=?',(report_id,))
        raise web.HTTPSeeOther('/admin')

    async def moderate(self,req):
        user=self.require_member(req);form=await self.post_data(req);self.csrf(req,user)
        if user['role']!='admin':raise web.HTTPForbidden()
        try:tid=int(form.get('topic_id','0'))
        except ValueError:raise web.HTTPBadRequest()
        changes={'pin':('pinned',1),'unpin':('pinned',0),'lock':('locked',1),'unlock':('locked',0)}
        if form.get('action') not in changes:raise web.HTTPBadRequest()
        field,value=changes[form['action']]
        with self.store.db() as db:db.execute('UPDATE topics SET '+field+'=? WHERE id=?',(value,tid))
        raise web.HTTPSeeOther('/t/'+str(tid))

    async def report(self,req):
        user=self.require_member(req);form=await self.post_data(req);self.csrf(req,user)
        try:tid=int(form.get('topic_id','0'));reason=valid_text(str(form.get('reason','')),1000,'Reason')
        except ValueError:raise web.HTTPBadRequest()
        with self.store.db() as db:
            if not db.execute('SELECT 1 FROM topics WHERE id=?',(tid,)).fetchone():raise web.HTTPNotFound()
            db.execute('INSERT INTO reports(reporter_id,topic_id,reason,created_at) VALUES(?,?,?,?)',(user['id'],tid,reason,utc()))
        raise web.HTTPSeeOther('/t/'+str(tid))

    async def rss(self,req):
        with self.store.db() as db:
            topics=db.execute('''SELECT t.id,t.title,t.body,t.created_at FROM topics t JOIN categories c ON c.id=t.category_id
                                 WHERE c.official=1 ORDER BY t.created_at DESC LIMIT 20''').fetchall()
        items=''.join('<item><title>'+xml_escape(t['title'])+'</title><link>https://community.expansemud.com/t/'+str(t['id'])+'</link>'
                      '<guid>https://community.expansemud.com/t/'+str(t['id'])+'</guid>'
                      '<description>'+xml_escape(t['body'][:1000])+'</description></item>' for t in topics)
        xml=('<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel><title>ExpanseMUD Official News</title>'
             '<link>https://community.expansemud.com/</link><description>Official development and server status announcements</description>'+items+'</channel></rss>')
        return web.Response(text=xml,content_type='application/rss+xml',headers={'Cache-Control':'public, max-age=120'})


def make_app(db_path: Path | None = None, *, secure: bool = True, bootstrap: tuple[str,str] | None = None, registration_enabled: bool = False):
    path = db_path or Path(os.environ.get('EXPANSE_COMMUNITY_DATA_DIR','./.community-data'))/'community.sqlite3'
    store = Store(path)
    if bootstrap is None and db_path is None:
        username = os.environ.get('EXPANSE_COMMUNITY_ADMIN_USER', '')
        password = os.environ.get('EXPANSE_COMMUNITY_ADMIN_PASSWORD', '')
        if username or password:
            bootstrap = (username, password)
    if bootstrap:
        store.bootstrap_admin(*bootstrap)
    forum = Forum(store, secure=secure, registration_enabled=registration_enabled)

    @web.middleware
    async def guard(req,handler):
        if req.method == 'POST':
            origin=req.headers.get('Origin','')
            if origin:
                expected=f"{req.scheme}://{req.host}"
                # Behind Render, HTTPS terminates at the edge; browser Origin remains HTTPS.
                if origin not in {expected, 'https://'+req.host}:
                    raise web.HTTPForbidden(text='Unexpected request origin.')
            elif req.headers.get('Sec-Fetch-Site') not in (None,'same-origin','none'):
                raise web.HTTPForbidden(text='Unexpected cross-site request.')
        resp=await handler(req)
        if isinstance(resp,web.StreamResponse):
            resp.headers.setdefault('X-Content-Type-Options','nosniff')
            resp.headers.setdefault('Referrer-Policy','same-origin')
            resp.headers.setdefault('X-Frame-Options','DENY')
        return resp

    app=web.Application(client_max_size=16_000,middlewares=[guard])
    forum_key=web.AppKey('forum', Forum)
    app[forum_key]=forum

    async def health(req):
        return web.json_response({'status':'ok','service':'expanse-community-staging'}, headers={'Access-Control-Allow-Origin':'*','Cache-Control':'no-store'})

    async def directory(req):
        with store.db() as db:
            categories = [dict(row) for row in db.execute('SELECT slug,title FROM categories ORDER BY position')]
            topics = [dict(row) for row in db.execute('SELECT id,title FROM topics ORDER BY updated_at DESC,id DESC LIMIT 25')]
        return web.json_response({'categories':categories,'topics':topics,'registration_open':forum.registration_enabled}, headers={'Access-Control-Allow-Origin':'*','Cache-Control':'no-store'})

    async def emote_styles(req):
        web_css = Path(__file__).resolve().parents[1]/'web/community-emotes.css'
        return web.Response(text=web_css.read_text() + Path(__file__).with_name('emote-positions.css').read_text(),
                            content_type='text/css',headers={'Cache-Control':'public,max-age=3600'})
    async def stylesheet(req):
        return web.FileResponse(STYLESHEET,headers={'Cache-Control':'public,max-age=3600'})
    app.add_routes([
        web.get('/',forum.home),web.get('/c/{slug}',forum.category),web.get('/t/{id:\\d+}',forum.topic),
        web.get('/new',forum.new),web.post('/new',forum.post_new),web.post('/reply',forum.post_reply),
        web.post('/verify-email',forum.verify_email),web.get('/register',forum.register),web.post('/register',forum.post_register),
        web.get('/login',forum.login),web.post('/login',forum.post_login),web.post('/logout',forum.logout),
        web.get('/admin',forum.admin),web.post('/admin/member',forum.admin_member),web.post('/admin/report',forum.admin_report),
        web.post('/moderate',forum.moderate),web.post('/report',forum.report),web.get('/news.rss',forum.rss),
        web.get('/healthz',health), web.get('/api/public/directory',directory),
        web.get('/style.css',stylesheet),web.get('/emotes.css',emote_styles),
    ])
    return app


def mount_forum(game, data_root, *, bootstrap):
    """Serve a disk-backed forum under /forum while retaining standalone routes."""
    if not os.path.ismount(data_root):
        raise RuntimeError('Forum storage must be on the mounted game disk.')
    app = make_app(Path(data_root) / 'community' / 'community.sqlite3',
                   bootstrap=bootstrap, registration_enabled=True)

    @web.middleware
    async def prefix_links(req, handler):
        try:
            response = await handler(req)
        except web.HTTPRedirection as redirect:
            location = redirect.headers.get('Location', '')
            if location.startswith('/') and not location.startswith('//'):
                redirect.headers['Location'] = '/forum' + location
            for cookie in redirect.cookies.values():
                cookie['path'] = '/forum'
            raise
        if isinstance(response, web.Response) and response.content_type == 'text/html':
            response.text = response.text.replace('href="/', 'href="/forum/').replace('action="/', 'action="/forum/')
        return response

    app.middlewares.insert(0, prefix_links)
    game.add_subapp('/forum', app)
    return app


if __name__=='__main__':
    root=Path(os.environ.get('EXPANSE_COMMUNITY_DATA_DIR','./.community-data')).resolve()
    admin_username=os.environ.get('EXPANSE_COMMUNITY_ADMIN_USER','')
    admin_password=os.environ.get('EXPANSE_COMMUNITY_ADMIN_PASSWORD','')
    if not admin_username or not admin_password:
        raise SystemExit('Set EXPANSE_COMMUNITY_ADMIN_USER and EXPANSE_COMMUNITY_ADMIN_PASSWORD through the Render secret environment. Never commit them.')
    web.run_app(make_app(root/'community.sqlite3',bootstrap=(admin_username,admin_password), registration_enabled=os.environ.get('EXPANSE_COMMUNITY_ALLOW_REGISTRATION')=='acknowledge-incomplete-recovery'),host='0.0.0.0',port=int(os.environ.get('PORT',10000)))