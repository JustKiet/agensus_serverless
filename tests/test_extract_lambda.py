"""Unit tests for Extract lambda with mocked S3 and Docling."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def s3_event():
    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "agensus"},
                    "object": {"key": "users/123/abc_test.pdf"},
                }
            }
        ],
        "job_id": "job-1",
    }


@pytest.fixture
def step_functions_input():
    return {
        "bucket": "agensus",
        "key": "users/123/abc_test.pdf",
        "job_id": "job-1",
        "blob_name": "users/123/abc_test.pdf",
    }


@patch("lambdas.extract.main.push_status_event")
@patch("lambdas.extract.main.s3_client")
@patch("lambdas.extract.main.document_converter")
@patch("lambdas.extract.main._detect_file_type", return_value="application/pdf")
def test_extract_from_step_functions(
    mock_detect, mock_converter, mock_s3, mock_push, step_functions_input
):
    # Setup mocks
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"fake pdf bytes")}
    mock_doc = MagicMock()
    mock_doc.document.export_to_markdown.return_value = "# Title\n\nExtracted content"
    mock_converter.convert.return_value = mock_doc
    mock_s3.put_object = MagicMock()

    from lambdas.extract.main import main

    result = main(step_functions_input, MagicMock())

    assert result["bucket"] == "agensus"
    assert result["key"] == "users/123/abc_test.pdf"
    assert result["extracted_text"] == "# Title\n\nExtracted content"
    assert result["summary_blob_name"].startswith("summaries/")
    assert result["job_id"] == "job-1"

    # Verify S3 put for raw summary
    mock_s3.put_object.assert_called_once()

    # Verify status events
    assert mock_push.call_count == 2
    statuses = [call.args[2] for call in mock_push.call_args_list]
    assert "EXTRACTING" in statuses
    assert "EXTRACTED" in statuses


@patch("lambdas.extract.main.push_status_event")
@patch("lambdas.extract.main.s3_client")
@patch("lambdas.extract.main.document_converter")
@patch("lambdas.extract.main._detect_file_type", return_value="application/pdf")
def test_extract_from_s3_event(
    mock_detect, mock_converter, mock_s3, mock_push, s3_event
):
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"fake pdf bytes")}
    mock_doc = MagicMock()
    mock_doc.document.export_to_markdown.return_value = "# Content"
    mock_converter.convert.return_value = mock_doc
    mock_s3.put_object = MagicMock()

    from lambdas.extract.main import main

    result = main(s3_event, MagicMock())

    assert result["bucket"] == "agensus"
    assert result["blob_name"] == "users/123/abc_test.pdf"
