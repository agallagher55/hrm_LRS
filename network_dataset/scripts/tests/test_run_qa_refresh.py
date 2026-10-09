"""
Tests for qa_refresh/run_qa_refresh.py. They need no ArcGIS: the step scripts are replaced by
fakes that record how they were called.

Run from network_dataset/scripts:
  > python -m unittest discover -s tests -v
"""

import contextlib
import io
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "tests"))

from test_network_definitions import load_script  # noqa: E402

KEYS = ["preflight", "backup", "audit_before", "delete", "copy", "remap", "verify_staging",
        "build", "verify_live", "build_errors", "metadata", "grants", "audit_after", "topology", "smoke"]

STEP_FILES = {
    "00_confirm_sources.py": "preflight",
    "01_backup_and_baseline.py": "backup",
    "02_delete_network_sources.py": "delete",
    "03_copy_sources.py": "copy",
    "04_remap_turns.py": "remap",
    "05_verify_staging_turns.py": "verify_staging",
    "06_swap_and_final_build.py": "build",
    "07_verify_live_turns.py": "verify_live",
    "collect_build_errors.py": "build_errors",
    "grant_network_access.py": "grants",
    "07_create_topology.py": "topology",
    "smoke_test_network.py": "smoke",
}


class FakeSteps:
    """Stands in for load_step. Records each main() call with the flags set at that moment."""

    def __init__(self, behaviour=None, grants_missing=7):
        self.calls = []
        self.behaviour = behaviour or {}
        self.grants_missing = grants_missing

    def load(self, filename, directory=None):
        calls = self.calls
        behaviour = self.behaviour
        module = types.SimpleNamespace(
            CONFIRM_DELETE_QA_NETWORK=False, NETWORK_TO_DELETE="?",
            CONFIRM_REVIEWED_STAGING=False, NETWORK_TO_BUILD="?",
            LABEL=None, APPLY=False,
        )
        key = STEP_FILES.get(filename, filename)

        def main():
            calls.append((key, dict(vars(module))))
            action = behaviour.get(key)

            if action:
                action()

            if filename == "grant_network_access.py":
                return self.grants_missing

        module.main = main

        return module

    def keys(self):
        return [key for key, _ in self.calls]


