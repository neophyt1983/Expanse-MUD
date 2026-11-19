#!/usr/bin/env python3
"""Real Talk/Location expression layout checks, without a server or saved game.

Run with PySide6 and QtWebEngine installed:
  QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu --no-sandbox' \
    python tools/probe_npc_expression_layout.py
"""
import argparse
import json
from pathlib import Path
import sys

from probe_location_panel_layout import ROOT, fixture as workspace_fixture


def fixture():
    html = workspace_fixture(ROOT / 'web/workspace.js')
    marker = '<script>' + (ROOT / 'web/play-windows.js').read_text()
    addition = '<script>document.getElementById("society-panels").remove();</script>'
    addition += '<script>' + (ROOT / 'web/society-ui.js').read_text() + '</script>'
    html = html.replace(marker, addition + marker)
    html += r'''<script>
const feelings=[['sad','Sad','Recent experience'],['angry','Angry','Recent experience'],
 ['anxious','Anxious','Reporting an experienced event to an officer; past authority experiences'],
 ['hopeful','Hopeful','Seeking help from an officer'],['grateful','Grateful','Past support experiences'],
 ['tired','Tired','Current hunger need'],['affectionate','Affectionate','An established close relationship']];
function expressions(scale){
 window.ExpansePlayWindows.disconnect();resetPanel(scale);
 packet.location.npcs=[{id:'mira',name:'Mira',description:'A resident reporting a witnessed loss.'}];
 packet.social={emotions:{happy:'🙂',serious:'😐'},npcs:[{id:'mira',name:'Mira',awake:true,adult:true,trust:10,likes:'',needs:'',quests:[],commerce:{},
 expression:{summary:feelings.map(row=>row[0]).join(', '),emotions:feelings.map(row=>({id:row[0],label:row[1],causes:[row[2]],intensity:40}))}}]};
 window.renderRoomPanel(packet);document.getElementById('location-panel').scrollTop=0;
 document.querySelector('.npc-expression').scrollIntoView({block:'nearest'});
}
function openExpression(){window.openNpcSocial('mira');const e=document.getElementById('npc-emotion-state');e.scrollIntoView({block:'start'});const d=e.closest('dialog');d.scrollTop-=d.querySelector('.expanse-window-bar').getBoundingClientRect().height+12;}
function measureExpression(talk){
 const e=document.querySelector(talk?'#npc-emotion-state':'.npc-expression'),r=e.getBoundingClientRect(),dialog=e.closest('dialog');
 return JSON.stringify({viewport:[innerWidth,innerHeight],visible:!e.hidden&&r.width>0&&r.bottom>0&&r.top<innerHeight,
 left:r.left,right:r.right,overflow:e.scrollWidth-e.clientWidth,text:e.textContent,count:e.querySelectorAll('li').length,
 dialogOpen:dialog?dialog.open:null,dialogOverflow:dialog?dialog.scrollWidth-dialog.clientWidth:0,
 smallest:[...e.querySelectorAll('small'),e].reduce((size,node)=>Math.min(size,parseFloat(getComputedStyle(node).fontSize)),100)});
}
</script>'''
    return html


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshot-dir', type=Path)
    args = parser.parse_args()
    try:
        from PySide6.QtCore import QTimer, QUrl, qVersion
        from PySide6.QtWidgets import QApplication
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError as error:
        parser.error(str(error))
    app = QApplication(sys.argv[:1])
    view = QWebEngineView()
    view.show()
    if args.screenshot_dir:
        args.screenshot_dir.mkdir(parents=True, exist_ok=True)
    cases = iter([(1280, 900, 100), (1280, 900, 150), (390, 844, 100), (390, 844, 125)])
    results = []
    current = None

    def next_case():
        nonlocal current
        current = next(cases, None)
        if current is None:
            passed = sum(row['passed'] for row in results)
            print(json.dumps({'runtime': qVersion(), 'checks': len(results), 'passed': passed, 'results': results}), flush=True)
            app.exit(0 if passed == len(results) else 1)
            return
        view.setFixedSize(current[0], current[1])
        QTimer.singleShot(150, lambda: view.page().runJavaScript('expressions(' + str(current[2]) + ')',
            lambda _: QTimer.singleShot(150, lambda: measure(False))))

    def measure(talk):
        view.page().runJavaScript('measureExpression(' + str(talk).lower() + ')', lambda value: record(value, talk))

    def record(value, talk):
        try:
            row = json.loads(value)
        except (ValueError, TypeError):
            print('NPC expression fixture failed.', file=sys.stderr)
            app.exit(2)
            return
        okay = (row['visible'] and row['left'] >= 0 and row['right'] <= current[0] + 1
                and row['overflow'] <= 1 and row['dialogOverflow'] <= 1
                and row['smallest'] >= (14 if current[0] < 680 else 11))
        if talk:
            okay = okay and row['dialogOpen'] and row['count'] == 7
        results.append({'case': current, 'check': 'Talk' if talk else 'Nearby', 'passed': bool(okay), **row})
        if args.screenshot_dir:
            view.grab().save(str(args.screenshot_dir / f'expression-{current[0]}-{current[2]}-{talk}.png'))
        if talk:
            next_case()
        else:
            view.page().runJavaScript('openExpression()', lambda _: QTimer.singleShot(150, lambda: measure(True)))

    view.loadFinished.connect(lambda okay: QTimer.singleShot(200, next_case) if okay else app.exit(2))
    view.setHtml(fixture(), QUrl('https://npc-expression.invalid/'))
    QTimer.singleShot(20000, lambda: app.exit(2))
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
