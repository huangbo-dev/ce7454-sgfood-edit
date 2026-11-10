"""All tests use invented records or synthetic images, never study outputs."""
import hashlib, json, math, tempfile, unittest
from pathlib import Path
from unittest import mock
import supplemental_controls as c

class CoreTests(unittest.TestCase):
    def test_first_max_and_ordered_tie(self):
        self.assertEqual(c.first_max([.1,.4,.4,.2]),1)
    def test_nonfinite_score_rejected(self):
        for scores in ([],[math.nan],[math.inf]):
            with self.assertRaises(ValueError): c.first_max(scores)
    def test_false_acceptance_is_not_inferred(self):
        self.assertIn("not a false acceptance",c.PROTOCOL["e4"]["interpretation"])
        self.assertEqual(c.PROTOCOL["human_status"],"not collected by this tool")
    def test_checker_predicate_boundaries(self):
        q={k:{"score":v} for k,v in {"edit":1.5,"preserve":1.5,"realism":3,"extra":.5}.items()}
        self.assertTrue(c.checker_pass(q,c.PROTOCOL["e4"]["checker_thresholds"]))
        q["extra"]["score"]=.6
        self.assertFalse(c.checker_pass(q,c.PROTOCOL["e4"]["checker_thresholds"]))
    def test_fixed_recolour_values_and_monotonic_brightness(self):
        self.assertEqual(c.recolour_pixel((255,255,255)),(209,173,136))
        self.assertEqual(c.recolour_pixel((0,0,0)),(0,0,0))
        self.assertTrue(all(a<b for a,b in zip(c.recolour_pixel((80,80,80)),c.recolour_pixel((180,180,180)))))
    def test_source_protected_from_output(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError): c.output_root(Path(td)/"new",[td])
    def test_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError): c.output_root(td,[])
    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError): c.safe_path(td,"../outside")
    def test_exclusive_result_write(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"result.json";c.write_new(p,{"old":1})
            with self.assertRaises(FileExistsError):c.write_new(p,{"new":2})
            self.assertEqual(c.read_json(p),{"old":1})
    def test_partial_e4_cohort_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"manifest.json";p.write_text(json.dumps({"schema_version":1,"cases":[]}))
            with self.assertRaises(ValueError):c.snapshot_e4_inputs(td,p,"synthetic-package")
    def test_wrong_model_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            for name in ("config.json","preprocessor_config.json","tokenizer_config.json"):
                (Path(td)/name).write_text("{}")
            with self.assertRaises(ValueError):c.snapshot_model(td)
    def test_summary_preserves_denominators(self):
        rows=[{"photo_id":"p","task":"T1-B","checker_passed":True,"in_existing_pair":True},
              {"photo_id":"p","task":"T2","checker_passed":False,"in_existing_pair":False}]
        result=c.result_summary(rows)
        self.assertEqual((result["cases"],result["photos"],result["checker_passes"]),(2,1,1))
        self.assertEqual(result["additional_output_judgments_vs_existing_pairs"],1)
    def test_checker_remote_destination_rejected_before_files_read(self):
        with self.assertRaises(ValueError):c.check_e4("not-real","https://example.com","not-real")

class PixelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import numpy as np
            from PIL import Image
            cls.np,cls.Image=np,Image
        except ImportError:
            raise unittest.SkipTest("Pillow/NumPy not installed on this executor.")
    def test_only_masked_pixels_change(self):
        np=self.np
        image=np.arange(48,dtype=np.uint8).reshape(4,4,3)
        mask=np.zeros((4,4),dtype=bool);mask[1:3,1:3]=True
        output=c.recolour_arrays(image,mask)
        self.assertTrue(np.array_equal(output[~mask],image[~mask]))
        for old,new in zip(image[mask],output[mask]):self.assertEqual(tuple(new),c.recolour_pixel(tuple(old)))
    def test_empty_and_full_masks_rejected(self):
        np=self.np;image=np.zeros((3,3,3),dtype=np.uint8)
        for mask in (np.zeros((3,3),bool),np.ones((3,3),bool)):
            with self.assertRaises(ValueError):c.recolour_arrays(image,mask)
    def test_checker_crop_matches_frozen_geometry(self):
        with tempfile.TemporaryDirectory() as td:
            mask=self.Image.new("L",(1024,1024),0)
            mask.paste(255,(400,400,600,600))
            p=Path(td)/"mask.png";mask.save(p)
            self.assertEqual(c.checker_crop_box(p),[350,350,650,650])
    def test_end_to_end_synthetic_e4_cleanup_and_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"inputs";root.mkdir()
            self.Image.new("RGB",(1024,1024),(240,230,220)).save(root/"source.png")
            mask=self.Image.new("L",(1024,1024),0);mask.paste(255,(400,400,600,600));mask.save(root/"mask.png")
            image_sha=c.sha(root/"source.png");mask_sha=c.sha(root/"mask.png")
            cases=[{"photo_id":"synthetic%d"%i,"task":"T2","source":"rice","image":"source.png","mask":"mask.png",
                    "image_sha256":image_sha,"mask_sha256":mask_sha} for i in range(14)]
            manifest=Path(td)/"manifest.json";manifest.write_text(json.dumps({"schema_version":1,"cases":cases}))
            out=Path(td)/"new-output"
            with mock.patch.object(c,"review_t2_cohort",return_value={row["photo_id"]: image_sha for row in cases}):
                c.freeze_e4(root,manifest,out,"synthetic-package")
            result=c.generate_e4(out)
            self.assertEqual(result,{"controls":14,"checker":"not_run","human":"not_collected"})
            self.assertEqual(c.sha(root/"source.png"),image_sha)
            self.assertEqual(c.sha(root/"mask.png"),mask_sha)
            with self.assertRaises(ValueError):c.generate_e4(out)
            receipt=Path(td)/"runtime.json"
            c.write_new(receipt,{"checker_model_id":"synthetic","checker_model_files_sha256":"synthetic",
                                "checker_source_sha256":"synthetic","question_version":"synthetic"})
            check={k:{"score":v} for k,v in {"edit":2,"preserve":2,"realism":4,"extra":0}.items()}
            import io
            with mock.patch("urllib.request.urlopen",side_effect=lambda *a,**k:io.StringIO(json.dumps(check))) as calls:
                summary=c.check_e4(out,"http://127.0.0.1:8781",receipt)
                self.assertEqual(calls.call_count,14)
            self.assertEqual(summary["checker_passes"],14)
            self.assertIsNone(summary["false_acceptance"])
            self.assertEqual(summary["human_status"],"not_collected")
            with self.assertRaises(ValueError):c.check_e4(out,"http://127.0.0.1:8781",receipt)



class E3SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/"tuned";self.source.mkdir()
        policy={"pass":c.PROTOCOL["e4"]["checker_thresholds"],"weights":{"edit":1,"preserve":.5,"realism":.5,"extra":.5}}
        c.write_new(self.source/"LOCK.json",{"policy":policy})
        rows=[]
        check={k:{"score":v} for k,v in {"edit":2,"preserve":2,"realism":4,"extra":0}.items()}
        for i in range(34):
            key="case%02d"%i;folder=self.source/"candidates"/key;folder.mkdir(parents=True)
            for n in range(4):
                tag="seed%d"%n;image=folder/(tag+".png")
                image.write_bytes(("synthetic-not-image-%s-%s"%(key,tag)).encode())
                c.write_new(folder/(tag+".json"),{"tag":tag,"sha256":c.sha(image),"check":check,
                                               "pass":True,"score":c.checker_score(check,policy["weights"])})
            rows.append({"key":key,"image_id":"photo%02d"%(i%20),"task":"T1-B" if i<20 else "T2",
                         "source":"noodles" if 14<=i<20 else "rice","seed_tags":["seed%d"%n for n in range(4)],
                         "best_check":"seed0","retry":"seed0"})
        (self.source/"results.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))
        c.write_new(self.source/"COMPLETE.json",{"completed_jobs":34,"results_sha256":c.sha(self.source/"results.jsonl")})
        self.patch=mock.patch.dict(c.PROTOCOL["e3"],{"source_results_sha256":c.sha(self.source/"results.jsonl"),
                                                  "source_lock_sha256":c.sha(self.source/"LOCK.json")})
        self.patch.start();self.addCleanup(self.patch.stop)
    def test_all_136_candidates_and_source_files_are_locked(self):
        result=c.snapshot_run(self.root)
        self.assertEqual(len(result["cases"]),34)
        self.assertEqual(len(result["files"]),275)
    def test_candidate_tampering_is_rejected(self):
        (self.source/"candidates/case00/seed0.png").write_bytes(b"changed")
        with self.assertRaises(ValueError):c.snapshot_run(self.root)
    def test_wrong_completion_receipt_is_rejected(self):
        (self.source/"COMPLETE.json").write_text(json.dumps({"completed_jobs":33,"results_sha256":c.sha(self.source/"results.jsonl")}))
        with self.assertRaises(ValueError):c.snapshot_run(self.root)

if __name__=="__main__":
    unittest.main()
