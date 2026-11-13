"""Bounded, fail-closed template snapshots for new-world history generation.

Definitions remain Creator-editable; recognized sidecars/media are copied without
re-encoding. Timestamped backups of recognized root JSON definitions stay in the source only.
Other unsupported entries and symlinks are errors, never silently omitted.
"""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import os
import re
from pathlib import Path,PurePosixPath
import stat
from engine.world_history import HistoryError

MAX_FILE=32*1024*1024
MAX_TOTAL=128*1024*1024
MAX_FILES=2048
JSON_SIDECARS={'creator-packs.json','world-rules.json','creator-tax-plans.json','population.json','shortcuts.json','pixel-art-library.json'}
DERIVED={'history.json','history-rules.json','manifest.json','chronicles.json'}
IMAGE_TYPES={'.png':'PNG','.jpg':'JPEG','.jpeg':'JPEG','.webp':'WEBP','.gif':'GIF'}


def _json(raw,label):
    def bad(value):raise ValueError('Nonfinite JSON constant: '+value)
    try:return json.loads(raw.decode('utf-8'),parse_constant=bad)
    except (ValueError,UnicodeError,RecursionError) as exc:raise HistoryError('Invalid '+label+': '+str(exc)) from exc


def _allowed(name):
    from editor.cli import FILE_MAP
    p=PurePosixPath(name)
    if p.is_absolute() or '\\' in name or any(x in ('','.', '..') for x in name.split('/')):
        raise HistoryError('Invalid template path: '+name)
    if len(p.parts)==1:
        if name in set(FILE_MAP.values())|{'metadata.json'}|JSON_SIDECARS|DERIVED:return
    else:
        from engine.world_package import media
        if media(name):return
    raise HistoryError('Unsupported template entry: '+name+'. Nothing was published; add a preservation handler first.')


def _source_backup(name):
    """Editor backups are recovery files, not authored world inputs.

    Match only the established editor timestamp convention and known root JSON
    definitions. Do not broaden this into ignoring arbitrary unknown content.
    """
    from editor.cli import FILE_MAP
    match=re.fullmatch(r'([^/\\]+\.json)\.bak-[0-9]{8}-[0-9]{6}',name)
    return bool(match and match.group(1) in set(FILE_MAP.values())|{'metadata.json'}|JSON_SIDECARS|DERIVED)


def _static_container(raw,extension):
    # Qt may report APNG as one PNG frame. Inspect container animation markers
    # before decoding so unsupported animation cannot bypass the static contract.
    if extension=='.png' and raw.startswith(b'\x89PNG\r\n\x1a\n'):
        offset=8;chunks=0
        while offset+12<=len(raw):
            chunks+=1
            if chunks>4096:raise ValueError('PNG chunk budget exceeded')
            size=int.from_bytes(raw[offset:offset+4],'big');kind=raw[offset+4:offset+8]
            end=offset+12+size
            if end>len(raw):raise ValueError('Truncated PNG chunk')
            if kind in (b'acTL',b'fcTL',b'fdAT'):raise ValueError('Animated PNG is unsupported')
            offset=end
            if kind==b'IEND':break
    if extension=='.webp' and raw.startswith(b'RIFF'):
        offset=12;chunks=0
        while offset+8<=len(raw):
            chunks+=1
            if chunks>4096:raise ValueError('WebP chunk budget exceeded')
            kind=raw[offset:offset+4];size=int.from_bytes(raw[offset+4:offset+8],'little')
            end=offset+8+size
            if end>len(raw):raise ValueError('Truncated WebP chunk')
            if kind in (b'ANIM',b'ANMF') or (kind==b'VP8X' and size and raw[offset+8]&2):raise ValueError('Animated WebP is unsupported')
            offset=end+(size%2)


def _validate_file(name,raw):
    _allowed(name)
    if not isinstance(raw,bytes) or len(raw)>MAX_FILE:raise HistoryError('Template file exceeds size limit: '+name)
    if name.endswith('.json'):
        obj=_json(raw,name)
        if name=='shortcuts.json' and (not isinstance(obj,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in obj.items())):
            raise HistoryError('shortcuts.json must be a string-to-string object')
        if name in JSON_SIDECARS|{'metadata.json'}|DERIVED and not isinstance(obj,dict):raise HistoryError(name+' must be an object')
    elif PurePosixPath(name).suffix.lower() in ('.ogg','.mp3','.wav'):
        suffix=PurePosixPath(name).suffix.lower()
        valid=(raw.startswith(b'OggS') if suffix=='.ogg' else raw.startswith(b'RIFF') and raw[8:12]==b'WAVE' if suffix=='.wav' else raw.startswith(b'ID3') or len(raw)>=2 and raw[0]==255 and raw[1]&224==224)
        if not valid:raise HistoryError('Invalid audio asset '+name)
    else:
        try:
            _static_container(raw,PurePosixPath(name).suffix.lower())
            from PIL import Image
            with Image.open(BytesIO(raw)) as image:
                if image.format != IMAGE_TYPES[PurePosixPath(name).suffix.lower()] or image.width * image.height > 16777216 or getattr(image,'n_frames',1) != 1:
                    raise HistoryError('Invalid image type, dimensions or frame count: '+name)
                image.verify()
            with Image.open(BytesIO(raw)) as image:
                image.load()
        except Exception as exc:raise HistoryError('Invalid image asset '+name+': '+str(exc)) from exc



