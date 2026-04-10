"""Transform lambda: chunks extracted markdown text."""

import hashlib
import logging
from typing import Any

from aws_lambda_typing import context
from shared.chunker import MarkdownChunker
from shared.db import create_document, update_ingestion_status
from shared.sqs import push_status_event

logger = logging.getLogger()

chunker = MarkdownChunker()


def main(event: dict[str, Any], context: context.Context) -> dict[str, Any]:
    """
    Transform lambda invoked by Step Functions after Extract.

    Input (from Extract):
        bucket, key, blob_name, job_id, extracted_text, summary_blob_name
    Output:
        TransformResult dict with chunks for Load lambda.
    """
    bucket: str = event["bucket"]
    key: str = event["key"]
    blob_name: str = event["blob_name"]
    job_id: str = event["job_id"]
    extracted_text: str = event["extracted_text"]
    summary_blob_name: str = event["summary_blob_name"]

    push_status_event(blob_name, job_id, "CHUNKING", processor="transform")

    # Create document record
    document_hash = hashlib.sha256(extracted_text.encode()).hexdigest()
    # Extract user_id from blob_name pattern: users/{user_id}/{uuid}_{filename}
    parts = blob_name.split("/")
    user_id = parts[1] if len(parts) > 1 else "unknown"
    filename = parts[-1].split("_", 1)[-1] if parts else key

    document_id = create_document(
        title=filename,
        document_hash=document_hash,
        blob_name=blob_name,
        user_id=user_id,
    )

    # Chunk the extracted text
    chunks = chunker.chunk(extracted_text, document_id, user_id)
    logger.info(f"Chunked into {len(chunks)} chunks for document_id={document_id}")

    # Update ingestion status
    update_ingestion_status(
        blob_name=blob_name,
        status="CHUNKED",
        processor="transform",
        chunk_count=len(chunks),
    )

    push_status_event(
        blob_name,
        job_id,
        "CHUNKED",
        processor="transform",
    )

    return {
        "bucket": bucket,
        "key": key,
        "blob_name": blob_name,
        "job_id": job_id,
        "summary_blob_name": summary_blob_name,
        "document_id": document_id,
        "user_id": user_id,
        "chunks": [chunk.model_dump() for chunk in chunks],
    }
