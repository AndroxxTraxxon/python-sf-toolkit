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
   results = save_insert_bulk(account_list)

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
   bulk_job = save_insert_bulk(contacts)

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
   contact_list = contacts.to_list()

   # Update all records
   for contact in contact_list:
       contact.Title = "Bulk API Example"

   # Update using bulk API
   bulk_job = save_update_bulk(contact_list)
   bulk_job.monitor_until_complete()

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
   bulk_job = save_upsert_bulk(accounts, external_id_field="ExternalId__c")

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
- Maximum file size for a single batch is 100MB (base64 encoded size up to 150MB)
- Certain SObject types are not supported in Bulk API
- Some operations like merge are not supported
- Processing is asynchronous; results are not immediately available

For more details on Salesforce Bulk API 2.0, see the `Salesforce Bulk API Developer Guide <https://developer.salesforce.com/docs/atlas.en-us.api_asynch.meta/api_asynch/>`_.


Bulk Query API
==============

Salesforce Toolkit also provides an interface to the Salesforce Bulk API 2.0 Query endpoint for efficiently retrieving very large result sets. Bulk Query runs asynchronously and streams records in pages so you can process millions of rows without loading everything into memory at once.

When to Use Bulk Query
----------------------

Use Bulk Query when:

- Expecting more than ~20,000 records (especially 100k+)
- Need to minimize API round‑trips (standard REST /query pagination returns 2k records per page)
- Want asynchronous, resumable retrieval
- Processing results incrementally (streaming)
- Need CSV-style export semantics

Basic Usage with select(...).execute_bulk()
-------------------------------------------

You can request a bulk query directly from the query builder:

.. code-block:: python

   from sf_toolkit.data import select, SObject
   from sf_toolkit.data.fields import IdField, TextField

   class Account(SObject):
       Id = IdField()
       Name = TextField()
       Industry = TextField()

   # Build a SOQL query
   bulk_result = select(Account).where(Industry="Technology").execute_bulk()

   # Iterate over all returned records (streaming pages internally)
   for account in bulk_result:
       print(account.Id, account.Name)

   # Convert entire result to a list (loads all pages)
   all_accounts = bulk_result.as_list()
   print(f"Total accounts: {len(all_accounts)}")

Asynchronous Usage
------------------

For very large datasets, async iteration lets other tasks run while pages are fetched:

.. code-block:: python

   import asyncio
   from sf_toolkit.client import AsyncSalesforceClient
   from sf_toolkit.auth import cli_login

   async def main():
       async with AsyncSalesforceClient(login=cli_login("my-org-alias")) as conn:
           bulk_result = (
               select(Account)
               .where(Industry="Technology")
               .execute_bulk_async(connection=conn)
           )

           async for account in bulk_result:
               print(account.Id, account.Name)

           # Load all records into memory (use cautiously for huge sets)
           all_accounts = await bulk_result.as_list_async()
           print(f"Loaded {len(all_accounts)} accounts")

   asyncio.run(main())

Working with BulkApiQueryJob Directly
-------------------------------------

For full control (custom SOQL string, manual monitoring) use BulkApiQueryJob:

.. code-block:: python

   from sf_toolkit.data.bulk import BulkApiQueryJob

   soql = "SELECT Id, Name, Industry FROM Account WHERE Industry = 'Technology'"

   # Initialize (creates job on Salesforce)
   query_job = BulkApiQueryJob.init_job(
       query=soql,
       connection=client  # SalesforceClient or AsyncSalesforceClient
   )

   # Monitor until completed
   query_job = query_job.monitor_until_complete()

   if query_job.state == "JobComplete":
       # Iterate through pages / records
       for record in query_job:
           print(record["Id"], record["Name"])
   else:
       print(f"Query failed: {query_job.errorMessage}")

Async direct usage:

.. code-block:: python

   async_query_job = await BulkApiQueryJob.init_job_async(
       query=soql,
       connection=async_client
   )

   async_query_job = await async_query_job.monitor_until_complete_async()

   if async_query_job.state == "JobComplete":
       async for record in async_query_job:
           print(record["Id"], record["Name"])
   else:
       print(f"Query failed: {async_query_job.errorMessage}")

Streaming and Pagination
------------------------

Bulk query results are delivered in pages:

- Iteration (for / async for) fetches one page at a time
- Each page is parsed into SObject instances (when using select().execute_bulk())
- Use as_list()/as_list_async() to force retrieval of all pages

If you only need the first N records, break early in the loop to avoid fetching remaining pages.

Job States for Query
--------------------

A bulk query job can be in one of these states:

- UploadComplete (SOQL accepted, processing started)
- InProgress (records being gathered)
- Aborted (stopped by user)
- JobComplete (all result pages ready)
- Failed (error encountered)

Error Handling
--------------

Check job.state and errorMessage after completion:

.. code-block:: python

   result = select(Account).execute_bulk()

   # You can inspect underlying job via result._job (internal)
   job = result._job
   if job.state == "Failed":
       print(f"Bulk query failed: {job.errorMessage}")
   else:
       print(f"State: {job.state}")

Partial failures (e.g., field-level errors) typically manifest as a Failed state for query jobs; records are not partially returned.

Performance Tips
----------------

1. Narrow fields: Select only required columns (avoid SELECT * style).
2. Use selective WHERE clauses: Reduces scan time.
3. Avoid overly complex formula fields: Can slow processing.
4. Process incrementally: Stream pages instead of materializing large lists.

Limitations
-----------

- Bulk Query is read-only (cannot modify data)
- ORDER BY and OFFSET are not supported in Bulk API 2.0 queries
- Real-time freshness is not guaranteed for very large result sets (eventual completion)
- Result format is CSV internally (Toolkit parses to objects/dicts)
- Relationship traversals (e.g., Account.Owner.Name) may be limited compared to REST query performance for huge datasets

Example: Filtering and Streaming
--------------------------------

.. code-block:: python

   tech_accounts = (
       select(Account)
       .where(Industry="Technology")
       .and_where(Name__like="Bulk%")
       .execute_bulk()
   )

   for acct in tech_accounts:
       # Process on-the-fly without accumulating
       do_something(acct)

Async Example with Early Break
------------------------------

.. code-block:: python

   async def first_100_account_ids(async_client):
       result = (
           select(Account)
           .fields("Id")  # Limit to Id only
           .execute_bulk_async(connection=async_client)
       )
       collected = []
       async for acct in result:
           collected.append(acct.Id)
           if len(collected) >= 100:
               break
       return collected

Comparing Standard vs Bulk Query
--------------------------------

Standard Query (REST):
- Immediate response, limited page size (2k records per batch)
- Better for small, interactive queries

Bulk Query:
- Asynchronous job creation + processing
- Efficient for very large datasets
- Stream or download full result set

Choose based on dataset size and latency requirements.
