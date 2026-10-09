"""
Record when the network dataset was last rebuilt and last refreshed in its own metadata.

Anyone who opens the network dataset in Pro (Catalog, Metadata) can then see how current it is
without asking. Two facts are kept:
  - Last rebuilt: when Build Network last finished. Script 03 writes it after every build.
  - Last refreshed from Prod: when the edge source was last copied from Prod's
    TRNLRS_TRN_STREET_VW. Only the QA refresh does this, so run_qa_refresh.py writes it and a
    network that is never refreshed from Prod has no such line.

The facts sit in one marked block at the end of the item description. Each write replaces that
block and keeps the line it was not given, so a rebuild alone does not erase the refresh time.
The rest of the description is left alone.

The reading and writing is done by the team's gispy.metadata module (get_sde_metadata and
update_metadata, in the gispy repo on GitHub), not by calling arcpy.metadata here. It lives on the
server under GISPY_MODULES_DIR. After the write the description is read back, so a read only item
(which update_metadata skips without an error) is reported instead of passing silently.

A failure to write the metadata is logged and returned, never raised: a stamp must not stop a
build that has already succeeded. Written 2026-10-09 and not yet run against a live network
dataset, so check that Pro shows the block (Catalog, the network dataset, Metadata, Description).
"""

import datetime
import os
import re
import sys

# The folder that holds the gispy package on the server (gispy\\metadata\\metadata.py). Taken from the
# path in gispy's parcelload script, so check it. It is added to sys.path only if gispy cannot be
# imported already.
GISPY_MODULES_DIR = r"E:\HRM\Scripts\Python\Modules"

# A connection file path ends at the .sde file. What follows is the dataset path inside it.
SDE_PATH_PATTERN = re.compile(r"^(.*?\.sde)[\\/](.+)$", re.IGNORECASE)

START = "[Network refresh status, written by the network scripts. Do not edit this block by hand.]"
END = "[End of network refresh status]"

REBUILT_LABEL = "Last rebuilt: "
REFRESHED_LABEL = "Last refreshed from Prod's TRNLRS_TRN_STREET_VW: "

TIME_FORMAT = "%Y-%m-%d %H:%M"

BLOCK_PATTERN = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)


def format_time(value):
    """The text written for a time: a datetime is formatted, a string is used as it is."""
    if isinstance(value, datetime.datetime):
        return value.strftime(TIME_FORMAT)

    return str(value)


def read_block_values(text):
    """The (rebuilt, refreshed) texts already in the description's block, None for a missing line."""
    match = BLOCK_PATTERN.search(text or "")
    rebuilt = refreshed = None

    if not match:
        return rebuilt, refreshed

    for line in match.group(0).splitlines():
        if line.startswith(REBUILT_LABEL):
            rebuilt = line[len(REBUILT_LABEL):].strip()
        elif line.startswith(REFRESHED_LABEL):
            refreshed = line[len(REFRESHED_LABEL):].strip()

    return rebuilt, refreshed


def merge_block(text, rebuilt=None, refreshed=None):
    """The description with the status block set. A value left as None keeps the one already there."""
    old_rebuilt, old_refreshed = read_block_values(text)
    rebuilt = format_time(rebuilt) if rebuilt is not None else old_rebuilt
    refreshed = format_time(refreshed) if refreshed is not None else old_refreshed
    lines = [START]

    if rebuilt:
        lines.append(REBUILT_LABEL + rebuilt)

    if refreshed:
        lines.append(REFRESHED_LABEL + refreshed)

    lines.append(END)
    block = "\n".join(lines)
    text = text or ""

    if BLOCK_PATTERN.search(text):
        return BLOCK_PATTERN.sub(lambda match: block, text, count=1)

    if text.strip():
        return text.rstrip() + "\n\n" + block

    return block


def split_sde_path(network_path):
    """(connection file, dataset path inside it) for a path such as ...\\qa_RW_sdeadm.sde\\FD\\Network."""
    match = SDE_PATH_PATTERN.match(str(network_path))

    if not match:
        raise ValueError(f"{network_path} is not a path inside an .sde connection file")

    return match.group(1), match.group(2)


def load_gispy_metadata():
    """The gispy.metadata.metadata module, importing it from GISPY_MODULES_DIR if it is not on the path."""
    try:
        from gispy.metadata import metadata as gispy_metadata
    except ImportError:
        if GISPY_MODULES_DIR and os.path.isdir(GISPY_MODULES_DIR) and GISPY_MODULES_DIR not in sys.path:
            sys.path.insert(0, GISPY_MODULES_DIR)

        from gispy.metadata import metadata as gispy_metadata

    return gispy_metadata


def stamp(network_path, logger=None, rebuilt=None, refreshed=None):
    """Write the status block into the network dataset's metadata. Returns True when it was saved."""
    def say(level, message):
        if logger:
            getattr(logger, level)(message)
        else:
            print(message)

    try:
        gispy_metadata = load_gispy_metadata()
        db, feature = split_sde_path(network_path)
        current = gispy_metadata.get_sde_metadata(db, feature)["DESCRIPTION"]
        merged = merge_block(current, rebuilt, refreshed)
        options = {"description": merged}

        # gispy's revised date is the item's own "Revised" date, so a rebuild moves it too.
        if isinstance(rebuilt, datetime.datetime):
            options["revised_date"] = rebuilt.strftime("%Y-%m-%dT00:00:00")

        gispy_metadata.update_metadata(db, feature, options)
        saved = gispy_metadata.get_sde_metadata(db, feature)["DESCRIPTION"]

        # update_metadata skips a read only item without an error, so read the description back.
        if read_block_values(saved) != read_block_values(merged):
            say("warning", f"Metadata not updated on {network_path}: the description did not change "
                           "(the item may be read only).")

            return False
    except Exception as error:  # noqa: BLE001 a stamp must never stop a build that already succeeded
        say("warning", f"Metadata not updated on {network_path}: {type(error).__name__}: {error}")

        return False

    say("info", f"Metadata updated on {network_path}: rebuilt {rebuilt and format_time(rebuilt)}, "
                f"refreshed {refreshed and format_time(refreshed)} (None means unchanged).")

    return True
