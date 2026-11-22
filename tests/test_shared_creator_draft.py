"""HTTP acceptance for the private-only account draft on a disposable staging host.

With EXPANSE_TEST_FOUNDING_CITIES set, run the same tests on the pinned game
archive instead of the small built-in archive.
"""
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestServer

from engine import exchange
from render_server import Accounts
from server import shared_staging
from server.stage_creator_draft import DRAFT_FLAG, DRAFT_PATH
import test_shared_host_founding_cities as founding
import test_shared_host_transport as transport


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class SharedCreatorDraft(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = transport.SharedHostTransportTests.asyncSetUp
    asyncTearDown = transport.SharedHostTransportTests.asyncTearDown
    files = staticmethod(transport.SharedHostTransportTests.files)
    stop = transport.SharedHostTransportTests.stop
    login = transport.SharedHostTransportTests.login

    async def start(self):
        if not hasattr(self, 'archive'):
            self.stack.enter_context(patch.dict(os.environ, {DRAFT_FLAG: '1'}))
            self.enabled = True
            selected = os.environ.get(founding.WORLD_VAR)
            if selected:
                self.archive = Path(selected).resolve(strict=True)
                self.revision = digest(self.archive)
                self.assertIn(self.revision, founding.WORLD_HASHES)
            else:
                minimal = self.root / 'minimal'
                minimal.mkdir()
                (minimal / 'metadata.json').write_text(json.dumps({'name': 'Draft fixture', 'start_room': 'inn'}))
                room = {'id': 'inn', 'name': 'Inn', 'description': 'An inn.', 'exits': {}}
                (minimal / 'rooms.json').write_text(json.dumps([room]))
                self.archive = self.root / 'minimal.expanse'
                ok, note = exchange.export_game('minimal', self.root, self.archive)
                self.assertTrue(ok, note)
                self.revision = digest(self.archive)
        self.auth = Accounts()
        self.app = shared_staging.make_app(self.archive, self.runtime, auth=self.auth,
                                          creator_draft_sha256=self.revision if self.enabled else None)
        self.service = self.app[shared_staging.STATE]
        self.http = TestServer(self.app)
        await self.http.start_server()
        self.origin = str(self.http.make_url('')).rstrip('/')
        self.service.origin = self.origin
        self.service.server.http_port = self.http.port

    async def set_role(self, owner, account, role):
        async with owner.post(self.origin + '/roles', data={'name': account, 'role': role},
                              headers={'Origin': self.origin}, allow_redirects=False) as response:
            self.assertEqual(303, response.status, await response.text())

    async def read_draft(self, client, status=200):
        async with client.get(self.origin + DRAFT_PATH) as response:
            self.assertEqual(status, response.status, await response.text())
            if status == 200:
                return await response.json()

    async def write_draft(self, client, body, status=200):
        async with client.post(self.origin + DRAFT_PATH, json=body,
                               headers={'Origin': self.origin}) as response:
            self.assertEqual(status, response.status, await response.text())
            if status == 200:
                return await response.json()

    async def test_account_drafts_roles_stale_writes_and_cold_restart(self):
        owner, alpha, beta, guest = [await self.login(n) for n in ('Owner', 'Alpha', 'Beta', 'Gamma')]
        await self.set_role(owner, 'Alpha', 'Admin')
        await self.set_role(owner, 'Beta', 'Full_Edit')
        await self.read_draft(guest, 403)
        base = await self.read_draft(alpha)
        self.assertEqual(base, await self.read_draft(beta))
        self.assertEqual(base['revision'], self.revision)
        self.assertEqual(base['version'], 0)
        room_id = base['room']['id']
        live_room = self.service.server.world.rooms[room_id]
        original = base['room']['name'], base['room']['description']
        self.assertEqual(original, (live_room.name, live_room.description))
        authored_digest = digest(self.service.world / 'rooms.json')
        names = ('Admin private draft', 'Full Edit private draft')
        bodies = [dict(world=base['world'], revision=self.revision, version=0, room=room_id,
                       name=name, description=name + ' saved text.') for name in names]
        await self.write_draft(guest, bodies[0], 403)
        saved_alpha = await self.write_draft(alpha, bodies[0])
        self.assertEqual(base, await self.read_draft(beta))
        saved_beta = await self.write_draft(beta, bodies[1])
        self.assertEqual([saved_alpha, saved_beta], [await self.read_draft(alpha), await self.read_draft(beta)])
        self.assertEqual(base, await self.read_draft(owner))
        for record, name in zip((saved_alpha, saved_beta), names):
            self.assertEqual(1, record['version'])
            self.assertEqual(name, record['room']['name'])
        await self.write_draft(alpha, bodies[0], 409)
        await self.write_draft(beta, dict(bodies[1], account='Alpha', version=1), 400)
        await self.write_draft(beta, dict(bodies[1], room='other_room', version=1), 409)
        async with beta.get(self.origin + DRAFT_PATH, params={'account': 'Alpha'}) as other:
            self.assertEqual(400, other.status)
        async with beta.get(self.origin + '/roles') as moderation:
            self.assertEqual(403, moderation.status)
        for client in (guest, alpha, beta, owner):
            async with client.get(self.origin + '/api/editor/games') as editor:
                self.assertEqual(403, editor.status)
        await self.set_role(owner, 'Beta', 'No_Edit')
        await self.read_draft(beta, 403)
        await self.write_draft(beta, dict(bodies[1], version=1), 403)
        self.assertEqual(original, (live_room.name, live_room.description))
        self.assertEqual(authored_digest, digest(self.service.world / 'rooms.json'))
        await self.stop()
        await self.start()
        owner, alpha, beta = [await self.login(n) for n in ('Owner', 'Alpha', 'Beta')]
        await self.read_draft(beta, 403)
        await self.set_role(owner, 'Beta', 'Full_Edit')
        self.assertEqual([saved_alpha, saved_beta], [await self.read_draft(alpha), await self.read_draft(beta)])
        live_room = self.service.server.world.rooms[room_id]
        self.assertEqual(original, (live_room.name, live_room.description))
        self.assertEqual(authored_digest, digest(self.service.world / 'rooms.json'))
        self.assertEqual(self.revision, digest(self.archive))

    async def test_explicit_archive_and_flag_are_required(self):
        await self.stop()
        other = self.root / 'invalid-pin'
        with self.assertRaisesRegex(ValueError, 'reviewed SHA-256'):
            shared_staging.make_app(self.archive, other, auth=self.auth, creator_draft_sha256='0' * 64)
        self.assertFalse(other.exists())
        with patch.dict(os.environ, {DRAFT_FLAG: ''}), self.assertRaisesRegex(ValueError, DRAFT_FLAG):
            shared_staging.make_app(self.archive, other, auth=self.auth, creator_draft_sha256=self.revision)
        self.assertFalse(other.exists())
        self.enabled = False
        await self.start()
        owner = await self.login('Owner')
        await self.read_draft(owner, 403)
        self.assertFalse((self.runtime / 'creator-proof').exists())
