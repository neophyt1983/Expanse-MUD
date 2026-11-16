"""Owned, mortal companions with persistent orders and species-based care."""
from dataclasses import asdict
from engine import living, relationships as rel, society

CARE = dict(treat_items=[], toy_items=[], cooldown_minutes=30)

def reserve(w):return living.state(w).setdefault('companion_reserve',{})

def owned(w,p,text):
    rows=[c for c in living.progress(p)['companions'] if text.lower() in (c['id'].lower(),c['name'].lower())]
    if len(rows)!=1:raise ValueError('Select one of your companions by exact name or ID.')
    record=rows[0];e=w.entities.get(record['id'])
    if e and (e.progress.get('zoo_exhibit') or w.npcs.get(e.source_def,{}).get('zoo_exhibit')):raise ValueError('Zoo exhibits remain in their protected habitat.')
    if e and e.progress.get('companion_owner')!=p.id:raise ValueError('You do not control that creature.')
    if e and not e.alive:raise ValueError('A dead companion cannot obey commands.')
    return record,e

def follow(w,e):
    owner=w.entities.get(e.progress.get('companion_owner'))
    if not owner or not owner.alive or e.progress.get('companion_order','follow')!='follow':return
    if not e.alive:return
    if owner.location!=e.location:
        from engine import frontiers
        steps=frontiers.path(w,e.location,owner.location,e)
        if steps:w.move_entity(e.id,steps[0][2])

def care(w,e):
    species=rel.profile(w,e)['species']
    return {**CARE,**getattr(w,'species',{}).get(species,{}).get('companion_care',{}),**w.npcs.get(e.source_def,{}).get('companion_care',{})}

def dismiss(w,p,record,e):
    if e is None:raise ValueError('That companion is already in the aether.')
    from engine import spell_life
    if spell_life.magical(e):
        # Storing a temporary body does not refresh its clock or move it through
        # a locked route. Recall checks its saved physical origin again.
        e.progress['companion_order']='dismissed'
        reserve(w)[e.id]=asdict(e)
        w.rooms[e.location].entities.remove(e.id);del w.entities[e.id]
        return e.name+' is dismissed; its original magical lifetime continues.'
    home=p.progress.get('home_room')
    e.progress['companion_order']='dismissed'
    from engine import geology_impacts
    if home in w.rooms and not geology_impacts.room_unusable(w,home):
        w.move_entity(e.id,home);return e.name+' returns home to '+w.rooms[home].name+'. Recall them when needed.'
    reserve(w)[e.id]=asdict(e)
    w.rooms[e.location].entities.remove(e.id);del w.entities[e.id]
    return e.name+' waits in the aether until recalled.'

def recall(w,p,record,e):
    from engine import spell_life
    now=getattr(w,'living_state',{}).get('minute',0)
    restriction=spell_life.control_restriction(w,p)
    if restriction:raise ValueError(restriction)
    saved=getattr(w,'living_state',{}).get('companion_reserve',{}).get(record['id'])
    magic=e.progress.get(spell_life.KEY) if e else saved.get('progress',{}).get(spell_life.KEY) if saved else None
    if magic:
        if magic['expires_minute']<=now:raise ValueError('That magical companion has expired.')
        from engine.core import Entity
        traveller=e or Entity(**saved)
        from engine import frontiers,regional_world
        route=frontiers.path(w,traveller.location,p.location,traveller)
        if regional_world.blocked(w,traveller,p.location) or route is None or any(frontiers.blocked(w,rid,di,traveller) for rid,di,_ in route):
            raise ValueError('No permitted route lets that magical companion return here.')
    from engine import companion_union
    if record not in companion_union.active(w,p):
        companion_union.check_space(w,p)
    from engine import mortality, geology_impacts
    if not p.alive or geology_impacts.room_unusable(w,p.location):raise ValueError('Recall requires a living caregiver in a safe location.')
    if (e is not None and not e.alive) or (e is None and saved is not None and saved.get('hp',0)<=0):raise ValueError('A deceased companion cannot be recalled.')
    if e is None and saved is None and record['id'] in mortality.state(w)['deaths']:raise ValueError('A deceased companion cannot be recalled.')
    if e is None:
        # Older worlds stored virtual companions by definition ID. Convert once.
        if not record.get('source_def') and record['id'] in w.npcs:
            from engine.core import Entity
            from uuid import uuid4
            source=record['id'];definition=w.npcs[source]
            ident='companion_'+uuid4().hex
            e=Entity(ident,record['name'],definition.get('hp',20),definition.get('hp',20),definition.get('attack',record.get('attack',1)),definition.get('defense',0),source_def=source,group_id=p.group_id)
            e.progress.update(companion_owner=p.id,companion_order='follow',companion_mode='defend')
            from engine import names
            names.migrate_saved(w,e)
            record.update(id=ident,source_def=source,name=e.name)
            w.add_entity(e,p.location)
            return e.name+' returns as a living companion.'
        saved=reserve(w).get(record['id'])
        if not saved or saved['progress'].get('companion_owner')!=p.id:raise ValueError('This companion is unavailable; no saved living companion was found.')
        if saved['hp']<=0:raise ValueError('A deceased companion cannot be recalled.')
        from engine.core import Entity
        e=Entity(**saved)
        from engine import names
        names.migrate_saved(w,e);record['name']=e.name
        w.add_entity(e,p.location);del reserve(w)[e.id]
    elif not w.move_entity(e.id,p.location):raise ValueError('That companion cannot enter this location.')
    e.progress.pop('union_boarded',None)
    e.progress['companion_order']='follow'
    return e.name+' returns and follows you.'

