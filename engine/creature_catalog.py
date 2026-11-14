"""Shared creature classification for the field books, encounters and zoos.

Aggression, danger and a place in an encounter do not make an animal a monster.
Creator categories take precedence; the small legacy list describes authored
supernatural beings whose old files predate the category field.
"""
ANIMALS = {'bird', 'fish', 'mammal', 'insect', 'arachnid', 'crustacean', 'reptile', 'mollusk'}
LEGACY_MONSTERS = frozenset('wl_horror_' + str(i) for i in range(5))


def kind(definition, species=None):
    explicit = definition.get('creature_kind')
    if explicit in ('monster', 'creature', 'person', 'plant'):
        return explicit
    profile = definition.get('social_profile') or {}
    sid = definition.get('species') or profile.get('species')
    spec = (species or {}).get(sid, {})
    if definition.get('is_monster') is True or definition.get('id') in LEGACY_MONSTERS:
        return 'monster'
    if profile.get('sentient') is True or spec.get('sentient') is True:
        return 'person'
    if spec.get('category') == 'plant' or definition.get('category') == 'plant':
        return 'plant'
    if profile.get('undead') is True or definition.get('supernatural') is True:
        return 'monster'
    if spec.get('category') in ANIMALS or definition.get('category') in ANIMALS:
        return 'creature'
    if profile.get('sentient') is False or definition.get('sentient') is False:
        return 'creature'
    return 'person'


def taxon(definition, species=None):
    """Sex/role variants share one ordinary species entry; monsters retain IDs."""
    category = kind(definition, species)
    if category == 'creature':
        sid = definition.get('species') or (definition.get('social_profile') or {}).get('species')
        if sid in (species or {}):
            return sid
    return definition.get('id') or definition.get('name', '')
