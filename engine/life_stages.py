"""Pure, fictional development rules measured in local Expanse years.

Sentient adulthood/work/school thresholds do not use animal breeding maturity.
No call here changes an actor, grants consent, or retires an elder. Legacy static
ages stay static unless the population system explicitly enrolls an actor.
"""
from copy import deepcopy
import math
from functools import lru_cache
from types import MappingProxyType
from engine import worldtime, living

DEFAULT_PROFILE = dict(fictional=True, infancy_end_years=3, school_start_years=6,
    adolescence_start_years=13, adulthood_years=18, work_start_years=18,
    elder_years=65)
THRESHOLDS = tuple(k for k in DEFAULT_PROFILE if k.endswith('_years'))
_DEFAULT_VIEW = MappingProxyType(DEFAULT_PROFILE)


def _number(value):
    if type(value) not in (int, float): return False
    try: return math.isfinite(value)
    except OverflowError: return False


def validate_profile(config, label='life_stages'):
    """Return errors, never mutate input or throw on malformed JSON values."""
    if not isinstance(config, dict): return [label + ' must be an object']
    errors = []
    if config.get('fictional', True) is not True:
        errors.append(label + '.fictional must be true: these are author settings')
    for key in config:
        if key not in DEFAULT_PROFILE: errors.append(label + ': unknown field ' + str(key))
    merged = {**DEFAULT_PROFILE, **config}
    # Raising adulthood alone also raises the default work and elder thresholds.
    if _number(merged['adulthood_years']):
        if 'work_start_years' not in config:
            merged['work_start_years'] = max(18, merged['adulthood_years'])
        if 'elder_years' not in config:
            merged['elder_years'] = max(65, merged['adulthood_years'])
    for key in THRESHOLDS:
        if not _number(merged[key]) or merged[key] < 0:
            errors.append(label + '.' + key + ' must be a finite nonnegative number')
    if errors: return errors
    if merged['adulthood_years'] < 18:
        errors.append(label + ': sentient adulthood cannot be below 18 local years')
    if not (merged['infancy_end_years'] <= merged['school_start_years'] <
            merged['adulthood_years'] and merged['infancy_end_years'] <=
            merged['adolescence_start_years'] < merged['adulthood_years']):
        errors.append(label + ': infancy, school and adolescence must precede adulthood')
    if merged['work_start_years'] < merged['adulthood_years']:
        errors.append(label + ': work cannot start before sentient adulthood')
    if merged['elder_years'] < merged['adulthood_years']:
        errors.append(label + ': elder threshold cannot precede adulthood')
    return errors


@lru_cache(maxsize=256)
def _resolved_values(values):
    config = {key: value for key, _kind, value in values}
    errors = validate_profile(config)
    if errors: raise ValueError('; '.join(errors))
    result = {**DEFAULT_PROFILE, **config}
    if 'work_start_years' not in config:
        result['work_start_years'] = max(18, result['adulthood_years'])
    if 'elder_years' not in config:
        result['elder_years'] = max(65, result['adulthood_years'])
    return MappingProxyType(result)


def _profile_view(species_def):
    if species_def is None: return _DEFAULT_VIEW
    if not isinstance(species_def, dict): raise ValueError('Species definition must be an object.')
    config = species_def.get('life_stages', {})
    if not isinstance(config, dict): raise ValueError('life_stages must be an object.')
    if not config: return _DEFAULT_VIEW
    # Key on values, not object identity, so Creator edits invalidate naturally.
    try: return _resolved_values(tuple((key, type(value).__name__, value) for key, value in sorted(config.items())))
    except TypeError: raise ValueError('life_stages values must be scalar author settings.') from None


def resolve_profile(species_id=None, species_def=None):
    """Return isolated explicit species rules; a profession is never a species.

    Unknown sentient species use a conservative 18-year gameplay floor. Animal
    maturity_years is intentionally ignored. No lore or real biology is inferred.
    """
    return dict(_profile_view(species_def))


