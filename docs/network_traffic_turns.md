
/
Claude finished the response

RE_ Road Network Dataset - Implementation of Updated LRS Version.msg
msg

okay, im ready to hand things off to mel and robbie. what do i need to communicate to the others? let me know if you have any questions.
things i can think of right off the bat are:

network dataset location
speed not integrated because the segmentation of E_SpeedLimit not compatible with the other events that are involved in creating TRNLRS_trn_street_vw.
TRNLRS_trn_street_vw has been copied - future goal is to only keep and maintain the one in the feature dataset.
Jun 26
Let me read the email first to make sure I have full context before helping you put together the handoff.


Ran 2 commands, viewed a file
Ran 2 commands, viewed a file
Good, I have everything I need. Here's a draft handoff summary you can send to Mel and Robbie (and loop in Jill on the June 30 status):

Subject: RE: Road Network Dataset - Implementation of Updated LRS Version

Hi Mel and Robbie,

Wanted to give you a status update and everything you need to start QA testing. Dev and QA builds are complete as of today (June 26), so we're on track for the June 30 target.

What was built

The new network dataset TRNLRS_street_network lives in feature dataset SDEADM.TRNLRS on the QA database (qa_RW_sdeadm.sde). It replaces the old TRN_street_network (which was in SDEADM.TRN_streets_routes) and uses the LRS-derived street feature class as its edge source instead of the legacy TRN_street. Travel attributes, turn restrictions, and one-way logic have all been carried over — properties check passed on my end.

What's been validated so far

Network Dataset Properties look correct — sources, evaluators, and directions field mappings all check out. Solve tests are still needed, which is where you come in.

What to test (Phase 5)

Route solve between two known endpoints — compare the path and travel time against the old TRN_street_network
Service area solve (e.g. 5-minute drive) from a known origin — compare coverage against the old network
One-way restriction enforcement — try routing both directions on a known one-way street
Turn restriction logic
Address range fields (FROM_LEFT, TO_LEFT, FROM_RIGHT, TO_RIGHT) if geocoding is in scope for you
Known differences to be aware of

No elevation modelling — the new edge source doesn't have FROM_ELEV/TO_ELEV fields, so the network uses endpoint-only connectivity instead of 3D elevation fields. Worth paying attention to connectivity at bridges and underpasses during testing.
No travel time (speed) attribute — this is intentional for this phase. E_SpeedLimit can't currently be segmented alongside the other LRS events that build the edge source, so it's been deferred. The network has Length (metres) as its only cost attribute, same as the old one.
Edge source — two copies, one authoritative

The standalone SDEADM.TRNLRS_TRN_STREET_VW (outside the feature dataset) is the authoritative version maintained by LRS_updates.py. The network dataset references a copy inside the feature dataset (SDEADM.TRNLRS\TRNLRS_TRN_STREET). The long-term goal is to consolidate to just the one inside the feature dataset, but for now both exist and the sync is automated in LRS_updates.py.

Let me know if you hit anything unexpected during testing — happy to jump in.

Alex

A few things to flag before you send:

Speed limitation wording — you mentioned the incompatibility is specifically that E_SpeedLimit segmentation isn't compatible with the other events. The draft reflects that, but double-check whether you want to go into more detail for Robbie (the email mentions he has additional HRFE tasks, so he may need more context on the speed gap).
Robbie's stakeholder question — Jill's original email asked Robbie about interested stakeholders to communicate to. That's still open and probably worth nudging him on in this reply.
Jill's check-in — since Jill emailed you yesterday asking about the June 30 target, you may want to CC or reply to her separately to confirm you're on track, rather than having her wait for this to filter through.
remove all em dashes

Jun 26
Hi Mel and Robbie,

Wanted to give you a status update and everything you need to start QA testing. Dev and QA builds are complete as of today (June 26), so we're on track for the June 30 target.

What was built

The new network dataset TRNLRS_street_network lives in feature dataset SDEADM.TRNLRS on the QA database (qa_RW_sdeadm.sde). It replaces the old TRN_street_network (which was in SDEADM.TRN_streets_routes) and uses the LRS-derived street feature class as its edge source instead of the legacy TRN_street. Travel attributes, turn restrictions, and one-way logic have all been carried over; properties check passed on my end.

What's been validated so far

Network Dataset Properties look correct: sources, evaluators, and directions field mappings all check out. Solve tests are still needed, which is where you come in.

What to test (Phase 5)

Route solve between two known endpoints; compare the path and travel time against the old TRN_street_network
Service area solve (e.g. 5-minute drive) from a known origin; compare coverage against the old network
One-way restriction enforcement: try routing both directions on a known one-way street
Turn restriction logic
Address range fields (FROM_LEFT, TO_LEFT, FROM_RIGHT, TO_RIGHT) if geocoding is in scope for you
Known differences to be aware of

No elevation modelling -- the new edge source doesn't have FROM_ELEV/TO_ELEV fields, so the network uses endpoint-only connectivity instead of 3D elevation fields. Worth paying attention to connectivity at bridges and underpasses during testing.
No travel time (speed) attribute -- this is intentional for this phase. E_SpeedLimit can't currently be segmented alongside the other LRS events that build the edge source, so it's been deferred. The network has Length (metres) as its only cost attribute, same as the old one.
Edge source: two copies, one authoritative

The standalone SDEADM.TRNLRS_TRN_STREET_VW (outside the feature dataset) is the authoritative version maintained by LRS_updates.py. The network dataset references a copy inside the feature dataset (SDEADM.TRNLRS\TRNLRS_TRN_STREET). The long-term goal is to consolidate to just the one inside the feature dataset, but for now both exist and the sync is automated in LRS_updates.py.

Let me know if you hit anything unexpected during testing and I'm happy to jump in.

Alex

1782733732353_image.png
help me troubleshoot this error

8:49 AM
This is a classic SDE registration issue. The error DBMS table not found [SDEADM.N_3_Props] means ArcGIS is looking for the network dataset's internal metadata/properties table in the geodatabase system tables and can't find it -- the network dataset either wasn't registered properly with SDE, or the registration is pointing at the wrong database.

