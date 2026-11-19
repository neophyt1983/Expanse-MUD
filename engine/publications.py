"""Immutable edition/source records and actual use of finite physical books.

Reading is an event; projections and time alone never manufacture copies or
knowledge. A quotation keeps its source's evidence roots. Later corrections
are separate claims/editions and cannot rewrite an older book's text.
"""
from copy import deepcopy
from hashlib import sha256
import json

KEY='publications_v1'
MEMORY='publication_readings_v1'
MAX_EDITIONS=4096
MAX_MEMORIES=128
MAX_EXCERPT=4000
QUIET_MINUTES=15_000
INACTIVE_MINUTES=90_000
CERTAINTY={'observed','sourced','rumor','opinion','uncertain'}
RELATIONS={'copy','quote','revision'}


def _text(item):
    return item.get('read_text') or item.get('text') or item.get('description') or ''


def _identity(item):
    info=item.get('publication',{})
    info=info if isinstance(info,dict) else {}
    work=info.get('work_id') or 'item:'+item['id']
    signature=sha256(json.dumps({'text':_text(item),'publication':info},sort_keys=True,
                               separators=(',',':'),ensure_ascii=False).encode()).hexdigest()[:20]
    return work,info.get('edition_id') or work+':'+signature


def _readable(item):
    return bool(item and isinstance(_text(item),str) and
                (item.get('read_text') or item.get('readable') or item.get('publication')))


def _minute(world):
    from engine import worldtime
    return int(getattr(world,'living_state',{}).get('minute',worldtime.initial_minute(world.metadata)))


def _index(world):
    return {_identity(item)[1]:item for item in world.items.values() if _readable(item)}


def source(world,item_id):
    """Read-only source identity. Callers decide whether an actor knows it."""
    item=world.items.get(item_id)
    if not _readable(item):return None
    info=item.get('publication',{});info=info if isinstance(info,dict) else {}
    work,edition=_identity(item)
    links=deepcopy(info.get('derives_from',[]));claims=deepcopy(info.get('claims',[]))
    roots=set(info.get('evidence_roots',[]))
    roots.update(claim['evidence_root'] for claim in claims if claim.get('evidence_root'))
    inherited=set();index=None;visited={edition}
    queue=list(links)
    while queue and len(visited)<=64:
        link=queue.pop(0);ident=link.get('edition_id')
        inherited.update(link.get('evidence_roots',[]))
        if ident in visited:continue
        visited.add(ident)
        if index is None:index=_index(world)
        parent=index.get(ident)
        if not parent:continue
        parent_info=parent.get('publication',{}) or {}
        parent_work,_=_identity(parent)
        parent_links=parent_info.get('derives_from',[])
        parent_roots=set(parent_info.get('evidence_roots',[]))
        parent_roots.update(claim['evidence_root'] for claim in parent_info.get('claims',[]) if claim.get('evidence_root'))
        if not parent_links and not parent_roots:parent_roots.add(parent_work)
        inherited.update(parent_roots);queue.extend(parent_links)
    # Reprints and excerpts do not become independent confirmation simply by
    # carrying a new title/item/edition. A revision may add explicit new roots.
    copied=bool(links) and all(link.get('relation') in ('copy','quote') for link in links)
    roots=inherited if copied else roots|inherited
    if not roots:roots={link['edition_id'] for link in links} if copied else {work}
    for claim in claims:
        claim.setdefault('certainty','sourced')
        claim.setdefault('evidence_root',sorted(roots)[0])
    return dict(kind='item',id=item_id,source_id=edition,edition_id=edition,work_id=work,
                evidence_roots=sorted(roots),claims=claims,derives_from=links,
                title=item.get('name',item_id),author=info.get('author',''),
                issued_minute=info.get('issued_minute',info.get('edition_minute')))


def _physical(world,actor,item_id):
    return (world.entities.get(actor.id) is actor and actor.alive and actor.location in world.rooms
            and (item_id in actor.inventory or item_id in world.rooms[actor.location].items))


