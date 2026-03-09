import httpx

from app.config import settings


class FraudDispatchError(Exception):
    pass


def submit_to_fraud_component(payload: dict, trace_id: str, source_type: str) -> None:
    """
    Sends a transaction to the external fraud component for asynchronous decisioning.
    The fraud component is expected to callback this service with the final decision.
    """
    if not settings.FRAUD_ENDPOINT_URL:
        raise FraudDispatchError("FRAUD_ENDPOINT_URL is not configured")

    body = {
        "trace_id": trace_id,
        "source_type": source_type,
        "transaction": payload,
    }

    try:
        response = httpx.post(
            settings.FRAUD_ENDPOINT_URL,
            json=body,
            timeout=settings.FRAUD_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise FraudDispatchError(str(exc)) from exc

    if response.status_code >= 500:
        raise FraudDispatchError(f"Fraud endpoint 5xx response: {response.status_code}")

    if response.status_code >= 400:
        raise FraudDispatchError(f"Fraud endpoint 4xx response: {response.status_code}")