def fight(w,p,e,target,defending=False):
    from engine import commands as cmd, mortality
    if not p.alive or not e.alive or not target.alive or e.location!=p.location or target.location!=e.location:raise ValueError('The companion and target must be alive and here.')
    if e.progress.get('companion_order','follow')=='dismissed':raise ValueError('Recall the companion first.')
    if w.npcs.get(e.source_def,{}).get('handling',{}).get('temperament')=='peaceful':raise ValueError('This companion does not fight. Use its field skill instead.')
    if e.progress.get('companion_mode','defend')=='peaceful':raise ValueError('Set attack or defend mode first.')
    if target.id in (p.id,e.id) or target.progress.get('companion_owner')==p.id:raise ValueError('A companion will not attack its caregiver or fellow companions.')
    from engine import combat
    combat.validate(w,e,target,controller=p,check_controller_restraint=not defending)
    now=living.state(w)['minute']
    if now-e.progress.get('last_companion_attack',-100000)<1:raise ValueError('The companion is recovering from its last attack.')
    combat.ammunition(w,e)
    e.progress['last_companion_attack']=now
    return combat.strike(w,e,target,credit=p,lawful=defending)


def defend(w,p,attacker):
    for c in list(living.progress(p)['companions']):
        e=w.entities.get(c['id'])
        if not e or not e.alive or e.progress.get('companion_owner')!=p.id or e.location!=p.location or e.progress.get('companion_mode','defend')!='defend':continue
        try:text=fight(w,p,e,attacker,True)
        except ValueError:continue
        w.runtime_notifications=getattr(w,'runtime_notifications',[])+[(p.location,text)]