def validate_age(config, now=None, label='social_profile'):
    if not isinstance(config, dict): return [label + ' must be an object']
    errors = []
    if now is not None and not _number(now): return [label + ': current minute must be finite']
    for key in ('age_years', 'age_epoch_years'):
        if key in config and (not _number(config[key]) or config[key] < 0):
            errors.append(label + '.' + key + ' must be a finite nonnegative number')
    for key in ('born_minute', 'age_epoch_minute'):
        value = config.get(key)
        if value is not None and (type(value) is not int or (now is not None and value > now)):
            errors.append(label + '.' + key + ' must be an integer at or before the current minute')
    if ('age_epoch_minute' in config) != ('age_epoch_years' in config):
        errors.append(label + ': age_epoch_minute and age_epoch_years must be supplied together')
    return errors


def age_years(social_profile, now=0):
    """Fractional local age; negative births are valid, future births are not."""
    if not isinstance(social_profile, dict) or not _number(now):
        raise ValueError('Age requires a profile and finite current minute.')
    born = social_profile.get('born_minute')
    if born is not None:
        if type(born) is not int or born > now: raise ValueError('Birth minute must be an integer at or before now.')
        return (now - born) / worldtime.MINUTES_PER_YEAR
    epoch = social_profile.get('age_epoch_minute')
    if epoch is not None:
        value = social_profile.get('age_epoch_years')
        if type(epoch) is not int or epoch > now or not _number(value) or value < 0:
            raise ValueError('Age epoch requires a past integer minute and nonnegative age_epoch_years.')
        return value + (now - epoch) / worldtime.MINUTES_PER_YEAR
    # Unknown age is never an implicit adult in the pure API. relationships
    # supplies its established age=25 default for legacy adult gameplay.
    value = social_profile.get('age_years', 0)
    if not _number(value) or value < 0: raise ValueError('Age must be finite and nonnegative.')
    return value


def anchor_profile(social_profile, now=0):
    """Opt-in copy for newly enrolled actors only; existing birth/epoch wins."""
    age = age_years(social_profile, now)
    result = deepcopy(social_profile)
    if result.get('born_minute') is None and result.get('age_epoch_minute') is None:
        result.update(age_epoch_minute=now, age_epoch_years=age)
    return result


def classify(social_profile, species_def=None, now=0):
    age = age_years(social_profile, now)
    cfg = _profile_view(species_def)
    sentient = social_profile.get('sentient', False) is True
    if not sentient:
        return dict(age_years=age, stage='animal', sentient=False, adult=False,
                    can_work=False, in_school=False, adulthood_years=cfg['adulthood_years'])
    adult = age >= cfg['adulthood_years']
    stage = ('infant' if age < cfg['infancy_end_years'] else
             'child' if age < cfg['adolescence_start_years'] else
             'adolescent' if not adult else
             'adult' if age < cfg['elder_years'] else 'elder')
    return dict(age_years=age, stage=stage, sentient=True, adult=adult,
        can_work=adult and age >= cfg['work_start_years'],
        in_school=cfg['school_start_years'] <= age < cfg['adulthood_years'],
        adulthood_years=cfg['adulthood_years'])


def is_adult(social_profile, species_def=None, now=0):
    """Allocation-free shared adulthood predicate for simulation hot paths."""
    return (social_profile.get('sentient') is True and
            age_years(social_profile, now) >= _profile_view(species_def)['adulthood_years'])


def can_work(social_profile, species_def=None, now=0):
    """Same work gate as classify, without constructing a descriptive result."""
    if social_profile.get('sentient') is not True: return False
    cfg = _profile_view(species_def)
    return age_years(social_profile, now) >= max(cfg['adulthood_years'], cfg['work_start_years'])


def for_entity(w, e, social_profile=None):
    if social_profile is None:
        from engine import relationships
        social_profile = relationships.profile(w, e)
    social = social_profile
    species = getattr(w, 'species', {}).get(social.get('species'), {})
    return classify(social, species, living.state(w)['minute'])


def validate(data, metadata=None, now=None):
    errors = []
    for row in data.get('species', []):
        if 'life_stages' in row:
            errors.extend(validate_profile(row['life_stages'], str(row.get('id', 'species')) + '.life_stages'))
    for kind in ('npc', 'race'):
        for row in data.get(kind, []):
            if 'social_profile' in row:
                errors.extend(validate_age(row['social_profile'], now, str(row.get('id', kind)) + '.social_profile'))
    return errors
