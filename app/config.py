import os

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


class Settings:
    APP_NAME = "TrustiPay Central Ledger API"
    APP_VERSION = "2.1.0"

    SECURITY_ENDPOINT_URL = os.getenv("SECURITY_ENDPOINT_URL", "")
    SECURITY_TIMEOUT_SECONDS = _env_float("SECURITY_TIMEOUT_SECONDS", 5.0)
    FRAUD_ENDPOINT_URL = os.getenv("FRAUD_ENDPOINT_URL", "")
    FRAUD_TIMEOUT_SECONDS = _env_float("FRAUD_TIMEOUT_SECONDS", 5.0)

    QUEUE_MAX_SECURITY_RETRIES = _env_int("QUEUE_MAX_SECURITY_RETRIES", 3)
    QUEUE_RETRY_BACKOFF_SECONDS = _env_float("QUEUE_RETRY_BACKOFF_SECONDS", 2.0)
    QUEUE_POLL_INTERVAL_SECONDS = _env_float("QUEUE_POLL_INTERVAL_SECONDS", 1.0)

    ENABLE_QUEUE_WORKER = _env_bool("ENABLE_QUEUE_WORKER", True)


settings = Settings()
