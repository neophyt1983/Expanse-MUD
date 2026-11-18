"""The optional native seed cannot read arbitrary files or bypass host scope."""
import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import MappingProxyType
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from server import desktop_asset_seed as seed


class DesktopAssetSeedTests(unittest.TestCase):
    def fixture(self, root):
        public = b'approved presentation bytes'
        private = b'never return these world definitions'
        output = BytesIO()
        with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
            archive.writestr('assets/terrain/public.png', public)
            archive.writestr('assets/updates/private.json', private)
        raw = output.getvalue()
        folder = Path(root) / 'worlds'
        folder.mkdir()
        path = folder / seed.ARCHIVE_NAME
        path.write_bytes(raw)
        checksum = hashlib.sha256(public).hexdigest()
        registry = MappingProxyType({'assets/terrain/public.png': (len(public), checksum, 'image/png')})
        return public, private, raw, checksum, registry, path

    def settings(self, root, raw, registry):
        return patch.multiple(seed, APPLICATION_ROOT=Path(root), ARCHIVE_SIZE=len(raw),
                              ARCHIVE_SHA256=hashlib.sha256(raw).hexdigest(), PUBLIC_PRESENTATION=registry)

    def test_only_reviewed_hashes_return_public_bytes_and_never_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            public, private, raw, checksum, registry, path = self.fixture(temporary)
            sentinel = Path(temporary) / 'save.db'
            sentinel.write_bytes(b'preserve user data')
            with self.settings(temporary, raw, registry):
                cache = seed.BundledAssetSeed()
                with patch.object(seed, '_released_archive', side_effect=AssertionError('Unknown hash did disk I/O')):
                    for value in ('../save.db', 'https://example.test/file', '', 'A' * 64,
                                  hashlib.sha256(private).hexdigest(), None):
                        self.assertEqual(cache.get(value), '')
                self.assertEqual(base64.b64decode(cache.get(checksum)), public)
                with patch.object(seed, '_released_archive', side_effect=AssertionError('Verified seed re-read')):
                    self.assertEqual(base64.b64decode(cache.get(checksum)), public)
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(sentinel.read_bytes(), b'preserve user data')
            self.assertEqual(sorted(p.name for p in Path(temporary).iterdir()), ['save.db', 'worlds'])

    def test_archive_size_and_hash_are_verified_before_zip_parsing(self):
        with tempfile.TemporaryDirectory() as temporary:
            _public, _private, raw, checksum, registry, path = self.fixture(temporary)
            with self.settings(temporary, raw, registry), patch.object(seed, 'ZipFile', side_effect=AssertionError('Unverified ZIP parsed')):
                path.write_bytes(raw + b'x')
                self.assertEqual(seed.BundledAssetSeed().get(checksum), '')
                path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
                self.assertEqual(seed.BundledAssetSeed().get(checksum), '')

    def test_linked_archive_and_world_directory_are_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            _public, _private, raw, checksum, registry, path = self.fixture(temporary)
            original = Path(temporary) / 'outside.expanse'
            original.write_bytes(raw)
            path.unlink()
            try:
                path.symlink_to(original)
            except OSError as error:
                self.skipTest(str(error))
            with self.settings(temporary, raw, registry):
                self.assertEqual(seed.BundledAssetSeed().get(checksum), '')
            path.unlink()
            path.parent.rmdir()
            outside = Path(temporary) / 'outside-worlds'
            outside.mkdir()
            (outside / seed.ARCHIVE_NAME).write_bytes(raw)
            path.parent.symlink_to(outside, target_is_directory=True)
            with self.settings(temporary, raw, registry):
                self.assertEqual(seed.BundledAssetSeed().get(checksum), '')

    def test_entry_digest_and_size_are_verified_independently(self):
        with tempfile.TemporaryDirectory() as temporary:
            public, _private, raw, checksum, registry, _path = self.fixture(temporary)
            for bad_size, bad_hash in ((len(public) + 1, checksum), (len(public), '0' * 64)):
                bad = {'assets/terrain/public.png': (bad_size, bad_hash, 'image/png')}
                with self.subTest(size=bad_size, digest=bad_hash), self.settings(temporary, raw, bad):
                    self.assertEqual(seed.BundledAssetSeed().get(bad_hash), '')

    def test_new_registry_keeps_unchanged_seeds_when_other_entries_change_or_are_absent(self):
        good = b'unchanged public media'
        old = b'previous public media'
        changed = b'new!' + old[4:]  # Same length; identity must depend on SHA-256.
        missing = b'newly approved absent media'
        digest = lambda value: hashlib.sha256(value).hexdigest()
        registry = {
            'assets/terrain/changed.png': (len(changed), digest(changed), 'image/png'),
            'assets/terrain/absent.png': (len(missing), digest(missing), 'image/png'),
            'assets/terrain/unchanged.png': (len(good), digest(good), 'image/png'),
        }
        output = BytesIO()
        with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
            archive.writestr('assets/terrain/changed.png', old)
            archive.writestr('assets/terrain/unchanged.png', good)
        raw = output.getvalue()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'worlds' / seed.ARCHIVE_NAME
            path.parent.mkdir()
            path.write_bytes(raw)
            with self.settings(temporary, raw, registry):
                cache = seed.BundledAssetSeed()
                self.assertEqual(cache.get(digest(changed)), '')
                self.assertEqual(cache.get(digest(missing)), '')
                self.assertEqual(base64.b64decode(cache.get(digest(good))), good)
                self.assertEqual(cache.get(digest(old)), '')
            self.assertEqual(path.read_bytes(), raw)

    @unittest.skipUnless(shutil.which('node'), 'Node is required for the synthetic bridge fixture')
    def test_optional_qt_bridge_wrapper_has_bounded_callback_and_timeout(self):
        overlay = Path(__file__).resolve().parents[1] / 'desktop' / 'qt-bundled-media-1.9.17.1.patch'
        added = '\n'.join(line[1:] for line in overlay.read_text().splitlines()
                          if line.startswith('+') and not line.startswith('+++'))
        bridge = added[added.index('    const bundled ='):]
        bridge = bridge[:bridge.index("    window.dispatchEvent(new Event('expanse:bundled-assets'));")]
        script = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const source = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const hash = 'a'.repeat(64);
