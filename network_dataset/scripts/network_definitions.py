"""
The networks this project builds, and every name that differs between them.

Two networks are built from the same LRS street data:

  DISTANCE  TRNLRS_street_network in SDEADM.TRNLRS_network. Distance only.
  HRFE      TRNLRS_street_network_HRFE in SDEADM.TRNLRS_network_HRFE. The fire and
            emergency network: its own exclusions (see network_exclusions.py) and,
            later, extra roads that Robbie Evans maintains.

Each network has its own feature dataset, and SDE requires feature class names to
be unique across the whole geodatabase, so every source class carries the _HRFE
suffix in the HRFE network. The network dataset's own name is read from inside the
template, so the template is rendered per network (render_template) rather than kept
as two copies that could drift apart.

Which network a script run works on
-----------------------------------
The scripts build the paths they use when they are imported, so the network is chosen
with an environment variable set before the run:

  > set HRM_NETWORK=HRFE        (Windows command prompt)
  > $env:HRM_NETWORK = "HRFE"   (PowerShell)

With nothing set, every script works on DISTANCE, exactly as before this module
existed. The chosen network is logged at the start of a run.

Turn restrictions are the same for both networks: each network's turn class is
remapped from the same legacy TRN_traffic_turn onto its own edge copy.
"""

import os
import re
from collections import namedtuple
from pathlib import Path


NETWORK_ENV_VAR = "HRM_NETWORK"
DEFAULT_NETWORK = "DISTANCE"

# The names in the committed template, which is written for DISTANCE.
BASE_FEATURE_DATASET = "TRNLRS_network"
BASE_NAMES = {
    "network": "TRNLRS_street_network",
    "edge": "TRNLRS_TRN_STREET",
    "junction": "TRNLRS_street_junction",
    "turn": "TRNLRS_traffic_turn",
}

NetworkDefinition = namedtuple(
    "NetworkDefinition",
    [
        "key",
        "description",
        "feature_dataset",
        "network_name",
        "edge_name",
        "junction_name",
        "turn_name",
        "staging_turn_name",
        "exclusion_profile",
    ],
)

DISTANCE = NetworkDefinition(
    key="DISTANCE",
    description="Distance network",
    feature_dataset="SDEADM.TRNLRS_network",
    network_name="TRNLRS_street_network",
    edge_name="TRNLRS_TRN_STREET",
    junction_name="TRNLRS_street_junction",
    turn_name="TRNLRS_traffic_turn",
    staging_turn_name="TRNLRS_traffic_turn_staging",
    exclusion_profile="GENERAL",
)

HRFE = NetworkDefinition(
    key="HRFE",
    description="HRFE (fire and emergency) network",
    feature_dataset="SDEADM.TRNLRS_network_HRFE",
    network_name="TRNLRS_street_network_HRFE",
    edge_name="TRNLRS_TRN_STREET_HRFE",
    junction_name="TRNLRS_street_junction_HRFE",
    turn_name="TRNLRS_traffic_turn_HRFE",
    staging_turn_name="TRNLRS_traffic_turn_staging_HRFE",
    exclusion_profile="HRFE",
)

DEFINITIONS = {d.key: d for d in (DISTANCE, HRFE)}


def _misspelled_variables():
    """Names that look like HRM_NETWORK but are not exactly it, such as "HRM_NETWORK " from a
    cmd line written 'set HRM_NETWORK = HRFE' (the spaces become part of the name)."""
    return [
        name for name in os.environ
        if name != NETWORK_ENV_VAR and name.strip().upper() == NETWORK_ENV_VAR
    ]


def get_definition(key=None):
    """
    Return the definition for key, or for the HRM_NETWORK variable, or DISTANCE.

    Raises ValueError if a variable is set under a near miss of the name, because ignoring it
    would quietly run the DISTANCE network, which is the live one the destructive steps delete.
    """
    misspelled = _misspelled_variables()

    if misspelled and not key:
        raise ValueError(
            "Found the environment variable {!r}, which is not {}. The name must be exactly "
            "{} with no spaces around it (write: set {}=HRFE).".format(
                misspelled[0], NETWORK_ENV_VAR, NETWORK_ENV_VAR, NETWORK_ENV_VAR
            )
        )

    key = (key or os.environ.get(NETWORK_ENV_VAR) or DEFAULT_NETWORK).strip().upper()

    try:
        return DEFINITIONS[key]

    except KeyError:
        raise ValueError(
            "Unknown network {!r} in {}. Choose one of: {}".format(
                key, NETWORK_ENV_VAR, ", ".join(sorted(DEFINITIONS))
            )
        )


def _name_pattern(name):
    """Match a whole source name, allowing a suffix such as _Junctions after it."""
    return re.compile(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9])")


def render_template(template_text, definition):
    """
    Return the template text with the network's names swapped in for DISTANCE's.

    The committed template is written for DISTANCE, so DISTANCE comes back unchanged.
    For any other network the network name (including the system junction source
    "<network>_Junctions"), the three source names and the feature dataset in the
    catalog path are replaced. Raises ValueError if a name is missing from the
    template, because that means the template and this module have drifted apart.
    """
    text = template_text

    for role, base_name in BASE_NAMES.items():

        new_name = getattr(definition, role + "_name")

        if new_name == base_name:
            continue

        pattern = _name_pattern(base_name)

        if not pattern.search(text):
            raise ValueError(
                "The template has no {!r} to rename for {}.".format(
                    base_name, definition.key
                )
            )

        text = pattern.sub(new_name, text)

    base_fd = "/FD={}/".format(BASE_FEATURE_DATASET)
    new_fd = "/FD={}/".format(definition.feature_dataset.split(".", 1)[-1])

    if new_fd != base_fd:

        if base_fd not in text:
            raise ValueError(
                "The template has no {!r} catalog path to rename for {}.".format(
                    base_fd, definition.key
                )
            )

        text = text.replace(base_fd, new_fd)

    return text


def rendered_template_path(definition, base_template_path, output_dir):
    """
    Return the template file to build definition's network from.

    DISTANCE uses the committed template as it is. Any other network gets a rendered
    copy written to output_dir, which is not committed.
    """
    base_template_path = Path(base_template_path)

    if definition.key == DEFAULT_NETWORK:
        return base_template_path

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "network_template_{}.xml".format(definition.key)
    out_path.write_text(
        render_template(base_template_path.read_text(encoding="utf-8"), definition),
        encoding="utf-8",
    )

    return out_path


if __name__ == "__main__":

    for definition in DEFINITIONS.values():

        print("{}: {}".format(definition.key, definition.description))

        for field in definition._fields[2:]:

            print("  {:<18} {}".format(field, getattr(definition, field)))

    print("\nActive ({} set to {!r}): {}".format(
        NETWORK_ENV_VAR, os.environ.get(NETWORK_ENV_VAR), get_definition().key
    ))
