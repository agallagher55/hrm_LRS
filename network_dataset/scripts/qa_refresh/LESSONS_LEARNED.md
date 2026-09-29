# QA Refresh — Lessons Learned (2026-09-18 session)

Working notes from actually running the full `qa_refresh` workflow end to end
against QA on 2026-09-18: path fix through turn remap, swap, rebuild, SQL
grants, smoke tests, and a template-automation follow-up. Read this before
your next QA refresh — several of these are easy to repeat if you don't know
to look for them. `README.md` in this folder is the step-by-step procedure;
this file is the accumulated "watch out for" knowledge that doesn't fit there.

> **Status note (2026-09-29):** the 2026-09-18 sections below describe a run that needed the
> interactive network recovery. That is no longer the normal path: on 2026-09-29 the committed
> template created and built by script once the stale T: copy was replaced. Read the
> "2026-09-29" sections at the end of this file first, and treat the interactive-recovery notes
> as fallback history.

## Repo hygiene — resolved this session

A second, stale copy of this entire folder existed at
`network_dataset/qa_refresh/` (one level up from this file, missing the
`scripts/` component). It predated the `89b6d43` "Derive QA refresh paths
from actual folder layout" fix and still contained the *broken* `_shared.py`
(`path = path.resolve()`) and `config.py`
(`CORE_SCRIPTS_DIR = NETWORK_DATASET_DIR / "scripts"`) — the exact
doubled-`scripts\scripts\` bug this session started with. Nothing in the repo
referenced that path, so it was fully orphaned. **Deleted 2026-09-18.** If a
similarly-named folder ever reappears at `network_dataset/qa_refresh/`
(rather than `network_dataset/scripts/qa_refresh/`), treat it the same way —
never edit or run scripts from it.

## Deployment drift (T: drive vs. this repo)

The session's opening bug (doubled `scripts\scripts\` path, `ERROR: Required
script not found`) turned out to be a stale **deployed** copy on
`T:\work\giss\monthly\<month>\<user>\...` predating a repo fix, not a live
repo bug. `config.py`/`_shared.py` on T: had literally different code
(`path.resolve()` present, `CORE_SCRIPTS_DIR` computed differently) from what
was committed. **Before debugging a qa_refresh script as if it's broken,
diff the deployed T: copy against this repo's version of the same file** —
it's cheap and would have saved real time this session.

## `03_create_network_dataset.py` / interactive network creation

- **`copy_fc_to_fd()` only checks `arcpy.Exists(dest)`.** If the destination
  FC already exists for *any* reason — including an incomplete prior cycle,
  not just a properly-finished one — it silently skips copying with a log
  line that's easy to miss: `"...skipping copy... was NOT refreshed"`. This
  is by design (idempotent reruns), but it means step 03 can silently build
  on stale QA data if step 02 wasn't actually run or didn't finish. **After
  seeing that log line, verify the QA edge FC's row count against Prod's
  current `TRNLRS_TRN_STREET_VW`** before trusting the rest of the pipeline. Since
  2026-09-29 the copy is expected to be *smaller* by the WA/island exclusions in
  `network_exclusions.py`; the skip path now also warns if the stale copy still holds
  excluded rows.
- **The "Create Network Dataset" GP tool's Elevation Model defaults to
  "Elevation fields", not "None".** Not called out in the README's
  `ERROR 030386` recovery steps — easy to miss and build elevation-aware
  connectivity by accident on a network that isn't supposed to have one.
  Set it to **None** explicitly every time you go through the interactive
  recovery.
- **Only `Length` gets created automatically.** `OneWay` and `TrafficTurn`
  do not exist on a freshly-created network dataset and must be added by
  hand on the Restrictions tab every single time the network dataset is
  deleted and recreated (which, per the controller-dataset locking rules in
  `CLAUDE.md`, is required on every turn-FC swap and every template retry).

## Turn remap diagnosis

- **`TRNLRS_traffic_turn`'s OBJECTID does not correspond to the legacy
  `TRN_traffic_turn`'s OBJECTID.** `TRNLRS_traffic_turn` is itself the
  product of an earlier remap cycle, with different `Edge{N}FID` references
  (and a different `Edge1FCID`) than the true legacy source. This session,
  querying `TRNLRS_traffic_turn` by the OIDs from a `05_rebuild_traffic_turns.py`
  skip list looked plausible (same OBJECTIDs exist, similar schema) but gave
  actively wrong data for 14 of 15 sampled turns — only one matched by
  coincidence. **When diagnosing skip reasons from a `05_rebuild_traffic_turns.py`
  log, always query the real `SDEADM.TRN_streets_routes\TRN_traffic_turn`
  (alongside `TRN_street`, same SDE), never `TRNLRS_traffic_turn`.**
- **`missing_old_geometry` covers two different causes**, indistinguishable
  from the summary log alone: a row with a genuinely null `SHAPE`, or an OID
  that doesn't exist as a row at all (deleted). This session it was almost
  entirely the second case — checking `SHAPE IS NULL` on the old edge source
  came back empty even though the skip category was large, which initially
  looked contradictory. Confirm the real cause with `OBJECTID IN (...)`
  existence checks, not just a null-geometry query.
- **"Standalone user-defined junction is detected" warnings (~1,000+ on
  every build) are expected and already documented** (see
  `network_dataset_migration_plan.md`, `turn_rebuild_qa_test_runbook.md`,
  `junction_network_workflow_esri_case.html`). Don't re-diagnose these as a
  new finding — only the `Cannot find edge element...` and
  `Cannot find at junction` categories need real attention.
- **`Cannot find at junction` turn-build errors are a separate, still-open
  category** from the "expected at preliminary stage" edge-remap errors —
  do not assume it's the same as a `no_shared_endpoint` skip; these turns
  already passed the remap and the verifier. Diagnose each by computing the
  true minimum distance across all four firstPoint/lastPoint combinations
  between the turn's consecutive edges (script approach used this session,
  also documented in `turn_rebuild_qa_test_runbook.md` §3.3). This session:
  5 occurrences (down from 9 on 2026-09-01), 3 real sub-metre digitizing
  gaps, 2 exact 0.0000m coincidences that both pivoted on the same edge
  (18393) — new supporting evidence for the still-open question to Esri, now
  recorded in `junction_network_workflow_esri_case.html`.

## Swap and rebuild

- **Running the manual swap commands (as printed by `04_remap_turns.py`
  itself) is functionally equivalent to running `06_swap_and_final_build.py`.**
  Both end up calling the same `03_create_network_dataset.py` create logic,
  which will hit `ERROR 030386` at the same point regardless of which path
  you took, **if the template is the old VBScript one**. (Corrected
  2026-09-29: the corrected template creates and builds fine, so neither path
  needs the interactive recovery once the right template is deployed.)
- Log files are timestamp-matched per run, not per script: `_shared.py`
  imports all three core scripts (03, 05, verifier) at module level for
  every qa_refresh entry point, so **three log files get created on every
  run**, each starting with a `"Logging to..."` header — but only the one
  whose `main()` actually executes gets real content. **Match the exact
  timestamp of the run you care about**, not just the script name, or you'll
  read a near-empty header and think something didn't log.

## SQL grants

- Must be **redone after every delete+recreate of the network dataset** —
  this happened three times in a single session today. Use the 2b audit
  query in `network_dataset_sql_permissions.md`; never assume a prior
  cycle's `N_<id>`/`ND_<id>` numbers still apply.
- The odd `1/2` partial-grant state on a fresh `ND_<id>` pair (`DIRTYAREAS`
  already granted for no clear reason, `DIRTYOBJECTS` not) recurred again
  this session exactly as it did on 2026-09-01 — apparently a repeatable
  pattern in this environment, not a one-off anomaly. Don't be thrown by it;
  grant `DIRTYOBJECTS` and re-run the `DIRTYAREAS` grant as a harmless no-op.

## Template export (`CreateTemplateFromNetworkDataset`)

- **Needs a Network Dataset Layer, not a raw SDE catalog path.** Passing the
  catalog path string directly can fail with
  `ERROR 030033: Parameter does not contain a network dataset data element`.
  Fix: `arcpy.na.MakeNetworkDatasetLayer(path, "lyr")` first, then pass the
  layer name/object to `CreateTemplateFromNetworkDataset`. Not previously
  documented anywhere in this repo.
- **The exported template's internal `<Name>`/`<CatalogPath>`/
  `<LogicalNetworkName>` are not reliably the live object's actual catalog
  name.** This session's export came back naming the network dataset
  `TRNLRS_network` instead of the real `TRNLRS_street_network`, for reasons
  never fully explained (the `DSID` matched the live network exactly, so it
  was unambiguously exporting the right object — just mislabeling it
  internally). Since `CreateNetworkDatasetFromTemplate` takes its **output
  name from inside the template file**, always check and correct these
  fields before committing or reusing an exported template, or a future
  automated rebuild will create a wrongly-named network dataset.
- **The `NetworkEvaluatorCLSID` `{68055FC4-37D5-4BD0-81A5-CD177A29759C}` is
  not, by itself, a reliable VBScript-vs-Python signal.** Both the old
  (broken, `ERROR 030386`-triggering) template and the new (validated)
  template carry this identical CLSID, with genuinely different-quality
  Python content underneath in each. Don't diagnose the VBScript-rejection
  bug by grepping for this CLSID alone — the only real test is whether
  `CreateNetworkDatasetFromTemplate` actually gets past evaluator
  validation. (This contradicts the framing in `CLAUDE.md`'s `ERROR 030386`
  section, which reads the CLSID as diagnostic on its own; treat that as
  necessary-but-not-sufficient going forward, not as ground truth.)
- **The exported template is missing `<NetworkDirections>` entirely** —
  present in the previously-committed template (`DefaultOutputLengthUnits =
  esriNAUMiles`, `LengthAttributeName = Length`) but absent from the
  2026-09-18 re-export, because the interactive rebuild this session never
  visited the Directions tab in Network Dataset Properties. This is a real
  functional gap, not a cosmetic one: the live QA network dataset currently
  has no Directions configuration, so a Route layer's driving-directions
  output would come back unconfigured. **Follow-up needed:** set Directions
  on the live network (`Base Name → STR_NAME`, `Suffix Type → STR_TYPE`,
  `Full Name → FULL_NAME`, per the workflow already documented in
  `junction_network_workflow_esri_case.html` step 5), then re-export and
  re-commit the template. Not done as part of this session — caught by a
  `/code-review` pass on the PR after the fact, not before committing.
- **A second `/code-review` pass flagged the template's `TrafficTurn` config as
  a possible regression — verified and ruled out.** The committed template
  encodes `TrafficTurn` as `default(Turn) = true` with no explicit per-source
  override, where the previous template used `default(Turn) = false` plus an
  explicit `TRNLRS_traffic_turn = true` override. Since this network registers
  exactly one turn source, both encodings produce identical results for every
  real turn element — confirmed by the passing prohibited-turn smoke test on
  this exact live configuration. Not a bug. Worth knowing if this network
  dataset is ever extended with a second turn source in the future: the
  current default-based encoding would then apply `true` to that new source's
  turns too unless explicitly overridden, where the old override-based
  encoding would have defaulted them to `false`. Revisit then, not now.
- **Correction, 2026-09-29: the "fix" below was wrong, confirmed in SQL.** On QA, `sys.tables`
  contains `TRNLRS_NETWORK_JUNCTIONS` and no `TRNLRS_STREET_NETWORK_JUNCTIONS`; Network Dataset
  Properties lists `SDEADM.TRNLRS_network_Junctions` (ID 40191, the ID the template gives it).
  So the export's `TRNLRS_network_Junctions` matched the live object. The system junction class
  is named after the name the network was created with, so this is not a mislabel: the
  wizard-built 2026-09-01/09-18 network was probably created as `TRNLRS_network` and renamed,
  which does not rename its system junction class (this would also explain the top-level
  `Name`; the wizard-default cause is unverified). `classify_unresolved_turns.py` now looks for
  either name. Docs that say `TRNLRS_street_network_Junctions` describe the earlier
  template-built networks.
- **Also caught by that same review, since questioned (see above):** the exported
  template's `SystemJunctionSource.Name` read `TRNLRS_network_Junctions`
  instead of `TRNLRS_street_network_Junctions` — the identical
  missing-`street_` mislabeling as the top-level `Name`/`CatalogPath`
  fields, just in a second, nested location that was missed when correcting
  those. **When fixing a mislabeled exported template, grep the whole file
  for the wrong string, not just the top-level fields** — this bug pattern
  can recur in nested `EdgeFeatureSource`/`JunctionFeatureSource`/
  `SystemJunctionSource`/`TurnFeatureSource` blocks too.
- **Safe way to test a candidate template without disrupting the live
  network:** rename its internal `Name`/`CatalogPath`/`LogicalNetworkName`
  to a disposable test name, then run `CreateNetworkDatasetFromTemplate`
  against the *same* feature dataset (the source FCs already exist there —
  no need to duplicate them). Expect `ERROR 030168: The network source
  participates in multiple network datasets` if the live network dataset is
  still up — that's an artifact of testing safely alongside it, not proof
  the template is still broken, since the real steady-state refresh flow
  always deletes the existing network dataset before recreating. Passing
  evaluator validation (no `ERROR 030386`) and reaching a *different*,
  later-stage error is itself the meaningful positive signal. Full
  end-to-end proof (create *and* build via template) is still open and
  should be observed on the next real full rebuild cycle — see the "Open"
  note in `roadmap_lrs_network.html`.

## State as of this session (2026-09-18)

- QA network fully refreshed: turn remap reviewed and swapped, network
  rebuilt (`Edges 37,788 / Junctions 16,185 / Turns 1,184`), SQL grants
  current (`N_3`, `ND_40192`), both Phase 7 smoke tests passed (one-way
  enforcement, prohibited-turn enforcement).
- `network_dataset/data/network_template.xml` replaced with a corrected,
  solve-validated export. Confirmed it clears the evaluator-validation stage
  that blocked every prior automated-rebuild attempt in this project's
  history. Not yet confirmed to build end-to-end unattended — that's the
  next real test, naturally satisfied by the next full QA rebuild.
- **Dev and Prod still need this entire SQL-grants procedure** whenever
  their network datasets are next rebuilt — unrelated to and not covered by
  today's QA-only work. See the "Still open" items in
  `network_dataset_sql_permissions.md`.
- Docs touched this session: `junction_network_workflow_esri_case.html`,
  `network_dataset_sql_permissions.md`, `roadmap_lrs_network.html`,
  `network_dataset/data/network_template.xml`. PR:
  [hrm_LRS#63](https://github.com/agallagher55/hrm_LRS/pull/63).

## 2026-09-29: the template was never broken, the deployed copy was stale

Step 03 failed with `ERROR 030386` and the README's explanation was that the committed
template is still rejected by Pro 3.5.8. It was not the committed template at all. The
`network_template.xml` in the T: drive `network_dataset\data` folder was the 2026-07-14 file
(22 KB, VBScript `Select Case UCase([STR_DIR])`, no `Language` key, 3.3.0 schema), never
overwritten after the 2026-09-18 re-export was committed. The T: folder also holds
`network_template_3_5_8.xml` (2026-09-03, has Directions), `network_template_3_5_8_Sep2026.xml`
(2026-09-18 raw export, still named `TRNLRS_network` inside) and `qa_current_state.xml`
(2026-09-02, whose Against-direction evaluator wrongly uses `FDTO`).

After renaming the stale file to `network_template_VBScript_20260714.xml` and copying the repo
template over it, step 03 (source copies skipped, so re-running was safe) created the network
in about 13 seconds and built it in about 9: 0 errors, Edges 37,674, Junctions 16,187,
Turns 0. Properties showed Length as a Python Field Script, both OneWay directions correct
(Along blocks `N`/`FDTO`/`T`, Against blocks `N`/`FOTD`/`T`), TrafficTurn default turns
Restricted, End Point connectivity on the edge source, Honor on the junction source.

This is the first end-to-end template-driven create and build. Lessons:

- **Diff the deployed template against the repo copy before believing 030386.** Same lesson
  as the deployment-drift note near the top, and it cost a session. Script 03 now says so when
  the deployed file contains `Select Case`.
- **Edge count check:** 37,674 against 37,788 on 2026-09-18. Excluding 61 WA features
  accounts for about 120 fewer edges.
- **Directions are still missing** from the repo template and therefore from this network. The
  2026-09-03 file on T: has the `NetworkDirections` block to copy from.
- **A run that printed its final message and then had to be stopped** (exit code
  `-1073741510`, interrupted) had already built the network; Properties showed Built at
  08:17:49. Check Properties before assuming a stopped run failed.

### 2026-09-29, rest of the run (steps 04 to 07)

- **Remap and verifier reproduced 2026-09-18 exactly:** 1,189 written, 49 skipped (4.0%), 99.7%
  Edge1End agreement, 10 of 10 checks. The inputs (QA's legacy `TRN_street` and
  `TRN_traffic_turn`) had not been refreshed, and the 61 excluded WA edges carried no turns.
- **Every written turn has exactly two edges** (2,378 references for 1,189 turns).
- **The step 01 backup closes the Cogswell ramp question by count.** It held 1,189 records,
  the same as the previous remap, so nothing hand-authored sat on top of it.
- **A staging turn keeps its geometry.** Staging OID 61 has the same 4.302219 m line as raw
  OID 66, so a remapped turn can be matched to its legacy turn by geometry length.
- **A second stale T: file:** `run_full_network_rebuild.py` there had `main()` with no
  arguments, so step 06's `orchestrator.main(["--use-existing-staging"])` raised `TypeError`
  before doing anything. Copy the repo version and rerun.
- **Same five rejected turns as 2026-09-18** (staging OIDs 686, 746, 747, 829, 830, all
  `Cannot find at junction`) on a rebuild done after the 11.5 upgrade and re-extract. Relevant to
  the Esri case.
- **Doubled log lines** during step 06 are cosmetic: script 03 and the orchestrator both
  attach a logger.
- **Not yet done at the time of writing:** grants under the new registration IDs, smoke tests,
  Directions, template re-export, gap check, T: folder sync.

### 2026-09-29, Directions merged into the template

The 2026-09-03 export on T: (`network_template_3_5_8.xml`) still had Directions. Two pieces were
copied unchanged into `data/network_template.xml`, and nothing else in the file changed (the diff
is exactly two insertions and the result parses as XML):

- the top-level `<NetworkDirections>` block (length in miles, `Length` as the length attribute),
  placed between `<SupportsTurns>` and `<Properties>`;
- the edge source's `<NetworkSourceDirections>` with `STR_NAME`, `STR_TYPE` and `FULL_NAME`,
  placed right after the edge source's `<Properties>`.

The junction source has none, as in the 2026-09-03 export. **Not yet proven:** no create has run
with the merged template. Test it before relying on it: the next scripted rebuild will exercise
it, and a failure there falls back to the previous template in git. The live network is not
affected and still has no Directions; configure them in Properties, or wait for the next
rebuild, which changes the registration IDs and so needs the grants redone.

### 2026-09-29, review changes

- **Step 03 is now copy-only (`03_copy_sources.py`, was `03_initial_build.py`).** The preliminary
  create-and-build was thrown away in step 06 anyway, and it produced the 1,238 confusing
  `Cannot find edge element` errors. Neither the remap nor the verifiers need a network, and
  step 06 already skips the delete when none exists. The early proof that the template works
  moved to `test_template_create.py`, which builds in a scratch file geodatabase. Untested
  against a live QA run at the time of writing: the first real check is the next refresh.
- **Step 01 now exports the sources outside SDE** (a file geodatabase under `output/`), and
  step 02 refuses to run unless that export still exists. This closes the gap where a
  database-level refresh of QA would have deleted the only backup with the network.
- **Step 02 needs a recent backup, step 06 a current orchestrator, step 00 shows what is deployed.**
- **Folder tidy:** diagnostics moved to `scripts/diagnostics/`, `patch.py` to
  `scripts/archive/patch_turn_edge1end.py`. See `scripts/README.md`.
- **`LRS_updates.py` sync fixed:** `sync_network_edge_source()` now calls the tested
  `04_sync_and_rebuild_network.sync_and_rebuild()` (DeleteRows plus Append through the edge
  exclusions) instead of its own `TruncateTable` copy, which would have failed with
  `ERROR 001395` and reloaded WA streets. It still leaves the turns stale after each sync; that
  is the open turn-OID-stability decision.

