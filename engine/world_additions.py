"""Apply compatible, additive content from an installed template to an older adventure in memory."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path


def additions(folder, games, *, template_dirs=()):
    rules_path = folder / 'world-rules.json'
    if not rules_path.is_file() or (not games.is_dir() and not template_dirs):
        return None
    raw=rules_path.read_bytes()
    digest=hashlib.sha256(raw).hexdigest()
    canonical=hashlib.sha256(json.dumps(json.loads(raw),sort_keys=True,separators=(',',':'),
                                       ensure_ascii=False).encode()).hexdigest()
    # The compatibility key also serves as the filename. Unrelated worlds are never opened.
    best=None
    templates = list(games.iterdir()) if games.is_dir() else []
    templates.extend(Path(path) for path in template_dirs)
    for template in sorted(set(templates)):
        if template == folder or template.name.startswith(('.', 'adventure_')) or template.is_symlink():
            continue
        updates=template/'assets'/'updates'
        base=digest
        if not (updates/(base+'.json')).is_file():
            aliases=updates/'rule-signatures.json'
            if aliases.is_symlink() or updates.is_symlink() or updates.parent.is_symlink() or not aliases.is_file():
                continue
            base=json.loads(aliases.read_bytes()).get(canonical)
            if not isinstance(base,str) or len(base)!=64 or any(c not in '0123456789abcdef' for c in base):
                continue
        patch=updates/(base+'.json')
        if patch.is_file() and not any(p.is_symlink() for p in (patch, patch.parent, patch.parent.parent)):
            data = json.loads(patch.read_bytes())
            if data.get('base') == base:
                def revision(entry):
                    return (entry.get('rules',{}).get('survey_revision',0),entry.get('text_revision',0))
                if best is None or revision(data)>revision(best):best=data
    return best


def records(name, rows, patch):
    if not patch or not isinstance(rows,list):
        return rows
    by_id={r['id']:r for r in rows}
    for extra in patch.get('records',{}).get(name,[]):
        if extra['id'] not in by_id:
            rows.append(extra)
            by_id[extra['id']]=extra
    # Compare before replacing a field so an adventure's creator edits survive.
    for change in patch.get('edits',{}).get(name,[]):
        row=by_id.get(change['id'])
        if row is not None and row.get(change['field'])==change['old']:
            row[change['field']]=change['new']
    # Old campaigns can contain records that the new template retired. Match
    # the full original row so a creator's replacement with the same ID survives.
    retired = patch.get('remove_records', {}).get(name, [])
    for original in retired:
        current = by_id.get(original['id'])
        if current == original:
            rows.remove(current)
            del by_id[original['id']]
    if name == 'rooms.json':
        for room, exits in patch.get('add_exits',{}).items():
            if room in by_id:
                for direction,target in exits.items():
                    by_id[room].setdefault('exits',{}).setdefault(direction,target)
    return rows


def metadata(current, patch):
    """Upgrade matching authored metadata fields without changing save identity."""
    if not patch:
        return current
    for change in patch.get('metadata_edits', []):
        if current.get(change['field']) == change.get('old'):
            current[change['field']] = change['new']
    return current


def rules(current, patch):
    """Add missing rule blocks, then conditionally upgrade known old values."""
    if not patch:
        return current
    for key, value in patch.get('rules', {}).items():
        current.setdefault(key, deepcopy(value))
    for change in patch.get('rule_edits', []):
        if current.get(change['field']) == change.get('old'):
            current[change['field']] = deepcopy(change['new'])
    return current


def pixel_library(current, patch):
    """Compose authored art in memory while retaining creator-owned revisions."""
    changes = (patch or {}).get('pixel_art')
    if not changes:
        return current
    result = deepcopy(current)
    for ident, document in changes.get('assets', {}).items():
        result['assets'].setdefault(ident, deepcopy(document))
    for change in changes.get('bindings', []):
        if result['bindings'].get(change['target']) == change.get('old'):
            result['bindings'][change['target']] = change['new']
    return result


