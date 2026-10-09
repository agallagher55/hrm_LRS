"""
Tests for qa_refresh/collect_build_errors.py. They need no ArcGIS.

Run from network_dataset/scripts:
  > python -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "tests"))

from test_network_definitions import load_script  # noqa: E402

JUNCTION = "Source table [SDEADM.TRNLRS_street_junction], Object ID [{}]: Standalone user-defined junction is detected."
TURN = "Source table [SDEADM.TRNLRS_traffic_turn], Object ID [{}]: Cannot find at junction."


def errors_text(junctions, turns):
    return "\n".join([JUNCTION.format(n) for n in junctions] + [TURN.format(n) for n in turns]) + "\n"


def log_text(path):
    return (
        "2026-10-09 10:14:24 | INFO | Build complete.\n"
        "WARNING 030116: The network was built, but with some errors.  "
        f'Error details are at "{path}".\n'
    )


class CollectTests(unittest.TestCase):

    def setUp(self):
        self.module = load_script("qa_refresh/collect_build_errors.py", None)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.logs = self.root / "logs"
        self.results = self.root / "intermediate_results"
        self.temp = self.root / "temp"

        for path in (self.logs, self.results, self.temp):
            path.mkdir()

    def write_log(self, stamp, path):
        log = self.logs / f"{stamp}_03_create_network_dataset.log"
        log.write_text(log_text(path) if path else "2026-10-09 | INFO | Copy-only mode.\n", encoding="utf-8")

        return log

    def run_main(self):
        printed = []

        with mock.patch.object(self.module, "LOG_DIR", self.logs), \
                mock.patch.object(self.module, "RESULTS_DIR", self.results), \
                mock.patch("builtins.print", side_effect=lambda *a, **k: printed.append(" ".join(map(str, a)))):
            result = self.module.main()

        return result, "\n".join(printed)

    def test_parse_counts_each_kind(self):
        errors, unparsed = self.module.parse_errors(errors_text([1, 2, 3], [686, 746]) + "something else\n")

        self.assertEqual(len(errors), 5)
        self.assertEqual(unparsed, 1)
        counts = self.module.summarise(errors)
        self.assertEqual(counts[("SDEADM.TRNLRS_traffic_turn", "Cannot find at junction")], 2)
        self.assertEqual(counts[("SDEADM.TRNLRS_street_junction", "Standalone user-defined junction is detected")], 3)

    def test_the_newest_log_with_a_path_is_used(self):
        self.write_log("20261008_090000", "C:/old/BuildErrors_old.txt")
        newest = self.write_log("20261009_101349", "C:/new/BuildErrors_new.txt")
        self.write_log("20261009_110000", None)

        log, path = self.module.find_error_path(self.logs)

        self.assertEqual(log, newest)
        self.assertEqual(path, "C:/new/BuildErrors_new.txt")

    def test_no_log_with_a_path_gives_none(self):
        self.write_log("20261009_101349", None)

        self.assertEqual(self.module.find_error_path(self.logs), (None, None))

    def test_the_file_is_copied_and_summarised(self):
        source = self.temp / "BuildErrors_new.txt"
        source.write_text(errors_text([1, 2], [686]), encoding="utf-8")
        self.write_log("20261009_101349", str(source))

        result, text = self.run_main()

        self.assertTrue((self.results / "BuildErrors_new.txt").exists())
        self.assertEqual(result["total"], 3)
        self.assertIn("3 errors and warnings", text)
        self.assertIn("No earlier BuildErrors file", text)

    def test_it_compares_with_the_previous_file_and_the_same_turns(self):
        earlier = self.results / "BuildErrors_old.txt"
        earlier.write_text(errors_text(range(1133), [686, 746]), encoding="utf-8")
        os.utime(earlier, (1, 1))
        source = self.temp / "BuildErrors_new.txt"
        source.write_text(errors_text(range(1153), [686, 746]), encoding="utf-8")
        self.write_log("20261009_101349", str(source))

        result, text = self.run_main()

        self.assertIn("Compared with BuildErrors_old.txt", text)
        comparison = [line for line in text.splitlines() if "Standalone user-defined junction" in line and "->" in line]
        self.assertEqual(len(comparison), 1)
        self.assertIn("1,133", comparison[0])
        self.assertIn("1,153", comparison[0])
        self.assertIn("the same turns", text)
        self.assertTrue(result["same_turns"])

    def test_different_rejected_turns_are_called_out(self):
        earlier = self.results / "BuildErrors_old.txt"
        earlier.write_text(errors_text([1], [686]), encoding="utf-8")
        os.utime(earlier, (1, 1))
        source = self.temp / "BuildErrors_new.txt"
        source.write_text(errors_text([1], [686, 999]), encoding="utf-8")
        self.write_log("20261009_101349", str(source))

        result, text = self.run_main()

        self.assertIn("DIFFERENT turns", text)
        self.assertFalse(result["same_turns"])

    def test_a_cleaned_up_temp_file_is_an_error(self):
        self.write_log("20261009_101349", str(self.temp / "BuildErrors_gone.txt"))

        with self.assertRaises(RuntimeError) as error:
            self.run_main()

        self.assertIn("no longer exists", str(error.exception))

    def test_no_log_is_an_error(self):
        with self.assertRaises(RuntimeError) as error:
            self.run_main()

        self.assertIn("No log", str(error.exception))

    def test_running_it_twice_does_not_copy_again(self):
        source = self.temp / "BuildErrors_new.txt"
        source.write_text(errors_text([1], [686]), encoding="utf-8")
        self.write_log("20261009_101349", str(source))

        self.run_main()
        _, text = self.run_main()

        self.assertIn("Already saved", text)


if __name__ == "__main__":
    unittest.main()
