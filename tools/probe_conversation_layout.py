#!/usr/bin/env python3
"""Check Conversation role colors, contrast, type size and wrapping in Qt 6.

Run with PySide6 / QtWebEngine installed:
  QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu --no-sandbox' \
    python tools/probe_conversation_layout.py

This uses the real app CSS, inline message renderer, and transcript controller.
No game server, account, world, or network service is used.
"""
import argparse
import json
from pathlib import Path
import re
import sys

from probe_location_panel_layout import ROOT, fixture as workspace_fixture


def fixture():
    source = (ROOT / 'web/index.html').read_text()
    start = source.index('function append(')
    end = source.index('\nfunction connect()', start)
    html = workspace_fixture(ROOT / 'web/workspace.js')
    html += '<script>' + source[start:end] + '</script>'
    html += r'''<script>
const samples=[
 ['system','Connected. Your game is ready.',null,'system'],
 ['user','> I shout ALERT!\nThis is the character\'s own text.',null,'character'],
 ['response','You move into the square.',null,'character'],
 ['system','Mira says, “I heard a shout yesterday.”',{role:'npc',emphasis:'normal'},'npc'],
 ['system','Watch captain shouts, “Stop! That cabinet belongs to the magistrate.”',{role:'npc',emphasis:'shout'},'shout'],
 ['system','A nearby resident warns that the bridge is unsafe.',{role:'npc',emphasis:'alert'},'alert'],
 ['error','That command is unavailable.',null,'error']
];
function showConversation(scale){
 resetPanel(scale);window.ExpansePanels.reveal('conversation');
 const log=document.getElementById('log');log.replaceChildren();window.ExpanseTranscript.jumpToLatest();
 for(const [kind,text,metadata] of samples)append(kind,text,metadata);
 log.scrollTop=0;
}
function conversationMeasurements(){
 const log=document.getElementById('log'),bounds=log.getBoundingClientRect();
 let owner=log,background='rgba(0, 0, 0, 0)';
 while(owner&&background==='rgba(0, 0, 0, 0)'){background=getComputedStyle(owner).backgroundColor;owner=owner.parentElement;}
 return JSON.stringify({viewport:[innerWidth,innerHeight],background,baseSize:parseFloat(getComputedStyle(log).fontSize),
  rows:[...log.querySelectorAll('.line')].map((line,i)=>{const style=getComputedStyle(line),box=line.getBoundingClientRect();
   return {role:samples[i][3],color:style.color,size:parseFloat(style.fontSize),weight:Number(style.fontWeight),
    textPreserved:line.textContent===samples[i][1],overflow:line.scrollWidth-line.clientWidth,
    withinWidth:box.left>=bounds.left&&box.right<=bounds.right,visible:box.width>0};})});
}
</script>'''
    return html


def rgb(value):
    return [int(channel) for channel in re.findall(r'\d+', value)[:3]]


def contrast(foreground, background):
    def luminance(color):
        values = [channel / 255 for channel in color]
        values = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
                  for value in values]
        return sum(value * weight for value, weight in zip(values, [.2126, .7152, .0722]))
    a, b = sorted([luminance(foreground), luminance(background)])
    return (b + .05) / (a + .05)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
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
    cases = iter([(1280, 900, 100), (1280, 900, 150), (390, 844, 100), (390, 844, 125)])
    current = None
    colors = {'system': [127, 209, 164], 'character': [255, 255, 255], 'npc': [183, 189, 200],
              'alert': [255, 133, 133], 'shout': [255, 133, 133], 'error': [224, 112, 112]}

    def next_case():
        nonlocal current
        current = next(cases, None)
        if current is None:
            passed = sum(row['passed'] for row in results)
            print(json.dumps({'runtime': 'Qt ' + qVersion(), 'checks': len(results),
                              'passed': passed, 'results': results}), flush=True)
            app.exit(0 if passed == len(results) else 1)
            return
        view.setFixedSize(current[0], current[1])
        QTimer.singleShot(120, lambda: view.page().runJavaScript('showConversation(' + str(current[2]) + ')',
            lambda _: QTimer.singleShot(150, read)))

    def read():
        view.page().runJavaScript('conversationMeasurements()', record)

    def record(value):
        try:
            data = json.loads(value)
        except (TypeError, ValueError):
            print('Conversation fixture did not return measurements.', file=sys.stderr)
            app.exit(2)
            return
        for row in data['rows']:
            ratio = row['size'] / data['baseSize']
            row['contrast'] = round(contrast(rgb(row['color']), rgb(data['background'])), 2)
            urgent = row['role'] in ('alert', 'shout')
            okay = (rgb(row['color']) == colors[row['role']] and row['contrast'] >= 4.5
                    and row['textPreserved'] and row['overflow'] <= 1 and row['withinWidth']
                    and row['visible'] and data['viewport'] == list(current[:2]))
            okay = okay and (row['weight'] >= 700 and 1.04 <= ratio <= 1.08 if urgent
                             else row['weight'] < 700 and abs(ratio - 1) <= .01)
            results.append({'viewport': current[:2], 'scale': current[2], 'passed': okay, **row})
        if args.screenshot_dir:
            view.grab().save(str(args.screenshot_dir / f'conversation-{current[0]}-{current[2]}.png'))
        next_case()

    def loaded(okay):
        if okay:
            QTimer.singleShot(200, next_case)
        else:
            print('Conversation fixture did not load.', file=sys.stderr)
            app.exit(2)

    def timeout():
        print('Conversation layout browser probe timed out.', file=sys.stderr)
        app.exit(2)

    view.loadFinished.connect(loaded)
    view.setHtml(fixture(), QUrl('https://conversation-layout.invalid/'))
    QTimer.singleShot(20000, timeout)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
