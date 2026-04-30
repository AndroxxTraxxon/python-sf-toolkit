Using BlobField for File Uploads
================================

SF Toolkit supports automatic file uploads when saving SObjects with blob data. This is done through the ``BlobField`` field type, which allows you to set file content that will be uploaded to Salesforce when the SObject is saved.

Defining SObjects with BlobFields
---------------------------------

When defining an SObject class that contains blob data, use the ``BlobField`` field type for the field that will contain the file content. SF Toolkit automatically detects the ``BlobField`` and configures the SObject so that file content is uploaded as part of ``save_insert`` / ``save_update``.

Note that the ``Document``, ``ContentVersion`` and ``Attachment`` SObjects shown below have already been implemented in the :mod:`sf_toolkit.data.standard_schemas` module for your convenience.

.. code-block:: python

   from sf_toolkit import SObject, BlobField
   from sf_toolkit.data.fields import IdField, TextField

   class Document(SObject, api_name="Document"):
       Id = IdField()
       Name = TextField()
       Description = TextField()
       FolderId = IdField()
       # Define the blob field
       Body = BlobField()

Setting File Content
--------------------

The ``BlobField`` can accept several types of input:

1. **File Path** — a string or :class:`pathlib.Path` pointing to a file
2. **Binary Data** — ``bytes`` containing the file content
3. **String Content** — a ``str`` that will be encoded to UTF-8 bytes
4. **File-like Object** — an object with a ``read()`` method (e.g. an open file handle or :class:`io.BytesIO`)

.. code-block:: python

   import io
   from pathlib import Path

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

Automatic Upload on Save
------------------------

Once you've set content on a ``BlobField``, the file is uploaded automatically when you call :func:`~sf_toolkit.io.save` (or :func:`~sf_toolkit.io.save_insert` / :func:`~sf_toolkit.io.save_update`) on the SObject. No separate file upload method is needed.

.. code-block:: python

   from pathlib import Path
   from sf_toolkit.io import save
   from sf_toolkit.data.standard_schemas import ContentVersion

   # Create a ContentVersion with a file
   cv = ContentVersion(
       Title="My Document",
       PathOnClient="example.pdf",
       Description="Description of the file",
   )

   # Set the file content
   cv.VersionData = Path("./example.pdf")

   # Save - file upload happens automatically
   save(cv)

   print(f"Created ContentVersion with ID: {cv.Id}")

Common Salesforce Blob SObjects
-------------------------------

There are three main SObject types in Salesforce that support blob data. These standard objects have been implemented in :mod:`sf_toolkit.data.standard_schemas` for your use:

- ``ContentVersion`` (for Lightning Files)
- ``Document`` (Classic Files)
- ``Attachment`` (for Notes and Attachments)

Updating Existing Records with New Files
----------------------------------------

You can also update an existing record with a new file by setting its ``BlobField`` and saving the record:

.. code-block:: python

   from pathlib import Path
   from sf_toolkit.io import fetch, save_update
   from sf_toolkit.data.standard_schemas import ContentVersion

   # Get an existing ContentVersion
   cv = fetch(ContentVersion, "068XXXXXXXXXXXX")

   # Update metadata
   cv.Description = "Updated description"

   # Update the file content
   cv.VersionData = Path("./updated_file.pdf")

   # Save - file upload happens automatically
   save_update(cv)

Downloading File Content
------------------------

Use :func:`~sf_toolkit.io.api.download_file` (or its async counterpart ``download_file_async``) to retrieve a record's blob content:

.. code-block:: python

   from pathlib import Path
   from sf_toolkit.io.api import download_file
   from sf_toolkit.data.standard_schemas import ContentVersion

   cv = fetch(ContentVersion, "068XXXXXXXXXXXX")

   # Stream to disk
   download_file(cv, Path("./downloaded.pdf"))

   # Or load into memory by passing dest=None
   data: bytes = download_file(cv, None)

File Size Limits
----------------

- For ``ContentVersion``: maximum file size is 2 GB
- For other objects (``Document``, ``Attachment``): maximum file size is 500 MB

Implementation Details
----------------------

The ``BlobField`` implementation automatically:

1. Converts the input to a consistent format using the ``BlobData`` class.
2. Determines the appropriate filename and content type.
3. Creates a multipart/form-data request with both the metadata and file content.
4. Uses HTTPX for efficient file uploads, including streaming for large files.
5. Handles responses and error cases.

This allows SObject instances with blob fields to be saved with a simple ``save()`` call without any additional code.
