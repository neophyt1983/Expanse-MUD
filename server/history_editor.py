"""Creator-only new-world history preview/publish controller."""
from copy import deepcopy
import hashlib
import json
import re
import secrets
import time
import tempfile
from pathlib import Path
from urllib.parse import urlparse



def handle(h,slug,body,app):
    from engine.history_publisher import prepare,publish_new_world
    from engine.historical_simulation import creator_schema
    from engine import history_templates
    raw_root=app.GAMES_DIR/slug
    root=raw_root.resolve()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',slug) or raw_root.is_symlink() or root.parent!=app.GAMES_DIR.resolve() or not root.is_dir():
        h._json({'error':'Unknown source world'},404);return
    if body is not None and h.headers.get('Origin') and urlparse(h.headers['Origin']).netloc!=h.headers.get('Host'):
        h._json({'error':'Open history tools from this server'},403);return
    try:
        template=history_templates.snapshot(root)
        with app._editors_lock:
            from editor.cli import FILE_MAP,Editor
            # Never re-open unchecked source paths after the descriptor snapshot.
            # Editor normalization still runs, but only against checked bytes.
            with tempfile.TemporaryDirectory(prefix='expanse-history-editor-') as temp:
                for name in set(FILE_MAP.values())|{'population.json'}:
                    if name in template['files']:Path(temp,name).write_bytes(template['files'][name])
                checked=Editor(temp)
            checked.data_dir=root
            ed=app._editors.get(slug)
            data=deepcopy(checked.data)
            # Disk snapshot owns untouched fields; only explicit Editor drafts
            # override it. A preview never creates or mutates the Editor cache.
            if ed is not None:
                for kind in ed.dirty:
                    if kind in FILE_MAP:data[kind]=deepcopy(ed.data[kind])
            if getattr(ed,'population_manifest_dirty',False):
                raw=json.dumps(ed.population_manifest,allow_nan=False).encode()
                history_templates._validate_file('population.json',raw)
                template['files']['population.json']=raw
                template['signature']=history_templates.signature(template['files'],template['directories'])
            metadata=history_templates._json(template['files']['metadata.json'],'metadata.json') if 'metadata.json' in template['files'] else {}
            source=hashlib.sha256(json.dumps([data,metadata,template['source_signature'],template['signature']],sort_keys=True).encode()).hexdigest()
            principal='host' if h._local_owner() else h.headers.get('X-Expanse-Player','')
            if body is None:
                saved=history_templates._json(template['files']['history.json'],'history.json') if 'history.json' in template['files'] else None
                from engine import worldtime, chronicles
                cfg={'fresh_world':True,'history_plan':{'seed':17,'present_minute':worldtime.initial_minute(metadata),'events':[]},'selection':[],'faction_pairs':[],'civic_years':100,'rules':{}}
                if 'history-rules.json' in template['files']:
                    saved_rules=history_templates._json(template['files']['history-rules.json'],'history-rules.json')
                    if saved_rules:cfg=deepcopy(saved_rules)
                archive=history_templates._json(template['files'][chronicles.ARCHIVE],chronicles.ARCHIVE) if chronicles.ARCHIVE in template['files'] else chronicles.generate(data.get('room',[]),data.get('npc',[]),data.get('group',[]),data.get('species',[]),metadata,chronicles.legacy_seed(slug),saved_rules if 'history-rules.json' in template['files'] else {},saved or {})
                from engine import field_archive
                book_file = template['files'].get(field_archive.FILE.as_posix())
                if book_file:
                    field_archive.compile_volume(archive,json.loads(book_file),*[
                        data.get(k,[]) for k in ('room','npc','group','species','race','item','encounter')])
                h._json(dict(chronicles=archive,config=cfg,rules=creator_schema(),references={k:[{'id':r['id'],'name':r.get('name',r['id'])} for r in data.get(k,[])] for k in ('npc','group','room')},
                    history=saved,text='Preview does not change the source world. Publish creates a separate new world, never applies to the running game.'));return
            if not isinstance(body,dict) or set(body)-{'action','config','target','preview_token'}:
                raise ValueError('Expected action, config, target and optional preview_token')
            cfg=body.get('config');target=body.get('target')
            if not isinstance(cfg,dict) or not isinstance(target,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,31}',target):
                raise ValueError('Use a lowercase new-world name starting with a letter, only letters/digits/underscores, at most 32 characters, and object configuration')
            destination=app.GAMES_DIR/target
            canonical=json.dumps([cfg,target],sort_keys=True,allow_nan=False)
            now=time.monotonic()
            for key,entry in list(app._history_previews.items()):
                if now-entry['created']>1200:app._history_previews.pop(key,None)
            if body.get('action')=='preview':
                if destination.exists() or destination.is_symlink():raise FileExistsError('New-world name is already in use')
                _,result,warnings=prepare(data,metadata,cfg,template=template)
                token=secrets.token_urlsafe(24)
                while len(app._history_previews)>=32:app._history_previews.pop(next(iter(app._history_previews)))
                app._history_previews[token]=dict(created=now,source=source,slug=slug,principal=principal,canonical=canonical)
                h._json(dict(preview_token=token,summary={'actors':len(result['actors']),'factions':len(result['factions']),'events':len(result['events']),'steps':result['steps']},history=result,warnings=warnings,
                    text='Preview only. Inspect proposed state and history before creating the separate world.'));return
            if body.get('action')!='publish':raise ValueError('Choose preview or publish')
            entry=app._history_previews.get(body.get('preview_token'))
            if not entry or any(entry[k]!=v for k,v in dict(source=source,slug=slug,principal=principal,canonical=canonical).items()):
                h._json({'error':'Preview expired or source/settings changed. Preview again.'},409);return
            if entry.get('published'):
                if not (destination/'metadata.json').exists():raise ValueError('Previously created target is no longer present')
                if json.loads((destination/'metadata.json').read_text()).get('historical_initialization',{}).get('result_hash')!=entry.get('published_hash'):
                    raise ValueError('Previously created target has changed; inspect it rather than publishing again')
                h._json(entry['published']);return
            result=publish_new_world(destination,data,metadata,cfg,template=template)
            response=dict(ok=True,target=target,warnings=result['warnings'],text='Created '+target+'. Source and running game were not changed. Select the new draft, export it, then import the .expanse file to play.')
            entry['published_hash']=result['history_hash']
            entry['published']=response
            h._json(response)
    except (ValueError,OSError,TypeError,KeyError) as exc:h._json({'error':str(exc)},400)
