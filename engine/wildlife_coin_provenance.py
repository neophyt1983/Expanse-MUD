"""Control new wildlife coin sources and retain previously held wallets."""

FLAG = 'wildlife_coin_provenance'
FORMAT = 'v1'
ANIMAL_CATEGORIES = frozenset({
    'amphibian', 'arachnid', 'bird', 'crustacean', 'fish',
    'insect', 'mammal', 'mollusk', 'reptile',
})


def enabled(metadata):
    """Recognize the Founding Cities template even under an import alias."""
    if FLAG in metadata:
        return metadata[FLAG] == FORMAT
    genesis = metadata.get('municipal_genesis')
    return (metadata.get('civic_opening_release') in ('1.10.0-rc1', '1.10.0')
            and isinstance(genesis, dict)
            and genesis.get('version') == 1 and genesis.get('seed') == 20261122)


def guarded(w, definition, actor=None):
    """Require positive evidence of a non-sentient animal; never guess from a name."""
    if not enabled(getattr(w, 'metadata', {})):
        return False
    if actor is not None and actor.is_player:
        return False
    profile = definition.get('social_profile', {})
    if not isinstance(profile, dict):
        return False
    current = actor.progress.get('social_profile', {}) if actor is not None else {}
    if not isinstance(current, dict):
        return False
    if (profile.get('sentient') is True or current.get('sentient') is True
            or profile.get('undead') is True or current.get('undead') is True
            or definition.get('creature_kind') in ('humanoid', 'undead', 'monster')):
        return False
    species_id = profile.get('species')
    # A conflicting present-day profile is not weak evidence for suppression.
    if 'species' in current and current['species'] != species_id:
        return False
    species = getattr(w, 'species', {}).get(species_id) if isinstance(species_id, str) else None
    if species is not None:
        category = species.get('category') if isinstance(species, dict) else None
        return (isinstance(category, str) and category in ANIMAL_CATEGORIES
                and species.get('sentient') is False)
    if profile.get('sentient') is not False:
        return False
    return (definition.get('creature_kind') == 'creature'
            or (species_id == 'expedition_wildlife'
                and definition.get('expedition_role') in ('quarry', 'predator')))


def initial_purse(w, definition):
    """A wildlife template is not a funding source for a new individual."""
    return 0 if guarded(w, definition) else definition.get('gold', 0)
