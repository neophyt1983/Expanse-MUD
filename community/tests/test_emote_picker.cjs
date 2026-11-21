'use strict';
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),test=require('node:test');
const source=fs.readFileSync(path.join(__dirname,'../static/emote-picker.js'),'utf8');

function boot({value='',start=value.length,end=start,maxLength=4000,supported=true,includeField=true}={}){
 const counters={focus:0,ranges:0,submits:0};let click;
 const field={value,maxLength,selectionStart:start,selectionEnd:end,
  setRangeText:supported?function(code,a,b,mode){assert.equal(mode,'end');this.value=this.value.slice(0,a)+code+this.value.slice(b);this.selectionStart=this.selectionEnd=a+code.length;counters.ranges++;}:undefined,
  focus(){counters.focus++;}};
 const reportField={value:'report stays plain'};
 const button={dataset:{emote:':wave:'},hidden:true,addEventListener(e,fn){assert.equal(e,'click');click=fn;}};
 const code={hidden:false},help={textContent:'Type a code below into your message.'},status={textContent:''};
 const picker={open:true,closest(sel){assert.equal(sel,'form');return {querySelector(selector){assert.equal(selector,'textarea[name="body"]');return includeField?field:null;},submit(){counters.submits++;}};},
  querySelector(sel){return {'[data-emote-help]':help,'[data-emote-status]':status}[sel];},
  querySelectorAll(sel){return {'button[data-emote]':[button],'[data-emote-fallback]':[code]}[sel];}};
 vm.runInNewContext(source,{document:{querySelectorAll(sel){assert.equal(sel,'[data-forum-emotes]');return [picker];}}});
 return {field,button,help,status,picker,code,counters,reportField,click:()=>click?.()};
}

test('inserts plain code at cursor, restores focus, does not submit or change report text',()=>{
 const f=boot({value:'Hi there',start:3});
 assert.equal(f.button.hidden,false);assert.equal(f.code.hidden,true);
 f.click();
 assert.equal(f.field.value,'Hi :wave:there');assert.equal(f.field.selectionStart,9);
 assert.equal(f.field.selectionEnd,9);assert.equal(f.picker.open,false);
 assert.equal(f.counters.focus,1);assert.equal(f.counters.submits,0);
 assert.equal(f.reportField.value,'report stays plain');
});

test('explicit selection replacement respects message limit and saved draft',()=>{
 const f=boot({value:'Keep old',start:5,end:8,maxLength:11});
 f.click();assert.equal(f.field.value,'Keep :wave:');assert.equal(f.field.selectionStart,11);
 const full=boot({value:'123456',maxLength:6});
 full.click();assert.equal(full.field.value,'123456');assert.equal(full.counters.ranges,0);
 assert.equal(full.picker.open,true);assert.match(full.status.textContent,/not enough room/);
});

test('fallback remains visible when entry field or editor API is unavailable',()=>{
 for(const args of [{supported:false},{includeField:false}]){
  const f=boot(args);f.click();assert.equal(f.button.hidden,true);
  assert.equal(f.code.hidden,false);assert.equal(f.counters.ranges,0);
  assert.match(f.help.textContent,/Type a code/);
 }
});