Most likely causes:

Wrong SDE connection -- you're connecting to a database where TRNLRS_street_network doesn't actually exist (e.g. pointing at prod when the build was on dev/QA, or vice versa). The N_3_Props table name suggests this is the 3rd network dataset registered in that geodatabase -- if the registration IDs don't line up with the actual database, you'll get this.
Network dataset exists in the geodatabase catalog but the underlying DBMS tables were dropped/never created -- the SDE layer registry has an entry for it but the actual SQL Server tables backing it are missing. This can happen if a previous failed build left a partial registration.
You're adding it from a .lyrx or map document that still has a hardcoded path pointing to the old network or a different environment.
Things to check:

Confirm which .sde connection file you're using to add the data -- open it in the Catalog pane and verify it's dev_RW_sdeadm.sde or qa_RW_sdeadm.sde as appropriate
In that same connection, browse to SDEADM.TRNLRS in the Catalog pane and confirm TRNLRS_street_network actually appears there as a child of the feature dataset
If it does appear in Catalog but still fails to add, try right-clicking it and choosing Add to Current Map from Catalog rather than using Add Data
If it doesn't appear in Catalog at all, the build may not have completed cleanly -- check whether BuildNetwork finished without errors in your script output
What does the Catalog pane show under SDEADM.TRNLRS for that connection?

1782733813424_image.png
im using an os authentication sde connection. TRNLRS_street_network is in the database, i can add it to the map as the sdeadm connection but not the os. if the script doesnt contain it, i havent built the network

8:50 AM
The network dataset exists and is visible, so the build is fine. The issue is a permissions one -- your OS auth user doesn't have SELECT on the underlying SDE system tables that back the network dataset (the N_3_Props table and likely others like N_3_DESC, N_3_FDESC, etc.).

These are SQL Server tables in the SDEADM schema that ArcGIS creates when a network dataset is registered. The SDEADM connection works because that user owns those tables. Your OS auth user has been granted access to the feature classes themselves but not to the network metadata tables.

Fix -- grant SELECT on the network system tables to the OS auth user (or a role it belongs to):

sql
GRANT SELECT ON SDEADM.N_3_DESC   TO [DOMAIN\username];
GRANT SELECT ON SDEADM.N_3_FDESC  TO [DOMAIN\username];
GRANT SELECT ON SDEADM.N_3_ICLASS TO [DOMAIN\username];
GRANT SELECT ON SDEADM.N_3_PROPS  TO [DOMAIN\username];
GRANT SELECT ON SDEADM.N_3_EDESC  TO [DOMAIN\username];
GRANT SELECT ON SDEADM.N_3_ECLASS TO [DOMAIN\username];
GRANT SELECT ON SDEADM.N_3_NCLASS TO [DOMAIN\username];
The 3 in the table names is the network dataset's registration ID in this geodatabase. You can confirm the full set of tables to grant by running:

sql
SELECT name FROM sys.tables
WHERE schema_id = SCHEMA_ID('SDEADM')
AND name LIKE 'N_3_%'
ORDER BY name;
That'll show you everything ArcGIS created for this network dataset so you don't miss any.

If you'd rather grant to a role (cleaner if Mel and Robbie will also need access):

sql
GRANT SELECT ON SDEADM.N_3_PROPS TO [your_gis_read_role];
-- etc.
Worth checking whether the old TRN_street_network has the same pattern -- if OS auth users can open that one fine, compare which tables were granted on that network's registration ID and mirror it for N_3_*.

1782734810620_image.png
i went to make these tables public, not just viewable by particular individuals

9:06 AM
Good call -- making them public is cleaner than managing individual grants. Here's the script:

sql
GRANT SELECT ON SDEADM.N_3_DESC           TO PUBLIC;
GRANT SELECT ON SDEADM.N_3_EDGEWEIGHT     TO PUBLIC;
GRANT SELECT ON SDEADM.N_3_JUNCTIONWEIGHT TO PUBLIC;
GRANT SELECT ON SDEADM.N_3_PROPS          TO PUBLIC;
GRANT SELECT ON SDEADM.N_3_TOPOLOGY       TO PUBLIC;
GRANT SELECT ON SDEADM.N_3_TURNWEIGHT     TO PUBLIC;
Worth also checking what was granted on the old network dataset's system tables so you can confirm this matches. You can find its registration ID and compare:

sql
SELECT name FROM sys.tables
WHERE schema_id = SCHEMA_ID('SDEADM')
AND name LIKE 'N_%'
AND name NOT LIKE 'N_3_%'
ORDER BY name;
That'll show you the other network dataset's tables (e.g. N_1_* or N_2_*) -- then you can check their existing permissions with:

sql
SELECT dp.name AS principal, p.permission_name
FROM sys.database_permissions p
JOIN sys.database_principals dp ON p.grantee_principal_id = dp.principal_id
WHERE p.major_id = OBJECT_ID('SDEADM.N_1_PROPS'); -- swap in the right table name
If PUBLIC already has SELECT on those, you know you're mirroring the right pattern.

1782734983408_image.png
9:09 AM
Interesting -- so there are three network datasets registered here: N_1_* (the old one with a different table structure), N_2_* (likely TRN_street_network), and N_3_* (your new one). The N_1_* set has a noticeably different table structure which is probably an older/different network.

Check permissions on N_2_PROPS to see the pattern that's already working for OS auth users on the existing network:

sql
SELECT dp.name AS principal, p.permission_name
FROM sys.database_permissions p
JOIN sys.database_principals dp ON p.grantee_principal_id = dp.principal_id
WHERE p.major_id = OBJECT_ID('SDEADM.N_2_PROPS');
My guess is PUBLIC already has SELECT on all the N_2_* tables, which would confirm your GRANT ... TO PUBLIC approach for N_3_* is exactly right. Once you've run those grants, try adding TRNLRS_street_network again with the OS auth connection and it should come up clean.

