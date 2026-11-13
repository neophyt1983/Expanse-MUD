"""Explicit, shared, finite hand-sorting stockpiles; never industrial harvest."""
from engine.item_catalog import counted
import math

def configured(resource):
    return isinstance(resource,dict) and 'manual_batches' in resource

def valid(resource):
    return (type(resource.get('manual_batches')) is int and 1<=resource['manual_batches']<=10000
            and type(resource.get('gather_minutes')) is int and 1<=resource['gather_minutes']<=60
            and not any(k in resource for k in ('reserve_batches','visual','shared_renewal')))

def claim(world,room,resource,actor):
    from engine import living
    if not getattr(actor,'is_player',False):return 'This source is reserved for manual player collection, not automated industrial harvesting.'
    if not valid(resource):return 'This hand-gather source needs Creator validation.'
    if not actor.alive or actor.location!=room:return 'Collect this stockpile while alive and present here.'
    state=living.state(world);now=state['minute'];key=room+':'+resource['id']
    ledger=state.setdefault('manual_resources',{});seen=state.setdefault('manual_resource_seen',[])
    if not isinstance(ledger,dict) or not isinstance(seen,list):return 'This hand-gather source has invalid saved state; ask the Creator to recover it.'
    if key in seen and key not in ledger:return 'This previously initialized hand-gather source is missing saved stock; ask the Creator to recover it.'
    if key not in seen:seen.append(key)
    row=ledger.setdefault(key,{'remaining':resource['manual_batches'],'next_at':now})
    if (not isinstance(row,dict) or type(row.get('remaining')) is not int or row['remaining']<0
        or type(row.get('next_at')) not in (int,float) or not math.isfinite(row['next_at'])):
        return 'This hand-gather source has invalid saved state; ask the Creator to recover it.'
    # A later capacity edit cannot create replacement stock or erase depletion.
    row['remaining']=min(row['remaining'],resource['manual_batches'])
    if row['remaining']==0:return 'This hand-gather stockpile is exhausted; it does not regenerate.'
    if now<row['next_at']:return 'This shared hand-gather source needs more collection time before another batch.'
    row['remaining']-=1;row['next_at']=now+resource['gather_minutes']
    return ''

def validate(data):
    return [r['id']+': manual_batches requires 1–10000 finite batches and gather_minutes 1–60, without visual/reserve/shared renewal metadata'
            for r in data.get('resource',[]) if configured(r) and not valid(r)]


def describe(world,room,resource):
    from engine import living
    if not valid(resource):return 'Manual stockpile: invalid configuration.'
    state=living.state(world);ledger=state.get('manual_resources',{});seen=state.get('manual_resource_seen',[]);key=room+':'+resource['id']
    if not isinstance(ledger,dict) or not isinstance(seen,list) or key in seen and key not in ledger:return 'Manual stockpile: saved stock unavailable; recovery required.'
    row=ledger.get(key,{'remaining':resource['manual_batches'],'next_at':state['minute']})
    if not isinstance(row,dict) or type(row.get('remaining')) is not int or row['remaining']<0 or type(row.get('next_at')) not in (int,float) or not math.isfinite(row['next_at']):return 'Manual stockpile: invalid saved stock; recovery required.'
    remaining=min(row['remaining'],resource['manual_batches'])
    if not remaining:return 'Manual stockpile exhausted: 0 batches remain; no regeneration.'
    wait=max(0,row['next_at']-state['minute'])
    cadence=(f'shared collection cadence {resource["gather_minutes"]} game minutes; an available batch is delivered immediately'
             if getattr(world,'realtime',False) else f'collection takes {resource["gather_minutes"]} game minutes')
    return f'Manual stockpile: {counted(remaining,"batch","batches")} left; {cadence}; '+(f'next batch in {counted(math.ceil(wait),"minute")}.' if wait else 'ready to collect.')
