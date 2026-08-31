# Turn Rebuild — QA Test Runbook

Step-by-step procedure for testing the 2026-08-31 rewrite of
`scripts/05_rebuild_traffic_turns.py` against **QA** (`ms-gis-sql-q21`), and the
list of outputs needed to assess the result.

Background on what changed and why:
[`network_dataset_script_review.md`](network_dataset_script_review.md) sections A1–A4 and B.

**Environment: QA only.** Nothing in this runbook writes to prod. Script 03 reads
`TRNLRS_TRN_STREET_VW` from prod, but only when the feature dataset copy is absent — it is
present in QA, so that read is skipped.

**Time:** roughly 1.5–2 hours, most of it waiting on the remap and the build.

---

## Phase 0 — Setup and baseline

### 0.1 Get the code

```
git fetch origin
git checkout claude/network-dataset-scripts-review-mj09ob
git pull
```

Run everything from the `scripts/` directory in an **ArcGIS Pro Python environment**
(`arcpy` importable, Network Analyst extension available). The scripts import `log_utils`
from their own directory.

Logs are written to `<repo>/logs/<timestamp>_<script>.log` — console gets INFO, the file
gets DEBUG. **The DEBUG lines matter here**: the per-reason skipped OID lists and the full
`BuildNetwork` messages only exist in the file. `logs/` is gitignored, so these stay local.

### 0.2 Confirm the environment config

Both scripts must point at QA. Check the top of each:

| File | Constant | Expected |
|---|---|---|
| `05_rebuild_traffic_turns.py` | `SDE` | `E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde` |
| `05_rebuild_traffic_turns.py` | `NETWORK_FD` | `SDEADM.TRNLRS_network` |
| `05_rebuild_traffic_turns.py` | `AUTO_SWAP_AND_REBUILD` | `False` |
| `03_create_network_dataset.py` | `SDE_CONNECTION_UPDATE` | `E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde` |
| `verify_turn_rebuild.py` | `SDE` | `E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde` |

They ship set this way. If you change one, change all of them — the orchestrator asserts
05 and 03 agree, but the standalone path does not.

### 0.3 Back up the current turn FC

The swap in Phase 3 **deletes** the live `TRNLRS_traffic_turn`. Take a copy first — this is
the only cheap undo, and it also preserves any turns hand-edited through the
`HRM\GIS_LRS_EVENT_EDITOR` grant since 2026-07-14.

```python
import arcpy
sde = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"
arcpy.management.CopyFeatures(
    sde + r"\SDEADM.TRNLRS_network\SDEADM.TRNLRS_traffic_turn",
    sde + r"\SDEADM.TRNLRS_traffic_turn_bak_20260831",   # standalone, outside the FD
)
print(arcpy.management.GetCount(sde + r"\SDEADM.TRNLRS_traffic_turn_bak_20260831"))
```

Outside the feature dataset, so it is not a network source and stays freely deletable.

### 0.4 Clear any stale staging FC

Script 05 refuses to run if its output already exists. If a
`TRNLRS_traffic_turn_staging` is left over from the 2026-07 runs, delete it (it is not a
registered network source, so this works without touching the network dataset).

### 0.5 Baseline — is QA broken today?

Run the verifier against the **current live** turn FC before changing anything. Set:

```python
TURN_FC = SDE + rf"\{NETWORK_FD}\SDEADM.TRNLRS_traffic_turn"
```

```
python verify_turn_rebuild.py
```

This is the check nobody has run. The review predicts it fails on check 2
(`Edge{N}FCID` = 2 rather than the DSID) and/or check 9 (`Edge1End`). **Whatever it says,
keep the output** — if it passes, the premise for this whole rewrite is wrong and we should
stop and re-think rather than swapping anything.

Then set `TURN_FC` back to the staging path for the rest of the run.

---

## Phase 1 — Remap (nothing is committed yet)

### 1.1 Run the remap

```
python 05_rebuild_traffic_turns.py
```

`AUTO_SWAP_AND_REBUILD` is `False`, so this only creates
`SDEADM.TRNLRS_network\TRNLRS_traffic_turn_staging`. The live turn FC and the network
dataset are untouched. Expect several minutes — it loads all ~18,500 new edge geometries
and all old `TRN_street` geometries into memory.

