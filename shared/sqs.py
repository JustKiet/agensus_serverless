"""SQS helper for publishing ingestion status events from Lambda functions."""

import json
import logging
from typing import Any

import boto3
from shared.config import settings

logger = logging.getLogger(__name__)

sqs_client = boto3.client(
    "sqs",
    region_name=settings.SQS_REGION,
    endpoint_url=settings.SQS_ENDPOINT_URL or None,
)


def push_status_event(
    blob_name: str,
    job_id: str,
    status: str,
    summary_blob_name: str | None = None,
    error: str | None = None,
    processor: str | None = None,
) -> None:
    """Publish an ingestion status event to SQS."""
    payload: dict[str, Any] = {
        "blob_name": blob_name,
        "job_id": job_id,
        "status": status,
        "summary_blob_name": summary_blob_name,
        "error": error,
        "processor": processor,
    }
    try:
        sqs_client.send_message(
            QueueUrl=settings.SQS_QUEUE_URL,
            MessageBody=json.dumps(payload),
        )
        logger.info("Pushed SQS status=%s for blob=%s", status, blob_name)
    except Exception:
        logger.warning(
            "Failed to push SQS event for blob=%s status=%s, falling back to webhook",
            blob_name,
            status,
        )
        # Fallback to HTTP webhook
        from shared.callbacks import notify_backend

        notify_backend(
            blob_name=blob_name,
            job_id=job_id,
            status=status,
            summary_blob_name=summary_blob_name,
            error=error,
            processor=processor,
        )
