/* Provenance: copied from the existing Expanse menu regression helper at
 * audit-mainline/verification/navigation/menu-dom.cjs, originally shipped in
 * review-tests/web/menu-dom.cjs. This project copy is distributed with the
 * repository license (GPL-3.0; see ../../LICENSE). No external DOM package.
 * Apart from this provenance header, the helper is unchanged.
 */
/* Explicit DOM/event test double for executing the real menu scripts.
 * This is not a browser, CSS engine, layout engine, or accessibility renderer.
 * Geometry is fixed test data; only DOM construction, events, and mutations
 * should be asserted with it. Unsupported selector syntax throws explicitly.
 */
'use strict';

function createDOM(tree){
 let document=null,window=null;
 const observers=new Set();

 class Event{
  constructor(type,options={}){this.type=String(type);this.bubbles=!!options.bubbles;this.cancelable=!!options.cancelable;this.composed=!!options.composed;this.defaultPrevented=false;this.target=null;this.currentTarget=null;this.eventPhase=0;this.isTrusted=false;Object.assign(this,options);this._stop=false;this._immediate=false;}
  preventDefault(){if(this.cancelable)this.defaultPrevented=true;}
  stopPropagation(){this._stop=true;}
  stopImmediatePropagation(){this._stop=this._immediate=true;}
  composedPath(){return [...(this._path||[])];}
 }
 class CustomEvent extends Event{constructor(type,options={}){super(type,options);this.detail=options.detail??null;}}
 class EventTarget{
  constructor(){this._listeners=new Map();}
  addEventListener(type,callback,options={}){
   if(!callback)return;const capture=options===true||!!options.capture,once=!!options.once;
   const rows=this._listeners.get(type)||[];
   if(!rows.some(r=>r.callback===callback&&r.capture===capture))rows.push({callback,capture,once});
   this._listeners.set(type,rows);
  }
  removeEventListener(type,callback,options={}){const capture=options===true||!!options.capture;this._listeners.set(type,(this._listeners.get(type)||[]).filter(r=>r.callback!==callback||r.capture!==capture));}
  _invoke(event,capture,phase){
   event.currentTarget=this;event.eventPhase=phase;
   for(const row of [...(this._listeners.get(event.type)||[])]){
    if(row.capture!==capture||!(this._listeners.get(event.type)||[]).includes(row))continue;
    if(row.once)this.removeEventListener(event.type,row.callback,{capture});
    if(typeof row.callback==='function')row.callback.call(this,event);else row.callback.handleEvent(event);
    if(event._immediate)return;
   }
   if(!capture&&typeof this['on'+event.type]==='function'){
    if(this['on'+event.type].call(this,event)===false)event.preventDefault();
   }
  }
  dispatchEvent(event){
   if(!event||typeof event.type!=='string')throw new TypeError('Expected an Event.');
   event.target=this;event._stop=event._immediate=false;
   const path=[this];let cursor=this;
   while(cursor.parentNode){cursor=cursor.parentNode;path.push(cursor);}
   if(cursor===document&&window)path.push(window);
   event._path=path;
   for(let i=path.length-1;i>0;i--){path[i]._invoke(event,true,1);if(event._stop)break;}
   if(!event._stop){this._invoke(event,true,2);if(!event._immediate)this._invoke(event,false,2);}
   if(event.bubbles&&!event._stop)for(let i=1;i<path.length;i++){path[i]._invoke(event,false,3);if(event._stop)break;}
   event.currentTarget=null;event.eventPhase=0;return !event.defaultPrevented;
  }
 }
 function mutation(record){
  for(const observer of observers)for(const {target,options} of observer.targets){
   if(record.target!==target&&!(options.subtree&&target.contains(record.target)))continue;
   if(record.type==='childList'&&!options.childList)continue;
   if(record.type==='attributes'&&(!options.attributes||(options.attributeFilter&&!options.attributeFilter.includes(record.attributeName))))continue;
   if(record.type==='characterData'&&!options.characterData)continue;
   observer.records.push({...record,addedNodes:[...(record.addedNodes||[])],removedNodes:[...(record.removedNodes||[])]});break;
  }
 }
 class MutationObserver{
  constructor(callback){this.callback=callback;this.targets=[];this.records=[];observers.add(this);}
  observe(target,options){this.targets=this.targets.filter(r=>r.target!==target);this.targets.push({target,options:{...options}});}
  disconnect(){this.targets=[];this.records=[];}
  takeRecords(){const rows=this.records;this.records=[];return rows;}
 }
 function flushMutations(limit=100){
  for(let pass=0;pass<limit;pass++){
   const pending=[...observers].filter(o=>o.records.length);
   if(!pending.length)return pass;
   for(const observer of pending){const records=observer.takeRecords();if(records.length)observer.callback(records,observer);}
  }
  throw Error('DOM double mutation delivery did not settle.');
 }
 class ResizeObserver{constructor(callback){this.callback=callback;}observe(){}unobserve(){}disconnect(){}}
 class Style{
  setProperty(name,value){this[name]=String(value);}
  getPropertyValue(name){return this[name]||'';}
  removeProperty(name){const old=this[name]||'';delete this[name];return old;}
  get cssText(){return this._cssText||'';}
  set cssText(value){for(const key of Object.keys(this))delete this[key];this._cssText=String(value);for(const piece of String(value).split(';')){const i=piece.indexOf(':');if(i<0)continue;const key=piece.slice(0,i).trim(),text=piece.slice(i+1).trim();this[key]=text;this[key.replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=text;}}
 }
 function splitTop(value,separator){
  const parts=[];let start=0,depth=0,quote=null,escaped=false;
  for(let i=0;i<value.length;i++){
   const char=value[i];if(escaped){escaped=false;continue;}if(char==='\\'){escaped=true;continue;}
   if(quote){if(char===quote)quote=null;continue;}if(char==='"'||char==="'"){quote=char;continue;}
   if(char==='('||char==='[')depth++;else if(char===')'||char===']')depth--;
   else if(depth===0&&char===separator){parts.push(value.slice(start,i).trim());start=i+1;}
  }
  parts.push(value.slice(start).trim());return parts.filter(Boolean);
 }
 function tokenize(selector){
  const parts=[];let buffer='',depth=0,quote=null,escaped=false,combinator=null;
  const push=()=>{if(buffer.trim()){parts.push({simple:buffer.trim(),combinator:parts.length?(combinator||' '):null});buffer='';combinator=null;}};
  for(const char of selector.trim()){
   if(escaped){buffer+=char;escaped=false;continue;}if(char==='\\'){buffer+=char;escaped=true;continue;}
   if(quote){buffer+=char;if(char===quote)quote=null;continue;}if(char==='"'||char==="'"){quote=char;buffer+=char;continue;}
   if(char==='('||char==='['){depth++;buffer+=char;continue;}if(char===')'||char===']'){depth--;buffer+=char;continue;}
   if(!depth&&/[>+~]/.test(char)){push();combinator=char;continue;}
   if(!depth&&/\s/.test(char)){push();if(parts.length&&!combinator)combinator=' ';continue;}
   buffer+=char;
  }
  push();return parts;
 }
 function attributeMatches(node,inside){
  const found=inside.trim().match(/^([\w:-]+)\s*(?:([~|^$*]?=)\s*(?:"((?:\\.|[^"\\])*)"|'((?:\\.|[^'\\])*)'|([^\s]+)))?\s*(?:i)?$/);
  if(!found)throw Error('Unsupported attribute selector ['+inside+']');
  const [,name,op,a,b,c]=found,actual=node.getAttribute(name);if(!op)return actual!==null;if(actual===null)return false;
  const expected=(a??b??c??'').replace(/\\(.)/g,'$1');
  return op==='='?actual===expected:op==='^='?actual.startsWith(expected):op==='$='?actual.endsWith(expected):op==='*='?actual.includes(expected):op==='~='?actual.split(/\s+/).includes(expected):op==='|='?actual===expected||actual.startsWith(expected+'-'):false;
 }
 function simpleMatch(node,simple,scope){
  if(node.nodeType!==1)return simple===':scope'&&node===scope;
  let i=0;const tag=simple.match(/^(\*|[\w-]+)/);if(tag){if(tag[1]!=='*'&&node.tagName!==tag[1].toUpperCase())return false;i=tag[0].length;}
  while(i<simple.length){
   const char=simple[i++];
   if(char==='#'||char==='.'){
    const match=simple.slice(i).match(/^(?:\\.|[\w-])+/);if(!match)throw Error('Bad simple selector '+simple);i+=match[0].length;const name=match[0].replace(/\\(.)/g,'$1');
    if(char==='#'?node.id!==name:!node.classList.contains(name))return false;
   }else if(char==='['){
    let end=i,quote=null,escaped=false;for(;end<simple.length;end++){const c=simple[end];if(escaped){escaped=false;continue;}if(c==='\\'){escaped=true;continue;}if(quote){if(c===quote)quote=null;}else if(c==='"'||c==="'")quote=c;else if(c===']')break;}
    if(!attributeMatches(node,simple.slice(i,end)))return false;i=end+1;
   }else if(char===':'){
    const match=simple.slice(i).match(/^[\w-]+/);if(!match)throw Error('Bad pseudo selector '+simple);const name=match[0];i+=name.length;let arg=null;
    if(simple[i]==='('){let depth=1,start=++i;for(;i<simple.length&&depth;i++){if(simple[i]==='(')depth++;if(simple[i]===')')depth--;}arg=simple.slice(start,i-1);}
    if(name==='scope'){if(node!==scope)return false;}
    else if(name==='not'){if(matches(node,arg,scope))return false;}
    else if(name==='is'||name==='where'){if(!matches(node,arg,scope))return false;}
    else if(name==='has'){if(!queryAll(node,arg).length)return false;}
    else if(name==='popover-open'){if(!node._popoverOpen)return false;}
    else if(name==='modal'){if(!node.open||!node._modal)return false;}
    else if(name==='disabled'){if(!node.disabled)return false;}
    else if(name==='enabled'){if(node.disabled)return false;}
    else if(name==='checked'){if(!(node.checked||node.selected))return false;}
    else if(name==='first-child'){if(node.parentElement?.firstElementChild!==node)return false;}
    else if(name==='last-child'){if(node.parentElement?.lastElementChild!==node)return false;}
    else if(name==='empty'){if(node.children.length||node.textContent)return false;}
    else if(name==='focus'){if(document.activeElement!==node)return false;}
    else throw Error('Unsupported pseudo selector :'+name);
   }else throw Error('Unsupported selector '+simple);
  }
  return true;
 }
 function matches(node,selector,scope=node){
  return splitTop(String(selector),',').some(group=>{
   const tokens=tokenize(group);
   function at(current,index){
    if(!current||index<0||!simpleMatch(current,tokens[index].simple,scope))return false;if(index===0)return true;
    const operator=tokens[index].combinator;
    if(operator==='>')return at(current.parentNode,index-1);
    if(operator==='+')return at(current.previousElementSibling,index-1);
    if(operator==='~'){for(let prev=current.previousElementSibling;prev;prev=prev.previousElementSibling)if(at(prev,index-1))return true;return false;}
    for(let parent=current.parentNode;parent;parent=parent.parentNode)if(at(parent,index-1))return true;
    return false;
   }
   return tokens.length&&at(node,tokens.length-1);
  });
 }
 function queryAll(root,selector){const found=[];const visit=node=>{for(const child of node.childNodes){if(child.nodeType===1&&matches(child,selector,root))found.push(child);visit(child);}};visit(root);return found;}
 function dataKey(key){return 'data-'+String(key).replace(/[A-Z]/g,c=>'-'+c.toLowerCase());}

 class Node extends EventTarget{
  constructor(tag='',type=1,text=''){
   super();this.nodeType=type;this.tagName=type===1?String(tag).toUpperCase():undefined;this.nodeName=type===3?'#text':type===9?'#document':type===11?'#document-fragment':this.tagName;
   this.parentNode=null;this.childNodes=[];this._attributes=new Map();this._text=String(text);this._value=undefined;this._selected=false;this._modal=false;this._popoverOpen=false;this.style=new Style();this.scrollTop=0;this.scrollLeft=0;this.clientWidth=640;this.clientHeight=480;this.scrollWidth=640;this.scrollHeight=480;this.offsetLeft=0;this.offsetTop=0;this._rect=null;this.ownerDocument=document;
   this.dataset=new Proxy({}, {get:(_,key)=>this.getAttribute(dataKey(key))??undefined,set:(_,key,value)=>{this.setAttribute(dataKey(key),value);return true;},deleteProperty:(_,key)=>{this.removeAttribute(dataKey(key));return true;},ownKeys:()=>[...this._attributes.keys()].filter(k=>k.startsWith('data-')).map(k=>k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())),getOwnPropertyDescriptor:()=>({enumerable:true,configurable:true})});
   this.classList={contains:name=>this.className.split(/\s+/).includes(name),add:(...names)=>{this.className=[...new Set([...this.className.split(/\s+/).filter(Boolean),...names])].join(' ');},remove:(...names)=>{this.className=this.className.split(/\s+/).filter(n=>n&&!names.includes(n)).join(' ');},toggle:(name,force)=>{const on=force===undefined?!this.classList.contains(name):!!force;if(on)this.classList.add(name);else this.classList.remove(name);return on;},replace:(oldName,newName)=>{if(!this.classList.contains(oldName))return false;this.classList.remove(oldName);this.classList.add(newName);return true;}};
  }
  get children(){return this.childNodes.filter(n=>n.nodeType===1);}
  get firstChild(){return this.childNodes[0]||null;}get lastChild(){return this.childNodes.at(-1)||null;}
  get firstElementChild(){return this.children[0]||null;}get lastElementChild(){return this.children.at(-1)||null;}
  get childElementCount(){return this.children.length;}
  get parentElement(){return this.parentNode?.nodeType===1?this.parentNode:null;}
  get nextSibling(){return this.parentNode?.childNodes[this.parentNode.childNodes.indexOf(this)+1]||null;}
  get previousSibling(){return this.parentNode?.childNodes[this.parentNode.childNodes.indexOf(this)-1]||null;}
  get nextElementSibling(){if(!this.parentNode)return null;const siblings=this.parentNode.children;return siblings[siblings.indexOf(this)+1]||null;}
  get previousElementSibling(){if(!this.parentNode)return null;const siblings=this.parentNode.children;return siblings[siblings.indexOf(this)-1]||null;}
  get isConnected(){let root=this;while(root.parentNode)root=root.parentNode;return root===document;}
  contains(node){for(let current=node;current;current=current.parentNode)if(current===this)return true;return false;}
  _node(value){return value instanceof Node?value:document.createTextNode(String(value));}
  append(...values){for(const value of values)this.insertBefore(this._node(value),null);}
  appendChild(node){this.insertBefore(node,null);return node;}
  prepend(...values){const before=this.firstChild;for(const value of values)this.insertBefore(this._node(value),before);}
  before(...values){if(!this.parentNode)return;for(const value of values)this.parentNode.insertBefore(this._node(value),this);}
  after(...values){if(!this.parentNode)return;const parent=this.parentNode,before=this.nextSibling;for(const value of values)parent.insertBefore(this._node(value),before);}
  insertBefore(node,before){
   if(node.nodeType===11){for(const child of [...node.childNodes])this.insertBefore(child,before);return node;}
   if(before!==null&&!this.childNodes.includes(before))throw Error('insertBefore target is not a child.');
   if(node===before)return node;if(node===this||node.contains(this))throw Error('Cannot insert an ancestor into its child.');
   if(node.parentNode)node.parentNode.removeChild(node);
   const index=before===null?this.childNodes.length:this.childNodes.indexOf(before);this.childNodes.splice(index,0,node);node.parentNode=this;node.ownerDocument=document;
   mutation({type:'childList',target:this,addedNodes:[node],removedNodes:[]});return node;
  }
  removeChild(node){const index=this.childNodes.indexOf(node);if(index<0)throw Error('removeChild target is not a child.');this.childNodes.splice(index,1);node.parentNode=null;mutation({type:'childList',target:this,addedNodes:[],removedNodes:[node]});return node;}
  remove(){this.parentNode?.removeChild(this);}
  replaceChildren(...values){for(const child of [...this.childNodes])this.removeChild(child);this.append(...values);}
  replaceWith(...values){this.before(...values);this.remove();}
  get textContent(){return this.nodeType===3?this._text:this.childNodes.map(n=>n.textContent).join('');}
  set textContent(value){const text=String(value??'');if(this.nodeType===3){const oldValue=this._text;this._text=text;mutation({type:'characterData',target:this,oldValue});}else this.replaceChildren(...(text?[document.createTextNode(text)]:[]));}
  get innerText(){return this.textContent;}set innerText(value){this.textContent=value;}
  get innerHTML(){return this.textContent;}
  set innerHTML(value){if(String(value)!=='')throw Error('Nonempty innerHTML parsing is intentionally unsupported by this DOM double.');this.replaceChildren();}
  setAttribute(name,value){name=String(name);const oldValue=this.getAttribute(name),next=String(value);if(oldValue===next)return;this._attributes.set(name,next);if(name==='style')this.style.cssText=next;mutation({type:'attributes',target:this,attributeName:name,oldValue});}
  getAttribute(name){return this._attributes.has(String(name))?this._attributes.get(String(name)):null;}
  hasAttribute(name){return this._attributes.has(String(name));}
  removeAttribute(name){const oldValue=this.getAttribute(name);if(oldValue===null)return;this._attributes.delete(String(name));if(name==='style')this.style.cssText='';mutation({type:'attributes',target:this,attributeName:String(name),oldValue});}
  toggleAttribute(name,force){const add=force===undefined?!this.hasAttribute(name):!!force;if(add)this.setAttribute(name,'');else this.removeAttribute(name);return add;}
  get id(){return this.getAttribute('id')||'';}set id(value){this.setAttribute('id',value);}
  get className(){return this.getAttribute('class')||'';}set className(value){this.setAttribute('class',value);}
  get options(){return this.querySelectorAll('option');}
  get selectedOptions(){if(this.tagName!=='SELECT')return [];const explicit=this.options.filter(o=>o._selected);if(explicit.length)return this.multiple?explicit:[explicit.at(-1)];return this._selectNone?[]:this.options.slice(0,1);}
  get selectedIndex(){return this.options.indexOf(this.selectedOptions[0]);}
  set selectedIndex(value){const at=Number(value);this._selectNone=at<0||at>=this.options.length;this.options.forEach((o,i)=>o._selected=i===at);}
  get selected(){return this._selected||!!(this.closest('select')?.selectedOptions.includes(this));}
  set selected(value){this._selected=!!value;const select=this.closest('select');if(select){select._selectNone=false;if(value&&!select.multiple)for(const option of select.options)if(option!==this)option._selected=false;}}
  get value(){if(this.tagName==='SELECT')return this.selectedOptions[0]?.value||'';if(this.tagName==='OPTION')return this.getAttribute('value')??this.textContent;return this._value??this.getAttribute('value')??'';}
  set value(value){value=String(value??'');if(this.tagName==='SELECT'){let found=false;for(const option of this.options){option._selected=!found&&option.value===value;if(option._selected)found=true;}this._selectNone=!found;}else if(this.tagName==='OPTION')this.setAttribute('value',value);else this._value=value;}
  get text(){return this.textContent;}set text(value){this.textContent=value;}
  get length(){return this.tagName==='SELECT'?this.options.length:this.children.length;}
  add(option,before=null){if(typeof before==='number')before=this.options[before]||null;if(before)this.insertBefore(option,before);else this.append(option);}
  matches(selector){return matches(this,selector,this);}
  closest(selector){for(let current=this;current;current=current.parentElement)if(current.nodeType===1&&matches(current,selector,current))return current;return null;}
  querySelectorAll(selector){return queryAll(this,selector);}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  click(){if(!this.disabled)this.dispatchEvent(new Event('click',{bubbles:true,cancelable:true}));}
  focus(){document.activeElement=this;this.dispatchEvent(new Event('focus'));this.dispatchEvent(new Event('focusin',{bubbles:true}));}
  blur(){if(document.activeElement===this)document.activeElement=document.body;this.dispatchEvent(new Event('blur'));}
  showModal(){this._modal=true;this.open=true;}
  show(){this._modal=false;this.open=true;}
  close(value=''){const wasOpen=this.open;this.returnValue=String(value);this.open=false;this._modal=false;if(wasOpen)this.dispatchEvent(new Event('close'));}
  showPopover(){if(this._popoverOpen)return;if(this.popover==='auto')for(const node of document.querySelectorAll('[popover]'))if(node!==this&&node._popoverOpen&&node.popover==='auto')node.hidePopover();this._popoverOpen=true;this.dispatchEvent(new Event('toggle',{oldState:'closed',newState:'open'}));}
  hidePopover(){if(!this._popoverOpen)return;this._popoverOpen=false;this.dispatchEvent(new Event('toggle',{oldState:'open',newState:'closed'}));}
  togglePopover(force){if(force===undefined?!this._popoverOpen:force)this.showPopover();else this.hidePopover();return this._popoverOpen;}
  getClientRects(){
   if(!this.isConnected)return [];
   for(let node=this;node?.nodeType===1;node=node.parentElement){
    if(node.hidden||node.style.display==='none'||node.tagName==='DIALOG'&&!node.open||node.hasAttribute('popover')&&!node._popoverOpen)return [];
   }
   return [this.getBoundingClientRect()];
  }
  getBoundingClientRect(){const r={x:0,y:0,width:this.clientWidth,height:this.clientHeight,...(this._rect||{})};r.left=r.left??r.x;r.top=r.top??r.y;r.right=r.left+r.width;r.bottom=r.top+r.height;r.toJSON=()=>({x:r.x,y:r.y,left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height});return r;}
  get offsetWidth(){return this.clientWidth;}get offsetHeight(){return this.clientHeight;}
  scrollIntoView(){}setPointerCapture(){}releasePointerCapture(){}hasPointerCapture(){return false;}
  checkValidity(){return true;}reportValidity(){return true;}
  reset(){for(const node of this.querySelectorAll('input,select,textarea')){if(node.tagName==='SELECT')node.selectedIndex=0;else node.value='';}}
 }
 for(const name of ['hidden','open','disabled','checked','multiple','required','inert','readOnly']){
  const attribute=name==='readOnly'?'readonly':name;
  Object.defineProperty(Node.prototype,name,{get(){return this.hasAttribute(attribute);},set(value){this.toggleAttribute(attribute,!!value);}});
 }
 for(const name of ['title','type','placeholder','name','label','href','src','popover'])Object.defineProperty(Node.prototype,name,{get(){return this.getAttribute(name)||'';},set(value){this.setAttribute(name,value);}});
 class Document extends Node{
  constructor(){super('',9);this.ownerDocument=this;this.activeElement=null;this.readyState='complete';}
  createElement(tag){return new Node(tag);}
  createElementNS(namespace,tag){return this.createElement(tag);}
  createTextNode(text){return new Node('',3,text);}
  createDocumentFragment(){return new Node('',11);}
  getElementById(id){return this.querySelectorAll('[id]').find(node=>node.id===String(id))||null;}
  get documentElement(){return this.querySelector('html')||this.firstElementChild;}
  get body(){return this.querySelector('body');}get head(){return this.querySelector('head');}
 }
 document=new Document();window=new EventTarget();window.window=window;window.document=document;document.defaultView=window;
 window.innerWidth=1280;window.innerHeight=800;window.visualViewport=new EventTarget();Object.assign(window.visualViewport,{width:1280,height:800});
 window.getComputedStyle=node=>({zoom:node.style.zoom||'1',display:node.style.display||'block',getPropertyValue:name=>node.style.getPropertyValue(name)});
 window.matchMedia=query=>({matches:false,media:query,addEventListener(){},removeEventListener(){}});
 function Option(text='',value=text,defaultSelected=false,selected=false){const option=document.createElement('option');option.textContent=text;option.value=value;option._selected=!!selected;option.defaultSelected=!!defaultSelected;return option;}
 function load(row){
  if(row===null||row===undefined)return null;if(typeof row==='string')return document.createTextNode(row);
  if(row.tag==='#text'||row.type==='text')return document.createTextNode(row.text||'');
  const node=row.tag==='#document'?document:document.createElement(row.tag||'div');
  for(const [name,value] of Object.entries(row.attrs||{}))node.setAttribute(name,value);
  if(row.text)node.append(document.createTextNode(row.text));
  for(const child of row.children||[]){const built=load(child);if(built)node.append(built);if(child&&typeof child==='object'&&child.tail)node.append(document.createTextNode(child.tail));}
  return node;
 }
 if(tree){const root=load(tree);if(root!==document)document.append(root);}else document.append(load({tag:'html',children:[{tag:'head'},{tag:'body'}]}));
 if(document.documentElement){document.documentElement.clientWidth=1280;document.documentElement.clientHeight=800;}
 document.activeElement=document.body;
 Object.assign(window,{Node,HTMLElement:Node,Event,CustomEvent,KeyboardEvent:Event,MouseEvent:Event,MutationObserver,ResizeObserver,Option});
 return {document,window,Node,Option,Event,CustomEvent,MutationObserver,ResizeObserver,flushMutations};
}

module.exports={createDOM};
