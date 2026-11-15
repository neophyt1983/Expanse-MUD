"""Inert Creator tax plans. Nothing here collects money or changes gameplay."""
import hashlib
import json
import math
import os
import re
import secrets
import stat
from urllib.parse import urlparse

FILE = 'creator-tax-plans.json'
LIMIT = 512 * 1024


def validate(config, refs):
    if not isinstance(config, dict) or config.get('version') != 1 or config.get('mode') != 'editor_only':
        raise ValueError('Expected version 1, editor_only tax plans')
    rows = config.get('policies')
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError('Use at most 100 tax plans')
    seen = set()
    for p in rows:
        if not isinstance(p, dict):raise ValueError('Each tax plan must be an object')
        ident=p.get('id')
        if not isinstance(ident,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}',ident) or ident in seen:
            raise ValueError('Use unique lowercase tax IDs (letters, numbers and underscores)')
        seen.add(ident)
        for field,limit in [('name',120),('notes',2000),('exemptions',2000)]:
            value=p.get(field,'')
            if not isinstance(value,str) or len(value)>limit:raise ValueError('Invalid '+field)
        if not p.get('name','').strip():raise ValueError('Give each plan a name')
        if p.get('basis') not in ('income','sale','property','flat'):raise ValueError('Choose a supported assessment basis')
        rate=p.get('rate')
        if type(rate) not in (int,float) or not math.isfinite(rate) or not 0<=rate<=(1000000 if p['basis']=='flat' else 100):
            raise ValueError('Percentage must be 0–100; flat gold 0–1,000,000')
        days=p.get('interval_days')
        if type(days) is not int or not 1<=days<=10000:raise ValueError('Collection interval must be 1–10,000 world days')
        rooms=p.get('rooms')
        if not isinstance(rooms,list) or not rooms or len(rooms)>1000 or any(not isinstance(x,str) or x not in refs['room'] for x in rooms) or len(set(rooms))!=len(rooms):
            raise ValueError('Choose valid, distinct jurisdiction rooms')
        if not isinstance(p.get('recipient'),str) or p['recipient'] not in refs['group']:raise ValueError('Choose a recipient faction')
        if not isinstance(p.get('collector',''),str) or (p.get('collector') and p['collector'] not in refs['npc']):raise ValueError('Choose a valid collector NPC or leave unassigned')
    raw=json.dumps(config,ensure_ascii=False,allow_nan=False,indent=2).encode()+b'\n'
    if len(raw)>LIMIT:raise ValueError('Tax plans exceed size limit')
    return raw


def _read(fd,name,limit=LIMIT):
    try:f=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
    except FileNotFoundError:return None
    with os.fdopen(f,'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise ValueError('Expected regular file: '+name)
        raw=stream.read(limit+1)
        if len(raw)>limit:raise ValueError('File exceeds limit: '+name)
        return raw


def handle(h,slug,body,app):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',slug):h._json({'error':'Invalid world'},400);return
    if body is not None and h.headers.get('Origin') and urlparse(h.headers['Origin']).netloc!=h.headers.get('Host'):
        h._json({'error':'Open tax plans from this server'},403);return
    try:
        with app._editors_lock:
            parent=os.open(app.GAMES_DIR,os.O_RDONLY|os.O_DIRECTORY)
            try:fd=os.open(slug,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            finally:os.close(parent)
            try:
                refs={}
                from engine.history_templates import MAX_FILE
                for kind,file in [('room','rooms.json'),('group','groups.json'),('npc','npcs.json')]:
                    rows=json.loads(_read(fd,file,MAX_FILE) or b'[]')
                    refs[kind]=[{'id':r['id'],'name':r.get('name',r['id'])} for r in rows]
                raw=_read(fd,FILE)
                revision=hashlib.sha256(raw or b'').hexdigest()
                config=json.loads(raw) if raw is not None else dict(version=1,mode='editor_only',policies=[])
                if body is not None:
                    if not isinstance(body,dict) or set(body)!={'revision','config'}:raise ValueError('Expected configuration and revision')
                    if body['revision']!=revision:h._json({'error':'Tax plans changed elsewhere. Close and reopen before saving.'},409);return
                    raw=validate(body['config'],{k:{r['id'] for r in rows} for k,rows in refs.items()})
                    temp='.'+FILE+'.'+secrets.token_hex(12)
                    try:
                        out=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
                        with os.fdopen(out,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
                        os.replace(temp,FILE,src_dir_fd=fd,dst_dir_fd=fd)
                    finally:
                        try:os.unlink(temp,dir_fd=fd)
                        except FileNotFoundError:pass
                    revision=hashlib.sha256(raw).hexdigest();config=body['config']
                h._json(dict(config=config,revision=revision,references=refs,text='Saved editor-only plans. No taxes collected or gameplay changed.' if body is not None else 'Editor-only plans. No gameplay collection.'))
            finally:os.close(fd)
    except (ValueError,OSError,TypeError,KeyError) as exc:h._json({'error':str(exc)},400)
