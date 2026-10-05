# BWI Flyover Tracker

A Python CLI application that polls live ADS-B flight data for commercial departures from Baltimore/Washington International Thurgood Marshall Airport (BWI), detects flyovers above a configurable home location (e.g. Elkridge, MD), and logs detected flyovers with flight details, aircraft type, destination, runway, and METAR weather information.

## Features

- **Automated Geocoding**: Geocodes street addresses via Nominatim (OpenStreetMap) on startup.
- **Live Flight Polling**: Query OpenSky Network REST API for state vectors in an auto-calculated bounding box.
- **Flight Filtering**: Filters airborne commercial flights within a configurable altitude window (500–10,000 ft) and detection radius.
- **Aircraft & Route Enrichment**: Auto-fetches aircraft model (e.g. `A320`, `B738` / `Boeing 737-800`) and destination route info (e.g. `FLL`, `BDL ⟶ FLL`).
- **Runway Inference**: Infers departure runway (28, 10, 15R, 33L) based on plane true track heading.
- **Weather Integration**: Fetches real-time KBWI METAR wind direction, speed, and gusts from NOAA Aviation Weather Center with a 10-minute cache.
- **Formatted Logging**: Appends enriched JSON records to `flyovers.jsonl` and outputs clean, formatted alert blocks to stdout.

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
LISTEN_ADDRESS=123 Main St, Elkridge, MD 21075
FLYOVER_RADIUS_NM=1.0
POLL_INTERVAL_SEC=30
```

## Running the App

Start the poll loop:
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
