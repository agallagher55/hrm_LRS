"""
Tests for network_metadata.py. They need no ArcGIS: arcpy is replaced by a stand-in.

Run from network_dataset/scripts:
  > python -m unittest discover -s tests -v
"""

import datetime
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import network_metadata  # noqa: E402

BUILT = datetime.datetime(2026, 10, 9, 16, 35, 26)
COPIED = datetime.datetime(2026, 10, 9, 16, 32, 54)


class FakeMetadata:

    def __init__(self, description="", read_only=False, fail_on_save=False):
        self.description = description
        self.isReadOnly = read_only
        self.saved = 0
        self.fail_on_save = fail_on_save

    def save(self):
        if self.fail_on_save:
            raise RuntimeError("item is locked")

        self.saved += 1


def fake_arcpy(metadata):
    return types.SimpleNamespace(metadata=types.SimpleNamespace(Metadata=lambda path: metadata))


class MergeBlockTests(unittest.TestCase):

    def test_an_empty_description_gets_just_the_block(self):
        text = network_metadata.merge_block("", rebuilt=BUILT)

        self.assertIn("Last rebuilt: 2026-10-09 16:35", text)
        self.assertNotIn("Last refreshed", text)
        self.assertTrue(text.startswith(network_metadata.START))
        self.assertTrue(text.endswith(network_metadata.END))

    def test_none_as_the_description_is_treated_as_empty(self):
        text = network_metadata.merge_block(None, rebuilt=BUILT)

        self.assertIn("Last rebuilt", text)

    def test_existing_text_is_kept_and_the_block_goes_after_it(self):
        text = network_metadata.merge_block("Street network for routing.", rebuilt=BUILT)

        self.assertTrue(text.startswith("Street network for routing.\n\n"))
        self.assertIn("Last rebuilt: 2026-10-09 16:35", text)

    def test_a_second_write_replaces_the_block_instead_of_adding_one(self):
        first = network_metadata.merge_block("Intro.", rebuilt=BUILT, refreshed=COPIED)
        later = datetime.datetime(2026, 10, 12, 9, 0)
        second = network_metadata.merge_block(first, rebuilt=later, refreshed=later)

        self.assertEqual(second.count(network_metadata.START), 1)
        self.assertIn("Last rebuilt: 2026-10-12 09:00", second)
        self.assertNotIn("2026-10-09", second)
        self.assertTrue(second.startswith("Intro."))

    def test_a_rebuild_alone_keeps_the_refresh_time(self):
        first = network_metadata.merge_block("", rebuilt=BUILT, refreshed=COPIED)
        later = datetime.datetime(2026, 10, 10, 8, 0)
        second = network_metadata.merge_block(first, rebuilt=later)

        self.assertIn("Last rebuilt: 2026-10-10 08:00", second)
        self.assertIn("2026-10-09 16:32", second)

    def test_a_refresh_alone_keeps_the_rebuild_time(self):
        first = network_metadata.merge_block("", rebuilt=BUILT)
        second = network_metadata.merge_block(first, refreshed=COPIED)

        self.assertIn("Last rebuilt: 2026-10-09 16:35", second)
        self.assertIn("Last refreshed from Prod's TRNLRS_TRN_STREET_VW: 2026-10-09 16:32", second)

    def test_text_after_the_block_is_kept(self):
        first = network_metadata.merge_block("Intro.", rebuilt=BUILT) + "\n\nTrailing note."
        second = network_metadata.merge_block(first, rebuilt=COPIED)

        self.assertTrue(second.endswith("Trailing note."))
        self.assertEqual(second.count(network_metadata.START), 1)

    def test_a_string_time_is_used_as_it_is(self):
        text = network_metadata.merge_block("", rebuilt="2026-01-01 00:00")

        self.assertIn("Last rebuilt: 2026-01-01 00:00", text)


class StampTests(unittest.TestCase):

    def stamp(self, metadata, **kwargs):
        with mock.patch.dict(sys.modules, {"arcpy": fake_arcpy(metadata)}):
            return network_metadata.stamp("nd", logger=mock.Mock(), **kwargs)

    def test_it_writes_the_description_and_saves(self):
        metadata = FakeMetadata("Intro.")

        self.assertTrue(self.stamp(metadata, rebuilt=BUILT, refreshed=COPIED))
        self.assertEqual(metadata.saved, 1)
        self.assertIn("Last rebuilt: 2026-10-09 16:35", metadata.description)
        self.assertTrue(metadata.description.startswith("Intro."))

    def test_a_read_only_item_is_reported_not_raised(self):
        metadata = FakeMetadata(read_only=True)

        self.assertFalse(self.stamp(metadata, rebuilt=BUILT))
        self.assertEqual(metadata.saved, 0)

    def test_a_failed_save_is_reported_not_raised(self):
        metadata = FakeMetadata(fail_on_save=True)

        self.assertFalse(self.stamp(metadata, rebuilt=BUILT))

    def test_a_missing_arcpy_is_reported_not_raised(self):
        with mock.patch.dict(sys.modules, {"arcpy": None}):
            self.assertFalse(network_metadata.stamp("nd", logger=mock.Mock(), rebuilt=BUILT))


if __name__ == "__main__":
    unittest.main()
