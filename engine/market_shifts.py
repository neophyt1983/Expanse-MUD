"""Rotating staffed counters with one persisted, finite depot per market.

No crafting or stock creation happens here after the initial world endowment.
Restocking buys bounded quantities of actual regional workshop surplus.
"""
import math
from engine import living, livelihoods, society, frontiers

COMMANDS = {'market': 'Find reachable rotating markets and available goods',
            'marketbuy': 'Buy an item by exact ID or name at a staffed rotating market'}


def definitions(w):
    if not w.metadata.get('market_shifts'): return {}
    return {d['market_counter']['id']: d['market_counter'] for d in w.npcs.values()
            if isinstance(d.get('market_counter'), dict) and isinstance(d['market_counter'].get('id'), str) and d['market_counter']['id']}


def depot(w, cfg):
    stores = society.economy(w).setdefault('rotating_markets', {})
    if cfg['id'] not in stores:
        stores[cfg['id']] = {'stock': {i: min(100, max(0, int(q))) for i, q in cfg.get('initial_stock', {}).items() if i in w.items},
                             'gold': max(0, int(cfg.get('capital', 500))), 'next_restock': 0}
    return stores[cfg['id']]


def staff(w, cfg, customer=None):
    rid = cfg['room']
    if rid not in w.rooms or not livelihoods.room_open(w, rid): return []
    return [n for n in w.entities_in_room(rid)
            if not n.is_player and n.alive
            and w.npcs.get(n.source_def, {}).get('market_id') == cfg['id']
            and livelihoods.applies(w, n) and livelihoods.on_shift(w, n)
            and livelihoods.awake(w, n)
            and (customer is None or society.friendliness(w, customer, n) >= 50)]


def routine(w, n):
    """Dedicated counters do not abandon a shift to perform supply errands.

    Authored homes and work rooms still apply. Default quarters are at the
    counter's public building, so a boundary cannot strand incoming staff.
    """
    d = w.npcs.get(n.source_def, {})
    if not w.metadata.get('market_shifts') or not d.get('market_id'): return False
    if not livelihoods.on_shift(w, n):
        if livelihoods.roused(w, n) and not livelihoods.scheduled_awake(w, n):
            n.activity = 'awake after being disturbed'
            return True
        if livelihoods.scheduled_awake(w, n): self_care(w, n)
        target = n.progress.get('home_room') or d.get('home_room') or n.location
        livelihoods.move_towards(w, n, target)
        n.activity = ('returning home' if n.location != target else
                      'relaxing off duty' if livelihoods.scheduled_awake(w, n) else 'sleeping')
        return True
    target = livelihoods.workplace(w, n)
    livelihoods.move_towards(w, n, target)
    n.activity = 'working at the rotating market' if n.location == target else 'commuting to the rotating market'
    return True


def self_care(w, n):
    """One finite, paid local need purchase per 30 off-duty minutes."""
    from engine import needs_market
    if not needs_market.applies(w, n): return False
    now = living.state(w)['minute']
    if now < n.progress.get('market_self_care_at', -1): return False
    n.progress['market_self_care_at'] = now + 30
    for iid in list(dict.fromkeys(n.inventory)):
        if needs_market.use(w, n, iid): return True
    cfg = definitions(w).get(w.npcs.get(n.source_def, {}).get('market_id'))
    if not cfg or n.location != cfg['room'] or not staff(w, cfg, n): return False
    s = depot(w, cfg)
    candidates = [(price(w, cfg, iid), iid) for iid, qty in s['stock'].items()
                  if qty > 0 and iid in w.items and needs_market.wants(w, n, iid)]
    if not candidates: return False
    cost, iid = min(candidates)
    if n.gold < cost: return False
    n.gold -= cost; s['gold'] += cost; s['stock'][iid] -= 1; n.inventory.append(iid)
    from engine import task_skills
    clerks=staff(w,cfg,n)
    task_skills.transaction(w,n,next((c for c in clerks if c.id!=n.id),None))
    needs_market.use(w, n, iid)
    return True


def price(w, cfg, iid):
    # Premium is applied to the base value, with scarcity separately visible.
    from engine import needs_market
    s = depot(w, cfg)
    base = max(1, int(w.items[iid].get('value', 1)))
    quote = needs_market.quote(w, iid, s['stock'].get(iid, 0), cfg.get('target_stock', {}).get(iid, 4), base, cfg.get('group'))
    return max(base + 1, math.ceil(max(base, quote) * max(1.1, float(cfg.get('premium', 1.5)))))


