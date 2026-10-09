"""
Tests for the count report in qa_refresh/03_copy_sources.py. They need no ArcGIS: the script is
imported against a stand-in for arcpy.

Run from network_dataset/scripts:
  > python -m unittest discover -s tests -v
"""

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "tests"))

from test_network_definitions import load_script  # noqa: E402

PROD = "prod_view"


def load_report(counts):
    """Import the script with a fake arcpy whose GetCount comes from the counts dict."""
    module = load_script("qa_refresh/03_copy_sources.py", None)
    cfg = module.config
    paths = {cfg.EDGE: "edge", cfg.JUNCTION: "junction", cfg.TURN: "turn", PROD: "prod"}

    module.arcpy = types.SimpleNamespace(
        Exists=lambda path: counts.get(paths.get(path)) is not None,
        management=types.SimpleNamespace(
            GetCount=lambda path: [str(counts[paths[path]])]
        ),
    )

    return module


class CountReportTests(unittest.TestCase):

    def run_report(self, counts, baselines=()):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        module = load_report(counts)

        for name, report in baselines:
            (Path(directory.name) / name).write_text(json.dumps(report), encoding="utf-8")

        printed = []

        with mock.patch.object(module.config, "OUTPUT_DIR", Path(directory.name)), \
                mock.patch("builtins.print", side_effect=lambda *a, **k: printed.append(" ".join(map(str, a)))):
            module.report_counts(PROD)

        return "\n".join(printed), module

    def baseline(self, module, counts, network=None):
        return {"network": network or module.config.NETWORK, "counts": counts}

    def test_the_report_shows_the_counts_prod_and_what_was_excluded(self):
        counts = {"edge": 18595, "junction": 15424, "turn": 1238, "prod": 18670}

        text, _ = self.run_report(counts)

        self.assertIn("18,595", text)
        self.assertIn("Prod view 18,670, excluded 75", text)
        self.assertIn("15,424", text)
        self.assertIn("1,238", text)
        self.assertIn("none found", text)

    def test_the_newest_baseline_for_this_network_is_shown(self):
        counts = {"edge": 18595, "junction": 15424, "turn": 1238, "prod": 18670}
        module = load_report(counts)
        old = self.baseline(module, {"edge": 1, "junction": 2, "turn": 3})
        new = self.baseline(module, {"edge": 18583, "junction": 15424, "turn": 1189})
        other = self.baseline(module, {"edge": 9, "junction": 9, "turn": 9}, network="elsewhere")

        text, _ = self.run_report(counts, [
            ("baseline_20261008_090000.json", old),
            ("baseline_20261009_093835.json", new),
            ("baseline_20261009_999999.json", other),
        ])

        self.assertIn("last QA baseline 18,583", text)
        self.assertIn("last QA baseline 1,189 remapped", text)
        self.assertNotIn("last QA baseline 9", text)

    def test_an_empty_class_stops_the_run(self):
        counts = {"edge": 18595, "junction": 0, "turn": 1238, "prod": 18670}

        with self.assertRaises(RuntimeError) as error:
            self.run_report(counts)

        self.assertIn("junction copy is empty", str(error.exception))
        self.assertIn("Do not continue to step 04", str(error.exception))

    def test_a_missing_class_stops_the_run(self):
        counts = {"edge": 18595, "junction": 15424, "turn": None, "prod": 18670}

        with self.assertRaises(RuntimeError) as error:
            self.run_report(counts)

        self.assertIn("turn copy is empty or missing", str(error.exception))

    def test_an_edge_copy_larger_than_prod_stops_the_run(self):
        counts = {"edge": 18700, "junction": 15424, "turn": 1238, "prod": 18670}

        with self.assertRaises(RuntimeError) as error:
            self.run_report(counts)

        self.assertIn("more than Prod's 18,670", str(error.exception))


if __name__ == "__main__":
    unittest.main()
