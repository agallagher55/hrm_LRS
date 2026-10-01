"""
Tests for network_definitions.py and for how the scripts use it. They need no ArcGIS:
the scripts are imported against a stand-in for arcpy.

Run from network_dataset/scripts:
  > python -m unittest discover -s tests -v
"""

import importlib.util
import logging
import os
import re
import sys
import tempfile
import types
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "qa_refresh"))

import network_definitions as nd  # noqa: E402

TEMPLATE_PATH = SCRIPTS.parent / "data" / "network_template.xml"
QA_SDE = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"


class _Any:
    """Stands in for any arcpy object: any attribute or call gives another one."""

    def __getattr__(self, name):
        return _Any()

    def __call__(self, *args, **kwargs):
        return _Any()


def fake_arcpy():
    module = types.ModuleType("arcpy")
    module.__getattr__ = lambda name: _Any()

    return module


def load_script(filename, env):
    """Import a script fresh, with HRM_NETWORK set to env (None for unset)."""
    environ = {k: v for k, v in os.environ.items() if k != nd.NETWORK_ENV_VAR}

    if env:
        environ[nd.NETWORK_ENV_VAR] = env

    quiet = logging.getLogger("test_network_definitions_quiet")
    quiet.addHandler(logging.NullHandler())
    quiet.propagate = False

    with mock.patch.dict(os.environ, environ, clear=True), \
            mock.patch.dict(sys.modules, {"arcpy": fake_arcpy()}), \
            mock.patch("log_utils.setup_logger", return_value=quiet):
        path = SCRIPTS / filename
        spec = importlib.util.spec_from_file_location("t_" + path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

    return module


def load_config(env):
    environ = {k: v for k, v in os.environ.items() if k != nd.NETWORK_ENV_VAR}

    if env:
        environ[nd.NETWORK_ENV_VAR] = env

    with mock.patch.dict(os.environ, environ, clear=True):
        spec = importlib.util.spec_from_file_location(
            "t_config", SCRIPTS / "qa_refresh" / "config.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

    return module


class DefinitionTests(unittest.TestCase):

    def test_distance_keeps_the_names_it_always_had(self):
        d = nd.DISTANCE

        self.assertEqual(d.feature_dataset, "SDEADM.TRNLRS_network")
        self.assertEqual(d.network_name, "TRNLRS_street_network")
        self.assertEqual(d.edge_name, "TRNLRS_TRN_STREET")
        self.assertEqual(d.junction_name, "TRNLRS_street_junction")
        self.assertEqual(d.turn_name, "TRNLRS_traffic_turn")
        self.assertEqual(d.staging_turn_name, "TRNLRS_traffic_turn_staging")
        self.assertEqual(d.exclusion_profile, "GENERAL")

    def test_hrfe_names(self):
        h = nd.HRFE

        self.assertEqual(h.feature_dataset, "SDEADM.TRNLRS_network_HRFE")
        self.assertEqual(h.network_name, "TRNLRS_street_network_HRFE")
        self.assertEqual(h.edge_name, "TRNLRS_TRN_STREET_HRFE")
        self.assertEqual(h.junction_name, "TRNLRS_street_junction_HRFE")
        self.assertEqual(h.turn_name, "TRNLRS_traffic_turn_HRFE")
        self.assertEqual(h.staging_turn_name, "TRNLRS_traffic_turn_staging_HRFE")
        self.assertEqual(h.exclusion_profile, "HRFE")

    def test_no_name_is_shared_between_networks(self):
        """SDE needs feature class names to be unique across the whole geodatabase."""
        fields = (
            "feature_dataset", "network_name", "edge_name", "junction_name", "turn_name",
            "staging_turn_name",
        )

        for field in fields:

            self.assertNotEqual(getattr(nd.DISTANCE, field), getattr(nd.HRFE, field), field)

        distance_names = {getattr(nd.DISTANCE, f) for f in fields}
        hrfe_names = {getattr(nd.HRFE, f) for f in fields}

        self.assertEqual(distance_names & hrfe_names, set())

    def test_exclusion_profiles_exist(self):
        import network_exclusions

        for definition in nd.DEFINITIONS.values():

            self.assertIn(definition.exclusion_profile, network_exclusions.PROFILES)

    def test_get_definition_defaults_to_distance(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIs(nd.get_definition(), nd.DISTANCE)

    def test_get_definition_reads_the_environment_variable_case_insensitively(self):
        with mock.patch.dict(os.environ, {nd.NETWORK_ENV_VAR: " hrfe "}, clear=True):
            self.assertIs(nd.get_definition(), nd.HRFE)

    def test_an_explicit_key_beats_the_environment(self):
        with mock.patch.dict(os.environ, {nd.NETWORK_ENV_VAR: "HRFE"}, clear=True):
            self.assertIs(nd.get_definition("DISTANCE"), nd.DISTANCE)

    def test_unknown_network_fails_loudly(self):
        with mock.patch.dict(os.environ, {nd.NETWORK_ENV_VAR: "HRFF"}, clear=True):
            with self.assertRaises(ValueError) as error:
                nd.get_definition()

        self.assertIn("HRFF", str(error.exception))
        self.assertIn("DISTANCE", str(error.exception))


class MisspelledVariableTests(unittest.TestCase):
    """A near miss of HRM_NETWORK must not quietly mean DISTANCE, the live network."""

    def test_a_name_with_spaces_is_refused(self):
        """cmd's 'set HRM_NETWORK = HRFE' makes a variable called 'HRM_NETWORK ' with a space."""
        with mock.patch.dict(os.environ, {"HRM_NETWORK ": " HRFE"}, clear=True):
            with self.assertRaises(ValueError) as error:
                nd.get_definition()

        self.assertIn("exactly HRM_NETWORK", str(error.exception))

    def test_a_lowercase_name_is_refused(self):
        with mock.patch.dict(os.environ, {"hrm_network": "HRFE"}, clear=True):
            with self.assertRaises(ValueError):
                nd.get_definition()

    def test_the_right_name_still_works(self):
        with mock.patch.dict(os.environ, {"HRM_NETWORK": "HRFE"}, clear=True):
            self.assertIs(nd.get_definition(), nd.HRFE)

    def test_unrelated_variables_are_ignored(self):
        with mock.patch.dict(os.environ, {"HRM_NETWORK_OTHER": "x", "PATH": "/bin"}, clear=True):
            self.assertIs(nd.get_definition(), nd.DISTANCE)

    def test_an_explicit_key_does_not_trip_over_a_stray_variable(self):
        with mock.patch.dict(os.environ, {"HRM_NETWORK ": "HRFE"}, clear=True):
            self.assertIs(nd.get_definition("DISTANCE"), nd.DISTANCE)


class DestructiveStepGuardTests(unittest.TestCase):
    """Steps 02 and 06 must name the network they act on, and it must match the run."""

    @classmethod
    def setUpClass(cls):
        with mock.patch.dict(sys.modules, {"arcpy": fake_arcpy()}):
            spec = importlib.util.spec_from_file_location(
                "t_shared", SCRIPTS / "qa_refresh" / "_shared.py"
            )
            cls.shared = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.shared)

    def test_a_matching_network_passes(self):
        with mock.patch.object(self.shared.config, "NETWORK_DEF", nd.HRFE):
            self.shared.require_network("HRFE", "NETWORK_TO_DELETE")

    def test_a_mismatch_is_refused_in_both_directions(self):
        for actual, expected in ((nd.DISTANCE, "HRFE"), (nd.HRFE, "DISTANCE")):
            with mock.patch.object(self.shared.config, "NETWORK_DEF", actual):
                with self.assertRaises(RuntimeError) as error:
                    self.shared.require_network(expected, "NETWORK_TO_DELETE")

            self.assertIn("NETWORK_TO_DELETE", str(error.exception))
            self.assertIn("Nothing was changed", str(error.exception))

    def test_the_destructive_scripts_default_to_distance_and_call_the_guard(self):
        for name, constant in (("02_delete_network_sources.py", "NETWORK_TO_DELETE"),
                               ("06_swap_and_final_build.py", "NETWORK_TO_BUILD")):
            source = (SCRIPTS / "qa_refresh" / name).read_text(encoding="utf-8")

            self.assertIn('{} = "DISTANCE"'.format(constant), source, name)
            self.assertIn('require_network({}, "{}")'.format(constant, constant), source, name)

    def test_step_02_only_trusts_this_networks_baseline(self):
        source = (SCRIPTS / "qa_refresh" / "02_delete_network_sources.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("same_path(report.get(\"network\", \"\"), config.NETWORK)", source)


class TemplateTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.base = TEMPLATE_PATH.read_text(encoding="utf-8")

    def test_distance_template_is_unchanged(self):
        self.assertEqual(nd.render_template(self.base, nd.DISTANCE), self.base)

    def test_hrfe_template_is_well_formed_xml(self):
        ElementTree.fromstring(nd.render_template(self.base, nd.HRFE).encode("utf-8"))

    def test_hrfe_template_has_the_new_names(self):
        text = nd.render_template(self.base, nd.HRFE)

        for name in (
            "<Name>TRNLRS_street_network_HRFE</Name>",
            "<Name>TRNLRS_street_network_HRFE_Junctions</Name>",
            "<Name>TRNLRS_TRN_STREET_HRFE</Name>",
            "<Name>TRNLRS_street_junction_HRFE</Name>",
            "<Name>TRNLRS_traffic_turn_HRFE</Name>",
            "/FD=TRNLRS_network_HRFE/ND=TRNLRS_street_network_HRFE",
        ):
            self.assertIn(name, text)

    def test_hrfe_template_keeps_no_distance_name(self):
        text = nd.render_template(self.base, nd.HRFE)
        left_over = re.findall(
            r"TRNLRS_(?:TRN_STREET|street_junction|traffic_turn|street_network)(?!_HRFE)\b", text
        )

        self.assertEqual(left_over, [])
        self.assertNotIn("/FD=TRNLRS_network/", text)

    def test_only_the_names_change(self):
        """Undo the renames and the template must come back exactly as committed."""
        text = nd.render_template(self.base, nd.HRFE)
        text = text.replace("/FD=TRNLRS_network_HRFE/", "/FD=TRNLRS_network/")
        text = re.sub(
            r"(TRNLRS_(?:TRN_STREET|street_junction|traffic_turn|street_network))_HRFE",
            r"\1", text,
        )

        self.assertEqual(text, self.base)

    def test_a_template_missing_a_name_is_refused(self):
        broken = self.base.replace("TRNLRS_traffic_turn", "SOMETHING_ELSE")

        with self.assertRaises(ValueError) as error:
            nd.render_template(broken, nd.HRFE)

        self.assertIn("TRNLRS_traffic_turn", str(error.exception))

    def test_rendered_path_for_distance_is_the_committed_file(self):
        with tempfile.TemporaryDirectory() as out:
            path = nd.rendered_template_path(nd.DISTANCE, TEMPLATE_PATH, out)

            self.assertEqual(path, TEMPLATE_PATH)
            self.assertEqual(list(Path(out).iterdir()), [])

    def test_rendered_path_for_hrfe_writes_a_copy(self):
        with tempfile.TemporaryDirectory() as out:
            path = nd.rendered_template_path(nd.HRFE, TEMPLATE_PATH, Path(out) / "generated")

            self.assertEqual(path.name, "network_template_HRFE.xml")
            self.assertIn("TRNLRS_street_network_HRFE", path.read_text(encoding="utf-8"))

        self.assertEqual(TEMPLATE_PATH.read_text(encoding="utf-8"), self.base)


class ScriptWiringTests(unittest.TestCase):
    """DISTANCE must resolve to the same paths as before, and HRFE to the new ones."""

    @classmethod
    def setUpClass(cls):
        cls.distance = {
            "03": load_script("03_create_network_dataset.py", None),
            "05": load_script("05_rebuild_traffic_turns.py", None),
            "verify": load_script("verify_turn_rebuild.py", None),
            "config": load_config(None),
        }
        cls.hrfe = {
            "03": load_script("03_create_network_dataset.py", "HRFE"),
            "05": load_script("05_rebuild_traffic_turns.py", "HRFE"),
            "verify": load_script("verify_turn_rebuild.py", "HRFE"),
            "config": load_config("HRFE"),
        }

    def test_distance_script_paths_are_the_ones_from_before(self):
        d = self.distance
        fd = QA_SDE + r"\SDEADM.TRNLRS_network"

        self.assertEqual(d["03"].NEW_ND_NAME, "TRNLRS_street_network")
        self.assertEqual(d["03"].EDGE_SOURCE_NAME, "TRNLRS_TRN_STREET")
        self.assertTrue(d["03"].FEATURE_DATASET.endswith("SDEADM.TRNLRS_network"))
        self.assertEqual(d["05"].NETWORK_FD, "SDEADM.TRNLRS_network")
        self.assertEqual(d["05"].NEW_EDGE_FC, fd + r"\SDEADM.TRNLRS_TRN_STREET")
        self.assertEqual(d["05"].NEW_TURN_FC, fd + r"\SDEADM.TRNLRS_traffic_turn_staging")
        self.assertEqual(d["05"].OLD_TURN_FC_FINAL, fd + r"\SDEADM.TRNLRS_traffic_turn")
        self.assertEqual(d["05"].NEW_NETWORK, fd + r"\SDEADM.TRNLRS_street_network")
        self.assertEqual(d["verify"].EDGE_FC, fd + r"\SDEADM.TRNLRS_TRN_STREET")
        self.assertEqual(d["verify"].TURN_FC, fd + r"\SDEADM.TRNLRS_traffic_turn_staging")
        self.assertEqual(d["config"].QA_NETWORK_FD_NAME, "SDEADM.TRNLRS_network")
        self.assertTrue(d["config"].EDGE.endswith("SDEADM.TRNLRS_TRN_STREET"))
        self.assertTrue(d["config"].TURN.endswith("SDEADM.TRNLRS_traffic_turn"))
        self.assertTrue(d["config"].STAGING_TURN.endswith("SDEADM.TRNLRS_traffic_turn_staging"))
        self.assertTrue(d["config"].NETWORK.endswith("SDEADM.TRNLRS_street_network"))

    def test_hrfe_script_paths(self):
        h = self.hrfe
        fd = QA_SDE + r"\SDEADM.TRNLRS_network_HRFE"

        self.assertEqual(h["03"].NEW_ND_NAME, "TRNLRS_street_network_HRFE")
        self.assertEqual(h["03"].EDGE_SOURCE_NAME, "TRNLRS_TRN_STREET_HRFE")
        self.assertEqual(h["05"].NEW_EDGE_FC, fd + r"\SDEADM.TRNLRS_TRN_STREET_HRFE")
        self.assertEqual(h["05"].NEW_TURN_FC, fd + r"\SDEADM.TRNLRS_traffic_turn_staging_HRFE")
        self.assertEqual(h["05"].OLD_TURN_FC_FINAL, fd + r"\SDEADM.TRNLRS_traffic_turn_HRFE")
        self.assertEqual(h["05"].NEW_NETWORK, fd + r"\SDEADM.TRNLRS_street_network_HRFE")
        self.assertEqual(h["verify"].EDGE_FC, fd + r"\SDEADM.TRNLRS_TRN_STREET_HRFE")
        self.assertEqual(h["verify"].TURN_FC, fd + r"\SDEADM.TRNLRS_traffic_turn_staging_HRFE")
        self.assertEqual(h["config"].QA_NETWORK_FD_NAME, "SDEADM.TRNLRS_network_HRFE")

    def test_hrfe_uses_the_same_legacy_turn_sources(self):
        """Same restrictions: both networks remap the same legacy turns and junctions."""
        self.assertEqual(self.hrfe["05"].OLD_TURN_FC, self.distance["05"].OLD_TURN_FC)
        self.assertEqual(self.hrfe["05"].OLD_EDGE_FC, self.distance["05"].OLD_EDGE_FC)
        self.assertEqual(self.hrfe["03"].SOURCE_TURN, self.distance["03"].SOURCE_TURN)
        self.assertEqual(self.hrfe["03"].SOURCE_JUNCTION, self.distance["03"].SOURCE_JUNCTION)
        self.assertEqual(
            self.hrfe["03"].STANDALONE_EDGE_SOURCE, self.distance["03"].STANDALONE_EDGE_SOURCE
        )

    def test_every_script_agrees_on_the_network(self):
        for scripts in (self.distance, self.hrfe):

            keys = {
                scripts["03"].NETWORK.key, scripts["05"].NETWORK.key,
                scripts["verify"].NETWORK.key, scripts["config"].NETWORK_DEF.key,
            }

            self.assertEqual(len(keys), 1)

    def test_the_exclusion_profile_follows_the_network(self):
        self.assertEqual(self.distance["03"].NETWORK.exclusion_profile, "GENERAL")
        self.assertEqual(self.hrfe["03"].NETWORK.exclusion_profile, "HRFE")

    def test_the_prod_sync_ignores_the_environment_variable(self):
        """04 runs inside the Prod LRS_updates.py job; the environment must not redirect it."""
        source = (SCRIPTS / "04_sync_and_rebuild_network.py").read_text(encoding="utf-8")

        self.assertNotIn("get_definition", source)
        self.assertIn("network_definitions.DISTANCE", source)


if __name__ == "__main__":
    unittest.main()
