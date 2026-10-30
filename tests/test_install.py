import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class InstallScriptTest(unittest.TestCase):
    def test_installs_symlinks_and_desktop_entry_into_home(self):
        with tempfile.TemporaryDirectory() as home:
            env = {k: v for k, v in os.environ.items() if k != "XDG_DATA_HOME"}
            env["HOME"] = home

            subprocess.run(["sh", str(ROOT / "install.sh")], env=env, check=True,
                           capture_output=True)

            for name in ("fknm", "fknm-rofi"):
                link = Path(home, ".local/bin", name)
                self.assertEqual(link.resolve(), ROOT / "bin" / name)
            desktop = Path(home, ".local/share/applications/io.github.krupis294.Fknm.desktop")
            self.assertIn(f"Exec={ROOT}/bin/fknm\n", desktop.read_text())


if __name__ == "__main__":
    unittest.main()
