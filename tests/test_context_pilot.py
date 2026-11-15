import json
from pathlib import Path
import tempfile
import unittest
from sgedit.context_pilot import PURPOSE, validate_manifest
from sgedit.robustness_run import digest


class ContextPilotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = self.root / "manifest.json"
        self.data = {"study_type": PURPOSE, "selection_rule": "first eligible dev ids",
                     "split_evidence": "private dev split manifest", "cases": []}
        for i in range(12):
            c = dict(case_id=f"case{i}", photo_group=f"photo{i}", split="dev", source="rice",
                     task="T1-B" if i < 6 else "T2", mask_qa="accept")
            for field in ("image", "mask", "protected_mask"):
                path = self.root / f"{i}-{field}.bin"
                path.write_bytes(path.name.encode())
                c[field], c[field + "_sha256"] = path.name, digest(path)
            self.data["cases"].append(c)

    def check(self):
        self.manifest.write_text(json.dumps(self.data))
        return validate_manifest(self.manifest, self.root)

    def test_valid_cohort_and_grouping(self):
        _, jobs = self.check()
        self.assertEqual(len(jobs), 12)

    def test_test_case_refused(self):
        self.data["cases"][0]["split"] = "test"
        with self.assertRaisesRegex(ValueError, "Only dev"):
            self.check()

    def test_changed_input_refused(self):
        (self.root / self.data["cases"][0]["image"]).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.check()

    def test_escape_refused(self):
        self.data["cases"][0]["image"] = "../secret"
        with self.assertRaisesRegex(ValueError, "within"):
            self.check()

    def test_duplicate_photo_task_refused(self):
        self.data["cases"][1].update(image_sha256=self.data["cases"][0]["image_sha256"])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.check()

    def test_split_evidence_required(self):
        self.data.pop("split_evidence")
        with self.assertRaisesRegex(ValueError, "split evidence"):
            self.check()
