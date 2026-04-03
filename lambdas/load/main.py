"""Load lambda: vectorizes chunks, stores in Qdrant + Postgres, generates summary via compakt."""

import logging
import uuid
from datetime import datetime, timezone

import boto3
from aws_lambda_typing import context
from compakt import Compakt
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from shared.config import settings
from shared.db import store_chunks, update_ingestion_status
from shared.sqs import push_status_event
from shared.vectorizer import SyncVoyageAIVectorizer

logger = logging.getLogger()

s3_client = boto3.client(
    "s3",
    region_name=settings.S3_REGION,
    endpoint_url=settings.S3_ENDPOINT_URL or None,
)

vectorizer = SyncVoyageAIVectorizer()
qdrant = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
compakt_client = Compakt()


def _ensure_qdrant_collection(vector_size: int) -> None:
    """Create collection if it doesn't exist."""
    collections = [c.name for c in qdrant.get_collections().collections]
    if settings.QDRANT_COLLECTION not in collections:
        qdrant.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection: %s", settings.QDRANT_COLLECTION)


def main(event: dict, context: context.Context) -> dict:
    """
    Load lambda invoked by Step Functions after Transform.

    Input (from Transform):
        bucket, key, blob_name, job_id, summary_blob_name, document_id, chunks
    Output:
        LoadResult dict with final status.
    """
    bucket = event["bucket"]
    blob_name = event["blob_name"]
    job_id = event["job_id"]
    summary_blob_name = event["summary_blob_name"]
    document_id = event["document_id"]
    chunks = event["chunks"]

    # --- Vectorize ---
    push_status_event(blob_name, job_id, "VECTORIZING", processor="load")

    texts = [c["text"] for c in chunks]
    vectors = vectorizer.batch_vectorize(texts, input_type="document")

    logger.info(f"Vectorized {len(vectors)} chunks")

    # --- Store in Qdrant ---
    if vectors:
        _ensure_qdrant_collection(vector_size=len(vectors[0]))

    point_ids = [str(uuid.uuid4()) for _ in chunks]
    points = [
        PointStruct(
            id=point_ids[i],
            vector=vectors[i],
            payload={
                "document_id": document_id,
                "chunk_index": chunks[i].get("chunk_index", i),
                "text": chunks[i]["text"],
                "metadata": chunks[i].get("metadata", {}),
            },
        )
        for i in range(len(chunks))
    ]

    if points:
        qdrant.upsert(
            collection_name=settings.QDRANT_COLLECTION,
            points=points,
        )
        logger.info(f"Upserted {len(points)} points to Qdrant")

    # --- Store chunks in Postgres ---
    store_chunks(
        document_id=document_id,
        chunks=chunks,
        qdrant_point_ids=point_ids,
    )

    update_ingestion_status(
        blob_name=blob_name,
        status="VECTORIZED",
        processor="load",
        vector_count=len(vectors),
    )

    push_status_event(blob_name, job_id, "VECTORIZED", processor="load")

    # --- Generate summary via compakt ---
    push_status_event(blob_name, job_id, "SUMMARIZING", processor="load")

    try:
        # compakt can summarize from an S3/local file or raw text
        # Download the raw markdown from S3 to a temp path for compakt
        raw_obj = s3_client.get_object(Bucket=bucket, Key=summary_blob_name)
        raw_markdown = raw_obj["Body"].read().decode("utf-8")

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write(raw_markdown)
            temp_path = f.name

        result = compakt_client.summarize(temp_path)
        summary_text = result.summary

        # Upload final summary to S3, replacing raw
        s3_client.put_object(
            Bucket=bucket,
            Key=summary_blob_name,
            Body=summary_text.encode("utf-8"),
            ContentType="text/markdown",
        )
        logger.info(f"Updated summary at s3://{bucket}/{summary_blob_name}")
    except Exception:
        logger.exception("Failed to generate summary, keeping raw text")

    # --- Final status ---
    now = datetime.now(timezone.utc)
    update_ingestion_status(
        blob_name=blob_name,
        status="COMPLETED",
        processor="load",
        completed_at=now,
    )

    push_status_event(blob_name, job_id, "COMPLETED", processor="load")

    return {
        "blob_name": blob_name,
        "job_id": job_id,
        "chunk_count": len(chunks),
        "vector_count": len(vectors),
        "status": "COMPLETED",
    }
