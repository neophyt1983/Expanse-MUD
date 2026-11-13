"""Bounded owner inventory adjustments, never arbitrary item or progress edits."""
import copy
import hashlib
import json
import time
from engine.commands import _slot_for, _cmd_equip, _cmd_unequip, CommandContext

ACTIONS={'grant_item','remove_item','equip_item','unequip_item'}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()


def item_state(player):
    return fingerprint({key:player.progress.get(key,{}) for key in ('enchants','durability')})


def basic_reason(player, iid, item):
    if any(item.get(key) for key in ('unique','instance','instance_id','unique_id','bound_to','owner','owner_id')):
        return 'Unique, bound or instance definitions cannot be created or destroyed here.'
    enchants=player.progress.get('enchants',{})
    durability=player.progress.get('durability',{})
    if not isinstance(enchants,dict) or not isinstance(durability,dict):
        return 'Item state needs repair before inventory adjustment.'
    if iid in enchants:return 'This character has an enchantment for this item type; quantity editing is restricted.'
    value=durability.get(iid,100)
    if type(value) not in (int,float) or value!=100:
        return 'This item type has non-pristine durability; quantity editing is restricted.'
    return ''


def trade_guard(server,player):
    for offer in server.offers.values():
        if player.id in (offer.get('sender'),offer.get('recipient')) and offer.get('expires',float('inf'))>time.monotonic():
            raise ValueError('Resolve or let the active player trade expire before changing inventory or equipment.')


def catalog(server,player,query):
    if not isinstance(query,str) or not 1<=len(query.strip())<=100:
        raise ValueError('Search by item name (1–100 characters).')
    needle=query.strip().casefold()
    rows=[]
    for iid,item in sorted(server.world.items.items(),key=lambda pair:(str(pair[1].get('name','')).casefold(),pair[0])):
        if needle not in str(item.get('name','')).casefold():continue
        rows.append(dict(id=iid,name=str(item.get('name',iid)),type=str(item.get('type','item')),
                         slot=_slot_for(server.world,iid),owned=player.inventory.count(iid),
                         restriction=basic_reason(player,iid,item)))
        if len(rows)==60:break
    return rows


def validate(server,player,action,iid,quantity):
    trade_guard(server,player)
    if not player.alive or player.progress.get('permanently_dead'):
        raise ValueError('Inventory editing requires a living character; use the normal revival rules first.')
    if not isinstance(iid,str) or iid not in server.world.items:
        raise ValueError('Choose a known catalog item, not a path or an unknown item instance.')
    item=server.world.items[iid]
    if type(quantity) is not int or not 1<=quantity<=100:
        raise ValueError('Quantity must be a whole number from 1 to 100.')
    if action in ('equip_item','unequip_item') and quantity!=1:
        raise ValueError('Equipment changes select one item type at a time.')
    if any(not isinstance(k,str) or v not in player.inventory for k,v in player.equipped.items()):
        raise ValueError('Existing equipment references missing inventory; repair that save before editing.')
    owned=player.inventory.count(iid);slot=_slot_for(server.world,iid)
    if action in ('grant_item','remove_item'):
        reason=basic_reason(player,iid,item)
        if reason:raise ValueError(reason)
    if action=='grant_item' and len(player.inventory)+quantity>10000:
        raise ValueError('This editor has a safety limit of 10,000 carried units; it is not a game weight rule.')
    if action!='grant_item' and not owned:raise ValueError('The player no longer owns this item.')
    if action=='remove_item':
        if owned<quantity:raise ValueError('Not enough owned units to remove.')
        if iid in player.equipped.values():raise ValueError('Unequip this item type before removing any of its units.')
    if action=='equip_item':
        if not isinstance(slot,str) or not slot or len(slot)>100:raise ValueError('This item has no valid equipment slot.')
        if player.equipped.get(slot)==iid:raise ValueError('This item is already equipped.')
        if iid in player.equipped.values():raise ValueError('This item is already equipped in another slot; unequip it first.')
    if action=='unequip_item' and iid not in player.equipped.values():raise ValueError('This item is not equipped.')
    return item,slot,owned


def prepare(server,player,action,payload):
    iid=payload.get('item');quantity=payload.get('quantity',1)
    item,slot,owned=validate(server,player,action,iid,quantity)
    plan=dict(item=iid,quantity=quantity,item_hash=fingerprint(item),item_state=item_state(player))
    label=str(item.get('name',iid))+' ['+iid+']'
    if action=='grant_item':summary=[f'CREATE {quantity} × {label} in {player.name}’s inventory. Owned: {owned} → {owned+quantity}. No stock or other player is charged.']
    elif action=='remove_item':summary=[f'DESTROY {quantity} × {label} from {player.name}’s inventory. Owned: {owned} → {owned-quantity}. No refund or dropped loot.']
    elif action=='equip_item':
        previous=player.equipped.get(slot)
        previous_name=server.world.items.get(previous,{}).get('name',previous or 'nothing')
        summary=[f'Equip {label} in {slot}, replacing {previous_name}. Both items remain in inventory.']
    else:summary=[f'Unequip {label}; it remains in inventory.']
    summary+=['Item type: '+str(item.get('type','item'))+'. Slot: '+str(slot or 'not equippable')+'.',
              'Enchantment and durability values are not edited. Collection quests may use current inventory; no quest history or completion is granted.']
    return plan,summary


def apply(server,player,plan):
    action=plan['action'];iid=plan['item'];quantity=plan['quantity']
    item,slot,owned=validate(server,player,action,iid,quantity)
    if fingerprint(item)!=plan['item_hash'] or item_state(player)!=plan['item_state']:
        raise ValueError('Item definition or enchantment/durability changed since preview. Review again.')
    before=dict(quantity=owned,equipment=copy.deepcopy(player.equipped))
    if action=='grant_item':player.inventory.extend([iid]*quantity)
    elif action=='remove_item':
        for _ in range(quantity):player.inventory.remove(iid)
    elif action in ('equip_item','unequip_item'):
        context=CommandContext(server.world,player,server.world.rooms[player.location])
        (_cmd_equip if action=='equip_item' else _cmd_unequip)(context,iid)
    return dict(item=iid,name=str(item.get('name',iid)),before=before,
                after=dict(quantity=player.inventory.count(iid),equipment=copy.deepcopy(player.equipped)))
