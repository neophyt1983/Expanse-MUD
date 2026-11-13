"""Appearance palettes are world data. Only the owning character selects a style."""
import hashlib

HAIR = ['brown','black','auburn','blond','gray','white']
PALETTES = dict(skin_color=['fair','tan','olive','brown','dark','pale','gray','green','blue'],
                hair_color=HAIR+['silver','red','green','blue','purple'],
                hair_style=['short','braided','long','bald'], facial_hair=['none','beard','mustache'],
                stature=['average','short','tall'], build=['average','slim','broad'], ears=['round','pointed'])
RACES = {
    'human': ('average','round',['fair','tan','olive','brown','dark','pale']),
    'dwarf': ('short','round',['tan','fair','brown','dark','olive']),
    'elf': ('tall','pointed',['olive','brown','fair','dark','pale']),
    'halfling': ('short','round',['brown','tan','olive','fair','dark']),
    'gnome': ('short','pointed',['fair','tan','brown','olive','dark']),
    'zombie': ('average','round',['gray','olive','pale','green','blue','brown']),
}
ACCENTS = {
    'mage':('Star embroidery','collar','purple'), 'hunter':('Trail binding','cuffs','green'),
    'fighter':('Company braid','sash','red'),'thief':('Shadow stitching','collar','gray'),
    'cleric':('Votive band','sash','gold'),'bard':('Ribbon cuffs','cuffs','purple'),
    'druid':('Leaf edging','collar','green'),'artificer':('Copper stitching','cuffs','orange'),
    'sx_artificer':('Workshop braid','sash','orange'),'sx_prospector':('Survey binding','cuffs','yellow'),
    'sx_field_surgeon':('Linen crossband','sash','white'),'sx_envoy':('Court piping','collar','blue'),
    'sx_quartermaster':('Stores braid','sash','brown'),'sx_runesmith':('Runic edge','cuffs','silver'),
    'sx_cartographer':('Meridian piping','collar','blue'),'sx_warden':('Watch binding','sash','green'),
}
COLORS = set(HAIR) | {'white','silver','gold','red','yellow','orange','green','purple','blue','pink'}

def race_choices(row):
    family = row.get('sprite_family', row.get('id',''))
    stature, ears, skin = RACES.get(family, RACES['human'])
    values = {**PALETTES, 'skin_color':skin, 'stature':list(dict.fromkeys([stature, 'average'])),
              'ears':[ears], 'build':['broad','average','slim'] if family=='dwarf' else PALETTES['build']}
    if family in {'human','zombie'}:
        values['stature'] = list(PALETTES['stature'])
    custom=row.get('appearance_choices')
    for key, choices in (custom if isinstance(custom,dict) else {}).items():
        if key in PALETTES and isinstance(choices,list):
            valid = [v for v in choices if v in PALETTES[key]]
            if valid: values[key] = list(dict.fromkeys(valid))
    return values

def class_accents(row):
    default=ACCENTS.get(row.get('id'),('Guild braid','sash','silver'))
    source=row.get('appearance_styles',[dict(zip(('name','mark','color'),default))])
    if not isinstance(source,list):return []
    return [accent for accent in source if isinstance(accent,dict) and isinstance(accent.get('name'),str)
            and 0<len(accent['name'])<=60 and accent.get('mark') in ('sash','collar','cuffs') and accent.get('color') in COLORS]

def choices(race,cls):
    family=race.get('sprite_family',race.get('id','human'))
    return dict(traits=race_choices(race), accents=class_accents(cls), family=family if family in RACES else 'human')

def validate(selection, options):
    if not isinstance(selection,dict) or len(selection)>len(PALETTES)+1:
        raise ValueError('Choose the appearance values from the available options.')
    traits=options['traits']
    for key,value in selection.items():
        allowed = ['Plain']+[a['name'] for a in options['accents']] if key=='accent' else traits.get(key,[])
        if not isinstance(value,str) or value not in allowed:
            raise ValueError('Unavailable appearance choice for '+str(key)[:40]+'.')
    return dict(selection)

def selected_accent(style, options):
    return next((a for a in options['accents'] if a['name']==style.get('accent')),None)

def variant(seed, *keys):
    return int.from_bytes(hashlib.blake2s('|'.join(map(str,(seed,*keys))).encode(),digest_size=4).digest(),'big')


def validate_world(data):
    issues=[]
    for r in data.get('race',[]):
        opts=r.get('appearance_choices',{})
        if not isinstance(opts,dict) or any(k not in PALETTES or not isinstance(v,list) or not v
                or any(not isinstance(x,str) or x not in PALETTES[k] for x in v) for k,v in opts.items()):
            issues.append(r['id']+' has an invalid appearance palette.')
    for c in data.get('class',[]):
        styles=c.get('appearance_styles',[])
        if not isinstance(styles,list) or len(styles)!=len(class_accents(c)) and 'appearance_styles' in c:
            issues.append(c['id']+' has an invalid class clothing detail.')
        elif len({s['name'] for s in styles})<len(styles):
            issues.append(c['id']+' has duplicate class detail names.')
    return issues
