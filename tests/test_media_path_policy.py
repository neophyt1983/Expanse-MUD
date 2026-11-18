"""Player media has a portable spelling and a narrow rendering JSON scope."""
import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from engine import public_media, world_package
import test_world_media_protocol as media_fixtures


class MediaPathPolicy(unittest.TestCase):
    def test_known_renderer_json_and_ordinary_images_audio_remain_deliverable(self):
        for name in (*public_media.RENDER_JSON, 'images/title.jpg',
                     'assets/audio/tavern_neutral.ogg', 'assets/Custom Art/Portrait.PNG'):
            with self.subTest(name=name):
                self.assertTrue(public_media.legacy_presentation(name))
        for name in ('assets/terrain/private-records.json', 'assets/audio/catalogue.json',
                     'assets/sprites/private-records.json', 'assets/arbitrary.json'):
            with self.subTest(name=name):
                self.assertFalse(public_media.legacy_presentation(name))
                self.assertTrue(world_package.media(name), 'Archive preservation policy must remain independent.')

    def test_nonportable_names_and_source_namespaces_are_rejected_before_io(self):
        invalid = (
            'assets/UPDATES/state.json', 'assets/Chronicles/notes.png',
            'assets/terrain /tiles.png', 'assets/terrain./tiles.png',
            'assets/terrain/tiles.png ', 'assets/terrain/tiles.png.',
            'assets/audio/part:audio.ogg', 'assets/audio/NUL.ogg',
            'assets/COM1/tone.ogg', 'assets/LPT9/tone.ogg',
            'assets/audio/abbrev~1.ogg', 'assets/audio/.private.ogg',
            'assets/audio/encoded%20name.ogg', 'assets/audio/invalid?.ogg',
            'assets/audio/invalid*.ogg', 'assets/audio/invalid|.ogg',
            'assets/audio/../other.ogg', 'assets\\audio\\tone.ogg',
        )
        with patch.object(public_media, '_open_regular', side_effect=AssertionError('Rejected name opened')):
            for name in invalid:
                with self.subTest(name=name):
                    self.assertFalse(public_media.legacy_presentation(name))
                    row = public_media.presentation_packet('/unused', name, 0)
                    self.assertTrue(row['missing'])
                    self.assertNotIn('data', row)

    def test_legacy_chunks_use_safe_link_checks_on_both_capability_paths(self):
        with tempfile.TemporaryDirectory(prefix='expanse-media-path-') as temporary:
            root = Path(temporary)
            path = root / 'assets/audio/example.ogg'
            path.parent.mkdir(parents=True)
            body = b'ordinary authored presentation'
            path.write_bytes(body)
            for native in (False, True) if public_media._directory_descriptors() else (False,):
                with patch.object(public_media, '_directory_descriptors', return_value=native):
                    row = public_media.presentation_packet(root, 'assets/audio/example.ogg', 0)
                    self.assertEqual(body, base64.b64decode(row['data']))
            original = root / 'original.ogg'
            path.rename(original)
            try:
                path.symlink_to(original)
            except OSError:
                self.skipTest('This platform/user does not permit test symlinks.')
            for native in (False, True) if public_media._directory_descriptors() else (False,):
                with patch.object(public_media, '_directory_descriptors', return_value=native):
                    self.assertTrue(public_media.presentation_packet(root, 'assets/audio/example.ogg', 0)['missing'])

    def test_released_world_rendering_inventory_keeps_legacy_compatibility(self):
        archive = Path(__file__).resolve().parents[2] / 'test-world/Expanse-Wild-Lands-1.9.15.expanse'
        if not archive.is_file():
            self.skipTest('Released world archive unavailable for the inventory check.')
        with ZipFile(archive) as world:
            for name in world.namelist():
                if name.startswith(('assets/terrain/', 'assets/sprites/', 'assets/audio/')):
                    self.assertTrue(public_media.legacy_presentation(name), name)
                elif name.startswith(public_media.PRIVATE_NAMESPACES):
                    self.assertFalse(public_media.legacy_presentation(name), name)


class NarrowJSONTransport(unittest.IsolatedAsyncioTestCase):
    async def test_other_json_names_do_not_reach_the_file_reader_on_a_joined_connection(self):
        fixture = media_fixtures.MediaTransport()
        with patch.object(public_media, 'presentation_packet', side_effect=AssertionError('Out-of-scope JSON read')):
            socket = await fixture.session([
                {'command': 'world asset', 'name': 'assets/terrain/private-records.json', 'request_id': 4},
                {'command': 'world asset', 'name': 'assets/UPDATES/private.json', 'request_id': 5},
            ])
        replies = [row for row in socket.packets if row['type'] == 'world_asset']
        self.assertEqual(2, len(replies))
        self.assertTrue(all(row.get('missing') and 'data' not in row for row in replies))


if __name__ == '__main__':
    unittest.main()
