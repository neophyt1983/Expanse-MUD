"""Private single-player Expanse, served through one public HTTP/WebSocket port."""
import asyncio
from collections import deque
from contextlib import suppress
from datetime import datetime
from html import escape
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import socket
import sqlite3
import sys
import tempfile
import time
from urllib.parse import urlsplit
import zipfile

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web
from server.accounts import display_name, name_key
from server.save_slots import DB as SLOTS_DB

ROOT = Path(__file__).resolve().parent
CSS = """body{background:#10171c;color:#e2e9e6;font:1rem/1.6 system-ui;margin:auto;padding:2rem 1rem;max-width:37rem}
h1{color:#95d9ad;font-family:Georgia,serif}h2{font-size:1.2rem;margin-top:2rem}
input,button,a.button{font:inherit;padding:.55rem .85rem;border-radius:.4rem}
input{max-width:92%;display:block;margin:.2rem 0 1rem}button,a.button{background:#314c41;color:white;border:1px solid #789789;cursor:pointer}
a{color:#aee6c0}form{margin:1rem 0}small{color:#bdc7c2}"""
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
        '<style>'+CSS+'</style><main><h1>'+escape(title)+'</h1>'+body+'</main></html>'))


def sign_in(error='', status=200):
    return page('Expanse', '<form method="post" action="/login"><label>Character name'
                '<input name="name" autocomplete="username" required></label><label>Password'
                '<input type="password" name="password" autocomplete="current-password" required></label>'
                '<button>Sign in</button></form><p role="alert">'+escape(error)+'</p>', status)


class Accounts:
    def __init__(self):
        owner = display_name(os.environ['EXPANSE_OWNER_NAME'])
        entries = [{'name':owner, 'password':os.environ['EXPANSE_OWNER_PASSWORD'],
                    'expires_at':os.environ.get('EXPANSE_OWNER_EXPIRES_AT')}]
        extra = json.loads(os.environ.get('EXPANSE_GUESTS_JSON','[]'))
        if not isinstance(extra,list):
            raise ValueError('EXPANSE_GUESTS_JSON must be an array.')
        self.owner = name_key(owner)
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
        valid = hmac.compare_digest(self.verifier(password),expected)
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
        row = self.sessions.get(token)
        if row and row[1]>time.time():
            return row[0]
        self.sessions.pop(token,None)
        return None


