"""Generate Fastmail-ready wiki HTML from reviewed GitHub Markdown source.

Deliberately small supported Markdown subset: headings, simple bullets, paragraphs,
inline code, emphasis and links. Never emits raw user-authored HTML.
"""
from __future__ import annotations
from html import escape
from pathlib import Path
import re
import json
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'wiki' / 'pages'
DEST = ROOT / 'dist' / 'wiki'


def safe_link(dest):
    parts=urlsplit(dest)
    if parts.scheme in ('https','http') and parts.netloc:
        return dest
    if not parts.scheme and not parts.netloc and re.fullmatch(r'[a-z0-9-]+\.html',dest):
        return dest
    return None


def inline(text):
    # Escape before substitution to eliminate source HTML; href is validated.
    escaped=escape(text)
    def mk_link(m):
        destination=safe_link(m.group(2))
        if not destination:return m.group(1)
        return '<a href="'+escape(destination,quote=True)+'">'+m.group(1)+'</a>'
    escaped=re.sub(r'\[([^\]]+)\]\(([^) ]+)\)',mk_link,escaped)
    escaped=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',escaped)
    escaped=re.sub(r'`([^`]+)`',r'<code>\1</code>',escaped)
    return escaped


def render_markdown(raw):
    lines=raw.splitlines();html=[];para=[];in_list=False
    def flush():
        nonlocal para
        if para:html.append('<p>'+inline(' '.join(para))+'</p>');para=[]
    def close_list():
        nonlocal in_list
        if in_list:html.append('</ul>');in_list=False
    for line in lines:
        s=line.strip()
        if not s:flush();close_list();continue
        if s.startswith('#') and re.match(r'^#{1,3} ',s):
            flush();close_list();level=len(s)-len(s.lstrip('#'));html.append(f'<h{level}>'+inline(s[level:].strip())+f'</h{level}>');continue
        if s.startswith('- '):
            flush()
            if not in_list:html.append('<ul>');in_list=True
            html.append('<li>'+inline(s[2:])+'</li>');continue
        close_list();para.append(s)
    flush();close_list();return '\n'.join(html)


STYLE='''
:root{color-scheme:dark;--bg:#0b151b;--card:#11272a;--line:#325451;--fg:#e5efec;--sub:#b2c8c0;--accent:#8fdec0}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(132deg,#10252a,#0a1119);color:var(--fg);font:16px/1.65 system-ui,sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}a:focus-visible{outline:2px solid #fff;outline-offset:3px}
header{border-bottom:1px solid var(--line);padding:20px 3vw;display:flex;justify-content:space-between;align-items:center;gap:1.5rem;flex-wrap:wrap}
.brand{font-family:Georgia,serif;letter-spacing:.2em;color:var(--fg);font-size:1.25rem}nav{display:flex;gap:1rem;flex-wrap:wrap}
.layout{display:grid;grid-template-columns:235px minmax(0,1fr);gap:2rem;max-width:1150px;margin:0 auto;padding:35px 20px}
aside{border:1px solid var(--line);background:var(--card);border-radius:8px;padding:19px;height:max-content}aside a{display:block;margin:12px 0;font-size:.92rem}
article{border:1px solid var(--line);background:var(--card);padding:35px;border-radius:8px;min-height:450px;overflow-wrap:anywhere}h1{font-size:2rem}h2{margin-top:32px;padding-top:12px;border-top:1px solid var(--line);font-size:1.4rem}h3{font-size:1.15rem}p,li{color:var(--sub)}li{padding:4px 0}article strong{color:var(--fg)}code{font-family:ui-monospace,monospace;color:#e9cfa7}footer{text-align:center;color:var(--sub);margin:30px auto;padding:20px}
#search{width:100%;max-width:440px;padding:11px;margin:10px 0 22px;background:#0a1519;border:1px solid #55766e;border-radius:4px;color:#fff;font:inherit}
@media(max-width:730px){.layout{grid-template-columns:1fr;gap:1rem;padding:16px 10px}aside{display:flex;flex-wrap:wrap;gap:8px}aside a{margin:0}article{padding:22px}}
'''


def page(content, title, sidebar):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape(title)} · Expanse Wiki</title><meta name="description" content="Official ExpanseMUD game wiki, documentation and community reference">
    <link rel="stylesheet" href="../assets/wiki.css"></head><body><header><a class="brand" href="https://expansemud.com/">EXPANSE · WIKI</a>
    <nav aria-label="Site"><a href="index.html">Wiki</a><a href="https://community.expansemud.com/">Forum</a><a href="https://expansemud.com/status/">Status</a><a href="https://expansemud.com/">Game</a></nav></header>
    <div class="layout"><aside><strong>Wiki navigation</strong>{sidebar}</aside><article>{content}</article></div>
    <footer>Expanse is independently created and transparently AI-assisted. Details may change between game versions.</footer></body></html>'''


def build():
    DEST.mkdir(parents=True,exist_ok=True)
    css=(ROOT/'dist'/'assets'/'wiki.css');css.parent.mkdir(parents=True,exist_ok=True);css.write_text(STYLE)
    items=[]
    for src in sorted(SOURCE.glob('*.md')):
        raw=src.read_text()
        title=next((line[2:].strip() for line in raw.splitlines() if line.startswith('# ')),src.stem)
        items.append((src,src.stem+'.html',title,raw))
    sidebar=''.join(f'<a href="{escape(fname)}">{escape(title)}</a>' for _,fname,title,_ in items)
    for src,fname,title,raw in items:
        html=render_markdown(raw)
        if src.stem=='index':
            html=html.replace('<h1>', '<label for="search">Find a wiki topic</label><input type="search" id="search" placeholder="Search wiki titles" oninput="document.querySelectorAll(\'.wiki-topic\').forEach(e=>e.hidden=!e.textContent.toLowerCase().includes(this.value.toLowerCase()))"><h1>',1) if False else html
        (DEST/fname).write_text(page(html,title,sidebar))
    # Fastmail supports static files and automatically presents index.html at /wiki/.
    status_dir=ROOT/'dist'/'status';status_dir.mkdir(parents=True,exist_ok=True)
    status_content='''<h1>ExpanseMUD — Service updates</h1><p>This is an independent static notice page. It does not automatically measure server uptime.
    The last confirmed operational status must be posted manually by the owner. An absence of new notices does not prove the game server is online.</p>
    <h2>News and maintenance</h2><p>See <a href="https://community.expansemud.com/c/news">Official News &amp; Server Status</a> for verified game updates.
    If the forum or game are both inaccessible, check this independent page for manual updates.</p>
    <h2>Last confirmed incident</h2><p>No incident information has been published to this static page yet.</p>'''
    (status_dir/'index.html').write_text(page(status_content,'Server status',sidebar))
    # Static site does not automatically deploy to Fastmail: operator publishes dist/.
    print('Built',len(items),'wiki pages, stylesheet, and independent status fallback in',ROOT/'dist')

if __name__=='__main__':build()