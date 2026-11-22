import unittest
import test_community
from app import Store


class PostingPolicyTests(test_community.ForumTests):
    async def post_topic(self, client, csrf, *, category='discussion', title='Travel question', body='Can I walk to the river?'):
        return await client.post('/new', data=dict(category=category, title=title, body=body, csrf=csrf),
                                 allow_redirects=False)

    async def post_reply(self, client, csrf, tid, body):
        return await client.post('/reply', data=dict(topic_id=tid, body=body, csrf=csrf),
                                 allow_redirects=False)

    async def test_title_body_and_reply_blocked_without_persisting_or_reflecting(self):
        admin, member = await self.create_member()
        r = await self.post_topic(self.visitor, member, title='See https://example.invalid/guide')
        assert r.status == 400
        output = await r.text()
        assert 'Title:' in output and 'Return to writing' in output and '/new?category=discussion' in output
        assert 'example.invalid' not in output
        r = await self.post_topic(self.visitor, member, body='Visit www.example.invalid for notes.')
        assert r.status == 400 and 'Message:' in await r.text()
        r = await self.post_topic(self.visitor, member, body='SELECT title FROM sample_notes;')
        assert r.status == 400 and 'sample_notes' not in await r.text()
        with Store(self.db).db() as conn:
            assert not conn.execute("SELECT count(*) FROM topics WHERE title IN (?, ?)",
                                    ('See https://example.invalid/guide', 'Travel question')).fetchone()[0]
        r = await self.post_topic(self.visitor, member, body='Select a passage from the history book. Update the map with a marker.')
        assert r.status == 303
        url = r.headers['Location']
        tid = url.split('/')[-1]
        r = await self.post_reply(self.visitor, member, tid, 'https://example.invalid/notes')
        assert r.status == 400
        output = await r.text()
        assert 'Reply:' in output and f'{url}#reply' in output and 'example.invalid' not in output
        r = await self.post_reply(self.visitor, member, tid, 'The database search was slow. I am using version 1.9.18.3.')
        assert r.status == 303
        with Store(self.db).db() as conn:
            assert [row[0] for row in conn.execute('SELECT body FROM replies WHERE topic_id=?', (tid,))] == [
                'The database search was slow. I am using version 1.9.18.3.']

    async def test_official_exemption_is_scoped_and_existing_nav_survives(self):
        admin, member = await self.create_member()
        link = 'Read https://example.invalid/guide for the guide.'
        r = await self.post_topic(self.visitor, member, category='news', body=link)
        assert r.status == 403
        r = await self.post_topic(self.admin, admin, body=link)
        assert r.status == 400
        r = await self.post_topic(self.admin, admin, category='news', body='SELECT title FROM sample_notes;')
        assert r.status == 400
        r = await self.post_topic(self.admin, admin, category='news', body=link)
        assert r.status == 303
        url = r.headers['Location']
        tid = url.split('/')[-1]
        r = await self.post_reply(self.visitor, member, tid, link)
        assert r.status == 400
        r = await self.post_reply(self.admin, admin, tid, link)
        assert r.status == 303
        r = await self.visitor.get(url)
        output = await r.text()
        assert link in output and 'https://expansemmo.com/wiki/' in output
        assert 'href="https://example.invalid/guide"' not in output

    async def test_historical_posts_unchanged(self):
        _, member = await self.create_member()
        historical = 'Old plain-text field note: https://example.invalid/old'
        r = await self.post_topic(self.visitor, member)
        assert r.status == 303
        url = r.headers['Location']
        tid = url.split('/')[-1]
        with Store(self.db).db() as conn:
            conn.execute('UPDATE topics SET body=? WHERE id=?', (historical, tid))
        r = await self.visitor.get(url)
        output = await r.text()
        assert historical in output and 'href="https://example.invalid/old"' not in output
        with Store(self.db).db() as conn:
            assert conn.execute('SELECT body FROM topics WHERE id=?', (tid,)).fetchone()[0] == historical


if __name__ == '__main__':
    unittest.main()