### 1.2 Read five things in the log

**(a) Environment** — confirm QA, not Dev:

```
Environment: E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde
Network feature dataset: SDEADM.TRNLRS_network
```

**(b) The `Edge1Pos` / `Edge1End` distributions.** This is the diagnostic that motivated
the rewrite, now folded into the run:

```
Source Edge1Pos / Edge1End distribution:
  Edge1Pos distribution (top N): [...]
  Edge1End distribution (top N): [...]
```

- `Edge1Pos` clustered on a single value (expected: `0.5`) → confirms the old
  `pos >= 0.5` test was a constant, and the rewrite was necessary.
- `Edge1Pos` spread across `0.0`–`1.0` → my reading of the Esri schema is wrong for this
  data. The rewrite is still correct (geometry beats inference either way), but **tell me** —
  it changes what the old 1,209/29 result actually meant.

**(c) The edge FC DSID:**

```
  TRNLRS_TRN_STREET DSID: <n>
```

Note this number. Every `Edge{N}FCID` in the output must equal it. If it is `2`, something
is very wrong — that is the ordering index, not a DSID.

**(d) The skip breakdown:**

```
  Total input turns : 1238
  Written           : ...
  Skipped           : ... (...%)
    <reason>        : ...
```

**Expect a higher skip count than the 2.3% from 2026-07-13.** That figure counted only
Edge1 misses; turns whose Edge2–5 failed were written out as one-edge or gapped records and
counted as successes. The new number is the honest one. What matters is the *breakdown*:

| Reason | What it means |
|---|---|
| `no_shared_endpoint` | consecutive old edges don't meet — suspicious in bulk, check `SNAP_TOLERANCE` |
| `unresolved_edge` | no new edge at the junction — segment dropped by LRS resegmentation (expected in small numbers) or tolerance too tight |
| `new_edge_not_spanning` | a middle edge was split by resegmentation; the turn genuinely can't be represented |
| `too_few_edges` | source record had <2 edges — a data problem in `TRN_traffic_turn`, not a remap failure |
| `missing_old_geometry` | old edge OID has no geometry — likewise a source data problem |
| `edge1end_undetermined` | junction at neither end of the matched edge — should be zero; tell me if not |

**(e) The Edge1End integrity check:**

```
Edge1End integrity check: X/Y (Z%) of source Edge1End values agree with the junction
derived from geometry.
```

This compares the source's own `Edge1End` against the junction this script finds on the
**old** Edge1. It is the strongest available signal that junction detection is sound.

- **≥ 99%** — junction detection confirmed. Proceed.
- **95–99%** — proceed, but the disagreeing OIDs (DEBUG in the log) are worth a look.
- **< 95%** — the script warns and will refuse an auto-swap. **Stop and send me the log.**

### 1.3 Gate

Do not continue if: the environment lines say Dev, the DSID is `2`, the agreement rate is
below 95%, or the total skip rate is above ~10%.

---

## Phase 2 — Verify the staging FC

### 2.1 Run the verifier

With `TURN_FC` pointing at `..._staging`:

```
python verify_turn_rebuild.py
```

Nine checks, all mechanical, none requiring a build. It exits `1` on any failure. Checks
8 (consecutive edges actually meet) and 9 (`Edge1End` matches geometry) are the ones that
catch a remap that looks plausible but is wrong.

**Gate: this must exit 0 before you swap anything.**

### 2.2 Spatial spot checks

The verifier proves the turn FC is *internally consistent with the edge FC*. It cannot tell
you a turn landed on the *correct* intersection. Work sections 3, 4 and 5 of
[`traffic_turn_staging_review_checklist.txt`](traffic_turn_staging_review_checklist.txt) —
especially the multi-leg intersections, where the bearing tiebreaker is doing the work.

---

## Phase 3 — Swap and rebuild

### 3.1 Swap the turn FC

