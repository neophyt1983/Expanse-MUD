"""Resolve public local guild choices against the authenticated actor."""
import shlex
from engine import sleep_movement


def resolve(world, actor, packet):
    from engine import guilds
    if not isinstance(packet, dict):
        raise ValueError('Choose a current local guild action.')
    if (actor is None or not actor.is_player or world.entities.get(actor.id) is not actor
            or not actor.alive or sleep_movement.asleep(world,actor)):
        raise ValueError('Choose a living, awake player character first.')
    if packet.get('actor_id') != actor.id:
        raise ValueError('The selected character changed. Refresh guild services.')
    if packet.get('room') != actor.location or actor.location not in world.rooms:
        raise ValueError('You have moved. Visit the local guild service again.')
    if packet.get('command') != 'guild action' or packet.get('guild_ui') is not True:
        raise ValueError('Unknown guild action.')
    request = packet.get('request_id')
    if not isinstance(request,str) or not request.strip() or len(request)>100:
        raise ValueError('Refresh guild services to create a valid request.')
    if set(packet)-{'command','guild_ui','action','sequence','request_id','actor_id','room','guild_id','offer_id','revision'}:
        raise ValueError('Choose a guild offer; its skills, needs and rewards are decided by the host.')
    action=packet.get('action')
    if action not in ('join','learn','accept','complete'):
        raise ValueError('Choose Join, Learn, Accept quest or Contribute / complete.')
    guild=next((g for g in guilds.projection(world,actor)['guilds'] if g['id']==packet.get('guild_id')),None)
    if guild is None:
        raise ValueError('That guild service is not available here.')
    if action=='join':
        if 'offer_id' in packet or packet.get('revision') is not None:
            raise ValueError('Choose the current guild membership offer.')
        offer=guild['join'];permit=offer
    else:
        collection=guild['lessons'] if action=='learn' else guild['quests']
        offer=next((row for row in collection if row['id']==packet.get('offer_id')),None)
        if offer is None:
            raise ValueError('That offer is no longer available here. Read or ask about current guild work.')
        permit=offer if action=='learn' else offer[action]
    revision=offer.get('revision')
    supplied=packet.get('revision')
    if revision is not None:
        if type(supplied) is not int or not 0<=supplied<2**48 or supplied!=revision:
            raise ValueError('This need changed. Read the updated guild offer before contributing.')
    elif supplied is not None:
        raise ValueError('Refresh this guild offer before choosing again.')
    if not permit.get('enabled'):
        raise ValueError(permit.get('reason') or 'That guild action is not currently available.')
    words=['guild',action,guild['id']]
    if action!='join':words.append(offer['id'])
    if revision is not None:words.append(str(revision))
    return shlex.join(words)
