Advanced Topics
===============

Async Operations
----------------

For high-performance applications, you can use the async client:

.. code-block:: python

   import asyncio
   from sf_toolkit import AsyncSalesforceClient, cli_login

   async def main():
       async with AsyncSalesforceClient(login=cli_login()) as client:
           response = await client.get("/services/data/v57.0/sobjects/Account/describe")
           data = response.json()
           print(f"Found {len(data['fields'])} fields on Account")

   asyncio.run(main())

Batch Operations
----------------

When working with large numbers of records:

.. code-block:: python

   from sf_toolkit.io import fetch_list_async

   # Fetch many records efficiently
   accounts = await fetch_list_async(
       Account,
       "001xx", "001yy", "001zz",  # Many IDs
       concurrency=5,  # Process in parallel
   )

   # Callback for progress tracking
   def on_chunk_processed(response):
       print(f"Processed chunk with {len(response.json())} records")

   accounts = Account.list(
       *many_ids,
       concurrency=5,
       on_chunk_received=on_chunk_processed
   )

Error Handling
--------------

Salesforce Toolkit provides specialized exceptions for different error scenarios:

.. code-block:: python

   from sf_toolkit.io import fetch
   from sf_toolkit.exceptions import (
       SalesforceError,
       SalesforceResourceNotFound,
       SalesforceRefusedRequest,
   )

   try:
       account = fetch(Account, "001xxxxxxxxxxxxxxx")
   except SalesforceResourceNotFound:
       print("Account not found")
   except SalesforceRefusedRequest:
       print("Permission denied")
   except SalesforceError as e:
       print(f"Error: {e}")

API Limits & Usage Monitoring
-----------------------------

Monitor your API usage:

.. code-block:: python

   with SalesforceClient(login=cli_login()) as client:
       # Make some requests
       response = client.get(f"{client.sobjects_url}/Account/describe")

       # Check API usage
       if client.api_usage:
           used, total = client.api_usage.api_usage
           print(f"API Usage: {used}/{total} ({used/total*100:.1f}%)")

Custom Field Types
------------------

You can create custom field types for specialized behavior:

.. code-block:: python

   import decimal
   from sf_toolkit.data.fields import Field, FieldFlag

   class DecimalField(Field[decimal.Decimal]):
       def __init__(self, *flags: FieldFlag, precision: int = 2, **props):
           super().__init__(*flags, py_type=decimal.Decimal, **props)
           self.precision = precision

       def format(self, value):
           return float(round(value, self.precision))

       def revive(self, value):
           if isinstance(value, (int, float)):
               return decimal.Decimal(str(value))
           return decimal.Decimal(value)

   # Use the custom field
   class Product(SObject, api_name="Product2"):
       Price__c = DecimalField(precision=4)
