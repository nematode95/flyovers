#!/usr/bin/env python3
"""Runway Observer JSON Server

Standalone HTTP server and observer worker that monitors BWI flight departures,
infers takeoff runways, aggregates batches of N flyovers into Supabase,
and manages hiatus intervals to conserve OpenSky API quota.
"""

import argparse
from http.server import ThreadingHTTPServer
import logging
import os
import sys

from api_logging import configure_logging
from config import load_settings
from runway_observer import RunwayObserverWorker, RunwayObserverRequestHandler

logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Runway Observer JSON Server")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("RUNWAY_OBSERVER_PORT", os.getenv("PORT", "8081"))),
        help="HTTP port to listen on (default: 8081 or RUNWAY_OBSERVER_PORT/PORT)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("RUNWAY_OBSERVER_BATCH_SIZE", "5")),
        help="Number of flyovers per observation bundle (default: 5 or RUNWAY_OBSERVER_BATCH_SIZE)",
    )
    parser.add_argument(
        "--hiatus-min",
        type=float,
        default=float(os.getenv("RUNWAY_OBSERVER_HIATUS_MIN", "30.0")),
        help="Hiatus duration in minutes after a bundle or timeout (default: 30 or RUNWAY_OBSERVER_HIATUS_MIN)",
    )
    parser.add_argument(
        "--timeout-min",
        type=float,
        default=float(os.getenv("RUNWAY_OBSERVER_TIMEOUT_MIN", "30.0")),
        help="Inactivity timeout in minutes without flyovers before entering hiatus (default: 30 or RUNWAY_OBSERVER_TIMEOUT_MIN)",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default="flyovers.jsonl",
        help="Path to JSONL log file (default: flyovers.jsonl)",
    )
    return parser.parse_args()


def run_runway_observer_server(
    port: int = 8081,
    batch_size: int = 5,
    hiatus_min: float = 30.0,
    timeout_min: float = 30.0,
    log_file: str = "flyovers.jsonl",
):
    configure_logging()
    settings = load_settings()

    worker = RunwayObserverWorker(
        settings=settings,
        batch_size=batch_size,
        hiatus_min=hiatus_min,
        timeout_min=timeout_min,
        log_file=log_file,
    )
    worker.sync_recent_flyovers()
    worker.start()

    RunwayObserverRequestHandler.worker = worker
    RunwayObserverRequestHandler.log_file = os.path.abspath(log_file)

    server_address = ("0.0.0.0", port)
    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer(server_address, RunwayObserverRequestHandler)

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"🛫  Runway Observer Server is running!")
    print(f"📡  Listening on          : http://0.0.0.0:{port}")
    print(f"🗂   Runway bundles API    : http://localhost:{port}/api/runways")
    print(f"⚙   Status endpoint       : http://localhost:{port}/api/status")
    print(f"✈   Live bbox aircraft    : http://localhost:{port}/api/live")
    print(f"📄  Flyovers endpoint     : http://localhost:{port}/api/flyovers")
    print(f"📦  Batch size            : {batch_size} flyovers")
    print(f"⏱   Hiatus duration       : {hiatus_min} minutes")
    print(f"⏳  Inactivity timeout    : {timeout_min} minutes")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Runway Observer Server...")
    finally:
        worker.stop()
        httpd.server_close()
        print("Runway Observer Server stopped cleanly.")


if __name__ == "__main__":
    args = parse_args()
    run_runway_observer_server(
        port=args.port,
        batch_size=args.batch_size,
        hiatus_min=args.hiatus_min,
        timeout_min=args.timeout_min,
        log_file=args.log_file,
    )