1782735031361_image.png
9:10 AM
Confirmed -- public has SELECT on N_2_PROPS, which is exactly the pattern you want to mirror. You also have HRM\GIS_STREET_EDITOR, WEB_EDITOR, and HRM\GIS_HRM_EDITINGAPP with full CRUD, but for the network dataset tables SELECT on public is all that's needed for read access.

Your grants from earlier are the right call. You just need SELECT on public for all six N_3_* tables -- no need to replicate the editor role grants since nobody will be editing the network system tables directly. Run those six grants and you should be good.

You may also want to mirror the same check against the source feature classes inside SDEADM.TRNLRS to make sure OS auth users can see TRNLRS_TRN_STREET, TRNLRS_street_junction, and TRNLRS_traffic_turn -- if those aren't granted to public (or the relevant roles) the network will open but solves may fail. You can check one quickly with:

sql
SELECT dp.name AS principal, p.permission_name
FROM sys.database_permissions p
JOIN sys.database_principals dp ON p.grantee_principal_id = dp.principal_id
WHERE p.major_id = OBJECT_ID('SDEADM.TRNLRS_TRN_STREET');
can you document this in the relevant md file?

9:11 AM

Ran 2 commands, viewed a file, edited a file
Ran 2 commands, viewed a file, edited a file
Added as "Step 2" under Completed Steps, covering: the error symptom, root cause (missing PUBLIC SELECT on N_3_* tables), how it was diagnosed (comparing against N_2_PROPS permissions on the working network), the fix SQL, and a note to also verify grants on the three source feature classes inside the FD.


Network build status
Document · MD 
1782735888750_image.png
help me troubleshoot

9:24 AM
Same pattern as before but now it's SDEADM.ND_37029_DirtyObjects -- that's one of the ND_* tables you saw in the earlier query (you had ND_37029_DIRTYAREAS and ND_37029_DIRTYOBJECTS in the list). These are the network dataset's dirty area tracking tables, separate from the N_3_* metadata tables you just granted.

Check what grants exist on the equivalent tables for the old network to confirm the pattern, then mirror it:

sql
-- find the dirty area/object tables for the old network to compare
SELECT dp.name AS principal, p.permission_name
FROM sys.database_permissions p
JOIN sys.database_principals dp ON p.grantee_principal_id = dp.principal_id
WHERE p.major_id = OBJECT_ID('SDEADM.ND_12010_DIRTYOBJECTS');
Then grant to PUBLIC for all four ND_37029_* tables:

sql
GRANT SELECT ON SDEADM.ND_37029_DIRTYAREAS   TO PUBLIC;
GRANT SELECT ON SDEADM.ND_37029_DIRTYOBJECTS  TO PUBLIC;
You may also need the other two ND_* registrations you saw -- ND_21268_DIRTYOBJECTS and ND_396_DIRTYOBJECTS -- but those are likely the old networks. To be safe, check which ones belong to TRNLRS_street_network specifically:

sql
SELECT name FROM sys.tables
WHERE schema_id = SCHEMA_ID('SDEADM')
AND name LIKE 'ND_%'
ORDER BY name;
Cross-reference the registration IDs against SDEADM.GDB_ITEMS to confirm which belong to your network:

sql
SELECT name, physicalname FROM SDEADM.GDB_ITEMS
WHERE name LIKE '%TRNLRS%';
That'll tell you definitively which ND_* ID maps to TRNLRS_street_network.

1782736036870_image.png
that worked. now i can bring in the network! update the md files with any relevant updates.

9:27 AM
Good news on the network loading. A few things to note from the screenshot before I update the docs:

ND_12010_DIRTYOBJECTS has PUBLIC SELECT plus HRM\GIS_STREET_EDITOR full CRUD -- but no WEB_EDITOR or HRM\GIS_HRM_EDITINGAPP like N_2_PROPS had. So the pattern isn't perfectly consistent across the old network's tables; I'll document what was actually applied for N_3_* and ND_37029_* rather than implying a blanket mirror.
The ND_37029_* grants (lines 7-8) ran as part of the same batch and the network now loads, confirming those were the remaining missing grants.

Edited a file, ran a command, read a file
Edited a file, ran a command, read a file
Updated. The permissions section now documents both errors in sequence, the grants applied for each, and a note that if the network is ever deleted and rebuilt the registration IDs (3 and 37029) will likely change and the grants will need to be re-applied using the lookup queries to find the new IDs.


Network build status
Document · MD 
do i need to build the network? is it already being built at some stage?

9:47 AM
Looking at your build status doc, yes -- it's already handled. Two places:

scripts/03_create_network_dataset.py -- runs BuildNetwork as its final step when the network is first created. This is what ran on Dev and QA on June 26.
scripts/LRS_updates.py (via sync_network_edge_source()) -- calls BuildNetwork after every LRS refresh cycle, keeping the network current as the edge source gets updated.
There's also scripts/04_sync_and_rebuild_network.py as a standalone one-off option if you ever need to trigger a sync/rebuild outside of a full LRS refresh.

So you shouldn't need to manually build -- unless you're about to promote to prod, in which case 03_create_network_dataset.py handles the initial build there too. Is that the context you're asking about?

what are WAs in a network dataset context?

10:01 AM
WAs are Weight Assignments -- they define how network attribute values are assigned to specific sources (edges, junctions, turns) when the network is built. They map a network cost or restriction attribute to a field or expression on a particular source feature class.

In practice for your network, the N_3_EDGEWEIGHT and N_3_JUNCTIONWEIGHT and N_3_TURNWEIGHT tables you granted permissions on earlier are exactly this -- they store the weight assignment records for each source in the network. So for example:

N_3_EDGEWEIGHT -- stores how the Length cost and OneWay restriction are evaluated against TRNLRS_TRN_STREET edges (the VB script expressions like [SHAPE.STLength()] and the STR_DIR Select Case)
N_3_JUNCTIONWEIGHT -- stores evaluators for junction sources
N_3_TURNWEIGHT -- stores how TrafficTurn restriction is evaluated against TRNLRS_traffic_turn
Are you seeing a WA-related error, or is this coming up in the network dataset properties somewhere?


2026-06-29_Evans, Robbie_txt.txt
244 lines

