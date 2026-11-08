import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from sgedit.preflight import check


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = self.root / 'manifest.json'
        self.h = hashlib.sha256(b'source-photo-fixture').hexdigest()
        self.iid = self.h[:12]
        d = self.root / 'data' / 'test' / self.iid
        d.mkdir(parents=True)
        # Byte fixtures test the hash contract, not image decoding or mask semantics.
        (d / 'image.png').write_bytes(b'processed-image-fixture')
        (d / 'mask.png').write_bytes(b'processed-mask-fixture')
        self.data = {'n_photos': 1, 'frozen_at': 'fixture', 'photos': [{
            'image_id': self.iid, 'source': 'rice', 'source_sha256': self.h,
            'file': 'fixture.jpg', 'dish': 'rice fixture',
            'mask_source_sha256': hashlib.sha256(b'source-mask-fixture').hexdigest(),
            'image_sha256': hashlib.sha256((d / 'image.png').read_bytes()).hexdigest(),
            'mask_sha256': hashlib.sha256((d / 'mask.png').read_bytes()).hexdigest()}],
            'jobs': [{'image_id': self.iid, 'source': 'rice', 'task': t,
                      'original_path': 'data/test/' + self.iid + '/image.png',
                      'mask_path': 'data/test/' + self.iid + '/mask.png'} for t in ['T1-B', 'T2']]}
        self.dev = [hashlib.sha256(b'development-fixture').hexdigest()]

    def run_check(self, data=None, dev=None):
        self.manifest.write_text(json.dumps(self.data if data is None else data))
        return check(self.manifest, self.root, self.dev if dev is None else dev)

    def test_valid_contract(self):
        self.assertEqual(self.run_check(), [])

    def test_missing_manifest(self):
        self.assertIn('Missing held-out manifest', check(self.manifest, self.root)[0])

    def test_overlap(self):
        self.assertTrue(any('overlap' in x for x in self.run_check(dev=[self.h])))

    def test_hash_mismatch(self):
        (self.root / 'data' / 'test' / self.iid / 'mask.png').write_bytes(b'changed')
        self.assertTrue(any('hash mismatch' in x for x in self.run_check()))

    def test_duplicate_photo(self):
        self.data['photos'].append(copy.deepcopy(self.data['photos'][0]))
        self.assertTrue(any('Duplicate photo' in x for x in self.run_check()))

    def test_incomplete_tasks(self):
        self.data['jobs'].pop()
        self.assertTrue(any('task coverage' in x for x in self.run_check()))

    def test_escape_path(self):
        self.data['jobs'][0]['original_path'] = '../outside.png'
        self.assertTrue(any('Unexpected job path' in x for x in self.run_check()))

    def test_invalid_development_hash(self):
        self.assertTrue(any('Invalid development' in x for x in self.run_check(dev=['bad'])))

    def test_malformed_manifest(self):
        self.manifest.write_text('{broken')
        self.assertIn('Unreadable manifest', check(self.manifest, self.root, self.dev)[0])

    def test_missing_development_inventory(self):
        self.manifest.write_text(json.dumps(self.data))
        self.assertTrue(any('not supplied' in x for x in check(self.manifest, self.root)))


if __name__ == '__main__':
    unittest.main()