Order matters: `TRNLRS_traffic_turn` is a registered turn source, so ArcGIS refuses to
delete or rename it (`ERROR 001919`) until the network dataset is gone. Script 05 prints
these four lines at the end of its run; they are reproduced here:

```python
import arcpy
sde = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"
fd = sde + r"\SDEADM.TRNLRS_network"

arcpy.management.Delete(fd + r"\SDEADM.TRNLRS_street_network")     # releases the lock
arcpy.management.Delete(fd + r"\SDEADM.TRNLRS_traffic_turn")
arcpy.management.Rename(fd + r"\SDEADM.TRNLRS_traffic_turn_staging", "TRNLRS_traffic_turn")
```

### 3.2 Recreate and build

```
python 03_create_network_dataset.py
```

It skips re-copying the three source FCs (they exist) and goes straight to
`CreateNetworkDatasetFromTemplate` + `BuildNetwork`. **Watch the log for
`Copying into feature dataset` on the turn FC** — that would mean it did *not* find your
swapped FC and has re-copied the raw unremapped `TRN_traffic_turn`, which is the
2026-07-07 / 2026-07-14 regression. It should say `Already present ... skipping` for all
three.

Run `BuildNetwork` exactly once. Do not also click Build Network in Pro — a double build
stacks two generations of system junctions (the 16,334 junctions / 37,728 edges seen
earlier).

### 3.3 Find and read the build errors file

The path is in the GP messages, which script 03 logs at DEBUG:

```
findstr /i "BuildErrors" ..\logs\<timestamp>_03_create_network_dataset.log
```

Open that file. Confirm its GUID matches the one in *this* run's log — a stale
`BuildErrors_*.txt` from an earlier build is what sent the 2026-06-29 investigation off
course for an afternoon.

Expected contents:
- **Zero** `Cannot find edge element corresponding to turn identifier` lines. Any at all
  means the remap did not take.
- Many `Standalone user-defined junction is detected` warnings for
  `TRNLRS_street_junction`. **Expected and harmless** — LRS resegmentation moved edge
  endpoints, so some manually-placed junctions no longer coincide with one. Count them, but
  they are not a failure.

---

## Phase 4 — Post-build

### 4.1 Re-verify against the live FC

Point `TURN_FC` at `SDEADM.TRNLRS_traffic_turn` (no `_staging`) and run
`verify_turn_rebuild.py` again. This confirms the rename didn't disturb anything and that
the FC the network is actually reading is the one you verified.

### 4.2 Re-apply the SQL grants — do not skip this

Deleting and recreating the network dataset **reassigns its registration IDs**, and the
`PUBLIC SELECT` grants go with the old ones. QA's OS-auth users will lose access until this
is redone. Follow
[`network_dataset_sql_permissions.md`](network_dataset_sql_permissions.md) — look up the new
`N_<id>_*` and `ND_<id>_*` numbers with the §2b audit query, then grant. The previous IDs
(`N_3`, `ND_38726`) are almost certainly stale now.

### 4.3 Network Dataset Properties

Open `TRNLRS_street_network` in Pro → Properties → **Sources**. The Turns row must show a
**nonzero** count. This has never been confirmed as nonzero on any build in this project.

### 4.4 Pick a turn to test, then solve

Find a clean two-edge turn between two differently-named streets:

```python
import arcpy
sde = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"
fd = sde + r"\SDEADM.TRNLRS_network"
turns, edges = fd + r"\SDEADM.TRNLRS_traffic_turn", fd + r"\SDEADM.TRNLRS_TRN_STREET"

names = {oid: (nm, geom.trueCentroid)
         for oid, nm, geom in arcpy.da.SearchCursor(edges, ["OID@", "FULL_NAME", "SHAPE@"])}

with arcpy.da.SearchCursor(turns, ["OID@", "Edge1FID", "Edge2FID", "Edge3FID", "SHAPE@"]) as cur:
    shown = 0
    for oid, e1, e2, e3, shp in cur:
        if e3 or e1 not in names or e2 not in names:
            continue
        n1, n2 = names[e1][0], names[e2][0]
        if n1 and n2 and n1 != n2:
            print(f"turn {oid}: {n1}  ->  {n2}   at {shp.trueCentroid.X:.1f}, {shp.trueCentroid.Y:.1f}")
            shown += 1
            if shown >= 10:
                break
```

