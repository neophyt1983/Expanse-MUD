"""Bounded, current-state story discovery without downloading the quest catalog."""
from engine.item_catalog import counted
import re
from engine import living, quest_progress


def adventures(ctx, args):
    w,p=ctx.world,ctx.player
    query=args.strip().lower();page=1
    match=re.search(r'(?:^|\s)page\s+(\d+)$',query)
    if match:page=max(1,int(match.group(1)));query=query[:match.start()].strip()
    arcs={}
    for q in w.quests.values():
        if p.progress.get('quests',{}).get(q['id']) not in ('active','complete'):continue
        if q.get('arc_id'):arcs.setdefault(q['arc_id'],[]).append(q)
    if not arcs:return 'No accepted adventures. Ask nearby people about local work.'
    rows=[]
    for arc,chapters in arcs.items():
        chapters.sort(key=lambda q:(q.get('chapter',0),q['id']))
        first=chapters[0];region=first.get('region','')
        if query and query not in (arc+' '+region+' '+first['name']).lower():continue
        statuses={q['id']:quest_progress.status(w,p,q['id']) for q in chapters}
        candidates=[q for q in chapters if statuses[q['id']]=='active' and not living.quest_blocked(w,p,q)]
        if not candidates:candidates=[q for q in chapters if statuses[q['id']]=='available' and not living.quest_blocked(w,p,q)]
        nxt=candidates[0] if candidates else None
        done=sum(s=='complete' for s in statuses.values())
        label=('ACTIVE' if statuses[nxt['id']]=='active' else 'AVAILABLE') if nxt else ('RECORDED' if done else 'LOCKED')
        lines=[f'{first["name"]} | {region or "world"} | {label} | {counted(done,"chapter")} completed']
        if nxt:
            lines.append('Next: '+nxt['name'])
            room=nxt.get('offer_room') or nxt.get('turn_in_room')
            if room in w.rooms:lines.append('Start/continue at '+w.rooms[room].name+'; select it on your map or use its name for directions.')
            lines.append('Review this accepted chapter in your journal.')
        else:lines.append('Review recorded chapters in your journal.')
        rows.append((0 if label=='ACTIVE' else 1 if label=='AVAILABLE' else 2,arc,'\n'.join(lines)))
    rows.sort();start=(page-1)*20
    header=f'Adventures: {len(rows)} matching arcs. Showing {start+1 if start<len(rows) else 0}–{min(start+20,len(rows))}. Choices can exclude other chapters.'
    lines=[header]+[row[2] for row in rows[start:start+20]]
    if start+20<len(rows):lines.append('More: adventures '+(query+' ' if query else '')+f'page {page+1}')
    lines.append('Filter by region or arc: adventures <words>. Journal shows your accepted objectives.')
    return '\n\n'.join(lines)
