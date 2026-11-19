#!/usr/bin/env python3
"""Check the real room/dock CSS and renderer in an isolated Qt 6 browser.

Run with a Python that has PySide6 and QtWebEngine installed:
  QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu --no-sandbox' \
    python tools/probe_location_panel_layout.py

No game server, account, save, or network service is used. --workspace-script can
point to an earlier renderer to verify that the refresh regression is detected.
"""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def fixture(renderer):
    source = (ROOT / 'web/index.html').read_text()
    html = source[:source.index('<script src="/damage-feedback.js">')]
    html = re.sub(r'<script\b[^>]*>[\s\S]*?</script>', '', html)
    html = re.sub(r'<link\b[^>]*>', '', html)
    for name in re.findall(r'<link[^>]*href="/([^"?]+\.css)(?:\?[^"]*)?"', source):
        html += '<style>' + (ROOT / 'web' / name).read_text() + '</style>'
    html += '''<script>
let selectGame=async()=>{},ws=null;function append(){}function refreshDesignerMap(){}function setStatus(){}
for(const id of ['player-map-panel','character-frame','session-actions','society-panels']){
 const n=document.createElement('div');n.id=id;document.getElementById('tab-game').append(n);
}
</script>'''
    scripts = [renderer] + [ROOT / 'web' / name for name in (
        'display-settings.js', 'dock-layout.js', 'window-controls.js',
        'play-windows.js', 'mobile-layout.js')]
    for script in scripts:
        html += '<script>' + script.read_text() + '</script>'
    html += '''<script>
const item=(i)=>({id:'item'+i,name:'Inventory Item '+i,location:'Your inventory',origin:'Dawnwatch Square',type:'misc',description:'A description that wraps at the ordinary sidebar width.'});
let packet;
function resetPanel(scale){
 window.ExpanseDisplay.choose('scale',String(scale));window.ExpansePanels.reveal('location');
 packet={character:{id:'p',name:'Tester',hp:100,max_hp:100,gold:0,inventory:Array.from({length:12},(_,i)=>item(i))},location:{id:'square',name:'Dawnwatch Civic Square',description:'An outdoor civic square with roads and buildings nearby.',npcs:[],players:[],items:[]}};
 window.renderRoomPanel(packet);document.querySelector('[data-section="Your inventory"]').open=true;
 const panel=document.getElementById('location-panel');panel.scrollTop=0;
}
function bottom(){const p=document.getElementById('location-panel');p.scrollTop=p.scrollHeight;}
function grow(){packet.character.inventory.at(-1).description+=' A changed condition adds more lines below the last description.'.repeat(8);window.renderRoomPanel(packet);}
function measure(){
 const p=document.getElementById('location-panel'),last=p.querySelector('.action-card:last-child .action-buttons'),a=p.getBoundingClientRect(),b=last.getBoundingClientRect();
 return {gap:p.scrollHeight-p.clientHeight-p.scrollTop,top:p.scrollTop,height:p.clientHeight,lastBottom:b.bottom,panelBottom:a.bottom,lastTop:b.top,panelTop:a.top,viewport:[innerWidth,innerHeight],scale:getComputedStyle(document.documentElement).zoom};
}
</script>'''
    return html


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace-script', type=Path, default=ROOT / 'web/workspace.js')
    args = parser.parse_args()
    try:
        from PySide6.QtCore import QTimer, QUrl, qVersion
        from PySide6.QtWidgets import QApplication
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError as error:
        parser.error('PySide6 / QtWebEngine 6 could not load: ' + str(error))
    app = QApplication(sys.argv[:1])
    view = QWebEngineView()
    view.setFixedSize(1280, 900)
    view.show()
    results, failures = [], []
    scenarios = iter([(1280, 900, 100), (1280, 900, 125), (1280, 900, 150),
                      (1280, 900, 200), (1920, 1080, 150), (900, 640, 100), (390, 844, 100)])
    current = None
    checks = 0

    def js(expression, callback=None):
        view.page().runJavaScript(expression, callback or (lambda result: None))

    def record(name, value, bottom=True):
        nonlocal checks
        checks += 1
        row = json.loads(value)
        okay = (abs(row['gap']) <= 2 and row['lastBottom'] <= row['panelBottom'] + 1
                and row['lastTop'] >= row['panelTop'] - 1) if bottom else abs(row['top'] - saved_top[0]) <= 1
        okay = okay and row['viewport'] == list(current[:2])
        results.append({'viewport': current[:2], 'scale': current[2], 'check': name,
                        'passed': okay, 'remaining_scroll': round(row['gap'], 2),
                        'scroll_top': round(row['top'], 2),
                        'last_control_clearance': round(row['panelBottom'] - row['lastBottom'], 2)})
        if not okay:
            failures.append({'check': name, 'scenario': current, 'measurement': row})

    def next_scenario():
        nonlocal current
        current = next(scenarios, None)
        if current is None:
            print(json.dumps({'runtime': 'Qt ' + qVersion(), 'checks': checks,
                              'passed': checks - len(failures), 'results': results,
                              'failures': failures}), flush=True)
            app.exit(1 if failures else 0)
            return
        view.setFixedSize(current[0], current[1])
        QTimer.singleShot(200, lambda: js('resetPanel(' + str(current[2]) + ')',
            lambda value: QTimer.singleShot(200, initial)))

    def initial():
        js('grow(); JSON.stringify(measure())', initial_result)

    def initial_result(value):
        saved_top[0] = 0
        record('unscrolled content stays at top', value, bottom=False)
        js('bottom()', lambda value: QTimer.singleShot(70, refresh))

    def refresh():
        js('grow(); JSON.stringify(measure())', refreshed)

    def refreshed(value):
        record('last control remains above border after refresh', value)
        if current[0] <= 680:
            # Phone panels have one bounded viewport and no floating resize UI.
            read_middle()
            return
        js("var c=document.querySelector('.dock-canvas');c.style.flex='none';c.style.height='220px';",
           lambda value: QTimer.singleShot(150, resized))

    def resized():
        js('JSON.stringify(measure())', resize_result)

    def resize_result(value):
        # Narrow desktop tabs deliberately expand as a page; phone and desktop
        # bounded docks keep their end as the visible panel becomes shorter.
        row = json.loads(value)
        if row['height'] < 700:
            record('last control remains visible after dock resize', value)
        read_middle()

    def read_middle():
        js("var p=document.getElementById('location-panel');p.scrollTop=Math.max(1,(p.scrollHeight-p.clientHeight)/2);p.scrollTop;",
           lambda value: middle(value))

    saved_top = [0]

    def middle(value):
        saved_top[0] = value
        QTimer.singleShot(70, lambda: js('grow(); JSON.stringify(measure())', middle_result))

    def middle_result(value):
        record('earlier reading position survives refresh', value, bottom=False)
        js("document.querySelector('.dock-canvas').removeAttribute('style');", lambda value: next_scenario())

    def loaded(ok):
        if not ok:
            print('Browser fixture did not load.', file=sys.stderr)
            app.exit(2)
        else:
            QTimer.singleShot(200, next_scenario)

    def timeout():
        print('Location layout browser probe timed out.', file=sys.stderr)
        app.exit(2)

    view.loadFinished.connect(loaded)
    view.setHtml(fixture(args.workspace_script), QUrl('https://layout.invalid/'))
    QTimer.singleShot(20000, timeout)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
