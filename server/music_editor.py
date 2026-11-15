"""Update just the selected world's soundtrack through the creator API."""
import hashlib
import json
import os
import re
import secrets
from urllib.parse import urlparse
from engine.soundtrack import VENUES, area_names
from server.tax_editor import _read


def handle(h,slug,body,app):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',slug):
        return h._json({'error':'Invalid world'},400)
    if body is not None and h.headers.get('Origin') and urlparse(h.headers['Origin']).netloc!=h.headers.get('Host'):
        return h._json({'error':'Open the soundtrack editor from this server.'},403)
    try:
        with app._editors_lock:
            parent=os.open(app.GAMES_DIR,os.O_RDONLY|os.O_DIRECTORY)
            try:fd=os.open(slug,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            finally:os.close(parent)
            try:
                raw=_read(fd,'metadata.json',16*1024*1024)
                meta=json.loads(raw);TRACKS={'silence':'Silence',**meta.get('music_tracks',{})};revision=hashlib.sha256(raw).hexdigest()
                areas=area_names(meta,json.loads(_read(fd,'rooms.json',128*1024*1024)))
                if body is not None:
                    if body.get('revision')!=revision:return h._json({'error':'World changed. Reopen the soundtrack editor to load the latest settings.'},409)
                    cfg=body['config']
                    if cfg['world'] not in TRACKS or not isinstance(cfg['areas'],dict) or any(k not in areas or v not in TRACKS for k,v in cfg['areas'].items()):
                        raise ValueError('Choose a listed area and track.')
                    venues=cfg.get('venues',{})
                    if not isinstance(venues,dict) or any(k not in VENUES or (v!='inherit' and v not in TRACKS) for k,v in venues.items()):
                        raise ValueError('Choose a listed building type and track.')
                    meta['soundtrack']={**cfg,'venues':venues} if venues else {'world':cfg['world'],'areas':cfg['areas']}
                    raw=(json.dumps(meta,indent=2,ensure_ascii=False)+'\n').encode()
                    temp='.music-'+secrets.token_hex(8)
                    try:
                        with os.fdopen(os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644,dir_fd=fd),'wb') as out:
                            out.write(raw);out.flush();os.fsync(out.fileno())
                        os.replace(temp,'metadata.json',src_dir_fd=fd,dst_dir_fd=fd)
                    finally:
                        try:os.unlink(temp,dir_fd=fd)
                        except FileNotFoundError:pass
                    revision=hashlib.sha256(raw).hexdigest()
                return h._json(dict(revision=revision,tracks=TRACKS,venues=VENUES,areas=areas,config=meta.get('soundtrack',{'world':'silence','areas':{}})))
            finally:os.close(fd)
    except (ValueError,TypeError,KeyError,OSError,AttributeError) as exc:return h._json({'error':str(exc)},400)

