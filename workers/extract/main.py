"""Extract worker: polls Step Functions Activity queue and processes documents.

Runs as a long-lived process on EC2 (or any Docker host). Docling models are
loaded once at startup and reused across all jobs — no cold-start overhead.

Environment variables (from shared.config + worker-specific):
    SFN_ACTIVITY_ARN   — Step Functions activity ARN to poll
    SFN_ENDPOINT_URL   — LocalStack SFN endpoint (empty = real AWS)
    All shared.config vars (S3, SQS, Postgres, etc.)
"""

import json
import logging
import os
import tempfile
from typing import Any

import boto3
import magic
from docling.document_converter import DocumentConverter
from shared.config import settings
from shared.db import update_ingestion_status
from shared.sqs import push_status_event

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level singletons — initialised once, reused across all jobs
# ---------------------------------------------------------------------------
s3_client = boto3.client(
    "s3",
    region_name=settings.S3_REGION,
    endpoint_url=settings.S3_ENDPOINT_URL or None,
)

_sfn_endpoint = os.environ.get("SFN_ENDPOINT_URL") or None
sfn_client = boto3.client(
    "stepfunctions",
    region_name=settings.SQS_REGION,  # reuse same region
    endpoint_url=_sfn_endpoint,
)

logger.info("Loading Docling models (this runs once at startup)...")
document_converter = DocumentConverter()
logger.info("Docling models ready.")

SFN_ACTIVITY_ARN: str = os.environ["SFN_ACTIVITY_ARN"]
PAGE_BREAK_PLACEHOLDER = "<---PAGE_BREAK--->"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _detect_file_type(blob: bytes) -> str:
    mime_type = magic.from_buffer(blob, mime=True)
    logger.info("Detected MIME type: %s", mime_type)
    return mime_type


def _download_source_blob(bucket: str, key: str) -> bytes:
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


def _convert_to_markdown(blob: bytes, mime_type: str) -> str:
    suffix_map = {
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "text/plain": ".txt",
        "text/markdown": ".md",
    }
    suffix = suffix_map.get(mime_type, ".bin")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(blob)
        tmp_path = tmp.name

    try:
        result = document_converter.convert(tmp_path)
        return result.document.export_to_markdown()
    finally:
        os.unlink(tmp_path)


def _upload_raw_markdown(bucket: str, job_id: str, markdown: str) -> str:
    summary_blob_name = f"summaries/{job_id}.md"
    s3_client.put_object(
        Bucket=bucket,
        Key=summary_blob_name,
        Body=markdown.encode("utf-8"),
        ContentType="text/markdown",
    )
    return summary_blob_name


# ---------------------------------------------------------------------------
# Task processing
# ---------------------------------------------------------------------------
def _process_task(task_token: str, event: dict[str, Any]) -> None:
    bucket: str = event["bucket"]
    key: str = event["key"]
    blob_name: str = event["blob_name"]
    job_id: str = event["job_id"]

    push_status_event(blob_name, job_id, "EXTRACTING", processor="extract-worker")
    update_ingestion_status(blob_name=blob_name, status="EXTRACTING", processor="extract-worker")

    blob = _download_source_blob(bucket, key)
    mime_type = _detect_file_type(blob)
    extracted_text = _convert_to_markdown(blob, mime_type)

    summary_blob_name = _upload_raw_markdown(bucket, job_id, extracted_text)

    update_ingestion_status(
        blob_name=blob_name,
        status="EXTRACTED",
        summary_blob_name=summary_blob_name,
        processor="extract-worker",
    )
    push_status_event(
        blob_name,
        job_id,
        "EXTRACTED",
        summary_blob_name=summary_blob_name,
        processor="extract-worker",
    )

    result = {
        "bucket": bucket,
        "key": key,
        "blob_name": blob_name,
        "job_id": job_id,
        "extracted_text": extracted_text,
        "summary_blob_name": summary_blob_name,
    }
    sfn_client.send_task_success(
        taskToken=task_token,
        output=json.dumps(result),
    )
    logger.info("Sent SendTaskSuccess for job_id=%s", job_id)


# ---------------------------------------------------------------------------
# Main polling loop
# ---------------------------------------------------------------------------
def run() -> None:
    logger.info("Extract worker started, polling activity: %s", SFN_ACTIVITY_ARN)
    while True:
        try:
            resp = sfn_client.get_activity_task(
                activityArn=SFN_ACTIVITY_ARN,
                workerName="extract-worker",
            )
        except Exception:
            logger.exception("get_activity_task failed, retrying in 5s")
            import time
            time.sleep(5)
            continue

        task_token = resp.get("taskToken")
        if not task_token:
            # Long-poll returned nothing — loop immediately
            continue

        raw_input = resp.get("input", "{}")
        event: dict[str, Any] = json.loads(raw_input)
        logger.info("Received task for job_id=%s", event.get("job_id"))

        try:
            _process_task(task_token, event)
        except Exception as exc:
            logger.exception("Extract failed for job_id=%s", event.get("job_id"))
            try:
                sfn_client.send_task_failure(
                    taskToken=task_token,
                    error=type(exc).__name__,
                    cause=str(exc)[:256],
                )
            except Exception:
                logger.exception("send_task_failure also failed")


if __name__ == "__main__":
    run()
