"""Player commands and public action summaries for live inventory theft."""
import shlex

from engine import burglary, living, relationships, sleep_movement, theft


def projection(world, player, online_players=()):
    online=set(online_players)
    now=int(living.state(world)['minute'])
    attempt=player.progress.get(burglary.ATTEMPT_KEY,{})
    ready=attempt.get('next_minute',0) if isinstance(attempt,dict) else 0
    remaining=max(0,ready-now) if type(ready) is int else 0
    reason=('You must be awake and able to act.' if not player.alive or sleep_movement.asleep(world,player)
            else 'You are restrained.' if player.progress.get('restrained_until',0)>now
            else 'Wait '+str(remaining)+' game minute(s) before another theft attempt.' if remaining else '')
    targets=[]
    for other in world.entities_in_room(player.location):
        if (other.id==player.id or not other.alive or other.location!=player.location
                or other.is_player and other.id not in online
                or not relationships.sentient(world,other)):
            continue
        # Identity is already visible in this room. Contents, equipment counts,
        # wealth and Observation levels never cross this projection boundary.
        targets.append(dict(id=other.id,name=other.name,kind='player' if other.is_player else 'npc'))
    return dict(level=burglary.skill(world,player),observation=burglary.skill(world,player,'observation'),
                cooldown_remaining=remaining,blocked=reason,targets=targets)


def command(ctx,args):
    from engine import npc_attention
    world,player=ctx.world,ctx.player
    if not args.strip():
        return ('Burgling '+str(burglary.skill(world,player))+'/100 · Observation '+
                str(burglary.skill(world,player,'observation'))+'/100. '
                'Use steal "<person here>" [maximum quantity]. This is theft. '
                'Success, quantity and detection are separate; the person loses exactly what you take.')
    try:parts=shlex.split(args)
    except ValueError as exc:raise ValueError('Close the quotes around the person’s name or ID.') from exc
    if not 1<=len(parts)<=2:
        raise ValueError('Use steal "<person here>" [maximum quantity].')
    try:quantity=int(parts[1]) if len(parts)==2 else 1
    except ValueError as exc:raise ValueError('Choose a positive whole maximum quantity.') from exc
    burglary._quantity(quantity)
    people=[other for other in world.entities_in_room(player.location)
            if other.id!=player.id and other.alive and other.location==player.location
            and relationships.sentient(world,other)]
    matches=[other for other in people if other.id==parts[0]]
    if not matches:matches=[other for other in people if other.name.casefold()==parts[0].casefold()]
    if len(matches)!=1:raise ValueError('Choose one different living person here by name or exact ID.')
    target=matches[0]
    result=theft.transfer(world,player,target.id,quantity=quantity,
                          online_players=getattr(world,'online_player_ids',()))
    if result.attempt.detected:
        npc_attention.begin(world,*result.attempt.detected)
    return result.message


def register(registry):
    from engine.commands import Command
    registry.register(Command('steal','Attempt theft from a person here',
                              'steal "<person here>" [maximum quantity]',command,
                              example='steal "Arden Lightbrook" 3'))
