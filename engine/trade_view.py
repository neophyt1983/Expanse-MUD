"""Local trade quotes and price-checked transactions, never remote inventory search."""
from collections import Counter
from importlib.util import find_spec
from engine import barter, livelihoods, needs_market, society, market_shifts, social


def trader(w, p, ident):
    n = w.entities.get(ident)
    if not p.alive or n is None or n.is_player or not n.alive or n.location != p.location:
        raise ValueError('That trader is no longer available here.')
    return n


def _entry(w, n, iid):
    return next((r for r in w.npcs.get(n.source_def, {}).get('stock', []) if isinstance(r, dict) and r.get('item') == iid), None)


def _service(w, p, n):
    if society.enabled(w) and society.friendliness(w, p, n) < 50:
        return 'This trader is not friendly enough to offer shop service.'
    if not livelihoods.service_open(w, n):
        return n.name + ' is off duty. ' + livelihoods.hours_text(w, n)
    return ''


def shop_quote(w, p, n, iid, selling=False):
    """Same stock and scarcity prices as ordinary buy/shop buyback."""
    entry = _entry(w, n, iid)
    if entry is None or iid not in w.items:
        raise ValueError('This shop does not stock that item.')
    needs_market.ensure(w)
    initial = int(entry.get('qty', 1) or 0)
    cost = int(entry.get('price', 0) or 0)
    if needs_market.enabled(w):
        initial = max(1, initial)
        cost = needs_market.merchant_price(w, n.source_def, iid, cost)
    quantity = w.shop_state.get(n.source_def, {}).get(iid, initial) if initial > 0 else None
    reason = _service(w, p, n)
    if selling:
        cost = max(1, cost // 2)
        if not needs_market.enabled(w): reason = 'This world does not enable shop buyback.'
        if not reason and n.gold < cost: reason = 'The trader cannot afford this item right now.'
    else:
        if not reason and quantity is not None and quantity <= 0: reason = 'Sold out. Supplies need time and materials.'
        if not reason and p.gold < cost: reason = 'You do not have enough gold.'
    return dict(price=cost, quantity=quantity, reason=reason, channel='shop')


def _sell_quote(w, p, n, iid, context=None):
    if _entry(w, n, iid):
        row = shop_quote(w, p, n, iid, True)
        row['detail'] = 'Shop buyback'
    else:
        row = dict(price=None, reason='', channel='personal', detail='Personal needs and useful components')
        if not needs_market.enabled(w): row['reason'] = 'This world does not enable NPC item sales.'
        else:
            try: barter.eligible(w, p, n)
            except ValueError as exc: row['reason'] = str(exc)
        if not row['reason'] and not barter.interested(w, n, iid, context): row['reason'] = 'Not wanted by this trader right now.'
        if not row['reason']:
            row['price'] = max(1, barter.value(w, n, iid, context) // 2)
            if n.gold < row['price']: row['reason'] = 'The trader cannot afford this item right now.'
    if iid in p.equipped.values(): row['reason'] = 'Equipped. Unequip this item before selling or trading it.'
    return row


def available(w,p,n,commerce=None):
    """Whether Trade has a meaningful local purpose; never a social-mode flag."""
    if not p.alive or not n.alive or n.is_player or n.location!=p.location or _service(w,p,n):return False
    market_id = w.npcs.get(n.source_def, {}).get('market_id')
    cfg = market_shifts.definitions(w).get(market_id) if market_id else None
    if cfg:
        if not any(x.id==n.id for x in market_shifts.staff(w,cfg,p)):return False
        if any(q>0 and iid in w.items for iid,q in market_shifts.depot(w,cfg)['stock'].items()):return True
    else:
        entries=w.npcs.get(n.source_def,{}).get('stock',[])
        if any(not isinstance(row,dict) for row in entries):return False
        for entry in entries:
            iid=entry.get('item')
            if iid not in w.items:continue
            row=shop_quote(w,p,n,iid)
            if row['quantity'] is None or row['quantity']>0:return True
            if needs_market.enabled(w) and iid in p.inventory and iid not in p.equipped.values():return True
    if not needs_market.enabled(w):return False
    if commerce is not None:return bool(commerce.get('buying'))
    if not p.inventory:return False
    try:barter.eligible(w,p,n)
    except ValueError:return False
    context=barter.quote_context(w,n)
    return any(iid not in p.equipped.values() and barter.interested(w,n,iid,context) for iid in set(p.inventory))


def _barter_offers(w,p,n,context):
    try:barter.eligible(w,p,n)
    except ValueError:return []
    wanted=set(social.prefs(w,n)['wanted_items']);cfg=social.prefs(w,n,include_needs=False)
    demand=context['demand'] if context and context['applies'] else None
    def likes(iid):return iid in demand if demand is not None else iid not in cfg['disliked_items'] and (iid in wanted or w.items.get(iid,{}).get('type') in cfg['wanted_types'])
    return [dict(id=iid,name=w.items[iid]['name'],value=barter.value(w,n,iid,context)) for iid in dict.fromkeys(n.inventory) if iid in w.items and iid not in n.equipped.values() and not likes(iid)]


def view(w, p, ident):
    n = trader(w, p, ident)
    service=_service(w,p,n)
    if service:raise ValueError(service)
    result = dict(type='trade_view', trader=n.id, name=n.name, location=w.rooms[p.location].name,
                  room=p.location, gold=p.gold, buy=[], sell=[], barter=[], buy_empty='This NPC has no goods listed for sale for gold.', note='Prices are for one item. Each purchase or sale is checked again; stock and money are finite.')
    legacy_stock = any(not isinstance(row, dict) for row in w.npcs.get(n.source_def, {}).get('stock', []))
    if legacy_stock:
        result['note'] = 'This trader has legacy stock without explicit prices. Ask the Creator to validate its stock before trading; no goods or prices have been changed.'
        for iid, quantity in Counter(p.inventory).items():
            if iid in w.items: result['sell'].append(dict(id=iid, name=w.items[iid]['name'], price=None, quantity=quantity, reason='Trader stock needs Creator validation.', channel='shop', enabled=False))
        return result
    cfg = market_shifts.definitions(w).get(w.npcs.get(n.source_def, {}).get('market_id')) if w.metadata.get('market_shifts') else None
    if cfg:
        result['note'] = cfg['name'] + ': shared finite provisions, with a convenience premium. Other clerks cover overlapping shifts; supplies still require gathering and production.'
        available = any(x.id == n.id for x in market_shifts.staff(w, cfg, p))
        if available:
            s = market_shifts.depot(w, cfg)
            for iid, qty in s['stock'].items():
                if iid not in w.items: continue
                cost = market_shifts.price(w, cfg, iid)
                reason = 'Sold out. Supplies need time and materials.' if qty <= 0 else 'You do not have enough gold.' if p.gold < cost else ''
                result['buy'].append(dict(id=iid, name=w.items[iid]['name'], quantity=qty, price=cost, reason=reason, channel='counter'))
        else: result['note'] += ' This clerk is unavailable; speak to an on-duty friendly clerk at the counter.'
    elif not _service(w, p, n):
        for entry in w.npcs.get(n.source_def, {}).get('stock', []):
            iid = entry.get('item')
            if iid in w.items: result['buy'].append(dict(id=iid, name=w.items[iid]['name'], **shop_quote(w, p, n, iid)))
        if not result['buy']: result['note'] += ' This person has no gold shop; personal barter remains available through Talk.'
    else: result['note'] += ' ' + _service(w, p, n)
    context = barter.quote_context(w, n) if p.inventory or n.inventory else None
    if needs_market.enabled(w) and n.inventory:result['barter']=_barter_offers(w,p,n,context)
    if result['barter']:result['buy_empty']='No gold-sale stock. These possessions are barter-only; their values are not purchase prices.'
    for iid, quantity in Counter(p.inventory).items():
        if iid in w.items: result['sell'].append(dict(id=iid, name=w.items[iid]['name'], **{**_sell_quote(w, p, n, iid, context), 'quantity':quantity}))
    for key in ('buy', 'sell'):
        result[key].sort(key=lambda row: (row['name'].casefold(), row['id']))
        for row in result[key]: row['enabled'] = not bool(row['reason'])
    # The consolidation knowledge system is optional in older engine copies.
    if find_spec('engine.knowledge') is not None:
        from engine import knowledge
        knowledge.teach(w, p, {'items': [row['id'] for row in result['buy']]})
    return result


def shop_sale(w, p, n, iid):
    trader(w, p, n.id)
    if iid not in p.inventory: raise ValueError('Carry the item you want to sell.')
    if iid in p.equipped.values(): raise ValueError('Unequip it first.')
    quote = shop_quote(w, p, n, iid, True)
    if quote['reason']: raise ValueError(quote['reason'])
    cost = quote['price']
    n.gold -= cost; p.gold += cost; p.inventory.remove(iid)
    stock = w.shop_state[n.source_def]; stock[iid] = stock.get(iid, 0) + 1
    if getattr(w,'living_state',{}).get('resident_watches'):
        from engine import resident_watch
        resident_watch.note(w,[n.id],f"Bought {w.items[iid]['name']} for {cost} gold.")
    return 'Sold ' + w.items[iid]['name'] + ' to ' + n.name + ' for ' + str(cost) + ' gold.'


def command(ctx, args):
    """Exact-target UI transactions use the ordinary command/save/timing pipeline."""
    words = args.split()
    if len(words) != 5 or words[0] not in ('buy', 'sell'):
        raise ValueError('Open Trade and choose Buy or Sell.')
    action, ident, iid, channel, price = words
    try: expected = int(price)
    except ValueError: raise ValueError('Refresh the trade prices first.')
    n = trader(ctx.world, ctx.player, ident)
    packet = view(ctx.world, ctx.player, ident)
    row = next((r for r in packet[action] if r['id'] == iid and r['channel'] == channel), None)
    if row is None: raise ValueError('That offer is no longer available. Refresh Trade.')
    if row['reason']: raise ValueError(row['reason'])
    if row['price'] != expected: raise ValueError('The price changed. Refresh Trade before confirming the new price.')
    w, p = ctx.world, ctx.player
    if action == 'sell':
        return shop_sale(w, p, n, iid) if channel == 'shop' else barter.sale(w, p, n, iid)
    if channel == 'shop':
        from engine.commands import _cmd_buy
        return _cmd_buy(ctx, iid + ' from ' + ident)
    cfg = market_shifts.definitions(w)[w.npcs[n.source_def]['market_id']]
    # Exact selected counter, not a potentially cheaper/different nearby counter.
    s = market_shifts.depot(w, cfg)
    s['stock'][iid] -= 1; p.gold -= expected; s['gold'] += expected; p.inventory.append(iid)
    return 'Purchased ' + w.items[iid]['name'] + ' for ' + str(expected) + ' gold at ' + cfg['name'] + '.'


def register(reg):
    from engine.commands import Command
    reg.register(Command('tradeitem', 'Confirm a priced trade from the Trade window', 'tradeitem', command,
                         example='Use the Trade window to select a priced item.'))
