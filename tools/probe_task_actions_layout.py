#!/usr/bin/env python3
"""Check task/service cards and dialogs in the real room/dock browser."""
import argparse
import json
from pathlib import Path
import sys
import time
from probe_location_panel_layout import fixture, ROOT

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--screenshot-dir',type=Path)
args=parser.parse_args()
try:
    from PySide6.QtCore import QTimer,QUrl,qVersion
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError as error:
    parser.error('PySide6 / QtWebEngine 6 could not load: '+str(error))
if args.screenshot_dir:args.screenshot_dir.mkdir(parents=True,exist_ok=True)
html=fixture(ROOT/'web/workspace.js')
for name in ('theft-ui.js','guild-ui.js','skills-ui.js','work-services-ui.js'):
    html+='<script>'+(ROOT/'web'/name).read_text()+'</script>'
html+='''<script>
function taskPacket(scale){
 window.ExpanseTheft.reset();resetPanel(scale);
 packet.location.npcs=[{id:'merchant',name:'Arden Lightbrook, Keeper of the Dawnwatch Winter Stores',description:'A real local guild contact.'}];
 packet.theft={level:40,observation:25,blocked:'',targets:[{id:'merchant',name:packet.location.npcs[0].name,kind:'npc'}]};
 packet.guilds={room:'square',memberships:['farmers'],guilds:[{id:'farmers',name:'Farmers and Market Gardeners Guild',member:true,tasks:[{name:'Farming',level:12}],join:{enabled:false,reason:'Already a member.',fee:0},lessons:[],quests:[
  {id:'food',name:'Help replenish the community store',description:'Bring grain to the storekeeper. The request remains available while the actual store needs supplies.',tier:'Apprentice',difficulty:10,status:'active',remaining:12,revision:1,reward:'One gold per unit accepted.',accept:{enabled:false,reason:'This quest is already active.'},complete:{enabled:false,reason:'You need grain in your inventory before you can contribute to this shared request. Other workers can contribute while you search.'}}
 ]}]};
 packet.work_services={cards:[
  {id:'employment',title:'Paid work at the Provision Counter',lines:['The counter reserves actual ingredients and pays only after the work is complete.'],entries:[
   {id:'kitchen',title:'Provision kitchen helper',lines:['3 gold per 5 game minutes. Carrot, onion and potato come from the finite workshop stock.'],actions:[{id:'job:apply',service:'employment',action:'apply',label:'Apply for kitchen work',enabled:true,reason:'',revision:'job1'}]}
  ]},
  {id:'art',title:'Artistic work and local commissions',lines:[],entries:[
   {id:'plan',title:'Draw a measured plan of the actual library',lines:['One paper and one ink; twenty game minutes of work at the station.'],actions:[{id:'art:begin',service:'art',action:'begin',label:'Begin the library plan',enabled:true,reason:'',revision:'art1'}]}
  ]},
  {id:'clinical',title:'Care at the Dawnwatch Hospital',lines:['A living local clinician must have the supplies needed for care.'],entries:[
   {id:'treatment',title:'Request examination and treatment',lines:['8 gold if the treatment is available.'],actions:[{id:'care:request',service:'clinical',action:'treatment',label:'Request treatment · 8 gold',enabled:false,reason:'The care cabinet needs a bandage and clean water. Bring supplies or return when staff can provide care.',revision:'care1'}]}
  ]}
 ]};
 window.renderRoomPanel(packet);const panel=document.getElementById('location-panel');panel.scrollTop=panel.scrollHeight;
}
function guildMeasure(){
 const panel=document.getElementById('location-panel'),card=panel.querySelector('.guild-card'),last=[...card.querySelectorAll('small')].at(-1);
 // A short desktop uses page scrolling; phones use the bounded panel.
 last.scrollIntoView({block:'nearest'});const b=panel.getBoundingClientRect(),r=last.getBoundingClientRect();
 return JSON.stringify({check:'guild final prerequisite',viewport:[innerWidth,innerHeight],left:r.left,right:r.right,top:r.top,bottom:r.bottom,panel:{left:b.left,right:b.right,top:b.top,bottom:b.bottom},overflow:card.scrollWidth-card.clientWidth,text:last.textContent});
}
function openTheft(){window.ExpanseTheft.open('merchant');}
function showWorkTail(){
 const card=[...document.querySelectorAll('.work-service-card')].at(-1);
 [...card.querySelectorAll('.work-service-action')].at(-1).scrollIntoView({block:'nearest'});
}
function workMeasure(){
 const panel=document.getElementById('location-panel'),card=[...panel.querySelectorAll('.work-service-card')].at(-1);
 const action=[...card.querySelectorAll('.work-service-action')].at(-1),button=action.querySelector('button'),reason=action.querySelector('small');
 const p=panel.getBoundingClientRect(),b=button.getBoundingClientRect(),r=reason.getBoundingClientRect();
 return JSON.stringify({check:'work final control and prerequisite',viewport:[innerWidth,innerHeight],disabled:button.disabled,described:button.getAttribute('aria-describedby')===reason.id,
  panel:{left:p.left,right:p.right,top:p.top,bottom:p.bottom},controls:{left:b.left,right:b.right,top:b.top,bottom:b.bottom},
  reason:{left:r.left,right:r.right,top:r.top,bottom:r.bottom},overflow:card.scrollWidth-card.clientWidth,text:reason.textContent});
}
function theftMeasure(){
 const dialog=document.getElementById('theft-action');
 const r=dialog.getBoundingClientRect(),buttons=dialog.querySelector('.action-buttons').getBoundingClientRect();
 return JSON.stringify({check:'theft final controls',visible:dialog.open,viewport:[innerWidth,innerHeight],left:r.left,right:r.right,top:r.top,bottom:r.bottom,overflow:dialog.scrollWidth-dialog.clientWidth,controls:{left:buttons.left,right:buttons.right,top:buttons.top,bottom:buttons.bottom},text:dialog.textContent});
}
function openSkills(){
 window.ExpanseTheft.reset();
 packet.character.skills={skills:Array.from({length:27},(_,i)=>({id:'skill'+i,name:i===26?'Observation and practical knowledge':'Task skill '+i,level:i,proficiency:'Apprentice',practice:13.5,next_practice:91})),knowledge:{recipes:[{name:'Winter grain porridge'}],techniques:[{name:'A learned technique'}],books:[{name:'The final complete reading journal entry'}]}};
 window.renderRoomPanel(packet);window.ExpanseSkills.open();
 const d=document.getElementById('player-skills');for(const row of d.querySelectorAll('details'))row.open=true;
 [...d.querySelectorAll('button')].at(-1).scrollIntoView({block:'nearest'});
}
function skillsMeasure(){
 const dialog=document.getElementById('player-skills'),r=dialog.getBoundingClientRect(),button=[...dialog.querySelectorAll('button')].at(-1).getBoundingClientRect();
 const last=[...dialog.querySelectorAll('li')].at(-1).getBoundingClientRect();
 return JSON.stringify({check:'skills final knowledge and close',visible:dialog.open,viewport:[innerWidth,innerHeight],left:r.left,right:r.right,top:r.top,bottom:r.bottom,overflow:dialog.scrollWidth-dialog.clientWidth,controls:{left:button.left,right:button.right,top:button.top,bottom:button.bottom},last:{top:last.top,bottom:last.bottom},text:dialog.textContent});
}
</script>'''
app=QApplication(sys.argv[:1]);view=QWebEngineView();view.show()
cases=iter([(1280,900,100),(1280,900,150),(1280,900,200),(390,844,100),(320,568,100),(844,390,100)])
rows=[];current=None;phase={'name':'load fixture'};started=time.monotonic()
def screenshot(prefix):
    if not args.screenshot_dir:return
    capture_started=time.monotonic()
    view.grab().save(str(args.screenshot_dir/(prefix+'-'+str(current[0])+'-'+str(current[2])+'.png')))
    rows[-1]['screenshot_seconds']=round(time.monotonic()-capture_started,3)
