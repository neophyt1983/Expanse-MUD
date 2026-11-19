#!/usr/bin/env python3
"""Compose the reviewed changes in a new world; never overwrite or import one."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))


def hashes(folder):
    return {str(path.relative_to(folder)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(folder.rglob('*')) if path.is_file()}


def stage(source, destination, archive=None):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if not source.is_dir() or destination.exists() or destination==source or destination.is_relative_to(source):
        raise ValueError('Choose an existing source and a new output directory outside it.')
    if archive and Path(archive).exists():raise ValueError('Choose a new archive path; no existing file will be replaced.')
    before=hashes(source)
    data={p.stem:json.loads(p.read_text()) for p in source.glob('*.json') if p.stem not in ('metadata','manifest')}
    metadata=json.loads((source/'metadata.json').read_text())
    from tools import author_animal_profiles,stage_guild_clinic_content,stage_art_content,stage_knowledge_content,stage_market_employment,audit_world_map
    report={'source':source.name,'source_files':before,'patches':{}}
    animal_data={'species':data['species'],'npc':data['npcs'],'room':data['rooms']}
    animal_patch=author_animal_profiles.build_patch(animal_data)
    updated=author_animal_profiles.apply_patch(animal_data,animal_patch)
    data.update(species=updated['species'],npcs=updated['npc'],rooms=updated['room'])
    report['patches']['animals']={'changes':len(animal_patch['changes']),
        'kinds':dict(Counter(row['path'][-1] for row in animal_patch['changes'])),'skipped':animal_patch['skipped']}
    for name,module in [('guilds_clinics',stage_guild_clinic_content),('art',stage_art_content),
                        ('knowledge',stage_knowledge_content),('market_work',stage_market_employment)]:
        report['patches'][name]=module.apply(data,metadata)
    report['patches']['map']=audit_world_map.repair_authored(data,metadata)
    report['map']=audit_world_map.audit(data,metadata)
    if report['map']['issues']:raise ValueError('Map audit failed: '+json.dumps(report['map']['issues'][:20]))
    metadata['name']='Expanse Wild Lands 1.9.16 Review 2026-11-19'
    metadata.setdefault('content_patches',{})['review_20261119']={
        'version':1,'status':'review','engine_branch':'feature/burglary-observation-20261119',
        'base_world':'Expanse Wild Lands 1.9.16','live_imported':False}
    manifest=json.loads((source/'manifest.json').read_text())
    manifest.update(name=metadata['name'],slug='expanse-wild-lands-review-20261119',review_only=True)
    manifest['counts']={key:len(data[key]) for key in manifest.get('counts',{}) if key in data}
    destination.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(source,destination)
    for key,value in {**data,'metadata':metadata,'manifest':manifest}.items():
        (destination/(key+'.json')).write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n')
    from engine import loader
    world=loader.build_world(destination);errors,warnings=loader.validate_world(world)
    report['validation']={'errors':errors,'warnings':warnings,'runtime_rooms_before_streets':len(world.rooms)}
    if errors:raise ValueError('Staging validation failed; separate output kept for inspection: '+str(errors[:20]))
    after=hashes(source)
    if after!=before:raise RuntimeError('Input changed during staging; review before using any output.')
    report['source_unchanged']=True
    report['catalog_counts']={key:len(value) for key,value in data.items() if isinstance(value,list)}
    if archive:
        archive=Path(archive).resolve();archive.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as output:
            for path in sorted(destination.rglob('*')):
                if path.is_file():output.write(path,path.relative_to(destination))
        report['archive']={'name':archive.name,'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--archive',type=Path);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();report=stage(args.input,args.output,args.archive)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'source_unchanged':report['source_unchanged'],'counts':report['catalog_counts'],
                      'validation_errors':len(report['validation']['errors']),'warnings':len(report['validation']['warnings']),
                      'map_issues':len(report['map']['issues']),'archive':report.get('archive')}))
