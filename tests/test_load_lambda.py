"""Unit tests for Load lambda with mocked dependencies."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def transform_output():
    return {
        "bucket": "agensus",
        "key": "users/123/abc_test.pdf",
        "blob_name": "users/123/abc_test.pdf",
        "job_id": "job-1",
        "summary_blob_name": "summaries/users/123/abc_test.pdf/raw.md",
        "document_id": "doc-123",
        "chunks": [
            {
                "id": None,
                "text": "Introduction content",
                "document_id": "doc-123",
                "chunk_index": 0,
                "metadata": {"H1": "Title"},
            },
            {
                "id": None,
                "text": "Section content",
                "document_id": "doc-123",
                "chunk_index": 1,
                "metadata": {"H1": "Title", "H2": "Section"},
            },
        ],
    }


@patch("lambdas.load.main.compakt_client")
@patch("lambdas.load.main.push_status_event")
@patch("lambdas.load.main.update_ingestion_status")
@patch("lambdas.load.main.store_chunks")
@patch("lambdas.load.main.qdrant")
@patch("lambdas.load.main.vectorizer")
@patch("lambdas.load.main.s3_client")
def test_load_vectorizes_and_stores(
    mock_s3, mock_vectorizer, mock_qdrant, mock_store,
    mock_update, mock_push, mock_compakt, transform_output
):
    # Setup mocks
    mock_vectorizer.batch_vectorize.return_value = [
        [0.1] * 1024,
        [0.2] * 1024,
    ]
    mock_qdrant.get_collections.return_value = MagicMock(collections=[])
    mock_s3.get_object.return_value = {
        "Body": MagicMock(read=lambda: b"# Raw markdown")
    }
    mock_compakt_result = MagicMock()
    mock_compakt_result.summary = "This is a detailed summary."
    mock_compakt.summarize.return_value = mock_compakt_result

    from lambdas.load.main import main

    result = main(transform_output, MagicMock())

    assert result["status"] == "COMPLETED"
    assert result["chunk_count"] == 2
    assert result["vector_count"] == 2

    # Verify vectorization
    mock_vectorizer.batch_vectorize.assert_called_once()

    # Verify Qdrant upsert
    mock_qdrant.upsert.assert_called_once()

    # Verify Postgres storage
    mock_store.assert_called_once()

    # Verify summary upload
    assert mock_s3.put_object.called

    # Verify status progression
    statuses = [call.args[2] for call in mock_push.call_args_list]
    assert "VECTORIZING" in statuses
    assert "VECTORIZED" in statuses
    assert "SUMMARIZING" in statuses
    assert "COMPLETED" in statuses
