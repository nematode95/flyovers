# BWI Flyover Tracker

A Python CLI application that polls live ADS-B flight data for commercial departures from Baltimore/Washington International Thurgood Marshall Airport (BWI), detects flyovers above a configurable home location (e.g. Elkridge, MD), and logs detected flyovers with flight details, aircraft type, destination, runway, and METAR weather information.

## Features

- **Automated Geocoding**: Geocodes street addresses via Nominatim (OpenStreetMap) on startup.
- **Live Flight Polling**: Query OpenSky Network REST API for state vectors in an auto-calculated bounding box; poll summaries list the 10 closest aircraft first with distance and altitude trend colors (green climbing, red descending, violet above 10,000 ft).
- **Flight Filtering**: Filters airborne commercial flights within a configurable altitude window (500–10,000 ft) and detection radius.
- **Aircraft & Route Enrichment**: Auto-fetches aircraft model (e.g. `A320`, `B738` / `Boeing 737-800`) and destination route info (e.g. `FLL`, `BDL ⟶ FLL`).
- **Runway Inference**: Infers departure runway (28, 10, 15R, 33L) based on plane true track heading.
- **Weather Integration**: Fetches real-time KBWI METAR wind direction, speed, and gusts from NOAA Aviation Weather Center with a 10-minute cache.
- **Formatted Logging**: Appends enriched JSON records to `flyovers.jsonl`, prints app output to the terminal, and appends that output to `flyovers.log`.

## Installation

1. Clone or navigate to the repository directory.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Copy `.env.example` to `.env` and adjust settings as needed:
```ini
OPENSKY_CLIENT_ID=your_client_id_here
OPENSKY_CLIENT_SECRET=your_client_secret_here
API_CONFIG_TOKEN=replace_with_a_long_random_secret
LISTEN_ADDRESS=123 Main St, Elkridge, MD 21075
FLYOVER_RADIUS_NM=1.0
BBOX_PADDING_NM=20.0
POLL_INTERVAL_SEC=30
LOG_LEVEL=INFO
LOG_EXTERNAL_API=false
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
```

`BBOX_PADDING_NM` controls how much extra area around the flyover radius is queried from OpenSky. The default of `20.0` means the bounding box extends approximately 21 nautical miles in each cardinal direction from the listening location (20 nm padding plus the 1 nm flyover radius). This affects which aircraft are fetched and shown in bbox poll summaries; it does not change the flyover detection radius.

`API_CONFIG_TOKEN` is required to enable `POST /api/config`; provide its value in the `Authorization` header. If unset, that endpoint is disabled. For local runs, set it in `.env`.

Python log records are written to the terminal and appended to `flyovers.log` in the working directory. Set `LOG_EXTERNAL_API=true` to include begin/end details for outbound API calls such as OpenSky and weather; it defaults to `false`. This setting does not redirect or suppress standard output. Detected flyover records are also stored separately in `flyovers.jsonl`.

### Supabase live snapshot

This sync runs in the HTTP server (`python server.py`), which provides `GET /api/live`; the standalone `python main.py` CLI does not expose that endpoint.

When both `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set, the server upserts the latest `/api/live` response after every poll into one row in `public.live_snapshot`. The row has `id = 'current'`, a `payload` JSONB column containing `last_poll_time`, `count`, and `aircraft`, and an `updated_at` timestamp. Empty polls replace the previous aircraft list with `count: 0` and `aircraft: []`. If the sync fails, the error is logged and local tracking continues. If both settings are absent, syncing is disabled.

Create the table and read policy in the Supabase SQL editor:

```sql
create table public.live_snapshot (
  id text primary key check (id = 'current'),
  payload jsonb not null,
  updated_at timestamptz not null default now()
);

alter table public.live_snapshot enable row level security;
grant select on public.live_snapshot to anon, authenticated;
grant all on public.live_snapshot to service_role;

create policy "Allow reading the current live snapshot"
  on public.live_snapshot
  for select
  to anon, authenticated
  using (id = 'current');
```

Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in the local `.env` file. Do not commit `.env` or expose the service-role key to React. The React app can use its Supabase URL and anon key to read:

```javascript
const { data, error } = await supabase
  .from("live_snapshot")
  .select("payload, updated_at")
  .eq("id", "current")
  .single();
```

`data.payload` has the same shape as `GET /api/live`.

### External API debug logs

Set `LOG_EXTERNAL_API=true` to emit two entries per outbound API call: a `begin calling` entry before the request and a `done calling` entry afterward. The done entry includes the HTTP code and up to 1 KiB of response content; larger bodies are marked as truncated. Request credentials and authorization headers are not logged, and sensitive token fields in response bodies are redacted. Calls that fail before receiving a response have a done entry with the error instead of an HTTP code. When `LOG_EXTERNAL_API=false`, low-level `urllib3` connection messages are also suppressed, even if `LOG_LEVEL=DEBUG`.

## Running the App

To run the HTTP server locally (including `/api/live` and Supabase snapshot sync):
```bash
python server.py
```

The server reads `.env` from the project directory and listens on port `8080` by default. Open `http://localhost:8080/api/live` to inspect the current snapshot. To run only the command-line poller instead, use `python main.py`; that mode does not expose `/api/live` or sync snapshots to Supabase.

Alternatively, start the standalone CLI poll loop:
```bash
python main.py
```

Example Output:
```
BWI Flyover Tracker
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Listening at : 123 Main St, Elkridge, MD 21075
Coordinates  : 39.21000°N, 76.71000°W
Radius       : 1.0 nm (~1.15 miles)
Poll interval: 30s
Log file     : flyovers.jsonl
Runways      : 10 (105°), 28 (285°), 15R (155°), 33L (335°)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Waiting for flyovers...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✈  JBU959           2026-10-05 07:12:33 EDT
   Aircraft  : A320 (Airbus A320 232)
   Destination: FLL (Windsor Locks (BDL) ⟶ Fort Lauderdale (FLL))
   Altitude  : 3,200 ft  |  Speed: 245 kt
   Heading   : 281°
   Runway    : 28 (West)
   Wind      : 270° at 12 kt, gusting 18 kt
   METAR     : KBWI 051254Z 27012G18KT 10SM FEW040 22/10 A2992
   Logged to : flyovers.jsonl
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Running Tests

Run unit tests via `pytest` or `unittest`:
```bash
python -m unittest discover tests -v
```
