"""Read locally available books by name and remember volumes actually read."""
from engine import ability_rules, knowledge

def publication_text(world, item):
    """Show authored provenance without inventing authors or publication dates."""
    info = item.get('publication')
    if not isinstance(info, dict):
        return ''
    from engine import chronicles, worldtime
    present = worldtime.initial_minute(world.metadata)
    lines = [item['name']]
    kind = {'fiction': 'Fiction', 'nonfiction': 'Nonfiction'}.get(info.get('kind'), '')
    lines.append(' · '.join(value for value in (kind, info.get('genre')) if value))
    if info.get('author'):
        lines.append('Author: '+info['author'])
    era = {'civilization': 'Civilization · Medium time', 'individual': 'Individuals · Recent time'}.get(info.get('original_era'), '')
    if type(info.get('original_minute')) is int:
        lines.append('Original: '+(' — '.join(value for value in (era, chronicles.date_text(info['original_minute'], present)) if value)))
    if type(info.get('edition_minute')) is int:
        lines.append('This edition: '+chronicles.date_text(info['edition_minute'], present))
    if info.get('attributed_to'):
        lines.append('Current attribution or editorial transmission: '+info['attributed_to'])
    return '\n'.join(line for line in lines if line)+'\n\n'


def finish(world,player,item):
    info=item.get('publication')
    if not isinstance(info,dict) or not info.get('author') or not info.get('genre'):return ''
    shelf=player.progress.setdefault('reading_journal_v1',[])
    if item['id'] not in shelf:shelf.append(item['id'])
    knowledge.teach(world,player,{'items':[item['id']],**item.get('knowledge',{})})
    result=[]
    for aid in item.get('study_abilities',[]):
        ab=world.abilities.get(aid)
        if not ab:continue
        reason=ability_rules.learning_eligibility(world,player,ab)
        if reason:result.append(ab['name']+' — '+reason)
        elif aid not in player.abilities:
            player.abilities.append(aid);result.append('You learned '+ab['name']+'.')
    return ('\n\n'+'\n'.join(result)) if result else ''

def browse(world,player,query=''):
    words=query.strip().casefold();journal=words=='read' or words.startswith('read ')
    if journal:words=words[4:].strip()
    ids=player.progress.get('reading_journal_v1',[]) if journal else player.inventory+world.rooms[player.location].items
    books=[world.items[i] for i in dict.fromkeys(ids) if i in world.items and isinstance(world.items[i].get('publication'),dict) and world.items[i]['publication'].get('genre') and world.items[i]['publication'].get('author')]
    rows=[b for b in books if words in (' '.join([b['name'],b['publication']['genre'],b['publication']['author'],b['publication'].get('kind',''),b['publication'].get('attributed_to','')])).casefold()]
    if not rows:return 'No matching titles in your reading journal.' if journal else 'No matching books here. Try a public library or a school.'
    text=['Your reading journal' if journal else 'Books available here']
    for genre in sorted({b['publication']['genre'] for b in rows}):
        text.append(genre)
        text.extend('  '+b['name']+' — '+b['publication']['author']+
                    (' ('+b['publication']['kind']+')' if b['publication'].get('kind') else '')
                    for b in sorted(rows,key=lambda r:r['name']) if b['publication']['genre']==genre)
    text.append('Read a local or carried book with read <title>.')
    return '\n'.join(text)
