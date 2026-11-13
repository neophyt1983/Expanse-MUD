"""Packaged Expanse foundation, separate from Creator templates and play saves.

The UI never edits this directory. Changed bytes fail closed; a release updates
this pinned source and the code together. User templates remain in games/.
"""
from pathlib import Path
from engine import history_templates
TEMPLATE_ID = 'official_expanse'
REVISION = '2026-11-10-open-horizons-1'
SIGNATURE = 'f07b39168d427e1826991cd5af64c3d170e8b0f26fdea9bcd07f890d35d805e3'

def directory(games_root):
    return Path(games_root).parent/'foundations'/'expanse'

def available(games_root):
    return directory(games_root).is_dir()

def snapshot(games_root):
    bundle=history_templates.snapshot(directory(games_root))
    if bundle['source_signature']!=SIGNATURE:
        raise ValueError('The official Expanse foundation changed or is incomplete. Reinstall the matching release; existing games were not changed.')
    return bundle
