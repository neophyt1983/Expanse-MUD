"""Editable starter pixels use the selected template's current definitions."""
from pathlib import Path
import json
from types import SimpleNamespace
from engine.commands import _slot_for
from engine.visual_mapping import appearance_for, _player_equipment
from engine.costumes import npc_doll, subject, UNIFORMS
from engine.character_style import choices, PALETTES, COLORS, class_accents
from engine.pixel_art import RIGS

def catalogue_world(folder):
    def rows(name):
        p=Path(folder)/(name+'.json')
        return {r['id']:r for r in json.loads(p.read_text())} if p.exists() else {}
    return SimpleNamespace(items=rows('items'),races=rows('races'),classes=rows('classes'),npcs=rows('npcs'),species=rows('species'))

def starter(world,kind,iid,rig):
    if rig not in RIGS:raise ValueError('Choose an anatomy.')
    if kind not in ('items','npcs','races','classes'):raise ValueError('Select an item, race, class or NPC.')
    row=getattr(world,kind).get(iid)
    if not row:raise ValueError('The selected entry is unavailable.')
    result=dict(name=row.get('name',iid),kind=kind,rig=rig,palettes=PALETTES,colors=sorted(COLORS),uniforms=sorted(UNIFORMS))
    if kind=='items':
        slot=_slot_for(world,iid)
        if not slot:raise ValueError('This item has no equipped artwork.')
        result['gear']=_player_equipment(world,SimpleNamespace(equipped={slot:iid}))[0]
    if kind=='races':result.update(choices(row,{}))
    if kind=='classes':result['accents']=class_accents(row)
    if kind=='npcs':
        prof=row.get('social_profile') or {}
        ent=SimpleNamespace(id=iid,source_def=iid,race=row.get('race'),sex=row.get('sex'),char_class=row.get('char_class') or row.get('class'),description=row.get('description',''),progress={},equipped=row.get('equipped') or {},is_player=False)
        species=world.species.get(row.get('species') or prof.get('species'),{})
        nonhuman=subject(row,species.get('category') in ('mammal','bird','fish','insect','reptile','amphibian','animal'))
        look=appearance_for(world,ent,row,ent.race or '',ent.char_class or '',species,bool(nonhuman))
        actor=dict(id=iid,name=result['name'],kind='npc',appearance=look)
        if nonhuman:actor['subject']=nonhuman
        else:actor['paperdoll']=npc_doll(world,ent,row,look,_player_equipment(world,ent))
        result['actor']=actor
    return result

def request(folder,body):
    return starter(catalogue_world(folder),body.get('target_type'),body.get('target_id'),body.get('rig'))
