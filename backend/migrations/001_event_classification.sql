-- SIH26162 stage 2: thermal event type classification.
--
-- Run this ONCE in the Supabase SQL Editor. It is additive on purpose -
-- schema.sql drops and recreates both tables, which would throw away the
-- 687,289 loaded places. These statements are all IF NOT EXISTS, so running
-- the file twice is harmless.

-- ---------------------------------------------------------------------------
-- places : the classified 2025 reference. One event type per 5 km cell.
-- ---------------------------------------------------------------------------
alter table places add column if not exists event_class      text;
alter table places add column if not exists class_source     text;
alter table places add column if not exists class_confidence real;

-- ---------------------------------------------------------------------------
-- alerts : tonight's detections, carrying the type of the place they sit in.
-- ---------------------------------------------------------------------------
alter table alerts add column if not exists event_class      text;
alter table alerts add column if not exists class_source     text;
alter table alerts add column if not exists class_confidence real;

-- class_source records HOW the type was decided, which the dashboard shows
-- so nobody mistakes a model guess for a mapped fact:
--   'mapped'    - matched OpenStreetMap / WRI / Smithsonian ground truth
--   'predicted' - the stage-2 classifier's answer for an unmapped place
--   'rule'      - the documented transient heuristic (wildfire / agriculture)

-- The classification page groups by type, and the map filters by it.
create index if not exists alerts_class_idx
    on alerts (event_class, alert_score desc);
create index if not exists places_class_idx
    on places (event_class);
