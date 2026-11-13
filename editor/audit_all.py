"""Audit every game; apply only explicit spelling and unambiguous exit repairs."""
import json
from pathlib import Path
from engine.directions import normalize_exits
from editor.cli import Editor

TEXT_FIXES={
'A harty smelling room where food is always read.':'A room filled with hearty cooking aromas, where food is always ready.',
'From all around everyone wonders what that smell is.':'Everyone nearby wonders what that smell is.',
'The dark home of death even under the high sun.':'A dark resting place for the dead, even beneath the midday sun.',
'The slacking skin of this risen hero reeks and the missing eyes bring further questions to life.':'The sagging skin of this risen hero reeks, and its empty eye sockets raise unsettling questions.',
'A large man that aparently eats well and is said to cook well.':'A large man who apparently eats well and is said to cook well.',
'A stout guard genial but dangerous.':'A stout guard, genial but dangerous.',
'The host for the graveyard hotel':'The host of the graveyard hotel.',
'Creates delecasies for the hotel patros':'Creates delicacies for the hotel patrons.',
'Good night deathling.':'Good night, deathling.',
"Come, eat, it's not going to kill you.":"Come, eat. It's not going to kill you.",
}

def clean_game(folder):
    """Return changed JSON files. Caller owns backup/application."""
    folder=Path(folder);changed={}
    for path in folder.glob('*.json'):
        data=json.loads(path.read_text());before=json.dumps(data,sort_keys=True)
        def visit(obj):
            if isinstance(obj,dict):
                for key,val in obj.items():
                    if key in ('description','dialogue','text') and isinstance(val,str) and val in TEXT_FIXES:obj[key]=TEXT_FIXES[val]
                    else:visit(val)
            elif isinstance(obj,list):
                for val in obj:visit(val)
        visit(data)
        if path.name=='rooms.json':
            for room in data:room['exits']=normalize_exits(room.get('exits',{}))
            # The supplied testground's reciprocal garden exits were swapped.
            byid={r['id']:r for r in data}
            if folder.name=='tutorial':
                descriptions={'emberhollow_square':'A stone well anchors the village square. The Gilded Tankard stands north, and a woodland trail leads east. Travelers pause here to prepare for their first adventure.', 'test_room':'A sheltered training clearing lies beneath the pines. Wooden practice posts line the grass, and the path south returns to the Whispering Woods.'}
                for rid,description in descriptions.items():
                    if rid in byid and byid[rid].get('description','').strip() in ('','...'):byid[rid]['description']=description
                training=byid.get('test_room',{})
                if training.get('name')=='Test Room':training['name']='Woodland Training Clearing'
                if training.get('exits')=={'north':'emberhollow_woods'} and byid.get('emberhollow_woods',{}).get('exits',{}).get('north')=='test_room':training['exits']={'south':'emberhollow_woods'}
            if folder.name=='testground' and all(x in byid for x in ('hall','armory','garden')):
                h,a,g=(byid[x]['exits'] for x in ('hall','armory','garden'))
                if h.get('east')=='garden' and a.get('north')=='garden' and g.get('south')=='hall' and g.get('west')=='armory':
                    g['south']='armory';g['west']='hall'
        if json.dumps(data,sort_keys=True)!=before:changed[path.name]=json.dumps(data,indent=2)+'\n'
    return changed

def audit_all(games):
    lines=[]
    for folder in sorted(Path(games).iterdir()):
        if not folder.is_dir():continue
        try:
            ed=Editor(folder);lines.append('\nGAME '+folder.name+'\n'+ed.validate())
            lines.extend(ed.validate_exits())
            for kind,objects in ed.data.items():
                ids=[o.get('id') for o in objects]
                if len(ids)!=len(set(ids)):lines.append(kind+': duplicate IDs')
                for obj in objects:
                    if kind=='room' and obj.get('description','').strip() in ('','...'):
                        lines.append('Unfinished room description: '+obj['id'])
            rooms={r['id']:r for r in ed.data['room']}
            meta=folder/'metadata.json';metadata=json.loads(meta.read_text()) if meta.exists() else {}
            start=metadata.get('start_room') or next((x for x in ('emberhollow_square','start') if x in rooms),next(iter(rooms),None))
            seen=set();todo=[start] if start else []
            while todo:
                rid=todo.pop()
                if rid in seen or rid not in rooms:continue
                seen.add(rid);todo.extend(rooms[rid].get('exits',{}).values())
            if set(rooms)-seen:lines.append('Unreachable from start (review intentional isolation): '+', '.join(sorted(set(rooms)-seen)))
            ability_ids={o['id'] for o in ed.data.get('ability',[])}
            item_ids={o['id'] for o in ed.data.get('item',[])}
            for kind in ('race','class'):
                for obj in ed.data.get(kind,[]):
                    for field,valid in [('starting_abilities',ability_ids),('starting_equipment',item_ids)]:
                        for ref in obj.get(field,[]):
                            if ref not in valid:lines.append(f'{kind} {obj["id"]}: missing {field} reference {ref}')
            if ed.data.get('quest') and not metadata.get('living_world'):lines.append('Quest progression is disabled for this world; enable living rules to use objectives.')
            if ability_ids and not metadata.get('living_world'):lines.append('Active abilities are disabled for this world; enable living rules and define ability effects.')
        except Exception as exc:lines.append(folder.name+': AUDIT ERROR: '+str(exc))
    return '\n'.join(lines)+'\n'

if __name__=='__main__':
    print(audit_all(Path(__file__).resolve().parent.parent/'games'))
