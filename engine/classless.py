"""Private, default-off trial for freshly created Wild Lands players.

No replacement profession or generic bypass: one training outcome follows
an actual craft action, local instructor and original ability's costs.
"""
from pathlib import Path

FLAG = 'player_progression_pilot'
VERSION = 'wild-lands-skill-start-v1'
MARKER = 'classless_start_v1'
ABILITY = 'ac_field_stitch'
RECIPE = 'lw_bandage'
MENTOR = 'ac_instructor_0'
SCHOOL = 'lw_hearth_school'


def active(w):
    return (Path(str(getattr(w,'game_dir',''))).name == 'wild_lands' or w.metadata.get('civic_opening_release') == '1.10.0-rc1') and w.metadata.get(FLAG) == VERSION


def marked(p):
    return p.is_player and p.char_class is None and p.progress.get(MARKER) == VERSION


def characterize(w, data):
    enabled = active(w)
    supplied = data.get('class')
    if enabled:
        if supplied is not None and (not isinstance(supplied, str) or supplied.strip()):
            raise ValueError('This adventure has no starting class. Reopen the character form.')
        return None, True
    return (supplied or '').strip() or None, False


def options(w):
    from engine.character_style import choices, class_accents
    enabled = active(w)
    return dict(
        races=[dict(choices(row, {}), id=row['id'], name=row.get('name', row['id'])) for row in w.races.values()],
        classes=[] if enabled else [dict(id=row['id'],name=row.get('name',row['id']),accents=class_accents(row)) for row in w.classes.values()],
        sexes=[dict(id=row['id'],name=row.get('name',row['id'])) for row in w.sexes.values()],
        factions=[dict(id=row['id'],name=row.get('name',row['id'])) for row in w.groups.values() if row.get('visibility')=='playable'],
        **({'classless_start':True} if enabled else {}))


def converted(p,a):
    return marked(p) and a.get('id') == ABILITY


def study_reason(w,p,a,*,via_school,preview=False):
    if not converted(p,a):
        return ''
    if not via_school:
        return 'Learn Field Stitch through practical training with Mara Fenwick at Hearthmere Adventurers School.'
    if p.location != SCHOOL:
        return 'Field Stitch practical training is at Hearthmere Adventurers School.'
    if preview:
        return ''
    mentor = next((n for n in w.entities_in_room(p.location)
                   if not n.is_player and n.alive and n.location == SCHOOL
                   and n.source_def == MENTOR and w.entities.get(n.id) is n),None)
    from engine import livelihoods
    if mentor is None or not livelihoods.awake(w,mentor):
        return 'Mara Fenwick is not available to assess your work right now.'
    if not p.progress.get('quest_talks',{}).get(MENTOR,0):
        return 'Speak to Mara Fenwick first to ask about Field Stitch.'
    if not p.progress.get('actions',{}).get('craft:'+RECIPE,0):
        return 'Craft a Clean Bandage yourself from cloth and a medicinal herb before studying Field Stitch.'
    return ''


def mentor_line(w,p,npc):
    if marked(p) and npc.source_def == MENTOR and npc.location == SCHOOL:
        fee=w.abilities.get(ABILITY,{}).get('training_cost',20)
        return ('For Field Stitch, first craft a Clean Bandage yourself from cloth and a medicinal herb. '
                'Then choose Field Stitch in Abilities or use study ac_field_stitch while I’m here. '
                f'The lesson costs {fee} gold. Each use still needs a Clean Bandage.')
    return ''
