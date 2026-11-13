"""Local NPC dress. Work garments are purely visual, actual equipped items take precedence."""
from engine.character_style import choices,selected_accent,variant,HAIR

# kind, shape, material, work accessory. All roles can be portrayed with any cut.
UNIFORMS = {
 'guard':('armor','gambeson','wool','helmet'), 'teacher':('robe','cassock','linen',''),
 'hunter':('coat','jerkin','hide','bow'), 'farmer':('tunic','work_shirt','linen','hat'),
 'performer':('coat','doublet','velvet','lute'), 'merchant':('coat','waistcoat','wool',''),
 'driver':('coat','greatcoat','leather','hat'), 'producer':('tunic','apron','leather',''),
 'chef':('tunic','apron','linen','hat'), 'royalty':('robe','long_robe','velvet','crown'),
 'pupil':('tunic','longshirt','linen',''), 'healer':('coat','wrap_robe','linen',''),
 'mariner':('coat','jerkin','canvas','hat'), 'resident':('tunic','longshirt','woven',''),
}
def occupation(row):
    explicit=(row.get('portrait') or {}).get('uniform')
    if explicit in UNIFORMS:return explicit
    ident=row.get('id','').lower()
    if 'ruler' in ident:return 'royalty'
    if 'pupil' in ident:return 'pupil'
    job=str(row.get('role') or row.get('occupation') or row.get('profession') or '').lower()
    if job in UNIFORMS:return job
    if 'clerk' in job or 'trader' in job:return 'merchant'
    if job=='entertainer':return 'performer'
    if 'warden' in ident or 'guard' in ident or 'risen' in ident:return 'guard'
    return 'resident'

def subject(row, default_creature=False):
    """Nonhuman bodies are drawn separately, including nonliving encounter sources."""
    profile=row.get('social_profile') or {}
    species=row.get('species') or profile.get('species') or ''
    ident=row.get('id','')
    if ident.endswith('_carriage'):return 'carriage'
    if ident.startswith('lw_') and ident.endswith('_source'):return ident[len('lw_'):-len('_source')]
    if 'familiar' in ident and not species:return 'familiar'
    if not species and ident.endswith('_mob'):return ident[3:-4]
    if default_creature or profile.get('sentient') is False or row.get('sentient') is False:
        return row.get('companion_art') or species.removeprefix('species_') or 'creature'
    return ''

