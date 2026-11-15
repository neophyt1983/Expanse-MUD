"""Portable declarative world rules and read-only access to a world's media."""
import base64
import json
import os
from pathlib import Path, PurePosixPath
import stat

CONTENT_TYPES = {'.ogg':'audio/ogg','.mp3':'audio/mpeg','.wav':'audio/wav',
                 '.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg',
                 '.webp':'image/webp','.gif':'image/gif','.json':'application/json'}
CHUNK = 96 * 1024

def media(name):
    if not isinstance(name,str) or len(name)>512 or '\\' in name or any(ord(c)<32 for c in name):
        return False
    parts=name.split('/')
    return (2<=len(parts)<=8 and parts[0] in ('images','assets') and
            all(p not in ('','.','..') for p in parts) and
            PurePosixPath(name).suffix.lower() in CONTENT_TYPES and
            (parts[0]=='assets' or CONTENT_TYPES[PurePosixPath(name).suffix.lower()].startswith('image/')))

def rules(folder,rooms,npcs=None):
    path=Path(folder)/'world-rules.json'
    if not path.is_file():return {}
    data=json.loads(path.read_bytes())
    if not isinstance(data,dict):raise ValueError('world-rules.json must be an object')
    regions=data.get('regions',[])
    if not isinstance(regions,list) or len(regions)>128:raise ValueError('Invalid expedition regions')
    prefixes=set()
    for region in regions:
        if not isinstance(region,dict) or region.get('gate') not in rooms:raise ValueError('Expedition entry is missing')
        for key in ('name','guide','terrain','landmark','relic','memory','prefix','summoner','threat','trail_note'):
            if not isinstance(region.get(key),str):raise ValueError('Expedition needs '+key)
        if (not isinstance(region.get('hazards'),list) or len(region['hazards'])!=3 or
            not all(isinstance(v,str) for v in region['hazards']) or len(region.get('weather',[]))!=3 or
            not all(isinstance(v,dict) for v in region['weather']) or not isinstance(region.get('sectors'),dict) or
            not isinstance(region.get('origin'),list) or len(region['origin'])!=3 or not all(type(x) is int for x in region['origin']) or
            not all(k in region for k in ('latitude','elevation','underground'))):
            raise ValueError('Invalid expedition settings')
        palette=region.get('palette',[]);grid=region.get('grid',[])
        if not isinstance(palette,list) or not 1<=len(palette)<=26 or not all(isinstance(t,str) for t in palette):
            raise ValueError('Invalid terrain palette')
        symbols=set(chr(65+i) for i in range(len(palette)))|{'.'}
        if not isinstance(grid,list) or not 1<=len(grid)<=2048 or not isinstance(grid[0],str) or not 1<=len(grid[0])<=2048 or any(not isinstance(row,str) or len(row)!=len(grid[0]) or set(row)-symbols for row in grid):
            raise ValueError('Invalid terrain layout')
        if (not region['prefix'] or region['prefix'] in prefixes or type(region.get('trail_y')) is not int or not 0<=region['trail_y']<len(grid) or type(region.get('landmark_x')) is not int or not 0<=region['landmark_x']<len(grid[0]) or type(region.get('hazard_damage')) is not int or region['hazard_damage']<0):
            raise ValueError('Invalid region coordinates, damage or identifier')
        prefixes.add(region['prefix'])
        for key,row in region['sectors'].items():
            if not isinstance(row,dict) or not all(isinstance(row.get(k),str) and row[k] for k in ('id','name','spawn_room')) or not all(type(row.get(k)) is int for k in ('hp','attack','defense')) or not isinstance(row.get('social_profile'),dict):
                raise ValueError('Invalid expedition resident')
            try:
                prefix,x,y=row['spawn_room'].rsplit('_',2);x,y=int(x),int(y)
                if prefix!=region['prefix'] or not 0<=x<len(grid[0]) or not 0<=y<len(grid) or grid[y][x]=='.' or key!=f'{x//16}/{y//16}':raise ValueError()
            except ValueError:raise ValueError('Invalid sector spawn point') from None
    if 'ward' in data:
        ward=data['ward']
        if not isinstance(ward,dict) or ward.get('gate') not in rooms or not isinstance(ward.get('prefix'),str) or not ward['prefix'] or not all(ward['prefix']+n in rooms for n in ('court','yard','house','refuge','quay','bridge','garden','rooms','ale')):
            raise ValueError('District references missing rooms')
        if not isinstance(ward.get('waiting'),list) or not isinstance(ward.get('activities'),dict) or any(len(ward['activities'].get(str(k),[]))!=3 for k in (1,2,5,7,8,11)):
            raise ValueError('Invalid district schedule')
    from engine import regional_rules
    regional_rules.validate(data, rooms, npcs)
    return data

def asset_packet(folder,name,offset):
    result={'type':'world_asset','name':name,'offset':offset}
    if not media(name) or type(offset) is not int or not 0<=offset<=32*1024*1024:
        return {**result,'missing':True}
    root=Path(folder)
    path=root/name
    if any(p.is_symlink() for p in [path,*path.parents] if p!=root and root in p.parents):
        return {**result,'missing':True}
    try:
        with path.open('rb') as stream:
            st=os.fstat(stream.fileno())
            if not stat.S_ISREG(st.st_mode) or not 0<=offset<=st.st_size<=32*1024*1024:return {**result,'missing':True}
            stream.seek(offset);raw=stream.read(CHUNK)
            return {**result,'size':st.st_size,'mime':CONTENT_TYPES[path.suffix.lower()],'data':base64.b64encode(raw).decode('ascii')}
    except OSError:return {**result,'missing':True}
