#!/usr/bin/env python3
"""Exercise the candidate world loader in an actual installed Qt WebEngine.

Uses a disposable loopback HTTP/WebSocket fixture and private browser profile.
Requires existing PySide6/QtWebEngine or Slicer Qt5 with its offscreen plugin;
no installer, game host, deployment, native cache bridge or user data is run.
Trace counts are WebSocket application JSON payloads, not TLS/frame overhead.
"""
import argparse
import asyncio
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile

from aiohttp import web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.public_media import PUBLIC_PRESENTATION, PublicMedia, presentation_packet


def digest(data):
    return hashlib.sha256(data).hexdigest()


QT_DRIVER = r'''
import json, os, qt, slicer
finished=False
qt.QTimer.singleShot(60000,lambda:slicer.app.exit(3))
w=slicer.qSlicerWebWidget()
def result(js,value):
    global finished
    if finished:return
    if js=='JSON.stringify(window.__probeComplete || null)' and value and value!='null':
        finished=True
        print('EXPANSE_BROWSER_RESULT '+value,flush=True)
        slicer.app.exit(0)
    else:qt.QTimer.singleShot(100,lambda:w.evalJS('JSON.stringify(window.__probeComplete || null)'))
w.connect('evalResult(QString,QString)',result)
w.url=os.environ['EXPANSE_BROWSER_PROBE_URL']
qt.QTimer.singleShot(100,lambda:w.evalJS('JSON.stringify(window.__probeComplete || null)'))
'''

QT6_DRIVER = r'''
import json, os, sys
from PySide6.QtCore import QCoreApplication, QEvent, QTimer, QUrl, qVersion
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
app=QApplication(sys.argv[:1])
profile=QWebEngineProfile('ExpanseMediaProbe',app)
profile.setPersistentStoragePath(os.path.join(os.environ['XDG_DATA_HOME'],'browser-profile'))
profile.setCachePath(os.path.join(os.environ['XDG_CACHE_HOME'],'http-cache'))
profile.setHttpCacheType(QWebEngineProfile.NoCache)
page=QWebEnginePage(profile,app)
finished=False
timer=QTimer()
def result(value):
    global finished
    if finished or not value or value=='null':return
    finished=True;timer.stop()
    print('EXPANSE_BROWSER_RUNTIME '+json.dumps({'qt_version':qVersion(),'http_cache':'NoCache','persistent_profile':True}),flush=True)
    print('EXPANSE_BROWSER_RESULT '+value,flush=True)
    app.exit(0)
timer.timeout.connect(lambda:page.runJavaScript('JSON.stringify(window.__probeComplete || null)',result))
timer.start(100)
QTimer.singleShot(60000,lambda:app.exit(3))
page.load(QUrl(os.environ['EXPANSE_BROWSER_PROBE_URL']))
status=app.exec()
page.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
profile.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
raise SystemExit(status)
'''


