"""
Check that the files on the T: drive match the repo before a QA refresh.

Stale copies cost time on 2026-09-29 and again on 2026-10-09 (an old template, an old
network_exclusions.py, an old _shared.py and a leftover step script). Comparing a few file sizes
did not catch them. This compares a hash of every file the refresh runs against a manifest
committed with the repo (data/deploy_manifest.json).

Regenerate the manifest with make_deploy_manifest.py after any change to a tracked file, and copy
it to the T: drive with the files. A test fails when the committed manifest is out of date.

Line endings and the final newline are normalised before hashing, so a copy with Windows line endings
still matches, and so does one that an editor (PyCharm on save) gave a different final newline.
The root is taken from this file's own location, without resolve(), so a mapped T: drive stays T:.
Only the standard library is used, so it still runs when other deployed files are stale.
"""

import datetime
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).parent.parent
MANIFEST_PATH = ROOT / "data" / "deploy_manifest.json"

# What the refresh runs or reads, relative to ROOT.
TRACKED_GLOBS = [
    "scripts/*.py",
    "scripts/qa_refresh/*.py",
    "data/network_template.xml",
]

# Developer tools that are not part of a refresh and may be renamed on T: (PyCharm offers to run
# a file called test_*.py as a pytest test, which fails on a script).
NOT_TRACKED = {"scripts/qa_refresh/test_template_create.py"}

# A file in one of these places that the manifest does not list is reported, since a stray step
# script can be run by mistake.
EXTRA_GLOBS = ["scripts/qa_refresh/*.py"]
IGNORED_EXTRA_ENDINGS = ("test_template_create.py",)


def file_hash(path):
    """SHA-256 of the file with line endings normalised to LF and no final newline."""
    data = Path(path).read_bytes().replace(b"\r\n", b"\n").rstrip(b"\n")

    return hashlib.sha256(data).hexdigest()


def tracked_files(root=ROOT):
    """Relative posix paths of every tracked file that exists under root."""
    found = set()

    for pattern in TRACKED_GLOBS:
        for path in Path(root).glob(pattern):
            if path.is_file():
                found.add(path.relative_to(root).as_posix())

    return sorted(found - NOT_TRACKED)


def build_manifest(root=ROOT):
    return {
        "generated": datetime.date.today().isoformat(),
        "files": {name: file_hash(Path(root) / name) for name in tracked_files(root)},
    }


def compare(root, manifest):
    """Return the files that differ from the manifest: stale, missing and extra."""
    root = Path(root)
    expected = manifest["files"]
    stale = []
    missing = []

    for name, wanted in sorted(expected.items()):
        path = root / name

        if not path.is_file():
            missing.append(name)
        elif file_hash(path) != wanted:
            stale.append(name)

    extra = set()

    for pattern in EXTRA_GLOBS:
        for path in root.glob(pattern):
            name = path.relative_to(root).as_posix()

            if name not in expected and not name.endswith(IGNORED_EXTRA_ENDINGS):
                extra.add(name)

    return {"stale": stale, "missing": missing, "extra": sorted(extra)}


def load_manifest(path=MANIFEST_PATH):
    path = Path(path)

    if not path.is_file():
        raise RuntimeError(
            f"{path} not found, so the deployed files cannot be checked. Copy "
            "network_dataset/data/deploy_manifest.json from the repo to that path."
        )

    return json.loads(path.read_text(encoding="utf-8"))


def check(root=ROOT, manifest_path=MANIFEST_PATH):
    """Print how the deployed files compare with the manifest and return the comparison."""
    manifest = load_manifest(manifest_path)
    result = compare(root, manifest)
    count = len(manifest["files"])

    print(f"Deployed files checked against deploy_manifest.json (generated {manifest.get('generated', '?')}, {count} files)")

    for label, key in (("STALE (differs from the repo)", "stale"), ("MISSING", "missing"), ("EXTRA (not in the repo)", "extra")):
        for name in result[key]:
            print(f"  {label}: {name}")

    if not (result["stale"] or result["missing"]):
        print("  All tracked files match the repo.")

    return result


def require_current(root=ROOT, manifest_path=MANIFEST_PATH):
    """Stop the run when a tracked file is stale or missing. Extra files only warn."""
    result = check(root, manifest_path)

    if result["stale"] or result["missing"]:
        raise RuntimeError(
            "The deployed files do not match the repo. Copy the files listed above from the "
            "repo, including data/deploy_manifest.json, and run again. Nothing has been changed."
        )

    return result