class Service:
    def __init__(self):
        self.auth = Accounts()
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
        self.worlds = self.data/'worlds'
        self.worlds.mkdir(exist_ok=True)
        self.update_world = os.environ.get('EXPANSE_UPDATE_WORLD_SHA256','').strip()
        if self.update_world and not re.fullmatch(r'[0-9a-f]{64}',self.update_world):
            raise ValueError('EXPANSE_UPDATE_WORLD_SHA256 must be the full SHA-256 of an imported game file.')
        self.active_game = None
        self.lock = asyncio.Lock()
        self.process = self.client = self.active = self.socket = self.socket_token = None
        self.importing = False
        self.assets = {p.name:p for p in (ROOT/'web').iterdir() if p.suffix in {'.css','.js','.svg'}}

    def bundle(self, ident):
        if not isinstance(ident,str) or not re.fullmatch(r'[0-9a-f]{64}',ident) or not (self.worlds/ident/'info.json').is_file():
            raise web.HTTPNotFound(text='Choose an imported world.')
        return self.worlds/ident

    def folder(self,key,ident):
        return self.data/'players'/hashlib.sha256(key.encode()).hexdigest()/ident

    def catalogue(self):
        return sorted(((p.parent.name,json.loads(p.read_bytes())) for p in self.worlds.glob('*/info.json')), key=lambda row:(row[1]['name'],row[0]))

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

    async def stop(self):
        if self.socket is not None:
            await self.socket.close()
        if self.client:
            await self.client.close()
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(),8)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.client = self.process = self.active = self.socket_token = self.socket = None

    async def start(self, key, ident):
        async with self.lock:
            bundle=self.bundle(ident)
            if (self.active,self.active_game)==(key,ident) and self.process and self.process.returncode is None:
                return
            if self.socket is not None and not self.socket.closed:
                raise web.HTTPConflict(text='An active play tab is using this single-player test. Close that tab before opening another game.')
            slug=json.loads((bundle/'info.json').read_bytes())['slug']
            template_args = [value for path in self.update_templates(ident,slug)
                             for value in ('--update-template',str(path))]
            await self.stop()
            save = self.folder(key,ident)
            save.mkdir(parents=True,exist_ok=True)
            # Pass a pre-bound loopback listener into the worker, closing the port-selection race.
            env = {k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','PYTHONUTF8','PYTHONUNBUFFERED','VIRTUAL_ENV','PYTHONPATH')}
            env['EXPANSE_WORKER_TOKEN'] = secrets.token_urlsafe(32)
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
                listener.bind(('127.0.0.1',0))
                listener.listen(16)
                self.worker_url = f'http://127.0.0.1:{listener.getsockname()[1]}'
                self.process = await asyncio.create_subprocess_exec(sys.executable,str(ROOT/'private_game.py'),
                    '--fd',str(listener.fileno()),'--name',self.auth.records[key][0],
                    '--world',str(bundle/'games'/slug),'--directory',str(save),
                    *template_args,
                    env=env,pass_fds=(listener.fileno(),))
            self.client = ClientSession(headers={'X-Worker-Key':env['EXPANSE_WORKER_TOKEN']},timeout=ClientTimeout(total=150))
            for _ in range(120):
                if self.process.returncode is not None:
                    await self.stop()
                    raise web.HTTPServiceUnavailable(text='Expanse could not start. Check the service logs.')
                try:
                    async with self.client.get(self.worker_url+'/api/config',timeout=1) as answer:
                        if answer.status==200:
                            self.active,self.active_game=key,ident
                            return
                except (OSError,asyncio.TimeoutError):
                    pass
                await asyncio.sleep(.1)
            await self.stop()
            raise web.HTTPServiceUnavailable(text='The game took too long to start.')

    async def landing(self,req):
        key = self.identity(req)
        if not key:
            return sign_in()
        name,_,expiry = self.auth.records[key]
        contents = '<p>Signed in as <strong>'+escape(name)+'</strong>.</p>'
        if expiry is not None:
            from datetime import timezone
            contents += '<p>Account access ends '+datetime.fromtimestamp(expiry,timezone.utc).isoformat()+' UTC.</p>'
        entries=self.catalogue()
        for ident,info in entries:
            contents+='<h2>'+escape(info['name'])+'</h2>'
            if sum(row['name']==info['name'] for _,row in entries)>1:
                contents += '<small>Game file '+ident[:12]+'</small>'
            contents+='<form action="/enter" method="post"><input type="hidden" name="game" value="'+ident+'"><button>Play Expanse</button></form>'
            contents+='<a href="/world.expanse?game='+ident+'" download>Download imported world</a>'
            if self.has_save(key,ident):
                contents+=' · <a href="/manual-saves.zip?game='+ident+'" download>Download your manual saves</a>'
        if key==self.auth.owner:
            contents += ('<h2>Import a game</h2><form action="/world/import" enctype="multipart/form-data" method="post"><label>'
                         'Game file<input name="world" type="file" accept=".expanse" required></label>'
                         '<button>Import world</button></form>')
        elif not entries:
            contents += '<p>The owner has not imported a world yet.</p>'
        return page('Expanse',contents+'<form method="post" action="/logout"><button>Sign out</button></form>')

    def has_save(self,key,ident):
        folder = self.folder(key,ident)
        return (folder/SLOTS_DB).is_file() or any(folder.glob('world_state*_single.json'))

    async def login(self,req):
        form=await req.post()
        name,password=form.get('name'),form.get('password')
        token = self.auth.authenticate(name,password) if isinstance(name,str) and isinstance(password,str) and len(password)<=128 else None
        if not token:
            return sign_in('Sign-in failed. Check the name, password and account access.',403)
        response = web.HTTPSeeOther('/')
        response.set_cookie(self.cookie,token,path='/',httponly=True,secure=not self.local,samesite='Strict',max_age=43200)
        return response

    async def logout(self,req):
        key = req['key']
        self.auth.sessions.pop(req.cookies[self.cookie],None)
        async with self.lock:
            if self.active==key:
                await self.stop()
        response = web.HTTPSeeOther('/')
        response.del_cookie(self.cookie,path='/')
        return response

    async def enter(self,req):
        form=await req.post()
        await self.start(req['key'],form.get('game'))
        return web.HTTPSeeOther('/play')

    async def install(self,req):
        if req['key']!=self.auth.owner:
            raise web.HTTPForbidden()
        if self.importing or (self.socket is not None and not self.socket.closed):
            raise web.HTTPConflict(text='Close the play tab and let any current import finish first.')
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

    def active_client(self,req):
        if self.active!=req['key'] or not self.client or self.client.closed or self.process.returncode is not None:
            raise web.HTTPConflict(text='Reopen your game from the start page.')
        return self.client

    async def api(self,req):
        client=self.active_client(req)
        body=await req.read()
        if len(body)>65536:
            raise web.HTTPBadRequest()
        async with client.request(req.method,self.worker_url+req.path_qs,data=body,
                                  headers={'Content-Type':'application/json'}) as reply:
            return web.Response(body=await reply.read(),status=reply.status,content_type=reply.content_type)

    async def socket_route(self,req):
        client=self.active_client(req)
        if self.socket is not None and not self.socket.closed:
            raise web.HTTPConflict(text='Close the existing play tab first.')
        ws=web.WebSocketResponse(max_msg_size=65536,heartbeat=30)
        self.socket=ws
        self.socket_token=req.cookies[self.cookie]
        try:
            async with client.ws_connect(self.worker_url+'/ws',max_msg_size=32*1024*1024) as game:
                await ws.prepare(req)
                async def copy(source,dest):
                    async for msg in source:
                        if msg.type!=WSMsgType.TEXT or self.identity(req)!=req['key']:
                            break
                        await dest.send_str(msg.data)
                tasks=[asyncio.create_task(copy(ws,game)),asyncio.create_task(copy(game,ws))]
                try:
                    await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for t in tasks:t.cancel()
                    await asyncio.gather(*tasks,return_exceptions=True)
        finally:
            if self.socket is ws:
                self.socket=self.socket_token=None
        return ws

    async def backup(self,req):
        key=req['key']
        ident=req.query.get('game')
        bundle=self.bundle(ident)
        if not self.has_save(key,ident):
            raise web.HTTPNotFound(text='Make a manual save in the game first.')
        async with self.lock:
            if self.active==key:
                if self.socket is not None and not self.socket.closed:
                    raise web.HTTPConflict(text='Close the play tab, then download your saved game.')
                await self.stop()
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
                if self.socket is not None and self.socket_token and not self.auth.lookup(self.socket_token):
                    await self.socket.close(code=1008,message=b'Sign in again.')
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
        if req.path not in ('/','/healthz','/login','/mode.html') and not key:
            if req.path=='/play':
                return web.HTTPSeeOther('/')
            return web.json_response({'error':'Sign in first.'},status=401)
        req['key']=key
        try:
            return await handler(req)
        except (ValueError,zipfile.BadZipFile) as exc:
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
                    web.post('/world/import',service.install),web.get('/world.expanse',world),
                    web.get('/manual-saves.zip',service.backup),web.get('/play',play),web.get('/ws',service.socket_route),
                    web.get('/api/{path:.*}',service.api),web.post('/api/{path:.*}',service.api),web.get('/{filename}',asset)])
    return app


if __name__=='__main__':
    os.umask(0o077)
    app=make_app()
    web.run_app(app,host='0.0.0.0' if os.environ.get('RENDER') or not os.environ.get('EXPANSE_PUBLIC_URL','').startswith('http://') else '127.0.0.1',
                port=int(os.environ.get('PORT','10000')),access_log=None)
