"""Local owner DM tools. Creator/player flags never grant this authority.

Only explicit fields leave the server. Raw commands, private chat, account
identifiers, authentication material and private appointments are not inspected.
"""
import asyncio
import copy
import hashlib
import json
import secrets
import sqlite3
import time
from collections import Counter, deque
from pathlib import Path
from server import dm_inventory

EDIT_LIMITS = {'hp': (0, 100000), 'max_hp': (1, 100000), 'attack': (0, 10000), 'defense': (0, 10000), 'gold': (0, 100000000)}
TEXT_LIMITS = {'first_name':80, 'last_name':80, 'description':2000}
ACTION_LABELS = {'go':'Travel request','look':'Looking around','inspect':'Inspecting','get':'Collecting items','drop':'Dropping items','attack':'Combat request','cast':'Casting','buy':'Trading','sell':'Trading','barter':'Trading','tradeitem':'Trading','offer':'Player trade','accept_offer':'Player trade','say':'Room chat','tell':'Private chat','chat':'World chat','faction':'Faction chat','camp':'Camping','rest':'Resting','sleep':'Sleeping','quest':'Quest action','accept':'Quest action','complete':'Quest action','save':'Saving','save_exit':'Saving and leaving','resume':'Connecting'}


def world_key(server):
    return Path(server.world.game_dir).name + ':' + server.mode


def ensure(server):
    if not hasattr(server,'_dm') or server._dm.get('world')!=world_key(server):
        server._dm={'world':world_key(server),'activity':deque(maxlen=200),'previews':{},'rates':{},'kicked':set()}
        server.db.execute('CREATE TABLE IF NOT EXISTS dm_bans (id TEXT PRIMARY KEY, world TEXT NOT NULL, scope TEXT NOT NULL, subject TEXT NOT NULL, label TEXT NOT NULL, reason TEXT NOT NULL, created REAL NOT NULL, expires REAL)')
        server.db.execute('CREATE UNIQUE INDEX IF NOT EXISTS dm_ban_subject ON dm_bans(world,scope,subject)')
        server.db.execute('CREATE TABLE IF NOT EXISTS dm_audit (id INTEGER PRIMARY KEY, world TEXT NOT NULL, time REAL NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL, label TEXT NOT NULL, reason TEXT NOT NULL, summary TEXT NOT NULL)')
    return server._dm


def owner(server,ws):
    if getattr(server,'mmo_authorizer',None):
        from server.shared_authority import can_moderate
        return can_moderate(server,ws)
    return ws in server.host_sockets


def account_for_player(server,pid):
    if getattr(server,'mmo_authorizer',None):
        return server.mmo_authorizer.ownership.owner(pid)
    accounts=getattr(server,'accounts',None)
    if not accounts:return None
    with accounts.lock:
        row=accounts.db.execute('SELECT account FROM ownership WHERE player=?',(pid,)).fetchone()
        return row[0] if row else None


def protects_owner(server,pid,account=None):
    policy=getattr(server,'mmo_authorizer',None)
    if policy:
        return bool(policy.owner and (account or account_for_player(server,pid))==policy.owner)
    return any(socket in server.host_sockets and (target==pid or (account and account_for_player(server,target)==account)) for socket,target in server.clients.items())


async def account_allowed(server,account):
    return not blocked(server,account=account)


def blocked(server,pid=None,account=None):
    ensure(server)
    subjects=[]
    if pid:subjects.append(('character',pid))
    if account:subjects.append(('account',account))
    now=time.time()
    return any(server.db.execute('SELECT 1 FROM dm_bans WHERE world=? AND scope=? AND subject=? AND (expires IS NULL OR expires>?)',(world_key(server),scope,subject,now)).fetchone() for scope,subject in subjects)


def record_activity(server,pid,command):
    if pid not in server.world.entities:return
    words=command.split(maxsplit=1)
    if not words:return
    verb=words[0].lower()
    expansion=server.world.shortcuts.get(verb,'')
    if expansion:verb=expansion.split()[0].lower()
    label=ACTION_LABELS.get(verb)
    if not label:return  # No raw arguments, unknown verbs, UI, credentials or calendar data.
    p=server.world.entities[pid]
    ensure(server)['activity'].append(dict(player=pid,name=p.name,action=label,room=server.world.rooms[p.location].name,time=time.time()))


