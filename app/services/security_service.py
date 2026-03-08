from dataclasses import dataclass

import httpx

from app.config import settings


class SecurityTransportError(Exception):
    pass


@dataclass
class SecurityResult:
    decision: str
    reason: str | None = None


def verify_transaction(payload: dict) -> SecurityResult:
    if not settings.SECURITY_ENDPOINT_URL:
        raise SecurityTransportError("SECURITY_ENDPOINT_URL is not configured")

    try:
        response = httpx.post(
            settings.SECURITY_ENDPOINT_URL,
            json=payload,
            timeout=settings.SECURITY_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise SecurityTransportError(str(exc)) from exc

    if response.status_code >= 500:
        raise SecurityTransportError(f"Security endpoint 5xx response: {response.status_code}")

    if response.status_code >= 400:
        return SecurityResult(decision="FAIL", reason=f"SECURITY_HTTP_{response.status_code}")

    try:
        body = response.json()
    except ValueError as exc:
        raise SecurityTransportError("Security endpoint returned non-JSON body") from exc

    decision = str(body.get("decision", "")).upper().strip()
    reason = body.get("reason")

    if decision not in {"PASS", "FAIL", "REVIEW"}:
        raise SecurityTransportError("Security endpoint returned invalid decision")

    return SecurityResult(decision=decision, reason=reason)
