#!/usr/bin/env python3
"""Reviewable animal metadata patch for an extracted authored world.

The input is always read-only. --apply-to names a separate staging directory;
only species/room fields whose prior values still match the patch are changed.
Bird numbers are explicit game tuning in permitted room edges, not measured
biological distances. Managed stock is bound only to a real local caretaker
already identified by the holding's feed-container ownership and work record.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import animal_life

FILES={'species':'species.json','npc':'npcs.json','room':'rooms.json'}
# Authored policy for these reviewed species IDs, not runtime name matching.
FLIGHT={
    'chicken':('short',2,1,20), 'turkey':('short',4,2,20),
    'quail':('short',3,2,15), 'duck':('sustained',40,8,20),
    'goose':('sustained',64,12,30), 'pigeon':('sustained',32,8,15),
    'raven':('sustained',24,6,20), 'owl':('sustained',12,4,20),
    'hawk':('sustained',24,6,20), 'heron':('sustained',32,8,20),
    'sparrow':('sustained',8,3,10), 'parrot':('sustained',12,4,15),
    'peregrine_falcon':('sustained',24,6,15), 'merlin_falcon':('sustained',16,4,15),
    'northern_goshawk':('sustained',16,4,20), 'golden_eagle':('sustained',40,8,20),
    'secretarybird':('sustained',24,6,20), 'sandhill_crane':('sustained',48,10,25),
    'scarlet_ibis':('sustained',24,6,20), 'roseate_spoonbill':('sustained',24,6,20),
    'avocet':('sustained',32,8,20), 'black_stork':('sustained',48,10,25),
    'magpie':('sustained',12,4,15), 'jackdaw':('sustained',16,4,15),
    'hoopoe':('sustained',16,4,20), 'kea':('sustained',12,4,20),
    'kookaburra':('sustained',6,2,20),
}


def load(directory):
    return {kind:json.loads((Path(directory)/name).read_text(encoding='utf-8'))
            for kind,name in FILES.items()}


def build_patch(data):
    changes=[];skipped=[]
    species={row['id']:row for row in data['species']}
    npcs={row['id']:row for row in data['npc']}
    def add(kind,row,path,value,basis,**extra):
        parent=row
        for key in path[:-1]:parent=parent[key]
        key=path[-1]
        changes.append(dict(kind=kind,id=row['id'],path=path,
                            before={'present':key in parent,'value':deepcopy(parent.get(key))},
                            value=value,basis=basis,**extra))
    for name,(mode,endurance,radius,recovery) in FLIGHT.items():
        row=species.get('species_'+name)
        if not row:continue
        if row.get('category')!='bird' or row.get('name','').casefold()!=name.replace('_',' '):
            skipped.append({'id':row['id'],'reason':'reviewed bird identity or category does not match'});continue
        if row.get('flight'):continue
        add('species',row,['flight'],dict(mode=mode,endurance_steps=endurance,
                                          range_steps=radius,recovery_minutes=recovery),
            'Reviewed bird species; explicit game balance in real outdoor route steps.')
    for room in data['room']:
        if 'husbandry' not in room.get('facilities',[]):continue
        keepers=set()
        for container in room.get('locks',[]):
            owner=npcs.get(container.get('owner'),{})
            if (owner.get('spawn_room')==room['id'] and owner.get('work_room')==room['id']
                    and owner.get('social_profile',{}).get('sentient') is True
                    and 'caretaker responsible for feeding' in owner.get('description','').lower()
                    and not container.get('direction') and container.get('contents')):
                keepers.add(owner['id'])
        if len(keepers)!=1:
            if room.get('spawners'):skipped.append({'id':room['id'],'reason':'no unique explicitly responsible local feed-store owner'})
            continue
        owner=npcs[next(iter(keepers))]
        for index,spawner in enumerate(room.get('spawners',[])):
            npc=npcs.get(spawner.get('npc'),{})
            profile=npc.get('social_profile',{})
            spec=species.get(npc.get('species') or profile.get('species'),{})
            if (spec.get('category') not in animal_life.ANIMALS
                    or profile.get('sentient',spec.get('sentient',False))
                    or profile.get('undead') or npc.get('creature_kind')=='monster'
                    or npc.get('livestock') or spawner.get('livestock')):continue
            # The actual holding is the only grounded enclosure room. Nearby
            # roads/homes are not quietly annexed to make a larger enclosure.
            escape=.02 if owner.get('title') in ('Farm Keeper','Ranch Keeper') and spec.get('category') in ('bird','mammal') else 0
            add('room',room,['spawners',index,'livestock'],
                dict(owner=owner['id'],home=room['id'],rooms=[room['id']],escape_chance=escape),
                'Existing husbandry spawner; feed-store owner is the actual caretaker working here.',
                spawner_npc=spawner['npc'])
        if room.get('climate',{}).get('sheltered') is True and not room.get('animal_shelter'):
            add('room',room,['animal_shelter'],True,'Existing holding climate explicitly marks this room sheltered.')
    return {'version':1,'policy':'animal-profiles-20261119','changes':changes,'skipped':skipped}


def apply_patch(data,patch):
    if patch.get('version')!=1:raise ValueError('Unsupported animal patch version.')
    result=deepcopy(data);indexes={kind:{row['id']:row for row in rows} for kind,rows in result.items()}
    for change in patch['changes']:
        row=indexes[change['kind']][change['id']];parent=row
        for key in change['path'][:-1]:parent=parent[key]
        key=change['path'][-1]
        if change.get('spawner_npc') and parent.get('npc')!=change['spawner_npc']:
            raise ValueError('The actual animal spawner changed: '+change['id'])
        if key in parent and parent[key]==change['value']:continue
        before=change['before']
        if (key in parent)!=before['present'] or parent.get(key)!=before['value']:
            raise ValueError('The authored animal field changed: '+change['id']+' '+str(change['path']))
        parent[key]=deepcopy(change['value'])
    errors=animal_life.validate(result)
    if errors:raise ValueError('\n'.join(errors))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--world',type=Path,required=True,help='Read-only extracted source world.')
    parser.add_argument('--patch-output',type=Path,required=True,help='Reviewable JSON patch and evidence.')
    parser.add_argument('--apply-to',type=Path,help='Separate existing staging world to patch.')
    args=parser.parse_args();source=args.world.resolve()
    patch=build_patch(load(source));validated=apply_patch(load(source),patch)
    if args.apply_to:
        target=args.apply_to.resolve()
        if target==source or any((target/name).resolve()==(source/name).resolve() for name in FILES.values()):
            parser.error('The original world is read-only. Choose a separate staging directory.')
        staged=load(target);updated=apply_patch(staged,patch)
        for kind,name in FILES.items():
            if staged[kind]==updated[kind]:continue
            destination=target/name;temporary=destination.with_name(destination.name+'.animal-patch-tmp')
            temporary.write_text(json.dumps(updated[kind],ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
            temporary.replace(destination)
    args.patch_output.parent.mkdir(parents=True,exist_ok=True)
    args.patch_output.write_text(json.dumps(patch,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'changes':len(patch['changes']),
                      'flight_profiles':sum(row['path']==['flight'] for row in patch['changes']),
                      'livestock_bindings':sum(row['path'][-1]=='livestock' for row in patch['changes']),
                      'shelters':sum(row['path']==['animal_shelter'] for row in patch['changes']),
                      'skipped':len(patch['skipped']),'validation_errors':animal_life.validate(validated),
                      'patch':str(args.patch_output),'applied_to':str(args.apply_to) if args.apply_to else None}))


if __name__=='__main__':main()
