# Using BlobField for File Uploads

SF Toolkit supports automatic file uploads when saving SObjects with blob data. This is done through the new `BlobField` field type, which allows you to set file content that will be uploaded to Salesforce when the SObject is saved.

## Defining SObjects with BlobFields

When defining an SObject class that contains blob data, use the `BlobField` field type for the field that will contain the file content. You should also specify the `blob_field` parameter in the class definition to indicate which field contains the blob data.

Note that the below `Document` SObject has already been implemented
in the `sf_toolkit.data.standard_schemas` module for your convenience.
```python
from sf_toolkit import SObject, BlobField

class Document(SObject):
    Id = IdField()
    Name = TextField()
    Description = TextField()
    FolderId = IdField()
    # Define the blob field
    Body = BlobField()
```

## Setting File Content

The `BlobField` can accept several types of input:

1. **File Path** - A string or `Path` object pointing to a file
2. **Binary Data** - `bytes` containing the file content
3. **String Content** - A `str` that will be encoded to UTF-8 bytes
4. **File-like Object** - An object with a `read()` method (like open file handles)

```python
# Using a file path
doc.Body = "./myfile.pdf"
# or
doc.Body = Path("./myfile.pdf")

# Using binary data
with open("./myfile.pdf", "rb") as f:
    doc.Body = f.read()

# Using string content
doc.Body = "This is the content of a text file"

# Using a file-like object
file_obj = io.BytesIO(b"File content")
file_obj.name = "myfile.txt"  # Optional - sets filename
doc.Body = file_obj
```

## Automatic Upload on Save

Once you've set content to a `BlobField`, the file will be automatically uploaded when you call `save()` on the SObject. No separate file upload method is needed.

```python
# Create a ContentVersion with a file
cv = ContentVersion(
    Title="My Document",
    PathOnClient="example.pdf",
    Description="Description of the file"
)

# Set the file content
cv.VersionData = Path("./example.pdf")

# Save - file upload happens automatically
save_record(cv)

print(f"Created ContentVersion with ID: {cv.Id}")
```

## Common Salesforce Blob SObjects

There are three main SObject types in Salesforce that support blob data. These standard
objects have been implemented in sf_toolkit.data.standard_schemas module for your use:

- ContentVersion (for Lightning Files)
- Document (Classic Files)
- Attachment (for Notes and Attachments)

## Updating Existing Records with New Files

You can also update an existing record with a new file by setting its `BlobField` and calling `save()`:

```python
# Get an existing ContentVersion
cv = read(ContentVersion, "068XXXXXXXXXXXX")

# Update metadata
cv.Description = "Updated description"

# Update the file content
cv.VersionData = Path("./updated_file.pdf")

# Save - file upload happens automatically
cv.save()
```

## File Size Limits

- For ContentVersion: Maximum file size is 2 GB
- For other objects (Document, Attachment): Maximum file size is 500 MB

## Implementation Details

The `BlobField` implementation automatically:

1. Converts the input to a consistent format using the `BlobData` class
2. Determines the appropriate filename and content type
3. Creates a multipart/form-data request with both the metadata and file content
4. Uses HTTPX for efficient file uploads, including streaming for large files
5. Handles responses and error cases

This allows SObject instances with blob fields to be saved with a simple `save()` call without any additional code.
