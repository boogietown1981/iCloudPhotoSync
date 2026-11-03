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

if __name__ == "__main__":
    unittest.main()
