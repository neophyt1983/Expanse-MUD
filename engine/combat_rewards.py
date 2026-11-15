"""Finite shared spoils and advancement for actual combat participants."""
from collections import Counter
from engine import living, progression, loot_tables

KEY = 'combat_contributions_v1'


def contribute(world, attacker, target, amount, credit=None):
    if amount <= 0 or target.progress.get('zoo_exhibit'):
        return
    beneficiary = credit or attacker
    if beneficiary.id == target.id:
        return
    now = living.state(world)['minute']
    ledger = target.progress.setdefault(KEY, {})
    row = ledger.setdefault(beneficiary.id, {'damage': 0, 'minute': now})
    row['damage'] += amount
    row['minute'] = now
    if attacker.id != beneficiary.id:
        companions = target.progress.setdefault('combat_assistants_v1', {})
        companion = companions.setdefault(attacker.id, {'damage': 0, 'minute': now})
        companion['damage'] += amount
        companion['minute'] = now
        if len(companions)>128:
            oldest=min(companions,key=lambda ident:(companions[ident]['minute'],ident))
            del companions[oldest]
    if len(ledger) > 128:
        oldest = min(ledger, key=lambda ident: (ledger[ident]['minute'], ident))
        del ledger[oldest]


def participants(world, dead, killer, credit=None):
    now = living.state(world)['minute']
    ledger = dead.progress.get(KEY, {})
    rows = []
    for ident, contribution in ledger.items():
        actor = world.entities.get(ident)
        if (actor and actor.alive and actor.location == dead.location
                and actor.id != dead.id and not actor.progress.get('zoo_exhibit')
                and contribution.get('damage', 0) > 0
                and 0 <= now-contribution.get('minute', now) <= 30):
            rows.append((actor, contribution['damage']))
    # Older ongoing fights have no ledger. The real finishing actor remains a
    # participant, including an owner's explicitly credited companion attack.
    beneficiary = credit or killer
    if (beneficiary and beneficiary.alive and beneficiary.location == dead.location
            and beneficiary.id != dead.id and not beneficiary.progress.get('zoo_exhibit')
            and not any(actor.id == beneficiary.id for actor, _ in rows)):
        rows.append((beneficiary, 1))
    return sorted(rows, key=lambda row: (-row[1], row[0].id))


def settle(world, dead, killer, credit=None, *, rng=None):
    if (dead.alive or dead.is_player or dead.progress.get('combat_rewards_settled_v1')
            or dead.progress.get('combat_drops_distributed') or dead.progress.get('zoo_exhibit')
            or world.npcs.get(dead.source_def, {}).get('zoo_exhibit')):
        return ''
    rows = participants(world, dead, killer, credit)
    if not rows:
        return ''
    definition = world.npcs.get(dead.source_def, {})
    coins = max(0, int(dead.gold))
    drops = [item for item in definition.get('drops', ()) if item in world.items]
    supplemental = loot_tables.roll(world, dead, rng=rng)
    if supplemental is not None:
        coins += supplemental['gold']
        drops.extend(supplemental['items'])
        dead.progress['combat_loot_v1'] = supplemental
    total = sum(damage for _, damage in rows)
    shares = [coins*damage//total for _, damage in rows]
    remainder_order = sorted(range(len(rows)), key=lambda i: (-(coins*rows[i][1] % total), i))
    for index in remainder_order[:coins-sum(shares)]:
        shares[index] += 1
    dead.gold = 0
    dead.progress['combat_rewards_settled_v1'] = True
    dead.progress['combat_drops_distributed'] = True
    goods = [[] for _ in rows]
    for index, item in enumerate(drops):
        goods[index % len(rows)].append(item)
    summaries = []
    for index, (actor, _) in enumerate(rows):
        living.on_kill(world, actor, dead, grant_drops=False)
        actor.gold += shares[index]
        actor.inventory.extend(goods[index])
        reward = []
        if shares[index]:
            reward.append(str(shares[index])+' gold')
        for item, count in Counter(goods[index]).items():
            reward.append(str(count)+' × '+world.items[item].get('name', item))
        advancement = progression.combat(world, actor, dead)
        message = actor.name+' receives '+(', '.join(reward) if reward else 'no physical spoils')+'.'
        if advancement:
            message += ' '+advancement
        summaries.append(message)
        if actor.is_player:
            world.dirty_players = getattr(world, 'dirty_players', set()) | {actor.id}
            if actor.id != getattr(credit or killer, 'id', None):
                world.rest_notifications = (getattr(world, 'rest_notifications', []) + [(actor.id, message)])[-500:]
    # A companion's physical spoils go to its explicitly credited caregiver,
    # but the animal that actually fought also learns from the encounter.
    credited={actor.id for actor,_ in rows}
    now=living.state(world)['minute']
    for ident,contribution in dead.progress.get('combat_assistants_v1',{}).items():
        actor=world.entities.get(ident)
        if (actor is None or ident in credited or not actor.alive or actor.location!=dead.location
                or actor.progress.get('zoo_exhibit') or contribution.get('damage',0)<=0
                or not 0<=now-contribution.get('minute',now)<=30):
            continue
        living.on_kill(world,actor,dead,grant_drops=False)
        advancement=progression.combat(world,actor,dead)
        if advancement:summaries.append(actor.name+' shares combat credit. '+advancement)
    return ' ' + ' '.join(summaries[:8]) + (f' {len(summaries)-8} other contributors also received their shares.' if len(summaries)>8 else '')
