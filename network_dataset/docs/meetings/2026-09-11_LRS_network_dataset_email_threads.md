# Email threads, 2026-09-10 and 2026-09-11

Primary-source record of the two email threads that changed this project's near-term plan.
Quotes are verbatim from the messages; anything outside a quote is a note added when this
record was written (2026-09-15).

---

## Thread 1: "RE: LRS Network dataset" (2026-09-09 to 2026-09-11)

**Participants:** Alex Gallagher, Robbie Evans, Jillian Landry.

### 2026-09-09, 2:49 PM, Alex Gallagher to Robbie Evans (cc Jillian Landry)

> Hey Robbie,
>
> Just wanted to let you know that the network dataset is good for your expert network testing
> - by end of week, please and then we can be in a good spot for our HRFE kickoff meeting next
> Tuesday. Might be good to test the turn and one-way restrictions.
>
> `E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde\SDEADM.TRNLRS_network\SDEADM.TRNLRS_street_network`

Sent the same afternoon as the 2026-09-09 "Road Network Check In", where Jillian asked Alex to
let Robbie know QA was ready. HRFE kickoff referenced as the following Tuesday, 2026-09-15.

### 2026-09-11, 9:30 AM, Robbie Evans to Alex Gallagher (cc Jillian Landry)

> Just within the first 2 min of me testing I'm finding streets that aren't getting calculated
> due to dangles in the segments when editing. I can continue to do testing, or I can identify
> all of these for the LRS folks to fix then rebuild the network?

(Two screenshots in the original, not captured here.)

### 2026-09-11, 10:26 AM, Jillian Landry

> Probably makes sense to identify all of them to be fixed, as you will still need to retest
> that corrected version.

### 2026-09-11, 1:39 PM, Robbie Evans

> K, there are quite a lot of errors. About 500 were flagged 😕 I'll email Mel and send them
> along. Probably be a while before we do testing again haha.
>
> Most of the ones I'm looked at are just simple fixes though. The segment is extended past the
> intersection.

(One screenshot in the original, not captured here.)

### 2026-09-11, 4:40 PM, Jillian Landry to Robbie Evans and Alex Gallagher

> Thanks Robbie - no sense in your continuing on until these are fixed. Can you also send to
> Ryan as they most likely will share the fixing..

### What this establishes

- QA expert acceptance testing is **paused, not failed**. Robbie never reached the turn or
  one-way restriction tests he was asked to run.
- The defects are in the **LRS source data**, upstream of the network build. "The segment is
  extended past the intersection" is the same failure mode as the seven sub-metre gaps that
  caused turn-build failures on 2026-09-01, at much larger scale.
- The corrected data has to be retested, which means **QA must be refreshed** before Robbie can
  resume. See [`qa_network_refresh_runbook.html`](../qa_network_refresh_runbook.html) for why
  that is a half-day rebuild rather than a reload.
- Ownership of the fixes is expected to be shared between Melanie Parker and Ryan Lowe.
- **Not captured anywhere in this repository:** the list itself. No FDMIDs, no locations, no
  effort estimate.

---

## Thread 2: "FW: Esri Case #04248942 - ArcGIS Pro - LRS Errors" (2026-08-31 to 2026-09-10)

**Participants:** Ryan Lowe, Esri Canada support (Lorraine, then Sukhjit P.), cc Jillian
Landry, Melanie Parker, hhainsworth@esri.ca.

### 2026-09-10, 8:01 AM, Ryan Lowe to Alex Gallagher

> The customer service person from Esri wants to know your workflow and any errors you had
> while creating the junction network. Do you mind sharing that with me so I can relay that to
> him?

### 2026-09-09, 7:23 PM, Sukhjit P. at Esri Canada

> I am able to reproduce the behavior in-house using the data you shared. At this time, the
> behavior seems data-specific and not specific to the version of ArcGIS Pro. I am still trying
> to better understand the issue and see if there are any workarounds. In the meantime, could
> you please confirm the following?
>
> 1. Do you see a datum warning similar to the following for your editing map?
> 2. To confirm, even using ArcGIS Pro 3.5.8, you experience the same behavior for all three
>    scenarios, correct?
> 3. For scenario 1 (screenshot below), you mentioned that this small error is causing an issue
>    when a coworker is trying to create our junction network. Could you reach out to the
>    coworker to get high-level information about the workflow they were following to create the
>    junction network and whether they encountered any errors? Please send screenshots of the
>    error message, if any.

The same request was made earlier, on 2026-09-01:

> 1. What is the high-level workflow for creating the junction network?
> 2. Is there any error message that they are encountering? If so, please send a screenshot.

### Environment Ryan gave Esri, 2026-08-31

> pro 3.3.5 --> 3.5.8
> enterprise 11.5 in qa, 11.3 in prod
> enterprise geodatabse:
> QA: ArcGIS Pro 3.5.8 - 11.5.0 geodatabase
> Prod: ArcGIS Pro 3.3.7 - 11.3.0 geodatabase
>
> sql server 2022
>
> NAD_1983_CSRS_2010_MTM_5_Nova_Scotia
>
> Not sure when the issue started, but we noticed the issue when our team was trying to create
> a junction network, roughly 2 months ago.

### Case timeline

| Date | Event |
|---|---|
| 2026-08-31 | Case opened with Esri Canada customer support; routed to the enterprise geodatabase team |
| 2026-09-01 | Zoom walkthrough with Sukhjit P.; Esri requests a SQL Server backup via FTP |
| 2026-09-04 | Ryan uploads a zipped file geodatabase copy of the LRS |
| 2026-09-09 | Esri reproduces the behaviour in-house; assesses it as **data-specific, not Pro-version-specific**; asks the three questions above |
| 2026-09-10 | Ryan forwards the workflow request to Alex |

### What this establishes

- Esri has **independently reproduced** the intersection behaviour from HRM's own data, and
  their working assessment is that it is a data problem rather than a software-version problem.
  That is consistent with what Robbie found the next day at much larger scale.
- The response owed to Esri is written up in
  [`junction_network_workflow_esri_case.html`](../junction_network_workflow_esri_case.html),
  including a draft reply to Ryan.
- Two of Esri's questions are **not** ours to answer from this repository: the datum warning in
  the editing map (nobody has checked), and whether all three scenarios still reproduce on Pro
  3.5.8 (Ryan's).
- Per the 2026-09-09 check-in, Jillian raised whether the ArcGIS Pro upgrade proceeds before
  this case closes, and noted LRS users may be held back from the upgrade if not. Unanswered.
