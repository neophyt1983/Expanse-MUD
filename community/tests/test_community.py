import asyncio
from pathlib import Path
import re
import sys
import tempfile
import unittest
from aiohttp import CookieJar
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import Store, make_app, text_html
from wiki.build import render_markdown, safe_link

class ForumTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.work=tempfile.TemporaryDirectory()
        self.db=Path(self.work.name)/'community.sqlite3'
        self.server=TestServer(make_app(self.db,secure=False,bootstrap=('owner','correct-long-password-123'),registration_enabled=True))
        await self.server.start_server()
        self.admin=TestClient(self.server,cookie_jar=CookieJar(unsafe=True));await self.admin.start_server()
        self.visitor=TestClient(self.server,cookie_jar=CookieJar(unsafe=True));await self.visitor.start_server()

    async def asyncTearDown(self):
        await self.admin.close();await self.visitor.close();await self.server.close();self.work.cleanup()

    async def login_admin(self):
        r=await self.admin.post('/login',data={'username':'owner','password':'correct-long-password-123'},allow_redirects=False)
        self.assertEqual(303,r.status)
        with Store(self.db).db() as conn:
            row=conn.execute("SELECT csrf FROM sessions JOIN users ON sessions.user_id=users.id WHERE username='owner'").fetchone()
        return row['csrf']

    async def create_member(self):
        r=await self.visitor.post('/register',data={'username':'tester','password':'different-long-password-123'},allow_redirects=False)
        self.assertEqual(r.status,200)
        with Store(self.db).db() as conn:
            row=conn.execute("SELECT id,status FROM users WHERE username='tester'").fetchone()
        self.assertEqual('pending',row['status'])
        a=await self.login_admin()
        r=await self.admin.post('/admin/member',data={'user_id':str(row['id']),'action':'approve','csrf':a},allow_redirects=False)
        self.assertEqual(303,r.status)
        r=await self.visitor.post('/login',data={'username':'tester','password':'different-long-password-123'},allow_redirects=False)
        self.assertEqual(303,r.status)
        with Store(self.db).db() as conn:
            row=conn.execute("SELECT csrf FROM sessions JOIN users ON sessions.user_id=users.id WHERE username='tester'").fetchone()
        return a,row['csrf']

    async def test_public_categories_and_health(self):
        r=await self.visitor.get('/');body=await r.text()
        self.assertEqual(200,r.status)
        self.assertIn('Official News &amp; Server Status',body)
        self.assertIn('The Tavern',body)
        r=await self.visitor.get('/healthz');self.assertEqual('expanse-community-staging',(await r.json())['service'])

    async def test_registration_disabled_by_default(self):
        separate=TestServer(make_app(Path(self.work.name)/'closed.sqlite3',secure=False,bootstrap=('administrator','another-strong-password-123')))
        await separate.start_server()
        try:
            client=TestClient(separate,cookie_jar=CookieJar(unsafe=True))
            await client.start_server()
            try:
                get=await client.get('/register',allow_redirects=False)
                self.assertEqual(503,get.status)
                post=await client.post('/register',data={'username':'tester','password':'another-strong-password-123'},allow_redirects=False)
                self.assertEqual(503,post.status)
                home=await client.get('/')
                self.assertNotIn('<a href="/register">Register</a>',await home.text())
            finally:
                await client.close()
        finally:
            await separate.close()

    async def test_registration_waits_for_approval(self):
        r=await self.visitor.post('/register',data={'username':'tester','password':'different-long-password-123'})
        self.assertIn('approve your account',await r.text())
        r=await self.visitor.post('/login',data={'username':'tester','password':'different-long-password-123'})
        self.assertEqual(403,r.status)

    async def test_official_news_permissions_and_html_escaping(self):
        admin_csrf,member_csrf=await self.create_member()
        bad=await self.visitor.post('/new',data={'category':'news','title':'Fake news','body':'Unauthorized announcement','csrf':member_csrf},allow_redirects=False)
        self.assertEqual(403,bad.status)
        fake=await self.visitor.post('/new',data={'category':'discussion','title':'Wrong csrf','body':'test','csrf':'invalid'},allow_redirects=False)
        self.assertEqual(403,fake.status)
        ok=await self.admin.post('/new',data={'category':'news','title':'[Maintenance] Planned server update','body':'<script>alert(1)</script> Game worlds remain in Single Player.','csrf':admin_csrf},allow_redirects=False)
        self.assertEqual(303,ok.status)
        url=ok.headers['Location']
        view=await self.visitor.get(url);page=await view.text()
        self.assertIn('&lt;script&gt;',page)
        self.assertNotIn('<script>alert(1)',page)
        rss=await self.visitor.get('/news.rss');feed=await rss.text()
        self.assertIn('&lt;script&gt;',feed)
        self.assertIn('[Maintenance] Planned server update',feed)

    async def test_replies_moderation_and_persistence(self):
        admin_csrf,member_csrf=await self.create_member()
        topic=await self.visitor.post('/new',data={'category':'discussion','title':'Welcome to Expanse','body':'We are discussing the game here.','csrf':member_csrf},allow_redirects=False)
        self.assertEqual(303,topic.status)
        url=topic.headers['Location'];tid=int(url.split('/')[-1])
        reply=await self.visitor.post('/reply',data={'topic_id':str(tid),'body':'A good place to talk.','csrf':member_csrf},allow_redirects=False)
        self.assertEqual(303,reply.status)
        view=await self.admin.get(url);self.assertIn('A good place to talk.',await view.text())
        act=await self.admin.post('/moderate',data={'topic_id':str(tid),'action':'lock','csrf':admin_csrf},allow_redirects=False)
        self.assertEqual(303,act.status)
        blocked=await self.visitor.post('/reply',data={'topic_id':str(tid),'body':'I should not post','csrf':member_csrf},allow_redirects=False)
        self.assertEqual(403,blocked.status)
        with Store(self.db).db() as conn:
            self.assertEqual(1,conn.execute('SELECT count(*) FROM replies WHERE topic_id=?',(tid,)).fetchone()[0])
            self.assertEqual(1,conn.execute('SELECT locked FROM topics WHERE id=?',(tid,)).fetchone()[0])

    async def test_report_approval_and_suspension(self):
        admin_csrf,member_csrf=await self.create_member()
        topic=await self.visitor.post('/new',data={'category':'bugs','title':'The magic quest issue','body':'In this build, I could not complete a quest.','csrf':member_csrf},allow_redirects=False)
        tid=int(topic.headers['Location'].split('/')[-1])
        r=await self.visitor.post('/report',data={'topic_id':str(tid),'reason':'Needs a staff review','csrf':member_csrf},allow_redirects=False)
        self.assertEqual(303,r.status)
        with Store(self.db).db() as conn:
            rid=conn.execute('SELECT id FROM reports').fetchone()['id']
            uid=conn.execute("SELECT id FROM users WHERE username='tester'").fetchone()['id']
        r=await self.admin.post('/admin/report',data={'report_id':str(rid),'action':'close','csrf':admin_csrf},allow_redirects=False)
        self.assertEqual(303,r.status)
        r=await self.admin.post('/admin/member',data={'user_id':str(uid),'action':'suspend','csrf':admin_csrf},allow_redirects=False)
        self.assertEqual(303,r.status)
        r=await self.visitor.get('/new');self.assertEqual(403,r.status)

    async def test_reject_bad_registration(self):
        r=await self.visitor.post('/register',data={'username':'bad user','password':'different-long-password-123'},allow_redirects=False)
        self.assertEqual(400,r.status)