def record_read(world,actor,item_id):
    """Record one real local/carried read, with no new independent evidence."""
    row=source(world,item_id)
    if row is None or not _physical(world,actor,item_id):
        raise ValueError('Read an actual book here or in your inventory first.')
    from engine import sleep_movement
    if sleep_movement.asleep(world,actor):raise ValueError('Wake before reading.')
    now=_minute(world)
    memories=actor.progress.setdefault(MEMORY,{})
    previous=memories.get(row['edition_id'],{})
    if isinstance(previous.get('source'),dict) and type(previous.get('read_minute')) is int and now<=previous['read_minute']:
        return deepcopy(previous['source'])
    record={'source':deepcopy(row),'read_minute':now,'excerpt':_text(world.items[item_id])[:MAX_EXCERPT]}
    memories[row['edition_id']]=record
    while len(memories)>MAX_MEMORIES:memories.pop(next(iter(memories)))
    state=getattr(world,'living_state',None)
    if state is None:world.living_state={};state=world.living_state
    ledger=state.setdefault(KEY,{'version':1,'editions':{}})['editions']
    saved=ledger.get(row['edition_id'])
    if saved is None and len(ledger)<MAX_EDITIONS:
        saved={'source':deepcopy(row),'first_use':now,'last_use':now,'reads':0}
        ledger[row['edition_id']]=saved
    if saved is not None and now>=saved['last_use']:
        saved['reads']=min(1_000_000_000,saved['reads']+1);saved['last_use']=now
    if actor.is_player:world.dirty_players=getattr(world,'dirty_players',set())|{actor.id}
    return row


def _stock(world):
    """Count actual existing units only; authored infinite shop stock is excluded."""
    from collections import Counter
    stock=Counter(iid for actor in world.entities.values() for iid in actor.inventory)
    stock.update(iid for room in world.rooms.values() for iid in room.items)
    state=getattr(world,'living_state',{})
    for row in state.get('physical_locks',{}).values():stock.update(row.get('contents',[]))
    for row in state.get('economy',{}).get('shops',{}).values():
        stock.update({iid:count for iid,count in row.get('stock',{}).items() if type(count) is int and count>0})
    for row in getattr(world,'shop_state',{}).values():
        stock.update({iid:count for iid,count in row.items() if type(count) is int and count>0})
    # An unopened authored container still contains its actual finite contents.
    for rid,details in getattr(world,'room_details',{}).items():
        for row in details.get('locks',[]):
            if rid+':'+row['id'] not in state.get('physical_locks',{}):stock.update(row.get('contents',[]))
    return stock


def view(world,item_id):
    """Edition history and circulation. This is not an NPC knowledge grant."""
    current=source(world,item_id)
    if current is None:return None
    now=_minute(world);edition=current['edition_id'];stock=_stock(world);copies=0;survivors=[];later=[]
    for ident,count in stock.items():
        if count<=0 or not _readable(world.items.get(ident)):continue
        candidate=source(world,ident)
        if candidate['edition_id']==edition:copies+=count
        elif any(link.get('edition_id')==edition and link.get('relation')=='quote' for link in candidate['derives_from']):
            survivors.append({'item':ident,'edition_id':candidate['edition_id'],'title':candidate['title'],'copies':count})
        elif any(link.get('edition_id')==edition for link in candidate['derives_from']):
            later.append({'item':ident,'edition_id':candidate['edition_id'],'title':candidate['title'],'copies':count})
    saved=getattr(world,'living_state',{}).get(KEY,{}).get('editions',{}).get(edition,{})
    info=world.items[item_id].get('publication',{})
    cfg=info.get('circulation',{}) if isinstance(info,dict) else {}
    quiet=cfg.get('quiet_after_minutes',QUIET_MINUTES);inactive=cfg.get('inactive_after_minutes',INACTIVE_MINUTES)
    last=saved.get('last_use');elapsed=max(0,now-last) if type(last) is int else None
    if not copies:status='survives_in_excerpts' if survivors else 'survives_in_later_editions' if later else 'no_current_copies'
    elif elapsed is None:status='unrecorded_use'
    elif elapsed>=inactive:status='out_of_use'
    elif elapsed>=quiet:status='rarely_used'
    else:status='in_circulation'
    return {**current,'circulation':status,'physical_copies':copies,'reads':saved.get('reads',0),
            'last_use':last,'surviving_excerpts':survivors[:32],'surviving_editions':later[:32]}


