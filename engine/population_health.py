"""Optional seeded initial chronic profiles, separate from acute disease/injury.

All conditions and support effects below are fictional author choices. This is
starting prevalence, never per-tick incidence or an age-based damage rule. The
optional adult_reference preset borrows ONLY 0/1/2+ counts for ten selected
conditions from NCHS 2024 US noninstitutionalized adults. It is not a universal
health target, a diagnosis model, or a disability survey.
"""
from copy import deepcopy
import math

FICTIONAL_BANDS = [
    dict(min_age_years=0, max_age_years=18, count_weights=[.98, .018, .002]),
    dict(min_age_years=18, max_age_years=45, count_weights=[.82, .15, .03]),
    dict(min_age_years=45, max_age_years=65, count_weights=[.62, .27, .11]),
    dict(min_age_years=65, max_age_years=None, count_weights=[.40, .36, .24]),
]
ADULT_REFERENCE_BANDS = [
    # There is no pediatric estimate in the adult source. This row is fictional.
    deepcopy(FICTIONAL_BANDS[0]),
    dict(min_age_years=18, max_age_years=45, count_weights=[.738, .198, .064]),
    dict(min_age_years=45, max_age_years=65, count_weights=[.385, .319, .296]),
    dict(min_age_years=65, max_age_years=None, count_weights=[.135, .245, .620]),
]
# Names describe a game-world condition, not a medical diagnosis. Support notes
# have no automatic work, combat, movement, mortality or ability-score effects.
CONDITIONS = [
    dict(id='joint_stiffness', label='Recurring joint stiffness', weight=1,
         support_chance=.3, support_notes=['Benefits from pauses between long tasks.']),
    dict(id='variable_stamina', label='Variable stamina', weight=1,
         support_chance=.3, support_notes=['Prefers a flexible pace with rest breaks.']),
    dict(id='light_sensitivity', label='Light-sensitive eyes', weight=1,
         support_chance=.3, support_notes=['Uses shaded work areas when available.']),
    dict(id='airway_sensitivity', label='Airway sensitivity', weight=1,
         support_chance=.3, support_notes=['Prefers work away from dust and smoke.']),
    dict(id='balance_fluctuation', label='Intermittent balance difficulty', weight=1,
         support_chance=.3, support_notes=['Values clear paths and steady handrails.']),
    dict(id='digestive_sensitivity', label='Digestive sensitivity', weight=1,
         support_chance=.3, support_notes=['Prefers familiar meals and regular breaks.']),
    dict(id='skin_irritation', label='Recurring skin irritation', weight=1,
         support_chance=.3, support_notes=['Chooses comfortable protective clothing.']),
    dict(id='head_discomfort', label='Recurring head discomfort', weight=1,
         support_chance=.3, support_notes=['Values a quiet place for short breaks.']),
    dict(id='sleep_disruption', label='Interrupted sleep', weight=1,
         support_chance=.3, support_notes=['Prefers predictable hours and rest periods.']),
    dict(id='hearing_difficulty', label='Hearing difficulty', weight=1,
         support_chance=.3, support_notes=['Uses written signs alongside spoken instructions.']),
]
DEFAULT_CONFIG = dict(enabled=False, preset='fictional', fictional=True,
    multi_count_weights={'2': .55, '3': .30, '4': .10, '5': .05})
KEYS = set(DEFAULT_CONFIG) | {'age_bands', 'conditions', 'species_profiles'}


def _number(value):
    if type(value) not in (int, float): return False
    try: return math.isfinite(value)
    except OverflowError: return False


def _weights(values):
    return (isinstance(values, list) and bool(values) and
            all(_number(v) and v >= 0 for v in values) and
            math.isclose(sum(values), 1, rel_tol=0, abs_tol=1e-8))