def command(ctx,args):
    w,p=ctx.world,ctx.player;action,_,rest=args.strip().partition(' ')
    if not action or action=='list':return '\n'.join(c['name']+' — '+c['order']+', '+c['mode']+'; '+c['location'] for c in view(w,p)) or 'No companions.'
    if action in ('treat','play','toy'):who,sep,item=rest.partition(' with ')
    elif action=='attack':who,sep,item=rest.partition(' at ')
    else:who=rest;sep='';item=''
    record,e=owned(w,p,who)
    if action=='recall':return recall(w,p,record,e)
    if e is None:raise ValueError('Recall the companion from the aether first.')
    if action=='dismiss':return dismiss(w,p,record,e)
    if e.location!=p.location or e.progress.get('companion_order')=='dismissed':raise ValueError('Recall the companion or meet it first.')
    if action in ('stay','follow'):
        e.progress['companion_order']=action;return e.name+' will '+action+'.'
    if action in ('peaceful','defend','attack'):
        if action!='peaceful' and w.npcs.get(e.source_def,{}).get('handling',{}).get('temperament')=='peaceful':raise ValueError('This companion works peacefully.')
        if action=='attack' and sep:
            from engine.social import target as npc_target
            matches=[x for x in w.entities_in_room(p.location) if item.lower() in (x.id.lower(),x.name.lower())]
            if len(matches)!=1:raise ValueError('Choose one nearby target by exact name or ID.')
            old=e.progress.get('companion_mode','defend');e.progress['companion_mode']='attack'
            try:return fight(w,p,e,matches[0])
            except ValueError:e.progress['companion_mode']=old;raise
        e.progress['companion_mode']=action
        return e.name+' is now '+action+('. Use attack <companion> at <target> to order a strike.' if action=='attack' else '.')
    if action in ('toy','treat','play'):
        from engine import npc_attention
        npc_attention.begin(w,p,e)
    if action=='toy':
        if not sep or item not in p.inventory or item not in care(w,e)['toy_items']:raise ValueError('Carry a suitable toy for this species first.')
        if item in p.equipped.values():raise ValueError('Unequip the toy first.')
        if item in e.inventory:raise ValueError('Your companion already has that toy.')
        p.inventory.remove(item);e.inventory.append(item)
        return e.name+' keeps the '+w.items[item]['name']+' for playtime.'
    if action in ('treat','play'):
        cfg=care(w,e);allowed=cfg['treat_items' if action=='treat' else 'toy_items']
        if not sep or (item not in p.inventory and not (action=='play' and item in e.inventory)) or item not in allowed:raise ValueError('Carry a suitable '+('treat' if action=='treat' else 'toy')+' for this species first.')
        if item in p.equipped.values():raise ValueError('Unequip the item first.')
        now=living.state(w)['minute'];key='last_care_'+action
        if now-e.progress.get(key,-1000000)<cfg['cooldown_minutes']:raise ValueError('Your companion needs a break before more '+action+'.')
        e.progress[key]=now
        if action=='treat':p.inventory.remove(item)
        e.progress['happiness']=min(100,e.progress.get('happiness',50)+5)
        rel.bond(w,p,e)['trust']=min(100,rel.bond(w,p,e)['trust']+2)
        return e.name+(' enjoys the treat.' if action=='treat' else ' plays with you and the '+w.items[item]['name']+'.')
    raise ValueError('Use companion attack, defend, peaceful, stay, follow, dismiss, recall, treat or play.')

def view(w,p):
    rows=[]
    for c in living.progress(p)['companions']:
        e=w.entities.get(c['id']);saved=reserve(w).get(c['id'],{})
        pr=e.progress if e else saved.get('progress',{})
        cfg=care(w,e) if e else CARE
        rows.append(dict(id=c['id'],name=c['name'],kind=c['kind'],order=pr.get('companion_order','follow' if e else 'unavailable'),mode=pr.get('companion_mode','defend'),location=w.rooms[e.location].name if e else ('Union stable' if saved and saved.get('progress',{}).get('union_boarded') else 'Aether') if saved else 'Unavailable',happiness=pr.get('happiness',50),held_toys=[dict(id=i,name=w.items[i]['name']) for i in (e.inventory if e else saved.get('inventory',[])) if i in w.items and i in cfg['toy_items']],treats=cfg['treat_items'],toys=cfg['toy_items']))
    return rows

def register(reg):
    from engine.commands import Command
    from engine import companion_union
    reg.register(Command('union','Companion training and stable services','union desk',companion_union.command,available=lambda ctx:companion_union.eligible(ctx.world,ctx.player),example='union desk'))
    reg.register(Command('companion','Give orders, treats and toys to your companions','companion <action>',command,available=lambda ctx:society.enabled(ctx.world),example='companion list'))

def validate(data):
    items={i['id'] for i in data.get('item',[])};issues=[]
    for obj in data.get('npc',[])+data.get('species',[]):
        cfg=obj.get('companion_care',{})
        if not isinstance(cfg,dict):issues.append(obj['id']+': invalid companion care');continue
        for field in ('treat_items','toy_items'):
            if not isinstance(cfg.get(field,[]),list) or any(i not in items for i in cfg.get(field,[])):issues.append(obj['id']+': invalid '+field)
        if type(cfg.get('cooldown_minutes',30)) is not int or cfg.get('cooldown_minutes',30)<1:issues.append(obj['id']+': invalid care cooldown')
    return issues