def next_case():
    global current
    current=next(cases,None)
    if current is None:
        print(json.dumps({'runtime':qVersion(),'completed':True,'elapsed_seconds':round(time.monotonic()-started,3),'checks':len(rows),'passed':sum(row['passed'] for row in rows),'rows':rows}))
        app.exit(0 if all(row['passed'] for row in rows) else 1);return
    phase['name']='configure viewport and render task packet'
    view.setFixedSize(current[0],current[1])
    QTimer.singleShot(100,lambda:view.page().runJavaScript('taskPacket('+str(current[2])+')',lambda _:QTimer.singleShot(180,read_guild)))
def read_guild():
    phase['name']='measure final guild prerequisite'
    view.page().runJavaScript('guildMeasure()',guild_result)
def guild_result(raw):
    row=json.loads(raw);p=row['panel']
    okay=row['overflow']<=1 and row['left']>=p['left']-1 and row['right']<=p['right']+1 and row['top']>=max(0,p['top'])-1 and row['bottom']<=min(row['viewport'][1],p['bottom'])+1
    rows.append({'case':current,'passed':okay,'elapsed_seconds':round(time.monotonic()-started,3),**row})
    screenshot('guild')
    phase['name']='reveal final work controls'
    view.page().runJavaScript('showWorkTail()',lambda _:QTimer.singleShot(180,read_work))
