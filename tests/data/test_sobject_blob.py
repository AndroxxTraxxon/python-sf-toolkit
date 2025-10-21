import pytest
import io
import tempfile
import json
from pathlib import Path
from unittest.mock import MagicMock

from sf_toolkit.data.fields import (
    BlobField,
    TextField,
    IdField,
    BlobData,
    serialize_object,
)
from sf_toolkit.io.api import save_insert
from sf_toolkit.data.sobject import SObject


# Define a test SObject with a BlobField
class Document(SObject, api_name="Document"):
    Id = IdField()
    Name = TextField()
    Description = TextField()
    Body = BlobField()  # This is where the file content will be stored


def test_sobject_with_blobfield_definition():
    """Test that an SObject with a BlobField is properly defined"""
    # Check that blob_field is properly set in attributes
    assert Document.attributes.blob_field == "Body"

    # Create an instance with blob data
    doc = Document(
        Name="Test Document",
        Description="Description",
        Body=BlobData("Test content", filename="test.txt"),
    )

    # Test basic properties
    assert doc.Name == "Test Document"
    assert doc.Description == "Description"
    assert isinstance(doc.Body, BlobData)

    # Test blob data properties
    assert doc.Body.filename == "test.txt"
    assert doc.Body.content_type == "application/octet-stream"

    # Test that we can access the content through the context manager
    with doc.Body as content:
        assert content == b"Test content"


def test_sobject_multiple_blobfields():
    """Test that an SObject cannot have multiple BlobFields"""
    # This should raise an assertion error
    with pytest.raises(AssertionError):
        # Define a test SObject with incorrect multiple BlobFields (for testing assertion)
        class InvalidDocument(SObject, api_name="InvalidDocument"):
            Id = IdField()
            Name = TextField()
            Body1 = BlobField()
            Body2 = BlobField()  # This should cause an assertion error


def test_save_insert_with_text_blob(mock_sf_client):
    """Test inserting an SObject with a text blob"""
    # Create a document with text content
    doc = Document(
        Name="Text Document",
        Description="A document with text content",
        Body=BlobData("Hello, world!", filename="hello.txt"),
    )

    # Mock the response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "id": "069XX000001abcdIAA",
        "success": True,
        "errors": [],
    }
    mock_sf_client.post.return_value = mock_response

    # Call save_insert
    save_insert(doc)

    # Verify the API call was made with the correct parameters
    mock_sf_client.post.assert_called_once()
    args, kwargs = mock_sf_client.post.call_args

    # Check the URL
    assert args[0] == "/services/data/v57.0/sobjects/Document"

    # Check that files parameter was used (multipart form upload)
    assert "files" in kwargs
    assert len(kwargs["files"]) == 2

    # First file part should be entity_document with JSON payload
    assert kwargs["files"][0][0] == "entity_document"
    json_data = json.loads(kwargs["files"][0][1][1])  # Extract JSON from tuple
    assert json_data["Name"] == "Text Document"
    assert json_data["Description"] == "A document with text content"
    assert "Body" not in json_data  # Body should not be in JSON

    # Second file part should be the blob field
    assert kwargs["files"][1][0] == "Body"  # Field name
    assert kwargs["files"][1][1][1] == b"Hello, world!"  # Content

    # Check that the ID was set on the object
    assert doc.Id == "069XX000001abcdIAA"


def test_save_insert_with_binary_blob(mock_sf_client):
    """Test inserting an SObject with binary data"""
    # Create binary data
    binary_data = b"\x89PNG\r\n\x1a\n\x00\x00"  # Start of a PNG file

    # Create a document with binary content
    doc = Document(
        Name="Binary Document",
        Description="A document with binary content",
        Body=BlobData(binary_data, filename="image.png", content_type="image/png"),
    )

    # Mock the response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "id": "069XX000001abceIAA",
        "success": True,
        "errors": [],
    }
    mock_sf_client.post.return_value = mock_response

    # Call save_insert
    save_insert(doc)

    # Verify the API call was made with the correct parameters
    mock_sf_client.post.assert_called_once()
    args, kwargs = mock_sf_client.post.call_args

    # Check that files parameter was used (multipart form upload)
    assert "files" in kwargs
    assert len(kwargs["files"]) == 2

    # Second file part should be the blob field with binary data
    assert kwargs["files"][1][0] == "Body"  # Field name
    assert kwargs["files"][1][1][1] == binary_data  # Binary content

    # Check that the ID was set on the object
    assert doc.Id == "069XX000001abceIAA"


