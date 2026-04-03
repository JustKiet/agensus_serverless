"""Shared Pydantic models for inter-lambda communication via Step Functions."""

from typing import Any

from pydantic import BaseModel


class ChunkItem(BaseModel):
    id: str | None = None
    text: str
    document_id: str
    chunk_index: int
    metadata: dict[str, Any]


class VectorizedChunkItem(ChunkItem):
    vector: list[float]


class ExtractResult(BaseModel):
    bucket: str
    key: str
    file_type: str
    extracted_text: str
    summary_blob_name: str
    job_id: str
    blob_name: str


class TransformResult(BaseModel):
    bucket: str
    key: str
    blob_name: str
    job_id: str
    summary_blob_name: str
    chunks: list[ChunkItem]


class LoadResult(BaseModel):
    blob_name: str
    job_id: str
    chunk_count: int
    vector_count: int
    status: str
