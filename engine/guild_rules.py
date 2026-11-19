"""Validate optional task guilds against the existing authored catalogs."""
import re

TASK = re.compile(r'^[a-z][a-z0-9_]{0,63}$')


def validate(data):
    by = {kind: {row['id']: row for row in data.get(kind, []) if isinstance(row, dict) and 'id' in row}
          for kind in ('group', 'npc', 'class', 'quest', 'room', 'item', 'recipe', 'resource')}
    errors = []

    def issue(where, text):
        errors.append(where + ': ' + text)

    def whole(row, key, low, high, where, default=0):
        value = row.get(key, default)
        if type(value) is not int or not low <= value <= high:
            issue(where, key + ' must be a whole number from ' + str(low) + ' to ' + str(high))

    def refs(value, kind, where, maximum=64):
        if (not isinstance(value, list) or len(value) > maximum or
                any(not isinstance(ident, str) or ident not in by[kind] for ident in value) or
                len(set(value)) != len(value)):
            issue(where, 'use a bounded list of distinct existing ' + kind + ' IDs')
            return False
        return True

    def task_map(value, where):
        if not isinstance(value, dict) or len(value) > 32:
            issue(where, 'task skills must be an object with at most 32 entries')
            return
        for task, level in value.items():
            if not isinstance(task, str) or not TASK.fullmatch(task) or type(level) is not int or not 0 <= level <= 100:
                issue(where, 'task skill IDs need whole levels from 0 to 100')

    guilds = {}
    for ident, group in by['group'].items():
        config = group.get('guild', {})
        if not isinstance(config, dict):
            issue(ident, 'guild must be an object')
            continue
        if not config:
            continue
        if set(config) - {'enabled', 'tasks', 'rooms', 'join_fee', 'requirements', 'lessons'}:
            issue(ident, 'unsupported guild fields')
        if type(config.get('enabled', False)) is not bool:
            issue(ident, 'guild.enabled must be boolean')
        tasks = config.get('tasks', [])
        if (not isinstance(tasks, list) or not 1 <= len(tasks) <= 32 or
                any(not isinstance(task, str) or not TASK.fullmatch(task) for task in tasks) or
                len(set(tasks)) != len(tasks)):
            issue(ident, 'guild.tasks needs 1-32 distinct task skill IDs')
            tasks = []
        if not refs(config.get('rooms', []), 'room', ident + ' guild.rooms', 32) or not config.get('rooms'):
            issue(ident, 'guild services need actual authored rooms')
        whole(config, 'join_fee', 0, 100000, ident)
        requirements = config.get('requirements', {})
        if not isinstance(requirements, dict) or set(requirements) - {'skills', 'quests'}:
            issue(ident, 'guild requirements support skills and quests')
        else:
            task_map(requirements.get('skills', {}), ident)
            refs(requirements.get('quests', []), 'quest', ident + ' requirements')
        lessons = config.get('lessons', [])
        if not isinstance(lessons, list) or len(lessons) > 64:
            issue(ident, 'guild.lessons must be a list of at most 64 authored courses')
            lessons = []
        seen = set()
        for lesson in lessons:
            if not isinstance(lesson, dict):
                issue(ident, 'lessons must be objects')
                continue
            where = ident + ' lesson ' + str(lesson.get('id', ''))
            if not isinstance(lesson.get('id'), str) or not lesson['id'] or lesson['id'] in seen:
                issue(where, 'lesson IDs must be nonempty and distinct')
            else:
                seen.add(lesson['id'])
            if set(lesson) - {'id', 'name', 'skill', 'min_level', 'max_level', 'gain', 'cost', 'trainer', 'requires_quests'}:
                issue(where, 'unsupported lesson fields')
            if lesson.get('skill') not in tasks:
                issue(where, 'skill must belong to this guild')
            if lesson.get('trainer') not in by['npc']:
                issue(where, 'trainer must be an existing NPC source')
            whole(lesson, 'min_level', 0, 99, where)
            whole(lesson, 'max_level', 1, 100, where)
            if type(lesson.get('max_level')) is int and type(lesson.get('min_level', 0)) is int and lesson['max_level'] <= lesson.get('min_level', 0):
                issue(where, 'max_level must exceed min_level')
            whole(lesson, 'gain', 1, 5, where, 1)
            whole(lesson, 'cost', 0, 100000, where)
            refs(lesson.get('requires_quests', []), 'quest', where)
        if config.get('enabled') is True:
            guilds[ident] = config

    for kind in ('npc', 'class'):
        for ident, row in by[kind].items():
            if 'task_skills' in row:
                task_map(row['task_skills'], ident)
    for ident, row in by['npc'].items():
        plan = row.get('guild_plan', {})
        if not isinstance(plan, dict):
            issue(ident, 'guild_plan must be an object')
            continue
        if not plan:
            continue
        if set(plan) - {'enabled', 'guilds', 'learn', 'quests', 'explore'}:
            issue(ident, 'unsupported guild_plan fields')
        for key in ('enabled', 'learn', 'quests', 'explore'):
            if key in plan and type(plan[key]) is not bool:
                issue(ident, 'guild_plan.' + key + ' must be boolean')
        choices = plan.get('guilds', [])
        if not refs(choices, 'group', ident + ' guild_plan', 16) or not choices:
            issue(ident, 'guild_plan needs explicitly selected guild IDs')
        elif any(choice not in guilds for choice in choices):
            issue(ident, 'guild_plan references a disabled or missing guild')

    for ident, quest in by['quest'].items():
        config = quest.get('guild', {})
        if not isinstance(config, dict):
            issue(ident, 'quest guild must be an object')
            continue
        if not config:
            continue
        if set(config) - {'id', 'skill', 'difficulty', 'need'}:
            issue(ident, 'unsupported quest guild fields')
        guild = guilds.get(config.get('id'))
        if not guild:
            issue(ident, 'quest needs an enabled authored guild')
            continue
        if config.get('skill') not in guild.get('tasks', []):
            issue(ident, 'quest skill must belong to its guild')
        whole(config, 'difficulty', 0, 100, ident)
        for key in ('offer_room', 'turn_in_room'):
            if quest.get(key) not in guild.get('rooms', []):
                issue(ident, key + ' must be an authored service room of its guild')
        if quest.get('progress_scope') != 'accepted':
            issue(ident, 'guild quests must count fresh work after acceptance')
        if not any(ident in source.get('knowledge', {}).get('quests', [])
                   for kind in ('npc', 'item') for source in by[kind].values()):
            issue(ident, 'guild request needs an actual NPC or readable-item knowledge source')
        need = config.get('need')
        if need is None:
            if not any(quest.get(key) for key in ('required_items', 'actions', 'kills', 'visit_rooms', 'talk_to', 'witnesses', 'escort', 'interface_tour')):
                issue(ident, 'guild work needs a real objective')
            continue
        if not isinstance(need, dict) or need.get('kind') != 'stock':
            issue(ident, 'guild need currently supports an authored stock target')
            continue
        if set(need) - {'kind', 'room', 'container', 'item', 'target', 'recipient', 'gold_per_unit', 'batch'}:
            issue(ident, 'unsupported stock need fields')
        if need.get('room') != quest.get('turn_in_room'):
            issue(ident, 'stock hand-in must occur at the actual receiving room')
        room = by['room'].get(need.get('room'), {})
        matches = [entry for entry in room.get('locks', []) if isinstance(entry, dict) and entry.get('id') == need.get('container') and not entry.get('direction')]
        if len(matches) != 1:
            issue(ident, 'stock need must name one real receiving container')
        elif matches[0].get('owner') != need.get('recipient'):
            issue(ident, 'the recipient must actually own the receiving container')
        if need.get('recipient') not in by['npc']:
            issue(ident, 'stock recipient must name an existing NPC source')
        item = by['item'].get(need.get('item'))
        if not item or item.get('anchored_readable') is True:
            issue(ident, 'stock need must request a real movable item')
        whole(need, 'target', 1, 1000, ident)
        whole(need, 'batch', 1, 1000, ident, need.get('target', 1))
        whole(need, 'gold_per_unit', 0, 10000, ident)
        if quest.get('reward_gold', 0) or quest.get('reward_items') or quest.get('required_items'):
            issue(ident, 'stock needs use actual contributions and recipient-funded payment, without additional item or gold rewards')
        if (quest.get('scope', 'character') != 'character' or quest.get('world_effects') or quest.get('world_flags') or
                quest.get('character_flags') or quest.get('reputation') or quest.get('quest_chain') or quest.get('interface_tour') or quest.get('escort')):
            issue(ident, 'stock needs cannot also apply story outcomes or chain rewards')
    return errors
