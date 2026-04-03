"""Unit tests for Transform lambda with mocked dependencies."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def extract_output():
    return {
        "bucket": "agensus",
        "key": "users/123/abc_test.pdf",
        "blob_name": "users/123/abc_test.pdf",
        "job_id": "job-1",
        "extracted_text": "# Title\n\nSome content\n\n## Section\n\nMore content",
        "summary_blob_name": "summaries/users/123/abc_test.pdf/raw.md",
    }


@patch("lambdas.transform.main.push_status_event")
@patch("lambdas.transform.main.update_ingestion_status")
@patch("lambdas.transform.main.create_document", return_value="doc-123")
def test_transform_chunks_text(mock_create_doc, mock_update, mock_push, extract_output):
    from lambdas.transform.main import main

    result = main(extract_output, MagicMock())

    assert result["document_id"] == "doc-123"
    assert result["blob_name"] == "users/123/abc_test.pdf"
    assert result["job_id"] == "job-1"
    assert len(result["chunks"]) > 0

    # Verify document was created
    mock_create_doc.assert_called_once()
    call_kwargs = mock_create_doc.call_args
    assert call_kwargs[1]["blob_name"] == "users/123/abc_test.pdf"

    # Verify status events
    statuses = [call.args[2] for call in mock_push.call_args_list]
    assert "CHUNKING" in statuses
    assert "CHUNKED" in statuses

    # Verify DB update
    mock_update.assert_called_once()


@patch("lambdas.transform.main.push_status_event")
@patch("lambdas.transform.main.update_ingestion_status")
@patch("lambdas.transform.main.create_document", return_value="doc-456")
def test_transform_empty_text(mock_create_doc, mock_update, mock_push, extract_output):
    extract_output["extracted_text"] = ""

    from lambdas.transform.main import main

    result = main(extract_output, MagicMock())

    assert result["document_id"] == "doc-456"
    assert len(result["chunks"]) == 0
