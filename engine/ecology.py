"""Species requirements shared by player crafting and NPC husbandry."""
from collections import Counter
from engine import relationships

# Wildlife migrations use these categories too. Keep them valid for existing
# worlds; validation must never rewrite a creator's species to a guessed class.
SPECIES_CATEGORIES = (
    'bird', 'fish', 'mammal', 'insect', 'plant',
    'arachnid', 'crustacean', 'reptile', 'mollusk',
)


def available(w, room, recipe):
    from engine import geology_impacts
    if geology_impacts.room_unusable(w,room):return False
    if any(geology_impacts.resource_blocked(w,room,rid) for rid in recipe.get('requires_resources',[])):return False
    if not set(recipe.get('requires_resources',[]))<=set(getattr(w,'room_details',{}).get(room,{}).get('resources',[])):return False
    # Recipes without an animal requirement need no livestock census.
    required=recipe.get('requires_species',{})
    if not required:return True
    counts=Counter()
    for animal in w.entities_in_room(room):
        if animal.is_player or not animal.alive:continue
        p=relationships.profile(w,animal)
        if recipe.get('requires_carrier') and p['reproductive_role']!='carrier':continue
        if not p['sentient'] and not p['undead'] and p['age_years']>=p['maturity_years']:
            counts[p['species']]+=1
    return all(counts[s]>=n for s,n in required.items())


def in_season(w,resource,room=None):
    from engine import climate
    if room in w.rooms:
        local=climate.conditions(w,room)
        if local['controlled_growing']:return True
        if resource.get('species') and not resource.get('temperature_min_c',0)<=local['temperature_c']<=resource.get('temperature_max_c',45):return False
    return not resource.get('seasons') or relationships.season(w,room) in resource['seasons']


def validate(data):
    issues=[];species={s['id'] for s in data.get('species',[])};items={i['id'] for i in data.get('item',[])}
    resources={r['id'] for r in data.get('resource',[])}
    for row in data.get('recipe',[])+data.get('resource',[]):
        if any(r not in resources for r in row.get('requires_resources',[])):issues.append(row['id']+': unknown required resource')
        refs=row.get('requires_species',{})
        if not isinstance(refs,dict) or any(s not in species or type(n) is not int or n<1 for s,n in refs.items()):issues.append(row['id']+': invalid species requirement')
    for row in data.get('species',[]):
        if row.get('category') not in SPECIES_CATEGORIES:
            issues.append(f"{row['id']}: invalid species category {row.get('category')!r}; "
                          f"expected one of: {', '.join(SPECIES_CATEGORIES)} (species.json)")
        for field in ('renewable_products','remains'):
            refs=row.get(field,{})
            if not isinstance(refs,dict) or any(i not in items or type(n) is not int or n<1 for i,n in refs.items()):issues.append(row['id']+': invalid '+field)
    for row in data.get('resource',[]):
        if 'shared_renewal' in row and type(row['shared_renewal']) is not bool:issues.append(row['id']+': shared_renewal must be boolean')
        if row.get('species') and row['species'] not in species:issues.append(row['id']+': unknown species')
        if any(s not in ('spring','summer','autumn','winter') for s in row.get('seasons',[])):issues.append(row['id']+': invalid harvest season')
    from engine import wildlife
    from engine import hand_resources
    return issues+wildlife.validate(data)+hand_resources.validate(data)
