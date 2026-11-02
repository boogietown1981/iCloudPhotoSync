"""Regression tests for safe file moves and incomplete media downloads."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "spk" / "icloudphotosync" / "src" / "lib"
sys.path.insert(0, str(LIB))
sys.path.insert(0, str(LIB / "vendor"))

import move_engine
import sync_engine


class SafeCrossVolumeCopyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.old = Path(self.temp.name) / "original.heic"
        self.new = Path(self.temp.name) / "destination.heic"
        self.old.write_bytes(b"original-photo-content")

    def test_verified_copy_preserves_source(self):
        move_engine._safe_cross_volume_copy(str(self.old), str(self.new))
        self.assertEqual(self.old.read_bytes(), self.new.read_bytes())
        self.assertTrue(self.old.exists())
        self.assertFalse(list(Path(self.temp.name).glob(".icloudphoto-move-*")))

    def test_destination_collision_cannot_overwrite(self):
        self.new.write_bytes(b"unrelated-existing-file")
        with self.assertRaises(FileExistsError):
            move_engine._safe_cross_volume_copy(str(self.old), str(self.new))
        self.assertEqual(self.new.read_bytes(), b"unrelated-existing-file")
        self.assertTrue(self.old.exists())

    def test_partial_copy_not_published(self):
        def partial_copy(src, dest):
            Path(dest).write_bytes(b"truncated")
        with mock.patch.object(move_engine.shutil, "copy2", side_effect=partial_copy):
            with self.assertRaises(OSError):
                move_engine._safe_cross_volume_copy(str(self.old), str(self.new))
        self.assertFalse(self.new.exists())
        self.assertEqual(self.old.read_bytes(), b"original-photo-content")
        self.assertFalse(list(Path(self.temp.name).glob(".icloudphoto-move-*")))


class DownloadVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / "photo.heic"

    def _get_session(self, chunks, content_length):
        class Response:
            status_code = 200
            headers = {"Content-Length": str(content_length)}
            def raise_for_status(self): pass
            def iter_content(self, chunk_size=65536):
                yield from chunks
        session = mock.Mock()
        session.get.return_value = Response()
        return session

    @mock.patch.object(sync_engine.time, "sleep", return_value=None)
    def test_rejects_truncated_response(self, _sleep):
        session = self._get_session([b"abc"], 7)
        self.assertFalse(sync_engine._download_file("https://example.test/1",
                                                     str(self.target), session=session))
        self.assertFalse(self.target.exists())
        self.assertFalse(Path(str(self.target) + ".part").exists())

    @mock.patch.object(sync_engine.time, "sleep", return_value=None)
    def test_rejects_apple_asset_size_mismatch(self, _sleep):
        session = self._get_session([b"abcd"], 4)
        self.assertFalse(sync_engine._download_file("https://example.test/2",
                                                     str(self.target), session=session,
                                                     expected_size=5))
        self.assertFalse(self.target.exists())

    def test_accepts_verified_size(self):
        session = self._get_session([b"abcd"], 4)
        self.assertTrue(sync_engine._download_file("https://example.test/3",
                                                    str(self.target), session=session,
                                                    expected_size=4))
        self.assertEqual(self.target.read_bytes(), b"abcd")


if __name__ == "__main__":
    unittest.main()