def forget_socket(server,ws):
    state=getattr(server,'_dm',None)
    if not state:return
    state['rates'].pop(ws,None)
    state['kicked'].discard(ws)
    for key,value in list(state['previews'].items()):
        if value['socket'] is ws:state['previews'].pop(key,None)


def connected(server,pid):
    if not isinstance(pid,str) or pid not in server.clients.values():raise ValueError('That player is no longer connected. Refresh the roster.')
    p=server.world.entities.get(pid)
    if p is None or not p.is_player:raise ValueError('Player is unavailable.')
    return p


def revision(p):
    # Compare fields this console can affect, not private calendar/preferences
    # or unrelated hunger ticks. Ownership is separately revalidated.
    relevant=dict(fields=editable(p),location=p.location,inventory=p.inventory,equipped=p.equipped,permanently_dead=bool(p.progress.get('permanently_dead')))
    return hashlib.sha256(json.dumps(relevant,sort_keys=True,default=str).encode()).hexdigest()


def editable(p):
    return {k:copy.deepcopy(getattr(p,k)) for k in (*TEXT_LIMITS,*EDIT_LIMITS)}


def detail(server,p):
    def named(catalog,key):return catalog.get(key,{}).get('name','Unknown') if key else 'Unspecified'
    inventory=[dict(id=i,name=named(server.world.items,i),quantity=q,equipped=i in p.equipped.values()) for i,q in Counter(p.inventory).items()]
    return dict(id=p.id,name=p.name,location=server.world.rooms[p.location].name,location_id=p.location,
                fields=editable(p),race=named(server.world.races,p.race),character_class=named(server.world.classes,p.char_class),
                inventory=inventory,equipment=[dict(slot=k,name=named(server.world.items,v)) for k,v in p.equipped.items()],
                stats={k:v for k,v in p.stats.items() if k in ('str','agi','vit','int','wis','cha') and type(v) is int},alive=p.alive,ban_scope='account' if account_for_player(server,p.id) else 'character',
                is_host=any(ws in server.host_sockets for ws,pid in server.clients.items() if pid==p.id))


def roster(server):
    state=ensure(server);rows=[]
    for pid in dict.fromkeys(server.clients.values()):
        p=server.world.entities.get(pid)
        if p is None or not p.is_player:continue
        last=next((x for x in reversed(state['activity']) if x['player']==pid),None)
        rows.append(dict(id=pid,name=p.name,location=server.world.rooms[p.location].name,hp=p.hp,max_hp=p.max_hp,
                         action=last['action'] if last else 'No recent action recorded',time=last['time'] if last else None))
    return sorted(rows,key=lambda x:(x['name'].casefold(),x['id']))


def destinations(server,query):
    if not isinstance(query,str) or len(query)>100:raise ValueError('Search destinations by name (100 characters maximum).')
    query=query.strip().casefold()
    if not query:return []
    return [dict(id=r.id,name=r.name,floor=r.map_z) for r in sorted(server.world.rooms.values(),key=lambda r:(r.name.casefold(),r.id)) if query in r.name.casefold()][:60]


def audit(server,action,pid,label,reason,summary):
    server.db.execute('INSERT INTO dm_audit(world,time,action,target,label,reason,summary) VALUES(?,?,?,?,?,?,?)',(world_key(server),time.time(),action,pid,label,reason,json.dumps(summary,ensure_ascii=False)))
    server.db.execute('DELETE FROM dm_audit WHERE id NOT IN (SELECT id FROM dm_audit ORDER BY id DESC LIMIT 2000)')


def recent_audit(server):
    rows=server.db.execute('SELECT time,action,label,reason,summary FROM dm_audit WHERE world=? ORDER BY id DESC LIMIT 50',(world_key(server),)).fetchall()
    return [dict(time=t,action=a,name=n,reason=r,summary=json.loads(s)) for t,a,n,r,s in rows]


def ban_list(server):
    return [dict(id=i,name=n,scope=s,reason=r,expires=e) for i,n,s,r,e in server.db.execute('SELECT id,label,scope,reason,expires FROM dm_bans WHERE world=? AND (expires IS NULL OR expires>?) ORDER BY created DESC LIMIT 200',(world_key(server),time.time()))]


