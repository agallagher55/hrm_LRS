"""
Run the whole QA refresh in order, from the preflight checks to the topology.

This replaces launching steps 00 to 07, the grants, the audits and the topology by hand. It runs
each step's own main(), so nothing about what a step does has changed. What it changes:
  - It checks the deployed files against the repo manifest before anything else.
  - It asks for a typed confirmation at the three points that need a person, instead of you
    editing CONFIRM_* flags in the step scripts: before the delete, before the swap and build
    (after the spatial review), and before the grants. Anything else typed stops the run.
  - It saves everything printed to a transcript and writes a run report with the key numbers,
    to the output folder.
  - It stops at the first failure and says where to resume (START_AT).

Settings are the globals below. Set NETWORK to match the HRM_NETWORK environment variable (unset
means DISTANCE); the run stops if they disagree. The step scripts keep their own checks: step 02
still needs a recent step 01 backup and step 06 still stops on a stale orchestrator.

Not automated, and printed at the end: the OS-auth add-to-map test, the route smoke tests,
reapplying Robbie's topology exceptions and telling him QA is ready.

Written 2026-10-09 and not yet run on live QA. Run it from PyCharm or an ArcGIS Pro Python prompt
(it needs to read what you type).
"""

import datetime
import re
import sys
import time
from collections import namedtuple
from pathlib import Path

# The scripts folder holds deploy_check.py, which uses only the standard library. Load it first so
# stale copies of the other files are reported before they can break an import.
sys.path.insert(0, str(Path(__file__).parent.parent))

import deploy_check  # noqa: E402
import config  # noqa: E402


# The network this run refreshes. It must match HRM_NETWORK (unset means DISTANCE).
NETWORK = "DISTANCE"

# Resume at this phase key after a failure, or stop after one. None runs everything. Keys are listed
# when the run starts.
START_AT = None
STOP_AFTER = None

# True prints the plan and the gates and does nothing else.
LIST_ONLY = False

# Replaced in the tests.
ask = input

Phase = namedtuple("Phase", "key title run gate on_failure")
Gate = namedtuple("Gate", "phrase message")


class GateDeclined(Exception):
    """The operator did not type the confirmation phrase."""


DELETE_GATE = Gate(
    "DELETE QA NETWORK",
    "\nThe next phase DELETES the QA network dataset, its topology and its edge, junction and turn "
    "classes.\nBefore you continue, check that:\n"
    "  - the backup and export just made are intact (the phase before this one reported them);\n"
    "  - Robbie and anyone else using QA know it will be down, and Pro has nothing open on it;\n"
    "  - Prod's TRNLRS_TRN_STREET_VW has the LRS fixes you expect (step 00 printed its counts and dates).",
)

BUILD_GATE = Gate(
    "REVIEWED",
    "\nThe next phase swaps the staging turns into place and builds the network, once.\n"
    "Complete the spatial review first: network_dataset/docs/traffic_turn_staging_review_checklist.txt "
    "(random turns on intersections, multi-leg intersections, the skipped turns).",
)

GRANT_GATE = Gate(
    "GRANT",
    "\nThe statements above grant PUBLIC SELECT on the new network's tables. Nothing else is changed.",
)


def load_step(filename, directory=None):
    """Import a step script by path without running its main block."""
    from _shared import load_script

    directory = directory or config.QA_REFRESH_DIR
    module_name = "run_qa_refresh_" + re.sub(r"\W", "_", Path(filename).stem)

    return load_script(Path(directory) / filename, module_name)


def run_preflight():
    load_step("00_confirm_sources.py").main()


def run_backup():
    load_step("01_backup_and_baseline.py").main()


def run_audit_before():
    module = load_step("audit_grants.py")
    module.LABEL = "before"
    module.main()


def run_delete():
    module = load_step("02_delete_network_sources.py")
    module.CONFIRM_DELETE_QA_NETWORK = True
    module.NETWORK_TO_DELETE = NETWORK
    module.main()


def run_copy():
    load_step("03_copy_sources.py").main()


def run_remap():
    load_step("04_remap_turns.py").main()


def run_verify_staging():
    load_step("05_verify_staging_turns.py").main()


def run_build():
    module = load_step("06_swap_and_final_build.py")
    module.CONFIRM_REVIEWED_STAGING = True
    module.NETWORK_TO_BUILD = NETWORK
    module.main()


def run_verify_live():
    load_step("07_verify_live_turns.py").main()


def run_build_errors():
    load_step("collect_build_errors.py").main()


def run_grants():
    """Show the grants as a dry run, then apply them after a typed confirmation."""
    module = load_step("grant_network_access.py")
    module.APPLY = False

    if not module.main():
        return

    confirm(GRANT_GATE)
    module.APPLY = True
    module.main()


def run_audit_after():
    module = load_step("audit_grants.py")
    module.LABEL = "after"
    module.main()


def run_topology():
    load_step("07_create_topology.py", config.CORE_SCRIPTS_DIR).main()