txt

can you summarize this discussion in the context of the network dataset. create a new file called network_review.md

10:46 AM

Created a file, ran a command, read a file
Created a file, ran a command, read a file
A few things I want to flag where the transcript was ambiguous:

Water access roads -- Robbie went back and forth on whether to remove them (initially said "should probably remove", then explained civics are coded to them and you need them). I've documented that as "no change recommended, needs further discussion" but let me know if you want that framed differently.
Transit access STR_TYPE code -- Robbie said "ATA" at one point but the transcript is noisy. Worth confirming the exact code against the domain before actioning.
Traffic turns -- Robbie said he'd look at them and send notes, but didn't share any findings during the call. I've left that as a pending item.

Network review
Document · MD 
1782750318449_image.png
SDEADM.TRNLRS_street_network_Junctions: 859 records
SDEADM.TRNLRS_street_junction: 15 424 records

SDEADM.TRN_street_network_Junctions: 15 367 records
SDEADM.TRN_street_junction: 15 424 records

Why so few records in SDEADM.TRNLRS_street_network_Junctions?

1:25 PM
That's a significant discrepancy and almost certainly points to a build problem. Here's what's going on:

What these two junction layers are:

TRNLRS_street_junction -- the user-defined junction source (manually placed junctions, copied from TRN_street_junction). 15,424 records, matches the old network exactly. Fine.
TRNLRS_street_network_Junctions -- the system junction class, auto-generated by BuildNetwork. This should have a junction at every edge endpoint that isn't covered by a user junction. In the old network it has 15,367 records; in the new one it only has 859.
Why so few system junctions?

The system junction count being 859 vs 15,367 strongly suggests the network only built connectivity for a tiny fraction of the edge source. Most likely causes:

The edge source (TRNLRS_TRN_STREET) has far fewer features than expected -- check the record count on SDEADM.TRNLRS\TRNLRS_TRN_STREET and compare it against SDEADM.TRNLRS_TRN_STREET_VW. If the standalone authoritative FC has ~15,000+ features but the FD copy only has a few hundred, the CopyFeatures step in 03_create_network_dataset.py didn't copy everything.
BuildNetwork completed with warnings rather than errors -- it may have only processed features it could connect cleanly and silently skipped the rest. Check the geoprocessing log for warnings during the build step.
Spatial extent mismatch -- less likely but worth ruling out; if the FD copy somehow got a different spatial reference or extent clipped during copy, features outside that extent would be dropped.
Start with the record count on TRNLRS_TRN_STREET inside the feature dataset -- that'll tell you immediately whether the edge source is the problem.

1782751382381_image.png
1782751461425_image.png

BuildErrors_7c65e48f-845d-4c57-976d-2b41912693a9.txt
3 lines

txt

1:44 PM
A few things to untangle here from these three pieces of evidence:

Good news -- the edge source is fine. TRNLRS_TRN_STREET has 18,575 records, which is more than the old network's junction count, so the CopyFeatures step worked correctly. The low system junction count is not a copy problem.

The build errors are a red herring. The BuildErrors file is from a build of SDEADM.TRN_street_network (the old network, in TRN_streets_routes) -- not TRNLRS_street_network. Those two standalone junction warnings are pre-existing issues on the legacy network, nothing to do with your build.

The real question is whether TRNLRS_street_network was actually rebuilt. Looking at the geoprocessing history, that BuildNetwork at 1:17 PM was run against SDEADM.TRN_street_network (old network), not TRNLRS_street_network. So the 859 system junction count may simply reflect that TRNLRS_street_network has never had a proper BuildNetwork run against it in this environment -- or it was built against an incomplete edge source at the time of creation.

Next step: run BuildNetwork explicitly against SDEADM.TRNLRS\TRNLRS_street_network and check the system junction count afterwards. Given 18,575 edge features you'd expect a system junction count much closer to the old network's 15,367.

1782751753902_image.png

BuildErrors_4c6bb0f4-9ae7-4167-8aea-a52ac2f4ac2c.txt
txt

1:49 PM
Good -- this build ran against SDEADM.TRNLRS\TRNLRS_street_network and took 1 minute 58 seconds, which is much more plausible for 18,575 edge features. Let me read the build errors file.


Read the build errors file for the TRNLRS network build
Read the build errors file for the TRNLRS network build
Two distinct issues here. Let me break them down:

Issue 1: Standalone junction warnings (TRNLRS_street_junction) -- not a problem

The hundreds of Standalone user-defined junction is detected warnings are expected and harmless. These are junctions in TRNLRS_street_junction that don't coincide with any edge endpoint in the new edge source (TRNLRS_TRN_STREET). This happens because the new LRS-derived edge source has different segmentation than TRN_street -- street segments are split differently, so some manually-placed junctions from the old network no longer land on an edge endpoint. The network still builds and routes correctly; these junctions are simply ignored during solves. The old TRN_street_network had only 2 of these; the new one has many more because the edge segmentation has changed substantially.

Issue 2: Turn errors (TRNLRS_traffic_turn) -- this IS a problem

Every single turn record is failing with Cannot find edge element corresponding to turn identifier 1. The phrase "turn identifier 1" is key -- it's not a specific OBJECTID, it's the first edge reference in each turn feature. Turn features in ArcGIS store edge references by the source feature's ObjectID. Since TRNLRS_traffic_turn was copied from TRN_streets_routes and still references ObjectIDs from the old TRN_street edge source, none of those ObjectIDs exist in TRNLRS_TRN_STREET. The turn table is effectively broken for this network -- all turns are being silently skipped during builds, meaning turn restrictions are not enforced at all.

What needs to happen:

The turn feature class needs to be rebuilt or remapped against the new edge source. The options are:

Rebuild turns from scratch against TRNLRS_TRN_STREET using the intersection geometry -- essentially re-digitizing or re-deriving each restricted turn against the new edge OBJECTIDs.
Spatial remapping -- for each turn in TRNLRS_traffic_turn, find the spatially coincident edge(s) in TRNLRS_TRN_STREET and update the edge references. This could be scripted in Python using arcpy's turn feature class utilities.
This is worth flagging with Robbie since he was planning to review the traffic turns -- the situation is worse than expected; it's not just a review, the turns need to be remapped before they'll work at all.