def text(value,limit,required=False):
    if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 and c not in '\n\t' for c in value):raise ValueError('Invalid text or text is too long.')
    value=value.strip()
    if required and not value:raise ValueError('A reason is required.')
    return value


def prepare(server,ws,payload):
    if not owner(server,ws):raise ValueError('Host authorization required.')
    state=ensure(server);action=payload.get('action');pid=payload.get('player')
    if action not in {'edit','teleport','kick','ban','unban','message'} | dm_inventory.ACTIONS:raise ValueError('Unknown DM action.')
    p=None;plan=dict(action=action,reason=text(payload.get('reason',''),240,action!='message'))
    summary=[]
    if action=='unban':
        ban=next((b for b in ban_list(server) if b['id']==payload.get('ban')),None)
        if not ban:raise ValueError('That block is no longer active.')
        plan.update(ban=ban['id'],label=ban['name']);summary=['Remove '+ban['scope']+' block for '+ban['name']+'.']
    elif action=='message' and pid=='all':
        plan.update(player='all',label='All connected players',text=text(payload.get('text',''),2000,True))
        summary=['Send to all '+str(len(set(server.clients.values())))+' connected players:',plan['text']]
    else:
        p=connected(server,pid);plan.update(player=p.id,label=p.name,revision=revision(p))
        if action in ('ban','kick') and protects_owner(server,pid,account_for_player(server,pid) if action=='ban' else None):raise ValueError('The local host cannot be kicked or banned.')
        if action in dm_inventory.ACTIONS:
            inventory_plan,summary=dm_inventory.prepare(server,p,action,payload)
            plan.update(inventory_plan)
        elif action=='edit':
            fields=payload.get('fields')
            if not isinstance(fields,dict) or not fields or set(fields)-set(TEXT_LIMITS)-set(EDIT_LIMITS):raise ValueError('Only the displayed character fields can be edited.')
            valid={}
            for key,value in fields.items():
                if key in EDIT_LIMITS:
                    low,high=EDIT_LIMITS[key]
                    if type(value) is not int or not low<=value<=high:raise ValueError(key+' is outside its allowed range.')
                    valid[key]=value
                else:valid[key]=text(value,TEXT_LIMITS[key],key=='first_name')
            if valid.get('hp',p.hp)>valid.get('max_hp',p.max_hp):raise ValueError('HP cannot exceed maximum HP.')
            if p.progress.get('permanently_dead') and valid.get('hp',p.hp)>0:raise ValueError('Permanent death cannot be undone by this editor.')
            plan['fields']=valid
            summary=[key.replace('_',' ')+': '+str(getattr(p,key) or '')+' → '+str(value) for key,value in valid.items() if getattr(p,key)!=value]
            if not summary:raise ValueError('No fields changed.')
        elif action=='teleport':
            room=server.world.rooms.get(payload.get('destination'))
            if room is None:raise ValueError('Choose an existing destination from the search results.')
            if not p.alive:raise ValueError('Use the game’s revival rules before teleporting this character.')
            if room.id==p.location:raise ValueError('The player is already there.')
            from engine import geology_impacts
            if geology_impacts.room_unusable(server.world,room.id):raise ValueError('That destination is currently unusable.')
            plan['destination']=room.id
            summary=['Teleport '+p.name+' from '+server.world.rooms[p.location].name+' to '+room.name+'.','This bypasses normal travel and records the destination as visited. Nearby hazards may still apply.']
        elif action=='kick':summary=['Save and disconnect '+p.name+'. They may reconnect.']
        elif action=='ban':
            account=account_for_player(server,p.id)
            plan.update(scope='account' if account else 'character',subject=account or p.id)
            hours=payload.get('hours',24)
            if type(hours) is not int or not 0<=hours<=8760:raise ValueError('Block duration must be 0 (until revoked) or 1–8760 hours.')
            plan['hours']=hours
            summary=['Block '+p.name+('’s account and all its characters from this world.' if account else '’s LAN character from this world. This does not identify a person and cannot prevent a new character.'),'Until revoked.' if hours==0 else 'Duration: '+str(hours)+' hours.']
        elif action=='message':
            plan['text']=text(payload.get('text',''),2000,True);summary=['Send to '+p.name+':',plan['text']]
    now=time.monotonic()
    state['previews']={k:v for k,v in state['previews'].items() if now-v['time']<60}
    if len(state['previews'])>=100:raise ValueError('Too many pending confirmations. Close an older preview or wait one minute.')
    token=secrets.token_urlsafe(24);state['previews'][token]=dict(socket=ws,time=now,plan=plan)
    return dict(token=token,summary=summary,reason=plan['reason'],expires_seconds=60)