PHASES = [
    Phase("preflight", "Step 00: confirm sources and deployed files", run_preflight, None,
          "Fix what it reports and run again. Nothing has been changed."),
    Phase("backup", "Step 01: backup and baseline", run_backup, None,
          "Nothing has been deleted. Fix the cause and rerun from this phase."),
    Phase("audit_before", "Audit the registration tables (before)", run_audit_before, None,
          "Read only. Rerun from this phase, or skip it by starting at 'delete'."),
    Phase("delete", "Step 02: delete the network and its sources", run_delete, DELETE_GATE,
          "Check what still exists in SDEADM.TRNLRS_network first. The backup in output is intact. "
          "Step 02 skips classes that are already gone, so rerun from this phase."),
    Phase("copy", "Step 03: copy fresh sources", run_copy, None,
          "Delete any partly copied class in the network feature dataset first, because step 03 skips a "
          "class that already exists. Then rerun from this phase."),
    Phase("remap", "Step 04: remap the turns", run_remap, None,
          "Delete TRNLRS_traffic_turn_staging if it was left behind (script 05 will not overwrite it), "
          "then rerun from this phase."),
    Phase("verify_staging", "Step 05: verify the staging turns", run_verify_staging, None,
          "Read the failed check. Do not go on to the build."),
    Phase("build", "Step 06: swap the turns, create and build the network", run_build, BUILD_GATE,
          "If the log shows the swap already ran (the staging class was renamed), do NOT rerun this phase. "
          "Fix the cause (for example the template), run 03_create_network_dataset.py directly (it "
          "creates and builds), then set START_AT = 'verify_live'. If it stopped before changing anything "
          "(for example a stale run_full_network_rebuild.py), fix that and rerun from this phase."),
    Phase("verify_live", "Step 07: verify the live turns", run_verify_live, None,
          "Read the failed check."),
    Phase("build_errors", "Save and summarise the BuildErrors file", run_build_errors, None,
          "Copy the file out of the temp folder by hand if it is still there. Then start at 'grants'."),
    Phase("grants", "Grant PUBLIC SELECT on the new network", run_grants, None,
          "Rerun from this phase. It only grants what is missing."),
    Phase("audit_after", "Audit the registration tables (after)", run_audit_after, None,
          "Read only. Rerun from this phase."),
    Phase("topology", "Rebuild the topology and export its errors", run_topology, None,
          "The network is already built. Rerun from this phase."),
]

# Lines worth keeping in the run report, by phase key. Each pattern is searched in a printed or
# logged line (the timestamp prefix is removed first).
FACT_PATTERNS = {
    "preflight": [r"Deployed files checked", r"STALE|MISSING|EXTRA", r"All tracked files match", r"^count=", r"count=[\d,]+"],
    "backup": [r"^Exported ", r"^Backup verified"],
    "delete": [r"^Turn backup confirmed", r"^Deleting ", r"^Already absent"],
    "copy": [r"Edge exclusions applied", r"STR_TYPE in|FDMID list", r"^\s*(edge|junction|turn)\s+[\d,]+", r"Source counts"],
    "remap": [r"Total input turns", r"Written\s*:", r"Skipped\s*:", r"missing_old_geometry|no_shared_endpoint|unresolved_edge",
              r"Edge1End integrity", r"DSID:"],
    "verify_staging": [r"VERIFICATION (PASSED|FAILED)", r"FAIL"],
    "build": [r"Network dataset created", r"Build complete", r"BuildNetwork messages", r"WARNING 030116",
              r"(Edges|Junctions|Turns) \((source|user-defined)\)"],
    "verify_live": [r"VERIFICATION (PASSED|FAILED)", r"FAIL"],
    "build_errors": [r"errors and warnings", r"^\s+[\d,]+\s", r"Turns with errors", r"Compared with", r"->"],
    "grants": [r"Tables checked", r"^\s+GRANT SELECT", r"Verified", r"Nothing to grant"],
    "audit_after": [r"^\s+(N|ND)_\d+\s", r"pair:", r"missing a grant"],
    "topology": [r"errors_(point|line|poly)", r"Must (Not|Be) "],
}

TIMESTAMP_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \| \w+ \| ")


class Transcript:
    """Collects everything printed or logged, for the transcript file and the per-phase facts."""

    def __init__(self, path):
        self.file = open(path, "w", encoding="utf-8")
        self.current = []
        self.closed = False

    def write(self, text):
        if not self.closed:
            self.file.write(text)
            self.current.append(text)

    def flush(self):
        if not self.closed:
            self.file.flush()

    def take(self):
        text = "".join(self.current)
        self.current = []

        return text

    def close(self):
        self.closed = True
        self.file.close()


class Tee:
    """Stands in for sys.stdout or sys.stderr and copies what is written to the transcript."""

    def __init__(self, stream, transcript):
        self.stream = stream
        self.transcript = transcript

    def write(self, text):
        self.transcript.write(text)

        return self.stream.write(text)

    def flush(self):
        self.transcript.flush()
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def extract_facts(text, patterns):
    """The distinct lines of text that match any pattern, without their log timestamps."""
    facts = []

    for line in text.splitlines():
        cleaned = TIMESTAMP_PREFIX.sub("", line).rstrip()

        if not cleaned.strip():
            continue

        if any(re.search(pattern, cleaned) for pattern in patterns) and cleaned not in facts:
            facts.append(cleaned)

    return facts


