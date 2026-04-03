import logging
from typing import Any

import httpx
from shared.config import settings

logger = logging.getLogger(__name__)


def notify_backend(
    blob_name: str,
    job_id: str,
    status: str,
    summary_blob_name: str | None = None,
    error: str | None = None,
    processor: str | None = None,
) -> None:
    """Call the FastAPI webhook to push a status update to WebSocket clients."""
    payload: dict[str, Any] = {
        "blob_name": blob_name,
        "job_id": job_id,
        "status": status,
        "summary_blob_name": summary_blob_name,
        "error": error,
        "processor": processor,
    }
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                settings.BACKEND_WEBHOOK_URL,
                json=payload,
                headers={"X-Webhook-Secret": settings.WEBHOOK_SECRET},
            )
            resp.raise_for_status()
    except Exception:
        logger.warning(
            "Failed to notify backend webhook for blob=%s status=%s",
            blob_name,
            status,
        )