how can we rebuild the turns feature class programmatically, referencing the old network to dictate the turns for the new network

1:54 PM
The core problem is that turn features store edge references as ObjectID + position along edge, and the ObjectIDs changed when you copied the edge source to a new feature class. The geometry of the intersections is the same though, so you can use spatial coincidence to remap them.

Here's the approach:

Conceptual steps:

For each turn in TRNLRS_traffic_turn, read the edge geometries it references from the old TRN_street source (using the stored ObjectIDs and edge positions)
Find the spatially coincident edges in TRNLRS_TRN_STREET at the same locations
Write new turn features referencing the new edge ObjectIDs
The complication: ArcGIS turn feature classes have a somewhat opaque schema. Each turn stores up to 5 edge references as sets of fields (Edge1FID, Edge1Pos, Edge1FCID, Edge2FID, etc.), where FID is the ObjectID of the referenced edge in the source feature class and Pos is a value between 0 and 1 indicating position along the edge. FCID is the feature class ID registered in the network.

The cleanest programmatic approach is:

python
import arcpy

old_turn_fc = r"<sde>\SDEADM.TRN_streets_routes\SDEADM.TRN_traffic_turn"
old_edge_fc = r"<sde>\SDEADM.TRN_streets_routes\SDEADM.TRN_street"
new_edge_fc = r"<sde>\SDEADM.TRNLRS\SDEADM.TRNLRS_TRN_STREET"
new_turn_fc = r"<sde>\SDEADM.TRNLRS\SDEADM.TRNLRS_traffic_turn"
new_network = r"<sde>\SDEADM.TRNLRS\SDEADM.TRNLRS_street_network"

# Step 1 -- build a spatial index of new edges for lookup
# For each turn, get the endpoint geometry of each referenced old edge,
# then find the new edge that passes through that point

# Step 2 -- for each turn in old_turn_fc:
#   - read Edge1FID, Edge1Pos, Edge2FID, Edge2Pos (and Edge3-5 if present)
#   - get the geometry of the old edge at Edge1FID, compute the point at Edge1Pos
#   - spatial query new_edge_fc for edges passing through that point
#   - write a new turn record with the matched new ObjectIDs
However, arcpy doesn't expose a clean API for writing turn feature classes directly -- the edge reference fields (Edge1FCID, Edge1FID, Edge1Pos) have to be populated correctly and FCID values are network-registration-specific.

The most reliable approach is actually arcpy.na.CreateTurnFeatureClass + manual population:

python
import arcpy

sde = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"
old_turn_fc  = sde + r"\SDEADM.TRN_streets_routes\SDEADM.TRN_traffic_turn"
old_edge_fc  = sde + r"\SDEADM.TRN_streets_routes\SDEADM.TRN_street"
new_edge_fc  = sde + r"\SDEADM.TRNLRS\SDEADM.TRNLRS_TRN_STREET"
new_turn_fc  = sde + r"\SDEADM.TRNLRS\SDEADM.TRNLRS_traffic_turn_new"
new_network  = sde + r"\SDEADM.TRNLRS\SDEADM.TRNLRS_street_network"

SNAP_TOLERANCE = 0.5  # metres -- adjust if needed

# ---------------------------------------------------------------
# 1. Build a spatial index of new edges: OID -> Polyline geometry
# ---------------------------------------------------------------
print("Indexing new edge geometries...")
new_edge_geoms = {}
with arcpy.da.SearchCursor(new_edge_fc, ["OID@", "SHAPE@"]) as cur:
    for oid, shape in cur:
        new_edge_geoms[oid] = shape

# ---------------------------------------------------------------
# 2. Build a point-to-new-OID lookup using edge endpoints
#    Turn junctions occur at endpoints, so index by snapped endpoint
# ---------------------------------------------------------------
def point_key(pt, tolerance=0.1):
    """Round coordinates to a grid for fuzzy matching."""
    return (round(pt.X / tolerance) * tolerance,
            round(pt.Y / tolerance) * tolerance)

endpoint_index = {}  # point_key -> list of (new_oid, 'start'|'end')
for oid, shape in new_edge_geoms.items():
    for end, pt in [("start", shape.firstPoint), ("end", shape.lastPoint)]:
        key = point_key(pt, SNAP_TOLERANCE)
        endpoint_index.setdefault(key, []).append((oid, end))

# ---------------------------------------------------------------
# 3. Read old turns and discover how many edge-ref fields exist
# ---------------------------------------------------------------
turn_fields = [f.name for f in arcpy.ListFields(old_turn_fc)]
edge_slots = []
for i in range(1, 6):
    if f"Edge{i}FID" in turn_fields:
        edge_slots.append(i)

print(f"Turn edge slots found: {edge_slots}")

# ---------------------------------------------------------------
# 4. Build lookup: old edge OID -> geometry
# ---------------------------------------------------------------
print("Indexing old edge geometries...")
old_edge_geoms = {}
with arcpy.da.SearchCursor(old_edge_fc, ["OID@", "SHAPE@"]) as cur:
    for oid, shape in cur:
        old_edge_geoms[oid] = shape

# ---------------------------------------------------------------
# 5. Helper: given an old edge OID + Pos, find the matching new OID
# ---------------------------------------------------------------
def find_new_oid(old_oid, pos):
    """
    Resolve an old edge reference (OID + 0-1 position) to a new edge OID
    by finding the new edge whose endpoint is closest to the junction point.
    Pos ~0 means the junction is near the start; pos ~1 means near the end.
    """
    if old_oid not in old_edge_geoms:
        return None
    shape = old_edge_geoms[old_oid]
    # The junction end is whichever endpoint pos is closest to
    pt = shape.firstPoint if pos < 0.5 else shape.lastPoint
    key = point_key(pt, SNAP_TOLERANCE)
    candidates = endpoint_index.get(key, [])
    if not candidates:
        return None
    # If multiple candidates, prefer the one whose geometry also contains
    # a midpoint near the old edge midpoint (same general direction)
    return candidates[0][0]  # take first match for now

