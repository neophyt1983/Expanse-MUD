"""Creator defaults shared by new records and the browser field forms."""
DEFAULTS={
 'group':dict(relations={}),
 'room':dict(truce=False,gates={},facilities=[],resources=[],encounters=[],campable=False,environment='settlement',services={}),
 'item':dict(fuel=False,camp_tent=False,alcohol=0,cure_injury=0,cure_disease=0,raw_risk=0,enchant_attack=0,enchant_defense=0,learn_ability=''),
 'npc':dict(patrol_route=[],spawn_managed=False,combatant=False,schedule=[],aggressive=False,aggression_chance=.25,roaming=False,disposition='neutral',drops=[],tameable=False,tame_item='',companion_kind='pet',companion_attack=1,disease_chance=0),
 'quest':dict(category='local work',progress_scope='lifetime',arc_id='',region='',chapter=0,witnesses=[],talk_to=[],requires_character_flags={},prerequisites=[],exclusive_with=[],offer_room='',turn_in_room='',required_items={},kills={},visit_rooms=[],actions={},reward_gold=0,reward_items=[],repeatable=False,cooldown_minutes=1500,scope='character',consequence='',completion_text='',character_flags={},world_flags={},requires_world_flags={},world_effects=[],reputation={},**{'class':'','race':''}),
 'recipe':dict(name='',description='',prerequisites=[],ingredients={},outputs={},station='hand',kind='crafting',minutes=5),
 'resource':dict(name='',description='',yields={},tool='',renewal_minutes=60),
 'encounter':dict(name='',description='',members=[],chance=1,harvest={},harvest_source='',harvest_minutes=120,harvest_damage=0),
 'class':dict(starting_gold=25),
 'ability':dict(effect='damage',training_cost=15),
}

for _kind in ('room','item','npc','quest','building','group','race','class','sex','ability','recipe','resource','encounter'):
    DEFAULTS.setdefault(_kind,{})['location']=''
    DEFAULTS[_kind]['creation_method']=''
DEFAULTS['group']['diplomacy']={}
DEFAULTS['room']['workshop']={}
DEFAULTS['npc']['profession']=''
DEFAULTS['npc']['inventory']=[]
DEFAULTS['npc']['equipped']={}

DEFAULTS['interaction']=dict(name='',description='',location='',creation_method='',tool='',components={},interaction_effect='create',target_kind='item',power=0,outputs={},result_text='Combination completed.')
DEFAULTS['item']['requires_ammo']=''

from copy import deepcopy
from engine.relationships import CONTENT_PROFILE as PROFILE, POLICY
DEFAULTS["npc"]["social_profile"] = deepcopy(PROFILE)
DEFAULTS["npc"]["social_profile"].update(sentient=False, accepts=["companion"])
DEFAULTS["race"]["social_profile"] = deepcopy(PROFILE)
DEFAULTS["group"]["coupling_rules"] = deepcopy(POLICY)

from engine.mortality import LAWS, TRAFFIC
DEFAULTS['room']['laws']=deepcopy(LAWS)
DEFAULTS['npc']['traffic']=deepcopy(TRAFFIC)

DEFAULTS['species']=dict(name='',description='',location='',creation_method='',category='mammal',habitat='',sentient=False,diet=[],renewable_products={},remains={},breeding_seasons=['spring'],maturity_years=1,gestation_minutes=43200)
DEFAULTS['recipe']['requires_species']={}
DEFAULTS['resource']['species']=''
DEFAULTS['resource']['seasons']=[]

DEFAULTS['recipe']['requires_resources']=[]

DEFAULTS['recipe']['requires_carrier']=False

from engine.climate import DEFAULT as CLIMATE_DEFAULT
DEFAULTS['room']['climate']=deepcopy(CLIMATE_DEFAULT)
DEFAULTS['room']['requires_boat']=False
DEFAULTS['item']['boat']=False

DEFAULTS['resource']['temperature_min_c']=0
DEFAULTS['resource']['temperature_max_c']=45

