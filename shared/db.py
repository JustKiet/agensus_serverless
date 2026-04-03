"""Direct Postgres access for Lambda functions using psycopg2."""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg2
from shared.config import settings

logger = logging.getLogger(__name__)


def _get_connection():
    return psycopg2.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        dbname=settings.POSTGRES_DB,
    )


def update_ingestion_status(
    blob_name: str,
    status: str,
    summary_blob_name: str | None = None,
    error: str | None = None,
    processor: str | None = None,
    chunk_count: int | None = None,
    vector_count: int | None = None,
    completed_at: datetime | None = None,
) -> None:
    """Update an existing ingestion_status record."""
    now = datetime.now(timezone.utc)
    with _get_connection() as conn:
        with conn.cursor() as cur:
            sets = ["status = %s", "updated_at = %s"]
            vals: list[str | datetime | int | None] = [status, now]
            if summary_blob_name is not None:
                sets.append("summary_blob_name = %s")
                vals.append(summary_blob_name)
            if error is not None:
                sets.append("error = %s")
                vals.append(error)
            if processor is not None:
                sets.append("processor = %s")
                vals.append(processor)
            if chunk_count is not None:
                sets.append("chunk_count = %s")
                vals.append(chunk_count)
            if vector_count is not None:
                sets.append("vector_count = %s")
                vals.append(vector_count)
            if completed_at is not None:
                sets.append("completed_at = %s")
                vals.append(completed_at)
            vals.append(blob_name)
            cur.execute(
                f"UPDATE ingestion_status SET {', '.join(sets)} WHERE blob_name = %s",
                vals,
            )
        conn.commit()
    logger.info("Updated ingestion_status for blob=%s to status=%s", blob_name, status)


def store_chunks(
    document_id: str,
    chunks: list[dict[str, Any]],
    qdrant_point_ids: list[str] | None = None,
) -> None:
    """Insert document chunks into the document_chunks table."""
    now = datetime.now(timezone.utc)
    with _get_connection() as conn:
        with conn.cursor() as cur:
            for i, chunk in enumerate(chunks):
                chunk_id = str(uuid.uuid4())
                point_id = qdrant_point_ids[i] if qdrant_point_ids else None
                cur.execute(
                    """
                    INSERT INTO document_chunks
                        (id, document_id, chunk_index, text, metadata_json, qdrant_point_id, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        chunk_id,
                        document_id,
                        chunk.get("chunk_index", i),
                        chunk["text"],
                        json.dumps(chunk.get("metadata", {})),
                        point_id,
                        now,
                        now,
                    ),
                )
        conn.commit()
    logger.info("Stored %d chunks for document_id=%s", len(chunks), document_id)


def create_document(
    title: str,
    document_hash: str,
    blob_name: str,
    user_id: str,
    document_type: str | None = None,
) -> str:
    """Create a document record, returning its ID."""
    doc_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents (id, title, document_hash, blob_name, user_id, document_type, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    doc_id,
                    title,
                    document_hash,
                    blob_name,
                    user_id,
                    document_type,
                    now,
                    now,
                ),
            )
        conn.commit()
    logger.info("Created document id=%s for blob=%s", doc_id, blob_name)
    return doc_id
