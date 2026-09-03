# Network Dataset Scripts — Full Review (2026-08-31)

A code-and-docs review of everything used to recreate `TRNLRS_street_network` from LRS
data: scripts `01`–`06`, `run_full_network_rebuild.py`, `log_utils.py`, the
`sync_network_edge_source()` path in `LRS_updates.py`, `data/network_template.xml`, and
the four docs in `docs/`.

Findings are split into **Confirmed** (readable directly from the repo) and **Needs
verification** (requires an arcpy/SDE session, which this review did not have).

**Update 2026-08-31:** findings A1–A4 and B have since been fixed in code, against **QA**.
Each section below is marked accordingly and records what changed. Findings C, D, E, F and
G are still open.

---

## TL;DR

1. **`TRNLRS_TRN_STREET` vs. route intersections: run 2026-08-31, no systematic transform bug
   — but a real, mostly-explained gap and a handful of genuine anomalies.** 249 of the city's
   active route intersections show no aligned edge endpoint; 221 have none at all within 10m.
   The offset vectors point in every direction (no shared direction/magnitude), so this is
   NOT the systematic `OverlayEvents` bug the original 3-spot-check note suggested. Names show
   the bulk is highway ramps/interchanges — an already-known consequence of no elevation
   modelling (grade-separated crossings get flagged as intersections with no street-level
   match). A handful of plain surface-street pairs (e.g. `HEMLOCK DR`/`HIGH TIMBER DR`,
   9m offset) are NOT explained by that and are real candidates for investigation. See
   [A0b](#a0b-junction-alignment-check-run-2026-08-31----grade-separation-not-a-transform-bug-a-handful-of-real-anomalies).
2. **The turn rebuild was broken in Dev and QA for over a month — the remap is now confirmed
   correct and its staging output passes every mechanical check (2026-08-31).** The status
   docs said Phase 5a was ✅ complete as of 2026-07-14, but the code comments added on
   2026-07-21/22 recorded that *every* turn produced by script 05 on that same build had
   actually failed to resolve. Those 2026-07-22 fixes were themselves incomplete (see item 3)
   and were never re-run until today. The rewritten script shows 99.7% Edge1End agreement and
   a healthy 4.0% skip rate against QA; the verifier itself needed the same fix (see
   [A1](#a1-edge1end-is-synthesised-from-edge1pos-rather-than-read-fixed-2026-08-31)'s final
   update) before it could confirm this, but once fixed, all 10 checks on the staging FC pass
   clean — including the previously-flagged duplicate-signature problem (see item 6), which
   turned out not to recur under the rewritten matching logic. Still open: the spatial spot
   checks in `traffic_turn_staging_review_checklist.txt` and the swap (Phase 3) haven't
   happened, so QA's live network dataset still has the old, broken turn FC.
3. **One of those two fixes was incomplete — now fixed.** Script 05 synthesised `Edge1End`
   from `Edge1Pos` instead of reading the value on the source turn FC, and derived it from
   the *old* edge rather than the *new* one. See
   [A1](#a1-edge1end-is-synthesised-from-edge1pos-rather-than-read-fixed-2026-08-31).
4. **`run_full_network_rebuild.py` was wired to two different environments — now fixed.**
   Script 05 was set to QA, script 03 to Dev. Both now point at QA and the orchestrator
   refuses to run if they diverge. See [B](#b-environment-config-drift-fixed-2026-08-31).
5. **The documented rebuild cadence is wrong in a way that will break prod on day one.**
   The migration plan states turns don't need rebuilding on each LRS refresh. They do —
   turn references are edge `OBJECTID`s, and the refresh reassigns them. See
   [D](#d-turn-references-do-not-survive-an-lrs-refresh-structural).
6. **Duplicate/degenerate turn signatures — flagged as a still-open problem, then found not
   to recur under the rewritten script (2026-08-31).** Discovered via locally-held diagnostic
   scripts uploaded the same day: an *older* version of the remap script was collapsing both
   carriageways of a divided road onto a single new edge, turning a legacy "segment A onto
   segment B" restriction into a self-collision. `verify_turn_rebuild.py`'s check 10 was added
   to surface this as a warning. Once run against the *rewritten* script's actual output,
   check 10 came back clean — zero duplicate signatures across 1,189 records. See
   [A0](#a0-duplicate--degenerate-turn-signatures----found-not-to-recur-under-the-rewritten-script-2026-08-31)
   for why, and what's still worth a light follow-up.
7. **`LRS_updates.py` will fail on its first prod run** with `ERROR 001395` — the
   `TruncateTable` fix that landed in script 04 was never ported to it. See [C](#c-lrs_updatespy-will-fail-on-first-prod-run).
8. **QA's network dataset had to be rebuilt from scratch, not from `data/network_template.xml` — done 2026-09-01.** After the swap (Phase 3), `CreateNetworkDatasetFromTemplate` failed with `ERROR 030386`: the template's `Length`/`OneWay` evaluators are VBScript, which ArcGIS Pro 3.5 refuses to build from. Attempting the Esri-documented fix (convert the evaluators to Python in Properties) hit a second wall: Dev's existing network dataset shows "Read-only network dataset" in Properties, and this is confirmed to be Esri's deliberate, one-way behavior for any network dataset with VBScript evaluators opened in Pro 3.4+ — not a lock, Pro-version, project-state, or schema-version issue (all four tested and disproven). There is no documented in-place fix. QA was rebuilt interactively with Python evaluators and **turn restrictions are confirmed enforced**; **`OneWay` is currently broken there** and is the top open item. See [F2](#f2-error-030386--vbscript-evaluators-make-the-network-dataset-permanently-read-only-qas-nd-must-be-rebuilt-from-scratch-not-from-this-template-confirmed-2026-09-01).
9. **`data/network_template.xml` is stale and actively misleading — confirmed 2026-09-01.** Its `OneWay` evaluator is a hardcoded no-op, while the *live* Dev network carries real `STR_DIR`-driven logic (recovered and transcribed in F2). The template was captured in Phase 1 and never re-exported after `OneWay` was fixed directly in Pro's Properties. Anything reasoning from this file about live behavior is reasoning from a stale snapshot — including, initially, this review.

---

## Current status (honest version)

| Area | State |
|---|---|
| Phase 1 — extract old config | ✅ Done (`network_config.json`, `network_template.xml`) |
| Phase 2 — schema comparison | ⚠️ Ran, but the evaluator half never executed — see [E](#e-script-02s-evaluator-cross-check-has-never-actually-run) |
| Phase 3 — XML template edits | ✅ Done (elevation cleared, sources renamed); stale `ClassID`s remain — see [F](#f-template-hygiene) |
| Phase 4 — create + build ND | ✅ **Rebuilt 2026-09-01** via the interactive Python-evaluator wizard procedure in [F2](#f2-error-030386--vbscript-evaluators-make-the-network-dataset-permanently-read-only-qas-nd-must-be-rebuilt-from-scratch-not-from-this-template-confirmed-2026-09-01) — Build Network succeeded with warnings (expected junction warnings + a small known turn-junction gap, see the runbook's Phase 3.3). `data/network_template.xml` still needs to be regenerated from this build via `CreateTemplateFromNetworkDataset` and committed. Dev's ND is untouched and still stuck read-only for the VBScript reason — not part of this fix. |
| Phase 5a — traffic turns | 🔄 **Remap confirmed correct, staging FC verified clean, spatial spot checks passed (2026-08-31/09-01)** — 99.7% Edge1End agreement, 4.0% skip rate, correct DSID, all 10 verifier checks pass including check 10 (zero duplicate signatures — see A0 update), 5 manual spot checks correct including the highest-risk multi-leg intersection. The turn FC itself is proven correct and already swapped into place; **blocked on Phase 4** (no network dataset currently exists in QA to attach it to). |
| Phase 5 — solve tests | 🔄 Properties ✅ (06-26); 50 km service area ✅ (Robbie, 06-29); **turn-restriction solve ✅ (2026-09-01)** — see the runbook's §4.4 for the Travel Mode gotcha this surfaced; **one-way solve ✅ (2026-09-02/03)** — root cause was `Force Full Build` not being checked after evaluator edits, which left precomputed weight tables stale regardless of how correct the evaluator was; see `CLAUDE.md` and `network_build_status.md`'s Step 6 for the full trail, including an 18-hour blocking-session incident on QA's SQL Server; route-comparison / address-range solves **not done** |
| SQL grants | QA ✅ (2026-07-14, `N_3_*` + `ND_38726_*` + 4 source tables + editor writes); **Dev pending**; prod N/A |
| FD separation (`TRNLRS_network`) | ⚠️ Dev + QA populated by script 03's *fallback copy*, not by script 06. Script 06 has never been run anywhere. Duplicate FCs still sitting in `SDEADM.TRNLRS` in both environments. |
| Prod | Nothing built. `TRNLRS_TRN_STREET` exists (created 2026-07-07); no `TRNLRS_network` FD, no ND, no grants, `LRS_updates.py` not deployed. |
| Open data-scope questions from QA (06-29) | ❌ All four still open: transit access roads, water access roads, George's Island, emergency turnarounds |

**Workstream cadence:** the last network-dataset commit was 2026-07-22. The six weeks since
were spent on `TRNLRS_TRN_Safe_School_Streets_VW`. Whoever picks this back up is resuming
cold, into a state where the docs and the code disagree about whether the last step worked.

---

## A0. Duplicate / degenerate turn signatures -- found not to recur under the rewritten script (2026-08-31)

Discovered via diagnostic scripts (`scripts/08_find_duplicate_siblings.py`,
`09_classify_origin_duplicate.py`, `classify_unresolved_turns.py`) and their outputs
(`intermediate_results/*.csv`) that predate A1-A4 and were uploaded to the repo separately.
This is **not** the same bug as A1-A4 -- it only shows up once the OID/FCID/Edge1End-level
failures are fixed and turns actually start resolving, which is exactly why it wasn't visible
earlier: every prior build had turns failing 100% for a more fundamental reason.

**Evidence.** Against an earlier, hand-patched build (`scripts/patch.py`, which recomputed
`Edge1End` in place using the same `Edge1Pos >= 0.5` heuristic A1 identifies as unsound), 1,209
turns produced 1,021 successful builds, 165 `Turn element already exists` failures, and 23
`Cannot find at junction` failures. `turn_review_for_mel.csv` / `intersection_context_check_v2.csv`
show the 165 are pairs of legacy turn records describing what looks like the same U-turn
restriction at a real intersection, each with slightly different measured positions.
`duplicate_turn_siblings.csv` shows the mechanism: both old edges in each pair resolve to the
**same** new edge, because LRS resegmentation merged the two old segments the turn originally
spanned into one new edge -- so "from segment A onto segment B" becomes "from an edge onto
itself" in the new topology, indistinguishable from its sibling. `degenerate_turns_disambiguated.csv`
records an attempt to decide, per pair, whether to keep one canonical record or drop both --
every row is `UNRESOLVED`. This is a domain question (does the restriction mean "no through
movement across the old segment break", now meaningless, or "no U-turn here", still
meaningful?), not something a script should decide unilaterally.

**Expected this to recur under the rewritten script -- it didn't.** The reasoning at the time
was that the cause (resegmentation merging segments) is a property of the *data*, not of which
script produced the remap, so check 10 in `verify_turn_rebuild.py` (added the same day this was
found) was expected to report a comparable pattern. Run against the actual rewritten script 05's
output (1,189 records, post the divided-road junction fix -- see A1's final update), check 10
came back with **zero duplicate signatures**.

**Why, on reflection:** the earlier evidence (165 collisions, `duplicate_turn_siblings.csv`)
was gathered against an *older* version of the remap logic -- one with a materially weaker
candidate-selection method than the current script's tangent-based tie-break, combined
independently with today's divided-road junction fix. Both of those problems shared a root
cause: a poor tie-break when a junction has more than one legitimate nearby candidate. It's
reasonable that fixing that root cause for Edge1End also fixed it for edge selection generally
-- each old edge (e.g. one carriageway of a divided road) is now correctly resolved to its own
distinct new edge, rather than both carriageways collapsing onto the same one. This is direct,
real evidence for this run, not a general proof; `05_rebuild_traffic_turns.py` still has no
explicit deduplication step, so a future dataset or edge case could still produce a collision --
check 10 stays in place to catch it if so.

**Still worth a light follow-up, not blocking:** the domain question in
`degenerate_turns_disambiguated.csv` (whether a restriction spanning a since-removed segment
break should still be represented, e.g. as a self-turn) may now be moot for this dataset if the
rewritten script is correctly splitting those old segments onto distinct new edges -- but the
specific pairs listed in that CSV haven't been individually re-checked against the current
output to confirm that's what's actually happening, as opposed to, say, both simply landing in
one of the 49 skip categories instead. Worth a spot check before fully closing this thread,
but it does not block today's swap decision.

**Still open, separately:** the 23 `Cannot find at junction` failures. `classify_unresolved_turns.py`'s
docstring referenced `junctions.md` and `06_check_junction_alignment.py` -- the latter has
since been uploaded (see [A0b](#a0b-possible-systematic-geometry-offset-in-trnlrs_trn_street-found-2026-08-31-not-yet-run)
immediately below) and is a strong candidate explanation. `junctions.md` itself is still
missing.

---

## A0b. Junction alignment check (run 2026-08-31) -- grade separation, not a transform bug; a handful of real anomalies

`scripts/06_check_junction_alignment.py` compares `TRNLRS_TRN_STREET` edge endpoints against
`SDEADM.INT_RouteOnRoute` (generated independently from `LRSN_Route` geometry via
`GenerateIntersections`) at every active route intersection. It was written because three
hand-picked intersections (Blowers/Barrington, Barrington/Salter, Upper Water/Hollis) showed
the edge source offset from the true crossing point "in a similar direction and magnitude" --
suggestive of a systematic transform bug. **Run city-wide, the result does not confirm that
hypothesis.**

**Result.** Of the active route intersections, 249 have no edge endpoint within 1cm (the
alignment tolerance): 221 have **no edge endpoint at all within the 10m search radius**
(`NO_MATCH`); the other 28 have a nearest endpoint somewhere between 0.03m and 10.0m away.
Read the raw numbers in `docs/turn_rebuild_qa_test_runbook.md` for the exact commands used.

**Not a systematic transform.** The offset vectors on the 28 matched-but-misaligned records
point in every direction with no shared sign or ratio -- e.g. `(-0.445, 9.984)`,
`(-8.973, 2.663)`, `(9.165, -0.516)`, `(-3.612, -7.914)` on the four largest. A coordinate
transform bug would produce the same vector (or a small family of them) repeatedly; this
doesn't. The pooled mean is near `(0, 0)` with a large standard deviation -- consistent with
unrelated small errors cancelling out, not a citywide shift.

**Mostly explained by grade separation, an already-known limitation.** Both the `NO_MATCH`
population and the largest offsets in the matched set are dominated by highway ramps and
interchanges -- `ALM-A RAMP`, `HIGHWAY 102 NB EXIT 4B ... OFF RAMP`, `RAMP MAC-L RAMP,RAMP
MAC-R RAMP`, `HIGHWAY 111 WB EXIT 6 ON RAMP`, repeatedly. This network has no elevation
modelling (`FROM_ELEV`/`TO_ELEV` cleared -- see `network_build_status.md`'s "No elevation
modelling" limitation), and `INT_RouteOnRoute` marks every place two LRS routes cross in the
measure/2D-plane sense with no awareness of grade separation. A highway passing over an
off-ramp gets flagged as an "intersection" even though the streets never meet at ground
level -- `TRNLRS_TRN_STREET` correctly has no shared edge endpoint there. This diagnostic is
quantifying an already-accepted limitation, not surfacing a new one, and does not on its own
justify a change to `OverlayEvents` or `LRS_updates.py`.

**A handful of real, unexplained anomalies remain.** Several of the largest offsets are plain
surface-street pairs with no grade-separation excuse: `HEMLOCK DR`/`HIGH TIMBER DR` (8.7m),
`WRIGHT AVE`/`COUNTRYVIEW DR` (9.36m), `SKREIA RD`/`SAILVIEW LANE` (6.26m), `MASSACHUSETTS
AVE`/`LADY HAMMOND RD` (7.44m). These are genuine candidates for a real defect in
`TRNLRS_TRN_STREET`'s geometry at those specific locations and are worth a manual look in Pro
-- not dismissible as interchange noise.

**Open:** none of the three original spot-check intersections (Blowers/Barrington,
Barrington/Salter, Upper Water/Hollis) appear by name in the 28 matched rows or in a 20-row
sample of the 221 `NO_MATCH` rows. Whether they came in aligned (contradicting the original
spot-check note) or are simply buried in the other ~200 unprinted `NO_MATCH` rows has not been
checked directly.

**Not yet done:**
- Confirm the three original spot-check locations directly by name (a targeted query, not yet
  run).
- Classify the full 249 (not just a 20-row sample of `NO_MATCH`) by an interchange-name
  heuristic (RAMP/EXIT/HIGHWAY/BRIDGE) to quantify what fraction is grade-separation vs. real
  anomaly, rather than judging by eye from a sample.
- Manually review the handful of plain-street anomalies identified above in Pro.

---

## A. Script 05 — `05_rebuild_traffic_turns.py`

## A. Script 05 — `05_rebuild_traffic_turns.py`

This is the script the whole migration is blocked on, so it gets the most attention.

### A1. `Edge1End` is synthesised from `Edge1Pos` rather than read (FIXED 2026-08-31)

**Confirmed from code.** Section 7 builds `read_fields` from the old turn FC as
`SHAPE@`, optional `NODE_`, then `Edge{i}FCID/FID/Pos` per slot, then `OID@`. `Edge1End` is
never read — even though Section 4 already builds `_fld_map` over *every* field on
`OLD_TURN_FC`, so the value is sitting right there. Instead, Section 8 derives it:

```python
edge1_end = "Y" if old_pos is not None and old_pos >= 0.5 else "N"
```

Two independent problems with that derivation:

- **`Edge#Pos` probably does not mean what the script assumes.** In the Esri turn schema,
  `Edge#Pos` identifies *which edge element* of the edge feature the turn uses, expressed as
  the relative position of that element's midpoint along the feature — an edge feature that
  is not split into multiple elements canonically carries `0.5`. It is not "how close the
  junction is to the start of the edge". The template sets `ClassConnectivity = 1`
  (endpoint), so new edge features are not split at interior junctions, which is exactly the
  case where every `Pos` collapses to `0.5`. If the old `TRN_traffic_turn` records also
  carry `~0.5`, then this expression evaluates to `"Y"` for **every** record, and
  `find_new_oid`'s sibling test (`pt = shape.firstPoint if pos < 0.5 else shape.lastPoint`)
  picks `lastPoint` for **every** record. Roughly half of those are the wrong end of the
  edge.
- **Even under the script's own assumption, it is computed from the wrong geometry.**
  `Edge1End` describes which end of the *new* Edge1 the turn passes through. It is computed
  here from the *old* edge's `Pos`. The old and new edge features are different features
  and may be digitised in opposite directions; when they are, the value is inverted.

This matters because the 2026-07-21 comment in this same file identifies an unset
`Edge1End` as *"the confirmed root cause of a total build failure (every remapped turn
failing to resolve)"*. The fix moved it from unset to derived — but the derivation may
still be wrong for most records, which would reproduce the same symptom.

**The 15-minute diagnostic that settles it.** Run against QA before touching anything else:

```python
import arcpy, collections
old_turn = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde\SDEADM.TRN_streets_routes\SDEADM.TRN_traffic_turn"
pos, end, combo = collections.Counter(), collections.Counter(), collections.Counter()
with arcpy.da.SearchCursor(old_turn, ["Edge1Pos", "Edge1End", "Edge2Pos"]) as cur:
    for p1, e1, p2 in cur:
        pos[round(p1, 2) if p1 is not None else None] += 1
        end[e1] += 1
        combo[(round(p1, 2) if p1 is not None else None, e1)] += 1
print("Edge1Pos distribution:", pos.most_common(10))
print("Edge1End distribution:", end.most_common())
print("(Pos, End) pairs      :", combo.most_common(10))
```

- If `Edge1Pos` is overwhelmingly `0.5` → **A1 is confirmed**, the derivation is dead code
  producing a constant, and `Edge1End` must be read from the source (and re-derived against
  the matched new edge). Fix before any further remap run.
- If `Edge1Pos` spreads across `0.0`–`1.0` and correlates with `Edge1End` → the assumption
  holds for this data and only the second problem (old-vs-new geometry) needs fixing.

Either way, **read `Edge1End` from the source turn FC** — it is authoritative and free.

**Fix applied (2026-08-31).** `Edge1Pos` is no longer used to locate anything. The junction
is derived from geometry (see [A2](#a2-junction-identification-is-indirect-and-fragile-fixed-2026-08-31)),
and `Edge1End` is computed from the **matched new** Edge1 via `edge_end_flag()` — `"Y"` if
the junction is at its `lastPoint`, `"N"` if at its `firstPoint` — so a new segment digitised
opposite to the old one gets the correct flag. The source `Edge1End` is now read, but as an
*integrity check*: it is compared against the junction the script derives on the **old**
Edge1, and the agreement rate is logged. Below `MIN_EDGE1END_AGREEMENT` (95%) the script
warns loudly and refuses the automatic swap. The diagnostic above is also folded into the
run itself — `log_source_edge1_distribution()` logs the `Edge1Pos`/`Edge1End` distributions
at startup, so every run carries its own evidence.

`Edge{N}Pos` on the output is written as the constant `NEW_EDGE_POS = 0.5` rather than
copied from the old record, since the old value refers to a different feature and, under
endpoint connectivity, `0.5` is the canonical position of the single element.

**Follow-up bug found and fixed (2026-08-31, same day).** Run against QA, this integrity
check came back at 70.9% (846/1194) — well below the 95% gate. Diagnosis
(`scripts/diagnose_edge1end_disagreement.py`) found 345 of the 348 disagreements shared one
exact signature: Edge1 and Edge2 tied at 0.0m on **both** possible endpoint pairings
simultaneously. That happens when two edges are digitised between the same pair of
cross-street nodes — e.g. the two carriageways of a divided road — and it is a genuine
structural ambiguity: both ends of Edge1 touch Edge2 equally, so no distance-based tie-break
can tell them apart. The old fixed "closest candidate" rule resolved every such tie the same
way regardless of which end a given turn was actually about, and every sampled case showed
that fixed choice disagreeing with the source's own (correct) value.

The turn record's own `SHAPE` is not ambiguous, though — it is a point placed by whoever
authored the turn at the real physical junction, already being read into the cursor to copy
into the output but never used for junction detection. `shared_endpoint()` now takes that
point as a `hint_pt`: with a single candidate the hint is irrelevant; with candidates tied,
the one closest to the turn's own recorded point wins. Verified against the exact reported
pattern (a synthetic couplet reproducing turn 29/30's geometry) — resolves correctly in both
directions. Not extended to junctions beyond the first (3+ edge turns), since Esri's
multipoint-per-junction convention for those hasn't been confirmed against real data.

**Confirmed 2026-08-31, same day, re-run against QA.** Agreement jumped from 70.9% to
**99.7% (1190/1194)** — well above the 95% gate. Only 4 residual disagreements remain (turn
OIDs 417, 693, 3948, 3968), a small enough number to be consistent with genuine legacy
`Edge1End` data errors rather than a remaining algorithmic issue. Skip counts unchanged (49,
same breakdown), DSID correct (`39618`). Gate cleared.

**The independent verifier caught the same bug, unfixed, in itself.** `verify_turn_rebuild.py`
was deliberately never fixed alongside script 05 (Phase 2 hadn't run yet when A1-A4 landed).
Run against the staging FC, its check 9 failed 346 of 1,189 records — because
`junction_between()` has the identical divided-road ambiguity `shared_endpoint()` had, and had
never read the turn's own `SHAPE` to resolve it. Fixed the same way: `SHAPE@` added to the
cursor, `junction_between()` takes an optional `hint_pt`, wired in at the check 9 call site.
Verified against the same divided-road pattern (both digitizing orders, confirming the hint
actually overrides the default rather than coincidentally agreeing with it) and the full
existing test suite (no regression).

**Confirmed 2026-08-31, re-run against QA.** All 10 checks pass clean, including check 9
(346/1,189 → 0). Phase 2 (staging FC verification) is complete.

### A2. Junction identification is indirect and fragile (FIXED 2026-08-31)

`find_new_oid` locates the turn junction by picking one endpoint of the *old* edge based on
`Pos`. A version that does not depend on `Pos` semantics at all:

1. The junction is the endpoint **shared** between old Edge1 and old Edge2 geometry —
   compute it directly, no `Pos` needed.
2. Snap that point into the new-edge endpoint index (as today).
3. For each resolved new edge, set `Edge{i}Pos = 0.5` (single element under endpoint
   connectivity) rather than copying the old value, which refers to a different feature.
4. Set `Edge1End = "Y"` if the junction coincides with the **matched new Edge1's**
   `lastPoint`, `"N"` if its `firstPoint`.

This removes both failure modes in A1 and makes the result independent of how the old FC
happened to encode position.

**Fix applied (2026-08-31).** Implemented as described. `shared_endpoint()` finds the
junction between consecutive old edges; each old edge is resolved to a new one anchored at
the junction where the turn enters it (the exit junction for Edge1); `Edge{N}Pos` is set to
`NEW_EDGE_POS`; `Edge1End` comes from the matched new Edge1. A turn whose consecutive old
edges do not meet end to end is now skipped as `no_shared_endpoint` rather than being
guessed at. `candidate_edges_at()` also searches the 3×3 neighbourhood of grid cells around
the junction and then filters by true distance — a junction landing near a cell boundary
could previously round away from an edge endpoint well within tolerance, producing a false
skip and inflating the skip count the go/no-go decision reads.

### A3. Partially-resolved turns are written as valid (FIXED 2026-08-31)

**Confirmed from code.** In Section 8, only an Edge1 miss sets `valid = False`. A miss on
Edge2–Edge5 writes `[None, None, None]` and continues:

```python
if new_fid is None:
    if i == 1:
        valid = False
        break
    else:
        new_row += [None, None, None]
        continue
```

Two invalid outputs fall out of this:

- A turn whose Edge2 did not resolve is written as a **one-edge turn**. A turn needs at
  least two edges; this will fail at build time.
- A turn whose Edge2 missed but Edge3 matched is written with a **gap** in the edge
  sequence (`Edge2FID = NULL`, `Edge3FID` set). ArcGIS expects Edge1..EdgeN contiguous.

Neither increments `skipped`, so both are invisible to the "1,209 written / 29 skipped
(2.3%)" quality gate the whole go/no-go decision has been resting on — and to the 5%
warning threshold. **The real skip rate is unknown.** Fix: treat a miss on any slot that was
populated in the source as a skip, and count/report per-slot misses separately.

**Fix applied (2026-08-31).** A turn is written only when *every* populated source slot
resolves. Skips are counted by reason and each reason's OID list is logged at DEBUG:

| Reason | Meaning |
|---|---|
| `too_few_edges` | fewer than 2 populated edge slots in the source (a turn needs at least 2) |
| `missing_old_geometry` | a referenced old edge OID has no geometry |
| `no_shared_endpoint` | consecutive old edges do not meet end to end |
| `unresolved_edge` | no new edge coincides with the junction |
| `new_edge_not_spanning` | a matched *middle* edge does not reach both of its junctions — LRS resegmentation split the old edge between them, so no single new edge carries the turn |
| `edge1end_undetermined` | the junction is at neither end of the matched new Edge1 |

Source slots are also read up to the first empty one, so a gap in the source is never
carried into the output. **Expect the reported skip count to rise** relative to the 2.3%
from 2026-07-13 — that number was measuring only Edge1 misses. The new number is the real
one, and the per-reason breakdown says whether it is tolerable.

### A4. Angle tiebreaker uses the old edge's chord, not its local tangent (FIXED 2026-08-31)

The multi-candidate tiebreaker compares the direction `junction → other endpoint` of the
*whole old edge* against the same for each candidate new edge. LRS resegmentation makes new
edges much shorter than old ones, so on a curved or long old street the old chord bearing
can differ substantially from the true bearing at the junction, and the nearest-angle
candidate can be the wrong leg. Using the first/last **vertex pair** (i.e. the tangent at
the junction) on both sides would compare like with like. Flagged in the staging checklist
as "highest-risk area" — this is why.

**Fix applied (2026-08-31), alongside A2.** `tangent_at()` returns the bearing from the
junction to the first vertex more than `SNAP_TOLERANCE` away, on both the old and the
candidate new edge, so like is compared with like. This came with A2 rather than separately:
resolving an edge at a junction needs a candidate-selection rule regardless, and the chord
version was not fit for it.

### A5. Minor

- ~~`ZeroDivisionError` if `total == 0` at `if skipped / total > 0.05` in the
  `AUTO_SWAP_AND_REBUILD` block (Section 10).~~ **Fixed 2026-08-31** — the swap block now
  guards `total == 0`, and additionally refuses to swap when the Edge1End agreement rate is
  below threshold.
- ~~The header comment says the Dev config is "Active by default" and QA is commented out.~~
  **Fixed 2026-08-31** — the config block now labels QA as active, matching the code.
- ~~The Section 4 validation comment still says *"the FCID lookup now reads from
  network_template.xml"*.~~ **Fixed 2026-08-31** — that comment and the matching claim in
  `run_full_network_rebuild.py`'s docstring now describe the DSID approach.

---

## B. Environment config drift (FIXED 2026-08-31)

**Confirmed from code.** Every script carries its own manually-edited connection constant,
and they currently disagree:

| Script | Active environment |
|---|---|
| `01_extract_network_config.py` | QA |
| `02_compare_schemas.py` | QA |
| `03_create_network_dataset.py` | **Dev** (`SDE_CONNECTION_UPDATE`) + prod (read-only, edge source) |
| `04_sync_and_rebuild_network.py` | prod only (by design) |
| `05_rebuild_traffic_turns.py` | **QA** |
| `06_migrate_network_fd.py` | Dev (hardcoded) |

`run_full_network_rebuild.py` takes the turn/edge/network paths from `mod05` and then calls
`mod03.main()`, which uses **its own** `FEATURE_DATASET` built from `mod03`'s constant. As
committed, running the orchestrator would: remap turns in QA → delete QA's network dataset →
swap QA's turn FC → then create and build a network dataset **in Dev**. The Dev build would
also silently succeed, because script 03 skips copying source FCs that already exist.

This has been on the open-questions list since 2026-07-07 ("consider replacing the manually
edit the active connection constant pattern with an `--env` flag"). The orchestrator turns
it from a papercut into a data-integrity hazard.

Related: `run_full_network_rebuild.py` also assumes `mod05.AUTO_SWAP_AND_REBUILD is False`.
If someone leaves it `True`, script 05 performs its own swap, the orchestrator then finds no
staging FC, and reports *"05 did not complete successfully"* — misleading, though it does
fail safe.

**Fix applied (2026-08-31).** Script 03's `SDE_CONNECTION_UPDATE` now points at **QA**,
matching script 05, and both config blocks say so with a cross-reference to the other
script. `run_full_network_rebuild.py` gained `check_environments_agree()`, called
immediately after both modules load and before any work: it compares
`os.path.join(mod05.SDE, mod05.NETWORK_FD)` against `mod03.FEATURE_DATASET` (normalised for
case and separators) and exits with both paths printed if they differ, and it also refuses
to run when `mod05.AUTO_SWAP_AND_REBUILD` is `True`.

Scripts 01, 02 and 06 keep their own constants and are unchanged — none of them is invoked
by the orchestrator, so they cannot produce the split-environment failure. The broader fix
(a single shared env module or an `--env` flag) is still worth doing and remains on the
list; this closes the hazard the orchestrator created.

---

## C. `LRS_updates.py` will fail on first prod run

**Confirmed from code.** `sync_network_edge_source()` (line ~528) calls `append_feature()`
(line ~720), which does:

```python
arcpy.TruncateTable_management(target_feature)
```

`TRNLRS_TRN_STREET` is a registered edge source of `TRNLRS_street_network`, i.e. a
controller-dataset member. Per `CLAUDE.md` and commit `b441b58`, `TruncateTable` raises
`ERROR 001395: Operation not supported on a feature class in a controller dataset`. Script
04 was fixed to use `DeleteRows`; **`LRS_updates.py` was not**. It has not surfaced only
because `LRS_updates.py` has never been deployed to prod. It will fail on the first run
after deployment.

Two further problems in the same helper, both specific to the FD copy:

- `append_feature` rebinds the target as
  `target_feature = os.path.join(sde_conn, arcpy.Describe(target_feature).name)` — dropping
  the feature dataset from the path. That is fine for the standalone FCs it was originally
  written for, but `TRNLRS_TRN_STREET` lives *inside* `SDEADM.TRNLRS_network`, and a feature
  class inside a feature dataset is not addressable at the workspace root in an enterprise
  geodatabase. **Needs verification**, but likely a second failure immediately after the
  first is fixed.
- `LRS_VIEW_NAME = "TRNLRS_TRN_street_VW"` is unqualified and mixed-case, so it resolves
  only when connected as `SDEADM`. True today (`SDEADM_RW`), but brittle.

Recommendation: don't reuse `append_feature()` here. Have `sync_network_edge_source()` call
`sync_and_rebuild()` from script 04 directly — that function is already correct, already
prod-scoped, and already logs. One import removes three bugs and the duplication.

---

## D. Turn references do not survive an LRS refresh (STRUCTURAL)

`docs/network_dataset_migration_plan.md` (Rebuild Cadence) states:

> **Note:** the traffic turn FC (`TRNLRS_traffic_turn`) does not need to be rebuilt on each
> LRS refresh -- turn restrictions are maintained separately from the street LRS pipeline
> and only need to be rebuilt if the turn source itself is updated.

**This is incorrect, and it is the single biggest gap between the current design and a
working prod cutover.** Chain of reasoning, each link established elsewhere in this repo:

1. `Edge{N}FID` stores the **`OBJECTID`** of a feature in the edge source
   (`network_traffic_turns.md`, root-cause section — this is the entire reason script 05
   exists).
2. `TRNLRS_TRN_STREET_VW` is *"truncated and repopulated on every LRS refresh run"*
   (`CLAUDE.md`).
3. The sync into the FD copy is `DeleteRows` + `Append(schema_type="NO_TEST")` (script 04)
   — `OBJECTID` is a database-managed field and is not carried across by `Append`; every row
   gets a fresh one.

So after each LRS refresh, the segment ↔ `OBJECTID` mapping the turn FC depends on is gone,
and `BuildNetwork` re-emits `Cannot find edge element corresponding to turn identifier 1`
for all 1,209 turns — the exact regression this project has already chased three times. The
steady-state pipeline as designed re-creates the bug on every run.

`Edge{N}FCID` is safer but not free: it holds the edge FC's `DSID`, which survives
`DeleteRows`/`Append` (the FC object persists) but **changes whenever the FC itself is
recreated** — script 03's fallback copy, script 06's move, or any manual drop/recreate. That
invariant is worth stating explicitly in the docs: **re-run script 05 after anything that
recreates `TRNLRS_TRN_STREET`, not just after edge geometry changes.**

Three ways out, to be decided before prod cutover:

1. **Remap every cycle.** Make `04`/`LRS_updates.py` run the full
   `05 → swap → 03 (recreate + build)` sequence rather than `sync → BuildNetwork`.
   Correct with today's tooling; expensive (deletes and recreates the ND on every LRS
   refresh, which also invalidates the SQL grants every time — see the permissions doc) and
   it re-runs a best-effort spatial heuristic unattended, on a schedule, with nobody
   reviewing the skip counts.
2. **Make edge `OBJECTID`s stable.** Replace truncate/reload with a keyed update
   (insert/update/delete against a stable business key — `FDMID` plus measures) so
   `OBJECTID`s persist across refreshes. Larger change to `LRS_updates.py`, but it is the
   only option that makes turns durable, and it would benefit any other consumer that holds
   references into this FC.
3. **Store turns against a stable key and regenerate.** Persist each restriction as
   street identity + junction point (not `OBJECTID`s) in a side table, and derive
   `Edge{N}FID/FCID/Pos` from geometry on each build. Most work up front; makes the turn
   source a durable asset rather than derived data that must be re-derived correctly every
   time.

This decision also determines whether hand-authored turns are safe: **Mel's Cogswell ramp
turns** (noted in `run_full_network_rebuild.py`) and any turn edits made through the editor
role granted on 2026-07-14 live only in the FC. Under option 1 they survive only because
they are carried through the remap from the *old* turn table; anything authored directly
against `TRNLRS_traffic_turn` is destroyed by the next swap. That should be written down
before more manual turn editing happens.

---

## E. Script 02's evaluator cross-check has never actually run

**Confirmed from code + data.** Script 01 writes each evaluator as:

```json
{"source": "...", "edge_direction": "...", "evaluator_type": "Field", "data": "[STR_DIR]..."}
```

Script 02's `map_evaluator_fields()` reads `ev.get("field_name")` and `ev["element_type"]` —
neither key exists. `field_ref` is therefore always `""`, every evaluator hits the
`if not field_ref: continue` guard, and the function returns `[]`. That is why
`data/evaluator_field_map.json` is `[]`. (Had the guard not fired first, `ev["element_type"]`
would have raised `KeyError`.)

`docs/network_build_status.md` explains the empty file as:

> `evaluator_field_map.json` is empty because the existing evaluators use VB Script
> expressions, not direct field evaluators.

`data/network_config.json` contradicts this: all four Length/OneWay evaluators are
`"evaluator_type": "Field"`. The file is empty because of a key mismatch, not because of
evaluator type.

The *conclusion* still holds — the expressions reference `[SHAPE.STLength()]` and
`[STR_DIR]`, both present and unchanged in the new source — but it was reached by hand, not
by the script. The automated safety net is dead, and it is precisely the check that should
catch a regression when `E_SpeedLimit` / a `TravelTime` attribute is added later.

Fix: extract bracketed field references out of `data` and test each against the new source:

```python
field_refs = re.findall(r"\[([A-Za-z0-9_.()]+)\]", ev.get("data") or "")
```

---

## F. Template hygiene (`data/network_template.xml`)

- **Stale `ClassID`s.** The template still carries the *old* network's dataset IDs:
  `7134` (edge), `7135` (junction), `7137` (turn), `7292` (system junctions), plus
  `<DSID>7293</DSID>` for the ND itself — while every `<Name>` has been updated to the
  `TRNLRS_*` FCs. Builds succeed, so `CreateNetworkDatasetFromTemplate` is evidently
  resolving sources by `<Name>` and reassigning IDs. Worth confirming and writing down,
  because `7134` is the exact number that muddied the 2026-07-14 diagnosis (it appeared in
  `EDGE1FCID` and in the template, and was read as corroboration).
- **`<ID>2</ID>`** on the edge source is the source *ordering index* — the "2" that cost a
  full day on 2026-07-21. That finding currently lives only in a code comment in script 05.
  It belongs in the docs.
- **`DefaultOutputLengthUnits = esriNAUMiles`.** Inherited verbatim from the legacy network.
  HRM is metric; directions output will report miles. Cheap change to `esriNAUKilometers` —
  worth a confirm with Robbie/Mel rather than a silent edit.
- **`network_config.json` understates the directions config.** Script 01's
  `describe_directions()` reads `getattr(d, "fieldMappings", [])`, which is not an arcpy
  attribute, so it always records `directions_field_mappings: []`. The mappings do exist and
  are correct in the template (`StreetNameFieldName=STR_NAME`, `SuffixTypeFieldName=STR_TYPE`,
  `FullNameFieldName=FULL_NAME`) and the 06-26 properties check verified them in Pro.
  Cosmetic, but the JSON is the thing people grep.

---

## F2. ERROR 030386 — VBScript evaluators make the network dataset permanently read-only; QA's ND must be rebuilt from scratch, not from this template (confirmed 2026-09-01)

**What happened:** after the turn FC swap (Phase 3.1) succeeded on QA, `03_create_network_dataset.py`
failed at `CreateNetworkDatasetFromTemplate` with `ERROR 030386` ("Cannot create a network
dataset from a template that uses ... evaluators configured with VBScript"). Trying the
Esri-documented fix — convert the evaluators to Python via Properties → Travel Attributes,
rebuild, re-export the template — hit a second, harder wall on Dev's *existing* (still-built)
`TRNLRS_street_network`: Properties opens showing "Read-only network dataset." with no
Evaluators tab, on every environment tried.

**Root cause, read directly out of `data/network_template.xml`:** only two attributes actually
use a scripted (VBScript) evaluator — `NetworkEvaluatorCLSID {68055FC4-37D5-4BD0-81A5-CD177A29759C}`
(Field Script). Everything else (junction/edge/turn defaults, `TrafficTurn`) uses the Constant
evaluator (`{318C4B91-F5D2-467A-996C-0AB51B0D8FF2}`), which is not VBScript and is not affected.
The two real ones, exact current content:

| Attribute | Direction | Expression | PreLogic |
|---|---|---|---|
| `Length` | Along Digitized | `[SHAPE.STLength()]` | *(empty)* |
| `Length` | Against Digitized | `[SHAPE.STLength()]` | *(empty)* |
| `OneWay` | Along Digitized | `restricted` | `restricted = False` |
| `OneWay` | Against Digitized | `restricted` | `restricted = False` |

**Side finding — CORRECTED 2026-09-01, read this before acting on the table above.** The
`OneWay` PreLogic in `data/network_template.xml` unconditionally sets `restricted = False` and
never references `STR_DIR`. My initial reading of that was "the live network doesn't enforce
one-way at all" — **that was wrong**, and the error mattered, because the like-for-like rebuild
faithfully reproduced the no-op into QA's new network.

`network_dataset_migration_plan.md`'s 2026-06-26 properties check recorded `OneWay` as
"Field Script (VB) on Along/Against referencing `STR_DIR` — correct", i.e. the *live* network
had real logic the template did not. Recovering Dev's live template on 2026-09-01
(`CreateTemplateFromNetworkDataset`, which succeeded on Pro 3.5.8 despite Esri's KB saying it
fails on VBScript-bearing networks) confirmed it:

```vbscript
' Along Digitized                          ' Against Digitized
restricted = False                          restricted = False
Select Case UCase([STR_DIR])                Select Case UCase([STR_DIR])
  Case "N", "FDTO", "T": restricted = True    Case "N", "FOTD", "T": restricted = True
End Select                                  End Select
```

`FDTO` blocks travel along the digitized direction, `FOTD` blocks travel against it, and `N`
or `T` block both (a fully closed segment). **The lesson for this repo: `data/network_template.xml`
is not a trustworthy record of what the live networks actually do.** It was captured in Phase 1
and never re-exported after someone fixed `OneWay` directly in Pro's Properties dialog. Treat
the live network — or a fresh `CreateTemplateFromNetworkDataset` export — as authoritative, not
the committed file.

**Why Dev's ND is read-only — confirmed against Esri's own documentation, not a guess:**
`support.esri.com` knowledge base 000034955 ("Deprecation: VBScript Evaluators in ArcGIS
Network Analyst") and FAQ 000034321 state that **starting in ArcGIS Pro 3.4, a network dataset
carrying VBScript-based Field/Element Script evaluators becomes permanently non-editable
through Properties — not just the evaluators, anything — until the evaluators are converted to
Python.** This is a deliberate one-way gate Esri built when deprecating VBScript, and it
explains every symptom observed, which is why four different hypotheses tried in sequence
during this session were each tested and confirmed wrong:

| Hypothesis | Test | Result |
|---|---|---|
| Stale lock / session | Restarted Pro, closed PyCharm; checked Geodatabase Administration → Locks | Disproven — 0 of 192 locks |
| Pro-version-specific (3.5 only) | Reproduced on a Pro 3.3 client against the same SDE instance | Disproven — identical behavior |
| Network dataset/layer loaded elsewhere in the project | Retried from a fresh, blank project | Disproven — still read-only |
| Old schema version | Ran `arcpy.management.UpgradeDataset` | Disproven — `ERROR 001266: The dataset is already upgraded` |

**There is no documented in-place fix.** The only remediation Esri publishes for `ERROR 030386`
is to convert the evaluators to Python and rebuild — but that requires Properties, which the
existing VBScript content has already locked. Esri's support content does not describe an
escape hatch for a network dataset that reached Pro 3.4+ already carrying VBScript evaluators
beyond building a new one.

**Path forward (not yet executed):**
1. Do not keep trying to unlock Dev's existing ND — treat the read-only state as permanent.
2. Since QA's ND is already deleted, build its replacement via Pro's **New Network Dataset**
   wizard (interactive), not `CreateNetworkDatasetFromTemplate` against the current XML —
   that would immediately reproduce `ERROR 030386`.
3. In the wizard, assign `Length` and `OneWay` as **Python** Field Script evaluators.
   `Length` → Value `!Shape!` (Pro's own auto-generated form for a Length cost attribute;
   equivalent to `[SHAPE.STLength()]` under this network's meter-based spatial reference).
   `OneWay` → **use the recovered `STR_DIR` logic in the corrected side finding above**, not
   the template's no-op. The correct Python structure is a function in the **Code Block** that
   receives the field as a parameter, called from the **Value** line:

   ```python
   # Code Block
   def oneway_restricted(str_dir):
       restricted = False
       if (str_dir or "").upper() in ("N", "FDTO", "T"):   # "FOTD" for Against Digitized
           restricted = True
       return restricted

   # Value
   oneway_restricted(!STR_DIR!)
   ```

   Use the function/Value form above rather than `!STR_DIR!` written inline directly inside the
   Code Block — the function/Value split is the standard, documented ArcGIS pattern. **More
   important than the exact syntax: after editing this evaluator, `Build Network` must be run
   with "Force Full Build" checked.** Without it, the network's precomputed per-edge weight
   tables stay stale and the edit has zero effect — with no build error and no warning of any
   kind. This was the actual root cause of a full day (2026-09-01/02) where `OneWay` appeared
   completely broken regardless of how the evaluator was written, including a version
   hardcoded to unconditionally `return True` that still produced no restriction anywhere
   until Force Full Build was used. Full trail in `CLAUDE.md` and
   `network_build_status.md`'s Step 6. **Always verify a restriction evaluator with a real
   two-direction solve after a Force Full Build** — never trust a clean build message alone,
   per the runbook's §4.4.
4. Match sources (`TRNLRS_TRN_STREET` edge, `TRNLRS_street_junction` junction,
   `TRNLRS_traffic_turn` turn) and connectivity settings to the values already recorded in
   `data/network_template.xml`.
5. `BuildNetwork` (Force Full Build), then export the corrected template with
   `CreateTemplateFromNetworkDataset` and commit it over `data/network_template.xml`, so
   `03_create_network_dataset.py` can
   reproduce this network going forward without ever touching VBScript again.
6. Resume the runbook at Phase 4 (post-build) — the turn FC itself needs no further work.

---

## G. Documentation drift

The docs are the main artifact this project hands to the next person, and several of them
now actively mislead:

| Item | Problem |
|---|---|
| `docs/traffic_turns.md` | **Does not exist.** Referenced from `05_rebuild_traffic_turns.py` (twice, including *"See traffic_turns.md for the full diagnosis"* of the DSID and `Edge1End` findings) and from `run_full_network_rebuild.py`. The actual file is `docs/network_traffic_turns.md` — which does **not** contain that diagnosis. |
| `network_review.md` | **Does not exist.** Referenced from `network_dataset_migration_plan.md` for the full QA review notes. Never committed. |
| The 2026-07-21/22 work | The two most consequential fixes in the project (FCID→DSID, `Edge1End`) exist only as inline comments. No doc, no status-table update, no log. |
| `traffic_turn_staging_review_checklist.txt` §2 | ~~Says *"Edge1FCID should equal the FCID logged during the run (2, for TRNLRS_TRN_STREET)"* — now exactly inverted.~~ **Fixed 2026-08-31**, along with the `Edge{N}Pos` carry-over check, which the rewrite also invalidated. The rest of the checklist (counts, spatial spot checks, skipped-turn assessment, ETAs) still stands. |
| `network_build_status.md` Phase 5a | `✅ Complete (2026-07-14)`. The 07-21 finding says that build's turns all failed. Should be walked back to ⚠️. |
| `run_full_network_rebuild.py` docstring | *"05 has since been patched to read the FCID from network_template.xml"* — superseded by the DSID fix committed 27 minutes earlier. |
| Solve-test status | `network_dataset_migration_plan.md` records a service area solve ✅ (06-29); `network_build_status.md` lists all solve tests as pending. Reconcile. |
| `network_traffic_turns.md` | ~600 of its 934 lines are a raw chat transcript containing three superseded versions of the remap script inline, including the original naive `candidates[0][0]` version. Someone will copy the wrong one. Worth reducing to the diagnosis + current procedure. |
| `README.md` | Advertises `tests/`. There is no `tests/` directory and no test of any kind. |

---

## H. Recommended next steps, in order

1. ~~Run the `Edge1Pos`/`Edge1End` diagnostic against QA.~~ **Done differently
   (2026-08-31)** — folded into script 05 itself as `log_source_edge1_distribution()`, so
   the first run produces the evidence. Read those two lines in the log before trusting
   anything else in the run.
2. ~~Fix script 05 ([A1](#a1-edge1end-is-synthesised-from-edge1pos-rather-than-read-fixed-2026-08-31)–[A3](#a3-partially-resolved-turns-are-written-as-valid-fixed-2026-08-31)).~~
   **Done 2026-08-31.** Not yet run.
3. ~~Fix the environment mismatch ([B](#b-environment-config-drift-fixed-2026-08-31)).~~ **Done 2026-08-31** — both
   scripts on QA, orchestrator asserts.
4. ~~Run the cycle in QA and actually verify the result.~~ **Done 2026-08-31 / 09-01.**
   1,189 turns written, 99.7% Edge1End agreement, all 10 verifier checks clean, 5 spatial spot
   checks correct, 1,180 built as live turn elements, and a Route solve through a known
   prohibited turn correctly refused. Phase 5a is complete for QA.

**Re-ordered 2026-09-01 — the list below is the current priority order:**

5. **Fix QA's `OneWay` evaluator and verify it with a solve.** Corrected Python is in
   [F2](#f2-error-030386--vbscript-evaluators-make-the-network-dataset-permanently-read-only-qas-nd-must-be-rebuilt-from-scratch-not-from-this-template-confirmed-2026-09-01);
   apply it, rebuild, then re-run the eastbound Bishop St test. Everything downstream
   (template export, Dev, prod) depends on this being right, because it gets baked into the
   template everything else is built from.
6. **Run `SELECT DISTINCT STR_DIR, COUNT(*)` against `TRNLRS_TRN_STREET`** (gap #14) before
   trusting one-way enforcement — the evaluator only handles four codes and nobody has
   confirmed those are the only ones in the data.
7. **Export the corrected template and commit it over `data/network_template.xml`**, then
   confirm `03_create_network_dataset.py` can actually rebuild from it (gap #13). Until this
   works, there is no automated rebuild path and the LRS-refresh automation story is broken.
8. **Rebuild Dev the same way** (gap #16) — and do it before anything happens to Dev's network
   dataset, because it is currently the only surviving copy of the original VBScript logic.
9. **Re-apply Dev's SQL grants** (still pending since 07-14) using the procedure in
   `network_dataset_sql_permissions.md`.
10. **Decide the OID-stability question ([D](#d-turn-references-do-not-survive-an-lrs-refresh-structural))** — it changes what `04` and
   `LRS_updates.py` have to do, so it gates prod cutover.
11. **Fix `LRS_updates.py` ([C](#c-lrs_updatespy-will-fail-on-first-prod-run))** before deploying to prod.
12. **Finish the remaining Phase 5 solve tests** (route comparison, address ranges).
13. **Chase the four open data-scope questions** with Robbie/Mel — transit access roads,
   water access roads, George's Island, emergency turnarounds. Open since 06-29; the ETA
   answer changes what the turn FC should contain, so it is upstream of any final turn
   rebuild. **Also ask about Mel's Cogswell ramp turns (gap #7)** — the 09-01 swap recreated
   the turn FC again, so if those were authored directly against `TRNLRS_traffic_turn` they
   are gone.
14. **Decide on the 9 build-rejected turns** (gaps #11/#12) — snap the 7 real gaps, tighten
   the tolerance, or accept 0.76% unenforced.
15. **Doc cleanup ([G](#g-documentation-drift)), script 02's evaluator fix ([E](#e-script-02s-evaluator-cross-check-has-never-actually-run)), template units ([F](#f-template-hygiene)).**

---

## I. Knowledge gaps — what could not be determined from the repo

These are the things blocking a confident read of where the project actually stands. Most
need one arcpy session against QA.

1. ~~Esri's `Edge#Pos` / `Edge1End` semantics as they apply to this data.~~ **Resolved
   2026-08-31** — see [A1](#a1-edge1end-is-synthesised-from-edge1pos-rather-than-read-fixed-2026-08-31):
   the rewritten script 05 no longer depends on `Edge#Pos` for junction detection at all.
2. **Were the 2026-07-22 fixes ever run?** No evidence either way. `logs/` is gitignored and
   runs write to a network share (`\\msfs203...\network_dataset\logs\`). Check for a log
   file dated after 2026-07-22.
3. **The actual current state of the Dev and QA turn FCs.** What are their `Edge1FCID`
   values (`2`, or a real DSID)? What does the ND Properties Sources tab report for Turns?
   What does the newest `BuildErrors_<guid>.txt` contain?
4. **Does `Append` reassign `OBJECTID`s in this pipeline?** Confident it does — the D chain
   depends on it. Confirmable in one pass: record a few `FDMID → OBJECTID` pairs, run
   script 04, compare.
5. **Has `TRNLRS_TRN_STREET`'s DSID changed** since the turn FCs were last written? If yes,
   every `Edge{N}FCID` in them is already stale regardless of everything else.
6. **Robbie's traffic turn notes.** Promised at the 06-29 QA session, never received per the
   docs. The ETA (emergency turnaround) scope question is still unanswered and is upstream
   of finalising the turn source.
7. **Mel's hand-authored Cogswell ramp turns** — are they in the old `TRN_traffic_turn`
   (and therefore carried through each remap), or authored directly against
   `TRNLRS_traffic_turn` (and therefore destroyed by each swap)?
8. **Prod topology and ownership.** Does `SDEADM.TRNLRS_network` exist in prod? Who owns
   the cutover window, and what is the rollback if the new ND misroutes? The old
   `TRN_street_network` is still live and untouched, which is the de facto rollback — worth
   confirming it stays that way through cutover.
9. **Consumers of `TRNLRS_TRN_STREET_VW`.** The impact assessment for eliminating the
   two-copy arrangement (open since 06-26) has never been done, and it gates the cleanest
   long-term fix for both [C](#c-lrs_updatespy-will-fail-on-first-prod-run) and [D](#d-turn-references-do-not-survive-an-lrs-refresh-structural).
10. **No regression coverage.** There is no test that would have caught any finding in this
    review. A small harness that, post-build, asserts (a) turn count > 0 in ND properties,
    (b) zero turn errors in the build errors file, and (c) a known prohibited turn is
    actually refused by a Route solve would have caught the 07-07, 07-14 and 07-21
    regressions at the point they happened rather than weeks later.

### Gap status as of 2026-09-01

Several of the above closed during the QA rebuild; new ones opened. Current picture:

**Closed**

| Gap | Answer |
|---|---|
| #3 — state of QA's turn FC / Turns count / build errors | `Edge1FCID = 39618` (a real DSID, not `2`). ND Properties reports **Turns: 1,180**. Build errors: 1,048 harmless standalone-junction warnings + 9 `Cannot find at junction` (see below). |
| Do turn restrictions actually work? | **Yes, confirmed by solve** — but only once the Travel Mode enables them. |
| What is the real `OneWay` logic? | Recovered from Dev — `FDTO`/`FOTD`/`N`/`T` semantics, transcribed in [F2](#f2-error-030386--vbscript-evaluators-make-the-network-dataset-permanently-read-only-qas-nd-must-be-rebuilt-from-scratch-not-from-this-template-confirmed-2026-09-01). |
| Is `data/network_template.xml` an accurate record? | **No.** Stale since Phase 1; missing the real `OneWay` logic entirely. |

**Still open, unchanged:** #2 (were the 07-22 fixes ever run — now moot, superseded by the
09-01 rebuild), #4 (does `Append` reassign OBJECTIDs), #5 (DSID stability), #6 (Robbie's turn
notes / ETA scope), #7 (Mel's Cogswell ramp turns — **now more urgent**, since the 09-01 swap
destroyed and recreated the turn FC again), #8 (prod topology/ownership), #9 (consumers of
`_VW`), #10 (no regression coverage).

**Newly opened 2026-09-01**

| # | Gap | Why it matters |
|---|---|---|
| 11 | **9 turns rejected at build with `Cannot find at junction`.** 7 explained: script 05's `SNAP_TOLERANCE = 0.5` is looser than the network's build-time XY tolerance (`0.001`), so genuine 0.006–0.41 m gaps in `TRNLRS_TRN_STREET` pass the remap but fail the build. **2 are unexplained** — an exact 0.0000 m coincidence that still failed. | Small (0.76% of turns unenforced) but the 2 unexplained ones mean the failure mode isn't fully understood. Worth checking whether a third turn referencing the same shared edge is the real culprit. |
| 12 | **Is the `SNAP_TOLERANCE` / build-tolerance mismatch worth fixing?** Options: tighten the script (rejects more turns), snap the 7 real gaps in the edge source (surgical, ~7 vertices), or accept it. | Recurs on every rebuild. Nobody has decided. |
| 13 | **Can `03_create_network_dataset.py` rebuild from a Python-evaluator template at all?** `CreateNetworkDatasetFromTemplate` has never been run against one in this project. | If it can't, the automated rebuild path stays broken and every future rebuild needs the manual wizard — which also breaks the LRS-refresh automation story. |
| 14 | **What is `STR_DIR`'s full domain?** Only the four codes the evaluator tests for are known. If other one-way codes exist in the data, they're silently unrestricted today. | A `SELECT DISTINCT STR_DIR, COUNT(*)` against `TRNLRS_TRN_STREET` answers it in seconds and should be run before trusting one-way enforcement. |
| 15 | **Are `N` and `T` (both-directions-blocked) intentional?** Fully closed segments are plausible but unverified with the data owner. | If wrong, the rebuilt network inherits a bug from the legacy one. |
| 16 | **Dev has no migration path yet.** It is still VBScript, permanently read-only, and cannot be rebuilt from the stale template either. | Dev is now behind QA and will need the same from-scratch treatment. Its live network is currently the *only* place the original VBScript logic exists. |
