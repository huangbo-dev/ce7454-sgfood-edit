import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from sgedit.robustness_run import PURPOSE, validate_inputs, write_new_json


class RobustnessInputTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        self.manifest = self.root / 'manifest.json'
        self.data = {'study_type': PURPOSE, 'photos': [{'image_id': 'photo1', 'dish': 'fixture',
            'source': 'rice', 'mask_qa': 'needs-review', 'original_path': 'image.bin', 'mask_path': 'mask.bin'}]}
        for key, field in [('image.bin', 'image_sha256'), ('mask.bin', 'mask_sha256')]:
            (self.root / key).write_bytes(key.encode())
            self.data['photos'][0][field] = hashlib.sha256(key.encode()).hexdigest()

    def check(self):
        self.manifest.write_text(json.dumps(self.data))
        return validate_inputs(self.manifest, self.root, 1, 2)

    def test_flagged_photo_retained(self):
        _, jobs = self.check()
        self.assertEqual([j['mask_qa'] for j in jobs], ['needs-review', 'needs-review'])

    def test_cannot_claim_primary_test(self):
        self.data['study_type'] = 'heldout'
        with self.assertRaises(ValueError): self.check()

    def test_changed_mask_refused(self):
        (self.root / 'mask.bin').write_bytes(b'changed')
        with self.assertRaises(ValueError): self.check()

    def test_escape_refused(self):
        self.data['photos'][0]['original_path'] = '../image.bin'
        with self.assertRaises(ValueError): self.check()

    def test_duplicate_identity_refused(self):
        self.data['photos'].append(dict(self.data['photos'][0]))
        with self.assertRaises(ValueError): self.check()

    def test_unknown_qa_refused(self):
        self.data['photos'][0]['mask_qa'] = 'unknown'
        with self.assertRaises(ValueError): self.check()

    def test_wrong_task_count_refused(self):
        self.data['photos'][0]['source'] = 'noodles'
        with self.assertRaises(ValueError): self.check()

    def test_never_overwrites_lock(self):
        p = self.root / 'LOCK.json'; write_new_json(p, {'original': True})
        with self.assertRaises(FileExistsError): write_new_json(p, {'original': False})
        self.assertEqual(json.loads(p.read_text()), {'original': True})

class GeometryTests(unittest.TestCase):
    def test_binary_canvas_accepted(self):
        from sgedit.robustness_run import validate_geometry
        validate_geometry((1024,1024),(1024,1024),[0,255])
        validate_geometry((1024,1024),(1024,1024),[False,True])

    def test_wrong_canvas_rejected(self):
        from sgedit.robustness_run import validate_geometry
        with self.assertRaises(ValueError): validate_geometry((512,512),(1024,1024),[0,255])

    def test_empty_mask_rejected(self):
        from sgedit.robustness_run import validate_geometry
        with self.assertRaises(ValueError): validate_geometry((1024,1024),(1024,1024),[0])

    def test_full_mask_rejected(self):
        from sgedit.robustness_run import validate_geometry
        with self.assertRaises(ValueError): validate_geometry((1024,1024),(1024,1024),[255])

    def test_nonbinary_mask_rejected(self):
        from sgedit.robustness_run import validate_geometry
        with self.assertRaises(ValueError): validate_geometry((1024,1024),(1024,1024),[0,128,255])
