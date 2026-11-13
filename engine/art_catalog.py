"""Use baked images only when the current creator artwork matches the catalogue."""
import hashlib
import json
def signature(row):
    traits={k:v for k,v in row.items() if k not in {'item_id','name','sprite_index','pixel_art','sprite_style'}}
    return hashlib.sha256(json.dumps(traits,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:20]

def bind(row,art):
    if isinstance(art,list) and len(art)==2 and type(art[0]) is int and art[1]==signature(row):
        row['sprite_index']=art[0]
        fields=('slot','layer','kind','shape','material','pattern','detail','silhouette','color','trim_color')
        row['sprite_style']='|'.join(row.get(k,'') for k in fields)
