#!/usr/bin/env python3
"""Verify personal custody notices in the real room and dock UI with Qt 6.

Run with PySide6 / QtWebEngine installed:
  QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu --no-sandbox' \
    python tools/probe_custody_layout.py

This reuses the location-layout browser fixture. It loads no game, account,
server, or saved world, and cannot advance or change a real custody case.
"""
import argparse
import json
import sys
from pathlib import Path
from probe_location_panel_layout import fixture,ROOT
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--screenshot-dir', type=Path)
args = parser.parse_args()
try:
 from PySide6.QtCore import QTimer,QUrl,qVersion
 from PySide6.QtWidgets import QApplication
 from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError as error:
 parser.error('PySide6 / QtWebEngine 6 could not load: ' + str(error))
if args.screenshot_dir:
 args.screenshot_dir.mkdir(parents=True, exist_ok=True)
html=fixture(ROOT/'web/workspace.js')+'''<script>
const mapHost=document.createElement('div');mapHost.id='player-visual-map';mapHost.className='field-atlas';mapHost.innerHTML='<div class="atlas-position-header"><div class="atlas-current-room">Here: Dawnwatch Police Station Jail</div></div><div class="atlas-viewport"></div>';
document.querySelector('#dock-game-map .dock-content').append(mapHost);
let stage='sentenced';
function casePacket(scale,released=false){
 resetPanel(scale);stage=released?'released':'sentenced';
 packet.custody={id:'layout-'+innerWidth+'-'+scale,status:stage,active:!released,title:released?'Released from custody':'In custody — sentence',accusation:'theft',reason:'The recorded accusation is theft: taking contents from the magistrate cabinet at Dawnwatch Civic Square.',witness_count:2,remaining_minutes:released?null:10,next_event:released?null:'release',custody_place:'Dawnwatch Police Station Jail',allowed_facilities:['Dawnwatch Police Station Jail'],fine_paid:5,instructions:released?[]:['You may use the permitted custody facilities; leaving them is blocked until the sentence ends.','Release happens automatically when the game-time deadline is reached. You will be moved to Dawnwatch Civic Square.','These are game minutes, not real minutes. The clock advances while you are connected.'],outcome:released?'Your sentence is complete. You have been released to Dawnwatch Civic Square.':null,can_wait:false,wait_command:null};
 window.renderRoomPanel(packet);window.ExpansePanels.reveal('map');document.querySelector('#dock-game-map .dock-content').scrollTop=0;
}
function measureCustody(selector,panelSelector){
 const e=document.querySelector(selector),p=document.querySelector(panelSelector),r=e.getBoundingClientRect(),b=p.getBoundingClientRect();
 return JSON.stringify({stage,hidden:e.hidden,visible:e.getClientRects().length>0&&r.width>0,left:r.left,right:r.right,top:r.top,bottom:r.bottom,overflow:e.scrollWidth-e.clientWidth,panel:{left:b.left,right:b.right,top:b.top,bottom:b.bottom},viewport:[innerWidth,innerHeight],text:e.textContent,focus:document.activeElement?.id});
}
function details(){[...document.getElementById('player-custody-notice').querySelectorAll('button')].find(b=>b.textContent==='Custody details').click();}
</script>'''
app=QApplication(sys.argv[:1]);view=QWebEngineView();view.show();rows=[];cases=iter([(1280,900,100,False),(1280,900,100,True),(1280,900,150,False),(1280,900,150,True),(390,844,100,False),(390,844,100,True)]);current=None

def next_case():
 global current
 current=next(cases,None)
 if current is None:
  print(json.dumps({'runtime':qVersion(),'checks':len(rows),'passed':sum(x['passed'] for x in rows),'rows':rows}));app.exit(0 if all(x['passed'] for x in rows) else 1);return
 view.setFixedSize(current[0],current[1]);QTimer.singleShot(100,lambda:view.page().runJavaScript('casePacket('+str(current[2])+','+str(current[3]).lower()+')',lambda _:QTimer.singleShot(200,read_banner)))
def read_banner():view.page().runJavaScript("measureCustody('#player-custody-notice','#dock-game-map .dock-content')",banner)
def banner(raw):
 row=json.loads(raw);p=row['panel'];okay=row['visible'] and not row['hidden'] and row['left']>=p['left']-1 and row['right']<=p['right']+1 and row['overflow']<=1 and row['top']>=p['top']-1 and row['bottom']<=p['bottom']+1
 rows.append({'case':current,'check':'visible map notice','passed':okay,**row})
 if args.screenshot_dir:view.grab().save(str(args.screenshot_dir / ('custody-map-'+str(current[0])+'-'+str(current[2])+'-'+str(current[3])+'.png')))
 view.page().runJavaScript('details()',lambda _:QTimer.singleShot(100,read_details))
def read_details():view.page().runJavaScript("measureCustody('#custody-details','#location-panel')",details)
def details(raw):
 row=json.loads(raw);p=row['panel'];okay=row['visible'] and row['left']>=p['left']-1 and row['right']<=p['right']+1 and row['overflow']<=1 and row['focus']=='custody-details' and row['top']>=p['top']-1
 rows.append({'case':current,'check':'details navigable and wrapped','passed':okay,**row})
 if args.screenshot_dir:view.grab().save(str(args.screenshot_dir / ('custody-details-'+str(current[0])+'-'+str(current[2])+'-'+str(current[3])+'.png')))
 next_case()
view.loadFinished.connect(lambda ok:QTimer.singleShot(200,next_case) if ok else app.exit(2));view.setHtml(html,QUrl('https://custody-layout.invalid/'));QTimer.singleShot(20000,lambda:app.exit(2));sys.exit(app.exec())
