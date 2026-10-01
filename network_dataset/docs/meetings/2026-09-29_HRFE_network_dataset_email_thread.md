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
| Transit: are all 124 transit access roads, or are there any you'd want to keep? | reject | **Ambiguous.** "No" to a two-part question: either "not all 124 are transit access roads" or "no, none I'd keep". Closed by Alex's decision to remove all 124, so no follow-up is needed. |
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
  One answer (keep any or not) was ambiguous; see the table. Alex then decided to remove all
  124 with no exceptions, and from every network, not only HRFE, so the rule sits in the
  `GENERAL` exclusion profile. No follow-up to Robbie is needed.
- **Expected effect on the HRFE edge copy:** the four sets (WA 61, emergency access 4, transit
  124, ETAs 22) share no FDMIDs, so 211 rows come out, leaving 18,433 of Prod's 18,644. With
  transit in the general profile, the general network's copy would be 18,459 (WA and transit,
  185 rows out). These are counts to check on the first build, not results.

## 2026-09-29, 3:30 PM, Alex Gallagher to Robbie Evans (summary and requests)

Sent after Robbie's answers and Alex's decisions on transit roads. It gave Robbie the current
exclusion list (WA 61 and transit 124 out of both networks; emergency access 4 and ETAs 22 out of
HRFE only; ETAs stay in the general network because vehicles can still use them), said the HRFE
network is not built yet, and warned that the transit and water access roads leave the distance
network he is testing at its next rebuild. It then asked for:

1. **The bridge:** which bridge it is, since the screenshot has no name or location.
2. **Station 2 left turn on University Ave:** Alex wants to do it first because Robbie called it
   urgent. Robbie is asked to draw the connector as a line in a new feature class and put it in
   Alex's "monthly" folder.
3. **Driveways:** a list of the driveways needed for dry hydrant mapping.
4. **Routes outside HRM:** which roads lead to the stations that respond to HRM, and which bridges
   on them cannot take fire trucks.

It described the plan (a new HRFE feature dataset in QA, the network built from the LRS streets
minus the excluded roads, and Robbie's extra roads loaded from a separate feature class so an LRS
update does not remove them) and answered his question about splits: keep the split points in
their own layer and re-apply them after each LRS update, which Alex would test on the Station 2
connector first.

Left out of the sent version compared with the draft: the offer to accept a road name or a point
on a map for the bridge, and the note that travel time (speed) comes later.

## 2026-10-01, 7:53 AM Halifax time (10:53 UTC), Robbie Evans to Alex Gallagher

> 1.	I confirmed the question about ETA/Tas in the last email. Good to go removing those, and
> numbers are good.
> 2.	Don't worry about that bridge actually. I'll just use a point barrier on it to block it.
> 3.	It's just a tiny little segment. I can copy it over to your monthly folder if you want?
> 4.	I can add these segments to the layer I create for #3 above.
>
> Sounds good about the splits.

His numbering is one off from Alex's list: his "1." is the exclusion list, and his 2, 3 and 4 answer
Alex's bridge, Station 2 and driveways/routes items. Reading each by its content:

| Robbie's answer | Reading |
|---|---|
| 1. ETAs and transit ("ETA/Tas"): "Good to go removing those, and numbers are good." | Confirms the 22 ETAs and 124 transit roads, and the counts in Alex's table. Closes both. |
| 2. The bridge: "Don't worry about that bridge actually. I'll just use a point barrier on it to block it." | **Dropped.** No break in the network and no barrier class needed from Alex. Robbie blocks the bridge himself at solve time. |
| 3. Station 2: "just a tiny little segment", offered to copy it to Alex's monthly folder. | Robbie **created the folder** (below). |
| 4. "I can add these segments to the layer I create for #3 above." | Read as the driveways and the routes outside HRM, which he adds to the same layer as the Station 2 segment. The email does not say which segments "these" are, so this is an interpretation. |
| "Sounds good about the splits." | Agrees to keeping split points in their own layer and re-applying them after each LRS update. |

**The monthly folder (screenshot, 2026-10-01 7:57 AM):** `monthly\202610oct\evansr\Network_Segments_For_Alex`,
holding a file geodatabase `Network_Segments.gdb` and an empty text file. This is the Station 2
turning lane. Its contents (feature class names, fields, geometry, spatial reference, and whether its
ends meet the LRS streets) have not been inspected yet; the repository has no copy of it.
`scripts/diagnostics/11_inspect_extra_roads.py` is written to do that.

Not answered by this email: whether the routes outside HRM need their weak bridges blocked (the
point barrier covers "that bridge", singular), and which feature class holds what Robbie calls
"the layer".

---

## Status of each request against the repository (updated 2026-10-01)

| Request | Status |
|---|---|
| Remove water access roads | Done in `network_exclusions.py` (profile `GENERAL`, so both networks). Ran in QA on 2026-09-29: 61 rows excluded, Edges 37,674. |
| Remove emergency access roads | Confirmed by Robbie 2026-09-29, numbers confirmed 2026-10-01. In the `HRFE` profile (`%EMERGENCY ACCESS%`, 4 rows). No HRFE network exists yet to apply it to. |
| Remove transit access roads | Filter `TA[0-9]%` (124 rows) confirmed by Robbie 2026-09-29. All 124 removed, no exceptions (Alex's decision, which closes Robbie's ambiguous answer). In the `GENERAL` profile, so both networks drop them. |
| Remove ETAs | Confirmed by Robbie 2026-09-29 and again 2026-10-01 ("numbers are good"): 22 rows, complete set, remove for HRFE. In the `HRFE` profile. |
| Break at the bridge trucks cannot cross | **Dropped 2026-10-01.** Robbie will use a point barrier on it himself. Nothing to build. |
| Add main routes outside HRM, broken at weak bridges | Not started. Robbie says he will add these segments to his layer (2026-10-01, interpretation). Blocking weak bridges on them is unanswered. |
| Station 2 left turn on University Ave (**urgent**) | **Received 2026-10-01** in `monthly\202610oct\evansr\Network_Segments_For_Alex\Network_Segments.gdb`. Not yet inspected; next step is `diagnostics/11_inspect_extra_roads.py`. |
| Driveways for dry hydrant mapping | Not started. Robbie says he will add them to the same layer as the Station 2 segment (2026-10-01, interpretation). |
| New feature dataset for the HRFE network in QA | Not started. |
| Point barriers feature class (Robbie's alternative) | **Not needed from Alex.** Robbie will add his own point barrier for the bridge. |
| Splits that survive an LRS update (Robbie's open question) | Proposal of 2026-09-29 accepted by Robbie 2026-10-01 ("Sounds good"): keep split points in their own feature class and re-apply them after every edge sync. Untested. |

Also open for the HRFE network, from other meetings: whether it is a second network dataset or
an added cost attribute, and the travel-time attribute (see `network_build_status.md`).
