"""Owned equipment projection and strict selectors for normal command dispatch.

Listing neither advances time nor cancels rest. This module never equips items:
resolved actions pass through the regular command and persistence lifecycle.
"""
from collections import Counter
import hashlib
import json
from engine.commands import _slot_for
from engine import item_catalog

SLOTS = {
    'body':'Underlayer', 'appearance_tunic':'Tunic / dress', 'armor':'Outer armor / coat',
    'appearance_cloak':'Cloak', 'head':'Head', 'appearance_hat':'Hat', 'hands':'Hands',
    'legs':'Legs', 'feet':'Feet', 'weapon':'Weapon', 'offhand':'Offhand', 'charm':'Charm',
}


def request_id(packet):
    value=packet.get('request_id')
    if not isinstance(value,str) or not 1<=len(value)<=100:
        raise ValueError('Equipment requests need a valid request identifier.')
    return value


def build(world, player, request=None):
    if player is None or not player.is_player:
        raise ValueError('Create or resume your character before managing equipment.')
    rows=[]
    for iid,count in Counter(player.inventory).items():
        if not isinstance(iid,str):continue
        item=world.items.get(iid)
        slot=_slot_for(world,iid)
        if not item or not isinstance(slot,str) or not slot:continue
        rows.append(dict(id=iid,name=str(item.get('name') or iid),count=count,slot=slot,
                         equipped=player.equipped.get(slot)==iid))
    rows.sort(key=lambda row:(row['name'].casefold(),row['id']))
    slot_ids=list(SLOTS)
    slot_ids+=sorted(({r['slot'] for r in rows}|set(player.equipped))-set(slot_ids))
    slots=[]
    for slot in slot_ids:
        iid=player.equipped.get(slot)
        item=world.items.get(iid,{})
        slots.append(dict(id=slot,label=SLOTS.get(slot,slot.replace('_',' ')),item_id=iid,
                          item_name=str(item.get('name') or iid) if iid is not None else None))
    # Private values stay private. Only hash identity/location and the very same
    # owned equipment projection; this is concurrency validation, not authority.
    fingerprint=[player.id,player.location,rows,slots]
    revision=hashlib.sha256(json.dumps(fingerprint,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return dict(type='equipment_state',request_id=request,actor_id=player.id,
                location=player.location,revision=revision,items=rows,slots=slots)


def resolve(world, player, packet):
    request_id(packet)
    state=build(world,player)
    if packet.get('actor_id')!=player.id:
        raise ValueError('Your active character changed. Refresh equipment before acting.')
    if packet.get('location')!=player.location:
        raise ValueError('You moved. Refresh equipment before acting.')
    if packet.get('revision')!=state['revision']:
        raise ValueError('Your equipment or inventory changed. Refresh and review the replacement again.')
    op=packet.get('op');iid=packet.get('item_id');slot=packet.get('slot')
    if op not in ('equip','unequip') or not isinstance(iid,str) or not isinstance(slot,str):
        raise ValueError('Choose an owned item and its equipment slot.')
    if 'expected_item' not in packet or packet['expected_item']!=player.equipped.get(slot):
        raise ValueError('That slot changed. Refresh and review the replacement again.')
    if not player.alive or player.progress.get('permanently_dead'):
        raise ValueError('You cannot change equipment while unconscious or dead.')
    if op=='equip':
        if iid not in player.inventory or iid not in world.items:
            raise ValueError('That item is no longer in your inventory.')
        if _slot_for(world,iid)!=slot:
            raise ValueError('That item does not fit the selected equipment slot.')
        if player.equipped.get(slot)==iid:
            raise ValueError('That item is already equipped there.')
    else:
        if player.equipped.get(slot)!=iid:
            raise ValueError('That item is no longer equipped in the selected slot.')
        # Existing unequip command resolves definitions, so never accidentally
        # fuzzy-match a corrupt/missing definition against another item.
        if iid not in world.items:
            raise ValueError('This item definition is unavailable. Ask the host to repair it.')
    selected=item_catalog.choose(item_catalog.item_rows(world,player.inventory if op=='equip' else player.equipped.values()),iid)
    if selected['id']!=iid:
        raise ValueError('This item identifier cannot be selected unambiguously. Ask the host to repair it.')
    return op+' '+iid