def signature(files,directories=()):
    if not isinstance(files,dict) or len(files)>MAX_FILES:raise HistoryError('Template file-count limit exceeded')
    if not isinstance(directories,(list,tuple)) or len(directories)>MAX_FILES or len(set(directories))!=len(directories):raise HistoryError('Invalid template directory list')
    total=0;digest=sha256()
    for name in sorted(directories):
        if not isinstance(name,str) or '\\' in name or any(p in ('','.','..') for p in name.split('/')) or not (name in ('assets','images') or name.startswith(('assets/','images/'))) or len(name.split('/'))>8:
            raise HistoryError('Invalid asset directory')
        digest.update(b'directory:');digest.update(name.encode());digest.update(b'\0')
    for name,raw in sorted(files.items()):
        if not isinstance(name,str):raise HistoryError('Invalid template filename')
        _validate_file(name,raw);total+=len(raw)
        if total>MAX_TOTAL:raise HistoryError('Template byte budget exceeded')
        digest.update(name.encode());digest.update(b'\0');digest.update(sha256(raw).digest())
    return digest.hexdigest()


def snapshot(root,*,population_override=None):
    root=Path(root)
    if root.is_symlink():raise HistoryError('Template root must not be a symlink')
    files={};directories=[];total=0;entries=0
    # Directory descriptors and O_NOFOLLOW prevent symlink swaps from escaping
    # the source tree while individual entries are read.
    def walk(fd,prefix='',depth=0):
        nonlocal total,entries
        if depth>7:raise HistoryError('Template directory depth exceeded')
        names=[]
        with os.scandir(fd) as entries_iter:
            for entry in entries_iter:
                if len(names)+entries>=MAX_FILES:raise HistoryError('Template entry budget exceeded')
                names.append(entry.name)
        for name in sorted(names):
            entries+=1
            if entries>MAX_FILES:raise HistoryError('Template entry budget exceeded')
            relative=prefix+name
            st=os.stat(name,dir_fd=fd,follow_symlinks=False)
            if stat.S_ISLNK(st.st_mode):raise HistoryError('Template symlink refused: '+relative)
            if stat.S_ISDIR(st.st_mode):
                if not (relative in ('assets','images') or relative.startswith(('assets/','images/'))):raise HistoryError('Unsupported template directory: '+relative)
                directories.append(relative)
                child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                try:walk(child,relative+'/',depth+1)
                finally:os.close(child)
            elif stat.S_ISREG(st.st_mode):
                # Do not read, modify, copy, or delete recovery backups. They
                # still count against the traversal entry budget above.
                if _source_backup(relative):continue
                _allowed(relative)
                if len(files)>=MAX_FILES or st.st_size>MAX_FILE or total+st.st_size>MAX_TOTAL:raise HistoryError('Template size/count budget exceeded')
                handle=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
                if not stat.S_ISREG(os.fstat(handle).st_mode):
                    os.close(handle);raise HistoryError("Template file changed type")
                try:
                    with os.fdopen(handle,'rb') as stream:raw=stream.read(MAX_FILE+1)
                except Exception:raise
                _validate_file(relative,raw);total+=len(raw)
                if total>MAX_TOTAL:raise HistoryError('Template byte budget exceeded')
                files[relative]=raw
            else:raise HistoryError('Unsupported non-regular template entry: '+relative)
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:walk(fd)
    finally:os.close(fd)
    source_signature=signature(files,directories)
    if population_override is not None:
        raw=json.dumps(deepcopy(population_override),allow_nan=False).encode()
        _validate_file('population.json',raw);files['population.json']=raw
    return {'files':files,'directories':directories,'source_signature':source_signature,'signature':signature(files,directories)}


def extras(bundle):
    if bundle is None:return {}
    if not isinstance(bundle,dict) or signature(bundle.get('files'),bundle.get('directories',[]))!=bundle.get('signature'):
        raise HistoryError('Template snapshot changed or is invalid')
    return {name:raw for name,raw in bundle['files'].items() if name in JSON_SIDECARS or name.startswith(('assets/','images/'))}


def validate_staged(directory,data,extra_files):
    from engine.world_package import rules
    rules(directory,{r['id'] for r in data.get('room',[])})
    if 'pixel-art-library.json' not in extra_files:return
    try:from engine import pixel_art
    except ImportError as exc:raise HistoryError('Pixel Studio template requires the compatible Pixel Studio engine; nothing published') from exc
    library=pixel_art.load(directory)
    kinds={'rooms':'room','npcs':'npc','races':'race','items':'item'}
    ids={k:{r['id'] for r in data.get(v,[])} for k,v in kinds.items()}
    for key,asset_id in library['bindings'].items():
        kind,identity=key.split(':',1);doc=library['assets'][asset_id]
        if kind in ('races','items'):
            suffix=':'+doc['rig']
            if not identity.endswith(suffix):raise HistoryError('Invalid Pixel Studio rig binding')
            identity=identity[:-len(suffix)]
        if identity not in ids[kind]:raise HistoryError('Pixel Studio binding references missing '+kind+': '+identity)
