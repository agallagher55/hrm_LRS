"""
Save the BuildErrors file from the latest network build and summarise it.

Build Network writes BuildErrors_<guid>.txt to a numbered folder under the client's temp
directory, and Windows cleans it up, so it has to be copied out the same day. The path is in the
script 03 log, on the line that reads:
  WARNING 030116: The network was built, but with some errors. Error details are at "<path>".

This finds the newest log that has such a line, copies the file to intermediate_results and
prints how many errors of each kind it holds. If an earlier BuildErrors file is in
intermediate_results it also shows what changed, including whether the same turns were rejected.
Run it right after step 06. It changes nothing in QA.
"""

import re
import shutil
from collections import Counter
from pathlib import Path

import config
import log_utils


LOG_DIR = log_utils.LOG_DIR
RESULTS_DIR = config.NETWORK_DATASET_DIR / "intermediate_results"

# Script 03 writes the build messages to its own log, for example
# 20261009_101349_03_create_network_dataset.log.
LOG_PATTERN = "*_03_create_network_dataset.log"
ERROR_PATH = re.compile(r'Error details are at "([^"]+BuildErrors_[^"]+\.txt)"')
ERROR_LINE = re.compile(r"^Source table \[([^\]]+)\], Object ID \[(\d+)\]: (.*?)\.?\s*$")


def find_error_path(log_dir=None):
    """Return (log file, BuildErrors path) from the newest log that names one, or (None, None)."""
    log_dir = log_dir or LOG_DIR

    for log_file in sorted(log_dir.glob(LOG_PATTERN), reverse=True):
        found = ERROR_PATH.findall(log_file.read_text(encoding="utf-8", errors="replace"))

        if found:
            return log_file, found[-1]

    return None, None


def parse_errors(text):
    """Return ([(source, object id, message)], number of lines that did not parse)."""
    errors = []
    unparsed = 0

    for line in text.splitlines():
        if not line.strip():
            continue

        match = ERROR_LINE.match(line)

        if match:
            errors.append((match.group(1), int(match.group(2)), match.group(3)))
        else:
            unparsed += 1

    return errors, unparsed


def summarise(errors):
    """Count the errors by source table and message."""
    return Counter((source, message) for source, _, message in errors)


def previous_file(results_dir, current_name):
    """The most recently saved BuildErrors file other than the current one, or None."""
    others = [
        path for path in results_dir.glob("BuildErrors_*.txt")
        if path.name != current_name
    ]

    return max(others, key=lambda path: path.stat().st_mtime) if others else None


def object_ids(errors, source_part):
    return {oid for source, oid, _ in errors if source_part in source}


def describe(counts):
    return [f"  {count:>6,}  {message}  [{source}]" for (source, message), count in counts.most_common()]


def main():
    log_file, error_path = find_error_path()

    if not error_path:
        raise RuntimeError(
            f"No log in {LOG_DIR} names a BuildErrors file. Run step 06 first, or check the script 03 log "
            "for the WARNING 030116 line. If the build had no errors there is nothing to collect."
        )

    print(f"Log: {log_file.name}\nBuildErrors file named in it: {error_path}")
    source = Path(error_path)

    if not source.is_file():
        raise RuntimeError(
            f"{error_path} no longer exists (Windows clears the temp folder). Rebuild the network to get a "
            "new one, or copy the file by hand if you still have it."
        )

    RESULTS_DIR.mkdir(exist_ok=True)
    saved = RESULTS_DIR / source.name
    previous = previous_file(RESULTS_DIR, source.name)

    if not saved.exists():
        shutil.copy2(source, saved)
        print(f"Saved to {saved}")
    else:
        print(f"Already saved: {saved}")

    errors, unparsed = parse_errors(saved.read_text(encoding="utf-8", errors="replace"))
    counts = summarise(errors)
    print(f"\n{len(errors):,} errors and warnings" + (f", {unparsed} lines not understood" if unparsed else ""))

    for line in describe(counts):
        print(line)

    result = {"file": saved, "counts": counts, "total": len(errors), "unparsed": unparsed, "previous": previous}

    if previous:
        earlier, _ = parse_errors(previous.read_text(encoding="utf-8", errors="replace"))
        before = summarise(earlier)
        print(f"\nCompared with {previous.name}")

        for key in sorted(set(counts) | set(before)):
            source_name, message = key
            print(f"  {before.get(key, 0):>6,} -> {counts.get(key, 0):>6,}  {message}  [{source_name}]")

        turns_now = object_ids(errors, "traffic_turn")
        turns_before = object_ids(earlier, "traffic_turn")
        same = "the same turns" if turns_now == turns_before else "DIFFERENT turns"
        print(f"  Turns with errors: {sorted(turns_now)} ({same} as before)")
        result["same_turns"] = turns_now == turns_before
    else:
        print("\nNo earlier BuildErrors file in intermediate_results to compare with.")

    return result


if __name__ == "__main__":
    main()
