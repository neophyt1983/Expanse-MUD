import asyncio,copy,hashlib,json,secrets,time,uuid
from collections import Counter
from engine import society

class SocietyServer:
    def init_society(self):
        self.host_sockets=set();self.creator_roles=set();self.offers={};self.host_token='';self.discarding=False;self.no_save_sockets=set()
    def valid_token(self,pid,token):
        if not isinstance(token,str) or not token:return False
        row=self.db.execute('SELECT progress FROM players WHERE id=? AND game_mode=?',(pid,self.mode)).fetchone()
        if not row:return False
        stored=json.loads(row[0] or '{}').get('delete_token_hash','')
        return secrets.compare_digest(stored,hashlib.sha256(token.encode()).hexdigest())
    def creator_auth(self,pid,token):
        if not isinstance(token,str) or pid not in self.creator_roles or pid not in self.clients.values():return False
        player=self.world.entities.get(pid)
        stored=player.progress.get('delete_token_hash','') if player else ''
        return bool(stored) and secrets.compare_digest(stored,hashlib.sha256(token.encode()).hexdigest())
    async def send_to(self,pid,payload):
        for ws,p in list(self.clients.items()):
            if p==pid:
                try:await ws.send(json.dumps(payload))
                except Exception:pass
    def person(self,query):
        choices=[self.world.entities[p] for p in set(self.clients.values()) if p in self.world.entities]
        match=[p for p in choices if p.id==query or p.name.lower()==query.lower()]
        if len(match)!=1:raise ValueError('Use an exact connected player ID or name. The host can list players.')
        return match[0]
    async def society_command(self,ws,packet,cmd,pid):
        words=cmd.split(maxsplit=1);verb=words[0].lower() if words else '';args=words[1] if len(words)>1 else ''
        if verb=='host_auth':
            remote=getattr(ws,'remote_address',None)
            import ipaddress
            local=remote and ipaddress.ip_address(remote[0]).is_loopback
            token=packet.get('control_token','')
            if local and self.host_token and isinstance(token,str) and secrets.compare_digest(token,self.host_token):
                self.host_sockets.add(ws);await ws.send(json.dumps({'type':'host_ready','text':'Host controls ready.'}))
            else:await ws.send(json.dumps({'type':'error','text':'Host authorization required.'}))
            return True
        if verb not in ('hostmap','players','promote','demote','announce','offer','accept_offer','decline_offer','chat','faction','tell','say','leave_no_save','quit'):return False
        async def reply(text,kind='response',**kw):await ws.send(json.dumps(dict(type=kind,text=text,**kw)))
        try:
            if verb in ('hostmap','players','promote','demote','announce'):
                if ws not in self.host_sockets:raise ValueError('Host authorization required.')
                if verb=='players':
                    return await reply('\n'.join(p.id+' | '+p.name+' | '+self.world.rooms[p.location].name+' | '+('creator' if p.id in self.creator_roles else 'player') for p in [self.world.entities[i] for i in set(self.clients.values()) if i in self.world.entities])) or True
                if verb=='hostmap':
                    from engine.mapping import render,room_records
                    records=room_records(self.world);center=args if args in self.world.rooms else next(iter(self.world.rooms))
                    players=[dict(id=p.id,name=p.name,location=p.location,location_name=self.world.rooms[p.location].name,marker=str(i%10)) for i,p in enumerate(self.world.entities.values()) if p.is_player and p.id in self.clients.values()]
                    data=render(records,center,players=players,designer=True)
                    await reply('Host map','host_map',map=data,players=players);return True
                if verb in ('promote','demote'):
                    target=self.person(args)
                    if verb=='promote':self.creator_roles.add(target.id)
                    else:self.creator_roles.discard(target.id)
                    await self.send_to(target.id,{'type':'permissions','text':'Creator access '+('granted' if verb=='promote' else 'revoked')+'.'})
                    await reply('Updated '+target.name+'.');return True
                for target in list(self.clients):
                    try:await target.send(json.dumps({'type':'system','text':'HOST: '+args[:2000]}))
                    except Exception:pass
                return True
            p=self.world.entities.get(pid)
            if p is None:raise ValueError('Create or load a character first.')
            if verb in ('leave_no_save','quit'):
                # A shared world cannot roll back only one participant.
                # Leaving does not commit or roll back the shared session.
                # Another player may explicitly save that session later.
                self.no_save_sockets.add(ws)
                await reply('Disconnected without an additional save.','saved_exit',discarded_exit=True)
                await ws.close();return True
            if verb in ('say','chat','faction','tell'):
                text=args;recipients=set(self.clients.values())
                if verb=='tell':
                    target_id,sep,text=args.partition(' ')
                    if not sep:raise ValueError('Use tell <player-id> <message>.')
                    target=self.person(target_id);recipients={target.id,p.id}
                for target_id in recipients:
                    target=self.world.entities.get(target_id)
                    if target is None:continue
                    if verb=='say' and target.location!=p.location:continue
                    if verb=='faction' and target.group_id!=p.group_id:continue
                    score=society.friendliness(self.world,p,target) if society.enabled(self.world) else 100
                    spoken=society.speech(text[:2000],score)
                    rendered=('You say: '+spoken if target.id==p.id else p.name+' says: "'+spoken+'"') if verb=='say' else f'[{verb}] {p.name}: '+spoken
                    await self.send_to(target.id,{'type':'response','text':rendered})
                return True
            if not society.enabled(self.world):raise ValueError('Enable civic rules in this world first.')
            if verb=='offer':
                parts=args.split()
                if len(parts) not in (4,6):raise ValueError('Use offer <player-id> <item-id> <quantity> <gold-price> [requested-item-id requested-quantity].')
                target=self.person(parts[0]);iid=parts[1];qty=int(parts[2]);gold=int(parts[3])
                requested=parts[4] if len(parts)==6 else '';requested_qty=int(parts[5]) if len(parts)==6 else 0
                if requested and (requested not in self.world.items or not 1<=requested_qty<=1000):raise ValueError('Invalid requested item or quantity.')
                if not p.alive or not target.alive:raise ValueError('Both traders must be alive.')
                if p.id==target.id or p.location!=target.location:raise ValueError('Meet the other player in the same room.')
                if society.friendliness(self.world,p,target)<=50:raise ValueError('Exchange needs the same faction or friendliness above 50%.')
                if not 1<=qty<=1000 or not 0<=gold<=1000000:raise ValueError('Invalid quantity or price.')
                if Counter(p.inventory)[iid]<qty or iid in p.equipped.values():raise ValueError('You need enough unequipped items.')
                oid=uuid.uuid4().hex[:12];self.offers[oid]=dict(sender=p.id,recipient=target.id,item=iid,quantity=qty,gold=gold,requested=requested,requested_qty=requested_qty,expires=time.monotonic()+120)
                await self.send_to(target.id,dict(type='trade_offer',id=oid,text=f'{p.name} offers {qty} {self.world.items[iid]["name"]} for {gold} gold'+(f' and {requested_qty} {self.world.items[requested]["name"]}' if requested else '')+'.'))
                await reply('Offer '+oid+' sent; expires in two minutes.');return True
            offer=self.offers.get(args)
            if not offer or offer['recipient']!=p.id:raise ValueError('No offer addressed to you with that ID.')
            if verb=='decline_offer':self.offers.pop(args,None);await reply('Offer declined.');return True
            sender=self.world.entities.get(offer['sender']);iid=offer['item'];qty=offer['quantity'];gold=offer['gold']
            if not sender or sender.id not in self.clients.values() or time.monotonic()>offer['expires']:raise ValueError('Offer expired or sender disconnected.')
            if not sender.alive or not p.alive:raise ValueError('Both traders must be alive.')
            if sender.location!=p.location or society.friendliness(self.world,sender,p)<=50:raise ValueError('Exchange conditions changed.')
            if Counter(sender.inventory)[iid]<qty or iid in sender.equipped.values() or p.gold<gold:raise ValueError('Items or payment no longer available.')
            requested=offer.get('requested','');requested_qty=offer.get('requested_qty',0)
            if requested and (Counter(p.inventory)[requested]<requested_qty or requested in p.equipped.values()):raise ValueError('Requested items are no longer available.')
            before=(list(sender.inventory),list(p.inventory),sender.gold,p.gold)
            try:
                for _ in range(qty):sender.inventory.remove(iid);p.inventory.append(iid)
                for _ in range(requested_qty):p.inventory.remove(requested);sender.inventory.append(requested)
                p.gold-=gold;sender.gold+=gold
                self._stage_players_and_world()
            except Exception as exc:
                self.db.rollback();sender.inventory,p.inventory,sender.gold,p.gold=before
                raise ValueError("Trade could not be saved; nothing was exchanged.") from exc
            self.offers.pop(args,None)
            await self.send_to(sender.id,{'type':'response','text':'Exchange completed.'});await reply('Exchange completed.');return True
        except (ValueError,KeyError,TypeError) as exc:await reply(str(exc),'error');return True
