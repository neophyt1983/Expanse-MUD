from engine import gazette

def area_names(meta, rows):
    names={('place:'+r['name'],r['name']) for r in meta.get('press_editions',[]) if r.get('name')}
    names.update(('region:'+r['world_region'],r['world_region']) for r in rows if r.get('world_region'))
    return dict(sorted(names,key=lambda pair:(pair[1].casefold(),pair[0])))


def selected(w,rid):
    cfg=w.metadata.get('soundtrack',{})
    if not isinstance(cfg,dict):cfg={}
    track=cfg.get('world','silence')
    overrides=cfg.get('areas',{})
    if isinstance(overrides,dict) and overrides:
        room=w.rooms[rid];detail=getattr(w,'room_details',{}).get(rid,{})
        locality=gazette.local(w,detail.get('street_front',rid))
        country=next((r for r in gazette.editions(w) if r.get('kind')=='country' and r.get('group')==room.group),{})
        for key in ('place:'+str((locality or {}).get('name','')),'region:'+str(detail.get('world_region','')),'place:'+str(country.get('name',''))):
            if key in overrides:
                track=overrides[key];break
    return track if isinstance(track,str) and track in w.metadata.get('music_tracks',{}) else 'silence'


VENUES={'home':'House or rented home','tavern':'Tavern or inn','civic':'Government building or palace','school':'School'}


def purpose(w,rid):
    row=getattr(w,'room_details',{}).get(rid,{})
    if (row.get('street_front') or rid in getattr(w,'_street_origins',{})):return ''
    def classify(r):
        explicit=r.get('music_venue')
        if explicit in VENUES:return explicit
        facilities=set(r.get('facilities',[]))
        if r.get('property_unit_kind') in ('house','rental') or 'residential' in facilities:return 'home'
        if facilities & {'school','academy','classroom'}:return 'school'
        if facilities & {'inn','tavern'}:return 'tavern'
        name=r.get('name','').casefold()
        if any(n in name for n in ('palace','council chamber','royal hall','town hall','city hall','embassy','throne room','courthouse','senate','council hall')):return 'civic'
        if any(n in name for n in ('school','academy','classroom','lecture hall')):return 'school'
        if any(n in name for n in ('tavern',' inn','taproom')):return 'tavern'
        if name.endswith((' cottage',' dwelling',' residence',' home',' farmhouse',' apartment')):return 'home'
        return ''
    from engine.visual_mapping import room_style
    compiled=getattr(w,'_compiled_map',None)
    record=compiled[0].get(rid,row) if compiled else row
    if room_style(record)[0]!='building':return ''
    if row.get('music_venue') in VENUES:return row['music_venue']
    building=(record.get('_visual_building') or {}).get('id')
    definition=getattr(w,'buildings',{}).get(building,{})
    if definition.get('music_venue') in VENUES:return definition['music_venue']
    local=classify(row)
    if local:return local
    if building:
        for member in definition.get('rooms',[]):
            local=classify(getattr(w,'room_details',{}).get(member,{}))
            if local:return local
    return ''


def _selection(w,player):
    """Use the settlement's public affiliation and the viewer's earned standing."""
    from hashlib import sha256
    from types import SimpleNamespace
    from engine import society
    rid=player.location
    detail=getattr(w,'room_details',{}).get(rid,{})
    source=detail.get('property_parcel_id') or detail.get('street_front') or rid
    source=getattr(w,'room_details',{}).get(source,{}).get('property_parcel_id') or source
    place=gazette.local(w,source)
    track=selected(w,source)
    config=w.metadata.get('soundtrack',{})
    venue=purpose(w,rid)
    theme=(config.get('venues',{}) if isinstance(config,dict) else {}).get(venue,venue)
    if theme not in w.metadata.get('music_tracks',{}):theme=''
    if not place or place.get('kind') not in ('city','town'):
        return dict(track=(theme or track) if track!='silence' else track,area='',mood='neutral',transpose=0,venue=venue)


    group=place.get('group')
    civic=SimpleNamespace(group_id=group,is_player=False,reputation={})
    score=society.friendliness(w,player,civic) if group and player.group_id else 50
    mood='hostile' if score<25 else 'wary' if score<50 else 'neutral' if score<60 else 'welcoming'
    # Distinct city themes and keys also work in existing worlds with no overrides.
    digest=sha256(place['name'].encode()).digest()
    config=w.metadata.get('soundtrack',{})
    if track!='silence' and theme:track=theme
    return dict(track=track,area=place['name'],mood=mood,venue=venue,transpose=(-5,-3,-2,0,2,3,5)[digest[1]%7])


def cue(w,player):
    result = _selection(w,player)
    assets = w.metadata.get('audio_assets',{})
    track = result['track']
    files = assets.get('tracks',{}).get(track,{})
    result['file'] = files if isinstance(files,str) else files.get(result['mood'],files.get('neutral'))
    result['title'] = w.metadata.get('music_tracks',{}).get(track,'')
    result['arrival'] = assets.get('cues',{}).get(result.get('venue') or 'street')
    result['thunder'] = assets.get('thunder')
    return result