from engine.social import PREFERENCES, QUEST_DEFAULT
from engine.companions import CARE
DEFAULTS['npc']['gift_preferences']=deepcopy(PREFERENCES)
DEFAULTS['npc']['companion_care']=deepcopy(CARE)
DEFAULTS['species']['companion_care']=deepcopy(CARE)
DEFAULTS['quest']['relationship_quest']=deepcopy(QUEST_DEFAULT)

DEFAULTS['npc'].update(name_mode='manual',title='',legacy_names=[],sex='')
DEFAULTS['group'].pop('name_pool',None)

DEFAULTS['npc']['interaction_pause_seconds']=15

from engine.needs_market import PROFILE as NEEDS_PROFILE
DEFAULTS['npc']['needs_profile']=deepcopy(NEEDS_PROFILE)
DEFAULTS['npc']['needs_starting_gold']=25
DEFAULTS['npc']['market']={'reserve_days':2,'target_stock':{}}
DEFAULTS['item']['need_effects']={}
DEFAULTS['item']['need_consumable']=False

DEFAULTS['species'].update(consumption='herbivore',prey_species=[],feeding_interval=180,forage_roaming=True,diet_notes='')
DEFAULTS['item'].update(food_origin='')

DEFAULTS['room'].update(property_plot={},land_uses={},port={},waterway={})
DEFAULTS['group']['development']={}

DEFAULTS['npc'].update(occupation='',work_room='',home_room='',leisure_room='',work_hours={},purchase_targets={},request_cooldown_minutes=180)
DEFAULTS['room']['opening_hours']={}
DEFAULTS['item']['salvage']={}

# Empty is an explicit opt-out; resources are never classified by their name.
DEFAULTS['resource']['visual']={}

# Optional explicit geological landforms, independent of climate terrain.
DEFAULTS['room']['geology']={}

# Optional rotating-market affiliation and shared depot settings.
DEFAULTS['npc'].update(market_id='',market_counter={})

# Empty objects leave legacy populations and species unchanged. These explicit
# author settings are not inferred from names, professions or animal maturity.
DEFAULTS['species'].update(life_stages={},population_health={})
DEFAULTS['npc']['population_profile']={}

# Optional explicit disclosures, taught only on successful interaction/acceptance.
for _knowledge_kind in ('npc','item','quest'):
    DEFAULTS[_knowledge_kind]['knowledge']={'items':[],'rooms':[],'recipes':[],'quests':[]}

# Optional authored ground surfaces; never add movement or reveal routes.
DEFAULTS['room']['route_surface']={}

DEFAULTS['room']['weather_shelter']=False

DEFAULTS['room']['weather_shelter_kind']='public_hall'
DEFAULTS['npc'].update(weather_refuge_preference='auto',weather_refuge_detour=2)

DEFAULTS['item']['light_source']=False

DEFAULTS['room']['facility_landmark']=''

# Optional 0–100 starting scores. Empty inherits stable role/place defaults.
DEFAULTS['npc']['life_profile']={}
DEFAULTS['room']['npc_life_defaults']={}

DEFAULTS['room']['locks']=[]
DEFAULTS['npc'].update(lockpicking=0,lock_keys=[],locksmith=False,lock_trainer=False,locksmith_fee=0,lock_lesson_fee=2,lock_work_start=0,lock_work_end=1500)
DEFAULTS['class']['lockpicking']=0
DEFAULTS['item']['lockpick_tool']=False

# Optional ability rules retain legacy behavior when absent.
DEFAULTS["ability"]["ability_rules"]={}
DEFAULTS["item"]["prepared_ability"]=""
DEFAULTS["item"]["teaches_abilities"]=[]
DEFAULTS["npc"]["teaches_abilities"]=[]
DEFAULTS["recipe"]["required_abilities"]=[]
DEFAULTS["ability"]["training_classes"]=[]

DEFAULTS["quest"]["escort"]={}
