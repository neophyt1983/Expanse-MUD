"""Private single-player Expanse, served through one public HTTP/WebSocket port."""
import asyncio
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
import hashlib
import hmac
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
import re
import secrets
import socket
import sqlite3
import sys
import tempfile
import time
from urllib.parse import quote, urlsplit
import zipfile

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web
from server import world_catalogue
from server.accounts import display_name, name_key
from server.save_slots import DB as SLOTS_DB
from server.public_access import PublicGuests, GuestLimit
from server.player_accounts import RegisteredPlayers, RegistrationError

ROOT = Path(__file__).resolve().parent
CSS = """body{background:#10171c;color:#e2e9e6;font:1rem/1.6 system-ui;margin:auto;padding:2rem 1rem;max-width:37rem}
h1{color:#95d9ad;font-family:Georgia,serif}h2{font-size:1.2rem;margin-top:2rem}
input,button,a.button{font:inherit;padding:.55rem .85rem;border-radius:.4rem}
input{max-width:92%;display:block;margin:.2rem 0 1rem}button,a.button{background:#314c41;color:white;border:1px solid #789789;cursor:pointer}
a{color:#aee6c0}form{margin:1rem 0}small{color:#bdc7c2}
.world-card{border:1px solid #52675e;border-radius:.65rem;padding:1.1rem;margin:1rem 0;min-width:0;overflow-wrap:anywhere}
.world-card h2{margin:0;font-size:1.2rem;line-height:1.5}.world-card p{margin:.6rem 0}
.world-meta,.world-links{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem .85rem}
.world-meta{margin:.65rem 0}.world-links{gap:.4rem 1rem}.world-links a{padding:.35rem 0}
.world-card form{margin:.85rem 0 .4rem}.world-card button{max-width:100%;min-height:44px;white-space:normal}
.world-badge{display:inline-block;border:1px solid #789789;border-radius:.35rem;padding:.1rem .5rem;font-size:.85rem;line-height:1.6}
.world-badge.latest{background:#254b37;color:#c2f5d2;border-color:#89c79c}.world-badge.older{color:#cbd4cf;border-color:#66776f}
.world-file{display:block;color:#bdc7c2;font-size:.9rem}.world-file code{color:inherit;font-size:inherit}
.world-note{color:#d0d9d4}.recovery-code{display:block;overflow-wrap:anywhere;word-break:break-all;background:#182b30;border:1px solid #52675e;border-radius:.4rem;padding:.75rem}button:focus-visible,a:focus-visible{outline:2px solid #b9f0cc;outline-offset:3px}
@media(max-width:420px){.world-card{padding:.85rem}body{padding:1.1rem .75rem}}"""
CSS += """
:root{color-scheme:dark}
body{font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:760px;
  background: radial-gradient(circle at 78% 5%,#22483c 0,transparent 29%),
  radial-gradient(circle at 12% 40%,#202c3a 0,transparent 55%),#0d151d;
  color:#e4eae9;min-height:100vh;box-sizing:border-box;padding:1.75rem 1rem}
body:before{content:'✦';position:absolute;top:1.6rem;right:1.7rem;color:#d6bb73;opacity:.75;font-size:2rem}
main{background:linear-gradient(165deg,rgba(24,39,47,.96),rgba(13,23,28,.98));
  padding:clamp(1.2rem,5vw,2.8rem);border:1px solid #4c655d;border-radius:1.15rem;
  box-shadow:0 24px 75px #02060aaa}
h1{font-size:clamp(2rem,5vw,3.3rem);letter-spacing:.12em;margin:.1rem 0 .5rem;
  color:#e8d4a1;font-weight:650}
h2{color:#e4d19b;margin:1.5rem 0 .5rem}
p{margin:.7rem 0 1.2rem;max-width:65ch}hr{border:0;border-top:1px solid #46534f;margin:2rem 0}
label{font-weight:650;color:#d8e6e0;display:block;margin:.75rem 0}
input{display:block;width:100%;box-sizing:border-box;max-width:none;
  padding:.82rem 1rem;background:#0c191f;border:1px solid #6a817b;color:#eaf4ee;
  border-radius:.6rem;font-size:1rem;margin:.35rem 0 0;min-height:46px}
input:focus-visible{outline:2px solid #abd9b5;outline-offset:2px}
button,a.button{display:inline-flex;align-items:center;justify-content:center;
  padding:.7rem 1.1rem;min-height:44px;font-weight:650;border-radius:.6rem;
  color:#0a221c;background:#a5d6b4;border:1px solid #bddfc3;text-decoration:none}
button:hover,a.button:hover{background:#c4e9cc}a{color:#a9dfbd}
.kicker{letter-spacing:.18em;color:#9cb8b1;text-transform:uppercase;font-weight:750;font-size:.76rem}
.lead{font-size:1.1rem;color:#d7e2e1}
.auth-card{padding:1.15rem;border:1px solid #46675d;background:#12252b;border-radius:.8rem;margin:1.2rem 0}
.auth-card h2{margin-top:.2rem}
.auth-actions{display:flex;gap:.8rem;flex-wrap:wrap;align-items:center;margin-top:1rem}
.auth-actions button,.auth-actions a.button{flex:1 1 160px}
.alert{padding:.75rem 1rem;border:1px solid #9b7664;background:#432b29;color:#fff0e7;border-radius:.5rem}
.auth-foot{color:#adbfbb;font-size:.88rem;margin-top:1.25rem}
.recovery-code{font-size:clamp(.85rem,2.6vw,1.35rem);color:#d4f7d9;letter-spacing:.06em}
.brand-nav{display:flex;gap:1.4rem;flex-wrap:wrap;border-bottom:1px solid #526760;padding-bottom:.8rem;margin-bottom:1rem}
.brand-nav a{font-size:.87rem;color:#cbdacf;text-decoration:none}.brand-nav a:hover{text-decoration:underline}
.two-fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(225px,1fr));gap:.75rem}
.note{font-size:.88rem;color:#b8c9bf}
@media(max-width:450px){body{padding:.6rem}main{padding:1.1rem}.auth-card{padding:.9rem}}
"""
LIMIT = 128 * 1024 * 1024


def disk_mounted(path):
    if os.path.ismount(path):
        return True
    # Linux bind mounts can share a device ID with their parent.
    info = Path('/proc/self/mountinfo')
    return info.is_file() and any(row.split()[4] == str(path) for row in info.read_text().splitlines())


def page(title, body, status=200):
    return web.Response(content_type='text/html',status=status,text=(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" '
        'content="width=device-width, initial-scale=1"><title>'+escape(title)+' · Expanse</title>'
        '<style>'+CSS+'</style><main><nav class="brand-nav" aria-label="External links">'
        '<a href="https://expansemud.com/">Official website</a>'
        '<a href="https://expansemud.discourse.group/">Community forum</a></nav>'
        '<h1>'+escape(title)+'</h1>'+body+'</main></html>'))


