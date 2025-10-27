Asynchronous Operations
=======================

The sf_toolkit provides comprehensive asynchronous support for all major operations, allowing you to build high-performance applications that can handle multiple Salesforce API calls concurrently. This section covers the async equivalents of the synchronous operations.

Client Classes
--------------

The toolkit provides both synchronous and asynchronous client classes:

**SalesforceClient (Sync)**
    The standard synchronous client for blocking operations.

**AsyncSalesforceClient (Async)**
    The asynchronous client that inherits from httpx.AsyncClient and supports concurrent operations.

Basic Usage
~~~~~~~~~~~

.. code-block:: python

    # Synchronous client
    from sf_toolkit import SalesforceClient, SalesforceLogin
    
    login = SalesforceLogin(username="user@example.com", password="password")
    with SalesforceClient(login=login) as client:
        # Synchronous operations here
        pass

    # Asynchronous client  
    from sf_toolkit import AsyncSalesforceClient
    import asyncio
    
    async def main():
        async with AsyncSalesforceClient(login=login) as client:
            # Asynchronous operations here
            pass
    
    asyncio.run(main())

Client Conversion
~~~~~~~~~~~~~~~~~

You can convert between sync and async clients:

.. code-block:: python

    # Convert sync client to async
    sync_client = SalesforceClient(login=login)
    async_client = sync_client.as_async
    
    # Convert async client to sync
    async_client = AsyncSalesforceClient(login=login)
    sync_client = async_client.as_sync

Record Operations
-----------------

Every synchronous record operation has an asynchronous equivalent:

Fetching Records
~~~~~~~~~~~~~~~~

.. code-block:: python

    from sf_toolkit.io.api import fetch, fetch_async
    
    # Synchronous
    account = fetch(Account, "001XXXXXXXXXX", client)
    
    # Asynchronous
    account = await fetch_async(Account, "001XXXXXXXXXX", client)

Saving Records
~~~~~~~~~~~~~~

.. code-block:: python

    from sf_toolkit.io.api import save, save_async
    
    # Synchronous
    save(account, client)
    
    # Asynchronous
    await save_async(account, client)

The async save functions mirror their sync counterparts:

- ``save_insert_async()`` - Insert new records
- ``save_update_async()`` - Update existing records  
- ``save_upsert_async()`` - Upsert using external ID

Deleting Records
~~~~~~~~~~~~~~~~

.. code-block:: python

    from sf_toolkit.io.api import delete, delete_async
    
    # Synchronous
    delete(account, client)
    
    # Asynchronous
    await delete_async(account, client)

Reloading Records
~~~~~~~~~~~~~~~~~

.. code-block:: python

    from sf_toolkit.io.api import reload, reload_async
    
    # Synchronous
    reload(account, client)
    
    # Asynchronous
    await reload_async(account, client)

File Operations
~~~~~~~~~~~~~~~

.. code-block:: python

    from sf_toolkit.io.api import download_file, download_file_async
    
    # Synchronous
    content = download_file(attachment, dest_path, client)
    
    # Asynchronous
    content = await download_file_async(attachment, dest_path, client)

List Operations
---------------

SObjectList operations also have async equivalents that support concurrency:

Fetching Multiple Records
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from sf_toolkit.io.api import fetch_list, fetch_list_async
    
    # Synchronous
    accounts = fetch_list(Account, "001XX1", "001XX2", "001XX3", sf_client=client)
    
    # Asynchronous with concurrency control
    accounts = await fetch_list_async(
        Account, 
        "001XX1", "001XX2", "001XX3",
        sf_client=client,
        concurrency=5  # Process up to 5 requests concurrently
    )

Bulk List Operations
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # Synchronous list operations
    results = save_insert_list(accounts, batch_size=200)
    results = save_update_list(accounts, only_changes=True)
    results = save_upsert_list(accounts, "External_ID__c")
    
    # Asynchronous list operations with concurrency
    results = await save_insert_list_async(
        accounts, 
        concurrency=5, 
        batch_size=200
    )
    results = await save_update_list_async(
        accounts, 
        only_changes=True,
        concurrency=3
    )

Bulk API Operations
~~~~~~~~~~~~~~~~~~~

The Bulk API operations support both sync and async modes:

.. code-block:: python

    # Synchronous bulk operations
    job = save_insert_bulk(accounts)
    job = save_update_bulk(accounts)
    job = save_upsert_bulk(accounts, "External_ID__c")
    
    # Asynchronous bulk operations
    job = await save_insert_bulk_async(accounts)
    job = await save_update_bulk_async(accounts)

Concurrency Control
-------------------

The async operations provide fine-grained concurrency control:

.. code-block:: python

    # Control concurrent requests
    results = await fetch_list_async(
        Account,
        *account_ids,
        concurrency=10,  # Maximum 10 concurrent requests
        sf_client=client
    )
    
    # Batch processing with concurrency
    results = await save_insert_list_async(
        large_account_list,
        concurrency=5,   # 5 concurrent batch requests
        batch_size=200   # 200 records per batch
    )

Error Handling
--------------

Async operations maintain the same error handling patterns:

.. code-block:: python

    from sf_toolkit.exceptions import SalesforceApiError
    
    try:
        account = await fetch_async(Account, "invalid_id", client)
    except SalesforceApiError as e:
        print(f"API Error: {e}")

Callback Functions
------------------

Some async operations support callback functions for progress tracking:

.. code-block:: python

    async def on_chunk_received(response):
        print(f"Processed chunk with {len(response.json())} records")
    
    accounts = await fetch_list_async(
        Account,
        *account_ids,
        sf_client=client,
        on_chunk_received=on_chunk_received
    )

Best Practices
--------------

1. **Use Context Managers**: Always use ``async with`` for AsyncSalesforceClient
2. **Control Concurrency**: Set appropriate concurrency limits to avoid API rate limits
3. **Batch Operations**: Use batch operations for multiple records instead of individual calls
4. **Connection Reuse**: Reuse client connections across multiple operations
5. **Error Handling**: Implement proper error handling for network and API errors

Performance Comparison
---------------------

Async operations provide significant performance benefits when working with multiple records:

.. code-block:: python

    import time
    import asyncio
    
    # Synchronous - processes sequentially
    start = time.time()
    accounts = []
    for account_id in account_ids:
        accounts.append(fetch(Account, account_id, sync_client))
    sync_time = time.time() - start
    
    # Asynchronous - processes concurrently
    async def fetch_all():
        return await fetch_list_async(
            Account, 
            *account_ids, 
            sf_client=async_client,
            concurrency=10
        )
    
    start = time.time()
    accounts = asyncio.run(fetch_all())
    async_time = time.time() - start
    
    print(f"Sync: {sync_time:.2f}s, Async: {async_time:.2f}s")
    print(f"Speedup: {sync_time/async_time:.1f}x")