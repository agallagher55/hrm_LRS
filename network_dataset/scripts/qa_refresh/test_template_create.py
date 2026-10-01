"""Prove the committed network template creates and builds, without touching QA.

Copies the three QA network sources into a scratch file geodatabase, creates a
network dataset there from data/network_template.xml, builds it, then exports a
template back out to confirm the Directions settings survived the round trip.
QA is only read, so it is safe to run while the live network is in use.

To prove the rendered HRFE template before touching QA, set HRM_NETWORK=HRFE first. The
sources are still read from the DISTANCE network (the HRFE ones do not exist yet) and
copied into the scratch geodatabase under the HRFE names, so the run exercises the same
renamed template that the real HRFE build will use.

Run from an ArcGIS Pro Python prompt with the Network Analyst extension:

    python test_template_create.py

Set KEEP_SCRATCH to True to keep the scratch geodatabase for inspection.
"""

import os
import shutil
import sys

import arcpy

import config
import network_definitions


KEEP_SCRATCH = False

SCRATCH_DIR = os.path.join(arcpy.env.scratchFolder, "template_create_test")
GDB_NAME = "template_test.gdb"
NETWORK = config.NETWORK_DEF
FEATURE_DATASET_NAME = NETWORK.feature_dataset.split(".", 1)[-1]
NETWORK_NAME = NETWORK.network_name
TEMPLATE = os.path.join(config.NETWORK_DATASET_DIR, "data", "network_template.xml")
EXPORTED_TEMPLATE = os.path.join(SCRATCH_DIR, "roundtrip_template.xml")

# Always read from the DISTANCE sources, which exist; copy them under this network's names.
DISTANCE = network_definitions.DISTANCE
DISTANCE_FD = os.path.join(config.QA_SDE, DISTANCE.feature_dataset)
SOURCES = {
    NETWORK.edge_name: os.path.join(DISTANCE_FD, "SDEADM." + DISTANCE.edge_name),
    NETWORK.junction_name: os.path.join(DISTANCE_FD, "SDEADM." + DISTANCE.junction_name),
    NETWORK.turn_name: os.path.join(DISTANCE_FD, "SDEADM." + DISTANCE.turn_name),
}

# Text that must appear in the template exported from the newly created network. A miss fails the test.
EXPECTED_IN_EXPORT = [
    "<NetworkDirections",
    "<StreetNameFieldName>STR_NAME</StreetNameFieldName>",
    "<SuffixTypeFieldName>STR_TYPE</SuffixTypeFieldName>",
    "<FullNameFieldName>FULL_NAME</FullNameFieldName>",
]

# The names the rendered template should carry. Reported but not a failure: an exported
# template's <Name>/<CatalogPath> fields are not reliably the live object's names (CLAUDE.md),
# so a miss here is a prompt to look, not proof of a bad rename. The real proof is that the
# network was found and built under NETWORK_NAME below.
NAMES_TO_REPORT = [
    f"<Name>{NETWORK.network_name}</Name>",
    f"<Name>{NETWORK.edge_name}</Name>",
    f"<Name>{NETWORK.junction_name}</Name>",
    f"<Name>{NETWORK.turn_name}</Name>",
]


def fail(message):
    print(f"FAIL: {message}")
    sys.exit(1)


def prepare_scratch():
    if os.path.exists(SCRATCH_DIR):
        shutil.rmtree(SCRATCH_DIR)

    os.makedirs(SCRATCH_DIR)
    gdb = arcpy.management.CreateFileGDB(SCRATCH_DIR, GDB_NAME).getOutput(0)
    spatial_reference = arcpy.Describe(DISTANCE_FD).spatialReference
    feature_dataset = arcpy.management.CreateFeatureDataset(
        gdb, FEATURE_DATASET_NAME, spatial_reference
    ).getOutput(0)

    return feature_dataset


def copy_sources(feature_dataset):
    for name, source in SOURCES.items():
        if not arcpy.Exists(source):
            fail(f"QA source not found: {source}")

        target = os.path.join(feature_dataset, name)
        arcpy.management.CopyFeatures(source, target)
        print(f"Copied {name}: {arcpy.management.GetCount(target)[0]} rows")


def main():
    if not os.path.exists(TEMPLATE):
        fail(f"Template not found: {TEMPLATE}")

    with open(TEMPLATE, encoding="utf-8") as template_file:
        template_text = template_file.read()

    if "Select Case" in template_text:
        fail("Template contains VBScript ('Select Case'): it is the stale copy.")

    print(f"Template under test: {TEMPLATE}")
    print(f"Contains NetworkDirections: {'<NetworkDirections' in template_text}")

    arcpy.CheckOutExtension("Network")
    feature_dataset = prepare_scratch()
    copy_sources(feature_dataset)

    # DISTANCE builds from the committed template as it is; HRFE from a rendered copy.
    template_to_build = str(network_definitions.rendered_template_path(NETWORK, TEMPLATE, SCRATCH_DIR))
    print(f"Network under test: {NETWORK.key}; building from {template_to_build}")

    try:
        arcpy.na.CreateNetworkDatasetFromTemplate(
            network_dataset_template=template_to_build,
            output_feature_dataset=feature_dataset,
        )
    except arcpy.ExecuteError:
        fail(f"CreateNetworkDatasetFromTemplate:\n{arcpy.GetMessages()}")

    network = os.path.join(feature_dataset, NETWORK_NAME)
    print(f"Created: {network}")

    try:
        arcpy.na.BuildNetwork(network)
    except arcpy.ExecuteError:
        fail(f"BuildNetwork:\n{arcpy.GetMessages()}")

    print("Built.")

    # Export needs a network dataset layer, not a raw catalog path.
    arcpy.na.MakeNetworkDatasetLayer(network, "nd_test_lyr")
    arcpy.na.CreateTemplateFromNetworkDataset("nd_test_lyr", EXPORTED_TEMPLATE)

    with open(EXPORTED_TEMPLATE, encoding="utf-8") as exported_file:
        exported_text = exported_file.read()

    missing = [text for text in EXPECTED_IN_EXPORT if text not in exported_text]

    for text in EXPECTED_IN_EXPORT:
        print(f"{'MISSING' if text in missing else 'found  '}: {text}")

    for text in NAMES_TO_REPORT:
        print(f"{'found  ' if text in exported_text else 'not seen'}: {text} (informational)")

    if not KEEP_SCRATCH:
        arcpy.management.Delete("nd_test_lyr")
        shutil.rmtree(SCRATCH_DIR, ignore_errors=True)
    else:
        print(f"Scratch kept at: {SCRATCH_DIR}")

    if missing:
        fail("Template created and built, but Directions did not round-trip.")

    print("PASS: the template creates, builds, and keeps its Directions settings.")


if __name__ == "__main__":
    main()