def sign_in(error='', status=200, public=False, registered=False, mail=False, allow_signup=True):
    """Public-facing sign in. Existing invited/owner logins remain valid."""
    alert = '<p role="alert" class="alert">'+escape(error)+'</p>' if error else ''
    if registered:
        public_intro = ('<p class="kicker">A world to explore · a world to create</p>'
            '<p class="lead">Your adventure starts with a free account. Choose a name, keep your account recovery '
            'code private, and return to your manually saved world whenever you like.</p>'
            '<section class="auth-card"><h2>New to Expanse?</h2>'
            '<p>Build a character, explore a living civilization, learn magic, and create your own story.</p>'
            + ('<p><a class="button" href="/register">Create free player account</a></p>' if allow_signup else
               '<p>New registrations are temporarily closed. Existing players can sign in.</p>')
            + '</section>')
    elif public:
        public_intro = ('<section class="auth-card"><h2>Play free without a password</h2>'
               '<p>Start a private adventure instantly. Your browser keeps your access key. '
               'Save the recovery code shown after joining to return on another device.</p>'
               '<form method="post" action="/public/join"><button>Play without a password</button></form>'
               '<p>Already played? <a href="/public/return">Recover your adventure</a></p></section>')
    else:
        public_intro=''
    account_type = 'Sign in to Expanse' if registered else 'Owner and invited accounts'
    links = ('<p><a href="/forgot">Forgot your password?</a> &nbsp;·&nbsp; '
             '<a href="/public/return">Use an older guest recovery code</a></p>') if registered else ''
    return page('Expanse', public_intro+'<section class="auth-card"><h2>'+account_type+'</h2>'
                '<form method="post" action="/login"><label>Username'
                '<input name="name" autocomplete="username" maxlength="24" required></label><label>Password'
                '<input type="password" name="password" autocomplete="current-password" required></label>'
                '<button>Sign in</button></form>'+links+alert+'</section>'
                '<p class="auth-foot">Each person needs their own Expanse account. Browser tabs in the same profile share a login. '
                'Signing in with the same username on another device replaces that account&#39;s previous session. '
                'Gameplay uses manual saves only. Your website and forum accounts '
                'are separate from Expanse game accounts.</p>',status)


def recovery_screen(code, detail, name=None):
    return page('Save your recovery code',
        '<p class="lead">'+escape(detail)+'</p>'
        + ('<p>Player: <strong>'+escape(name)+'</strong></p>' if name else '')
        + '<div class="auth-card"><p class="kicker">Private recovery code — shown once</p>'
        + '<code class="recovery-code">'+escape(code)+'</code>'
        + '<p>Store it somewhere safe, separate from your password. It is a one-use proof of ownership.'
        + ' If you reset your password, the old code immediately stops working.</p>'
        + '<button type="button" onclick="navigator.clipboard.writeText(document.querySelector(&quot;.recovery-code&quot;).textContent)"'
        + ' aria-label="Copy recovery code">Copy recovery code</button></div>'
        + '<p><a class="button" href="/">Continue to Expanse</a></p>')


class Accounts:
    def __init__(self, public=None, registered=None):
        self.public = public
        self.registered = registered
        owner_name = os.environ.get('EXPANSE_OWNER_NAME','')
        owner_password = os.environ.get('EXPANSE_OWNER_PASSWORD','')
        if owner_name and owner_password:
            owner = display_name(owner_name)
            entries = [{'name':owner, 'password':owner_password,
                        'expires_at':os.environ.get('EXPANSE_OWNER_EXPIRES_AT')}]
            self.owner = name_key(owner)
        elif public and not owner_name and not owner_password:
            # Deliberately allow public play with no administrator configured;
            # owner-only imports and reporting are unavailable until configured.
            self.owner = ''
            entries = []
        else:
            raise ValueError('Set BOTH EXPANSE_OWNER_NAME and EXPANSE_OWNER_PASSWORD, or enable passwordless public play without either. Set a protected owner account for editor and report access.')
        extra = json.loads(os.environ.get('EXPANSE_GUESTS_JSON','[]'))
        if not isinstance(extra,list):
            raise ValueError('EXPANSE_GUESTS_JSON must be an array.')
        self.records = {}
        self.pepper = secrets.token_bytes(32)
        self.sessions = {}
        self.failures = {}
        for row in entries + extra:
            name = display_name(row['name'])
            key = name_key(name)
            password = row['password']
            if key in self.records or not isinstance(password,str) or not 15 <= len(password) <= 128:
                raise ValueError('Each private account needs a unique name and a 15–128 character password.')
            expiry = None
            if row.get('expires_at'):
                dt = datetime.fromisoformat(row['expires_at'].replace('Z','+00:00'))
                if dt.utcoffset() is None:
                    raise ValueError('Account expiration must include a UTC offset.')
                expiry = dt.timestamp()
            self.records[key] = (name, self.verifier(password), expiry)
        self.player_keys = set()
        if self.public:
            for guest_name in self.public.registered_names():
                key = name_key(guest_name)
                if key in self.records:
                    raise ValueError('A public account name conflicts with an existing configured login.')
                self.records[key] = (guest_name, None, None)
                self.player_keys.add(key)
        if self.registered:
            for player in self.registered.registered_names():
                key = name_key(player)
                if key in self.records:
                    raise ValueError('A registered player conflicts with an existing configured login.')
                self.records[key] = (player, None, None)
                self.player_keys.add(key)

    def verifier(self, password):
        return hmac.digest(self.pepper,password.encode(),'sha256')

    def authenticate(self, name, password):
        try:
            key = name_key(name)
        except ValueError:
            key = ''
        now = time.time()
        # Bound attempts per configured identity, including a single unknown-name bucket.
        recent = self.failures.setdefault(key if key in self.records else '',deque())
        while recent and recent[0] <= now-60:
            recent.popleft()
        if len(recent)>=8:
            return None
        _, expected, expiry = self.records.get(key,('',bytes(32),0))
        valid = expected is not None and hmac.compare_digest(self.verifier(password),expected)
        if not valid or (expiry is not None and expiry<=now):
            recent.append(now)
            return None
        recent.clear()
        token = secrets.token_urlsafe(32)
        # A new login replaces the previous browser session for the same identity.
        for old, (account,until) in list(self.sessions.items()):
            if account==key or until<=now:
                self.sessions.pop(old,None)
        self.sessions[token] = key, min(now+12*3600, expiry if expiry is not None else float('inf'))
        return token

    def lookup(self, token):
        if self.public and isinstance(token, str) and token.startswith('g.'):
            return self.public.lookup(token)
        if self.registered and isinstance(token, str) and token.startswith('u.'):
            return self.registered.lookup(token)
        row = self.sessions.get(token)
        if row and row[1]>time.time():
            return row[0]
        self.sessions.pop(token,None)
        return None


@dataclass
class PrivateWorker:
    account: str
    game: str
    process: object = None
    client: object = None
    url: str = ''
    socket: object = None
    socket_token: str = None
    saved_exit: bool = False
    feedback_complete: bool = False
    discarded_exit: bool = False
    last_used: float = field(default_factory=time.monotonic)


