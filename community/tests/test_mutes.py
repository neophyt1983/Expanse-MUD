from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
import unittest

from aiohttp import CookieJar
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import Store, make_app, password_digest, utc

PASS='long-disposable-password'

class ForumMuteTests(unittest.IsolatedAsyncioTestCase):
    async def start(self):
        self.server=TestServer(make_app(self.path,secure=False,bootstrap=('owner',PASS)))
        await self.server.start_server()
        self.clients={}
        self.tokens={}
        for name in ('guest','owner','alice','bob','carol','otheradmin'):
            client=TestClient(self.server,cookie_jar=CookieJar(unsafe=True))
            await client.start_server()
            self.clients[name]=client
            if name!='guest':
                res=await client.post('/login',data={'username':name,'password':PASS},allow_redirects=False)
                self.assertEqual(res.status,303)
                main=await client.get('/')
                self.tokens[name]=re.search(r'name="csrf" value="([^"]+)"',await main.text())[1]

    async def stop(self):
        for c in self.clients.values(): await c.close()
        await self.server.close()

    async def asyncSetUp(self):
        self.temp=TemporaryDirectory()
        self.path=Path(self.temp.name)/'forum.sqlite3'
        self.store=Store(self.path)
        self.store.bootstrap_admin('owner',PASS)
        self.ids={}
        with self.store.db() as db:
            for name,role,status in [('alice','member','active'),('bob','member','active'),
                                     ('carol','member','active'),('otheradmin','admin','active'),
                                     ('pending','member','pending')]:
                salt=bytes(16)
                cur=db.execute("INSERT INTO users(username,salt,verifier,role,status,created_at) VALUES(?,?,?,?,?,?)",
                               (name,salt,password_digest(PASS,salt),role,status,utc()))
                self.ids[name]=cur.lastrowid
        await self.start()

    async def asyncTearDown(self):
        await self.stop()
        self.temp.cleanup()

    async def post(self,name,path,**data):
        data.setdefault('csrf',self.tokens.get(name,''))
        return await self.clients[name].post(path,data=data,allow_redirects=False)

    async def read(self,name,path):
        res=await self.clients[name].get(path)
        self.assertEqual(res.status,200)
        return await res.text()

    async def thread(self,name,title,body):
        res=await self.post(name,'/new',category='discussion',title=title,body=body)
        self.assertEqual(res.status,303)
        return res.headers['Location']

    async def test_personal_mute_private_reversible_and_persistent(self):
        bobtopic=await self.thread('bob','Bobs amazing topic','Bobs original topic text')
        owntopic=await self.thread('alice','Alices amazing topic','Alices original topic text')
        self.assertEqual((await self.post('bob','/reply',topic_id=owntopic[3:],body='Bobs distinctive reply')).status,303)
        self.assertNotIn('Mute for me',await self.read('guest',bobtopic))
        self.assertIn('Mute for me',await self.read('alice',bobtopic))
        for target,expected in [('pending',404),('alice',400)]:
            res=await self.post('alice','/mutes',action='mute',user_id=self.ids[target],topic_id=bobtopic[3:])
            self.assertEqual(res.status,expected)
        self.assertEqual((await self.post('alice','/mutes',action='mute',user_id=self.ids['bob'],topic_id=bobtopic[3:],csrf='bad')).status,403)
        self.assertEqual((await self.post('alice','/mutes',action='mute',user_id=self.ids['bob'],topic_id=bobtopic[3:])).status,303)
        await self.stop();await self.start()
        for path,probe in [('/','Bobs amazing topic'),('/c/discussion','Bobs amazing topic'),
                           (bobtopic,'Bobs original topic text'),(owntopic,'Bobs distinctive reply')]:
            self.assertNotIn(probe,await self.read('alice',path))
            for name in ('guest','carol'):self.assertIn(probe,await self.read(name,path))
        self.assertIn('0 replies',await self.read('alice','/c/discussion'))
        self.assertIn('1 replies',await self.read('carol','/c/discussion'))
        self.assertIn('Unmute for me',await self.read('alice','/mutes'))
        self.assertNotIn('Unmute for me',await self.read('carol','/mutes'))
        self.assertEqual((await self.post('alice','/mutes',action='unmute',user_id=self.ids['bob'])).status,303)
        self.assertIn('Bobs distinctive reply',await self.read('alice',owntopic))

    async def test_only_bound_owner_can_pause_new_public_posts(self):
        thread=await self.thread('bob','Existing public topic','Old post remains')
        for who in ('alice','otheradmin'):
            self.assertEqual((await self.post(who,'/admin/posting-mute',action='pause',user_id=self.ids['bob'])).status,403)
        for _ in range(2):
            self.assertEqual((await self.post('owner','/admin/posting-mute',action='pause',user_id=self.ids['bob'])).status,303)
        await self.stop();await self.start()
        self.assertIn('Old post remains',await self.read('guest',thread))
        self.assertIn('Old post remains',await self.read('bob',thread))
        self.assertNotIn('Post reply',await self.read('bob',thread))
        self.assertEqual((await self.post('bob','/new',category='discussion',title='New blocked topic',body='Still blocked')).status,403)
        self.assertEqual((await self.post('bob','/reply',topic_id=thread[3:],body='New blocked reply')).status,403)
        self.assertEqual((await self.post('bob','/report',topic_id=thread[3:],reason='Report allowed')).status,303)
        self.assertEqual((await self.post('bob','/posting-status',reason='Private unique appeal')).status,303)
        self.assertIn('awaiting review',await self.read('bob','/posting-status'))
        self.assertIn('Private unique appeal',await self.read('owner','/admin'))
        self.assertNotIn('Private unique appeal',await self.read('otheradmin','/admin'))
        self.assertNotIn('Private unique appeal',await self.read('guest',thread))
        self.assertEqual((await self.post('owner','/admin/posting-mute',action='restore',user_id=self.ids['bob'])).status,303)
        self.assertEqual((await self.post('bob','/reply',topic_id=thread[3:],body='Restored post')).status,303)
        self.assertIn('Restored post',await self.read('guest',thread))
        with self.store.db() as db:
            self.assertEqual([tuple(r) for r in db.execute('SELECT action,changed FROM posting_mute_audit ORDER BY id')],[('pause',1),('restore',1)])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM posting_mute_appeals').fetchone()[0],0)


    async def test_public_reply_rules_after_reversible_pause(self):
        topic = await self.thread('alice', 'Kitchen help', 'Where can we find the kitchen?')
        topic_id = topic.rsplit('/', 1)[1]
        # A writer can pass one gate and still fail the other.
        link = 'https://example.com/recipes'
        pause = await self.post('owner', '/admin/posting-mute', action='pause', user_id=self.ids['bob'])
        self.assertEqual(pause.status, 303)
        withheld = await self.post('bob', '/reply', topic_id=topic_id, body=link)
        self.assertEqual(withheld.status, 403)
        restore = await self.post('owner', '/admin/posting-mute', action='restore', user_id=self.ids['bob'])
        self.assertEqual(restore.status, 303)
        invalid = await self.post('bob', '/reply', topic_id=topic_id, body=link)
        self.assertEqual(invalid.status, 400)
        self.assertNotIn(link, await invalid.text())
        self.assertEqual((await self.post('bob', '/reply', topic_id=topic_id,
                                         body='Find the cook beside the inn.')).status, 303)
        for reader in ('guest', 'alice', 'bob'):
            visible = await self.read(reader, topic)
            self.assertIn('Find the cook beside the inn.', visible)
            self.assertNotIn(link, visible)

class OwnerBindingTests(unittest.TestCase):
    def test_ambiguous_legacy_rename_never_auto_binds_after_restart(self):
        from mutes import owner
        with TemporaryDirectory() as temp:
            p=Path(temp)/'db'
            store=Store(p);store.bootstrap_admin('oldowner',PASS)
            with store.db() as db: db.execute('DELETE FROM forum_owner')
            store.bootstrap_admin('newowner',PASS)
            Store(p).bootstrap_admin('newowner',PASS)
            with store.db() as db:
                user=dict(db.execute("SELECT id FROM users WHERE username='newowner'").fetchone())
                self.assertFalse(owner(db,user))
                self.assertIsNone(db.execute('SELECT user_id FROM forum_owner').fetchone()[0])
