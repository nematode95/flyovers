import json
import logging
import os
import re
from typing import Any, Callable, Union
from urllib.parse import urlsplit


LOGGER = logging.getLogger("external_api")
MAX_RESPONSE_LOG_BYTES = 1024
_SENSITIVE_KEYS = {
    "accesstoken",
    "api_key",
    "apikey",
    "authorization",
    "clientsecret",
    "idtoken",
    "password",
    "refreshtoken",
    "secret",
    "secretkey",
    "servicerole",
    "servicerolekey",
    "supabaseservicerolekey",
    "token",
}


def _is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return normalized in _SENSITIVE_KEYS


def configure_logging() -> None:
    external_api_logging = os.getenv("LOG_EXTERNAL_API", "false").strip().lower()
    if external_api_logging not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
        raise ValueError(f"Invalid LOG_EXTERNAL_API: {external_api_logging}")
    log_external_api = external_api_logging in {"true", "1", "yes", "on"}

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        raise ValueError(f"Invalid LOG_LEVEL: {level_name}")

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("flyovers.log", encoding="utf-8"),
        ],
        force=True,
    )
    LOGGER.disabled = not log_external_api
    if log_external_api:
        LOGGER.setLevel(logging.DEBUG)
    logging.getLogger("urllib3").setLevel(
        logging.NOTSET if log_external_api else logging.WARNING
    )


def _endpoint(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.netloc}{parsed.path}"


def _redact_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _is_sensitive_key(key) else _redact_json(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    return value


def _redact_text(value: str) -> str:
    sensitive_names = "|".join(
        sorted(
            (r"access[_-]?token", r"api[_-]?key", r"authorization", r"client[_-]?secret",
             r"id[_-]?token", r"password", r"refresh[_-]?token", r"secret[_-]?key",
             r"supabase[_-]?service[_-]?role[_-]?key", r"service[_-]?role(?:[_-]?key)?",
             r"secret", r"token"),
            key=len,
            reverse=True,
        )
    )
    return re.sub(
        rf'(?i)(["\']?(?:{sensitive_names})["\']?\s*[:=]\s*)'
        r'("[^"]*"|\'[^\']*\'|[^,}\s]+)',
        r"\1[REDACTED]",
        value,
    )


def _response_preview(body: Union[str, bytes]) -> str:
    if isinstance(body, bytes):
        text = body.decode("utf-8", errors="replace")
    else:
        text = body

    try:
        safe_text = json.dumps(_redact_json(json.loads(text)), ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        safe_text = _redact_text(text)

    encoded = safe_text.encode("utf-8")
    if len(encoded) <= MAX_RESPONSE_LOG_BYTES:
        return safe_text
    truncated = encoded[:MAX_RESPONSE_LOG_BYTES].decode("utf-8", errors="ignore")
    return f"{truncated}… [truncated at {MAX_RESPONSE_LOG_BYTES} bytes]"


def log_http_response(
    service: str,
    method: str,
    url: str,
    status_code: int,
    body: Union[str, bytes],
) -> None:
    if LOGGER.isEnabledFor(logging.DEBUG):
        try:
            response = _response_preview(body)
        except Exception:
            response = "[response body unavailable]"
        LOGGER.debug(
            "done calling external API service=%s method=%s endpoint=%s http_code=%s response=%s",
            service,
            method,
            _endpoint(url),
            status_code,
            response,
        )


def log_http_error(service: str, method: str, url: str, error: BaseException) -> None:
    if LOGGER.isEnabledFor(logging.DEBUG):
        error_text = _redact_text(str(error))
        error_text = re.sub(
            r"(?i)\burl:\s*(?:https?://)?[^\s'\"<>]+",
            "url:[request parameters redacted]",
            error_text,
        )
        error_text = re.sub(
            r"(?i)\bbearer\s+[a-z0-9._~+/-]+=*",
            "Bearer [REDACTED]",
            error_text,
        )
        LOGGER.debug(
            "done calling external API service=%s method=%s endpoint=%s error=%s",
            service,
            method,
            _endpoint(url),
            error_text,
        )


def logged_request(
    service: str,
    method: str,
    url: str,
    request: Callable[..., Any],
    **kwargs: Any,
) -> Any:
    if LOGGER.isEnabledFor(logging.DEBUG):
        LOGGER.debug(
            "begin calling external API service=%s method=%s endpoint=%s",
            service,
            method.upper(),
            _endpoint(url),
        )
    try:
        response = request(url, **kwargs)
    except Exception as error:
        log_http_error(service, method.upper(), url, error)
        raise

    if LOGGER.isEnabledFor(logging.DEBUG):
        log_http_response(service, method.upper(), url, response.status_code, response.text)
    return response


def log_call_started(service: str, method: str, url: str) -> None:
    if LOGGER.isEnabledFor(logging.DEBUG):
        LOGGER.debug(
            "begin calling external API service=%s method=%s endpoint=%s",
            service,
            method.upper(),
            _endpoint(url),
        )
