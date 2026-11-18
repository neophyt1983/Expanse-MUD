"""Supplement canonical asset measurements without creating a runtime cache."""
import asyncio
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import probe_asset_delivery as probe
from tools import sample_game_bandwidth as sample
from tools.measure_asset_delivery import local_http_probe


class ProbeTests(unittest.TestCase):
    def test_invalid_public_origins_are_refused_before_network_access(self):
        with patch.object(probe.urllib.request, 'urlopen', side_effect=AssertionError('Unexpected network request')):
            for value in ('http://localhost', 'https://secret@example.test', 'https://@example.test',
                          'https://:secret@example.test', 'https://example.test/path',
                          'https://example.test?token=secret', 'https://example.test/#fragment'):
                with self.subTest(origin=value), self.assertRaises(ValueError):
                    probe.public_probe(value)

    def test_public_probe_contains_only_aggregate_sizes_and_safe_headers(self):
        requests = []

        class Response(io.BytesIO):
            code = 200
            headers = {'Cache-Control': 'no-store', 'Set-Cookie': 'do-not-export', 'X-Private': 'do-not-export'}

        def open_request(request, **kwargs):
            requests.append(request)
            return Response(b'fixture body never exported')

        with patch.object(probe.urllib.request, 'urlopen', side_effect=open_request):
            result = probe.public_probe('https://example.test')
        self.assertEqual([request.full_url for request in requests],
                         ['https://example.test' + path for path in ('/healthz', '/', '/world-assets.js', '/visual-map.js')])
        for request in requests:
            names = {name.lower() for name, _ in request.header_items()}
            self.assertFalse({'authorization', 'cookie'} & names)
        self.assertEqual(len(result['requests']), 4)
        serialized = json.dumps(result)
        self.assertNotIn('do-not-export', serialized)
        self.assertNotIn('fixture body never exported', serialized)
        self.assertFalse(result['authenticated'])

    def test_canonical_local_probe_preserves_authentication_and_closed_mmo_gate(self):
        report = asyncio.run(local_http_probe(probe.ROOT))
        self.assertEqual(report['unauthenticated_static_status'], 401)
        self.assertEqual(report['mmo_enter_status'], 503)
        self.assertEqual(report['response_body_bytes'], report['repeat_without_validator_body_bytes'])
        for row in report['files']:
            self.assertEqual(row['cache_control'], 'no-store')
            self.assertEqual(row['status'], 200)
        conditional = next(row for row in report['files'] if row['url'] == '/world-assets.js')
        self.assertEqual(conditional['explicit_conditional_status'], 304)
        self.assertEqual(conditional['explicit_conditional_body_bytes'], 0)

    def test_both_new_probe_commands_refuse_to_overwrite_existing_user_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'existing-save.json'
            output.write_bytes(b'preserve my save')
            with patch.object(probe, 'public_probe', side_effect=AssertionError('Should refuse before networking')):
                with self.assertRaises(FileExistsError):
                    probe.main(['--public-origin', 'https://example.test', '--output', str(output)])
            with patch.object(sample.sys, 'argv', ['sample_game_bandwidth.py', '--world', temporary, '--output', str(output)]), \
                 patch.object(sample, 'measure', side_effect=AssertionError('Should refuse before copying')):
                with self.assertRaises(FileExistsError):
                    sample.main()
            self.assertEqual(output.read_bytes(), b'preserve my save')

    def test_game_sample_refuses_an_arbitrary_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, 'extracted authored world'):
                asyncio.run(sample.measure(Path(temporary)))


if __name__ == '__main__':
    unittest.main()