def confirm(gate):
    print(gate.message)
    answer = ask(f'\nType "{gate.phrase}" to continue. Anything else stops the run: ').strip()

    if answer != gate.phrase:
        raise GateDeclined(f"The confirmation {gate.phrase!r} was not typed.")


def select_phases():
    keys = [phase.key for phase in PHASES]

    for name, value in (("START_AT", START_AT), ("STOP_AFTER", STOP_AFTER)):
        if value is not None and value not in keys:
            raise RuntimeError(f"{name} is {value!r}. It must be None or one of: {', '.join(keys)}")

    start = keys.index(START_AT) if START_AT else 0
    stop = keys.index(STOP_AFTER) + 1 if STOP_AFTER else len(PHASES)

    if stop <= start:
        raise RuntimeError("STOP_AFTER comes before START_AT.")

    return PHASES[start:stop]


def print_plan(phases):
    print(f"QA refresh for {NETWORK} ({len(phases)} phases)")

    for phase in phases:
        gate = f"   [asks you to type {phase.gate.phrase!r}]" if phase.gate else ""
        print(f"  {phase.key:<15} {phase.title}{gate}")

    print()


def build_report(network, started, results, transcript_path, outcome):
    lines = [
        f"# QA refresh report: {network}",
        "",
        f"Started {started:%Y-%m-%d %H:%M:%S}. Outcome: {outcome}.",
        f"Transcript: {transcript_path}",
        "",
        "| Phase | Result | Seconds |",
        "|---|---|---|",
    ]

    for result in results:
        lines.append(f"| {result['title']} | {result['status']} | {result['seconds']:.0f} |")

    for result in results:
        if result["facts"] or result.get("error"):
            lines += ["", f"## {result['title']}", ""]
            lines += [f"- {fact}" for fact in result["facts"]]

            if result.get("error"):
                lines.append(f"- FAILED: {result['error']}")

    lines += [
        "",
        "## Still manual",
        "",
        "- An OS-auth add-to-map test and a route solve with directions on.",
        "- Smoke tests with the travel mode restrictions ticked: one way in both directions and a prohibited turn.",
        "- Reapply Robbie's topology exceptions, then tell him QA is ready.",
    ]

    return "\n".join(lines) + "\n"


def check_network():
    from _shared import require_network

    require_network(NETWORK, "NETWORK in run_qa_refresh.py")


def run_phase(phase, transcript):
    """Run one phase. Return its result dict."""
    result = {"key": phase.key, "title": phase.title, "status": "ok", "seconds": 0.0, "facts": []}
    began = time.time()
    print(f"\n=== {phase.title} ===")

    try:
        phase.run()
    except SystemExit as error:
        if error.code not in (None, 0):
            result["status"] = "FAILED"
            result["error"] = str(error.code)
    except GateDeclined:
        raise
    except Exception as error:  # noqa: BLE001 a step may fail in any way and the run must report it
        result["status"] = "FAILED"
        result["error"] = f"{type(error).__name__}: {error}"

    result["seconds"] = time.time() - began
    result["facts"] = extract_facts(transcript.take(), FACT_PATTERNS.get(phase.key, []))

    return result


def main():
    phases = select_phases()
    print_plan(phases)

    if LIST_ONLY:
        return

    deploy_check.require_current()
    check_network()
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    started = datetime.datetime.now()
    stamp = started.strftime("%Y%m%d_%H%M%S")
    transcript_path = config.OUTPUT_DIR / f"refresh_run_{stamp}.log"
    report_path = config.OUTPUT_DIR / f"refresh_report_{stamp}.md"
    transcript = Transcript(transcript_path)
    saved_streams = (sys.stdout, sys.stderr)
    sys.stdout = Tee(sys.stdout, transcript)
    sys.stderr = Tee(sys.stderr, transcript)
    results = []
    outcome = "completed"
    failed = None

    try:
        for phase in phases:
            if phase.gate:
                confirm(phase.gate)
                transcript.take()

            result = run_phase(phase, transcript)
            results.append(result)

            if result["status"] != "ok":
                outcome = f"stopped, {phase.key} failed"
                failed = (phase, result)

                break
    except GateDeclined as error:
        outcome = f"stopped at a gate: {error}"
    finally:
        text = build_report(NETWORK, started, results, transcript_path, outcome)
        report_path.write_text(text, encoding="utf-8")
        sys.stdout, sys.stderr = saved_streams
        transcript.close()

    print(f"\nRun report: {report_path}\nTranscript: {transcript_path}")

    if failed:
        phase, result = failed
        print(f"\nFAILED in '{phase.key}': {result['error']}\n{phase.on_failure}\nTo resume, set START_AT = '{phase.key}' "
              "unless the note above says otherwise, and run again.")
        sys.exit(1)

    if outcome != "completed":
        print(f"\n{outcome}. Nothing after the gate ran. Set START_AT to resume.")

        return

    print("\nStill manual: the OS-auth add-to-map test, the route smoke tests, Robbie's topology exceptions and telling him.")


if __name__ == "__main__":
    main()
