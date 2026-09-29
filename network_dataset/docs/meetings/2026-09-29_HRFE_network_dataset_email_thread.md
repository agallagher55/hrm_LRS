# Email thread "HRFE network dataset", 2026-09-01 to 2026-09-29

Primary-source record of the thread in which Robbie Evans (Halifax Regional Fire & Emergency)
said what he needs in an HRFE street network. Quotes are verbatim. Anything outside a quote is
a note added when this record was written (2026-09-29).

**Participants:** Alex Gallagher (GIS Systems Analyst, IT), Robbie Evans (HRFE).

This is the thread behind the "second network" in the 2026-09-09 and 2026-09-23 notes: the
distance network (`TRNLRS_street_network`, in `SDEADM.TRNLRS_network`) plus an HRFE network with
its own inclusions and exclusions. Robbie's requests are for the HRFE network. The WA exclusion
was later also applied to the distance network after the 2026-09-23 meeting.

---

## 2026-09-01, 10:12 AM, Alex Gallagher to Robbie Evans

> What kind of streets do you need filtered out from the general street network in order to
> support an HRFE street network? Do you have a SQL query that would work?

## 2026-09-01, 10:28 AM, Robbie Evans to Alex Gallagher

> Off the top of my head these would be most of the things but prob forgetting some things.
>
> Remove Water Access Rds
>
> Remove Transit Access Rds
>
> Remove ETAs
>
> Remove emergency access roads.
>
> Put break in the network here as trucks can't cross this bridge.
>
> Add main routes outside HRM that lead to fire stations that respond to HRM. Need to break
> these segments at bridges not weighted for fire trucks.
>
> Then a bunch of little things like a little segment to let Station 2 turn left on University Ave.
>
> Lots of driveways like this too where the civics are far away from the road.

Five screenshots came with the thread. From their order and content (not labelled in the
message): a map with a yellow highlighted area over a stream crossing, presumably the bridge
break, with no bridge name or coordinates; an aerial view of University Ave with a short red
connector between the two carriageways (the Station 2 turn); a map with a long red line running
north from a street to a pond (a driveway to a water source); an aerial view of a divided highway
with a highlighted median crossing (an ETA); and a table of the four emergency access road names.
The screenshots are not stored in this repository.

## 2026-09-17, 11:56 AM, Alex Gallagher to Robbie Evans (questions), with Robbie's inline answers

| Alex asked | Robbie answered |
|---|---|
| Water access roads are the roads where `STR_TYPE = 'WA'`? | "Correct." |
| Transit access roads are the roads like `TA# RD`? | "Correct." |
| What do you mean by ETAs? | "Emergency Turnarounds. They are the small highway connectors which enable emergency vehicles to do U-turns between divided highways." |
| How are the emergency access roads identified? | "Emergency Access roads can be queried by FULL_NAME LIKE '%EMERGENCY ACCESS%'. There are only 4 of them" (table: Highland Park, Buckingham Dr x2, Westwood Blvd, each "EMERGENCY ACCESS 01"). |
| (Alex) I will have to create a new feature dataset to host this network. I can do this in QA. Would you then be able to populate feature classes for anything you need added? | "I sure can bud." |
| Driveways | "Yes, I require driveways for dry hydrant mapping." |
| Outside of HRM streets | "Yes, I require a few random segments throughout HRM." |
| Random segments | "Yes. The best example is a turning lane for station 2 which isn't part of the network. This is URGENTLY required, as station 2 can turn here but not reflected in the LRS….So unless Mel wants to add it, I'll require it." |
| Points where segments need to be split | "Not sure what to put here as if I split segments for my random segments and driveways, that will be different than LRS….So if you update the streets in my network these splits will go away. Suggestions?" |

Robbie also offered an alternative for the bridge break:

> Another option that we could do for this…You could create a FC called "point barriers" or
> something similar…Then I could load them into the network prior to running routes. I don't
> like doing that (as service areas look terrible), but would most likely be easier for you.

## 2026-09-17, 1:18 PM, Robbie Evans to Alex Gallagher

> Thank you for reaching out regarding this. I will confirm things to the best of my abilities,
> but I am still quite new to GIS so I may not be able to understand everything. Please resort to
> the original email for commenting, confirmation, and elaboration.

The 11:56 AM message above therefore carries his answers; this one only frames them.

## 2026-09-29, 11:03 AM, Alex Gallagher to Robbie Evans (follow-up)

Sent after running `network_dataset/scripts/diagnostics/10_find_candidate_exclusions.py` against
Prod's `TRNLRS_TRN_STREET_VW` (18,644 rows). The run's output is saved as
[`../../intermediate_results/candidate_exclusions_20260929.csv`](../../intermediate_results/candidate_exclusions_20260929.csv)
and was attached to the email. What the email reported and asked:

