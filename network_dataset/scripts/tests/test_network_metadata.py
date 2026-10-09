"""
Tests for network_metadata.py. They need no ArcGIS: arcpy is replaced by a stand-in.

Run from network_dataset/scripts:
  > python -m unittest discover -s tests -v
"""

import datetime
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import network_metadata  # noqa: E402

BUILT = datetime.datetime(2026, 10, 9, 16, 35, 26)
COPIED = datetime.datetime(2026, 10, 9, 16, 32, 54)


class FakeGispy:
    """Stands in for gispy.metadata.metadata: one description per dataset, as the real functions read it."""

    def __init__(self, description="", read_only=False, fail_on_update=False):
        self.description = description
        self.read_only = read_only
        self.fail_on_update = fail_on_update
        self.updates = []

    def get_sde_metadata(self, db, feature):
        return {"DESCRIPTION": self.description}

    def update_metadata(self, db, feature, options):
        self.updates.append((db, feature, dict(options)))

        if self.fail_on_update:
            raise RuntimeError("item is locked")

        if not self.read_only and options.get("description"):
            self.description = options["description"]


PATH = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde\SDEADM.TRNLRS_network\TRNLRS_street_network"


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

    def stamp(self, fake, path=PATH, **kwargs):
        with mock.patch.object(network_metadata, "load_gispy_metadata", lambda: fake):
            return network_metadata.stamp(path, logger=mock.Mock(), **kwargs)

    def test_it_writes_the_description_through_gispy(self):
        fake = FakeGispy("Intro.")

        self.assertTrue(self.stamp(fake, rebuilt=BUILT, refreshed=COPIED))
        db, feature, options = fake.updates[0]
        self.assertEqual(db, r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde")
        self.assertEqual(feature, r"SDEADM.TRNLRS_network\TRNLRS_street_network")
        self.assertIn("Last rebuilt: 2026-10-09 16:35", options["description"])
        self.assertTrue(options["description"].startswith("Intro."))

    def test_a_rebuild_moves_the_revised_date_and_a_refresh_alone_does_not(self):
        rebuilt = FakeGispy()
        refreshed = FakeGispy()

        self.stamp(rebuilt, rebuilt=BUILT)
        self.stamp(refreshed, refreshed=COPIED)

        self.assertEqual(rebuilt.updates[0][2]["revised_date"], "2026-10-09T00:00:00")
        self.assertNotIn("revised_date", refreshed.updates[0][2])

    def test_a_read_only_item_is_reported_because_the_description_is_read_back(self):
        fake = FakeGispy(read_only=True)

        self.assertFalse(self.stamp(fake, rebuilt=BUILT))

    def test_a_failed_update_is_reported_not_raised(self):
        fake = FakeGispy(fail_on_update=True)

        self.assertFalse(self.stamp(fake, rebuilt=BUILT))

    def test_a_path_outside_an_sde_file_is_reported_not_raised(self):
        self.assertFalse(self.stamp(FakeGispy(), path=r"C:\data\test.gdb\net", rebuilt=BUILT))

    def test_a_missing_gispy_is_reported_not_raised(self):
        def missing():
            raise ImportError("No module named 'gispy'")

        with mock.patch.object(network_metadata, "load_gispy_metadata", missing):
            self.assertFalse(network_metadata.stamp(PATH, logger=mock.Mock(), rebuilt=BUILT))


class SplitPathTests(unittest.TestCase):

    def test_it_splits_at_the_connection_file(self):
        db, feature = network_metadata.split_sde_path(PATH)

        self.assertTrue(db.endswith("qa_RW_sdeadm.sde"))
        self.assertEqual(feature, r"SDEADM.TRNLRS_network\TRNLRS_street_network")

    def test_forward_slashes_and_capitals_work(self):
        db, feature = network_metadata.split_sde_path("E:/x/QA.SDE/FD/Net")

        self.assertEqual((db, feature), ("E:/x/QA.SDE", "FD/Net"))


if __name__ == "__main__":
    unittest.main()
