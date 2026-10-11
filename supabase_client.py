import os
from datetime import datetime, timezone
from typing import Any

import requests

from api_logging import logged_request


def upsert_live_snapshot(snapshot: dict[str, Any]) -> bool:
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not supabase_url and not service_role_key:
        return False
    if not supabase_url or not service_role_key:
        raise RuntimeError("Both SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required to sync live snapshots.")

    endpoint = f"{supabase_url}/rest/v1/live_snapshot"
    response = logged_request(
        "Supabase live snapshot",
        "POST",
        endpoint,
        requests.post,
        params={"on_conflict": "id"},
        headers={
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        json={
            "id": "current",
            "payload": snapshot,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        timeout=10,
    )
    response.raise_for_status()
    return True


def upsert_recent_flyovers(flyovers: list[dict[str, Any]]) -> bool:
    if len(flyovers) > 5:
        raise ValueError("At most five recent flyovers can be synced.")

    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not supabase_url and not service_role_key:
        return False
    if not supabase_url or not service_role_key:
        raise RuntimeError("Both SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required to sync recent flyovers.")

    endpoint = f"{supabase_url}/rest/v1/recent_flyovers"
    response = logged_request(
        "Supabase recent flyovers",
        "POST",
        endpoint,
        requests.post,
        params={"on_conflict": "id"},
        headers={
            "apikey": service_role_key,
            "Authorization": "******",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        json={
            "id": "current",
            "flyovers": flyovers,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        timeout=10,
    )
    response.raise_for_status()
    return True