def make_excerpt(world,actor,source_item_id,*,new_item_id,title,claim_ids=None,max_chars=1600):
    """Prepare an attributed draft from this actor's actual remembered reading.

    This never registers an item, consumes materials, grants practice or mints a
    copy. The existing authorized commission/crafting action must supply real
    paper/ink and commit one physical output before any work reward is earned.
    """
    if not isinstance(new_item_id,str) or not new_item_id or len(new_item_id)>160 or new_item_id in world.items:
        raise ValueError('An excerpt needs a new item ID.')
    if not isinstance(title,str) or not title.strip() or len(title)>160:
        raise ValueError('An excerpt needs a short title.')
    if type(max_chars) is not int or not 40<=max_chars<=MAX_EXCERPT:
        raise ValueError('Choose an excerpt length from 40 to 4000 characters.')
    if world.entities.get(actor.id) is not actor or not actor.alive:raise ValueError('The author is unavailable.')
    records=[record for record in actor.progress.get(MEMORY,{}).values()
             if record.get('source',{}).get('id')==source_item_id]
    if not records:raise ValueError('The author has not actually read that source.')
    remembered=max(records,key=lambda record:record['read_minute']);origin=remembered['source']
    if claim_ids is not None:
        if not isinstance(claim_ids,list) or not claim_ids or any(not isinstance(value,str) for value in claim_ids):
            raise ValueError('Choose claim IDs actually present in the remembered source.')
        claims=[deepcopy(claim) for claim in origin['claims'] if claim['id'] in claim_ids]
        if {claim['id'] for claim in claims}!=set(claim_ids):raise ValueError('That claim was not in the remembered source.')
        body='\n\n'.join(claim['text'] for claim in claims)
        if len(body)>max_chars:raise ValueError('Selected claims exceed the excerpt length; choose fewer complete claims.')
    else:claims=[];body=remembered['excerpt']
    body=body[:max_chars].rstrip()
    now=_minute(world)
    lineage=[{'edition_id':origin['edition_id'],'relation':'quote',
              'evidence_roots':list(origin['evidence_roots']),'title':origin['title']}]
    lineage.extend(deepcopy(origin['derives_from'][:15]))
    return {'id':new_item_id,'name':title.strip(),'type':'book','readable':True,
            'read_text':body,'description':'An attributed excerpt from '+origin['title']+'.',
            'publication':{'work_id':'item:'+new_item_id,'edition_id':'edition:'+new_item_id,
                           'author':actor.name,'author_source':actor.source_def or actor.id,
                           'genre':'Collected excerpts','kind':'nonfiction','edition_minute':now,
                           'evidence_roots':list(origin['evidence_roots']),
                           'derives_from':lineage,'claims':claims}}


