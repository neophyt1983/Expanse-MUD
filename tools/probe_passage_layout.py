#!/usr/bin/env python3
"""Check blocked-passage explanations with the real UI scripts and Qt 6 CSS.

Run with a Python that has PySide6 and QtWebEngine installed:
  QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu --no-sandbox' \
    python tools/probe_passage_layout.py

No game server, account, save, or network service is used. The host-supplied
custody reason is fixture data; this probe does not decide or change custody.
Use --street-script with an earlier script to verify the regression is detected.
"""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def fixture(street_script):
    source = (ROOT / 'web/index.html').read_text()
    css = ''.join(re.findall(r'<style[^>]*>([\s\S]*?)</style>', source))
    for name in re.findall(r'<link[^>]*href="/([^"?]+\.css)(?:\?[^"]*)?"', source):
        css += '\n' + (ROOT / 'web' / name).read_text()
    html = '''<!doctype html><html><head><meta charset="utf-8"><style>''' + css + '''</style></head>
<body><div id="player-visual-map"><div class="atlas-position-header"><div id="here"></div></div>
<div class="atlas-viewport"><canvas></canvas></div><div id="inspect"></div></div>'''
    for script in [ROOT / 'web/display-settings.js', ROOT / 'web/window-controls.js', street_script]:
        html += '<script>' + script.read_text() + '</script>'
    html += '''<script>
window.ExpansePlayerControls={move(){throw Error('A blocked action must not send movement.')}};
const host=document.getElementById('player-visual-map');
const tile={id:'jail',name:'Dawnwatch Police Station Jail',current:true,x:0,y:0,z:0};
const why="The judge's sentence has 10 game minutes remaining. You may use the facilities inside your place of custody.";
const packet={character:{id:'tester'},location:{id:tile.id,name:tile.name},visual:{center:tile.id,
 context:{id:'building:police',kind:'building'},tiles:[tile],exits:[],passages:[
  {direction:'south',kind:'passage',label:'Go to Dawnwatch Police Station',blocked:why},
  {direction:'out',kind:'passage',label:'Go to Dawnwatch Police Station Cell Corridor',blocked:why}]}};
const point={tile,x:120,y:120,radius:24};
const state={options:{},packet,data:packet.visual,canvas:host.querySelector('canvas'),
 viewport:host.querySelector('.atlas-viewport'),locationStatus:document.getElementById('here'),
 inspect:document.getElementById('inspect'),positions:[point]};
function setup(scale){
 window.ExpanseDisplay.choose('scale',scale);window.ExpanseStreet.draw(state,point);
 window.ExpanseStreet.select(state,tile);
}
function measure(){
 const dialog=document.getElementById('street-passage'),r=dialog.getBoundingClientRect();
 const reasons=[...dialog.querySelectorAll('.street-passage-reason')];
 const actions=[...dialog.querySelectorAll('.street-passage-action button')];
 return JSON.stringify({dialog:{left:r.left,right:r.right,width:r.width,
  overflow:dialog.scrollWidth-dialog.clientWidth},viewport:[innerWidth,innerHeight],
  reasons:reasons.map(p=>{const b=p.getBoundingClientRect(),s=getComputedStyle(p);
   return {left:b.left,right:b.right,height:b.height,overflow:p.scrollWidth-p.clientWidth,
    opacity:s.opacity,color:s.color,font:s.fontSize,lineHeight:s.lineHeight};}),
  action_count:actions.length,disabled:actions.every(a=>a.disabled),
  descriptions:actions.every(a=>document.getElementById(a.getAttribute('aria-describedby'))?.textContent===why),
  label_only:actions.every(a=>!a.textContent.includes(why))});
}
</script></body></html>'''
    return html


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--street-script', type=Path, default=ROOT / 'web/street-actions.js')
    parser.add_argument('--screenshot-dir', type=Path)
    args = parser.parse_args()
    try:
        from PySide6.QtCore import QTimer, QUrl, qVersion
        from PySide6.QtWidgets import QApplication
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError as error:
        parser.error('PySide6 / QtWebEngine 6 could not load: ' + str(error))
    app = QApplication(sys.argv[:1])
    view = QWebEngineView()
    view.show()
    if args.screenshot_dir:
        args.screenshot_dir.mkdir(parents=True, exist_ok=True)
    results = []
    scenarios = iter([(1280, 900, 100), (1280, 900, 150), (1280, 900, 200),
                      (900, 640, 150), (390, 844, 100), (390, 844, 125)])
    current = None

    def next_scenario():
        nonlocal current
        current = next(scenarios, None)
        if current is None:
            passed = sum(row['passed'] for row in results)
            print(json.dumps({'runtime': 'Qt ' + qVersion(), 'checks': len(results),
                              'passed': passed, 'results': results}), flush=True)
            app.exit(0 if passed == len(results) else 1)
            return
        view.setFixedSize(current[0], current[1])
        QTimer.singleShot(120, lambda: view.page().runJavaScript('setup(' + str(current[2]) + ')',
            lambda _: QTimer.singleShot(150, read)))

    def read():
        view.page().runJavaScript('measure()', record)

    def record(value):
        try:
            row = json.loads(value)
        except (TypeError, ValueError):
            print('Passage browser fixture did not return its measurements.', file=sys.stderr)
            app.exit(2)
            return
        dialog = row['dialog']
        okay = (dialog['left'] >= -1 and dialog['right'] <= current[0] + 1
                and dialog['overflow'] <= 1 and row['viewport'] == list(current[:2])
                and row['action_count'] == 2 and row['disabled'] and row['descriptions']
                and row['label_only'] and len(row['reasons']) == 2)
        okay = okay and all(reason['left'] >= dialog['left'] and reason['right'] <= dialog['right']
                            and reason['overflow'] <= 1 and reason['opacity'] == '1'
                            for reason in row['reasons'])
        results.append({'viewport': current[:2], 'scale': current[2], 'passed': okay, **row})
        if args.screenshot_dir:
            view.grab().save(str(args.screenshot_dir / f'passages-{current[0]}-{current[2]}.png'))
        next_scenario()

    def loaded(okay):
        if okay:
            QTimer.singleShot(200, next_scenario)
        else:
            print('Passage browser fixture did not load.', file=sys.stderr)
            app.exit(2)

    def timeout():
        print('Passage layout browser probe timed out.', file=sys.stderr)
        app.exit(2)

    view.loadFinished.connect(loaded)
    view.setHtml(fixture(args.street_script), QUrl('https://passage-layout.invalid/'))
    QTimer.singleShot(20000, timeout)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