class WikiTests(unittest.TestCase):
    def test_markdown_escapes_inline_html(self):
        markup=render_markdown('# Welcome\n\nHi <script>bad</script>\n\n- [Wiki](index.html)')
        self.assertIn('&lt;script&gt;',markup)
        self.assertNotIn('<script>',markup)
        self.assertIn('href="index.html"',markup)

    def test_markdown_rejects_script_url(self):
        self.assertIsNone(safe_link('javascript:alert(1)'))
        self.assertIsNone(safe_link('//evil.example/'))
        self.assertEqual('https://expansemud.com/','https://expansemud.com/' if safe_link('https://expansemud.com/') else None)

    def test_static_wiki_and_status_use_working_forum_and_wiki_links(self):
        from wiki.build import build
        build()
        dist=Path(__file__).resolve().parents[1]/'dist'
        for page in [*(dist/'wiki').glob('*.html'),dist/'status'/'index.html']:
            content=page.read_text()
            self.assertNotIn('community.expansemud.com/',content, str(page))
            self.assertIn('href="../wiki/index.html"',content)
            self.assertIn('href="https://expanse-mud.onrender.com/forum/"',content)
        self.assertIn('https://expanse-mud.onrender.com/forum/c/news',(dist/'status'/'index.html').read_text())

    def test_user_text_escapes(self):
        self.assertIn('&lt;b&gt;',text_html('<b>hello</b>'))

if __name__=='__main__':unittest.main()