| Item | Found in Prod | Question to Robbie |
|---|---|---|
| Water access roads | 61 rows, `STR_TYPE = 'WA'`, named for an island, lake or point ("SAULS ISLAND WA", "LAKE CHARLOTTE WA", "LITTLE INDIAN POINT WA"); already excluded | None. |
| Emergency access roads | 4 rows, matches his list | None. |
| Transit access roads | 124 rows matching `FULL_NAME LIKE 'TA[0-9]%'`: TA1 to TA52 (all 52 numbers), all `STR_TYPE = 'RD'`. The looser `TA%` matches 209 rows and adds 85 ordinary streets (Taylor, Tamarack, Tanner and similar). The old `STR_TYPE = 'ATA'` guess matches 0 rows | Are all 124 transit access roads, or are any to be kept? Are there transit access roads not named "TA# RD"? |
| ETAs | 22 rows named "HIGHWAY nnn ETA n": Highway 101 (3), 102 (8), 103 (8), 118 (3). All `STR_TYPE` null, class EXPRESSWAY. Found by a guessed name search, so this is a candidate, not a confirmed filter | Are these the ETAs, and is 22 the full set? Are there ETAs not named this way? |
| Direction | (none) | His 2026-09-01 list says remove ETAs and emergency access roads from the HRFE network, but those are the connectors emergency vehicles are meant to use. Is removal what he wants for HRFE routing, and not the reverse? |

The email asked for a yes or no per item.

## 2026-09-29, 1:39 PM Halifax time (16:39 UTC), Robbie Evans to Alex Gallagher

> I provided a simple yes/no answer in the original email below as you requested. Thank you for
> your time and effort on this project. HRFE really appreciates it.

The answers are inline in the quoted copy of Alex's email, as a pair of reaction images (a
"Drake approves" image and a "Drake rejects" image) under each bullet, plus one typed answer.
Reading approve as yes and reject as no. Which image sits under which bullet was read from the
message body, not from any text, so the mapping is this record's interpretation.

| Alex's question | Robbie's answer | Reading |
|---|---|---|
| Water access roads: 61 segments, already excluded | approve | Fine. |
| Emergency access roads: 4 segments, matches your list | approve | Matches. |
| Transit: are all 124 transit access roads, or are there any you'd want to keep? | reject | **Ambiguous.** "No" to a two-part question: either "not all 124 are transit access roads" or "no, none I'd keep". Needs a one-line follow-up. |
| Transit: are there transit access roads named differently, not "TA# RD"? | reject | No. There are none. |
| ETAs: are these the ETAs, and is 22 the full set? | approve | Yes to both. |
| ETAs: are there any ETAs that aren't named this way? | reject | No. |
| Direction: is removing ETAs and emergency access roads what you want for HRFE routing? | approve, with typed text below | Yes, remove. |

His typed answer to the direction question (capitals are his):

> YES, EMERGENCY VEHICLES CAN USE ETA'S, BUT WE CALCULATE OUR ROUTES WITHOUT THEM, WE DON'T WANT
> TO BASE OUR ROUTES ON USING THEM, CAN BE USED WHEN NECESSARY THOUGH. EMERGECNY [sic] ACCESS
> ROADS ARE FOR EVACUATION, NOT FOR FIRE APPARATUS RESPONDING INTO SUBDIVISIONS.

### What this settles

- **ETAs are removed from the HRFE network.** The 22 segments named "HIGHWAY nnn ETA n" are the
  complete set. Because vehicles can still use them in the field, they should stay in the general
  distance network; only the HRFE exclusion profile drops them.
- **Emergency access roads are removed from the HRFE network.** They are evacuation routes, not
  routes for apparatus responding into subdivisions.
- **Transit access roads: `TA[0-9]%` is the filter**, with no transit roads under other names.
  One answer (keep any or not) is ambiguous; see the table.
- **Expected effect on the HRFE edge copy:** the four sets (WA 61, emergency access 4, transit
  124, ETAs 22) share no FDMIDs, so 211 rows come out, leaving 18,433 of Prod's 18,644. The
  general network's copy stays at 18,583 (WA only). These are counts to check on the first
  HRFE copy, not results.

---

## Status of each request against the repository (2026-09-29)

| Request | Status |
|---|---|
| Remove water access roads | Done in `network_exclusions.py` (profile `GENERAL`, so both networks). Ran in QA on 2026-09-29: 61 rows excluded, Edges 37,674. |
| Remove emergency access roads | Confirmed by Robbie 2026-09-29. In the `HRFE` profile (`%EMERGENCY ACCESS%`, 4 rows). No HRFE network exists yet to apply it to. |
| Remove transit access roads | Filter `TA[0-9]%` (124 rows) confirmed by Robbie 2026-09-29, apart from one ambiguous answer. Not yet in the profile. |
| Remove ETAs | Confirmed by Robbie 2026-09-29: 22 rows, complete set, remove for HRFE. Not yet in the profile. |
| Break at the bridge trucks cannot cross | Not started. Needs the bridge location from Robbie. |
| Add main routes outside HRM, broken at weak bridges | Not started. Needs a data source for the routes and the bridge list. |
| Station 2 left turn on University Ave (**urgent**) | Not started. |
| Driveways for dry hydrant mapping | Not started. |
| New feature dataset for the HRFE network in QA | Not started. |
| Point barriers feature class (Robbie's alternative) | Not decided. He dislikes it because service areas look bad. |
| Splits that survive an LRS update (Robbie's open question) | Not answered. Proposal: keep split points in their own feature class and re-apply them after every edge sync. |

Also open for the HRFE network, from other meetings: whether it is a second network dataset or
an added cost attribute, and the travel-time attribute (see `network_build_status.md`).
