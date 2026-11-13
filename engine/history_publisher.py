"""Publish a validated historical scenario into an exclusively NEW world folder.

No save migration or in-place update path. A pending sentinel blocks loader use
until publication completes. On interruption leave the sentinel for inspection;
never recursively remove a directory that might contain creator work.
"""
from copy import deepcopy
import json
import hashlib
import os
from pathlib import Path
import tempfile
from engine.historical_simulation import simulate_new_world
from engine.world_history import HistoryError


def prepare(data, metadata, config, *, template=None):
    from editor.cli import FILE_MAP
    from engine import loader,history_templates
    extra_files=history_templates.extras(template)
    if not isinstance(metadata,dict):raise HistoryError('Metadata must be an object')
    result=simulate_new_world(data,config)
    content=deepcopy(data);meta=deepcopy(metadata)
    npcs={n['id']:n for n in content.get('npc',[])}
    groups={g['id']:g for g in content.get('group',[])}
    rooms={r['id']:r for r in content.get('room',[])}
    ownership={r['source_id']:set(r.get('generated_fields',[])) for r in config.get('selection',[])}
    allowed={'gold','health','life_profile','birth_epoch'}
    for aid,proposal in result['npc_proposals'].items():
        npc=npcs[aid];owned=ownership[aid]
        if owned-allowed:raise HistoryError('Unknown generated NPC field ownership')
        if 'gold' in owned or 'gold' not in npc:npc['gold']=proposal['gold']
        if 'health' in owned:npc['historical_initial_hp']=proposal['hp']
        place=npc.get('home_room') or npc.get('work_room') or npc.get('spawn_room')
        old={**rooms.get(place,{}).get('npc_life_defaults',{}),**npc.get('life_profile',{})}
        npc['life_profile']={**old,**proposal['life_profile']} if 'life_profile' in owned else {**proposal['life_profile'],**old}
        sp=npc.setdefault('social_profile',{})
        if 'birth_epoch' in owned or ('born_minute' not in sp and 'age_epoch_minute' not in sp):
            sp['born_minute']=proposal['social_profile']['born_minute']
    pair_rules={frozenset((r['a'],r['b'])):r for r in config.get('faction_pairs',[])}
    for p in result['relation_proposals']:
        rule=pair_rules[frozenset((p['a'],p['b']))]
        if p['locked']:continue
        for a,b in ((p['a'],p['b']),(p['b'],p['a'])):
            g=groups[a];relations=g.setdefault('relations',{});diplomacy=g.setdefault('diplomacy',{})
            existing=b in relations or b in diplomacy or b in g.get('hostile_to',[]) or '*' in g.get('hostile_to',[])
            if existing and rule.get('generated_relation') is not True:continue
            old=diplomacy.get(b,{})
            low=old.get('minimum',rule.get('minimum',0));high=old.get('maximum',rule.get('maximum',100))
            if not low<=p['base']<=high:raise HistoryError('Generated relation exceeds authored diplomacy bounds')
            relations[b]=p['relation'];diplomacy[b]={**old,'base':p['base'],'minimum':low,'maximum':high}
    from engine import dynamic_diplomacy
    live=config.get('live_diplomacy',{})
    dynamic_diplomacy.validate(live,groups)
    if live:meta['dynamic_diplomacy']=deepcopy(live)
    # All generation happens before first play. No startup rerun flag is written.
    result['template']={name:hashlib.sha256(raw).hexdigest() for name,raw in extra_files.items()}
    result['template_directories']=(template or {}).get('directories',[])
    result['template_signature']=(template or {}).get('signature')
    result['template_regenerated']=[name for name in sorted((template or {}).get('files',{})) if name in history_templates.DERIVED]
    result['status']='generated_initial_state'
    result['limitations']=[x for x in result['limitations'] if not x.startswith('No save/startup hook')]
    result['limitations'].append('Only projected initial fields are applied; live ancestry, terrain and warfare are not implemented.')
    result.pop('hash',None)
    result['hash']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    meta['historical_initialization']={'version':1,'result_hash':result['hash'],'present_minute':config['history_plan']['present_minute']}
    from engine import worldtime
    if config['history_plan']['present_minute'] not in (480, worldtime.initial_minute(metadata)):
        raise HistoryError('History must use the campaign start minute or the legacy 480 epoch')
    payloads={FILE_MAP[k]:v for k,v in content.items() if k in FILE_MAP}
    from engine import chronicles
    payloads[chronicles.ARCHIVE]=chronicles.generate(content.get('room',[]),content.get('npc',[]),
        content.get('group',[]),content.get('species',[]),meta,config['history_plan']['seed'],config,result)
    from engine import field_archive
    book_file=extra_files.get(field_archive.FILE.as_posix())
    if book_file:
        field_archive.compile_volume(payloads[chronicles.ARCHIVE],json.loads(book_file),*[
            content.get(k,[]) for k in ('room','npc','group','species','race','item','encounter')])
    payloads.update({'metadata.json':meta,'history.json':result,'history-rules.json':deepcopy(config)})
    with tempfile.TemporaryDirectory(prefix='expanse-history-validate-') as tmp:
        for directory in (template or {}).get('directories',[]):Path(tmp,directory).mkdir(parents=True,exist_ok=True)
        for name,raw in extra_files.items():
            path=Path(tmp,name);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        history_templates.validate_staged(tmp,content,extra_files)
        for name,value in payloads.items():
            Path(tmp,name).write_text(json.dumps(value,allow_nan=False),encoding='utf-8')
        world=loader.build_world(tmp)
        errors,warnings=loader.validate_world(world)
        if errors:raise HistoryError('Generated world validation: '+'; '.join(errors))
        loader.spawn_npcs(world)
        if result['template_regenerated']:
            warnings.append('Derived template records are regenerated or replaced in the new world only: '+', '.join(result['template_regenerated'])+'; original source histories remain unchanged.')
        # Build/spawn are the same entry points used by the actual game server.
    return payloads,result,warnings


def publish_new_world(target,data,metadata,config,*,template=None):
    target=Path(target)
    from engine.exchange import SLUG_RE
    if not SLUG_RE.fullmatch(target.name):raise HistoryError("New world names require lowercase letters/digits/underscores, start with a letter, and at most 32 characters")
    if target.exists() or target.is_symlink():raise FileExistsError('Refusing any existing world target')
    from engine import history_templates
    extra_files=history_templates.extras(template)
    payloads,result,warnings=prepare(data,metadata,config,template=template)
    target.mkdir(mode=0o700)  # Exclusive reservation; races cannot replace a world.
    pending=target/'history-build.pending'
    with pending.open('x',encoding='utf-8') as f:
        f.write('Incomplete historical world publication. Do not play or rerun into this folder.\n');f.flush();os.fsync(f.fileno())
    for directory in (template or {}).get('directories',[]):(target/directory).mkdir(parents=True,exist_ok=True)
    for name,raw in extra_files.items():
        path=target/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    for name,value in payloads.items():
        with (target/name).open('x',encoding='utf-8') as f:
            json.dump(value,f,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    for directory in sorted([target,*[p for p in target.rglob('*') if p.is_dir()]],key=lambda p:len(p.parts),reverse=True):
        fd=os.open(directory,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    pending.unlink()
    fd=os.open(target,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return {'path':str(target),'history_hash':result['hash'],'warnings':warnings}