def advance(w):
    now = living.state(w)['minute']
    for cfg in definitions(w).values():
        s = depot(w, cfg)
        if now < s['next_restock']: continue
        s['next_restock'] = now + max(30, int(cfg.get('restock_minutes', 60)))
        clerks = staff(w, cfg)
        if not clerks: continue
        needed = {iid: target for iid, target in cfg.get('target_stock', {}).items()
                  if iid in w.items and s['stock'].get(iid, 0) < min(100, target)}
        if not needed: continue
        budget = min(32, max(0, int(cfg.get('restock_batch', 8))))
        for rid, rd in w.room_details.items():
            if not budget: break
            if rid not in w.rooms or w.rooms[rid].group != cfg.get('group') or not rd.get('workshop'): continue
            if not livelihoods.room_open(w, rid): continue
            _, source = society.shop(w, rid)
            if not any(source['stock'].get(iid, 0) > 1 and s['gold'] >= max(1, int(w.items[iid].get('value', 1))) for iid in needed): continue
            workers = [n for n in w.entities_in_room(rid) if n.alive and not n.is_player
                       and w.npcs.get(n.source_def, {}).get('profession') == 'producer'
                       and livelihoods.on_shift(w, n) and livelihoods.awake(w, n)]
            if not workers: continue
            if frontiers.path(w, cfg['room'], rid, clerks[0]) is None: continue
            for iid, target in needed.items():
                if iid not in w.items: continue
                cost = max(1, int(w.items[iid].get('value', 1)))
                # Leave one item for the producer/local business. No minting,
                # catch-up batches, overnight transfers or negative inventories.
                qty = min(budget, max(0, min(100, target) - s['stock'].get(iid, 0)),
                          max(0, source['stock'].get(iid, 0) - 1), s['gold'] // cost)
                if qty:
                    source['stock'][iid] -= qty; s['stock'][iid] = s['stock'].get(iid, 0) + qty
                    s['gold'] -= cost * qty; source['gold'] += cost * qty; budget -= qty
                if not budget: break


def accessible(w, p, cfg):
    return cfg['room'] in w.rooms and frontiers.path(w, p.location, cfg['room'], p) is not None


def summary(w, p):
    lines = []
    for cfg in definitions(w).values():
        if cfg['room'] != p.location: continue
        names = ', '.join(n.name for n in staff(w, cfg, p))
        lines.append(cfg['name'] + ': ' + ('serving: ' + names if names else 'no available friendly staff') + '. Use the Markets list or marketbuy <item name>.')
    return '\n'.join(lines)


def menu(w, p, npc):
    """Local dialogue/trade surface, including off-duty clerk redirection."""
    cfg = definitions(w).get(w.npcs.get(npc.source_def, {}).get('market_id'))
    if not cfg: return 'This counter is not currently configured.'
    if society.friendliness(w, p, npc) < 50: return npc.name + ' refuses to trade. Use market for other reachable friendly suppliers.'
    lines = [cfg['name'], livelihoods.hours_text(w, npc)]
    if not livelihoods.awake(w, npc): lines.append(npc.name + ' is sleeping; check the on-duty counter staff below.')
    elif not livelihoods.on_shift(w, npc): lines.append(npc.name + ' is off duty; check the on-duty counter staff below.')
    lines.append(summary(w, p)); lines.append(_next_shift(w, cfg))
    s = depot(w, cfg)
    from engine import knowledge
    knowledge.teach(w,p,{'items':list(s['stock'])})
    for iid in sorted(s['stock']):
        if iid in w.items: lines.append(f'{w.items[iid]["name"]}: {s["stock"][iid]} left; {price(w,cfg,iid)} gold')
    lines.append('Shared finite stock. Convenience premium included. Use marketbuy <item name>; the Markets list shows known counters.')
    return '\n'.join(lines)


def _next_shift(w, cfg):
    now = living.state(w)['minute']
    entries = []
    for n in w.entities.values():
        if n.is_player or not n.alive or w.npcs.get(n.source_def, {}).get('market_id') != cfg['id']: continue
        start, duration = livelihoods.hours(w, n)
        if duration:
            entries.append(((start-now) % livelihoods.DAY, n.name, start))
    if not entries: return 'No surviving scheduled staff.'
    delay, name, start = min(entries)
    return f'Next scheduled handover: {name} at {start//60:02d}:{start%60:02d} (in {delay} minutes; arrival and access required).'


def command(ctx, args, name):
    w, p = ctx.world, ctx.player
    configs = definitions(w)
    if not configs: return 'No rotating markets are installed. Existing merchants and workshops still trade on their own schedules.'
    from engine import knowledge
    known_rooms=knowledge.ids(w,p,'rooms')
    local_configs=[cfg for cfg in configs.values() if cfg['room']==p.location and staff(w,cfg,p)]
    for cfg in local_configs:knowledge.teach(w,p,{'items':list(depot(w,cfg)['stock'])})
    known_items=knowledge.ids(w,p,'items')
    query = args.strip()
    if name == 'marketbuy':
        item = living.choose([w.items[i] for i in known_items], query)
        iid = item['id']
        local = [cfg for cfg in configs.values() if cfg['room'] == p.location and staff(w, cfg, p)]
        stocked = [cfg for cfg in local if depot(w, cfg)['stock'].get(iid, 0) > 0]
        if not stocked:
            raise ValueError('No staffed local counter has that item. Check known counters; exhausted supplies need gathering and timed production.')
        cfg = min(stocked, key=lambda c: price(w, c, iid)); s = depot(w, cfg); cost = price(w, cfg, iid)
        if p.gold < cost: raise ValueError(f'Not enough gold: this convenience purchase costs {cost} gold.')
        s['stock'][iid] -= 1; p.gold -= cost; s['gold'] += cost; p.inventory.append(iid)
        from engine import task_skills
        clerks=staff(w,cfg,p)
        task_skills.transaction(w,p,clerks[0] if clerks else None)
        return f'Purchased {item["name"]} for {cost} gold at {cfg["name"]}.'
    iid = living.choose([w.items[i] for i in known_items], query)['id'] if query else None
    lines = ['Rotating markets: finite goods, paid convenience; 25-hour day. Restocking requires paid, reachable, open staffed suppliers.']
    matches = []
    for cfg in configs.values():
        if cfg['room'] not in known_rooms:continue
        if cfg['room']!=p.location:
            lines.append(cfg['name']+' | '+w.rooms[cfg['room']].name+' | Known counter; travel there to inspect current stock, prices and staff.')
            continue
        if not accessible(w, p, cfg): continue
        members = [n for n in w.entities.values() if n.alive and w.npcs.get(n.source_def, {}).get('market_id') == cfg['id']]
        if not any(society.friendliness(w, p, n) >= 50 for n in members): continue
        s = depot(w, cfg)
        if iid and iid not in cfg.get('target_stock', {}) and iid not in s['stock']: continue
        crew = staff(w, cfg, p)
        matches.append((not bool(crew), cfg['room'] != p.location, cfg, s, crew))
    for _, _, cfg, s, crew in sorted(matches, key=lambda row: row[:2]):
        status = 'OPEN: ' + ', '.join(n.name for n in crew) if crew else 'UNAVAILABLE (off shift, absent, interrupted or building closed)'
        lines.append(f'{cfg["name"]} | {w.rooms[cfg["room"]].name} | {status}')
        lines.append(_next_shift(w, cfg))
        keys = [iid] if iid else sorted(s['stock'])
        for key in keys:
            if key not in w.items: continue
            lines.append(f'  {w.items[key]["name"]}: {s["stock"].get(key,0)} available; {price(w,cfg,key)} gold')
    if not matches: lines.append('No reachable friendly rotating supplier lists this item. Check ordinary merchants, provenance and recipes; route obstructions and faction standing can block access.')
    if iid and not any(crew and s['stock'].get(iid, 0) for _, _, cfg, s, crew in matches):
        lines.append('No available supply now. Stock is not created by waiting: gather inputs, supply producers, or check another reachable region after production.')
    lines.append('Select a known place on the map or use route <place name>, then marketbuy <item name>. Prices are checked again when buying.')
    return '\n'.join(lines)


def validate(data):
    issues = []; rooms = {r['id'] for r in data.get('room', [])}; items = {i['id'] for i in data.get('item', [])}; counters = {}
    for n in data.get('npc', []):
        cfg = n.get('market_counter')
        if cfg is None or cfg == {}: continue
        if not isinstance(cfg, dict) or not isinstance(cfg.get('id'), str) or not cfg['id']:
            issues.append(n['id'] + ': invalid market counter'); continue
        if cfg['id'] in counters: issues.append(n['id'] + ': duplicate market counter')
        counters[cfg['id']] = cfg
        if not isinstance(cfg.get('name'), str) or not cfg['name'].strip(): issues.append(n['id'] + ': invalid market name')
        if not isinstance(cfg.get('group'), str) or not cfg['group']: issues.append(n['id'] + ': invalid market group')
        if not isinstance(cfg.get('room'), str) or cfg['room'] not in rooms: issues.append(n['id'] + ': unknown market room')
        for field in ('initial_stock', 'target_stock'):
            rows = cfg.get(field, {})
            if not isinstance(rows, dict) or any(i not in items or type(q) is not int or not 0 <= q <= 100 for i, q in rows.items()): issues.append(n['id'] + ': invalid market ' + field)
        for field, low, high, default in [('capital',0,1000000,500),('restock_minutes',30,1500,60),('restock_batch',0,32,8)]:
            value = cfg.get(field,default)
            if type(value) is not int or not low <= value <= high: issues.append(n['id'] + ': invalid market ' + field)
        premium = cfg.get('premium',1.5)
        if type(premium) not in (int,float) or not 1.1 <= premium <= 10: issues.append(n['id'] + ': invalid market premium')
    for n in data.get('npc', []):
        if n.get('market_id') and (not isinstance(n['market_id'], str) or n['market_id'] not in counters): issues.append(n['id'] + ': unknown market_id')
    return issues