def test_save_insert_with_file_blob(mock_sf_client):
    """Test inserting an SObject with a file"""
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"File content for testing")
        temp_path = Path(temp_file.name)

    try:
        # Create a document with file content
        doc = Document(
            Name="File Document",
            Description="A document with file content",
            Body=BlobData(temp_path),
        )

        # Mock the response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "069XX000001abcfIAA",
            "success": True,
            "errors": [],
        }
        mock_sf_client.post.return_value = mock_response

        # Call save_insert
        save_insert(doc)

        # Verify the API call was made with the correct parameters
        mock_sf_client.post.assert_called_once()
        args, kwargs = mock_sf_client.post.call_args

        # Check that files parameter was used (multipart form upload)
        assert "files" in kwargs
        assert len(kwargs["files"]) == 2

        # Second file part should be the blob field with file content
        assert kwargs["files"][1][0] == "Body"  # Field name
        assert kwargs["files"][1][1][1] == b"File content for testing"  # File content

        # Check that the ID was set on the object
        assert doc.Id == "069XX000001abcfIAA"
    finally:
        # Clean up the temporary file
        temp_path.unlink()


def test_save_insert_with_stream_blob(mock_sf_client):
    """Test inserting an SObject with a stream/file-like object"""
    # Create a file-like object
    stream = io.BytesIO(b"Stream content for testing")

    # Create a document with stream content
    doc = Document(
        Name="Stream Document",
        Description="A document with stream content",
        Body=BlobData(stream, filename="stream.txt"),
    )

    # Mock the response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "id": "069XX000001abcgIAA",
        "success": True,
        "errors": [],
    }
    mock_sf_client.post.return_value = mock_response

    # Call save_insert
    save_insert(doc)

    # Verify the API call was made with the correct parameters
    mock_sf_client.post.assert_called_once()
    args, kwargs = mock_sf_client.post.call_args

    # Check that files parameter was used (multipart form upload)
    assert "files" in kwargs
    assert len(kwargs["files"]) == 2

    # Second file part should be the blob field with stream content
    assert kwargs["files"][1][0] == "Body"  # Field name
    assert kwargs["files"][1][1][1] == b"Stream content for testing"  # Stream content

    # Check that the ID was set on the object
    assert doc.Id == "069XX000001abcgIAA"


def test_save_insert_with_blob_and_reload(mock_sf_client):
    """Test inserting an SObject with a blob and reloading"""
    # Create a document with text content
    doc = Document(
        Name="Reload Document",
        Description="Testing reload after insert",
        Body=BlobData("Content to upload", filename="reload.txt"),
    )

    # Mock the insert response
    insert_response = MagicMock()
    insert_response.json.return_value = {
        "id": "069XX000001abchIAA",
        "success": True,
        "errors": [],
    }

    # Mock the get response for reload
    get_response = MagicMock()
    get_response.json.return_value = {
        "attributes": {"type": "Document"},
        "Id": "069XX000001abchIAA",
        "Name": "Reload Document (Updated)",
        "Description": "Description updated after insert",
        # Note: Body is not returned in the reload
    }
    # Configure the mock client to return different responses
    mock_sf_client.post.return_value = insert_response
    mock_sf_client.get.return_value = get_response

    # Call save_insert with reload
    save_insert(doc, reload_after_success=True)

    # Verify both API calls were made
    mock_sf_client.post.assert_called_once()
    mock_sf_client.get.assert_called_once()

    # Check that fields were updated from the reload
    assert doc.Id == "069XX000001abchIAA"
    assert doc.Name == "Reload Document (Updated)"
    assert doc.Description == "Description updated after insert"

    # Blob field should still be present
    assert doc.Body is not None
    with doc.Body as content:
        assert content == b"Content to upload"


def test_blob_field_not_included_in_serialization():
    """Test that BlobField is not included in serialization"""
    # Create a document with text content
    doc = Document(
        Name="Serialization Test",
        Description="Testing serialization",
        Body=BlobData("Test content", filename="serialize.txt"),
    )

    # Serialize the document
    serialized = serialize_object(doc)

    # Check that Body is not included in the serialized data
    assert "Name" in serialized
    assert "Description" in serialized
    assert "Body" not in serialized
