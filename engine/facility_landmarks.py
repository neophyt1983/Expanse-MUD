"""Explicit visual landmarks; never implies indoor space or shelter."""
KINDS={'lodging','forge','workshop','market','residence'}
LABELS={'residence':'Residential sign','lodging':'Lodging sign','forge':'Smithy sign','workshop':'Workshop sign','market':'Open market stalls'}
def descriptor(room):
    value=room.get('facility_landmark')
    return {'kind':value,'label':LABELS[value]} if isinstance(value,str) and value in KINDS else None

def validate(data):
    return [str(r.get('id'))+': facility_landmark must be blank or lodging, forge, workshop, market, residence' for r in data.get('room',[]) if 'facility_landmark' in r and r['facility_landmark'] not in ('',*KINDS)]