# ---------------------------------------------------------------
# 6. Create a fresh turn FC and populate it
# ---------------------------------------------------------------
print("Creating new turn feature class...")

# Get FCID of new edge source from the network
nd_desc = arcpy.Describe(new_network)
new_edge_fcid = None
for src in nd_desc.sources:
    if "TRNLRS_TRN_STREET" in src.name.upper():
        new_edge_fcid = src.sourceID
        break

if new_edge_fcid is None:
    raise ValueError("Could not find FCID for TRNLRS_TRN_STREET in network sources")

print(f"New edge FCID: {new_edge_fcid}")

arcpy.na.CreateTurnFeatureClass(
    out_location=sde + r"\SDEADM.TRNLRS",
    out_feature_class_name="TRNLRS_traffic_turn_new",
    maximum_edges=max(edge_slots),
    # NOT in_network_dataset=new_network: that registers this FC as a live
    # turn source of the network dataset immediately, which then blocks
    # Delete/Rename on it (ERROR 001919) until the network dataset itself
    # is deleted. in_template_feature_class copies the same schema instead.
    in_template_feature_class=old_turn_fc_final,
)

# Build insert field list
insert_fields = ["SHAPE@"]
for i in edge_slots:
    insert_fields += [f"Edge{i}FCID", f"Edge{i}FID", f"Edge{i}Pos"]

read_fields = ["SHAPE@", "NODE_"]  # NODE_ stores the restricted turn type if present
for i in edge_slots:
    read_fields += [f"Edge{i}FCID", f"Edge{i}FID", f"Edge{i}Pos"]

# Add NODE_ to insert fields if it exists in old FC
if "NODE_" in turn_fields:
    insert_fields.append("NODE_")

print("Remapping turns...")
skipped = 0
written = 0

with arcpy.da.SearchCursor(old_turn_fc, read_fields) as read_cur, \
     arcpy.da.InsertCursor(new_turn_fc, insert_fields) as ins_cur:

    for row in read_cur:
        row = list(row)
        shape = row[0]
        new_row = [shape]
        valid = True

        field_offset = 2 if "NODE_" in read_fields else 2  # shape + NODE_

        for idx, i in enumerate(edge_slots):
            old_fcid = row[2 + idx * 3]
            old_fid  = row[3 + idx * 3]
            old_pos  = row[4 + idx * 3]

            if old_fid is None or old_fid == 0:
                # No more edges in this turn
                new_row += [None, None, None]
                continue

            new_fid = find_new_oid(old_fid, old_pos)
            if new_fid is None and i == 1:
                # First edge is required; skip this turn entirely
                valid = False
                break

            new_row += [new_edge_fcid, new_fid, old_pos]

        if not valid:
            skipped += 1
            continue

        if "NODE_" in turn_fields:
            new_row.append(row[1])  # carry NODE_ value

        ins_cur.insertRow(new_row)
        written += 1

print(f"Done. Written: {written}, Skipped: {skipped}")
A few things to be aware of before running this:

The pos assumption -- using pos < 0.5 to determine which endpoint a junction is at is a simplification. Turns connect at shared endpoints between sequential edges, so pos near 0 = start of edge, pos near 1 = end. This holds in practice but worth verifying on a few known turns first.
The snap tolerance -- 0.5 metres is a starting point. If the LRS resegmentation shifted any endpoints slightly, you may need to widen it; if there are closely-spaced intersections, you may need to tighten it. Check the skipped count after running.
Multiple candidates -- the candidates[0][0] fallback is naive. If you get many skipped turns, add a tiebreaker that checks which candidate edge shares the most geometry with the old edge (direction/angle comparison).
After running -- delete the old TRNLRS_traffic_turn, rename TRNLRS_traffic_turn_new to TRNLRS_traffic_turn, update the network template XML if the source name changed, then rebuild. Or swap the network to reference the new FC name and rebuild.
Want me to make any part of this more robust before you run it?

update the md files as required and create a new md file for traffic turns

2:13 PM
Let me read the current state of the files before making changes.


Viewed 2 files
Viewed 2 files
Now I'll make all three updates:


Edited 4 files
Edited 4 files
Now update network_review.md to expand the traffic turns section:


Update the traffic turns section in network_review.md
Update the traffic turns section in network_review.md
Now create the traffic turns file:


Created a file, ran a command, read a file
Created a file, ran a command, read a file
Here's a summary of what changed across all three files:

network_build_status.md

Added Phase 5a to the status table flagging the turn rebuild as a blocking issue
Updated the TRNLRS_traffic_turn prerequisite row to ⚠️ with a note pointing to traffic_turns.md
Added Step 3 (turn rebuild) as a new blocking remaining step before validation
Updated the turn restriction solve test item to note it's currently blocked
network_review.md

Expanded the Traffic Turns section from a placeholder to a full summary of the diagnosis, distinguishing the critical turn OID issue from the non-critical standalone junction warnings, with links to traffic_turns.md
traffic_turns.md (new)

Full diagnosis of the root cause
Note clarifying that standalone junction warnings are a separate, non-critical issue
The complete remapping script with inline comments
Post-script steps (delete/rename, rebuild, verify)
Known limitations, including the ETA note Robbie raised during the QA session

Traffic turns
Document · MD 

Network build status
Document · MD 

Network review
Document · MD 






Claude is AI and can make mistakes. Please double-check responses.


Traffic turns · MD
# Traffic Turn Feature Class -- Rebuild Notes
## TRNLRS_traffic_turn
 
---
 
## Problem
 
`TRNLRS_traffic_turn` was initially created by copying `TRN_streets_routes\TRN_traffic_turn`
into `SDEADM.TRNLRS`. The copy succeeded, but every record fails at `BuildNetwork` time:
 
```
SourceName: SDEADM.TRNLRS_traffic_turn, ObjectID: 1,
Cannot find edge element corresponding to turn identifier 1.
SourceName: SDEADM.TRNLRS_traffic_turn, ObjectID: 2,
Cannot find edge element corresponding to turn identifier 1.
... (all records)
```
 
