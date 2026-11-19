/* Run the real inline Conversation renderer and transcript controller. These
 * checks use explicit geometry; Qt checks actual colors, contrast and wrapping. */
'use strict';
const assert=require('node:assert/strict');
const {test}=require('node:test');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createDOM}=require('./support/menu-dom.cjs');
const read=name=>fs.readFileSync(path.join(__dirname,'..',name),'utf8');
function renderer(source){
 const start=source.indexOf('function append('),end=source.indexOf('\nfunction connect()',start);
 assert.ok(start>=0&&end>start,'Served Conversation renderer must be present');
 return source.slice(start,end);
}
function boot({entry='web/index.html',transcript=false}={}){
 const {window,document,Event}=createDOM(),frames=[];
 const make=(tag,id,parent=document.body)=>{const n=document.createElement(tag);n.id=id;parent.append(n);return n;};
 const app=make('div','app'),log=make('div','log',app),form=make('form','input-form',app);
 make('input','input',form);const latest=make('button','conversation-latest',form);make('button','command-done',form);make('button','command-send',form);
 let top=0,content=0;log.clientHeight=200;
 Object.defineProperty(log,'scrollHeight',{get:()=>content});
 Object.defineProperty(log,'scrollTop',{get:()=>top,set:v=>{top=Math.max(0,Math.min(v,content-log.clientHeight));}});
 const append=log.appendChild.bind(log);log.appendChild=node=>{append(node);content+=100;return node;};
 Object.assign(window,{console,requestAnimationFrame:fn=>{frames.push(fn);return frames.length;},setTimeout:fn=>{frames.push(fn);return frames.length;}});
 vm.runInNewContext(renderer(read(entry)),window,{filename:entry+'#append'});
 if(transcript)vm.runInNewContext(read('web/mobile-layout.js'),window,{filename:'web/mobile-layout.js'});
 const flush=()=>{for(let i=0;frames.length;i++){assert.ok(i<50,'Animation frames settle');frames.shift()();}};
 flush();return {window,document,Event,log,latest,flush,
  append(kind,text,meta){window.append(kind,text,meta);flush();return log.lastElementChild;}};
}

test('legacy Character and system messages keep explicit readable role defaults',()=>{
 const f=boot();
 for(const kind of ['user','response'])assert.equal(f.append(kind,'The character acts.').dataset.conversationRole,'character');
 for(const kind of ['welcome','system'])assert.equal(f.append(kind,'The host responds.').dataset.conversationRole,'system');
 const error=f.append('error','Cannot do that.');assert.ok(error.classList.contains('error'));assert.equal(error.dataset.conversationRole,undefined);
});

test('explicit NPC messages receive ordinary or urgent roles without changing text',()=>{
 const f=boot(),text='Guard shouts at Player, “Stop!”\nThe second line remains intact.\n<script>not HTML</script>';
 for(const emphasis of ['normal','alert','shout']){
  const line=f.append('system',text,{role:'npc',emphasis});
  assert.equal(line.textContent,text);assert.equal(line.children.length,0);
  assert.equal(line.dataset.conversationRole,'npc');assert.ok(line.classList.contains('conversation-npc'));
  assert.equal(line.classList.contains('conversation-npc-'+emphasis),emphasis!=='normal');
 }
 assert.equal(f.log.children.length,3,'No transcript content is replaced or truncated');
});

test('urgent-looking player text and invalid metadata never impersonate an NPC alert',()=>{
 const f=boot(),text='I shout: THIEF! ALERT! <b>Stop now</b>';
 for(const meta of [undefined,null,'shout',{role:'character',emphasis:'shout'},
  {role:'not-a-role',emphasis:'alert'},{role:['npc'],emphasis:'shout'},
  {role:'npc',emphasis:'shout arbitrary-class'}]){
  const line=f.append('user',text,meta);assert.equal(line.textContent,text);
  assert.equal(line.dataset.conversationEmphasis,undefined);
  assert.ok(!line.classList.contains('conversation-npc-alert'));assert.ok(!line.classList.contains('conversation-npc-shout'));
 }
});

test('metadata may describe the source while transport type remains compatible',()=>{
 const f=boot();
 assert.equal(f.append('system','NPC words',{role:'npc'}).dataset.conversationRole,'npc');
 assert.equal(f.append('system','Player words',{role:'character'}).dataset.conversationRole,'character');
 assert.equal(f.append('response','Game notice',{role:'system'}).dataset.conversationRole,'system');
});

test('colored NPC alerts preserve reading position, unread controls, multiline history and inline actions',()=>{
 const f=boot({transcript:true});
 for(let i=0;i<6;i++)f.append('system','Earlier line '+i+'\nwith a second line.');
 assert.equal(f.log.scrollTop,400);
 f.log.scrollTop=200;f.log.dispatchEvent(new f.Event('wheel',{deltaY:-100}));f.log.dispatchEvent(new f.Event('scroll'));
 const prior=f.log.firstElementChild,action=f.document.createElement('button');let clicks=0;
 action.textContent='Open existing quest';action.onclick=()=>clicks++;prior.append(action);
 f.append('system','The guard warns you.',{role:'npc',emphasis:'alert'});
 assert.equal(f.log.scrollTop,200);assert.equal(f.latest.hidden,false);assert.match(f.latest.textContent,/New messages \(1\)/);
 action.click();assert.equal(clicks,1);assert.equal(prior.textContent,'Earlier line 0\nwith a second line.Open existing quest');
 f.latest.click();f.flush();assert.equal(f.log.scrollTop,500);assert.equal(f.latest.hidden,true);
 f.log.scrollTop=200;f.log.dispatchEvent(new f.Event('wheel',{deltaY:-100}));
 f.append('user','> look');assert.equal(f.log.scrollTop,600);assert.equal(f.latest.hidden,true);
});

test('root and web entrypoints use the same renderer and forward structured metadata',()=>{
 const root=read('index.html'),web=read('web/index.html');
 assert.equal(renderer(root),renderer(web));
 for(const source of [root,web])assert.ok(source.includes("append(msg.type || 'response', displayText || JSON.stringify(msg), msg.conversation)"));
 const f=boot({entry:'index.html'});assert.equal(f.append('system','NPC words',{role:'npc',emphasis:'shout'}).dataset.conversationEmphasis,'shout');
});
