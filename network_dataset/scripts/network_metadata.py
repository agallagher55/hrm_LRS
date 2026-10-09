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

A failure to write the metadata is logged and returned, never raised: a stamp must not stop a
build that has already succeeded. Written 2026-10-09 and not yet run against a live network
dataset, so check that Pro shows the block (Catalog, the network dataset, Metadata, Description).
"""

import datetime
import re

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


def stamp(network_path, logger=None, rebuilt=None, refreshed=None):
    """Write the status block into the network dataset's metadata. Returns True when it was saved."""
    def say(level, message):
        if logger:
            getattr(logger, level)(message)
        else:
            print(message)

    try:
        import arcpy

        metadata = arcpy.metadata.Metadata(network_path)

        if metadata.isReadOnly:
            say("warning", f"Metadata not updated: {network_path} is read only.")

            return False

        metadata.description = merge_block(metadata.description, rebuilt, refreshed)
        metadata.save()
    except Exception as error:  # noqa: BLE001 a stamp must never stop a build that already succeeded
        say("warning", f"Metadata not updated on {network_path}: {type(error).__name__}: {error}")

        return False

    say("info", f"Metadata updated on {network_path}: rebuilt {rebuilt and format_time(rebuilt)}, "
                f"refreshed {refreshed and format_time(refreshed)} (None means unchanged).")

    return True