def validate_profile(config, label='population health', _nested=False):
    """Pure JSON validation, including disabled profiles; no silent coercions."""
    if not isinstance(config, dict): return [label + ' must be an object']
    errors = []
    for key in config:
        if key not in KEYS: errors.append(label + ': unknown field ' + str(key))
    if type(config.get('enabled', False)) is not bool: errors.append(label + '.enabled must be boolean')
    if config.get('fictional', True) is not True: errors.append(label + '.fictional must be true')
    preset = config.get('preset', 'fictional')
    if preset not in ('fictional', 'adult_reference'):
        errors.append(label + ': unknown initial prevalence preset')
    bands = config.get('age_bands', ADULT_REFERENCE_BANDS if preset == 'adult_reference' else FICTIONAL_BANDS)
    if not isinstance(bands, list) or not bands:
        errors.append(label + '.age_bands must be a nonempty list')
    else:
        end = 0
        for index, band in enumerate(bands):
            name = label + '.age_bands[' + str(index) + ']'
            if not isinstance(band, dict): errors.append(name + ' must be an object'); continue
            low, high = band.get('min_age_years'), band.get('max_age_years')
            if not _number(low) or low < 0 or low != end:
                errors.append(name + ': contiguous age bands must start at zero')
            if high is None:
                if index != len(bands) - 1: errors.append(name + ': only final band may be open-ended')
            elif not _number(high) or not _number(low) or high <= low:
                errors.append(name + ': maximum age must exceed minimum age')
            if index == len(bands) - 1 and high is not None:
                errors.append(name + ': final band must be open-ended')
            end = high
            weights = band.get('count_weights')
            if not _weights(weights) or len(weights) != 3:
                errors.append(name + ': zero/one/two-plus count_weights must be three probabilities summing to one')
    catalog = config.get('conditions', CONDITIONS)
    if not isinstance(catalog, list) or len(catalog) < 2:
        errors.append(label + '.conditions must contain at least two fictional conditions')
        catalog = []
    ids = set()
    for condition in catalog:
        if not isinstance(condition, dict): errors.append(label + ': condition must be an object'); continue
        ident = condition.get('id')
        if not isinstance(ident, str) or not ident or ident in ids:
            errors.append(label + ': condition IDs must be unique nonempty strings')
        else: ids.add(ident)
        if not isinstance(condition.get('label'), str) or not condition['label'].strip():
            errors.append(label + ': condition needs a nonempty label')
        if not _number(condition.get('weight', 1)) or condition.get('weight', 1) <= 0:
            errors.append(label + ': condition weight must be positive and finite')
        chance = condition.get('support_chance', 0)
        if not _number(chance) or not 0 <= chance <= 1:
            errors.append(label + ': fictional support_chance must be 0–1')
        notes = condition.get('support_notes', [])
        if not isinstance(notes, list) or any(not isinstance(n, str) or not n.strip() for n in notes):
            errors.append(label + ': support_notes must be nonempty text strings')
    multiple = config.get('multi_count_weights', DEFAULT_CONFIG['multi_count_weights'])
    if not isinstance(multiple, dict) or not multiple:
        errors.append(label + '.multi_count_weights must be an object')
    else:
        if any(not isinstance(k, str) or not k.isdigit() or not 2 <= int(k) <= len(catalog) for k in multiple):
            errors.append(label + ': multiple counts must be string integers from 2 through catalog size')
        if not _weights(list(multiple.values())):
            errors.append(label + ': multiple-count probabilities must sum to one')
    species = config.get('species_profiles', {})
    if not isinstance(species, dict): errors.append(label + '.species_profiles must be an object')
    elif _nested and species: errors.append(label + ': nested species_profiles are not supported')
    else:
        for ident, override in species.items():
            if not isinstance(ident, str) or not ident: errors.append(label + ': species ID must be nonempty text')
            if not isinstance(override, dict): errors.append(label + ': species override must be an object'); continue
            # An explicit species override inherits root choices, never claims a
            # separately measured species-specific epidemiology.
            merged = {k: v for k, v in config.items() if k != 'species_profiles'}
            merged.update(override)
            errors.extend(validate_profile(merged, label + '.species_profiles.' + str(ident), True))
    return errors


def _choose(rng, rows, weights):
    target = rng.random() * sum(weights)
    for row, weight in zip(rows, weights):
        target -= weight
        if target < 0: return row
    return rows[-1]


def seed_profile(age_years, species_id, config, rng):
    """Return a reproducible initial snapshot or None; never mutate inputs.

    rng must be an isolated seeded random.Random supplied by the caller. No
    global RNG, tick hook, automatic cure, disability inference or retirement.
    """
    errors = validate_profile(config)
    if errors: raise ValueError('; '.join(errors))
    if not _number(age_years) or age_years < 0: raise ValueError('Age must be finite and nonnegative.')
    if not isinstance(species_id, str) or not species_id: raise ValueError('Species must be explicit nonempty text.')
    cfg = {**DEFAULT_CONFIG, **config}
    cfg.update(config.get('species_profiles', {}).get(species_id, {}))
    if not cfg['enabled']: return None
    bands = cfg.get('age_bands', ADULT_REFERENCE_BANDS if cfg['preset'] == 'adult_reference' else FICTIONAL_BANDS)
    band = next(b for b in bands if age_years >= b['min_age_years'] and
                (b['max_age_years'] is None or age_years < b['max_age_years']))
    bucket = _choose(rng, [0, 1, 2], band['count_weights'])
    count = bucket
    if bucket == 2:
        multiple = cfg['multi_count_weights']
        count = int(_choose(rng, list(multiple), list(multiple.values())))
    available = list(cfg.get('conditions', CONDITIONS))
    conditions = []
    for _ in range(count):
        selected = _choose(rng, available, [c.get('weight', 1) for c in available])
        available.remove(selected)
        notes = (list(selected.get('support_notes', []))
                 if rng.random() < selected.get('support_chance', 0) else [])
        conditions.append(dict(id=selected['id'], label=selected['label'], support_notes=notes))
    return dict(version=1, fictional=True, initial_age_years=age_years, species=species_id,
        preset=cfg['preset'], conditions=conditions,
        support_notes=list(dict.fromkeys(n for c in conditions for n in c['support_notes'])),
        source=('NCHS 2024 adult count calibration; conditions, child curves and supports are fictional.'
                if cfg['preset'] == 'adult_reference' else 'Fictional author-selected initial prevalence.'),
        mechanical_effects=False)


def assign_initial(w, e, rng, config):
    """Explicit enrollment helper, never called automatically for legacy actors."""
    if 'population_health' in e.progress: return e.progress['population_health']
    from engine import relationships, life_stages
    social = relationships.profile(w, e)
    stage = life_stages.for_entity(w, e, social)
    if not stage['sentient']: return None
    result = seed_profile(stage['age_years'], social['species'], config, rng)
    if result is not None: e.progress['population_health'] = result
    return result


def validate(data, metadata=None):
    errors = []
    metadata = {} if metadata is None else metadata
    population = metadata.get('population', {})
    if isinstance(population, dict) and 'health' in population:
        errors.extend(validate_profile(population['health']))
    for row in data.get('species', []):
        if 'population_health' in row:
            errors.extend(validate_profile(row['population_health'], str(row.get('id', 'species')) + '.population_health'))
    return errors
