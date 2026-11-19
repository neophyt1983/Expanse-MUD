#!/usr/bin/env python3
"""Post grocery directions and finite paid kitchen work in existing markets.

``apply(data, metadata)`` composes plural in-memory world catalogs. The CLI
always creates a separate staging copy; source worlds and running saves are
never restocked. Existing ingredients and workshop cash fund every batch.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

PATCH='market_employment_v1'
MARKET='fw_dawn_4'
FISH='fw_dawn_5'
EMPLOYER='fw_dawn_merchant_4'
WORKER='fw_dawn_citizen_18'
VACANCY='provision_kitchen_helper'
NOTICES=('work119_produce_notice','work119_fish_notice')


def apply(data,metadata):
    if metadata.get('content_patches',{}).get(PATCH):
        return {'patch':PATCH,'already_applied':True}
    by={kind:{row['id']:row for row in data.get(kind,[])} for kind in ('rooms','npcs','items','recipes')}
    for kind,ids in (('rooms',(MARKET,FISH)),('npcs',(EMPLOYER,WORKER,'fw_dawn_merchant_5')),
                     ('recipes',('lw_stew',)),('items',('lw_carrot','lw_onion','lw_potato','lw_stew'))):
        if any(ident not in by[kind] for ident in ids):
            raise ValueError('Market staging requires the reviewed existing '+kind+'.')
    market=by['rooms'][MARKET];shop=market.get('workshop') or {}
    boss=by['npcs'][EMPLOYER];worker=by['npcs'][WORKER];recipe=by['recipes']['lw_stew']
    if (not {'kitchen','market'}<=set(market.get('facilities',[]))
            or boss.get('spawn_room')!=MARKET or boss.get('work_room')!=MARKET
            or not any(row.get('owner')==EMPLOYER and row.get('contents') for row in market.get('locks',[]))):
        raise ValueError('The existing kitchen, market and explicitly owned provision store must still match.')
    if (worker.get('work_room')!=MARKET or worker.get('social_profile',{}).get('sentient') is not True
            or not any(row.get('room')==MARKET and row.get('activity')=='working' for row in worker.get('schedule',[]))):
        raise ValueError('The reviewed provision worker no longer has an actual work schedule here.')
    if worker.get('employment_plan'):
        raise ValueError('Preserve and review the worker’s existing employment plan before applying this patch.')
    if (recipe.get('station')!='kitchen' or recipe.get('minutes')!=5
            or recipe.get('ingredients')!={'lw_carrot':1,'lw_onion':1,'lw_potato':1}
            or recipe.get('outputs')!={'lw_stew':1}):
        raise ValueError('The actual five-minute vegetable stew recipe changed.')
    stock=shop.get('initial_stock',{})
    if shop.get('capital',0)<3 or any(stock.get(iid,0)<count for iid,count in recipe['ingredients'].items()):
        raise ValueError('This posting requires existing real ingredients and at least one funded wage.')
    if stock.get('lw_stew',0)>=12:
        raise ValueError('The reviewed stew demand is already filled; do not invent a new vacancy.')
    if any(ident in by['items'] for ident in NOTICES) or any(row.get('id')==VACANCY for row in market.get('employment',[])):
        raise ValueError('Market staging identities already exist without the patch marker.')

    # Finish every preflight before modifying the caller's catalogs.
    initial_shop=deepcopy(shop)
    offer=dict(id=VACANCY,title='Provision kitchen helper',employer=EMPLOYER,
               recipe='lw_stew',wage=3,slots=2,target_stock=12,min_skill=0)
    market.setdefault('employment',[]).append(offer)
    if 'lw_stew' not in shop.setdefault('recipes',[]):shop['recipes'].append('lw_stew')
    worker['employment_plan']=dict(enabled=True,room=MARKET,vacancy=VACANCY)

    descriptions={
        MARKET:'GROCERIES & PAID WORK: buy food at the Provision Counter or speak with '+boss['name']+'. A kitchen hiring notice is posted beside the counter.',
        FISH:'FISH & GROCERIES: buy from '+by['npcs']['fw_dawn_merchant_5']['name']+'. The produce market and its kitchen hiring notice are through the west exit.',
    }
    texts={
        MARKET:(
            'Groceries for sale\n'+boss['name']+' sells food here. The Provision Counter also sells its actual available stock. '
            'Use Buy in the market or Trade controls; workshop lists the counter and order <item name> buys from it. Prices and remaining quantities are shown before purchase.\n\n'
            'Hiring: Provision kitchen helper\n'
            'Two worker places are available to eligible adults. Make one batch of Vegetable Stew from the counter’s carrot, onion and potato. '
            'The wage is 3 gold for 5 game minutes of completed work, paid from the existing counter treasury. '
            'Apply here, then choose Work to reserve the ingredients and wage. Stay at this work site while the batch is prepared. '
            'Leaving, resting, injury or a stopped session returns the reserved supplies and wage. '
            'No wage is paid for applying alone. Work is offered only while the counter needs stew, has ingredients and can fund the wage. '
            'Use jobs, job apply '+VACANCY+', job work, job stop or job leave. '
            'The nearby fish market is through the east exit.'),
        FISH:(
            'Fish market\n'+by['npcs']['fw_dawn_merchant_5']['name']+' sells the fish and other goods actually stocked here. '
            'Choose Buy in Trade to pay for groceries. Availability and prices depend on the remaining real stock. '
            'For vegetables, prepared stew and the current kitchen hiring notice, follow the west exit to '+market['name']+'.'),
    }
    for room_id,ident in zip((MARKET,FISH),NOTICES):
        room=by['rooms'][room_id]
        room['description']=room.get('description','').rstrip()+'\n\n'+descriptions[room_id]
        item=dict(id=ident,name='Produce counter grocery and hiring notice' if room_id==MARKET else 'Fish market grocery sign',
            type='notice',anchored_readable=True,description='A fixed local notice beside the existing sales counter.',
            read_text=texts[room_id],knowledge={'rooms':[MARKET,FISH]},location=room_id,
            creation_method='A fixed market sign; it adds no sale stock or wages.')
        data['items'].append(item);room.setdefault('items',[]).append(ident)
    metadata.setdefault('content_patches',{})[PATCH]=1
    return dict(patch=PATCH,market=MARKET,employer=EMPLOYER,vacancy=VACANCY,
        wage=3,minutes=5,slots=2,target_stock=12,npc_plans=[WORKER],notices=list(NOTICES),
        new_rooms=[],new_npcs=[],stock_added={},gold_added=0,
        initial_treasury=initial_shop['capital'],initial_ingredients={iid:initial_shop['initial_stock'][iid] for iid in recipe['ingredients']},
        initial_stew=initial_shop['initial_stock'].get('lw_stew',0))


def stage(source,destination):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if destination==source or source in destination.parents or destination.exists():
        raise ValueError('Choose a new staging directory outside the input world.')
    data={kind:json.loads((source/(kind+'.json')).read_text(encoding='utf-8'))
          for kind in ('rooms','npcs','items','recipes')}
    metadata=json.loads((source/'metadata.json').read_text(encoding='utf-8'))
    report=apply(data,metadata)
    from engine import employment
    errors=employment.validate({kind: data[plural] for kind,plural in
        (('room','rooms'),('npc','npcs'),('item','items'),('recipe','recipes'))})
    if errors:raise ValueError('\n'.join(errors))
    shutil.copytree(source,destination)
    for kind in ('rooms','npcs','items'):
        (destination/(kind+'.json')).write_text(json.dumps(data[kind],ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    (destination/'metadata.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (destination/'market-employment-staging-report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    print(json.dumps(stage(args.input,args.output),indent=2))