def validate(data):
    """Validate new lineage fields while retaining all existing provenance keys."""
    issues=[];editions={};rows=data.get('item',[])
    def text(value,limit=160):return isinstance(value,str) and bool(value.strip()) and len(value)<=limit
    def roots(values):return isinstance(values,list) and len(values)<=32 and all(text(value) for value in values)
    for item in rows:
        info=item.get('publication',{})
        if not isinstance(info,dict):issues.append(item['id']+': publication must be an object');continue
        if not info:continue
        label=item['id']+': '
        for key in ('work_id','edition_id'):
            if key in info and not text(info[key]):issues.append(label+key+' must be a short nonempty ID')
        if 'issued_minute' in info and (type(info['issued_minute']) is not int or abs(info['issued_minute'])>10**12):
            issues.append(label+'issued_minute must be a world-clock integer')
        if 'evidence_roots' in info and not roots(info['evidence_roots']):issues.append(label+'invalid evidence_roots')
        links=info.get('derives_from',[])
        if not isinstance(links,list) or len(links)>16:issues.append(label+'derives_from must list at most 16 sources');links=[]
        for link in links:
            if not isinstance(link,dict) or not text(link.get('edition_id')) or not isinstance(link.get('relation'),str) or link.get('relation') not in RELATIONS:
                issues.append(label+'invalid publication source link');continue
            if 'evidence_roots' in link and not roots(link['evidence_roots']):issues.append(label+'invalid linked evidence roots')
        claims=info.get('claims',[]);ids=set()
        if not isinstance(claims,list) or len(claims)>32:issues.append(label+'claims must list at most 32 qualified claims');claims=[]
        for claim in claims:
            if (not isinstance(claim,dict) or not text(claim.get('id'),96) or not text(claim.get('text'),2000)
                    or not isinstance(claim.get('certainty','sourced'),str) or claim.get('certainty','sourced') not in CERTAINTY):
                issues.append(label+'invalid qualified claim');continue
            if claim['id'] in ids:issues.append(label+'duplicate claim ID')
            ids.add(claim['id'])
            if 'evidence_root' in claim and not text(claim['evidence_root']):issues.append(label+'invalid claim evidence root')
            if 'qualification' in claim and not text(claim['qualification'],1000):issues.append(label+'invalid claim qualification')
            revisions=claim.get('revises',[])
            if not isinstance(revisions,list) or len(revisions)>8:issues.append(label+'invalid claim revision links');continue
            for previous in revisions:
                if not isinstance(previous,dict) or not text(previous.get('edition_id')) or not text(previous.get('claim_id'),96):
                    issues.append(label+'a claim revision needs an edition ID and claim ID')
        cfg=info.get('circulation',{})
        if not isinstance(cfg,dict) or set(cfg)-{'quiet_after_minutes','inactive_after_minutes'}:
            issues.append(label+'invalid circulation policy')
        else:
            quiet=cfg.get('quiet_after_minutes',QUIET_MINUTES);inactive=cfg.get('inactive_after_minutes',INACTIVE_MINUTES)
            if type(quiet) is not int or type(inactive) is not int or not 1<=quiet<inactive<=10**8:
                issues.append(label+'circulation intervals must increase and be positive')
        if all(text(info[key]) for key in ('work_id','edition_id') if key in info):
            _,edition=_identity(item)
            if edition in editions and (_text(editions[edition])!=_text(item) or editions[edition].get('publication',{}).get('claims',[])!=claims):
                issues.append(label+'an edition ID cannot identify conflicting texts or claims')
            editions[edition]=item
    if issues:return issues
    for item in rows:
        if _readable(item):editions.setdefault(_identity(item)[1],item)
    # Cycles would turn a quotation into its own alleged primary source.
    def visit(edition,trail):
        if edition in trail:return True
        if len(trail)>64:return True
        item=editions.get(edition,{})
        links=item.get('publication',{}).get('derives_from',[])
        return any(visit(link['edition_id'],trail|{edition}) for link in links
                   if isinstance(link,dict) and isinstance(link.get('edition_id'),str) and link['edition_id'] in editions)
    for edition,item in editions.items():
        if visit(edition,set()):issues.append(item['id']+': publication lineage contains a cycle or exceeds 64 editions')
    if issues:return issues
    from types import SimpleNamespace
    world=SimpleNamespace(items={item['id']:item for item in rows})
    for item in rows:
        info=item.get('publication',{}) or {};links=info.get('derives_from',[])
        for link in links:
            if link['edition_id'] not in editions and not link.get('evidence_roots'):
                issues.append(item['id']+': an unavailable source must retain its evidence roots')
        if links and all(link['relation'] in ('copy','quote') for link in links):
            inherited=set(source(world,item['id'])['evidence_roots'])
            authored=set(info.get('evidence_roots',[]))|{claim['evidence_root'] for claim in info.get('claims',[]) if claim.get('evidence_root')}
            if authored-inherited:issues.append(item['id']+': copies and quotes cannot add independent evidence roots')
    return issues
