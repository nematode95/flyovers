import os
from datetime import datetime, timezone
from typing import Any

import requests

from api_logging import logged_request


def _get_credentials(action_description: str) -> tuple[str, str] | None:
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not supabase_url and not service_role_key:
        return None
    if not supabase_url or not service_role_key:
        raise RuntimeError(f"Both SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required to {action_description}.")
    return supabase_url, service_role_key


def _post_to_supabase(
    action_label: str,
    table: str,
    payload: dict[str, Any],
    params: dict[str, str] | None = None,
    prefer: str = "resolution=merge-duplicates,return=minimal",
) -> bool:
    creds = _get_credentials(f"sync {table}")
    if creds is None:
        return False
    supabase_url, service_role_key = creds

    endpoint = f"{supabase_url}/rest/v1/{table}"
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer

    response = logged_request(
        action_label,
        "POST",
        endpoint,
        requests.post,
        params=params,
        headers=headers,
        json=payload,
        timeout=10,
    )
    response.raise_for_status()
    return True


def upsert_live_snapshot(snapshot: dict[str, Any]) -> bool:
    creds = _get_credentials("sync live snapshots")
    if creds is None:
        return False
    supabase_url, service_role_key = creds

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

    creds = _get_credentials("sync recent flyovers")
    if creds is None:
        return False
    supabase_url, service_role_key = creds

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


def insert_runway_observation_batch(batch_payload: dict[str, Any]) -> bool:
    creds = _get_credentials("insert runway observations")
    if creds is None:
        return False
    supabase_url, service_role_key = creds

    endpoint = f"{supabase_url}/rest/v1/runway_observations"
    response = logged_request(
        "Supabase runway observations batch",
        "POST",
        endpoint,
        requests.post,
        headers={
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json=batch_payload,
        timeout=10,
    )
    response.raise_for_status()
    return True

