"""Creator-owned data-only pixel library. Immutable revisions, explicit binding CAS."""
import copy
import json
import os
from pathlib import Path
from engine.fighting_pose import STANCES
import re
import tempfile
import threading
import uuid

SIZES = {'tile': 24, 'character': 16, 'equipment': 16}
RIGS = {f'humanoid:{stature}:{build}' for stature in ('short','average','tall') for build in ('slim','average','broad')}
SLOTS = {'body','armor','head','hands','legs','feet','weapon','offhand','charm','appearance_tunic','appearance_cloak','appearance_hat'}
KINDS = {'rooms':'tile','npcs':'character','races':'character','items':'equipment'}
_LOCK = threading.RLock()
_CACHE = {}
_PUBLIC_CACHE = {}
_PUBLIC_CACHE_LOCK = threading.Lock()
MAX_BYTES = 8_000_000

def validate(doc):
    if not isinstance(doc, dict) or doc.get('version') != 1 or doc.get('kind') not in SIZES:
        raise ValueError('Unsupported art document')
    n = 32 if doc['kind']!='tile' and doc.get('width')==32 else SIZES[doc['kind']]
    if type(doc.get('width')) is not int or type(doc.get('height')) is not int or doc['width'] != n or doc['height'] != n:
        raise ValueError(f'{doc["kind"]} requires {n} × {n} pixels')
    for key, limit in [('name',80),('author',120),('license',200)]:
        if not isinstance(doc.get(key),str) or len(doc[key]) > limit:
            raise ValueError('Invalid '+key)
    layers=doc.get('layers')
    if not isinstance(layers,list) or not 1 <= len(layers) <= 8:
        raise ValueError('Use 1–8 layers')
    clean=[]
    for layer in layers:
        if not isinstance(layer,dict) or not isinstance(layer.get('name'),str) or len(layer['name'])>80 or type(layer.get('visible')) is not bool:
            raise ValueError('Invalid layer')
        pixels=layer.get('pixels')
        if not isinstance(pixels,list) or len(pixels)!=n*n or any(p is not None and (not isinstance(p,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?',p)) for p in pixels):
            raise ValueError('Invalid pixel data')
        clean.append(dict(name=layer['name'],visible=layer['visible'],pixels=pixels.copy()))
    registration={}
    if 'pose' in doc:
        if doc['kind']!='character' or doc['pose'] not in STANCES:raise ValueError('Invalid fighting pose')
        registration['pose']=doc['pose']
    if 'rig' in doc:
        if doc['rig'] not in RIGS or doc['kind']=='tile':raise ValueError('Invalid anatomy registration')
        registration['rig']=doc['rig']
    if 'slot' in doc:
        if doc['kind']!='equipment' or doc['slot'] not in SLOTS:raise ValueError('Invalid equipment slot')
        registration['slot']=doc['slot']
    return {**registration,**{k:doc[k] for k in ('version','kind','width','height','name','author','license')},'layers':clean}

def location(game_dir):
    root=Path(game_dir).resolve()
    path=root/'pixel-art-library.json'
    if path.is_symlink():raise ValueError('Art library must not be a symlink')
    return path

def load(game_dir, *, clone=True):
    path=location(game_dir)
    if not path.exists():return {'version':1,'assets':{},'bindings':{}}
    st=path.stat()
    if st.st_size>MAX_BYTES:raise ValueError('Art library exceeds 8 MB')
    stamp=(st.st_mtime_ns,st.st_size,st.st_ino)
    cached=_CACHE.get(str(path))
    if cached and cached[0]==stamp:return copy.deepcopy(cached[1]) if clone else cached[1]
    try:data=json.loads(path.read_text())
    except (RecursionError,UnicodeError) as exc:raise ValueError('Invalid art library encoding/nesting') from exc
    if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('assets'),dict) or len(data['assets'])>256 or not isinstance(data.get('bindings'),dict):raise ValueError('Invalid art library')
    if any(not re.fullmatch(r'[0-9a-f]{32}',key) for key in data['assets']):raise ValueError('Invalid asset ID')
    data={'version':1,'assets':{k:validate(v) for k,v in data['assets'].items()},'bindings':data['bindings']}
    for key,value in data['bindings'].items():
        if not isinstance(key,str) or key.split(':',1)[0] not in KINDS or value not in data['assets']:raise ValueError('Invalid art binding')
        kind=key.split(':',1)[0];doc=data['assets'][value]
        if doc['kind']!=KINDS[kind]:raise ValueError('Art binding kind mismatch')
        suffix='@'+doc['pose'] if doc.get('pose') else ''
        if suffix and (kind not in ('races','npcs') or not key.endswith(suffix)):raise ValueError('Art binding pose mismatch')
        if kind in ('races','items') and (doc.get('rig') not in RIGS or not key.endswith(':'+doc['rig']+suffix)):raise ValueError('Art binding anatomy mismatch')
        if kind=='items' and doc.get('slot') not in SLOTS:raise ValueError('Art binding slot missing')
    _CACHE[str(path)]=(stamp,copy.deepcopy(data))
    return data

def change(game_dir,body):
    if not isinstance(body,dict):raise ValueError('Expected object')
    if body.get('action')=='starter':
        from engine.studio_subject import request
        return request(game_dir,body)
    with _LOCK:
        data=load(game_dir)
        if body.get('action')=='save':
            if len(data['assets'])>=256:raise ValueError('Library limit is 256 revisions; export drafts for archival')
            asset_id=uuid.uuid4().hex
            data['assets'][asset_id]=validate(body.get('document'))
        elif body.get('action')=='bind':
            kind=body.get('target_type');target=body.get('target_id');asset_id=body.get('asset_id')
            if kind not in KINDS or not isinstance(target,str):raise ValueError('Unsupported art target')
            rows=json.loads((Path(game_dir)/(kind+'.json')).read_text())
            if not any(row.get('id')==target for row in rows):raise ValueError('Target does not exist')
            key=kind+':'+target
            if kind in ('items','races'):
                rig=body.get('rig')
                if rig not in RIGS:raise ValueError('Select matching humanoid anatomy')
                key+=':'+rig
            pose=body.get('pose')
            if pose:
                if pose not in STANCES or kind not in ('races','npcs'):raise ValueError('Unsupported fighting pose target')
                key+='@'+pose
            if body.get('expected')!=data['bindings'].get(key):raise ValueError('Binding changed; refresh before replacing')
            if asset_id is None:data['bindings'].pop(key,None)
            else:
                doc=data['assets'].get(asset_id)
                if doc is None or doc['kind']!=KINDS[kind]:raise ValueError('Asset type does not match target')
                if doc.get('pose')!=(pose or None):raise ValueError('Art fighting pose does not match binding')
                if kind in ('items','races') and doc.get('rig')!=rig:raise ValueError('Asset anatomy does not match binding')
                if kind=='items' and doc.get('slot') not in SLOTS:raise ValueError('Equipment art requires a slot')
                data['bindings'][key]=asset_id
        else:raise ValueError('Unknown art action')
        raw=json.dumps(data,separators=(',',':'))
        if len(raw.encode())>MAX_BYTES:raise ValueError('Art library exceeds 8 MB')
        path=location(game_dir)
        fd,temp=tempfile.mkstemp(prefix='.pixel-art-',dir=path.parent)
        try:
            with os.fdopen(fd,'w') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            os.replace(temp,path)
        finally:
            if os.path.exists(temp):os.unlink(temp)
        _CACHE.pop(str(path),None)
        return {'asset_id':asset_id,'library':data}

def public_art(asset_id,doc):
    """Flatten only visible layers; never ship editor names/hidden pixels."""
    cache_key=(asset_id,id(doc))
    with _PUBLIC_CACHE_LOCK:
        cached=_PUBLIC_CACHE.get(cache_key)
        if cached is not None:return cached[1]
    pixels=[]
    for index in range(doc['width']*doc['height']):
        out=[0.,0.,0.];alpha=0.
        for layer in doc['layers']:
            value=layer['pixels'][index] if layer['visible'] else None
            if value is None:continue
            a=int(value[7:9],16)/255 if len(value)==9 else 1.
            rgb=[int(value[i:i+2],16) for i in (1,3,5)]
            combined=a+alpha*(1-a)
            if combined:out=[(rgb[i]*a+out[i]*alpha*(1-a))/combined for i in range(3)]
            alpha=combined
        pixels.append('#'+''.join(f'{min(255,max(0,int(v+.5))):02x}' for v in [*out,alpha*255]) if alpha else None)
    result={k:doc[k] for k in ('version','kind','width','height','rig','slot') if k in doc}
    result.update(id=asset_id,layers=[{'visible':True,'pixels':pixels}])
    with _PUBLIC_CACHE_LOCK:
        cached=_PUBLIC_CACHE.get(cache_key)
        if cached is not None:return cached[1]
        if len(_PUBLIC_CACHE)>=256:_PUBLIC_CACHE.pop(next(iter(_PUBLIC_CACHE)))
        _PUBLIC_CACHE[cache_key]=(doc,result)
    return result

def apply(world,visual):
    """Attach only art for permitted rooms/occupants, never expose the library."""
    try:
        if not getattr(world,'game_dir',None):return
        library=load(world.game_dir,clone=False)
    except (ValueError,OSError,TypeError):return  # broken optional art cannot halt play
    if not library['bindings']:return
    assets={}
    def reference(art):
        assets[art['id']]=art
        return {k:art[k] for k in ('id','rig','slot') if k in art}
    def get(kind,target):
        if not isinstance(target,str):return None
        key=library['bindings'].get(kind+':'+target)
        doc=library['assets'].get(key)
        if doc:return public_art(key,doc)
    for tile in visual.get('tiles',[]):
        # Interior artwork must never reveal rooms through an exterior facade.
        art=get('rooms',tile.get('surface_id',tile['id'])) if not tile.get('exterior') and not tile.get('learnedOnly') and not tile.get('scenery') else None
        if art:tile['pixel_art']=reference(art)
    for actor in visual.get('actors',[]):
        entity=world.entities.get(actor['id'])
        art=get('npcs',entity.source_def) if entity and not entity.is_player else None
        if art:actor['pixel_art']=reference(art)
        stance=actor.get('combat_pose',{}).get('stance')
        if stance and entity and not entity.is_player and entity.source_def:
            pose_art=get('npcs',entity.source_def+'@'+stance)
            if pose_art:actor['pose_art']=reference(pose_art)
        if entity and actor.get('paperdoll'):
            doll=actor.get('paperdoll',{});features=doll.get('characteristics',{})
            if features.get('silhouette','humanoid')!='humanoid':continue
            rig='humanoid:'+features.get('stature','average')+':'+features.get('build','average')
            base=get('races',(entity.race or doll.get('family',''))+':'+rig)
            if base and base.get('rig')==rig:doll['pixel_base']=reference(base)
            if stance:
                posed=get('races',(entity.race or doll.get('family',''))+':'+rig+'@'+stance)
                if posed:doll['pose_base']=reference(posed)
            for item in doll.get('equipment',[]):
                if not item.get('item_id'):continue
                gear=get('items',item['item_id']+':'+rig)
                if gear and gear.get('rig')==rig and gear.get('slot')==item['slot']:
                    item['pixel_art']=reference(gear)
                    item['layer']={'armor':'body','appearance_tunic':'body','appearance_cloak':'cloak','appearance_hat':'head'}.get(item['slot'],item['slot'])
                    item['kind']='custom'
    if assets:visual['pixel_assets']=assets


def decorate_rooms(game_dir, rooms):
    """Same art for already-authorized atlas detail cells; no new geography."""
    from types import SimpleNamespace
    visual={'tiles':rooms}
    apply(SimpleNamespace(game_dir=str(game_dir),entities={}),visual)
    return visual.get('pixel_assets',{})