Pick one you can picture. In Pro, build a **Route** on `TRNLRS_street_network` with a stop
on Edge1 before the junction and a stop on Edge2 after it, then:

1. Solve with the **TrafficTurn** restriction **on** → the route must detour around the
   turn (or fail to solve).
2. Solve with it **off** → the route should go straight through.

Different results between the two = turn restrictions are enforced. Identical results =
they are not, regardless of what the Turns count says.

While you have a Route open, the other two outstanding Phase 5 tests are cheap:

- **One-way**: route both directions along a known one-way street; the wrong-way direction
  must detour.
- **Route comparison**: same two endpoints on `TRNLRS_street_network` and the legacy
  `TRN_street_network`; compare path and length. Pay attention to bridges and underpasses —
  the new network has no elevation modelling, so grade separations are the expected place
  for it to differ.

---

## What to send me

Enough to assess it without a second round trip. In rough priority order:

**Essential**

1. **The full `05_rebuild_traffic_turns` log file** (`logs/<timestamp>_05_*.log`). Not
   excerpts — the DEBUG lines carry the per-reason OID lists and the Edge1End disagreements.
2. **Both `verify_turn_rebuild` runs** — the Phase 0.5 baseline against the current live FC,
   and the Phase 2 run against staging. The baseline is what confirms or refutes the premise
   that QA's turns are broken today.
3. **The `BuildErrors_<guid>.txt` file**, plus the log line naming it so I can confirm the
   GUID matches the run. If it's huge, the line counts are enough:
   `find /c "Cannot find edge element" BuildErrors_*.txt` and
   `find /c "Standalone user-defined" BuildErrors_*.txt`.
4. **The Network Dataset Properties → Sources tab** — screenshot or the counts typed out.
   Specifically the Turns number.

**Also useful**

5. **Feature counts** for `TRNLRS_TRN_STREET`, `TRNLRS_street_junction`,
   `TRNLRS_traffic_turn`, `TRNLRS_street_network_Junctions`. The system junction count is
   the tell for a double build (~15,400 is sane against the old network; 859 or ~30,000 are
   not).
6. **The turn you tested** and what happened both ways — which intersection, which two
   streets, restriction on vs. off.
7. **The `03_create_network_dataset` log**, if anything looked odd during the build.

**If something fails**

8. The exact error text and which phase it happened in. For an `ERROR 001919` or `001395`,
   also say which object it named — that identifies the controller-dataset lock.
9. For verifier failures, the sample OIDs it prints, plus 2–3 of those records' attributes
   (`Edge1FCID`, `Edge1FID`, `Edge1End`, `Edge1Pos`) from the attribute table.

**Questions I can't answer from here**

- Did the Phase 0.5 baseline pass or fail? Either answer is informative; a pass would mean
  the review's central claim is wrong.
- What is the `Edge1Pos` distribution? This is the last open question behind the A1 finding.
- Are Mel's Cogswell ramp turns in `TRN_traffic_turn` (so they survive the remap), or were
  they authored directly against `TRNLRS_traffic_turn` (in which case the swap destroys them
  and the Phase 0.3 backup is how we get them back)?
- Has Robbie's emergency-turnaround question been settled? If ETAs should be excluded, that
  is a filter on the read cursor and is better done before the swap than after.

---

## If it goes wrong

- **Verifier fails in Phase 2** — nothing has been changed yet. Send me the output; the
  staging FC is disposable, delete it and we go again.
- **Build errors still show turn failures in Phase 3** — the network dataset can be
  recreated at any time by re-running script 03, and the pre-swap turn FC is in the Phase
  0.3 backup. To restore: delete the network dataset, delete `TRNLRS_traffic_turn`,
  `CopyFeatures` the backup into the feature dataset under that name, re-run script 03.
- **`ERROR 001919` on a delete** — the network dataset still exists. Delete it first.
- **`ERROR 001395` on a truncate** — you're on a controller-dataset member; `DeleteRows`
  instead. Should not arise in this runbook.
