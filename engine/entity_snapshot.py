"""Exact dataclasses.asdict snapshots with a fast path for normal save values.

Every mutable list/dict is copied. Unusual Python types still use asdict's own
conversion rules rather than introducing a new persistence format.
"""
from dataclasses import dataclass,asdict,fields

_ATOMIC={str,int,float,bool,type(None)}

@dataclass
class _Fallback:
    value: object


def _copy(value):
    kind=type(value)
    if kind in _ATOMIC:return value
    if kind is list:return [_copy(item) for item in value]
    if kind is dict:return {_copy(key):_copy(item) for key,item in value.items()}
    if kind is tuple:return tuple(_copy(item) for item in value)
    return asdict(_Fallback(value))['value']


def snapshot(entity):
    return {field.name:_copy(getattr(entity,field.name)) for field in fields(entity)}
