"""Helpers for loading and validating the maintained network scripts."""

import importlib.util
import os
import sys
from pathlib import Path

import arcpy

import config


def load_script(path, module_name):
    """Load a numerically named core script without executing its main block."""
    # Do not call Path.resolve() here. On HRM workstations it expands the mapped
    # T: drive back to its file-server UNC path, which makes diagnostics harder
    # to compare with the paths operators see in ArcGIS Pro and PyCharm.
    path = Path(path)
    if not path.exists():
        raise RuntimeError(f"Required script not found: {path}")
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def same_path(left, right):
    return os.path.normcase(os.path.normpath(left)) == os.path.normcase(
        os.path.normpath(right)
    )


def load_and_validate_core_scripts():
    """Load core scripts and refuse to continue if their QA paths diverge."""
    build = load_script(config.SCRIPT_03, "qa_refresh_create_network")
    turns = load_script(config.SCRIPT_05, "qa_refresh_rebuild_turns")
    verifier = load_script(config.VERIFY_SCRIPT, "qa_refresh_verify_turns")

    keys = {
        "config": config.NETWORK_DEF.key,
        "03": build.NETWORK.key,
        "05": turns.NETWORK.key,
        "verifier": verifier.NETWORK.key,
    }
    if len(set(keys.values())) != 1:
        raise RuntimeError(f"The scripts disagree about which network this run is on: {keys}")
    print(f"Network: {config.NETWORK_DEF.key} ({config.NETWORK_DEF.description})")

    expected = config.QA_NETWORK_FD
    configured_paths = {
        "03 FEATURE_DATASET": build.FEATURE_DATASET,
        "05 network feature dataset": os.path.join(turns.SDE, turns.NETWORK_FD),
        "verifier network feature dataset": os.path.join(
            verifier.SDE, verifier.NETWORK_FD
        ),
    }
    mismatches = {
        label: path
        for label, path in configured_paths.items()
        if not same_path(path, expected)
    }
    if mismatches:
        details = "\n".join(f"  {label}: {path}" for label, path in mismatches.items())
        raise RuntimeError(
            f"Core script environment mismatch; expected {expected}:\n{details}"
        )
    if turns.AUTO_SWAP_AND_REBUILD:
        raise RuntimeError(
            "05_rebuild_traffic_turns.py has AUTO_SWAP_AND_REBUILD=True; set it "
            "to False before using this reviewed-staging workflow."
        )
    if not same_path(verifier.EDGE_FC, config.EDGE):
        raise RuntimeError(
            f"Verifier edge path mismatch: {verifier.EDGE_FC} != {config.EDGE}"
        )
    return build, turns, verifier


def require_network(expected_key, setting_name):
    """
    Stop a destructive step unless this run is on the network the operator named in the script.

    The environment variable decides which network a run works on, and an unset or mistyped one
    quietly means DISTANCE, the live network. Naming the network in the script as well means a
    delete or rebuild needs two deliberate settings that agree.
    """
    actual = config.NETWORK_DEF.key

    if actual != expected_key:
        raise RuntimeError(
            f"This step is set for the {expected_key} network ({setting_name} in the script), but "
            f"this run is on {actual}. Check HRM_NETWORK, and {setting_name}. Nothing was changed."
        )

    print(f"Confirmed network for this step: {actual} ({config.NETWORK_DEF.description})")


def require_exists(path, label):
    if not arcpy.Exists(path):
        raise RuntimeError(f"{label} not found: {path}")
