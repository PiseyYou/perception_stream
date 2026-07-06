import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ConfigLoaderPathTest(unittest.TestCase):
    def test_script_resolves_ssh_key_path_to_project_absolute_path(self):
        result = subprocess.run(
            [sys.executable, "robot_monitor/config_loader.py"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )

        expected = PROJECT_ROOT / "data" / "conf" / "bestmow_rsa_202607"
        self.assertIn(f"SSH Key Path: {expected}", result.stdout)
        self.assertNotIn("data/conf/data/conf", result.stdout)


if __name__ == "__main__":
    unittest.main()