PAGE = r'''<!doctype html><meta charset="utf-8"><title>World media fixture</title>
<script src="/world-assets.js"></script><script>
const scenario=__SCENARIO__, expected=__EXPECTED__, paths=Object.keys(expected);
const HASH='expanse-public-world-media-v1';
const assert=(ok,message)=>{if(!ok)throw Error(message);};
const sum=rows=>rows.reduce((n,row)=>n+row.size,0);
function db(){return new Promise((resolve,reject)=>{const r=indexedDB.open(HASH,1);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(Error('Open IndexedDB failed'));});}
async function rows(){const d=await db();return new Promise((resolve,reject)=>{const t=d.transaction('blobs','readonly'),r=t.objectStore('blobs').getAll();r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(Error('Read cache failed'));t.oncomplete=()=>d.close();});}
async function corrupt(){const d=await db(),info=expected[paths[0]];return new Promise((resolve,reject)=>{const t=d.transaction('blobs','readwrite'),s=t.objectStore('blobs');s.get(info.hash).onsuccess=e=>{const row=e.target.result;assert(row,'No persisted row to corrupt');row.blob=new Blob([new Uint8Array(row.size)],{type:row.mime});s.put(row);};t.oncomplete=()=>{d.close();resolve();};t.onerror=()=>reject(Error('Corrupt test row failed'));});}
async function sha(blob){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await blob.arrayBuffer())),n=>n.toString(16).padStart(2,'0')).join('');}
function socket(world){return new Promise((resolve,reject)=>{const ws=new WebSocket(location.origin.replace('http','ws')+'/ws?scenario='+encodeURIComponent(scenario)+'&world='+world);window.expanseAssetSend=packet=>{if(ws.readyState!==1)return false;ws.send(JSON.stringify(packet));return true;};ws.onmessage=e=>{const row=JSON.parse(e.data);ExpanseAssets.receive(row);if(row.type==='map')resolve(ws);};ws.onerror=()=>reject(Error('WebSocket fixture unavailable'));});}
async function loadAll(){for(const path of paths){const asset=await ExpanseAssets.get(path),info=expected[path];assert(asset,'Asset missing '+path);assert(asset.blob.size===info.size,'Wrong size '+path);assert(await sha(asset.blob)===info.hash,'Wrong digest '+path);if(path==='assets/terrain/tiles.png'){const check=createImageBitmap(asset.blob).then(image=>{const ok=image.width>0&&image.height>0;image.close();return ok;}).catch(()=>false);window.__pngDecoded=await Promise.race([check,new Promise(resolve=>setTimeout(()=>resolve(false),1500))]);}asset.release?.();}}
(async()=>{
 const started=performance.now();
 if(scenario==='corruption')await corrupt();
 let ws=await socket('main');
 await loadAll();
 const before=ExpanseAssets.statistics();
 const repeated=await ExpanseAssets.get(paths[0]);
 const after=ExpanseAssets.statistics();
 assert(['infoRequests','assetRequests','downloadedBytes'].every(key=>before[key]===after[key]),'In-memory repeat used transport');
 repeated?.release?.();
 const cached=await rows();
 const result={scenario,origin:location.origin,ua:navigator.userAgent,secure:window.isSecureContext,
   stats:ExpanseAssets.statistics(),cache_entries:cached.length,cache_bytes:sum(cached),
   validated_assets:paths.length,png_decoded:!!window.__pngDecoded,memory_repeat_no_traffic:true,elapsed_ms:Math.round(performance.now()-started)};
 await fetch('/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(result)});
 if(scenario==='cold'){location.href='/probe?scenario=reload';return;}
 if(scenario==='corruption'){
   ExpanseAssets.disconnect();ws.close();ws=await socket('changed');
   const path='assets/terrain/index.json',asset=await ExpanseAssets.get(path);
   assert(asset,'Changed host world did not return media');
   assert(await sha(asset.blob)===__CHANGED_HASH__,'Changed world reused old bytes');
   const switched={scenario:'world-switch',origin:location.origin,stats:ExpanseAssets.statistics(),
     returned_sha256:await sha(asset.blob),cache_entries:(await rows()).length};
   await fetch('/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(switched)});
 }
 if(scenario==='host-b'){location.href=__RETURN_ORIGIN__+'/probe?scenario=return-host-a';return;}
 ws.close();window.__probeComplete={success:true,scenario};
})().catch(async error=>{const result={scenario,success:false,error:String(error),stack:error.stack};
 try{await fetch('/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(result)});}catch{}
 window.__probeComplete=result;});
</script>'''


def world_bytes(path):
    raw = path.read_bytes()
    if path.suffix == '.run':
        marker = b'__EXPANSE_PAYLOAD__\n'
        offset = raw.find(marker)
        if offset < 0:
            raise ValueError('Installer payload marker missing.')
        with tarfile.open(fileobj=io.BytesIO(raw[offset + len(marker):]), mode='r:gz') as archive:
            member = archive.getmember('worlds/Expanse-Wild-Lands-1.9.15.expanse')
            if not member.isfile() or member.size > 32 * 1024 * 1024:
                raise ValueError('Unexpected embedded world.')
            return archive.extractfile(member).read()
    return raw


