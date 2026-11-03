"""Structural regression tests for DSM Integrity tab discoverability.

Runtime widget validation still requires installing on Synology DSM.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "spk" / "icloudphotosync" / "src" / "app"


class IntegrityUiLayoutTests(unittest.TestCase):
    def setUp(self):
        self.js = (APP / "iCloudPhotoSync.js").read_text()
        self.cfg = json.loads((APP / "config").read_text())
        self.definition = self.cfg["iCloudPhotoSync.js"]["SYNO.SDS.iCloudPhotoSync.Instance"]

    def test_dedicated_tab_is_instantiated_and_registered(self):
        self.assertIn("this.integrityTab = new SYNO.SDS.iCloudPhotoSync.IntegrityTab", self.js)
        self.assertIn("this.logTab,\n                this.integrityTab,\n                this.aboutTab", self.js)
        self.assertIn('Ext.define("SYNO.SDS.iCloudPhotoSync.IntegrityTab"', self.js)
        self.assertIn("SYNO.SDS.iCloudPhotoSync.IntegrityTab", self.definition["depend"])
        self.assertIn("SYNO.SDS.iCloudPhotoSync.IntegrityTab",
                      self.cfg["iCloudPhotoSync.js"])

    def test_buttons_are_not_in_crowded_logs_toolbar(self):
        log_segment = self.js.split("// --- Log Viewer (Placeholder) ---", 1)[1].split(
            "// --- Photo Integrity (dedicated tab", 1)[0]
        for key in ("log:btn_integrity", "log:btn_repair_preview",
                    "log:btn_integrity_report"):
            self.assertNotIn(key, log_segment)
            self.assertIn(key, self.js)

    def test_buttons_are_three_separate_rows(self):
        segment = self.js.split("// --- Photo Integrity (dedicated tab", 1)[1]
        self.assertIn("var actionRows = [startBtn, previewBtn, exportBtn]", segment)
        self.assertIn("height: 46", segment)
        self.assertIn("_startScan: function", segment)
        self.assertIn("_preview: function", segment)
        self.assertIn("_exportReport: function", segment)

    def test_translations_are_preloaded_for_both_languages(self):
        needed = ["tab:integrity", "integrity:title",
                  "integrity:description", "integrity:status_idle",
                  "integrity:status_running", "integrity:status_issues",
                  "log:btn_integrity", "log:btn_repair_preview",
                  "log:btn_integrity_report"]
        for key in needed:
            self.assertIn(key, self.definition["preloadTexts"])
        for locale in ("ger", "enu"):
            s = (APP / "texts" / locale / "strings").read_text()
            self.assertIn("[integrity]", s)
            self.assertRegex(s, r"(?m)^integrity\s*=\s*\"")
            for key in ("title", "description", "status_idle", "status_running"):
                self.assertRegex(s, rf"(?m)^{key}\s*=\s*\"")


if __name__ == "__main__":
    unittest.main()
