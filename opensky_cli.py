#!/usr/bin/env python3
"""
OpenSky API CLI Wrapper
A simplified command line tool for querying OpenSky Network REST API (departures and arrivals).
Defaults to KBWI airport and supports intuitive relative time flags like -s7 -e2 (7 hours ago to 2 hours ago).
Reads credentials automatically from .env.
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Union, List

from api_logging import configure_logging,  log_call_started, log_http_error, log_http_response, logged_request

# Try importing requests; fallback to urllib.request if unavailable
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    HAS_REQUESTS = False

DEFAULT_AIRPORT = "KBWI"


def load_env(env_path: str = ".env") -> None:
    """Load environment variables from .env file without external dependencies."""
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
        return
    except ImportError:
        pass

    target_path = env_path
    if not os.path.isabs(target_path):
        if not os.path.exists(target_path):
            script_dir_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), env_path)
            if os.path.exists(script_dir_env):
                target_path = script_dir_env

    if os.path.exists(target_path):
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        v_str = v.strip().strip("'\"")
                        os.environ.setdefault(k.strip(), v_str)
        except Exception as e:
            sys.stderr.write(f"Warning: Failed reading {target_path}: {e}\n")


class OpenSkyAuth:
    """Manages authentication token retrieval and caching for OpenSky API."""
    
    TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"

    def __init__(
        self,
        token: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        self.explicit_token = token or os.getenv("OPENSKY_BEARER_TOKEN") or os.getenv("OPENSKY_TOKEN") or os.getenv("TOKEN")
        self.client_id = (client_id or os.getenv("OPENSKY_CLIENT_ID") or "").strip()
        self.client_secret = (client_secret or os.getenv("OPENSKY_CLIENT_SECRET") or "").strip()
        
        self.cached_token: Optional[str] = None
        self.token_expiry: float = 0.0

    def get_bearer_token(self) -> Optional[str]:
        if self.explicit_token:
            return self.explicit_token

        now = time.time()
        if self.cached_token and now < self.token_expiry:
            return self.cached_token

        if self.client_id and self.client_secret and self.client_id != "your_client_id_here":
            token, expires_in = self._request_oauth_token()
            if token:
                self.cached_token = token
                self.token_expiry = now + max(expires_in - 30, 60)
                return self.cached_token

        return None

    def _request_oauth_token(self) -> tuple[Optional[str], int]:
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        if HAS_REQUESTS:
            try:
                resp = logged_request(
                    "OpenSky CLI OAuth",
                    "POST",
                    self.TOKEN_URL,
                    requests.post,
                    data=data,
                    timeout=10,
                )
                if resp.status_code == 200:
                    res_json = resp.json()
                    return res_json.get("access_token"), res_json.get("expires_in", 1800)
                else:
                    sys.stderr.write(f"[Auth Error] Failed ({resp.status_code}): {resp.text[:200]}\n")
            except Exception as e:
                sys.stderr.write(f"[Auth Error] Request exception: {e}\n")
        else:
            try:
                import urllib.parse
                encoded_data = urllib.parse.urlencode(data).encode("utf-8")
                req = urllib.request.Request(self.TOKEN_URL, data=encoded_data, method="POST")
                req.add_header("Content-Type", "application/x-www-form-urlencoded")
                log_call_started("OpenSky CLI OAuth", "POST", self.TOKEN_URL)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    response_body = resp.read()
                    log_http_response("OpenSky CLI OAuth", "POST", self.TOKEN_URL, resp.status, response_body)
                    if resp.status == 200:
                        res_json = json.loads(response_body.decode("utf-8"))
                        return res_json.get("access_token"), res_json.get("expires_in", 1800)
            except urllib.error.HTTPError as e:
                response_body = e.read()
                log_http_response("OpenSky CLI OAuth", "POST", self.TOKEN_URL, e.code, response_body)
                sys.stderr.write(f"[Auth Error] Failed ({e.code}): {response_body.decode('utf-8')[:200]}\n")
            except Exception as e:
                log_http_error("OpenSky CLI OAuth", "POST", self.TOKEN_URL, e)
                sys.stderr.write(f"[Auth Error] Request exception: {e}\n")

        return None, 0

    def get_headers(self) -> Dict[str, str]:
        headers = {"User-Agent": "opensky-cli/1.0"}
        token = self.get_bearer_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers


def parse_time_param(val: Optional[Union[str, int, float]], default_hours_ago: float = 0.0) -> int:
    """
    Parse start/end time parameters:
    - Numbers like 7, -7, '7' -> 7 hours ago
    - 'now', 0 -> current timestamp
    - Unix epoch integer (> 100000) -> epoch timestamp
    - Relative string ('7h', '30m', '1d') -> offset from now
    - ISO date string -> timestamp
    """
    now = int(time.time())
    if val is None or val == "":
        return int(now - (default_hours_ago * 3600))

    if isinstance(val, (int, float)):
        if abs(val) < 10000:
            return int(now - abs(val) * 3600)
        return int(val)

    val_str = str(val).strip()

    if val_str.lower() in ("now", "0", "-0"):
        return now

    # Check numeric value (hours ago vs epoch)
    try:
        num = float(val_str)
        if abs(num) < 10000:
            return int(now - abs(num) * 3600)
        return int(num)
    except ValueError:
        pass

    # Relative time string (e.g. 7h, 30m, 1d)
    val_clean = val_str.replace("-", "")
    if val_clean.endswith("h") and val_clean[:-1].isdigit():
        return int(now - float(val_clean[:-1]) * 3600)
    if val_clean.endswith("m") and val_clean[:-1].isdigit():
        return int(now - float(val_clean[:-1]) * 60)
    if val_clean.endswith("d") and val_clean[:-1].isdigit():
        return int(now - float(val_clean[:-1]) * 86400)

    # ISO or standard date formats
    date_formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in date_formats:
        try:
            dt = datetime.strptime(val_str, fmt)
            return int(dt.replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            pass

    try:
        dt = datetime.fromisoformat(val_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        raise ValueError(
            f"Invalid timestamp or hours format: '{val_str}'. Use hours ago (e.g. 7 or -s7), Unix timestamp, or ISO date."
        )


def make_api_request(url: str, params: Dict[str, Any], headers: Dict[str, str]) -> Any:
    """Execute HTTP GET request to OpenSky REST API."""
    if HAS_REQUESTS:
        try:
            resp = logged_request(
                "OpenSky CLI data",
                "GET",
                url,
                requests.get,
                params=params,
                headers=headers,
                timeout=20,
            )
            if resp.status_code == 200:
                return resp.json()
            else:
                sys.stderr.write(f"HTTP Error {resp.status_code}: {resp.text[:300]}\n")
                if resp.status_code == 400:
                    sys.stderr.write("Note: OpenSky flight endpoints limit query interval to maximum 7 days.\n")
                sys.exit(1)
        except requests.RequestException as e:
            sys.stderr.write(f"Network error: {e}\n")
            sys.exit(1)
    else:
        import urllib.parse
        query_string = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        full_url = f"{url}?{query_string}" if query_string else url
        req = urllib.request.Request(full_url, headers=headers, method="GET")
        log_call_started("OpenSky CLI data", "GET", url)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                response_body = resp.read()
                log_http_response("OpenSky CLI data", "GET", url, resp.status, response_body)
                if resp.status == 200:
                    return json.loads(response_body.decode("utf-8"))
        except urllib.error.HTTPError as e:
            response_body = e.read()
            log_http_response("OpenSky CLI data", "GET", url, e.code, response_body)
            body = response_body.decode("utf-8")
            sys.stderr.write(f"HTTP Error {e.code}: {body[:300]}\n")
            if e.code == 400:
                sys.stderr.write("Note: OpenSky flight endpoints limit query interval to maximum 7 days.\n")
            sys.exit(1)
        except Exception as e:
            log_http_error("OpenSky CLI data", "GET", url, e)
            sys.stderr.write(f"Network error: {e}\n")
            sys.exit(1)


def add_human_timestamps(data: Any) -> Any:
    """Recursively enrich timestamp fields in JSON response with human-readable ISO UTC dates."""
    if isinstance(data, list):
        return [add_human_timestamps(item) for item in data]
    elif isinstance(data, dict):
        new_dict = {}
        for key, val in data.items():
            new_dict[key] = val
            if key in ("firstSeen", "lastSeen", "time", "estDepartureTime", "estArrivalTime") and isinstance(val, (int, float)) and val > 1000000000:
                utc_str = datetime.fromtimestamp(val, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                new_dict[f"{key}_formatted"] = utc_str
            elif isinstance(val, (dict, list)):
                new_dict[key] = add_human_timestamps(val)
        return new_dict
    return data


def print_table(data: List[Dict[str, Any]]) -> None:
    """ASCII table formatter for flight departure/arrival data."""
    if not isinstance(data, list) or not data:
        print("No records found.")
        return

    if isinstance(data[0], dict):
        headers = ["callsign", "icao24", "estDepartureAirport", "estArrivalAirport", "firstSeen", "lastSeen"]
        sample = data[0]
        active_headers = [h for h in headers if h in sample] or list(sample.keys())[:6]

        rows = []
        for item in data:
            row = []
            for h in active_headers:
                val = item.get(h)
                if h in ("firstSeen", "lastSeen", "time") and isinstance(val, (int, float)):
                    val = datetime.fromtimestamp(val, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
                row.append(str(val) if val is not None else "")
            rows.append(row)

        col_widths = [len(h) for h in active_headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(cell))

        header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(active_headers))
        sep_line = "-+-".join("-" * col_widths[i] for i in range(len(active_headers)))
        print(header_line)
        print(sep_line)
        for row in rows:
            print(" | ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(row)))
    else:
        print(json.dumps(data, indent=2))


def build_parser() -> argparse.ArgumentParser:
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument("-a", "--airport", default=DEFAULT_AIRPORT, help=f"ICAO airport code (default: {DEFAULT_AIRPORT})")
    common_parser.add_argument("-s", "--start", "--begin", "-b", dest="start", help="Start time: hours ago (e.g. 7 or -s7), Unix timestamp, or ISO date")
    common_parser.add_argument("-e", "--end", help="End time: hours ago (e.g. 2 or -e2), 'now', Unix timestamp, or ISO date")
    common_parser.add_argument("--env-file", default=".env", help="Path to .env file (default: .env)")
    common_parser.add_argument("-o", "--out", help="Save JSON output to file")
    common_parser.add_argument("-c", "--compact", action="store_true", help="Output minified JSON")
    common_parser.add_argument("-d", "--human-dates", action="store_true", help="Add formatted UTC dates to JSON")
    common_parser.add_argument("-t", "--table", action="store_true", help="Output ASCII table instead of JSON")

    parser = argparse.ArgumentParser(
        parents=[common_parser],
        description=f"Simple OpenSky Network REST API CLI for Departures and Arrivals.\nDefaults to airport: {DEFAULT_AIRPORT}.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  # Departures for KBWI from 7 hours ago to 2 hours ago:
  python opensky_cli.py departures -s7 -e2

  # Arrivals for KBWI for the last 4 hours:
  python opensky_cli.py arrivals -s4

  # Departures at Frankfurt (EDDF) from 12 hours ago to 2 hours ago in table view:
  python opensky_cli.py departures -a EDDF -s 12 -e 2 -t

  # Default query (departures for KBWI for the last 2 hours):
  python opensky_cli.py
        """,
    )

    subparsers = parser.add_subparsers(dest="endpoint", help="Action (departures or arrivals)")

    # 1. DEPARTURES
    subparsers.add_parser("departure", aliases=["departures", "dep"], parents=[common_parser], help="Get departures (default)")

    # 2. ARRIVALS
    subparsers.add_parser("arrival", aliases=["arrivals", "arr"], parents=[common_parser], help="Get arrivals")

    # 3. STATES (optional)
    p_st = subparsers.add_parser("states", parents=[common_parser], help="Get live states")
    p_st.add_argument("--icao24", help="Filter by ICAO24 hex address")

    # 4. TRACKS (optional)
    p_tr = subparsers.add_parser("track", aliases=["tracks"], parents=[common_parser], help="Get aircraft track")
    p_tr.add_argument("--icao24", help="ICAO24 hex address")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Load credentials automatically from .env
    load_env(args.env_file)
    configure_logging()
    auth = OpenSkyAuth()

    # Default to departures if no subcommand given
    endpoint_name = (args.endpoint or "departures").lower()

    # Resolve time range: default start to 2 hours ago if not provided, end to now (0 hours ago)
    begin_ts = parse_time_param(args.start, default_hours_ago=2.0)
    end_ts = parse_time_param(args.end, default_hours_ago=0.0)

    # Ensure begin <= end
    if begin_ts > end_ts:
        begin_ts, end_ts = end_ts, begin_ts

    base_url = "https://opensky-network.org/api"
    airport_code = (args.airport or DEFAULT_AIRPORT).upper()

    if endpoint_name in ("departure", "departures", "dep"):
        api_url = f"{base_url}/flights/departure"
        params = {"airport": airport_code, "begin": begin_ts, "end": end_ts}

    elif endpoint_name in ("arrival", "arrivals", "arr"):
        api_url = f"{base_url}/flights/arrival"
        params = {"airport": airport_code, "begin": begin_ts, "end": end_ts}

    elif endpoint_name == "states":
        api_url = f"{base_url}/states/all"
        params = {}
        if getattr(args, "icao24", None):
            params["icao24"] = args.icao24.lower()

    elif endpoint_name in ("track", "tracks"):
        if not getattr(args, "icao24", None):
            sys.stderr.write("Error: --icao24 required for track endpoint\n")
            sys.exit(1)
        api_url = f"{base_url}/tracks/all"
        params = {"icao24": args.icao24.lower()}

    else:
        sys.stderr.write(f"Unknown command: {endpoint_name}\n")
        sys.exit(1)

    headers = auth.get_headers()
    data = make_api_request(api_url, params, headers)

    if args.human_dates:
        data = add_human_timestamps(data)

    if args.table:
        print_table(data)
    else:
        if args.compact:
            json_output = json.dumps(data, separators=(",", ":"))
        else:
            json_output = json.dumps(data, indent=2)

        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(json_output + "\n")
            print(f"Output saved to {args.out}")
        else:
            print(json_output)


if __name__ == "__main__":
    main()
