"""First local scan baselines; later scans detect file changes."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
LIB = Path(__file__).resolve().parents[1] / "spk" / "icloudphotosync" / "src" / "lib"
sys.path.insert(0, str(LIB))
import integrity_checker
import sync_manifest

class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.pics = root / "pics"
        self.pics.mkdir()
        self.acc = root / "acc"
        self.acc.mkdir()
        self.file = self.pics / "one.heic"
        self.file.write_bytes(b"original")
        patch = mock.patch.multiple(integrity_checker.config_manager,
            get_account=lambda aid: {"id": aid},
            get_account_dir=lambda aid: str(self.acc),
            get_sync_config=lambda aid: {"target_dir": str(self.pics)})
        patch.start()
        self.addCleanup(patch.stop)
        db = sync_manifest._connect("demo")
        db.execute("INSERT INTO synced_photos(record_id,album,filename,local_path,size,synced_at) "
                   "VALUES(?,?,?,?,?,?)", ("one", "all", "one.heic", str(self.file), 8, 1))
        db.commit()
        db.close()

    def test_baseline_verify_change_missing(self):
        s = integrity_checker.scan("demo")
        self.assertEqual((s["status"], s["baselined"]), ("complete", 1))
        s = integrity_checker.scan("demo")
        self.assertEqual(s["verified"], 1)
        self.file.write_bytes(b"changed")
        s = integrity_checker.scan("demo")
        self.assertEqual((s["status"], s["changed"]), ("issues", 1))
        self.assertTrue(self.file.is_file())
        self.file.unlink()
        s = integrity_checker.scan("demo")
        self.assertEqual(s["missing"], 1)

    def test_symlink_denied(self):
        outside = self.acc / "private"
        outside.write_bytes(b"data")
        self.file.unlink()
        self.file.symlink_to(outside)
        s = integrity_checker.scan("demo")
        self.assertEqual(s["errors"], 1)
        self.assertTrue(outside.exists())

    def test_complete_report_lists_all_findings_and_preview_is_read_only(self):
        # First completed audit establishes a baseline.
        s = integrity_checker.scan("demo")
        self.assertEqual(s["status"], "complete")
        self.file.write_bytes(b"changed-contents")
        from integrity_report import report_page, iter_findings
        before = self.file.read_bytes()
        s = integrity_checker.scan("demo")
        self.assertEqual(s["report_issue_count"], 1)
        self.assertEqual(s["changed"], 1)
        findings = list(iter_findings("demo"))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["kind"], "changed")
        self.assertEqual(findings[0]["path"], "one.heic")
        page = report_page("demo", offset=0, limit=25)
        self.assertTrue(page["available"])
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["findings"][0]["suggested_action"],
                         "review_and_redownload_from_icloud")
        self.assertEqual(before, self.file.read_bytes())

    def test_interrupted_scan_keeps_prior_complete_report(self):
        integrity_checker.scan("demo")
        self.file.unlink()
        integrity_checker.scan("demo")
        old_report = integrity_checker.report_path("demo")
        snapshot = Path(old_report).read_bytes()
        self.file.write_bytes(b"newphoto")  # same length as baseline
        with mock.patch.object(integrity_checker, "_digest",
                               side_effect=RuntimeError("synthetic failure")):
            result = integrity_checker.scan("demo")
        self.assertEqual(result["status"], "error")
        self.assertEqual(Path(old_report).read_bytes(), snapshot)
        from integrity_report import report_page
        self.assertTrue(report_page("demo")["stale"])

    def test_unsafe_path_is_redacted_in_export(self):
        outside = self.acc / "hidden-key-file"
        outside.write_bytes(b"data")
        self.file.unlink()
        self.file.symlink_to(outside)
        integrity_checker.scan("demo")
        from integrity_report import iter_findings
        entries = list(iter_findings("demo"))
        self.assertEqual(entries[0]["kind"], "unsafe")
        self.assertEqual(entries[0]["path"], "[outside target]")
        self.assertNotIn("hidden-key-file", str(entries))
        self.assertTrue(outside.exists())

    def test_full_report_exceeds_25_sample_limit(self):
        from integrity_report import iter_findings, report_page
        db = sync_manifest._connect("demo")
        try:
            for i in range(37):
                path = self.pics / ("missing_%03d.jpg" % i)
                db.execute(
                    "INSERT INTO synced_photos(record_id,album,filename,local_path,size,synced_at) "
                    "VALUES(?,?,?,?,?,?)",
                    ("miss_%03d" % i, "all", path.name, str(path), 123, 1))
            db.commit()
        finally:
            db.close()
        state = integrity_checker.scan("demo")
        self.assertEqual(state["missing"], 37)
        self.assertEqual(state["report_issue_count"], 37)
        self.assertEqual(len(state["samples"]), 25)
        self.assertEqual(len(list(iter_findings("demo"))), 37)
        page = report_page("demo", offset=20, limit=30)
        self.assertEqual(len(page["findings"]), 17)
        self.assertEqual(page["total"], 37)

if __name__ == "__main__":
    unittest.main()