def read_work():
    phase['name']='measure final work controls and prerequisite'
    view.page().runJavaScript('workMeasure()',work_result)
def work_result(raw):
    row=json.loads(raw);p=row['panel'];w,h=row['viewport']
    def contained(rect):
        return rect['left']>=max(0,p['left'])-1 and rect['right']<=min(w,p['right'])+1 and rect['top']>=max(0,p['top'])-1 and rect['bottom']<=min(h,p['bottom'])+1
    okay=row['disabled'] and row['described'] and row['overflow']<=1 and contained(row['controls']) and contained(row['reason'])
    rows.append({'case':current,'passed':okay,'elapsed_seconds':round(time.monotonic()-started,3),**row})
    screenshot('work')
    phase['name']='open theft dialog'
    view.page().runJavaScript('openTheft()',lambda _:QTimer.singleShot(180,read_theft))
def read_theft():
    phase['name']='measure theft dialog controls'
    view.page().runJavaScript("var d=document.getElementById('theft-action');d.scrollTop=d.scrollHeight",lambda _:QTimer.singleShot(100,lambda:view.page().runJavaScript('theftMeasure()',theft_result)))
def theft_result(raw):
    row=json.loads(raw);c=row['controls'];w,h=row['viewport']
    okay=row['visible'] and row['overflow']<=1 and row['left']>=-1 and row['right']<=w+1 and row['top']>=-1 and row['bottom']<=h+1 and c['left']>=row['left'] and c['right']<=row['right'] and c['top']>=row['top'] and c['bottom']<=row['bottom']
    rows.append({'case':current,'passed':okay,'elapsed_seconds':round(time.monotonic()-started,3),**row})
    screenshot('theft')
    phase['name']='open skills dialog'
    view.page().runJavaScript('openSkills()',lambda _:QTimer.singleShot(180,read_skills))
def read_skills():
    phase['name']='measure skills dialog'
    view.page().runJavaScript('skillsMeasure()',skills_result)
def skills_result(raw):
    row=json.loads(raw);c=row['controls'];w,h=row['viewport'];last=row['last']
    okay=row['visible'] and row['overflow']<=1 and row['left']>=-1 and row['right']<=w+1 and row['top']>=-1 and row['bottom']<=h+1 and c['top']>=row['top'] and c['bottom']<=row['bottom'] and last['top']>=row['top'] and last['bottom']<=row['bottom']
    rows.append({'case':current,'passed':okay,'elapsed_seconds':round(time.monotonic()-started,3),**row})
    screenshot('skills')
    phase['name']='close skills dialog'
    view.page().runJavaScript('window.ExpanseSkills.reset()',lambda _:next_case())
def fail(reason):
    print(json.dumps({'runtime':qVersion(),'completed':False,'elapsed_seconds':round(time.monotonic()-started,3),'reason':reason,'case':current,'blocked_at':phase['name'],
                      'checks':len(rows),'passed':sum(row['passed'] for row in rows),'rows':rows}),flush=True)
    app.exit(2)
view.loadFinished.connect(lambda ok:QTimer.singleShot(200,next_case) if ok else fail('fixture failed to load'))
view.setHtml(html,QUrl('https://task-actions-layout.invalid/'))
QTimer.singleShot(20000,lambda:fail('20-second watchdog expired'));sys.exit(app.exec())