async def commit(server,ws,token):
    if not owner(server,ws):raise ValueError('Host authorization required.')
    state=ensure(server)
    if not isinstance(token,str):raise ValueError('Missing confirmation.')
    preview=state['previews'].get(token)
    if not preview or preview['socket'] is not ws or time.monotonic()-preview['time']>60:raise ValueError('Confirmation expired. Preview the change again.')
    state['previews'].pop(token,None)
    plan=preview['plan'];action=plan['action'];p=None
    if plan.get('player') not in (None,'all'):
        p=connected(server,plan['player'])
        if revision(p)!=plan['revision']:raise ValueError('The player changed since preview. Refresh and review again.')
    if action in ('ban','kick') and protects_owner(server,p.id,account_for_player(server,p.id) if action=='ban' else None):raise ValueError('The local host cannot be kicked or banned.')
    dirty_before=set(getattr(server.world,'dirty_players',set()))
    snapshot=copy.deepcopy(vars(p)) if p else None
    old_rooms={rid:list(server.world.rooms[rid].entities) for rid in {p.location,plan.get('destination')} if rid in server.world.rooms} if p else {}
    sockets=[]
    server.db.commit()
    transaction_before=sqlite3.connect(':memory:')
    server.db.backup(transaction_before)
    try:
        if action in dm_inventory.ACTIONS:
            summary=dm_inventory.apply(server,p,plan)
        elif action=='edit':
            before=editable(p)
            for key,value in plan['fields'].items():setattr(p,key,value)
            p.name=((p.first_name or '')+' '+(p.last_name or '')).strip() or p.name
            summary=dict(before={k:before[k] for k in plan['fields']},after=plan['fields'])
        elif action=='teleport':
            room=server.world.rooms.get(plan['destination'])
            from engine import geology_impacts
            if room is None or geology_impacts.room_unusable(server.world,room.id):raise ValueError('Destination changed or became unusable; preview again.')
            origin=server.world.rooms[p.location].name
            server.world.move_entity(p.id,room.id,forced=True);server.mark_explored(p.id)
            summary=dict(before=origin,after=room.name)
        elif action=='ban':
            account=account_for_player(server,p.id)
            if plan['subject']!=(account or p.id):raise ValueError('Character ownership changed; preview again.')
            expires=time.time()+plan['hours']*3600 if plan['hours'] else None
            server.db.execute('INSERT OR REPLACE INTO dm_bans VALUES(?,?,?,?,?,?,?,?)',(secrets.token_hex(16),world_key(server),plan['scope'],plan['subject'],p.name,plan['reason'],time.time(),expires))
            sockets=[s for s,pid in list(server.clients.items()) if pid==p.id or (account and account_for_player(server,pid)==account)]
            summary=dict(scope=plan['scope'],expires=expires)
        elif action=='unban':
            row=server.db.execute('DELETE FROM dm_bans WHERE id=? AND world=?',(plan['ban'],world_key(server)))
            if not row.rowcount:raise ValueError('That block no longer exists.')
            summary=dict(result='Block removed')
        elif action=='kick':
            sockets=[s for s,pid in list(server.clients.items()) if pid==p.id];summary=dict(result='Session disconnect requested')
        elif action=='message':summary=dict(recipient=plan['label'],characters=len(plan['text']))
        audit(server,action,plan.get('player',''),plan['label'],plan['reason'],summary)
        server._stage_players_and_world()
        if action in ('ban','unban'):server._persist_moderation()
    except Exception:
        server.db.rollback()
        transaction_before.backup(server.db)
        if hasattr(server.world,'dirty_players'):server.world.dirty_players=dirty_before
        if p:
            vars(p).clear();vars(p).update(snapshot)
            for rid,entities in old_rooms.items():server.world.rooms[rid].entities[:]=entities
        raise
    finally:transaction_before.close()
    delivery=None
    if action=='message':
        targets=list(server.clients) if plan['player']=='all' else [s for s,pid in server.clients.items() if pid==plan['player']]
        delivery=dict(attempted=len(targets),sent=0,failed=0)
        for socket in targets:
            try:
                await socket.send(json.dumps(dict(type='system',text='DM: '+plan['text'])))
                delivery['sent']+=1
            except Exception:delivery['failed']+=1
    elif action in {'edit','teleport'} | dm_inventory.ACTIONS:
        try:
            await server.send_to(p.id,dict(type='system',text='The Dungeon Master '+('updated your inventory or equipment.' if action in dm_inventory.ACTIONS else 'updated your character.' if action=='edit' else 'teleported you from '+summary['before']+' to '+summary['after']+'.')))
            await server.update_maps()
        except Exception as exc:print('DM action committed; client refresh failed:',repr(exc))
    if action=='kick':state['kicked'].update(sockets)
    async def close_socket(socket):
        try:
            await asyncio.wait_for(socket.close(code=1008,reason='Removed by the Dungeon Master.' if action=='kick' else 'Blocked from this world by the Dungeon Master.'),timeout=3)
            return True
        except Exception:return False
    results=await asyncio.gather(*(close_socket(s) for s in sockets))
    result_text='DM action saved.'
    if results and not all(results):result_text='DM action saved; some disconnect notifications failed. Refresh the roster.'
    if delivery is not None:
        result_text=('DM message audit saved. Socket sends: '+str(delivery['sent'])+' succeeded, '
                     +str(delivery['failed'])+' failed, of '+str(delivery['attempted'])+' attempted. '
                     +'Successful sends are not read receipts; no automatic retries were made.')
        return dict(text=result_text,action=action,delivery=delivery)
    return dict(text=result_text,action=action)



