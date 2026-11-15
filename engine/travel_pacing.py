"""Interpret a world's optional travel speed without changing its other clocks."""
import math


def validate(metadata):
    value = metadata.get('travel_speed_multiplier', 1)
    if type(value) not in (int, float) or not math.isfinite(value) or not .25 <= value <= 4:
        return ['travel_speed_multiplier must be a number from 0.25 to 4']
    return []


def speed(world):
    metadata = getattr(world, 'metadata', {})
    return 1 if validate(metadata) else metadata.get('travel_speed_multiplier', 1)


def quote(world, traveller, base_minutes):
    """Quote elapsed minutes and the fractional remainder without changing state.

    The caller commits the remainder only after an actual successful move.
    Unconfigured worlds keep their old cost. Shared real-time worlds do not
    call this turn-based accounting function.
    """
    remainder = traveller.progress.get('travel_time_fraction', 0)
    if type(remainder) not in (int, float) or not math.isfinite(remainder) or not 0 <= remainder < 1:
        remainder = 0
    total = base_minutes / speed(world) + remainder
    whole = math.floor(total + 1e-9)
    remainder = max(0, round(total - whole, 9))
    return whole, remainder


def commit(traveller, remainder):
    """Ordinary progress, checkpointed only by the existing explicit Save."""
    if remainder:
        traveller.progress['travel_time_fraction'] = remainder
    else:
        traveller.progress.pop('travel_time_fraction', None)
