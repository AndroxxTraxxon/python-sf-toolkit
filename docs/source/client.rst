Salesforce Client
===============

The Salesforce Client is the main interface for interacting with the Salesforce API.

Client Types
-----------

There are two main client types:

* ``SalesforceClient`` - Synchronous client
* ``AsyncSalesforceClient`` - Asynchronous client for use with ``async/await``

Basic Usage
----------

.. code-block:: python

    from sf_toolkit import SalesforceClient, cli_login
    from sf_toolkit.data import select
    from sf_toolkit import SObject
    from sf_toolkit.data.fields import IdField, TextField
    # Define an SObject model (fields you care about)
    class Account(SObject):
        Id = IdField()
        Name = TextField()

    # Basic synchronous usage with SF CLI authentication (alias optional)
    with SalesforceClient(login=cli_login()) as sf:
        # Synchronous properties (populated at login)
        print("Available API versions:", sf.versions)
        print("Current user Id:", sf._userinfo.user_id)

        # Raw API GET request (immediate response as dict/json)
        account_describe = sf.get("/services/data/v57.0/sobjects/Account/describe")
        print("Account label:", account_describe["label"])

        # Build a SOQL query using the query builder (returns an iterator)
        accounts_iter = select(Account).where(Name__like="Acme%").limit(5).execute()

        # Iterate results (records loaded lazily)
        for acct in accounts_iter:
            print("Got account:", acct.Id, acct.Name)

        # You can also perform other CRUD operations, bulk operations, etc.
        # e.g. sf.post("/services/data/v57.0/sobjects/Account", data={...})

   # Client session is automatically closed when exiting the context manager

Asynchronous Usage
--------------------
The asynchronous client mirrors the synchronous API but is designed for use with Python's async / await syntax. Use AsyncSalesforceClient in an async context manager and await any network-bound operations (methods ending in _async). Attribute access (like sf.versions and sf._userinfo) remains synchronous (retrieved / cached on login), while actions that call the API are asynchronous.

Minimal example:

.. code-block:: python

   import asyncio
   from sf_toolkit import AsyncSalesforceClient, cli_login
   from sf_toolkit.io import sobject_from_description

   async def main():
       # Acquire an authenticated async client (SF CLI auth by default if no alias passed)
       async with AsyncSalesforceClient(login=cli_login()) as sf:
           # Synchronous properties (available after login)
           print("API versions:", sf.versions)
           print("User Id:", sf._userinfo.user_id)

           # Raw async GET request
           account_describe = await sf.get("/services/data/v57.0/sobjects/Account/describe")
           print("Account label:", account_describe["label"])

           # Example SOQL query using the high-level query builder (returns an async iterator)
           from sf_toolkit.data import select
           from sf_toolkit import SObject
           from sf_toolkit.data.fields import IdField, TextField

           class Account(SObject):
               Id = IdField()
               Name = TextField()

           # Build and execute query asynchronously
           accounts_iter = await select(Account).where(Name__like="Acme%").limit(5).execute_async()
           async for acct in accounts_iter:
               print("Got account:", acct.Id, acct.Name)

       # Client is automatically closed on exit

   if __name__ == "__main__":
       asyncio.run(main())

Common async operations:

* Raw requests: await sf.get(path), await sf.post(path, data=...)
* SOQL via builder: await select(MyObject).where(...).execute_async()
* Bulk / batch helpers expose *_async variants
* Use async for to iterate result sets without loading all rows into memory

Tip: Keep long-running org interactions inside the async with block so the underlying HTTP session can be reused efficiently.


Authentication Methods
--------------------

The client supports several authentication methods:

* SF CLI authentication (using the SF CLI or SFDX CLI)
* Username/Password flow (planned)
* JWT flow (planned)
* Refresh token flow (planned)
* OAuth web flow (planned)

See the :doc:`auth` section for more details.

Working with multiple connections
-------------------------------

You can register and manage multiple connections to different Salesforce orgs:

.. code-block:: python

    # Create connections with different names
    with (
        SalesforceClient(connection_name="production", login=cli_login("prod-org")) as prod,
        SalesforceClient(connection_name="sandbox", login=cli_login("sandbox-org")) as sandbox
    ):
            # Now you can use both clients
            prod_versions = prod.versions
            sandbox_versions = sandbox.versions

            # Later, you can retrieve connections by name
            prod_client = SalesforceClient.get_connection("production")
            sandbox_client = SalesforceClient.get_connection("sandbox")
