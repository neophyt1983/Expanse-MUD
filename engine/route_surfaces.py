"""Authored road/trail tile surfaces, never movement edges or secret routes."""
KINDS = ('road', 'trail')
AXES = ('east_west', 'north_south', 'crossroads')


def descriptor(room):
    value = room.get('route_surface')
    if (isinstance(value, dict) and value.get('kind') in KINDS
            and value.get('axis') in AXES):
        return {'kind': value['kind'], 'axis': value['axis']}
    return None


def validate(data):
    errors = []
    for room in data.get('room', []):
        value = room.get('route_surface', {})
        if value == {}:
            continue
        if (not isinstance(value, dict) or set(value) != {'kind', 'axis'}
                or descriptor(room) is None):
            errors.append(str(room.get('id')) + ': route_surface must be {} or kind road/trail and axis east_west/north_south/crossroads')
    return errors
