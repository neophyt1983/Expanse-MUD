"""Deterministic regional climate; geography is authored, not inferred from names."""
import hashlib,math
from engine import worldtime

DEFAULT = dict(latitude=35.0,elevation_m=100,coastal=False,rain_shadow=False,
               terrain='plains',sheltered=False,controlled_growing=False)
TERRAINS=('plains','forest','rainforest','desert','mountain','valley','wetland','coast','ocean','settlement','cave','snow')


def conditions(w,room,minute=None):
    from engine import living
    minute=living.state(w)['minute'] if minute is None else minute
    cfg={**DEFAULT,**living.details(w,room).get('climate',{})}
    lat=cfg['latitude'];abs_lat=abs(lat);alt=cfg['elevation_m'];terrain=cfg['terrain']
    season=worldtime.season(minute,lat)
    amplitude=1 if abs_lat<15 else 4+abs_lat/8
    if cfg['coastal']:amplitude*=.55
    seasonal={'spring':0,'summer':1,'autumn':0,'winter':-1}[season]*amplitude
    temperature=29-.48*abs_lat-alt*.006+seasonal
    if cfg['coastal'] and abs_lat>=30:temperature+=4
    if terrain=='desert':temperature+=5
    if terrain=='valley':temperature-=2
    moisture=.5
    if terrain in ('forest','rainforest','wetland'):moisture={'forest':.65,'rainforest':.92,'wetland':.85}[terrain]
    if cfg['coastal']:moisture=max(moisture,.82 if abs_lat>=25 else .7)
    if cfg['rain_shadow'] or terrain=='desert':moisture=.12
    if terrain in ('mountain','valley'):moisture=max(.08,moisture-alt/7000-.15)
    biodiversity='low' if terrain in ('desert','plains','mountain') or temperature<0 else 'high' if terrain in ('rainforest','wetland','forest') else 'moderate'
    day=int(minute)//worldtime.MINUTES_PER_DAY
    roll=int(hashlib.sha256(f'{room}:{day}'.encode()).hexdigest()[:8],16)/0xffffffff
    weather=('snow' if temperature<=0 else 'rain') if roll<moisture*.55 else 'overcast' if roll<moisture else 'clear'
    if terrain=='desert' and roll>.95:weather='dust storm'
    if terrain=='ocean' and roll<.12:weather='rough seas'
    daylight=worldtime.date(minute,w.metadata.get('sunrise_minute',375))['daylight']
    if not daylight:temperature-=2 if cfg['coastal'] else 7 if terrain=='desert' else 4
    if cfg['sheltered']:weather='sheltered';temperature=max(10,temperature)
    travel=1+(terrain in ('mountain','valley','desert'))+(weather in ('snow','dust storm','rough seas'))
    result=dict(**cfg,season=season,temperature_c=round(temperature,1),moisture=round(moisture,2),biodiversity=biodiversity,weather=weather,daylight=daylight,travel_minutes=int(travel))
    from engine import regional_weather
    # The richer opt-in model resolves precipitation after the final night temperature.
    from engine import wildlands
    position=wildlands.cell(w,room) if wildlands.enabled(w) else None
    if position:return wildlands.weather(w,position[0],minute,result)
    return regional_weather.overlay(w,room,result,minute)


def describe(w,room):
    c=conditions(w,room)
    return f'{c["season"].title()} | {c["weather"]} | {c["temperature_c"]} °C | {c["terrain"]} | biodiversity: {c["biodiversity"]}'


def validate(data,meta):
    issues=[]
    sunrise=meta.get('sunrise_minute',375)
    if type(sunrise) is not int or not 0<=sunrise<worldtime.MINUTES_PER_DAY:issues.append('sunrise_minute must be 0–1499; daylight lasts exactly 750 minutes')
    if 'start_minute' in meta and (type(meta['start_minute']) is not int or not 0<=meta['start_minute']<worldtime.MINUTES_PER_DAY):issues.append('start_minute must be 0–1499 for a fresh world')
    for room in data.get('room',[]):
        raw=room.get('climate',{})
        if not isinstance(raw,dict):issues.append(room['id']+': climate must be an object');continue
        c={**DEFAULT,**raw}
        for key,low,high in [('latitude',-90,90),('elevation_m',-1000,12000)]:
            if type(c[key]) not in (int,float) or not math.isfinite(c[key]) or not low<=c[key]<=high:issues.append(room['id']+': invalid '+key)
        for key in ('coastal','rain_shadow','sheltered','controlled_growing'):
            if type(c[key]) is not bool:issues.append(room['id']+': invalid '+key)
        if c['terrain'] not in TERRAINS:issues.append(room['id']+': invalid terrain')
    return issues