**Root cause:** turn feature classes in ArcGIS Network Analyst store edge references as
`Edge{N}FID` fields containing the ObjectID of a feature in the registered edge source FC.
The old turn FC referenced ObjectIDs from `SDEADM.TRN_street`. When the turn FC was copied
into `SDEADM.TRNLRS` and registered against `TRNLRS_TRN_STREET`, those OIDs no longer
correspond to any feature in the new edge source. ArcGIS cannot resolve the turn geometry
and skips every record silently -- no turn restrictions are enforced in the current build.
 
**Scope:** all records in `TRNLRS_traffic_turn` are affected. This is not a data quality
issue with a subset of turns; the entire FC needs to be remapped.
 
---
 
## Separate issue -- standalone junction warnings
 
The build errors file also contains many `Standalone user-defined junction is detected`
warnings for `TRNLRS_street_junction`. These are distinct from the turn problem and are
not critical -- they indicate that some manually-placed junctions no longer coincide with
an edge endpoint after LRS resegmentation. These junctions are ignored during solves but
do not cause incorrect results. No action required for go-live.
 
---
 
## Solution -- spatial remapping
 
Turn junctions occur at shared endpoints between two or more sequential edges. The geometry
of those intersections is unchanged between old and new edge sources, so the old turn
references can be remapped to new edge OIDs by spatial coincidence:
 
1. For each turn record, read the `Edge{N}FID` and `Edge{N}Pos` values
2. Use `Pos` (0 = start of edge, 1 = end) to determine which endpoint of the old edge
   the turn junction sits on
3. Look up that point in a spatial index of `TRNLRS_TRN_STREET` endpoints
4. Write a new turn record with the matched new OIDs and the same `Pos` values
**Script:** `scripts/05_rebuild_traffic_turns.py`
 
Key parameters in the script:
 
| Variable | Value | Notes |
|---|---|---|
| `old_turn_fc` | `SDEADM.TRN_streets_routes\TRN_traffic_turn` | Source of truth for turn geometry and type |
| `old_edge_fc` | `SDEADM.TRN_streets_routes\TRN_street` | Used to resolve old OIDs to geometry |
| `new_edge_fc` | `SDEADM.TRNLRS\TRNLRS_TRN_STREET` | Target edge source |
| `new_turn_fc` | `SDEADM.TRNLRS\TRNLRS_traffic_turn_new` | Output -- rename after verification |
| `new_network` | `SDEADM.TRNLRS\TRNLRS_street_network` | Used to look up `FCID` of new edge source |
| `SNAP_TOLERANCE` | `0.5` metres | Widen if skipped count is high; tighten if intersections are close together |
 
---
 
## Remapping script
 
```python
import arcpy
 
sde = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"
old_turn_fc  = sde + r"\SDEADM.TRN_streets_routes\SDEADM.TRN_traffic_turn"
old_edge_fc  = sde + r"\SDEADM.TRN_streets_routes\SDEADM.TRN_street"
new_edge_fc  = sde + r"\SDEADM.TRNLRS\SDEADM.TRNLRS_TRN_STREET"
new_turn_fc  = sde + r"\SDEADM.TRNLRS\SDEADM.TRNLRS_traffic_turn_new"
new_network  = sde + r"\SDEADM.TRNLRS\SDEADM.TRNLRS_street_network"
 
SNAP_TOLERANCE = 0.5  # metres
 
# 1. Build spatial index of new edge endpoints
print("Indexing new edge geometries...")
new_edge_geoms = {}
with arcpy.da.SearchCursor(new_edge_fc, ["OID@", "SHAPE@"]) as cur:
    for oid, shape in cur:
        new_edge_geoms[oid] = shape
 
def point_key(pt, tolerance=0.1):
    return (round(pt.X / tolerance) * tolerance,
            round(pt.Y / tolerance) * tolerance)
 
endpoint_index = {}
for oid, shape in new_edge_geoms.items():
    for pt in [shape.firstPoint, shape.lastPoint]:
        key = point_key(pt, SNAP_TOLERANCE)
        endpoint_index.setdefault(key, []).append(oid)
 
# 2. Discover edge slot count from old turn FC
turn_fields = [f.name for f in arcpy.ListFields(old_turn_fc)]
edge_slots = [i for i in range(1, 6) if f"Edge{i}FID" in turn_fields]
print(f"Edge slots: {edge_slots}")
 
# 3. Build lookup of old edge geometries
print("Indexing old edge geometries...")
old_edge_geoms = {}
with arcpy.da.SearchCursor(old_edge_fc, ["OID@", "SHAPE@"]) as cur:
    for oid, shape in cur:
        old_edge_geoms[oid] = shape
 
# 4. Helper: resolve old OID + Pos to new OID
def find_new_oid(old_oid, pos):
    if old_oid not in old_edge_geoms:
        return None
    shape = old_edge_geoms[old_oid]
    pt = shape.firstPoint if pos < 0.5 else shape.lastPoint
    key = point_key(pt, SNAP_TOLERANCE)
    candidates = endpoint_index.get(key, [])
    return candidates[0] if candidates else None
 
# 5. Get FCID of new edge source
nd_desc = arcpy.Describe(new_network)
new_edge_fcid = None
for src in nd_desc.sources:
    if "TRNLRS_TRN_STREET" in src.name.upper():
        new_edge_fcid = src.sourceID
        break
if new_edge_fcid is None:
    raise ValueError("Could not find FCID for TRNLRS_TRN_STREET in network sources")
print(f"New edge FCID: {new_edge_fcid}")
 
# 6. Create new turn FC
arcpy.na.CreateTurnFeatureClass(
    out_location=sde + r"\SDEADM.TRNLRS",
    out_feature_class_name="TRNLRS_traffic_turn_new",
    maximum_edges=max(edge_slots),
    # NOT in_network_dataset=new_network: that registers this FC as a live
    # turn source of the network dataset immediately, which then blocks
    # Delete/Rename on it (ERROR 001919) until the network dataset itself
    # is deleted. in_template_feature_class copies the same schema instead.
    in_template_feature_class=old_turn_fc_final,
)
 
# 7. Build field lists
insert_fields = ["SHAPE@"]
read_fields   = ["SHAPE@"]
if "NODE_" in turn_fields:
    read_fields.append("NODE_")
for i in edge_slots:
    read_fields   += [f"Edge{i}FCID", f"Edge{i}FID", f"Edge{i}Pos"]
    insert_fields += [f"Edge{i}FCID", f"Edge{i}FID", f"Edge{i}Pos"]
if "NODE_" in turn_fields:
    insert_fields.append("NODE_")
 
# 8. Remap
print("Remapping turns...")
skipped = 0
written = 0
 
with arcpy.da.SearchCursor(old_turn_fc, read_fields) as read_cur, \
     arcpy.da.InsertCursor(new_turn_fc, insert_fields) as ins_cur:
 
    for row in read_cur:
        row = list(row)
        shape    = row[0]
        node_val = row[1] if "NODE_" in turn_fields else None
        offset   = 2 if "NODE_" in turn_fields else 1
 
        new_row = [shape]
        valid   = True
 
        for idx, i in enumerate(edge_slots):
            old_fid = row[offset + idx * 3 + 1]
            old_pos = row[offset + idx * 3 + 2]
 
            if old_fid is None or old_fid == 0:
                new_row += [None, None, None]
                continue
 
            new_fid = find_new_oid(old_fid, old_pos)
            if new_fid is None and i == 1:
                valid = False
                break
 
            new_row += [new_edge_fcid, new_fid, old_pos]
 
        if not valid:
            skipped += 1
            continue
 
        if "NODE_" in turn_fields:
            new_row.append(node_val)
 
        ins_cur.insertRow(new_row)
        written += 1
 
print(f"Done. Written: {written}, Skipped: {skipped}")
```
 
