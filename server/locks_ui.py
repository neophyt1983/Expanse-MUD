"""Translate scoped graphical lock actions; never trust a client command string."""
from engine import locks
import shlex


def resolve(world,actor,packet):
    if not actor or not actor.is_player:raise ValueError('Choose a player character first.')
    if packet.get('actor_id')!=actor.id:raise ValueError('The selected character changed. Refresh local actions.')
    if packet.get('room')!=actor.location:raise ValueError('You have moved. Refresh the local actions.')
    action=packet.get('action')
    if action in ('lesson','kit'):
        npc=locks.find_npc(world,actor,str(packet.get('npc','')))
        if action=='lesson' and packet.get('fee')!=world.npcs.get(npc.source_def,{}).get('lock_lesson_fee',2):raise ValueError('The lesson price changed. Refresh local actions.')
        return 'locks '+action+' '+npc.id
    if action not in ('inspect','pick','unlock','lock','open','take','take_item','put_item','reset','service'):raise ValueError('Unknown lock action.')
    origin,row=locks.select(world,actor,str(packet.get('target','')))
    expected=packet.get('locked')
    if type(expected) is not bool or expected!=locks.saved(world,origin,row)['locked']:raise ValueError('The lock has changed. Refresh the local actions.')
    target=origin+':'+row['id']
    if action in ('take_item','put_item'):
        iid=packet.get('item_id');quantity=packet.get('quantity')
        _,_,_,_,count=locks.transfer_selection(world,actor,target,iid,quantity,putting=action=='put_item',exact=True)
        expected_count=packet.get('expected_count')
        if type(expected_count) is not int or expected_count!=count:
            raise ValueError('The item quantity changed. Refresh local actions before transferring it.')
        return 'locks '+('put' if action=='put_item' else 'take-item')+' '+shlex.join([target,iid,str(quantity)])
    if action=='service':
        npc=locks.find_npc(world,actor,str(packet.get('npc','')))
        if packet.get('fee')!=world.npcs.get(npc.source_def,{}).get('locksmith_fee',0):raise ValueError('The service price changed. Refresh local actions.')
        return 'locks service '+npc.id+' for '+target
    return 'locks '+action+' '+target