async def handle(server,ws,payload,command):
    if command!='dm':return False
    if not owner(server,ws):
        await ws.send(json.dumps(dict(type='dm_error',text='Host authorization required.')));return True
    state=ensure(server);now=time.monotonic();rate=state['rates'].setdefault(ws,deque())
    while rate and now-rate[0]>60:rate.popleft()
    if len(rate)>=120:
        await ws.send(json.dumps(dict(type='dm_error',text='Too many DM requests; wait a moment.')));return True
    rate.append(now)
    rid=payload.get('request_id');rid=str(rid)[:80] if isinstance(rid,(str,int)) and not isinstance(rid,bool) else None
    try:
        if server.closing:raise ValueError('The server is shutting down.')
        operation=payload.get('operation')
        if operation=='roster':result=dict(players=roster(server),activity=list(state['activity'])[-50:])
        elif operation=='detail':result=dict(player=detail(server,connected(server,payload.get('player'))))
        elif operation=='items':result=dict(items=dm_inventory.catalog(server,connected(server,payload.get('player')),payload.get('query','')))
        elif operation=='destinations':result=dict(destinations=destinations(server,payload.get('query','')))
        elif operation=='audit':result=dict(audit=recent_audit(server),bans=ban_list(server))
        elif operation=='preview':result=dict(preview=prepare(server,ws,payload))
        elif operation=='commit':result=await commit(server,ws,payload.get('token'))
        elif operation=='cancel':
            token=payload.get('token');preview=state['previews'].get(token) if isinstance(token,str) else None
            if preview and preview['socket'] is ws:state['previews'].pop(token,None)
            result=dict(text='Preview cancelled.')
        else:raise ValueError('Unknown DM request.')
        await ws.send(json.dumps(dict(type='dm_result',operation=operation,request_id=rid,**result)))
    except Exception as exc:
        message=str(exc) if isinstance(exc,(ValueError,TypeError)) else 'DM action failed; changes were not committed. Check the server log and retry after refreshing.'
        if not isinstance(exc,(ValueError,TypeError)):print('DM action failed:',repr(exc))
        await ws.send(json.dumps(dict(type='dm_error',request_id=rid,text=message)))
    return True
