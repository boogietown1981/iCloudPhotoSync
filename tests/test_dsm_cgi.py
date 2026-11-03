"""Safety regression tests for the DSM CGI Python runtime launcher."""
import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "spk" / "icloudphotosync" / "src" / "app"


class CgiRuntimeTests(unittest.TestCase):
    def test_shell_launcher_and_python_entrypoint(self):
        wrapper = APP / "api.cgi"
        entrypoint = APP / "api_main.py"
        self.assertEqual(wrapper.read_text().splitlines()[0], "#!/bin/sh")
        self.assertTrue(entrypoint.is_file())
        content = wrapper.read_text()
        self.assertIn("exec", content)
        self.assertIn("api_main.py", content)
        self.assertIn("(3,10)", content)
        self.assertIn("(3,12)", content)
        self.assertNotIn("/usr/bin/env python3", content.splitlines()[0])
        subprocess.run(["sh", "-n", str(wrapper)], check=True)

    def test_api_main_python_syntax(self):
        import ast
        ast.parse((APP / "api_main.py").read_text())


class LogInitializationTests(unittest.TestCase):
    def test_album_import_survives_unwritable_logs(self):
        lib = ROOT / "spk" / "icloudphotosync" / "src" / "lib"
        sys.path.insert(0, str(lib))
        import importlib
        import logging
        import config_manager
        import handlers.album
        orig = config_manager.PKG_VAR
        try:
            # Simulate DSM CGI having no package-log write permission.
            config_manager.PKG_VAR = "/proc/unwritable/icloudphotosync"
            with mock.patch.object(logging.root, "handlers", []):
                importlib.reload(handlers.album)
        finally:
            config_manager.PKG_VAR = orig
            importlib.reload(handlers.album)


if __name__ == "__main__":
    unittest.main()
