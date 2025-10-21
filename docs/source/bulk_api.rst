Bulk API
========

Salesforce Toolkit provides an interface to the Salesforce Bulk API 2.0, which is designed for loading, updating, or deleting large sets of data. The Bulk API is ideal for processing many records asynchronously.

Overview
--------

The Bulk API in Salesforce Toolkit consists of two main components:

1. **BulkApiIngestJob** - Represents a Salesforce Bulk API 2.0 job
2. **SObjectList** bulk methods - Methods to efficiently process large collections of records

When to Use Bulk API
------------------

Use the Bulk API when:

- Processing 10,000+ records
- Performing batch operations that would otherwise exceed API limits
- Running operations that can be processed asynchronously
- Needing better performance for large datasets

Basic Usage
---------

The simplest way to use Bulk API is through the ``SObjectList`` bulk methods:

.. code-block:: python

   from sf_toolkit.data import SObject
   from sf_toolkit.data.fields import IdField, TextField

   class Account(SObject):
       Id = IdField()
       Name = TextField()
       Industry = TextField()

   # Create a list of accounts
   accounts = [
       Account(Name=f"Bulk Account {i}", Industry="Technology")
       for i in range(1, 1001)
   ]

   # Create SObjectList
   account_list = SObjectList(accounts)

   # Insert using bulk API
   results = account_list.save_insert_bulk()

   print(f"Successfully inserted {results.numberRecordsProcessed} records")
   print(f"Failed to insert {results.numberRecordsFailed} records")

Bulk Insert
---------

To insert large sets of records:

.. code-block:: python

   # Create SObjectList with many records
   contacts = SObjectList([
       Contact(FirstName=f"Contact{i}", LastName=f"Bulk{i}")
       for i in range(1, 50000)
   ])

   # Insert using bulk API
   bulk_job = contacts.save_insert_bulk()

   # Check job status
   print(f"Job ID: {bulk_job.id}")
   print(f"Status: {bulk_job.state}")

   # Refresh to get latest status
   updated_job = bulk_job.refresh()
   print(f"Updated status: {updated_job.state}")

Bulk Update
---------

To update large sets of records:

.. code-block:: python

   # Get existing records
   contacts = select(Contact).where(LastName="Bulk").execute()

   # Convert to SObjectList
   contact_list = SObjectList(contacts)

   # Update all records
   for contact in contact_list:
       contact.Title = "Bulk API Example"

   # Update using bulk API
   bulk_job = contact_list.save_update_bulk()

   print(f"Records processed: {bulk_job.numberRecordsProcessed}")

Bulk Upsert
---------

To upsert (insert or update) records based on an external ID:

.. code-block:: python

   # Create or update records with external ID
   accounts = SObjectList([
       Account(ExternalId__c=f"EXT-{i}", Name=f"Upsert Account {i}")
       for i in range(1, 10000)
   ])

   # Upsert using bulk API with external ID field
   bulk_job = accounts.save_upsert_bulk(external_id_field="ExternalId__c")

   print(f"Job state: {bulk_job.state}")
   print(f"Records processed: {bulk_job.numberRecordsProcessed}")
   print(f"Records failed: {bulk_job.numberRecordsFailed}")

Working with BulkApiIngestJob Directly
-----------------------------------

For more control, you can work with the BulkApiIngestJob class directly:

.. code-block:: python

   from sf_toolkit.data.bulk import BulkApiIngestJob

   # Initialize a new bulk job
   bulk_job = BulkApiIngestJob.init_job(
       sobject_type="Account",
       operation="insert",
       column_delimiter="COMMA",
       line_ending="LF",
       connection=client  # Your SalesforceClient instance
   )

   # Create a list of records
   accounts = SObjectList([
       Account(Name=f"Direct Bulk Job {i}")
       for i in range(1, 5000)
   ])

   # Upload data batches
   bulk_job = bulk_job.upload_batches(accounts)

   # Monitor job status
   print(f"Job ID: {bulk_job.id}")
   print(f"Current state: {bulk_job.state}")

   # Refresh to get latest status
   updated_job = bulk_job.refresh()

   # Check final results
   if updated_job.state == "JobComplete":
       print(f"Successfully processed: {updated_job.numberRecordsProcessed}")
       print(f"Failed records: {updated_job.numberRecordsFailed}")

Bulk Job States
------------

A Bulk API job can be in one of these states:

- **Open** - Job has been created and is ready for data upload
- **UploadComplete** - All data has been uploaded and the job is being processed
- **Aborted** - Job was aborted by the user
- **JobComplete** - Job has completed processing
- **Failed** - Job has failed

Monitoring Job Status
------------------

You can monitor the status of a bulk job:

.. code-block:: python

   # Get a job by ID
   job_id = "750xx000000001234"
   connection = SalesforceClient(login=cli_login())

   # Create a job instance with just the ID
   job = BulkApiIngestJob(id=job_id, connection=connection)

   # Refresh to get current status
   job = job.refresh()

   print(f"Job state: {job.state}")
   print(f"Records processed: {job.numberRecordsProcessed}")
   print(f"Records failed: {job.numberRecordsFailed}")
   print(f"Error message: {job.errorMessage}")

Performance Considerations
-----------------------

When using the Bulk API:

1. **Batch size** - Data is automatically split into optimal batch sizes (up to 100MB per batch)
2. **Column delimiter** - Default is COMMA, but you can choose others like TAB or PIPE
3. **Parallel processing** - Salesforce processes batches in parallel
4. **API limits** - Bulk API operations don't count against your regular API limits

Error Handling
------------

For bulk operations, errors are tracked at the job level:

.. code-block:: python

   bulk_job = accounts.save_insert_bulk()

   # Check for errors
   if bulk_job.state == "Failed":
       print(f"Job failed: {bulk_job.errorMessage}")
   elif bulk_job.numberRecordsFailed > 0:
       print(f"{bulk_job.numberRecordsFailed} records failed to process")

   # For partial failures, some records processed successfully
   if bulk_job.numberRecordsProcessed > 0:
       print(f"{bulk_job.numberRecordsProcessed} records processed successfully")

Advanced Configuration
-------------------

You can configure various aspects of the bulk job:

.. code-block:: python

   # Custom column delimiter
   bulk_job = BulkApiIngestJob.init_job(
       sobject_type="Account",
       operation="insert",
       column_delimiter="TAB",  # Use tab delimiter
       connection=client
   )

   # Create a job for hard delete operation
   delete_job = BulkApiIngestJob.init_job(
       sobject_type="Account",
       operation="hardDelete",  # Permanently delete records
       connection=client
   )

Limitations
---------

- Bulk API 2.0 only supports CSV format (not JSON or XML)
- Maximum file size for a single upload is 100MB (base64 encoded size up to 150MB)
- Certain SObject types are not supported in Bulk API
- Some operations like merge are not supported
- Processing is asynchronous; results are not immediately available

For more details on Salesforce Bulk API 2.0, see the `Salesforce Bulk API Developer Guide <https://developer.salesforce.com/docs/atlas.en-us.api_asynch.meta/api_asynch/>`_.
