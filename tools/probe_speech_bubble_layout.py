#!/usr/bin/env python3
"""Render real map speech at phone/desktop sizes and read its final sentence.

No server, account or network assets. PySide6 / QtWebEngine is required.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]


def fixture():
    css=(ROOT/'web/visual-map.css').read_text()
    html='<!doctype html><html><head><meta charset="utf-8"><style>body{margin:0;background:#121e24;color:white}'+css+'</style></head><body><div id="player-visual-map"></div>'
    for name in ('display-settings.js','visual-map.js'):
        html+='<script>'+(ROOT/'web'/name).read_text()+'</script>'
    return html+r'''<script>
const advice='If you are heading to Open meadow, start east from here. I can describe the route I know if you need more directions.';
const extra=' I learned this road by walking it. A friend told me about the farther hills, but I have not visited them and cannot promise the path is safe.';
let expected='';
function setup(scale,long){
 window.ExpanseDisplay.choose('scale',scale);expected=advice+(long?extra.repeat(7):'');
 const tile={id:'square',name:'Dawnwatch Civic Square',x:0,y:0,z:0,current:true,visited:true,terrain:'grassland'};
 window.ExpanseMap.render({character:{id:'player'},location:{id:'square',name:tile.name},visual:{version:1,center:'square',floor:0,
  context:{id:'outside',kind:'outdoors',label:'Dawnwatch'},tiles:[tile],exits:[],links:[],
  actors:[{id:'bel',name:'Bel Stone of Dawnwatch',room:'square',kind:'npc',speech_bubble:{tone:'says',symbol:'🙂',words:expected}},
   {id:'player',name:'Player',room:'square',kind:'self',self:true}]}});
}
function position(){document.querySelector('.atlas-viewport').scrollIntoView({block:'center'});}
function measure(){
 const b=document.querySelector('.atlas-speech'),v=document.querySelector('.atlas-viewport'),before=b.scrollHeight-b.clientHeight;
 b.focus({preventScroll:true});b.scrollTop=b.scrollHeight;
 const r=b.getBoundingClientRect(),vr=v.getBoundingClientRect(),style=getComputedStyle(b),range=document.createRange(),text=b.firstChild;
 range.setStart(text,Math.max(0,text.length-16));range.setEnd(text,text.length);const last=range.getBoundingClientRect();
 return JSON.stringify({visible:!b.hidden,full:b.textContent.endsWith(expected),accessible:b.getAttribute('aria-label').includes(expected),
  viewport:[innerWidth,innerHeight],box:{left:r.left,right:r.right,top:r.top,bottom:r.bottom},map:{top:vr.top,bottom:vr.bottom},
  final:{top:last.top,bottom:last.bottom},horizontal:b.scrollWidth-b.clientWidth,vertical:before,
  overflowY:style.overflowY,focusable:document.activeElement===b,font:parseFloat(style.fontSize)});
}
</script></body></html>'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshot-dir',type=Path)
    args=parser.parse_args()
    try:
        from PySide6.QtCore import QTimer,QUrl,qVersion
        from PySide6.QtWidgets import QApplication
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError as error:parser.error(str(error))
    app=QApplication(sys.argv[:1]);view=QWebEngineView();view.show()
    if args.screenshot_dir:args.screenshot_dir.mkdir(parents=True,exist_ok=True)
    cases=iter([(w,h,scale,long) for w,h,scale in [(1280,900,100),(1280,900,150),(390,844,100),
               (390,844,125),(320,568,100),(844,390,100)] for long in (False,True)])
    rows=[];current=None

    def next_case():
        nonlocal current
        current=next(cases,None)
        if current is None:
            passed=sum(row['passed'] for row in rows)
            print(json.dumps({'runtime':qVersion(),'checks':len(rows),'passed':passed,'results':rows}),flush=True)
            app.exit(0 if passed==len(rows) else 1);return
        view.setFixedSize(*current[:2])
        QTimer.singleShot(130,lambda:view.page().runJavaScript(f'setup({current[2]},{str(current[3]).lower()})',
            lambda _:QTimer.singleShot(150,lambda:view.page().runJavaScript('position()',
                lambda _:QTimer.singleShot(100,lambda:view.page().runJavaScript('measure()',record))))))

    def record(value):
        try:row=json.loads(value)
        except (ValueError,TypeError):
            print('Speech bubble fixture failed.',file=sys.stderr);app.exit(2);return
        b,last=row['box'],row['final']
        okay=(row['visible'] and row['full'] and row['accessible'] and row['focusable'] and row['horizontal']<=1
              and b['left']>=0 and b['right']<=current[0]+1 and b['top']>=row['map']['top']-1
              and b['bottom']<=row['map']['bottom']+1 and last['top']>=b['top']-1 and last['bottom']<=b['bottom']+1
              and row['overflowY']=='auto' and (current[3] or row['vertical']<=1))
        rows.append({'case':current,'passed':okay,**row})
        def finish_case():
            if args.screenshot_dir:view.grab().save(str(args.screenshot_dir/f'speech-{current[0]}-{current[2]}-{int(current[3])}.png'))
            next_case()
        QTimer.singleShot(40,finish_case)

    view.loadFinished.connect(lambda okay:QTimer.singleShot(150,next_case) if okay else app.exit(2))
    view.setHtml(fixture(),QUrl('https://speech-layout.invalid/'))
    QTimer.singleShot(25000,lambda:app.exit(2))
    return app.exec()


if __name__=='__main__':raise SystemExit(main())
