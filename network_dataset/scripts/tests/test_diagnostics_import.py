"""
The diagnostics that import modules from the scripts folder must find them when run as a script.

Running diagnostics/11_inspect_extra_roads.py put only diagnostics/ on the path, so its imports of
connectivity_check and network_exclusions failed with ModuleNotFoundError on the first real run
(2026-10-01). This runs the script the way PyCharm does, with a stand-in arcpy that finds nothing,
so it stops at its own "Cannot find" message once its imports have worked.

Run from network_dataset/scripts:
  > python -m unittest discover -s tests -v
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DIAGNOSTICS = Path(__file__).resolve().parents[1] / "diagnostics"

# Diagnostics that import from the scripts folder.
SCRIPTS_THAT_IMPORT_SIBLINGS = ["11_inspect_extra_roads.py"]


class DiagnosticsImportTests(unittest.TestCase):

    def run_script(self, name):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "arcpy.py").write_text("def Exists(path):\n    return False\n", encoding="utf-8")
            environment = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            environment["PYTHONPATH"] = folder

            return subprocess.run(
                [sys.executable, str(DIAGNOSTICS / name)],
                cwd=folder, env=environment, capture_output=True, text=True,
            )

    def test_scripts_find_the_modules_they_import(self):
        for name in SCRIPTS_THAT_IMPORT_SIBLINGS:
            result = self.run_script(name)

            self.assertNotIn("ModuleNotFoundError", result.stderr, name)
            self.assertIn("Cannot find", result.stderr, name)

    def test_the_list_is_complete(self):
        """Any diagnostic that imports a scripts-folder module must be in the list above."""
        scripts = Path(__file__).resolve().parents[1]
        local_modules = {p.stem for p in scripts.glob("*.py") if not p.stem[0].isdigit()}
        found = []

        for path in sorted(DIAGNOSTICS.glob("*.py")):
            text = path.read_text(encoding="utf-8")

            if any(("import " + module) in text for module in local_modules):
                found.append(path.name)

        self.assertEqual(found, SCRIPTS_THAT_IMPORT_SIBLINGS)


if __name__ == "__main__":
    unittest.main()
