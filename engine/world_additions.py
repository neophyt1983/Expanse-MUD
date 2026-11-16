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
    best=None;best_updates=None
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
                if best is None or revision(data)>revision(best):best=data;best_updates=updates
    return resolve(folder,expand_references(best,best_updates))


def expand_references(patch,updates):
    """Read verified shared update data from the selected template's asset folder.

Each reference names one local JSON transaction and pins its exact bytes. This
keeps portable game files within their existing size budget without repeating
the same authored revision in every historical compatibility bridge.
"""
    if not patch or not patch.get('transaction_refs'):
        return patch
    refs=patch['transaction_refs']
    if not isinstance(refs,list) or updates is None:
        raise ValueError('Content update references need a template directory.')
    result=deepcopy({key:value for key,value in patch.items() if key!='transaction_refs'})
    directory=Path(updates)
    if any(path.is_symlink() for path in (directory,directory.parent,directory.parent.parent)):
        raise ValueError('Content update references cannot follow symbolic links.')
    for ref in refs:
        filename=ref.get('file') if isinstance(ref,dict) else None
        digest=ref.get('sha256') if isinstance(ref,dict) else None
        if (not isinstance(filename,str) or Path(filename).name!=filename or not filename.endswith('.json')
                or not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest)):
            raise ValueError('Content update reference needs a local JSON filename and SHA-256 hash.')
        path=directory/filename
        if path.is_symlink():
            raise ValueError('Content update references cannot follow symbolic links.')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:
            raise ValueError('Content update reference does not match its SHA-256 hash.')
        transaction=json.loads(raw)
        if not isinstance(transaction,dict) or 'transaction_refs' in transaction:
            raise ValueError('Content update reference must contain one transaction object.')
        result.setdefault('transactions',[]).append(transaction)
    return result


def _canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),
                                     ensure_ascii=False).encode()).hexdigest()


def _merge(current,update):
    """Keep transaction order, including remove-then-add of the same record ID."""
    if any(key in update for key in ('transactions','transaction_refs','_resolved_updates')):
        raise ValueError('Nested content update transactions are not supported.')
    current.setdefault('_resolved_updates',[]).append(deepcopy(update))


def resolve(folder,patch):
    """Apply each guarded multi-file revision completely, or leave it unapplied.

    Guards are hashes of original records after earlier compatible revisions, or
    null for IDs which must be absent. Optional metadata/rule guards hash the
    current field value (JSON null when absent). This prevents a half-upgraded quest chain
when a Creator has customized one of its objectives, sources or destinations.
Only authored catalog JSON inside the supplied game directory can be read.
Nothing is written to the imported world or a gameplay checkpoint.
"""
    if not patch or not patch.get('transactions'):
        return patch
    result=deepcopy({key:value for key,value in patch.items() if key!='transactions'})
    applied=[];skipped=[]
    for transaction in patch['transactions']:
        if not isinstance(transaction,dict) or not isinstance(transaction.get('id'),str):
            raise ValueError('Content update transaction needs an ID.')
        guards=transaction.get('record_guards')
        update=transaction.get('update')
        if not isinstance(guards,dict) or not guards or not isinstance(update,dict):
            raise ValueError('Content update transaction needs record guards and an update.')
        matches=True
        for filename,wanted in guards.items():
            if (not isinstance(filename,str) or Path(filename).name!=filename
                    or not filename.endswith('.json') or not isinstance(wanted,dict)):
                raise ValueError('Content update guards must name local JSON catalogs.')
            path=Path(folder)/filename
            if path.is_symlink():
                raise ValueError('Content update guards cannot follow symbolic links.')
            rows=json.loads(path.read_bytes()) if path.is_file() else []
            if not isinstance(rows,list):
                raise ValueError('Content update guards require a record catalog.')
            current={row['id']:row for row in records(filename,deepcopy(rows),result)}
            for ident,digest in wanted.items():
                if not isinstance(ident,str) or (digest is not None and (not isinstance(digest,str)
                        or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest))):
                    raise ValueError('Content update guard needs an ID and a SHA-256 hash or null.')
                if (ident in current if digest is None else ident not in current or _canonical(current[ident])!=digest):
                    matches=False
        for guard_key,filename,apply in (('metadata_guards','metadata.json',metadata),
                                         ('rule_guards','world-rules.json',rules)):
            fields=transaction.get(guard_key,{})
            if not isinstance(fields,dict):
                raise ValueError('Content update field guards must be an object.')
            if not fields:continue
            path=Path(folder)/filename
            if path.is_symlink():
                raise ValueError('Content update guards cannot follow symbolic links.')
            current=json.loads(path.read_bytes()) if path.is_file() else {}
            if not isinstance(current,dict):
                raise ValueError('Content update field guards require an object.')
            current=apply(current,result)
            for field,digest in fields.items():
                if (not isinstance(field,str) or not isinstance(digest,str) or len(digest)!=64
                        or any(c not in '0123456789abcdef' for c in digest)):
                    raise ValueError('Content update field guard needs a name and SHA-256 hash.')
                if _canonical(current.get(field))!=digest:matches=False
        if matches:
            _merge(result,update);applied.append(transaction['id'])
        else:
            skipped.append(transaction['id'])
    result['_applied_transactions']=applied
    result['_skipped_transactions']=skipped
    return result


def records(name, rows, patch):
    if not patch or not isinstance(rows,list):
        return rows
    by_id={r['id']:r for r in rows}
    for extra in patch.get('records',{}).get(name,[]):
        if extra['id'] not in by_id:
            added=deepcopy(extra)
            rows.append(added)
            by_id[added['id']]=added
    # Compare before replacing a field so an adventure's creator edits survive.
    for change in patch.get('edits',{}).get(name,[]):
        row=by_id.get(change['id'])
        if row is not None and row.get(change['field'])==change['old']:
            row[change['field']]=deepcopy(change['new'])
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
    for update in patch.get('_resolved_updates',[]):
        rows=records(name,rows,update)
    return rows


def metadata(current, patch):
    """Upgrade matching authored metadata fields without changing save identity."""
    if not patch:
        return current
    for change in patch.get('metadata_edits', []):
        if current.get(change['field']) == change.get('old'):
            current[change['field']] = deepcopy(change['new'])
    for update in patch.get('_resolved_updates',[]):
        current=metadata(current,update)
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
    for update in patch.get('_resolved_updates',[]):
        current=rules(current,update)
    return current


def pixel_updates(patch):
    """Keep only authored art updates for the world's lazy asset loader."""
    result={}
    if (patch or {}).get('pixel_art'):
        result['pixel_art']=deepcopy(patch['pixel_art'])
    later=[pixel_updates(update) for update in (patch or {}).get('_resolved_updates',[])]
    later=[update for update in later if update]
    if later:result['_resolved_updates']=later
    return result or None


def pixel_library(current, patch):
    """Compose authored art in memory while retaining creator-owned revisions."""
    changes = (patch or {}).get('pixel_art')
    result = deepcopy(current) if changes else current
    if changes:
        for ident, document in changes.get('assets', {}).items():
            result['assets'].setdefault(ident, deepcopy(document))
        for change in changes.get('bindings', []):
            if result['bindings'].get(change['target']) == change.get('old'):
                result['bindings'][change['target']] = change['new']
    for update in (patch or {}).get('_resolved_updates',[]):
        result=pixel_library(result,update)
    return result