function fixture(native) {
  let next = 0;
  const timers = new Map();
  const context = {channel:{objects:{bundledAssets:native}},window:{},
    setTimeout(fn) { timers.set(++next, fn); return next; },
    clearTimeout(id) { timers.delete(id); }};
  vm.runInNewContext(source, context);
  assert(Object.isFrozen(context.window.ExpanseBundledAssets));
  return {get:context.window.ExpanseBundledAssets.get, timers};
}
(async () => {
  let calls = 0;
  const good = fixture({getBundledAsset(value, callback) {
    calls++; assert.equal(value, hash); callback('cHVibGlj');
  }});
  assert.equal(await good.get('../save.db'), null);
  assert.equal(calls, 0);
  assert.equal(await good.get(hash), 'cHVibGlj');
  assert.equal(good.timers.size, 0);
  assert.equal(await fixture({getBundledAsset(h, cb) {cb('A'.repeat(700000));}}).get(hash), null);
  assert.equal(await fixture({getBundledAsset() {throw Error('unavailable');}}).get(hash), null);
  assert.equal(await fixture(undefined).get(hash), null);
  let late;
  const missing = fixture({getBundledAsset(h, cb) {late = cb;}});
  const pending = missing.get(hash);
  assert.equal(missing.timers.size, 1);
  [...missing.timers.values()][0]();
  assert.equal(await pending, null);
  late('cHVibGlj');
  assert.equal(missing.timers.size, 0);
})().catch(error => {console.error(error); process.exitCode = 1;});
'''
        subprocess.run([shutil.which('node'), '-e', script], input=json.dumps(bridge),
                       text=True, check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