def npc_doll(world, ent, row, appear, equipment):
    profile=row.get('social_profile') or {}
    info=row.get('portrait') or {}
    identity=ent.id if ent.progress.get('population',{}).get('born_resident') else ent.source_def or ent.id
    race=ent.race or row.get('race') or profile.get('species') or ('zombie' if 'risen' in identity or 'zombie' in identity else 'human')
    cls=ent.char_class or row.get('char_class') or row.get('class') or ''
    opts=choices(world.races.get(race,{'id':race}),world.classes.get(cls,{'id':cls}))
    features={k:v[variant(identity,k)%len(v)] for k,v in opts['traits'].items()}
    natural=[c for c in opts['traits']['hair_color'] if c in HAIR]
    if natural:features['hair_color']=natural[variant(identity,'hair')%len(natural)]
    from engine import life_stages, worldtime
    social = {**profile, **ent.progress.get('social_profile', {})}
    # Studio previews and live rooms share age thresholds and drawing code.
    if 'age_years' not in social: social['age_years'] = 25
    social.setdefault('sentient', True)
    now = (getattr(world, 'living_state', {}) or {}).get('minute', worldtime.initial_minute(getattr(world, 'metadata', {})))
    stage = life_stages.classify(social, getattr(world, 'species', {}).get(social.get('species', race)), now)
    life = stage['stage']
    if life == 'child':
        life = 'school' if stage['in_school'] else 'preschool'
    if life == 'elder' and 'gray' in natural: features['hair_color']='gray' 
    population=(row.get('population_profile') or {}).get('appearance') or {}
    described={'dark':'black','fair':'blond','silver':'gray'}.get(population.get('hair'),population.get('hair'))
    if described in opts['traits']['hair_color']:features['hair_color']=described
    if population.get('hair')=='shaved':features['hair_style']='bald'
    # Authored sex/presentation controls the garment cut only where supplied.
    presentation=info.get('cut') or row.get('gender') or getattr(ent,'sex',None) or row.get('sex') or 'neutral'
    features.update({k:v for k,v in (row.get('appearance') or {}).items() if k in opts['traits'] and v in opts['traits'][k]})
    if not stage['adult']:
        features.update(stature='short',facial_hair='none')
    if 'hair_color' in appear:features['hair_color']=appear['hair_color']
    job=ent.progress.get('population',{}).get('vocation',{}) if life in ('adult','elder') else {}
    role='pupil' if life in ('infant','preschool','school','adolescent') else occupation({**row,**job})
    kind,shape,material,accessory=UNIFORMS[role]
    authored_cloth=appear.get('clothing')
    if authored_cloth and appear.get('sources',{}).get('clothing')=='configuration':
        kind=shape=authored_cloth
    dye=appear.get('clothing_color') or info.get('color') or ('blue','green','brown','gray','red','purple')[variant(row.get('group',''),'livery')%6]
    taken={g['layer'] for g in equipment}
    outfit=[]
    if 'legs' not in taken:
        outfit.append(dict(layer='legs',slot='legs',kind='leggings',shape='trousers',material='wool',color='gray'))
    if 'body' not in taken:
        outfit.append(dict(layer='body',slot='body',kind=kind,shape=shape,material=material,color=dye,
                        pattern={'female':'embroidered','male':'edged','feminine':'embroidered','masculine':'edged'}.get(str(presentation).lower(),'stitched')))
    if 'feet' not in taken:
        outfit.append(dict(layer='feet',slot='feet',kind='boots',material='leather',color='brown'))
    for token in dict.fromkeys([accessory,*appear.get('accessories',[])]):
        layer='head' if token in {'helmet','hat','crown','hood'} else 'offhand' if token=='shield' else 'cloak' if token=='cloak' else 'weapon'
        if token and layer not in taken:
            outfit.append(dict(layer=layer,slot=layer,kind=token,material='iron' if token in {'helmet','shield','sword'} else 'wood' if layer=='weapon' else 'cloth',color='gold' if token=='crown' else dye))
            taken.add(layer)
    return dict(version=1,characteristics=features,equipment=outfit+equipment,
                family=opts['family'],accent=selected_accent({'accent':(opts['accents'] or [{}])[0].get('name')},opts) if cls else None,
                life_stage=life, occupation=role, workwear='body' not in taken, cut=str(presentation))

def distant_portrait(actor):
    """Only visible pixels cross a room boundary. Naming a stranger requires meeting."""
    out={k:actor[k] for k in ('kind','room','subject','pixel_art','combat_pose','pose_art') if k in actor}
    out['appearance']={k:v for k,v in actor['appearance'].items() if k not in ('seed','sources')}
    if 'paperdoll' in actor:
        doll=actor['paperdoll']
        out['paperdoll']={k:v for k,v in doll.items() if k not in ('cut','equipment')}
        out['paperdoll']['equipment']=[{k:v for k,v in g.items() if k not in ('item_id','name')} for g in doll['equipment']]
    if actor.get('activity'):out['activity']={'kind':actor['activity']['kind']}
    if actor.get('combat_pose'):
        equipped=actor.get('paperdoll',{}).get('equipment',[]) or actor.get('held_gear',[])
        out['held_visual']=[{k:v for k,v in g.items() if k not in ('item_id','name')} for g in equipped if g.get('item_id') and (g.get('layer') in ('weapon','offhand') or g.get('slot') in ('weapon','mainhand','offhand'))]
    if actor.get('held_gear'):
        out['held_gear']=[{k:v for k,v in g.items() if k not in ('item_id','name')} for g in actor['held_gear']]
    return out