---
 
## Post-script steps
 
After the script completes:
 
1. **Review the skipped count.** A small number of skipped turns is acceptable -- these
   are turns where the old edge endpoint no longer exists in the new network (e.g. segments
   removed by LRS resegmentation). A high skipped count (>5% of total) suggests the snap
   tolerance needs adjustment.
2. **Delete the network dataset first.** `TRNLRS_traffic_turn` is itself a registered turn
   source of `TRNLRS_street_network` (defined in `data/network_template.xml`), which makes
   it a "controller dataset" participant. ArcGIS refuses to `Delete` or `Rename` it while the
   network dataset still references it (`ERROR 001919: <value> cannot be deleted because it
   participates in a controller dataset...`). There is no arcpy call to unregister a single
   source from an existing network dataset -- the network dataset must be deleted to release
   the lock on all its sources:
```python
   arcpy.management.Delete(sde + r"\SDEADM.TRNLRS\SDEADM.TRNLRS_street_network")
```
3. **Delete the old turn FC and rename the new one:**
```python
   arcpy.management.Delete(sde + r"\SDEADM.TRNLRS\SDEADM.TRNLRS_traffic_turn")
   arcpy.management.Rename(
       sde + r"\SDEADM.TRNLRS\SDEADM.TRNLRS_traffic_turn_new",
       "TRNLRS_traffic_turn"
   )
```
 
4. **Recreate and rebuild the network dataset** by re-running
   `scripts/03_create_network_dataset.py` -- it's idempotent, so it will skip re-copying the
   three source FCs (they already exist) and go straight to
   `CreateNetworkDatasetFromTemplate` + `BuildNetwork`.
 
5. **Confirm the build errors file no longer contains turn errors.** Standalone junction
   warnings for `TRNLRS_street_junction` will likely still appear and can be ignored.
6. **Run a turn restriction solve test** -- route through a known prohibited turn and
   confirm the solver avoids it.

**Note:** the remap script itself creates `TRNLRS_traffic_turn_new` via
`in_template_feature_class` (schema copied from the current `TRNLRS_traffic_turn`), not
`in_network_dataset`. Passing `in_network_dataset` to `CreateTurnFeatureClass` registers the
output as a live turn source of that network dataset immediately on creation -- the same
controller-dataset lock described above -- which would make the staging FC itself
undeletable/unrenameable before it's even reviewed. Using a numbered or otherwise
differently-named staging FC would not avoid this: the lock is caused by the
`in_network_dataset` parameter, not the output name, so each attempt would just leave behind
another permanently-locked orphan turn source.
---
 
## Known limitations
 
- **Snap tolerance sensitivity:** the `find_new_oid` function takes the first candidate
  at a snapped endpoint. If multiple new edges share an endpoint (a multi-leg intersection),
  the wrong edge could be selected. For most turns this won't matter -- the turn geometry
  itself disambiguates direction -- but complex intersections may need manual review.
- **Turns referencing removed segments:** if a segment was present in `TRN_street` but
  was not carried through into `TRNLRS_TRN_STREET_VW` (e.g. a segment filtered out by
  `TO_DATE IS NULL`), those turns will be skipped. This is correct behaviour -- a turn
  restriction referencing a segment that no longer exists in the network is not applicable.
- **Emergency turnarounds (ETAs):** Robbie flagged during the 2026-06-29 QA session that
  emergency turnarounds may need to be removed from the turn source. Confirm scope of
  `TRNLRS_traffic_turn` records before finalising the rebuild -- if ETAs are present and
  should be excluded, add a filter in the read cursor.
---
 
## Key paths
 
| Item | Path |
|---|---|
| Old turn FC (source) | `SDEADM.TRN_streets_routes\SDEADM.TRN_traffic_turn` |
| Old edge FC (for OID lookup) | `SDEADM.TRN_streets_routes\SDEADM.TRN_street` |
| New edge FC | `SDEADM.TRNLRS\SDEADM.TRNLRS_TRN_STREET` |
| Current (broken) turn FC | `SDEADM.TRNLRS\SDEADM.TRNLRS_traffic_turn` |
| Rebuild script | `scripts/05_rebuild_traffic_turns.py` |
| QA SDE connection | `E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde` |
 