class RunnerTests(unittest.TestCase):

    def setUp(self):
        self.module = load_script("qa_refresh/run_qa_refresh.py", None)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.output = Path(self.folder.name)
        self.printed = []
        self.stamped = []
        self.fake_metadata = types.SimpleNamespace(stamp=self.fake_stamp)
        self.answers = []
        self.asked = []

        for patcher in (
            mock.patch.object(self.module.config, "OUTPUT_DIR", self.output),
            mock.patch.object(self.module, "check_network", lambda: None),
            mock.patch.object(self.module, "deploy_check", types.SimpleNamespace(require_current=lambda: None)),
            mock.patch.object(self.module, "ask", self.fake_ask),
            mock.patch.object(self.module, "START_AT", None),
            mock.patch.object(self.module, "STOP_AFTER", None),
            mock.patch.object(self.module, "NETWORK", "DISTANCE"),
            mock.patch.object(self.module, "network_metadata", self.fake_metadata),
            mock.patch.object(self.module, "COPY_FINISHED", None),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def fake_stamp(self, path, logger=None, rebuilt=None, refreshed=None):
        self.stamped.append((path, rebuilt, refreshed))

        return True

    def fake_ask(self, prompt):
        self.asked.append(prompt)

        return self.answers.pop(0) if self.answers else ""

    def run_main(self, steps, answers=("DELETE QA NETWORK", "REVIEWED", "GRANT"), **settings):
        self.answers = list(answers)

        for name, value in settings.items():
            patcher = mock.patch.object(self.module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        buffer = io.StringIO()

        try:
            with mock.patch.object(self.module, "load_step", steps.load), \
                    contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                return self.module.main()
        finally:
            self.printed = [buffer.getvalue()]

    def report(self):
        files = list(self.output.glob("refresh_report_*.md"))
        self.assertEqual(len(files), 1)

        return files[0].read_text(encoding="utf-8")

    def test_the_metadata_phase_records_the_copy_time_after_a_full_run(self):
        self.run_main(FakeSteps())

        self.assertEqual(len(self.stamped), 1)
        path, rebuilt, refreshed = self.stamped[0]
        self.assertEqual(path, self.module.config.NETWORK)
        self.assertIsNone(rebuilt)
        self.assertIsNotNone(refreshed)

    def test_a_run_that_resumes_after_the_copy_leaves_the_refresh_time_alone(self):
        self.run_main(FakeSteps(), START_AT="verify_live")

        self.assertEqual(self.stamped, [])

    def test_the_phase_keys_are_what_the_tests_expect(self):
        self.assertEqual([phase.key for phase in self.module.PHASES], KEYS)

    def test_list_only_prints_the_plan_and_runs_nothing(self):
        steps = FakeSteps()

        self.run_main(steps, LIST_ONLY=True)

        self.assertEqual(steps.calls, [])
        text = "\n".join(self.printed)
        self.assertIn("DELETE QA NETWORK", text)
        self.assertIn("REVIEWED", text)

    def test_a_full_run_goes_in_order_with_the_flags_set(self):
        steps = FakeSteps()

        self.run_main(steps)

        self.assertEqual(steps.keys(), [
            "preflight", "backup", "audit_grants.py", "delete", "copy", "remap", "verify_staging", "build",
            "verify_live", "build_errors", "grants", "grants", "audit_grants.py", "topology", "smoke",
        ])
        flags = {key: flags for key, flags in steps.calls}
        self.assertTrue(flags["delete"]["CONFIRM_DELETE_QA_NETWORK"])
        self.assertEqual(flags["delete"]["NETWORK_TO_DELETE"], "DISTANCE")
        self.assertTrue(flags["build"]["CONFIRM_REVIEWED_STAGING"])
        self.assertEqual(flags["build"]["NETWORK_TO_BUILD"], "DISTANCE")
        self.assertIn("completed", self.report())

    def test_the_audits_get_their_labels_and_the_grants_run_dry_then_applied(self):
        steps = FakeSteps()

        self.run_main(steps)

        audits = [flags["LABEL"] for key, flags in steps.calls if key == "audit_grants.py"]
        self.assertEqual(audits, ["before", "after"])
        grants = [flags["APPLY"] for key, flags in steps.calls if key == "grants"]
        self.assertEqual(grants, [False, True])

    def test_three_gates_are_asked_in_order(self):
        steps = FakeSteps()

        self.run_main(steps)

        self.assertEqual(len(self.asked), 3)
        self.assertIn("DELETE QA NETWORK", self.asked[0])
        self.assertIn("REVIEWED", self.asked[1])
        self.assertIn("GRANT", self.asked[2])

    def test_declining_the_delete_gate_deletes_nothing_and_stops(self):
        steps = FakeSteps()

        self.run_main(steps, answers=("no",))

        self.assertNotIn("delete", steps.keys())
        self.assertNotIn("copy", steps.keys())
        self.assertIn("stopped at a gate", self.report())

    def test_a_wrong_phrase_does_not_count(self):
        steps = FakeSteps()

        self.run_main(steps, answers=("delete qa network",))

        self.assertNotIn("delete", steps.keys())

    def test_declining_the_build_gate_leaves_the_network_deleted_but_does_not_swap(self):
        steps = FakeSteps()

        self.run_main(steps, answers=("DELETE QA NETWORK", "yes"))

        self.assertIn("verify_staging", steps.keys())
        self.assertNotIn("build", steps.keys())
        self.assertNotIn("grants", steps.keys())

    def test_nothing_to_grant_skips_the_grant_gate(self):
        steps = FakeSteps(grants_missing=0)

        self.run_main(steps, answers=("DELETE QA NETWORK", "REVIEWED"))

        self.assertEqual(len(self.asked), 2)
        self.assertEqual([k for k in steps.keys() if k == "grants"], ["grants"])
        self.assertEqual(steps.keys()[-1], "smoke")

    def test_a_failing_step_stops_the_run_and_says_where_to_resume(self):
        def fail():
            raise RuntimeError("skip rate 40%")

        steps = FakeSteps({"remap": fail})

        with self.assertRaises(SystemExit) as error:
            self.run_main(steps)

        self.assertEqual(error.exception.code, 1)
        self.assertNotIn("verify_staging", steps.keys())
        self.assertNotIn("build", steps.keys())
        text = "\n".join(self.printed)
        self.assertIn("START_AT = 'remap'", text)
        report = self.report()
        self.assertIn("FAILED: RuntimeError: skip rate 40%", report)
        self.assertIn("stopped, remap failed", report)

    def test_a_step_that_calls_sys_exit_with_a_message_is_a_failure(self):
        def quit_with_message():
            sys.exit("ERROR: template not found")

        steps = FakeSteps({"copy": quit_with_message})

        with self.assertRaises(SystemExit):
            self.run_main(steps)

        self.assertIn("template not found", self.report())

    def test_sys_exit_zero_is_not_a_failure(self):
        steps = FakeSteps({"backup": lambda: sys.exit(0)})

        self.run_main(steps)

        self.assertIn("topology", steps.keys())

    def test_the_build_failure_note_warns_against_rerunning_the_phase(self):
        def fail():
            raise RuntimeError("ERROR 030168")

        steps = FakeSteps({"build": fail})

        with self.assertRaises(SystemExit):
            self.run_main(steps)

        self.assertIn("do NOT rerun this phase", "\n".join(self.printed))
        self.assertIn("03_create_network_dataset.py", "\n".join(self.printed))

    def test_start_at_skips_earlier_phases_and_their_gates(self):
        steps = FakeSteps()

        self.run_main(steps, answers=("REVIEWED", "GRANT"), START_AT="copy")

        self.assertEqual(steps.keys()[0], "copy")
        self.assertNotIn("delete", steps.keys())
        self.assertEqual(len(self.asked), 2)

    def test_starting_at_the_build_still_asks_the_build_gate(self):
        steps = FakeSteps()

        self.run_main(steps, answers=("no",), START_AT="build")

        self.assertEqual(steps.calls, [])
        self.assertEqual(len(self.asked), 1)

    def test_stop_after_ends_the_run(self):
        steps = FakeSteps()

        self.run_main(steps, answers=("DELETE QA NETWORK",), STOP_AFTER="remap")

        self.assertEqual(steps.keys()[-1], "remap")

    def test_a_bad_phase_key_is_refused_before_anything_runs(self):
        steps = FakeSteps()

        with self.assertRaises(RuntimeError) as error:
            self.run_main(steps, START_AT="deleet")

        self.assertIn("START_AT", str(error.exception))
        self.assertEqual(steps.calls, [])

    def test_a_stale_deployment_stops_before_any_step(self):
        steps = FakeSteps()

        def stale():
            raise RuntimeError("The deployed files do not match the repo.")

        with mock.patch.object(self.module, "deploy_check", types.SimpleNamespace(require_current=stale)):
            with self.assertRaises(RuntimeError):
                self.run_main(steps)

        self.assertEqual(steps.calls, [])

    def test_a_mismatched_network_stops_before_any_step(self):
        steps = FakeSteps()

        def mismatch():
            raise RuntimeError("NETWORK does not match HRM_NETWORK")

        with mock.patch.object(self.module, "check_network", mismatch):
            with self.assertRaises(RuntimeError):
                self.run_main(steps)

        self.assertEqual(steps.calls, [])

    def test_the_report_keeps_the_key_numbers_from_each_phase(self):
        def copy():
            print("2026-10-09 10:04:41 | INFO | Edge exclusions applied (profile GENERAL): 18,595 of 18,670 kept, 75 excluded.")
            print("  edge        18,595  (Prod view 18,670, excluded 75; last QA baseline 18,583)")
            print("an unrelated line")

        def remap():
            print("2026-10-09 10:11:41 | INFO |   Written           : 1189")
            print("2026-10-09 10:11:41 | INFO |   Skipped           : 49 (4.0%)")

        steps = FakeSteps({"copy": copy, "remap": remap})

        self.run_main(steps)

        report = self.report()
        self.assertIn("Edge exclusions applied (profile GENERAL): 18,595 of 18,670 kept", report)
        self.assertIn("Written           : 1189", report)
        self.assertIn("Skipped           : 49 (4.0%)", report)
        self.assertNotIn("an unrelated line", report)
        self.assertNotIn("2026-10-09 10:04:41", report)

    def test_the_transcript_holds_everything_printed(self):
        steps = FakeSteps({"copy": lambda: print("a line from step 03")})

        self.run_main(steps)

        transcripts = list(self.output.glob("refresh_run_*.log"))
        self.assertEqual(len(transcripts), 1)
        self.assertIn("a line from step 03", transcripts[0].read_text(encoding="utf-8"))

    def test_the_streams_are_restored_after_a_run(self):
        before = (sys.stdout, sys.stderr)

        self.run_main(FakeSteps())

        self.assertEqual((sys.stdout, sys.stderr), before)

    def test_extract_facts_removes_timestamps_and_repeats(self):
        text = "2026-10-09 10:11:41 | INFO | Written : 5\nWritten : 5\nother\n"

        self.assertEqual(self.module.extract_facts(text, [r"Written"]), ["Written : 5"])


if __name__ == "__main__":
    unittest.main()
