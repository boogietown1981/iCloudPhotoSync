"""Python prerequisites guard against silently selecting Python 3.8/3.9."""
import subprocess
import tempfile
import tarfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class PythonPrerequisitesTests(unittest.TestCase):
    def test_both_launchers_check_python_version(self):
        scripts = [ROOT / "build.sh", ROOT / "spk" / "icloudphotosync" /
                   "src" / "service-setup.sh"]
        for path in scripts:
            body = path.read_text()
            with self.subTest(path=str(path)):
                self.assertIn("sys.version_info >= (3,10)", body)
                self.assertNotIn('[ -x "$c" ] && exit 0', body)
                self.assertNotIn('[ -x "$c" ] && { echo "$c"; return 0; }', body)

if __name__ == "__main__":
    unittest.main()