class Service:
    def __init__(self):
        self.origin = os.getenv('EXPANSE_PUBLIC_URL') or os.getenv('RENDER_EXTERNAL_URL','')
        self.origin = self.origin.rstrip('/')
        parsed = urlsplit(self.origin)
        self.local = parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost','::1') and not os.getenv('RENDER')
        if not (self.local or parsed.scheme=='https') or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError('Set a complete HTTPS public origin or an explicit loopback HTTP origin for local use.')
        self.cookie = 'expanse_local' if self.local else '__Host-expanse'
        self.data = Path(os.environ['EXPANSE_DATA_DIR']).resolve()
        if os.getenv('RENDER') and not disk_mounted(self.data):
            raise ValueError('The configured Render persistent disk is not mounted.')
        self.data.mkdir(parents=True,exist_ok=True)
        self.public_enabled = os.environ.get('EXPANSE_PUBLIC_PLAY','0').strip().lower() in ('1','true','yes','on')
        self.public_max = int(os.environ.get('EXPANSE_MAX_PUBLIC_PLAYERS','30'))
        if not 1 <= self.public_max <= 200:
            raise ValueError('EXPANSE_MAX_PUBLIC_PLAYERS must be between 1 and 200.')
        signup_setting = os.environ.get('EXPANSE_ACCOUNT_REGISTRATION')
        self.registered_enabled = self.public_enabled and (
            signup_setting is not None and signup_setting.strip().lower() in ('1','true','yes','on'))
        # Keep old 1.9.16 guest joining usable only when the new signup switch is
        # completely absent. Explicitly setting it to 0 closes ALL new signups,
        # including the legacy passwordless endpoint, while allowing returns.
        self.legacy_signups_enabled = self.public_enabled and signup_setting is None
        public = PublicGuests(self.data,self.public_max) if self.public_enabled else None
        # Disabling signup must never lock out previously registered players.
        self.registered = RegisteredPlayers(self.data,self.public_max,public) if self.public_enabled else None
        self.registered_login = bool(self.registered and (self.registered_enabled or self.registered.count()>0))
        self.auth = Accounts(public,self.registered)
        self.mail_user = os.environ.get('EXPANSE_SMTP_USER','').strip()
        self.mail_password = os.environ.get('EXPANSE_SMTP_APP_PASSWORD','')
        self.mail_from = os.environ.get('EXPANSE_SMTP_FROM','').strip()
        self.mail_host = os.environ.get('EXPANSE_SMTP_HOST','smtp.fastmail.com').strip()
        self.mail_port = int(os.environ.get('EXPANSE_SMTP_PORT','465'))
        self.mail_enabled = bool(self.mail_user and self.mail_password and self.mail_from)
        if any((self.mail_user,self.mail_password,self.mail_from)) and not self.mail_enabled:
            raise ValueError('Configure all EXPANSE_SMTP_USER, EXPANSE_SMTP_APP_PASSWORD and EXPANSE_SMTP_FROM or none.')
        self.public_signups = deque()
        self.public_recovery_attempts = deque()
        self.public_login_attempts = {}
        self.email_request_attempts = deque()
        self.worlds = self.data/'worlds'
        self.worlds.mkdir(exist_ok=True)
        self.update_world = os.environ.get('EXPANSE_UPDATE_WORLD_SHA256','').strip()
        if self.update_world and not re.fullmatch(r'[0-9a-f]{64}',self.update_world):
            raise ValueError('EXPANSE_UPDATE_WORLD_SHA256 must be the full SHA-256 of an imported game file.')
        self.max_workers = int(os.getenv('EXPANSE_MAX_ACTIVE_GAMES', '2'))
        if not 1 <= self.max_workers <= 8:
            raise ValueError('EXPANSE_MAX_ACTIVE_GAMES must be between 1 and 8.')
        self.workers = {}
        self.selected_games = {}
        self.lock = asyncio.Lock()
        self.importing = False
        self.editors = {}
        self.editor_lock = asyncio.Lock()
        self.assets = {p.name:p for p in (ROOT/'web').iterdir() if p.suffix in {'.css','.js','.svg'}}

    def bundle(self, ident):
        if not isinstance(ident,str) or not re.fullmatch(r'[0-9a-f]{64}',ident) or not (self.worlds/ident/'info.json').is_file():
            raise web.HTTPNotFound(text='Choose an imported world.')
        return self.worlds/ident

    def folder(self,key,ident):
        return self.data/'players'/hashlib.sha256(key.encode()).hexdigest()/ident

    def catalogue(self):
        # Read the original import's authored metadata, without rewriting legacy
        # info records or starting a game. Archive IDs continue to own all saves.
        def read_object(path, bundle):
            try:
                if path.is_symlink() or not path.resolve().is_relative_to(bundle.resolve()):
                    return {}
                with path.open('rb') as stream:
                    raw = stream.read(16 * 1024 * 1024 + 1)
                if len(raw) > 16 * 1024 * 1024:
                    return {}
                value = json.loads(raw)
                return value if isinstance(value, dict) else {}
            except (OSError, ValueError, UnicodeError):
                return {}

        rows = []
        for path in self.worlds.glob('*/info.json'):
            bundle = path.parent
            if bundle.is_symlink() or not re.fullmatch(r'[0-9a-f]{64}', bundle.name):
                continue
            info = read_object(path, bundle)
            slug = info.get('slug')
            if not isinstance(slug, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', slug):
                continue
            game = bundle/'games'/slug
            rows.append((bundle.name, world_catalogue.display_info(
                info, read_object(game/'metadata.json', bundle),
                read_object(game/'manifest.json', bundle))))
        return world_catalogue.annotate_latest(rows)

    def update_templates(self, ident, slug):
        if not self.update_world or self.update_world == ident:
            return ()
        bundle = self.worlds/self.update_world
        if not (bundle/'info.json').is_file():
            raise ValueError('Import the game file selected by EXPANSE_UPDATE_WORLD_SHA256 before playing with this update enabled.')
        info = json.loads((bundle/'info.json').read_bytes())
        if info.get('slug') != slug:
            return ()
        template = bundle/'games'/slug
        if template.is_symlink() or not template.is_dir() or not template.resolve().is_relative_to(bundle.resolve()):
            raise ValueError('The selected world update template is unavailable.')
        return (template,)

    def identity(self,request):
        return self.auth.lookup(request.cookies.get(self.cookie,''))

    async def stop(self, key=None, ident=None):
        for worker_key, worker in list(self.workers.items()):
            if (key is not None and worker.account != key) or (ident is not None and worker.game != ident):
                continue
            if worker.socket is not None:
                await worker.socket.close()
            if worker.client:
                await worker.client.close()
            if worker.process and worker.process.returncode is None:
                worker.process.terminate()
                try:
                    await asyncio.wait_for(worker.process.wait(), 8)
                except asyncio.TimeoutError:
                    worker.process.kill()
                    await worker.process.wait()
            if self.workers.get(worker_key) is worker:
                self.workers.pop(worker_key, None)

    async def start(self, key, ident):
        async with self.lock:
            bundle = self.bundle(ident)
            worker = self.workers.get((key, ident))
            if worker and worker.process and worker.process.returncode is None:
                self.selected_games[key] = ident
                worker.last_used = time.monotonic()
                return worker
            if worker:
                await self.stop(key, ident)
            for old in list(self.workers.values()):
                if old.process and old.process.returncode is not None:
                    await self.stop(old.account, old.game)
            # A passwordless player cannot occupy several independent worlds
            # at once. Do not terminate their unsaved adventure implicitly.
            if key in self.auth.player_keys:
                if any(account == key for account, game in self.workers):
                    raise web.HTTPConflict(text='You already have an active adventure. Use Save & quit in that world before opening another.')
            if len(self.workers) >= self.max_workers:
                raise web.HTTPServiceUnavailable(text='All private game slots are in use. Try again after a player saves and quits. No active player has been disconnected.')
            slug = json.loads((bundle/'info.json').read_bytes())['slug']
            template_args = [value for path in self.update_templates(ident,slug)
                             for value in ('--update-template',str(path))]
            save = self.folder(key,ident)
            save.mkdir(parents=True,exist_ok=True)
            worker = PrivateWorker(key, ident)
            self.workers[(key, ident)] = worker
            try:
                # Each private game receives its own pre-bound listener, secret
                # worker token, process memory and account/world save directory.
                env = {k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','PYTHONUTF8','PYTHONUNBUFFERED','VIRTUAL_ENV','PYTHONPATH')}
                env['EXPANSE_WORKER_TOKEN'] = secrets.token_urlsafe(32)
                with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
                    listener.bind(('127.0.0.1',0))
                    listener.listen(16)
                    worker.url = f'http://127.0.0.1:{listener.getsockname()[1]}'
                    worker.process = await asyncio.create_subprocess_exec(sys.executable,str(ROOT/'private_game.py'),
                        '--fd',str(listener.fileno()),'--name',self.auth.records[key][0],
                        '--world',str(bundle/'games'/slug),'--directory',str(save),
                        *template_args,env=env,pass_fds=(listener.fileno(),))
                worker.client = ClientSession(headers={'X-Worker-Key':env['EXPANSE_WORKER_TOKEN']},timeout=ClientTimeout(total=150))
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    if worker.process.returncode is not None:
                        raise web.HTTPServiceUnavailable(text='Expanse could not start. Check the service logs.')
                    try:
                        async with worker.client.get(worker.url+'/api/config',timeout=1) as answer:
                            if answer.status==200:
                                self.selected_games[key] = ident
                                return worker
                    except (OSError,asyncio.TimeoutError):
                        pass
                    await asyncio.sleep(.1)
                raise web.HTTPServiceUnavailable(text='The game took too long to start.')
            except BaseException:
                await self.stop(key, ident)
                raise

    async def landing(self,req):
        key = self.identity(req)
        if not key:
            return sign_in(public=(self.legacy_signups_enabled and not self.registered_login),
                           registered=self.registered_login,mail=self.mail_enabled,
                           allow_signup=self.registered_enabled)
        name,_,expiry = self.auth.records[key]
        contents = '<p>Signed in as <strong>'+escape(name)+'</strong>.</p>'
        if expiry is not None:
            from datetime import timezone
            contents += '<p>Account access ends '+datetime.fromtimestamp(expiry,timezone.utc).isoformat()+' UTC.</p>'
        entries=self.catalogue()
        if entries:
            contents += '<p class="world-note">To continue an existing character, open the same game file you used before.</p>'
        for ident,info in entries:
            title = escape(info['display_name'])
            contents += '<section class="world-card" data-game="'+ident+'" aria-labelledby="world-'+ident+'"><h2 id="world-'+ident+'">'+title+'</h2>'
            version = info.get('version')
            contents += '<div class="world-meta"><span>Imported world version '+(escape(version) if version else 'not specified')+'</span>'
            if info['is_latest']:
                label = 'Newest numbered version' if info['unranked_in_family'] else 'Newest version'
                contents += '<span class="world-badge latest">'+label+'</span>'
            elif info['is_older']:
                contents += '<span class="world-badge older">Older version</span>'
            if key == self.auth.owner and ident == self.update_world:
                contents += '<span class="world-badge">Update template</span>'
            contents += '</div><span class="world-file">File ID <code>'+ident[:12]+'</code></span>'
            contents += '<form action="/enter" method="post"><input type="hidden" name="game" value="'+ident+'"><button aria-label="Play Expanse — '+title+'; file '+ident[:12]+'">Play Expanse</button></form>'
            contents += '<div class="world-links"><a href="/world.expanse?game='+ident+'" download>Download imported world</a>'
            if key==self.auth.owner:
                contents+='<a href="/editor?game='+ident+'">Edit a draft</a>'
            if self.has_save(key,ident):
                contents+='<a href="/manual-saves.zip?game='+ident+'" download>Download your manual saves</a>'
            contents += '</div></section>'
        if key==self.auth.owner:
            contents += '<p><a href="/playtest">Playtest reports</a></p>'
            contents += ('<h2>Import a game</h2><form action="/world/import" enctype="multipart/form-data" method="post"><label>'
                         'Game file<input name="world" type="file" accept=".expanse" required></label>'
                         '<button>Import world</button></form>')
        elif not entries:
            contents += '<p>The owner has not imported a world yet.</p>'
        if key==self.auth.owner and self.public_enabled:
            contents += '<p><a href="/public/players">Public player registrations</a></p>'
        if key in self.auth.player_keys:
            if self.registered and key in {name_key(x) for x in self.registered.registered_names()}:
                contents += '<p><a href="/account">Account security &amp; recovery</a></p>'
            else:
                contents += "<p>Your guest access stays with this browser. Keep the recovery code you received when you joined; signing out removes this browser's access.</p>"
        return page('Expanse',contents+'<form method="post" action="/logout"><button>Sign out</button></form>')

    def has_save(self,key,ident):
        folder = self.folder(key,ident)
        return (folder/SLOTS_DB).is_file() or any(folder.glob('world_state*_single.json'))

    @staticmethod
    def _rate_limit(queue, window, maximum):
        now=time.monotonic()
        while queue and queue[0] <= now-window:
            queue.popleft()
        if len(queue)>=maximum:
            raise web.HTTPTooManyRequests(text='Too many attempts. Please try again later.')
        queue.append(now)

    def _public_cookie(self, response, token):
        response.set_cookie(self.cookie,token,path='/',httponly=True,
                            secure=not self.local,samesite='Strict',max_age=90*86400)
        return response

    async def public_join(self, req):
        if not self.legacy_signups_enabled or self.registered_login:
            raise web.HTTPNotFound()
        if req['key']:
            return web.HTTPSeeOther('/')
        self._rate_limit(self.public_signups,60,5)
        try:
            name, token, recovery = self.auth.public.create(set(self.auth.records))
        except GuestLimit as exc:
            return page('Expanse — registration full','<p>'+escape(str(exc))+'</p><p><a href="/">Back</a></p>',503)
        key=name_key(name)
        self.auth.records[key]=(name,None,None)
        response = page('Welcome to Expanse',
            '<p>Your player name is <strong>'+escape(name)+'</strong>.</p>'
            '<p>There is no password to enter. This browser is signed in automatically.</p>'
            '<h2>Save this recovery code</h2><p><code class="recovery-code">'+escape(recovery)+'</code></p>'
            '<p>Keep it private. If you change devices, sign out, or clear browser data, '
            'enter this code on the Recover page to restore access to your character and saves. '
            'It is shown only once.</p><p><a class="button" href="/">Continue to your game</a></p>')
        return self._public_cookie(response,token)

    async def public_return(self, req):
        if not self.public_enabled:
            raise web.HTTPNotFound()
        return page('Recover your Expanse player',
            '<p>Enter the recovery code you saved when you joined. It is not your character name.</p>'
            '<form action="/public/recover" method="post"><label>Recovery code'
            '<input type="text" name="code" autocomplete="off" required></label>'
            '<button>Recover player</button></form><p><a href="/">Back</a></p>')

    async def public_recover(self, req):
        if not self.public_enabled:
            raise web.HTTPNotFound()
        self._rate_limit(self.public_recovery_attempts,60,8)
        form = await req.post()
        code = form.get('code','')
        found = self.auth.public.recover(code)
        if not found:
            return page('Recovery unsuccessful','<p>The code is invalid or the player is disabled.</p><p><a href="/public/return">Try again</a></p>',403)
        name, token, new_recovery = found
        return self._public_cookie(recovery_screen(new_recovery,
            'Your older guest recovery code has been used and replaced. Save this new code.',name),token)

    def _registered_cookie(self, response, token):
        response.set_cookie(self.cookie,token,path='/',httponly=True,
                            secure=not self.local,samesite='Strict',max_age=90*86400)
        return response

    async def _mail(self, recipient, subject, message):
        if not self.mail_enabled:
            return False
        def send():
            mail=EmailMessage()
            mail['From']=self.mail_from
            mail['To']=recipient
            mail['Subject']=subject
            mail.set_content(message)
            with smtplib.SMTP_SSL(self.mail_host,self.mail_port,context=ssl.create_default_context(),timeout=15) as smtp:
                smtp.login(self.mail_user,self.mail_password)
                smtp.send_message(mail)
        try:
            await asyncio.to_thread(send)
            return True
        except (OSError,smtplib.SMTPException):
            # Do not log recipients, tokens, passwords, or SMTP credentials.
            return False

    async def register(self,req):
        if not self.registered_enabled:
            raise web.HTTPNotFound()
        if req['key']:
            return web.HTTPSeeOther('/')
        email=('<label>Recovery email (optional; must be verified)'
               '<input type="email" name="email" autocomplete="email" maxlength="254"></label>') if self.mail_enabled else ''
        return page('Create your Expanse account',
            '<p class="lead">Free personal adventure access. Save manually and keep your recovery code private.</p>'
            '<section class="auth-card"><form action="/register" method="post">'
            '<label>Choose a username<input name="name" autocomplete="username" required minlength="3" maxlength="24"'
            ' pattern="[A-Za-z][A-Za-z0-9_]{2,23}" placeholder="adventurer_1"></label>'
            '<label>Create a password<input type="password" name="password" autocomplete="new-password"'
            ' minlength="12" maxlength="128" required></label>'
            '<label>Repeat password<input type="password" name="confirm" autocomplete="new-password"'
            ' minlength="12" maxlength="128" required></label>'+email+
            '<p class="note">Your game account is separate from Discourse and Patreon. We store a salted, '
            'one-way password hash—not your plaintext password.</p>'
            '<button>Create free account</button></form></section><p><a href="/">Return to sign-in</a></p>')

    async def register_submit(self,req):
        if not self.registered_enabled:
            raise web.HTTPNotFound()
        if req['key']:
            return web.HTTPSeeOther('/')
        self._rate_limit(self.public_signups,60,5)
        form=await req.post()
        name,password,confirm=form.get('name',''),form.get('password',''),form.get('confirm','')
        if password!=confirm:
            return page('Passwords do not match','<p>Please try again. <a href="/register">Return</a>.</p>',400)
        try:
            user,token,recovery=await asyncio.to_thread(self.registered.register,name,password,set(self.auth.records))
        except RegistrationError as exc:
            return page('Unable to create account', '<p role="alert">'+escape(str(exc))+'</p>'
                        '<p><a href="/register">Try again</a></p>',409)
        self.auth.records[user]=(user,None,None)
        self.auth.player_keys.add(user)
        self.registered_login = True
        note='Your player account is active. Your recovery code is the only way to regain access without your password or verified email.'
        email=(form.get('email') or '').strip() if self.mail_enabled else ''
        if email:
            try:
                verify=await asyncio.to_thread(self.registered.start_email_verification,user,email)
                link=self.origin+'/email/verify?token='+quote(verify)
                sent=await self._mail(email,'Verify your Expanse recovery email',
                    'Confirm your Expanse account email by opening this link:\n\n'+link+'\n\n'
                    'If you did not register, ignore this message. The link expires in 24 hours.')
                note+= (' A verification link has been sent to your email.' if sent
                        else ' The confirmation email could not be sent; add or retry it in account settings.')
            except RegistrationError:
                note+=' The email address could not be added; you can correct it in account settings.'
        return self._registered_cookie(recovery_screen(recovery,note,user),token)

    async def forgot(self,req):
        if not self.registered:
            raise web.HTTPNotFound()
        request_email = ("<form method='post' action='/forgot/email'><label>Username "
                         "<input name='name' autocomplete='username' required></label> "
                         "<button>Send a reset link to my verified email</button></form>") if self.mail_enabled else '' 
        return page('Recover an Expanse account',
            '<p>Use the private recovery code you saved when registering. It is single-use and will be replaced.</p>'
            '<section class="auth-card"><h2>Reset with recovery code</h2><form method="post" action="/forgot/code">'
            '<label>Username<input name="name" autocomplete="username" required></label>'
            '<label>Recovery code<input name="recovery" autocomplete="off" required></label>'
            '<label>New password<input type="password" name="password" autocomplete="new-password" required minlength="12"></label>'
            '<button>Reset password and generate new recovery code</button></form></section>'
            + ('<section class="auth-card"><h2>Use verified email</h2>'+request_email+'</section>' if request_email else '')
            + '<p><a href="/">Back to sign in</a></p>')

    async def forgot_code(self,req):
        if not self.registered: raise web.HTTPNotFound()
        self._rate_limit(self.public_recovery_attempts,60,8)
        form=await req.post()
        result=await asyncio.to_thread(self.registered.reset_with_code,form.get('name',''),
                                        form.get('recovery',''),form.get('password',''))
        if not result:
            return page('Recovery failed','<p>The username, recovery code or new password is invalid. '
                        '<a href="/forgot">Try again</a>.</p>',403)
        user,token,recovery=result
        await self._notify_recovery(user,recovery)
        return self._registered_cookie(recovery_screen(recovery,
            'Your password has been changed, old sessions are invalidated, and this replaces your previous recovery code.',user),token)

    async def _notify_recovery(self,user,recovery):
        if not self.mail_enabled:return
        email=await asyncio.to_thread(self.registered.email_for,user)
        if email:
            await self._mail(email,'Expanse recovery code replaced',
                             'Your Expanse password/recovery was changed. Your new recovery code is:\n\n'
                             +recovery+'\n\nStore it privately. If you did not request this change, '
                             'contact the Expanse administrator immediately.')

    async def account(self,req):
        if not self.registered or req['key'] not in {n.casefold() for n in self.registered.registered_names()}:
            raise web.HTTPForbidden()
        email=await asyncio.to_thread(self.registered.email_for,req['key'])
        email_section = ''
        if self.mail_enabled:
            email_section=('<section class="auth-card"><h2>Verified recovery email</h2>'
                           '<p>Current: '+(escape(email) if email else 'None verified')+'</p>'
                           '<form method="post" action="/account/email"><label>Email address'
                           '<input type="email" name="email" autocomplete="email" maxlength="254" required></label>'
                           '<button>Send verification email</button></form></section>')
        return page('Account security',
            '<p class="lead">Signed in as '+escape(req['key'])+'. Passwords and recovery codes are never shown to administrators.</p>'
            '<section class="auth-card"><h2>Change password</h2><p>A new recovery code is issued every time.</p>'
            '<form method="post" action="/account/password">'
            '<label>Current password<input type="password" name="old" autocomplete="current-password" required></label>'
            '<label>New password<input type="password" name="new" autocomplete="new-password" minlength="12" required></label>'
            '<button>Change password</button></form></section>'+email_section+'<p><a href="/">Return to game</a></p>')

    async def change_password(self,req):
        if not self.registered or req['key'] not in {n.casefold() for n in self.registered.registered_names()}:
            raise web.HTTPForbidden()
        form=await req.post()
        result=await asyncio.to_thread(self.registered.change_password,req['key'],form.get('old',''),form.get('new',''))
        if not result:
            return page('Password not changed', '<p>Current password incorrect or new password invalid. '
                        '<a href="/account">Try again</a>.</p>',403)
        token,recovery=result
        await self._notify_recovery(req['key'],recovery)
        return self._registered_cookie(recovery_screen(recovery,
            'Password changed. Previous browser sessions and recovery codes have been invalidated.',req['key']),token)

    async def account_email(self,req):
        if not self.mail_enabled or not self.registered or req['key'] not in {n.casefold() for n in self.registered.registered_names()}:
            raise web.HTTPForbidden()
        form=await req.post()
        email=(form.get('email') or '').strip().lower()
        try:
            token=await asyncio.to_thread(self.registered.start_email_verification,req['key'],email)
        except RegistrationError as exc:
            return page('Email not configured',escape(str(exc))+'<p><a href="/account">Back</a></p>',400)
        link=self.origin+'/email/verify?token='+quote(token)
        sent=await self._mail(email,'Verify your Expanse recovery email',
             'Confirm your Expanse recovery email by visiting:\n\n'+link+'\n\n'
             'Expires in 24 hours. If you did not request this, ignore this email.')
        return page('Email verification',
            '<p>'+('Check your inbox and open the verification link.' if sent else
                   'The message could not be sent. Check your SMTP settings and try again.')+'</p>'
            '<p><a href="/account">Back to account settings</a></p>')

    async def email_verify_page(self,req):
        if not self.registered:
            raise web.HTTPNotFound()
        token=req.query.get('token','')
        if not isinstance(token,str) or not token.startswith('v.') or len(token)>100:
            raise web.HTTPBadRequest()
        return page('Confirm Expanse email',
            '<p>This will confirm the email address associated with your player account.</p>'
            '<form method="post" action="/email/verify">'
            '<input type="hidden" name="token" value="'+escape(token,quote=True)+'">'
            '<button>Confirm recovery email</button></form>')

    async def email_verify_finish(self,req):
        if not self.registered: raise web.HTTPNotFound()
        form=await req.post()
        try:
            row=await asyncio.to_thread(self.registered.verify_email,form.get('token',''))
        except RegistrationError as exc:
            return page('Verification failed',escape(str(exc)),409)
        if not row:
            return page('Verification failed','<p>Link invalid or expired. You can request a new link from Account security.</p>',403)
        return page('Recovery email verified','<p>Email verified for '+escape(row[0])+'. You can now request '
                    'a password reset link by email if you lose your password and recovery code.</p>'
                    '<p><a href="/">Return to Expanse</a></p>')

    async def forgot_email(self,req):
        if not self.registered or not self.mail_enabled:
            raise web.HTTPNotFound()
        self._rate_limit(self.email_request_attempts,60,5)
        form=await req.post()
        result=await asyncio.to_thread(self.registered.start_email_reset,form.get('name',''))
        if result:
            email,token=result
            link=self.origin+'/email/reset?token='+quote(token)
            await self._mail(email,'Reset your Expanse password',
                        'You requested a password reset. Open this link to continue:\n\n'+link+'\n\n'
                        'It expires in 30 minutes. If you did not request this, ignore it.')
        return page('Check your email','<p>If this username has a verified recovery email, '
                    'a reset link has been sent. Otherwise, use your saved recovery code.</p>'
                    '<p><a href="/forgot">Back</a></p>')

    async def email_reset_page(self,req):
        if not self.registered or not self.mail_enabled:
            raise web.HTTPNotFound()
        token=req.query.get('token','')
        if not isinstance(token,str) or not token.startswith('p.') or len(token)>100:
            raise web.HTTPBadRequest()
        return page('Set a new Expanse password',
            '<form method="post" action="/email/reset">'
            '<input type="hidden" name="token" value="'+escape(token,quote=True)+'">'
            '<label>New password<input type="password" name="password" autocomplete="new-password"'
            ' minlength="12" maxlength="128" required></label><button>Reset password</button></form>')

    async def email_reset_finish(self,req):
        if not self.registered or not self.mail_enabled:
            raise web.HTTPNotFound()
        self._rate_limit(self.public_recovery_attempts,60,8)
        form=await req.post()
        found=await asyncio.to_thread(self.registered.reset_with_email_token,form.get('token',''),form.get('password',''))
        if not found:
            return page('Reset failed','<p>The link has expired or is invalid. '
                        '<a href="/forgot">Request another</a>.</p>',403)
        user,token,recovery,email=found
        await self._notify_recovery(user,recovery)
        return self._registered_cookie(recovery_screen(recovery,
            'Your password has been reset, prior sessions are invalidated, and a new recovery code has been issued.',user),token)

    async def public_players(self, req):
        if req['key']!=self.auth.owner or not self.public_enabled:
            raise web.HTTPForbidden()
        guests=self.auth.public.rows()
        registered=self.registered.rows() if self.registered else []
        contents=('<p>Enabled player registrations: '+str(self.auth.public.count() + (self.registered.count() if self.registered else 0))+' of '+str(self.public_max)+'. ' 
                  'Active private adventures: '+str(len(self.workers))+' of '+str(self.max_workers)+'.</p>')
        for name,enabled,created,verified in registered:
            action = 'disable' if enabled else 'enable'
            contents += ('<section class="world-card"><strong>'+escape(name)+'</strong> — '+
                         ('enabled' if enabled else 'disabled')+
                         (' · Verified email' if verified else ' · Recovery code only')+
                         ('<form action="/public/players/action" method="post">'
                          '<input type="hidden" name="name" value="'+escape(name)+'">'
                          '<input type="hidden" name="action" value="send-reset">'
                          '<button>Send password reset link</button></form>' if verified and self.mail_enabled else '')+
                         '<form action="/public/players/action" method="post">'
                         '<input type="hidden" name="name" value="'+escape(name)+'">'
                         '<input type="hidden" name="action" value="'+action+'">'
                         '<button>'+action.capitalize()+' player</button></form></section>')
        for name,enabled,created in guests:
            action = 'disable' if enabled else 'enable'
            contents += ('<section class="world-card"><strong>'+escape(name)+'</strong> — '+
                         ('enabled' if enabled else 'disabled')+
                         '<form action="/public/players/action" method="post">'
                         '<input type="hidden" name="name" value="'+escape(name)+'">'
                         '<input type="hidden" name="action" value="'+action+'">'
                         '<button>'+action.capitalize()+' player</button></form></section>')
        return page('Public players',contents+'<a href="/">Back to Expanse</a>')

    async def public_players_action(self, req):
        if req['key']!=self.auth.owner or not self.public_enabled:
            raise web.HTTPForbidden()
        form=await req.post()
        name, action=form.get('name'),form.get('action')
        if action not in ('enable','disable','send-reset') or not isinstance(name,str):
            raise web.HTTPBadRequest()
        if action=='send-reset':
            if not self.mail_enabled or not self.registered:
                raise web.HTTPForbidden()
            result=await asyncio.to_thread(self.registered.start_email_reset,name)
            if result:
                email,token=result
                link=self.origin+'/email/reset?token='+quote(token)
                sent=await self._mail(email,'Expanse account password reset requested by the administrator',
                    'An Expanse administrator requested an account recovery link. Use it only if you requested help:\n\n'
                    +link+'\n\nExpires in 30 minutes. If you did not request a reset, ignore it.')
                return page('Password reset request',
                    '<p>'+('A reset link was sent to the verified recovery email.' if sent else
                           'The email could not be sent. Check SMTP settings and try again.')+'</p>'
                    '<p>The administrator cannot see the reset token or the player password.</p>'
                    '<p><a href="/public/players">Back to players</a></p>')
            return page('Password reset unavailable','<p>This player has no verified recovery email.</p>'
                        '<p><a href="/public/players">Back to players</a></p>',409)
        try:
            updated=(self.registered.set_enabled(name,action=='enable') if self.registered and
                     name.casefold() in {n.casefold() for n in self.registered.registered_names()}
                     else self.auth.public.set_enabled(name,action=='enable'))
        except (GuestLimit,RegistrationError) as exc:
            return page('Unable to enable player',escape(str(exc))+'<p><a href="/public/players">Back</a></p>',409)
        if not updated:
            raise web.HTTPNotFound()
        if action=='disable':
            async with self.lock:
                await self.stop(name_key(name))
        return web.HTTPSeeOther('/public/players')

    async def login(self,req):
        form=await req.post()
        name,password=form.get('name'),form.get('password')
        name = name.strip() if isinstance(name,str) else ''
        password = password if isinstance(password,str) and len(password)<=128 else ''
        key = name.casefold()
        failures=self.public_login_attempts.setdefault(key if len(key)<=24 else '',deque())
        now=time.monotonic()
        while failures and failures[0] < now-60:
            failures.popleft()
        if len(failures)>=8:
            raise web.HTTPTooManyRequests(text='Too many sign-in attempts. Try again shortly.')
        token = (await asyncio.to_thread(self.registered.authenticate,name,password)
                 if self.registered and self.registered.valid_name(name) else None)
        if not token:
            token = self.auth.authenticate(name,password)
        if not token:
            failures.append(now)
            return sign_in('Sign-in failed. Check your name, password and account access.',403,
                           public=(self.legacy_signups_enabled and not self.registered_login),
                           registered=self.registered_login,mail=self.mail_enabled,
                           allow_signup=self.registered_enabled)
        failures.clear()
        response = web.HTTPSeeOther('/')
        response.set_cookie(self.cookie,token,path='/',httponly=True,secure=not self.local,
                            samesite='Strict',max_age=90*86400 if token.startswith('u.') else 43200)
        return response

    async def logout(self,req):
        key = req['key']
        token = req.cookies.get(self.cookie,'')
        self.auth.sessions.pop(token,None)
        if self.auth.public:
            self.auth.public.invalidate(token)
        if self.registered:
            self.registered.invalidate(token)
        async with self.lock:
            await self.stop(key)
            self.selected_games.pop(key, None)
        response = web.HTTPSeeOther('/')
        response.del_cookie(self.cookie,path='/')
        return response

    async def enter(self,req):
        form=await req.post()
        await self.start(req['key'],form.get('game'))
        return web.HTTPSeeOther('/play?game='+form['game'])

    async def install(self,req):
        if req['key']!=self.auth.owner:
            raise web.HTTPForbidden()
        if self.importing:
            raise web.HTTPConflict(text='Let the current import finish first.')
        self.importing = True
        try:
            with tempfile.TemporaryDirectory(dir=self.data) as scratch:
                stage=Path(scratch)/'bundle'
                stage.mkdir()
                archive=stage/'world.expanse'
                field=await (await req.multipart()).next()
                if field is None or field.name!='world' or not (field.filename or '').lower().endswith('.expanse'):
                    raise ValueError('Choose a complete .expanse game file.')
                size=0
                digest=hashlib.sha256()
                with archive.open('wb') as f:
                    while chunk:=await field.read_chunk(65536):
                        size += len(chunk)
                        if size>LIMIT:
                            raise web.HTTPRequestEntityTooLarge(max_size=LIMIT,actual_size=size)
                        f.write(chunk)
                        digest.update(chunk)
                ident=digest.hexdigest()
                if (self.worlds/ident).is_dir():
                    return web.HTTPSeeOther('/')
                def validate():
                    from engine.exchange import import_game
                    ok,note=import_game(archive,stage/'games')
                    if not ok:
                        raise ValueError(note)
                    slug=next(p.name for p in (stage/'games').iterdir() if not p.name.startswith('.'))
                    meta=json.loads((stage/'games'/slug/'metadata.json').read_bytes())
                    (stage/'info.json').write_text(json.dumps({'slug':slug,'name':meta.get('name') or slug}))
                await asyncio.to_thread(validate)
                stage.rename(self.worlds/ident)
        finally:
            self.importing=False
        return web.HTTPSeeOther('/')

    def active_worker(self,req):
        key = req['key']
        ident = req.headers.get('X-Expanse-Game') or req.query.get('game') or self.selected_games.get(key)
        worker = self.workers.get((key, ident))
        if not worker or not worker.client or worker.client.closed or not worker.process or worker.process.returncode is not None:
            raise web.HTTPConflict(text='Reopen your game from the start page.')
        worker.last_used = time.monotonic()
        return worker

    def active_client(self,req):
        return self.active_worker(req).client

    async def editor_service(self, req, ident=None):
        if req['key'] != self.auth.owner:
            raise web.HTTPForbidden(text='Only the signed-in owner can open world drafts.')
        ident = ident or req.headers.get('X-Expanse-Editor') or req.query.get('editor_game')
        bundle = self.bundle(ident)
        info = json.loads((bundle/'info.json').read_bytes())
        source = bundle/'games'/info['slug']
        if source.is_symlink() or not source.is_dir() or not source.resolve().is_relative_to(bundle.resolve()):
            raise ValueError('Imported world template is unavailable.')
        async with self.editor_lock:
            if ident not in self.editors:
                from server.editor_service import EditorService
                self.editors[ident] = await asyncio.to_thread(EditorService, self.data/'drafts'/ident, source, ident)
            return self.editors[ident]

    async def editor(self, req):
        await self.editor_service(req, req.query.get('game'))
        return web.FileResponse(ROOT/'web'/'index.html')

    async def editor_api(self, req):
        editor = await self.editor_service(req)
        body = None
        if req.method == 'POST':
            if req.content_type != 'application/json':
                raise web.HTTPBadRequest(text='Creator requests require JSON.')
            raw = await req.read()
            if len(raw) > LIMIT:
                raise web.HTTPRequestEntityTooLarge(max_size=LIMIT, actual_size=len(raw))
            def bad_constant(value):
                raise ValueError('Invalid JSON constant: '+value)
            body = json.loads(raw, parse_constant=bad_constant)
        path = req.path.removeprefix('/api/editor/')
        headers = {name:req.headers.get(name,'') for name in ('Origin','Host','Content-Type')}
        reply = await asyncio.to_thread(editor.dispatch, req.method, path, body, dict(req.query), headers)
        if reply.path is not None:
            headers = {'Content-Type':reply.mime or 'application/octet-stream'}
            if reply.download:
                headers['Content-Disposition'] = "attachment; filename*=UTF-8''" + quote(reply.download, safe='')
            return web.FileResponse(reply.path, status=reply.status, headers=headers)
        return web.json_response(reply.data, status=reply.status)

    async def playtest_report(self, req):
        if req['key'] != self.auth.owner:
            raise web.HTTPForbidden(text='Only the signed-in owner can view playtest reports.')
        from server.playtest_telemetry import owner_report, report_html
        worlds = self.catalogue()
        sources = []
        for account, (name, _, _) in self.auth.records.items():
            for ident, info in worlds:
                folder = self.folder(account, ident)
                if folder.is_dir() and not folder.is_symlink():
                    sources.append({'directory':folder, 'account':name, 'game':info['slug']+' · '+ident[:12]})
        report = await asyncio.to_thread(owner_report, sources, limit=200)
        if req.path == '/api/playtest/report':
            return web.json_response(report)
        return web.Response(text=report_html(report), content_type='text/html')

    async def api(self,req):
        if req.path == '/api/playtest/report':
            return await self.playtest_report(req)
        if req.path == '/api/editor' or req.path.startswith('/api/editor/'):
            return await self.editor_api(req)
        if req.headers.get('X-Expanse-Editor') or req.query.get('editor_game'):
            editor = await self.editor_service(req)
            if req.method == 'GET' and req.path == '/api/config':
                from engine.build_info import BUILD
                return web.json_response(dict(mode='edit', running_game=editor.slug, title='Expanse Creator', build=BUILD,
                    render_web=True, editor_only=True, editor_enabled=True, editor_reason='enabled',
                    character_name=self.auth.records[req['key']][0], can_manage_server=False, game_status='editor',
                    editor_url='/editor?game='+editor.bundle_id))
            if req.method == 'GET' and req.path == '/api/games':
                return web.json_response(await asyncio.to_thread(editor.games))
            return web.json_response({'error':'This draft session does not run a game or open player saves.'}, status=409)
        worker=self.active_worker(req)
        client=worker.client
        body=await req.read()
        if len(body)>65536:
            raise web.HTTPBadRequest()
        async with client.request(req.method,worker.url+req.path_qs,data=body,
                                  headers={'Content-Type':'application/json'}) as reply:
            if req.path == '/api/config' and reply.status == 200:
                config = await reply.json()
                owner = req['key'] == self.auth.owner
                config.update(editor_enabled=owner, editor_reason='enabled' if owner else 'owner_only', editor_only=False, render_game=worker.game)
                if owner:
                    config['editor_url'] = '/editor?game='+worker.game
                return web.json_response(config)
            raw = await reply.read()
            if req.path == '/api/save-slots/open' and reply.status == 200:
                restored = json.loads(raw)
                if restored.get('redirect') == '/play':
                    restored['redirect'] = '/play?game='+worker.game
                return web.json_response(restored)
            response = web.Response(body=raw,status=reply.status,content_type=reply.content_type)
        if req.path == '/api/playtest/feedback' and response.status == 200 and worker.saved_exit:
            worker.feedback_complete = True
            if worker.socket is None or worker.socket.closed:
                async with self.lock:
                    if self.workers.get((worker.account,worker.game)) is worker:
                        await self.stop(worker.account,worker.game)
        return response

    async def socket_route(self,req):
        worker=self.active_worker(req)
        client=worker.client
        if worker.socket is not None and not worker.socket.closed:
            raise web.HTTPConflict(text='Close the existing play tab first.')
        ws=web.WebSocketResponse(max_msg_size=65536,heartbeat=30)
        worker.socket=ws
        worker.socket_token=req.cookies[self.cookie]
        worker.saved_exit=False
        worker.feedback_complete=False
        worker.discarded_exit=False
        try:
            async with client.ws_connect(worker.url+'/ws',max_msg_size=32*1024*1024) as game:
                await ws.prepare(req)
                async def copy(source,dest):
                    async for msg in source:
                        if msg.type!=WSMsgType.TEXT or self.identity(req)!=req['key']:
                            break
                        worker.last_used = time.monotonic()
                        if source is game:
                            try:
                                packet = json.loads(msg.data)
                                if isinstance(packet,dict) and packet.get('type')=='saved_exit' and packet.get('checkpoint_saved') is True and not packet.get('save_failed'):
                                    worker.saved_exit=True
                                    feedback = packet.get('playtest')
                                    worker.feedback_complete = not (isinstance(feedback,dict) and feedback.get('questionnaire') is True)
                                if isinstance(packet,dict) and packet.get('type')=='saved_exit' and packet.get('discarded_exit') is True:
                                    worker.discarded_exit=True
                            except ValueError:
                                pass
                        await dest.send_str(msg.data)
                tasks=[asyncio.create_task(copy(ws,game)),asyncio.create_task(copy(game,ws))]
                try:
                    await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for t in tasks:t.cancel()
                    await asyncio.gather(*tasks,return_exceptions=True)
        finally:
            if worker.socket is ws:
                worker.socket=worker.socket_token=None
                worker.last_used=time.monotonic()
                if worker.discarded_exit or (worker.saved_exit and worker.feedback_complete):
                    async with self.lock:
                        if self.workers.get((worker.account,worker.game)) is worker:
                            await self.stop(worker.account,worker.game)
        return ws

    async def backup(self,req):
        key=req['key']
        ident=req.query.get('game')
        bundle=self.bundle(ident)
        if not self.has_save(key,ident):
            raise web.HTTPNotFound(text='Make a manual save in the game first.')
        async with self.lock:
            worker=self.workers.get((key,ident))
            if worker:
                if worker.socket is not None and not worker.socket.closed:
                    raise web.HTTPConflict(text='Close the play tab, then download your saved game.')
                await self.stop(key,ident)
            folder=self.folder(key,ident)
            with tempfile.TemporaryDirectory() as tmp:
                backup_path=Path(tmp)/'saves.zip'
                with zipfile.ZipFile(backup_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
                    for name in ('world.db',SLOTS_DB):
                        if (folder/name).is_file():
                            from contextlib import closing
                            with closing(sqlite3.connect((folder/name).resolve().as_uri()+'?mode=ro',uri=True)) as src, closing(sqlite3.connect(Path(tmp)/name)) as dest:
                                src.backup(dest)
                            z.write(Path(tmp)/name,'save/'+name)
                    for p in folder.glob('world_state*_single.json*'):
                        if p.suffix in ('.json','.save-journal'):
                            z.write(p,'save/'+p.name)
                    z.writestr('WORLD.txt',json.loads((bundle/'info.json').read_bytes())['slug']+'\n'+ident+'\n')
                return web.Response(body=backup_path.read_bytes(),content_type='application/zip',
                                    headers={'Content-Disposition':'attachment; filename="Expanse-manual-saves.zip"'})

    async def expiry(self,app):
        async def monitor():
            while True:
                await asyncio.sleep(3)
                for worker in list(self.workers.values()):
                    if worker.socket is not None and worker.socket_token and not self.auth.lookup(worker.socket_token):
                        await worker.socket.close(code=1008,message=b'Sign in again.')
                    # A completed manual Save & quit can release an abandoned
                    # questionnaire after 15 minutes. Unsaved games are retained.
                    if worker.saved_exit and worker.socket is None and time.monotonic()-worker.last_used>900:
                        async with self.lock:
                            if self.workers.get((worker.account,worker.game)) is worker:
                                await self.stop(worker.account,worker.game)
        timer=asyncio.create_task(monitor())
        yield
        timer.cancel()
        with suppress(asyncio.CancelledError):await timer
        await self.stop()


def make_app():
    service=Service()
    @web.middleware
    async def guard(req,handler):
        if req.method=='POST' or req.path=='/ws':
            origin=req.headers.get('Origin')
            if origin is None and req.method=='POST':
                ref=urlsplit(req.headers.get('Referer',''))
                origin=ref.scheme+'://'+ref.netloc
            if origin!=service.origin:
                raise web.HTTPForbidden(text='Open Expanse at its configured address.')
        key=service.identity(req)
        if req.path not in ('/','/healthz','/login','/mode.html', '/public/join','/public/return','/public/recover',
                            '/register','/forgot','/forgot/code','/forgot/email',
                            '/email/verify','/email/reset') and not key:
            if req.path=='/play':
                return web.HTTPSeeOther('/')
            return web.json_response({'error':'Sign in first.'},status=401)
        req['key']=key
        try:
            return await handler(req)
        except (ValueError,zipfile.BadZipFile) as exc:
            if req.path.startswith('/api/'):
                return web.json_response({'error':str(exc)},status=400)
            return page('Expanse',escape(str(exc))+'<p><a href="/">Back</a></p>',400)
    app=web.Application(middlewares=[guard],client_max_size=LIMIT+65536)
    async def prepare(req,resp):
        resp.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
                             'Referrer-Policy':'same-origin','X-Frame-Options':'DENY',
                             'Content-Security-Policy':"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; media-src 'self' blob: data:; connect-src 'self' "+service.origin.replace('https://','wss://').replace('http://','ws://')+"; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
    app.on_response_prepare.append(prepare)
    app.cleanup_ctx.append(service.expiry)
    async def health(req):
        return web.Response(text='ok')
    async def play(req):
        service.active_client(req)
        return web.FileResponse(ROOT/'web'/'index.html')
    async def world(req):
        bundle=service.bundle(req.query.get('game'))
        slug=json.loads((bundle/'info.json').read_bytes())['slug']
        return web.FileResponse(bundle/'world.expanse',headers={'Content-Disposition':'attachment; filename="'+slug+'.expanse"'})
    async def asset(req):
        path=service.assets.get(req.match_info['filename'])
        if not path:raise web.HTTPNotFound()
        return web.FileResponse(path)
    app.add_routes([web.get('/healthz',health),web.get('/',service.landing),web.get('/mode.html',service.landing),
                    web.post('/login',service.login),web.post('/logout',service.logout),web.post('/enter',service.enter),
                    web.post('/public/join',service.public_join),web.get('/public/return',service.public_return),
                    web.post('/public/recover',service.public_recover),
                    web.get('/register',service.register),web.post('/register',service.register_submit),
                    web.get('/forgot',service.forgot),web.post('/forgot/code',service.forgot_code),
                    web.post('/forgot/email',service.forgot_email),
                    web.get('/email/verify',service.email_verify_page),web.post('/email/verify',service.email_verify_finish),
                    web.get('/email/reset',service.email_reset_page),web.post('/email/reset',service.email_reset_finish),
                    web.get('/account',service.account),web.post('/account/password',service.change_password),
                    web.post('/account/email',service.account_email),
                    web.get('/public/players',service.public_players),web.post('/public/players/action',service.public_players_action),
                    web.post('/world/import',service.install),web.get('/world.expanse',world),
                    web.get('/editor',service.editor),
                    web.get('/playtest',service.playtest_report),
                    web.get('/manual-saves.zip',service.backup),web.get('/play',play),web.get('/ws',service.socket_route),
                    web.get('/api/{path:.*}',service.api),web.post('/api/{path:.*}',service.api),web.get('/{filename}',asset)])
    return app


if __name__=='__main__':
    os.umask(0o077)
    app=make_app()
    web.run_app(app,host='0.0.0.0' if os.environ.get('RENDER') or not os.environ.get('EXPANSE_PUBLIC_URL','').startswith('http://') else '127.0.0.1',
                port=int(os.environ.get('PORT','10000')),access_log=None)
