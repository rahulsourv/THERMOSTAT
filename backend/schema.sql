-- ThermoStats database schema
-- Run this ONCE in the Supabase SQL Editor (left sidebar -> SQL Editor -> New query)

-- ---------------------------------------------------------------------------
-- places : the 2025 reference data. One row per 5 km cell.
--          This is what the model learned from and scored.
-- ---------------------------------------------------------------------------
drop table if exists alerts;
drop table if exists places;

create table places (
    cell_id             bigint primary key,
    latitude            double precision not null,
    longitude           double precision not null,

    -- what the model thinks
    static_probability  real,

    -- the behaviour that produced that score
    active_days         smallint,
    months_active       smallint,
    night_fraction      real,
    total_detections    integer,
    duty_cycle          real,
    frp_mean            real,
    frp_std             real,
    spread_km           real,

    -- outside-NASA context
    is_volcanic         boolean default false,
    km_to_volcano       real,
    near_power_plant    boolean default false,
    km_to_thermal_plant real,

    label               smallint
);

-- The map constantly asks "what is inside this rectangle?".
-- Without this index every such question scans all 687,000 rows.
create index places_bbox_idx on places (latitude, longitude);
create index places_prob_idx on places (static_probability desc);

-- ---------------------------------------------------------------------------
-- alerts : live FIRMS detections, already scored against place history.
--          Replaced completely each time the pipeline runs.
-- NOTE: no foreign key to places on purpose - about 38,000 detections happen
--       at brand new locations that have no 2025 history yet.
-- ---------------------------------------------------------------------------
create table alerts (
    id                  bigserial primary key,
    cell_id             bigint,
    latitude            double precision not null,
    longitude           double precision not null,

    acq_date            date,
    acq_time            integer,
    frp                 real,
    confidence          text,
    daynight            text,

    static_probability  real,
    alert_score         real,
    alert_level         text,
    why                 text,

    known_place         boolean default false,
    is_volcanic         boolean default false,
    near_power_plant    boolean default false
);

create index alerts_bbox_idx  on alerts (latitude, longitude);
create index alerts_level_idx on alerts (alert_level, alert_score desc);
create index alerts_cell_idx  on alerts (cell_id);

-- ---------------------------------------------------------------------------
-- Security: Row Level Security ON with no policies means ONLY the
-- service_role key (used by our FastAPI backend) can read these tables.
-- The public anon key cannot. That is what we want: the browser talks to
-- FastAPI, and only FastAPI talks to the database.
-- ---------------------------------------------------------------------------
alter table places enable row level security;
alter table alerts enable row level security;

-- ---------------------------------------------------------------------------
-- pipeline_runs : one row per automated run, success or failure.
--                 This is how you find out the job died at 3am without
--                 having to go digging through log files.
-- ---------------------------------------------------------------------------
create table if not exists pipeline_runs (
    id           bigserial primary key,
    started_at   timestamptz not null,
    finished_at  timestamptz,
    status       text not null,
    detections   integer,
    high_alerts  integer,
    error        text
);

create index if not exists pipeline_runs_started_idx
    on pipeline_runs (started_at desc);

alter table pipeline_runs enable row level security;
