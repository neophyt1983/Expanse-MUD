/* Read-only, offline handbook. No editor mutation or service calls. */
(()=>{'use strict';
const chapters=window.ExpanseCreatorGuideData;if(!Array.isArray(chapters))return;
const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
const d=node('dialog');d.id='creator-guide';d.setAttribute('aria-labelledby','creator-guide-title');
const header=node('header'),title=node('h2','Creator handbook'),close=node('button','Close handbook');title.id='creator-guide-title';close.type='button';header.append(title,close);d.append(header);
const intro=node('p','Read-only instructions and examples. No example runs automatically. Use the actual labels and validation in your installed build.');d.append(intro);
const label=node('label','Find guide text '),query=node('input');query.type='search';query.id='creator-guide-search';label.htmlFor=query.id;label.append(query);d.append(label);
const status=node('p');status.id='creator-guide-status';status.setAttribute('role','status');d.append(status);
const layout=node('div');layout.className='creator-guide-layout';const nav=node('nav'),article=node('article');nav.setAttribute('aria-label','Creator handbook topics');article.tabIndex=-1;layout.append(nav,article);d.append(layout);
let selected='overview',returnFocus=null;
function matching(){const words=query.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);return chapters.filter(c=>words.every(w=>(c.title+' '+c.paragraphs.join(' ')).toLocaleLowerCase().includes(w)));}
function render(focus=false){const matches=matching();if(!matches.some(c=>c.id===selected))selected=matches[0]?.id||'';nav.replaceChildren();for(const c of matches){const b=node('button',c.title);b.type='button';b.dataset.topic=c.id;b.setAttribute('aria-current',String(c.id===selected));b.onclick=()=>{selected=c.id;render(true);};nav.append(b);}article.replaceChildren();const chapter=matches.find(c=>c.id===selected);status.textContent=matches.length+' of '+chapters.length+' topics match';if(chapter){article.append(node('h3',chapter.title));for(const paragraph of chapter.paragraphs){const lines=paragraph.split('\n');article.append(node('p',lines[0]));if(lines.length>1)article.append(node('pre',lines.slice(1).join('\n')));}}else article.append(node('p','No matching topic. Clear or shorten the search.'));if(focus)article.focus();}
function open(topic='overview'){if(!d.open)returnFocus=document.activeElement;query.value='';selected=chapters.some(c=>c.id===topic)?topic:'overview';render();if(!d.open)d.showModal();query.focus();}
close.onclick=()=>d.close();d.addEventListener('close',()=>{if(returnFocus?.isConnected)returnFocus.focus();});query.oninput=()=>render();query.addEventListener('keydown',e=>{if(e.key==='Escape'&&query.value){e.preventDefault();e.stopPropagation();query.value='';render();}});
document.body.append(d);
const launch=node('button','Creator handbook');launch.type='button';launch.className='ed-btn';launch.id='ed-creator-guide';launch.onclick=()=>open();document.getElementById('ed-toolbar')?.append(launch);
const contexts=[['#history-dialog','history'],['#tax-dialog','tax'],['#population-dialog','population'],['#geology-dialog','geology'],['#regional_weather-dialog','weather'],['dialog.pixel-studio','pixels']];
function help(dialog,topic){if(dialog.querySelector(':scope > .creator-context-help'))return;const b=node('button','Help and examples');b.type='button';b.className='ed-btn creator-context-help';b.onclick=()=>open(topic);dialog.prepend(b);}
function attach(){for(const box of document.querySelectorAll('.creator-assist')){if(!box.querySelector('.creator-assist-guide')){const b=node('button','JSON help and examples');b.type='button';b.className='ed-btn creator-assist-guide';b.onclick=()=>open('ide');box.append(b);}}for(const [selector,topic] of contexts)for(const dialog of document.querySelectorAll(selector))help(dialog,topic);for(const dialog of document.querySelectorAll('dialog')){if(dialog===d)continue;if([...dialog.querySelectorAll('button')].some(b=>b.textContent==='Save world rules'))help(dialog,'rules');}}
new MutationObserver(attach).observe(document.body,{childList:true,subtree:true});attach();
window.ExpanseCreatorGuide={open};
})();