async def probe(args):
    source = (ROOT / 'web/world-assets.js').read_bytes()
    source_names = ('web/world-assets.js','engine/public_media.py','engine/world_package.py',
                    'server/game_server.py','web/index.html','web/visual-map.js',
                    'web/character-sheets.js','web/world-audio.js')
    source_hashes = {name:digest((ROOT/name).read_bytes()) for name in source_names}
    world = world_bytes(args.world)
    results, traces, errors = [], [], []
    with tempfile.TemporaryDirectory(prefix='expanse-world-browser-') as temporary:
        private = Path(temporary)
        main = private / 'world'
        changed = private / 'changed-world'
        main.mkdir(); changed.mkdir()
        expected = {}
        with zipfile.ZipFile(io.BytesIO(world)) as archive:
            for path, (size, checksum, mime) in PUBLIC_PRESENTATION.items():
                data = archive.read(path)
                if len(data) != size or digest(data) != checksum:
                    raise ValueError('Reviewed source media mismatch: ' + path)
                target = main / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
                expected[path] = {'size':size, 'hash':checksum, 'mime':mime}
        # Valid but unreviewed content must stay transient, never reuse old bytes.
        altered = (main / 'assets/terrain/index.json').read_bytes().replace(b'"seeds":7', b'"seeds":6')
        if altered == (main / 'assets/terrain/index.json').read_bytes():
            altered = altered.rstrip() + b' \n'
        target = changed / 'assets/terrain/index.json'; target.parent.mkdir(parents=True); target.write_bytes(altered)
        policy = PublicMedia(main)
        policies = {'main': policy, 'changed': PublicMedia(changed)}
        source_hash = digest(source)
        sites = []
        origin_a = None

        async def page(request):
            scenario = request.query.get('scenario','cold')
            body = (PAGE.replace('__SCENARIO__',json.dumps(scenario))
                    .replace('__EXPECTED__',json.dumps(expected,separators=(',',':')))
                    .replace('__CHANGED_HASH__',json.dumps(digest(altered)))
                    .replace('__RETURN_ORIGIN__',json.dumps(origin_a)))
            return web.Response(text=body,content_type='text/html',headers={'Cache-Control':'no-store'})

        async def script(request):
            return web.Response(body=source,content_type='text/javascript',headers={'Cache-Control':'no-store'})

        async def result(request):
            row = await request.json(); results.append(row)
            print(json.dumps({'completed_scenario':row.get('scenario'),'stats':row.get('stats'),'error':row.get('error')}),flush=True)
            if row.get('success') is False: errors.append(row)
            return web.json_response({'ok':True})

        async def websocket(request):
            ws = web.WebSocketResponse(compress=False)
            await ws.prepare(request)
            scenario = request.query['scenario']; selection = request.query.get('world','main')
            folder = main if selection == 'main' else changed
            trace = {'scenario':scenario,'world':selection,'origin':str(request.host),
                     'info_requests':0,'asset_requests':0,'raw_asset_bytes':0,'inbound_json_bytes':0,
                     'outbound_json_bytes':0,'metadata_json_bytes':0,'asset_json_bytes':0}
            traces.append(trace)
            await ws.send_json({'type':'map','media_world':scenario+'-'+selection,'media_protocol':1})
            async for message in ws:
                if message.type != web.WSMsgType.TEXT: continue
                trace['inbound_json_bytes'] += len(message.data.encode())
                packet = json.loads(message.data)
                if packet.get('command') == 'world asset info':
                    trace['info_requests'] += 1
                    info = await asyncio.to_thread(policies[selection].info,packet['name'])
                    row = {'type':'world_asset_info','name':packet['name'],'request_id':packet['request_id'],
                           **(info if info else {'scope':'transient'})}
                    kind = 'metadata_json_bytes'
                elif packet.get('command') == 'world asset':
                    trace['asset_requests'] += 1
                    row = await asyncio.to_thread(presentation_packet,folder,packet.get('name'),packet.get('offset',0))
                    row['request_id'] = packet['request_id']
                    trace['raw_asset_bytes'] += len(base64.b64decode(row.get('data','')))
                    kind = 'asset_json_bytes'
                else: raise AssertionError('Unexpected fixture command.')
                payload = json.dumps(row)
                trace['outbound_json_bytes'] += len(payload.encode()); trace[kind] += len(payload.encode())
                await ws.send_str(payload)
            return ws

        for _ in range(2):
            app = web.Application()
            app.add_routes([web.get('/probe',page),web.get('/world-assets.js',script),web.post('/result',result),web.get('/ws',websocket)])
            runner = web.AppRunner(app); await runner.setup()
            site = web.TCPSite(runner,'127.0.0.1',0); await site.start()
            sites.append((runner,site,site._server.sockets[0].getsockname()[1]))
        origin_a = 'http://127.0.0.1:'+str(sites[0][2]); origin_b = 'http://127.0.0.1:'+str(sites[1][2])
        driver = private / 'qt-driver.py'; driver.write_text(QT6_DRIVER if args.qt_python else QT_DRIVER)
        dirs = {name:private/name for name in ('config','cache','data','tmp')}
        for path in dirs.values():path.mkdir(mode=0o700)
        env = dict(os.environ,QT_QPA_PLATFORM='offscreen',
                   QT_QPA_PLATFORM_PLUGIN_PATH=args.qt_plugins,QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu',
                   XDG_CONFIG_HOME=str(dirs['config']),XDG_CACHE_HOME=str(dirs['cache']),
                   XDG_DATA_HOME=str(dirs['data']),TMPDIR=str(dirs['tmp']))
        commands = [str(args.slicer),'--no-splash','--no-main-window','--disable-cli-modules',
                    '--disable-loadable-modules','--disable-scripted-loadable-modules','--ignore-slicerrc',
                    '--python-script',str(driver)]
        if args.qt_python:
            commands=[str(args.qt_python),str(driver)]
            for name in ('QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH'):
                env.pop(name,None)
            env.update(QTWEBENGINE_DISABLE_SANDBOX='1',QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu --no-sandbox')
        processes = []
        try:
            for label,origin,scenario in [('cold-and-reload',origin_a,'cold'),('browser-restart',origin_a,'restart'),
                                          ('corruption-and-world-switch',origin_a,'corruption'),('changed-host-and-return',origin_b,'host-b')]:
                started = time.perf_counter()
                process_env = dict(env,EXPANSE_BROWSER_PROBE_URL=origin+'/probe?scenario='+scenario)
                completed = await asyncio.to_thread(subprocess.run,commands,env=process_env,timeout=70,capture_output=True,text=True)
                row={'process':label,'exit_code':completed.returncode,'elapsed_ms':round((time.perf_counter()-started)*1000),
                     'stdout':completed.stdout[-12000:],'stderr':completed.stderr[-8000:]}
                processes.append(row)
                print(json.dumps({'process':label,'exit_code':completed.returncode,'result_count':len(results),'trace_count':len(traces)}),flush=True)
                if completed.returncode or 'EXPANSE_BROWSER_RESULT' not in completed.stdout:
                    raise AssertionError('Real browser process failed: '+label+' '+completed.stdout[-1500:]+' '+completed.stderr[-1500:])
                if errors:raise AssertionError(str(errors))
            by_case={row['scenario']:row for row in results}
            for name in ['cold','reload','restart','corruption','world-switch','host-b','return-host-a']:
                if name not in by_case:raise AssertionError('Missing scenario '+name)
            n=len(expected); raw_total=sum(row['size'] for row in expected.values())
            for name in ('cold','host-b'):
                row=by_case[name]['stats']
                if row['persistentWrites']!=n or row['persistentHits'] or row['downloadedBytes']!=raw_total:
                    raise AssertionError('Cold cache did not fetch/write each reviewed asset: '+name+' '+str(row))
            for name in ('reload','restart','return-host-a'):
                row=by_case[name]['stats']
                if row['persistentHits']!=n or row['assetRequests'] or row['downloadedBytes']:
                    raise AssertionError('Real persistent cache did not survive navigation/restart: '+name+' '+str(row))
            row=by_case['corruption']['stats']
            if row['integrityFailures']!=1 or row['persistentHits']!=n-1 or row['downloadedBytes']!=expected[next(iter(expected))]['size']:
                raise AssertionError('Corrupt cache did not repair exactly one asset: '+str(row))
            if by_case['world-switch']['stats']['transientDownloads']!=1:
                raise AssertionError('Unreviewed changed media was not transient.')
            if source_hashes != {name:digest((ROOT/name).read_bytes()) for name in source_names}:
                raise AssertionError('Candidate source changed during browser verification; rerun.')
            outcome='pass'
        except Exception as exc:
            errors.append({'probe_error':str(exc)});outcome='fail'
        finally:
            for runner,_,_ in sites:await runner.cleanup()
        storage_files=[path for path in private.rglob('*') if path.is_file() and ('IndexedDB' in str(path) or 'Local Storage' in str(path))]
        safe_processes=[{key:row[key] for key in ('process','exit_code','elapsed_ms')} for row in processes]
        if args.diagnostics is not None:
            args.diagnostics.parent.mkdir(parents=True,exist_ok=True)
            args.diagnostics.write_text(json.dumps({'processes':processes,'results':results,'traces':traces,'errors':errors},indent=2)+'\n')
        for row in results:
            if 'origin' in row:row['host']='a' if row.pop('origin')==origin_a else 'b'
            row.pop('stack',None)
        for row in traces:row['host']='a' if row.pop('origin')==origin_a.removeprefix('http://') else 'b'
        errors=[{'error':'Real browser scenario failed; inspect local scratch diagnostics.'}] if errors else []
        evidence={'schema_version':1,'status':outcome,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  'world_archive_sha256':digest(world),'world_assets_source_sha256':source_hash,
                  'public_media_source_sha256':digest((ROOT/'engine/public_media.py').read_bytes()),
                  'candidate_source_sha256':source_hashes,
                  'measurement':'actual Qt WebEngine HTML, WebSocket, WebCrypto SHA256 and IndexedDB; private profile reused across four processes',
                  'executed_modules':['web/world-assets.js','engine/public_media.py'],
                  'runtime':{'browser_engine':'PySide6 / QtWebEngine 6.10.3' if args.qt_python else 'installed QtWebEngine 5.15.2 / Chromium 83',
                             'qt_plugins':'runtime bundled Qt6 offscreen plugin' if args.qt_python else 'system Qt5 offscreen plugin',
                             'qt_platform':'offscreen','chromium_flags':'--disable-gpu --no-sandbox' if args.qt_python else '--disable-gpu',
                             'profile_http_cache':'NoCache' if args.qt_python else 'default; fixture HTTP responses are no-store',
                             'standalone_chromium_limit':'AF_UNIX socket() is forbidden; installed Qt engine uses socketpair',
                             'engine_limit':'Browser subprocess sandbox disabled for isolated local fixtures; runtime security controls remain unchanged.' if args.qt_python else 'QtWebEngine5.15.2 Chromium83, older than shipped desktop Qt6.10.3; bundled Slicer emits sandbox-disabled message without probe override'},
                  'scope_limits':['Loopback fixture authenticates no real game account and mutates no live world, account or save.',
                                  'Fixture uses actual v1 PublicMedia.info and presentation_packet runtime handlers with exact bundled reviewed bytes; not full GameServer gameplay.',
                                  'Trace counts UTF8 WebSocket JSON application payloads only; excludes HTTP/TLS/WebSocket frame bytes and compression.',
                                  'PNG createImageBitmap decoding is an optional separate rendering probe; no visible display or physical device is exercised.',
                                  'No native installed-asset bridge is exercised; pure browser persistent cache only.',
                                  'Application-shell HTTP cache is measured separately.'],
                  'reviewed_asset_count':len(expected),'reviewed_asset_bytes':sum(row['size'] for row in expected.values()),
                  'results':results,'websocket_traces':traces,'browser_processes':safe_processes,'persistent_storage':{'file_count':len(storage_files),'bytes':sum(path.stat().st_size for path in storage_files)},'errors':errors}
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(evidence,indent=2)+'\n')
        print(json.dumps({'status':outcome,'results':results,'traces':traces,'errors':errors,'output':str(args.output)},indent=2))
        return outcome=='pass'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--world',type=Path,required=True,help='.expanse file or Linux .run containing the unchanged world')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--diagnostics',type=Path,help='Optional private diagnostic file; do not publish raw browser logs.')
    parser.add_argument('--slicer',type=Path,default=Path('/opt/slicer/5.10.0/Slicer'))
    parser.add_argument('--qt-python',type=Path,help='Existing Python interpreter with PySide6/QtWebEngine; otherwise use existing Slicer Qt5.')
    parser.add_argument('--qt-plugins',default='/usr/lib/x86_64-linux-gnu/qt5/plugins/platforms')
    args=parser.parse_args()
    raise SystemExit(0 if asyncio.run(probe(args)) else 1)

if __name__=='__main__':main()
