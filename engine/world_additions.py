"""Apply compatible, additive content from an installed template to an older adventure in memory."""
import hashlib
import json


def additions(folder, games):
    rules_path = folder / 'world-rules.json'
    if not rules_path.is_file() or not games.is_dir():
        return None
    raw=rules_path.read_bytes()
    digest=hashlib.sha256(raw).hexdigest()
    canonical=hashlib.sha256(json.dumps(json.loads(raw),sort_keys=True,separators=(',',':'),
                                       ensure_ascii=False).encode()).hexdigest()
    # The compatibility key also serves as the filename. Unrelated worlds are never opened.
    best=None
    for template in sorted(games.iterdir()):
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
    if name == 'rooms.json':
        for room, exits in patch.get('add_exits',{}).items():
            if room in by_id:
                for direction,target in exits.items():
                    by_id[room].setdefault('exits',{}).setdefault(direction,target)
    return rows
