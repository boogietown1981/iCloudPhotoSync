"""Streaming ZIP tests: complete transfer, missing asset, duplicate names."""
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "spk" / "icloudphotosync" / "src" / "app"
LIB = ROOT / "spk" / "icloudphotosync" / "src" / "lib"
sys.path.insert(0, str(LIB))
# DSM packages write logs in their var directory at import time. Provide
# an isolated fixture path before loading the CGI and its handlers.
_TEST_PKG = tempfile.TemporaryDirectory()
os.environ["SYNOPKG_PKGVAR"] = _TEST_PKG.name
import config_manager
config_manager.PKG_VAR = _TEST_PKG.name
import requests
import importlib.util

spec = importlib.util.spec_from_file_location("ics_api", APP / "api.cgi")
# CGI is a script without .py extension; use a SourceFileLoader explicitly.
from importlib.machinery import SourceFileLoader
spec = importlib.util.spec_from_loader(
    "ics_api", SourceFileLoader("ics_api", str(APP / "api.cgi")))
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class MockResponse:
    def __init__(self, chunks, reported_length, status=200):
        self.chunks = chunks
        self.headers = {"Content-Length": str(reported_length)}
        self.status = status
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def raise_for_status(self):
        if self.status != 200:
            raise requests.HTTPError(str(self.status))
    def iter_content(self, chunk_size=262144):
        yield from self.chunks


class StreamingExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def test_zero_zip_buffer_and_successful_media(self):
        session = mock.Mock()
        session.get.return_value = MockResponse([b"abc", b"def"], 6)
        out = io.BytesIO()
        stats = api._stream_export_zip(
            [{"url": "https://a.icloud-content.com/x", "filename": "photo.jpg"}],
            out, requests_module=session, temp_dir=self.temp.name)
        self.assertEqual(stats, {"exported": 1, "failed": 0})
        with zipfile.ZipFile(io.BytesIO(out.getvalue())) as z:
            self.assertEqual(z.read("photo.jpg"), b"abcdef")

    def test_partial_download_does_not_enter_zip(self):
        session = mock.Mock()
        session.get.return_value = MockResponse([b"abc"], 10)
        out = io.BytesIO()
        stats = api._stream_export_zip(
            [{"url": "https://a.icloud-content.com/x", "filename": "broken.jpg"}],
            out, requests_module=session, temp_dir=self.temp.name)
        self.assertEqual(stats["failed"], 1)
        with zipfile.ZipFile(io.BytesIO(out.getvalue())) as z:
            self.assertNotIn("broken.jpg", z.namelist())
            self.assertIn("broken.jpg", z.read("_EXPORT_ERRORS.txt").decode())

    def test_duplicate_names_do_not_overwrite(self):
        session = mock.Mock()
        session.get.return_value = MockResponse([b"ok"], 2)
        out = io.BytesIO()
        api._stream_export_zip([
            {"url": "https://a.icloud-content.com/1", "filename": "one.jpg"},
            {"url": "https://a.icloud-content.com/2", "filename": "one.jpg"}
        ], out, requests_module=session, temp_dir=self.temp.name)
        with zipfile.ZipFile(io.BytesIO(out.getvalue())) as z:
            self.assertEqual(set(z.namelist()), {"one.jpg", "one_2.jpg"})

    def test_form_payload_and_https_policy(self):
        payload = json.dumps({"items": [{"filename": "a.jpg", "url": "https://a.icloud-content.com/x"}]})
        from urllib.parse import urlencode
        self.assertEqual(api._parse_export_request(urlencode({"payload": payload}),
                         "application/x-www-form-urlencoded")["items"][0]["filename"], "a.jpg")
        self.assertFalse(api._is_icloud_url("http://a.icloud-content.com/x"))
        self.assertFalse(api._is_icloud_url("https://icloud-content.com.attacker.com/x"))


if __name__ == "__main__":
    unittest.main()
