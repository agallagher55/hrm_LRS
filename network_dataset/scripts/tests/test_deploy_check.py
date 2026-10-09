"""
Tests for deploy_check.py and make_deploy_manifest.py. They need no ArcGIS.

Run from network_dataset/scripts:
  > python -m unittest discover -s tests -v
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import deploy_check  # noqa: E402


def make_tree(root, files):
    for name, content in files.items():
        path = Path(root) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


FILES = {
    "scripts/a.py": b"print('a')\n",
    "scripts/qa_refresh/_shared.py": b"shared\n",
    "scripts/qa_refresh/03_copy_sources.py": b"copy\n",
    "data/network_template.xml": b"<x/>\n",
}


class HashTests(unittest.TestCase):

    def test_line_endings_do_not_change_the_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            make_tree(folder, {"unix.py": b"a\nb\n", "windows.py": b"a\r\nb\r\n"})

            self.assertEqual(
                deploy_check.file_hash(Path(folder) / "unix.py"),
                deploy_check.file_hash(Path(folder) / "windows.py"),
            )

    def test_different_content_gives_a_different_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            make_tree(folder, {"one.py": b"a\n", "two.py": b"b\n"})

            self.assertNotEqual(
                deploy_check.file_hash(Path(folder) / "one.py"),
                deploy_check.file_hash(Path(folder) / "two.py"),
            )


class ManifestTests(unittest.TestCase):

    def test_the_manifest_lists_tracked_files_only(self):
        files = dict(FILES)
        files["scripts/tests/test_x.py"] = b"t\n"
        files["scripts/archive/old.py"] = b"o\n"
        files["scripts/qa_refresh/test_template_create.py"] = b"t\n"
        files["scripts/qa_refresh/output/readme.txt"] = b"o\n"

        with tempfile.TemporaryDirectory() as folder:
            make_tree(folder, files)

            manifest = deploy_check.build_manifest(folder)

        self.assertEqual(sorted(manifest["files"]), sorted(FILES))

    def test_the_committed_manifest_matches_the_repo(self):
        committed = deploy_check.load_manifest()
        current = deploy_check.build_manifest()

        self.assertEqual(
            committed["files"], current["files"],
            "data/deploy_manifest.json is out of date. Run make_deploy_manifest.py and commit it.",
        )


class CompareTests(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        make_tree(self.folder.name, FILES)
        self.manifest = deploy_check.build_manifest(self.folder.name)

    def test_a_matching_tree_has_no_differences(self):
        result = deploy_check.compare(self.folder.name, self.manifest)

        self.assertEqual(result, {"stale": [], "missing": [], "extra": []})

    def test_a_changed_file_is_stale(self):
        make_tree(self.folder.name, {"scripts/qa_refresh/_shared.py": b"old\n"})

        result = deploy_check.compare(self.folder.name, self.manifest)

        self.assertEqual(result["stale"], ["scripts/qa_refresh/_shared.py"])

    def test_a_deleted_file_is_missing(self):
        (Path(self.folder.name) / "data/network_template.xml").unlink()

        result = deploy_check.compare(self.folder.name, self.manifest)

        self.assertEqual(result["missing"], ["data/network_template.xml"])

    def test_a_stray_step_script_is_extra(self):
        make_tree(self.folder.name, {"scripts/qa_refresh/03_initial_build.py": b"old\n"})

        result = deploy_check.compare(self.folder.name, self.manifest)

        self.assertEqual(result["extra"], ["scripts/qa_refresh/03_initial_build.py"])

    def test_a_renamed_template_test_is_not_extra(self):
        make_tree(self.folder.name, {"scripts/qa_refresh/_test_template_create.py": b"x\n"})

        result = deploy_check.compare(self.folder.name, self.manifest)

        self.assertEqual(result["extra"], [])

    def test_extra_files_outside_qa_refresh_are_ignored(self):
        make_tree(self.folder.name, {"scripts/05_Stub.py": b"x\n", "scripts/lrs_updates.py": b"x\n"})

        result = deploy_check.compare(self.folder.name, self.manifest)

        self.assertEqual(result["extra"], [])

    def test_windows_line_endings_still_match(self):
        make_tree(self.folder.name, {"scripts/a.py": b"print('a')\r\n"})

        result = deploy_check.compare(self.folder.name, self.manifest)

        self.assertEqual(result["stale"], [])


class RequireCurrentTests(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        make_tree(self.folder.name, FILES)
        manifest = deploy_check.build_manifest(self.folder.name)
        self.manifest_path = Path(self.folder.name) / "data" / "deploy_manifest.json"
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_a_current_tree_passes(self):
        deploy_check.require_current(self.folder.name, self.manifest_path)

    def test_a_stale_file_stops_the_run(self):
        make_tree(self.folder.name, {"scripts/a.py": b"changed\n"})

        with self.assertRaises(RuntimeError) as error:
            deploy_check.require_current(self.folder.name, self.manifest_path)

        self.assertIn("do not match the repo", str(error.exception))

    def test_an_extra_file_only_warns(self):
        make_tree(self.folder.name, {"scripts/qa_refresh/03_initial_build.py": b"old\n"})

        result = deploy_check.require_current(self.folder.name, self.manifest_path)

        self.assertEqual(result["extra"], ["scripts/qa_refresh/03_initial_build.py"])

    def test_a_missing_manifest_says_what_to_copy(self):
        with self.assertRaises(RuntimeError) as error:
            deploy_check.require_current(self.folder.name, Path(self.folder.name) / "nope.json")

        self.assertIn("deploy_manifest.json", str(error.exception))


if __name__ == "__main__":
    unittest.main()
