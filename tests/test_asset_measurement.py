"""Measurement guardrails; these tests do not enable a runtime cache."""
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from tools.measure_asset_delivery import category, main, presentation_comparison, static_inventory, websocket_model, world_inventory
from engine.world_package import CHUNK


class AssetMeasurementTests(unittest.TestCase):
    def test_archive_budget_is_checked_before_any_member_decompression(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / 'oversized.expanse'
            with ZipFile(archive, 'w') as bundle:
                bundle.writestr('assets/audio/first.ogg', b'x' * 16)
                bundle.writestr('private-world.json', b'x' * 16)
            for limits in ({'MAX_ARCHIVE_FILES': 1}, {'MAX_ARCHIVE_BYTES': 31}):
                with self.subTest(limits=limits), patch.multiple('tools.measure_asset_delivery', **limits), \
                     patch.object(ZipFile, 'open', side_effect=AssertionError('Member decompression attempted')):
                    with self.assertRaisesRegex(ValueError, 'before decompression'):
                        world_inventory(archive)

    def test_comparison_uses_hashes_and_ignores_server_update_transactions(self):
        def report(name, values):
            return {'archive': name, 'archive_bytes': 10, 'archive_sha256': name,
                    'transport_eligible_media': {}, 'categories': {},
                    'files': [dict(path=path, sha256=sha, raw_bytes=size, category=category(path)) for path, sha, size in values]}
        before = report('before', [('assets/audio/test.ogg', 'a' * 64, 12),
                                  ('assets/updates/old.json', 'old-update', 10000)])
        after = report('after', [('assets/audio/test.ogg', 'b' * 64, 12),
                                ('assets/updates/new.json', 'new-update', 20000)])
        result = presentation_comparison(before, after)
        self.assertEqual(result['presentation_files_changed'], 1)
        self.assertEqual(result['presentation_files_added'], 0)
        self.assertEqual(result['ideal_warm_cache_missing_or_changed_raw_bytes'], 12)

    def test_unhashed_oversized_asset_cannot_be_classified_as_unchanged(self):
        row = {'path': 'assets/audio/too-large.ogg', 'raw_bytes': 32 * 1024 * 1024 + 1,
               'category': category('assets/audio/too-large.ogg'),
               'transport_readable_with_32_mib_limit': False}
        before = {'files': [dict(row)]}
        after = {'files': [dict(row)]}
        with self.assertRaisesRegex(ValueError, '32 MiB transport bound; comparison refused'):
            presentation_comparison(before, after)

    def test_transport_model_matches_real_multichunk_json_encoding(self):
        raw = b'x' * (CHUNK + 7)
        size = 0
        for offset in range(0, len(raw), CHUNK):
            packet = dict(type='world_asset', name='assets/audio/test.ogg', offset=offset, size=len(raw),
                          mime='audio/ogg', data=base64.b64encode(raw[offset:offset + CHUNK]).decode(), request_id=1)
            size += len(json.dumps(packet).encode())
        modeled = websocket_model('assets/audio/test.ogg', len(raw))
        self.assertEqual(modeled['chunks'], 2)
        self.assertEqual(modeled['uncompressed_response_json_bytes'], size)

    def test_update_payloads_are_separate_and_archive_stays_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / 'fixture.expanse'
            with ZipFile(archive, 'w') as bundle:
                bundle.writestr('assets/updates/transaction.json', '{}')
                bundle.writestr('assets/audio/test.ogg', b'OggS test data')
                bundle.writestr('world.db', b'private data')
            before = archive.read_bytes()
            report = world_inventory(archive)
            self.assertEqual(report['transport_eligible_media']['files'], 2)
            self.assertEqual(len(report['categories']), 2)
            self.assertNotEqual(category('assets/updates/transaction.json'), category('assets/audio/test.ogg'))
            self.assertEqual(archive.read_bytes(), before)

    def test_static_inventory_excludes_unserved_files_and_resolves_versioned_references(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            web = root / 'web'
            web.mkdir()
            (web / 'index.html').write_text('<script src="/app.js?v=2"></script><link rel="stylesheet" href="/app.css">')
            (web / 'app.js').write_text('const version = 2;')
            (web / 'app.css').write_text('body {}')
            (web / 'not-served.json').write_text('{"secret":"not-an-asset"}')
            report = static_inventory(root)
            self.assertEqual(report['served_static_allowlist']['files'], 2)
            self.assertEqual(report['play_html_direct_static_references']['files'], 2)
            self.assertEqual(report['play_html_and_direct_static_references']['files'], 3)
            self.assertEqual(report['play_html_and_direct_static_references']['raw_bytes'],
                             sum((web / name).stat().st_size for name in ('index.html', 'app.js', 'app.css')))
            self.assertEqual(report['unresolved_local_references'], [])

    def test_output_refuses_to_replace_existing_user_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'existing-save.json'
            output.write_text('preserve me')
            with patch('tools.measure_asset_delivery.static_inventory', return_value={}), \
                 patch('tools.measure_asset_delivery.subprocess.check_output', return_value='test-commit'):
                with self.assertRaises(FileExistsError):
                    main(['--output', str(output)])
            self.assertEqual(output.read_text(), 'preserve me')


if __name__ == '__main__':
    unittest.main()
