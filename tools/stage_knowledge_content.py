#!/usr/bin/env python3
"""Compose bounded founding instruction and sourced literature into 1.9.16.

apply(data, metadata) accepts plural in-memory catalogs and returns a report.
The CLI copies the source into a new directory before writing. It never imports
into a live game, replenishes a saved shelf, or rewrites an older book's prose.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

PATCH='bounded_knowledge_literature_v1'
LIBRARIES=('fw_dawn_17','fw_hollow_17','lw_hearth_library','lw_reed_library',
           'lw_cinder_library','lw_glass_library','lw_pine_library','lw_star_library')
COMMON=(
    ('paper_ink','Paper, Ink and a Second Copy',('make_sx_paper','make_sx_ink'),
     'A written record needs a physical surface and a marking material. The two patterns below are common workshop instructions. '
     'The pattern travels readily; paper, ink and a practiced hand are still needed for each copy. '
     'When a page is copied, name the source. Ten copies of one account are ten surviving copies, not ten independent witnesses.'),
    ('woven_cloth','Flax into Cloth',('lw_cloth',),
     'The usefulness of cloth reaches farther than any single garment: a household needs something it can mend, fold and carry. '
     'This booklet preserves one weaving pattern. It does not promise that fiber is available in every settlement. '
     'A weaver should count the fiber already held before promising another length of cloth.'),
    ('smith_hammer','The Hammer’s Material Account',('lw_hammer',),
     'An everyday tool has a material history. A hammer begins with metal at the bench and the practiced hand that shapes it. '
     'This short manual records the local pattern and its material account. Practice with actual tools can improve the worker; '
     'the pattern records what must be set aside before work begins.'),
    ('bread','Bread for the Shared Table',('sx_make_bread',),
     'This bread pattern is published for broad use. A shared recipe can travel farther than its first kitchen, '
     'while flour, water, fuel and working time still have to come from somewhere. This edition gives the recorded '
     'batch account below; it does not turn a household’s private variations into common knowledge.'),
)
BIOGRAPHIES=(
    ('lw_hearth_ruler','lw_hearth_library','Elian: Petitions and the Road',
     'The sympathetic reading begins with the petitions. Food, roads and travelers’ safety are practical concerns; '
     'a reader may value a ruler who gives them attention. That favorable appraisal remains an appraisal, not a tally of completed improvements.',
     'The critical reading asks what attention achieved. Which petitions were answered, who waited, and which travelers never reached the clerk? '
     'Those records are not supplied here. A generous account of intentions cannot answer questions about results.'),
    ('lw_cinder_ruler','lw_cinder_library','Torven: A Crown under Question',
     'A defender can read the practical crown and the petition desk as signs of a working office. '
     'Roads and food give that defense a concrete subject: the ordinary needs of people who must live under decisions made above them.',
     'A critic can ask whether the same office protects its petitioners or expects obedience before listening. '
     'The surviving profile does not settle that question. This edition neither acquits the office of every abuse nor invents a crime for its ruler.'),
    ('lw_glass_ruler','lw_glass_library','Sahra: Reading a Court’s Promises',
     'An appreciative reader sees a court attending to provisions and journeys, rather than only ceremony. '
     'It is possible to admire that stated direction and still ask for evidence of the work that followed.',
     'A skeptical reader distinguishes a public description from the experience of people outside the court. '
     'Whose safety is counted, and whose account is absent? This biography preserves the question until a dated, attributable account can answer it.'),
)


def apply(data,metadata):
    if metadata.get('content_patches',{}).get(PATCH):return {'patch':PATCH,'already_applied':True}
    from engine import npc_backgrounds, publications, worldtime
    by={kind:{row['id']:row for row in data.setdefault(kind,[])} for kind in ('items','rooms','recipes','npcs')}
    missing=[ident for ident in LIBRARIES if ident not in by['rooms']]
    missing += [ident for ident in ('sx_paper','sx_ink') if ident not in by['items']]
    missing += [ident for _,_,ids,_ in COMMON for ident in ids if ident not in by['recipes']]
    missing += [ident for ident in ('rhome_oren','locks_lw_hearth_school_tutor',*(row[0] for row in BIOGRAPHIES)) if ident not in by['npcs']]
    if missing:raise ValueError('The supplied world lacks required literature sources: '+', '.join(missing))
    report={'patch':PATCH,'books':[],'copy_recipes':[],'placements':[],'shared_designs':[],
            'local_sources':[],'backgrounds':0,'preserved_publications':sum(bool(item.get('publication')) for item in by['items'].values()),
            'limits':['No invented birth/accession dates or moral verdicts for rulers.',
                      'Only real published recipe sources are indexed; unknown dangerous subjects remain absent or qualified.',
                      'New copies require paper, ink and an actually read text. No automatic reprinting.']}
    present=worldtime.initial_minute(metadata)
    source_world=SimpleNamespace(items=by['items'])

    def add(kind,row):
        if row['id'] in by[kind]:raise ValueError('Staging ID already exists: '+row['id'])
        by[kind][row['id']]=row;data[kind].append(row);return row

    def book(key,title,text,genre,places,*,author='locks_lw_hearth_school_tutor',recipes=(),claims=(),roots=(),links=(),sources=(),kind='nonfiction'):
        ident='knowledge119_'+key;copy_id='copy_'+ident
        editor=by['npcs'][author]
        info={'work_id':'work:'+ident,'edition_id':'edition:'+ident+':1','genre':genre,'author':editor['name'],
              'author_source':author,'kind':kind,'original_era':'individual','original_minute':present,'edition_minute':present,
              'evidence_roots':list(roots) or ['work:'+ident],'claims':list(claims)}
        if links:info['derives_from']=list(links)
        item={'id':ident,'name':title,'type':'book','value':6,'weight':1,'location':places[0],
              'description':'A modestly bound '+genre.lower()+' booklet, with its compiler and sources named inside.',
              'read_text':title+'\nCompiled by '+editor['name']+'\n\n'+text,
              'publication':info,'knowledge':{'recipes':list(dict.fromkeys([*recipes,copy_id]))},
              'historical_sources':list(sources),'creation_method':'Authored staged edition; each later copy consumes real paper and ink.'}
        add('items',item)
        add('recipes',{'id':copy_id,'name':'Copy '+title,'kind':'crafting','station':'scriptorium','minutes':12,
                       'ingredients':{'sx_paper':2,'sx_ink':1},'outputs':{ident:1},'location':places[0],
                       'knowledge_scope':'private','requires_reading':[ident],
                       'description':'Copy a known text from reading notes, using fresh paper and ink for each volume.',
                       'creation_method':'Finite scriptorium copying from an attributed reading source.'})
        for room_id in dict.fromkeys(places):
            by['rooms'][room_id].setdefault('items',[]).append(ident)
            report['placements'].append({'item':ident,'room':room_id,'quantity':1})
        report['books'].append({'id':ident,'name':title,'genre':genre,'copies':len(set(places))})
        report['copy_recipes'].append(copy_id)
        return item

    def pattern(recipe_id):
        recipe=by['recipes'][recipe_id]
        def quantities(table):return ', '.join(str(count)+' × '+by['items'][ident]['name'] for ident,count in table.items())
        if any(ident not in by['items'] for ident in (*recipe['ingredients'],*recipe['outputs'])):
            raise ValueError('A printed pattern refers to missing materials: '+recipe_id)
        return (recipe['name']+'\nMaterials: '+quantities(recipe['ingredients'])+'.\nResult: '+quantities(recipe['outputs'])+
                '.\nStation: '+recipe.get('station','hand')+'. Recorded working time: '+str(recipe.get('minutes',1))+' minutes.')

    for key,title,recipes,intro in COMMON:
        for ident in recipes:
            if by['recipes'][ident].get('prerequisites') or by['recipes'][ident].get('knowledge_scope')=='private':
                raise ValueError('Do not publish a gated/private pattern as common technology: '+ident)
            by['recipes'][ident]['knowledge_scope']='public';report['shared_designs'].append(ident)
        book(key,title,intro+'\n\n'+'\n\n'.join(pattern(ident) for ident in recipes),
             'Common practical technology' if key!='bread' else 'Shared cookery',LIBRARIES,
             author='rhome_oren' if key!='bread' else 'locks_lw_hearth_school_tutor',recipes=recipes,
             roots=['pattern:'+ident for ident in recipes],
             sources=[{'catalog':'recipes.json','id':ident} for ident in recipes])

    # A regional note may only select designs already present in an actual
    # local cookbook. It cannot enumerate remote recipes from the world table.
    for room_id in LIBRARIES:
        candidates=[]
        for iid in by['rooms'][room_id].get('items',[]):
            item=by['items'].get(iid,{})
            if item.get('publication',{}).get('genre')!='Food and cookery':continue
            actual=[rid for rid in item.get('knowledge',{}).get('recipes',[])
                    if rid in by['recipes'] and by['recipes'][rid].get('kind')=='cooking'
                    and not by['recipes'][rid].get('prerequisites') and by['recipes'][rid].get('knowledge_scope')!='private']
            if actual:candidates.append((item,actual[0]))
        if not candidates:continue
        origin,recipe_id=sorted(candidates,key=lambda row:row[0]['id'])[0]
        source=publications.source(source_world,origin['id'])
        title='Kitchen Notes from '+by['rooms'][room_id]['name']
        text=('This short selection comes from '+origin['name']+', a book physically filed in this library. '
              'Its presence here establishes a source for this recipe. It does not show that every resident knows it, '
              'or that the kitchen can supply the ingredients today. Other local variations remain with their own sources.\n\n'+
              pattern(recipe_id)+'\n\nThe copied passage keeps the earlier work’s attribution. Repetition does not independently verify its account.')
        book('kitchen_'+room_id,title,text,'Local cookery sources',[room_id],recipes=[recipe_id],
             roots=source['evidence_roots'],links=[{'edition_id':source['edition_id'],'relation':'quote','title':origin['name']}],
             sources=[{'catalog':'items.json','id':origin['id'],'field':'knowledge.recipes'}])
        report['local_sources'].append({'room':room_id,'source':origin['id'],'recipe':recipe_id})

    for person_id,room_id,title,sympathetic,critical in BIOGRAPHIES:
        person=by['npcs'][person_id];profile=person.get('description')
        if not isinstance(profile,str) or not profile.strip():raise ValueError('A biography needs its real public profile: '+person_id)
        root='public-profile:'+person_id
        claims=[{'id':'public-profile','text':profile,'certainty':'sourced','evidence_root':root,
                 'qualification':'This edition preserves a public profile, not a record that every petition succeeded.'},
                {'id':'favorable-reading','text':sympathetic,'certainty':'opinion','evidence_root':root},
                {'id':'critical-reading','text':critical,'certainty':'opinion','evidence_root':root}]
        text=('The surviving public profile\n'+profile+'\n\nA sympathetic reading\n'+sympathetic+
              '\n\nA critical reading\n'+critical+'\n\nLimits of this biography\n'
              'The source does not supply a birth date, accession date, complete childhood or a record of every decision. '
              'Those gaps remain. Readers may judge the office differently; neither praise nor suspicion is presented as an observed event. '
              'A later edition may add a dated account or correct a claim while retaining this earlier text.')
        book('life_'+person_id,title,text,'Biography and civic criticism',[room_id],claims=claims,roots=[root],
             sources=[{'catalog':'npcs.json','id':person_id,'field':'description'}])

    # Poetry/fiction are attributed works, not automatic evidence for places or
    # incidents named within them. Index only volumes physically on each shelf.
    for room_id in LIBRARIES:
        poems=[by['items'][iid] for iid in by['rooms'][room_id].get('items',[])
               if iid in by['items'] and by['items'][iid].get('publication',{}).get('genre')=='Verse and performance'][:3]
        if not poems:continue
        lines=['A poem can preserve a voice without establishing that its imagined incident occurred. '
               'The works listed here are on this shelf. Read the complete poem to hear its speaker in context.']
        for poem in poems:lines.append(poem['name']+' — '+poem['publication']['author']+'.')
        lines.append('When a later poem borrows a line, keep the earlier attribution. When discussing a speaker’s feelings, '
                     'distinguish the voice in the poem from the feelings of the living author or performer.')
        book('verse_index_'+room_id,'Voices on the Shelf — '+by['rooms'][room_id]['name'],'\n\n'.join(lines),
             'Poetry and reading',[room_id],roots=['work:'+poem['id'] for poem in poems],
             sources=[{'catalog':'items.json','id':poem['id'],'field':'publication'} for poem in poems])

    for person in data['npcs']:
        config=npc_backgrounds.parameters(person,by['rooms'])
        if config:
            person['background']=config;report['backgrounds']+=1
    problems=npc_backgrounds.validate({'npc':data['npcs'],'room':data['rooms'],'item':data['items']})
    problems+=publications.validate({'item':data['items']})
    if problems:raise ValueError('Invalid staged knowledge content: '+'; '.join(problems))
    metadata.setdefault('content_patches',{})[PATCH]={'version':1,'initial_books':len(report['placements']),
                                                   'works':len(report['books']),'new_founders':report['backgrounds']}
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    source,target=args.input.resolve(),args.output.resolve()
    if not source.is_dir() or target.exists() or target==source or target.is_relative_to(source):
        parser.error('Input must exist; output must be a new directory outside the input.')
    data={path.stem:json.loads(path.read_text()) for path in source.glob('*.json')
          if path.stem in ('items','rooms','recipes','npcs')}
    metadata=json.loads((source/'metadata.json').read_text())
    report=apply(data,metadata)
    shutil.copytree(source,target)
    for kind,rows in data.items():(target/(kind+'.json')).write_text(json.dumps(rows,ensure_ascii=False,separators=(',',':'))+'\n')
    (target/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,separators=(',',':'))+'\n')
    if args.report:args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
