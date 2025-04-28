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

   # Using SF CLI Authentication
   with SalesforceClient(login=cli_login()) as sf:
       # Get available API versions
       versions = sf.versions

       # Get user info
       user_info = sf._userinfo

       # Make a raw API request
       response = sf.get("/services/data/v57.0/sobjects/Account/describe")

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
        SalesforceClient(connection_name="production", login=cli_login("prod-org") as prod,
        SalesforceClient(connection_name="sandbox", login=cli_login("sandbox-org") as sandbox
    ):
            # Now you can use both clients
            prod_versions = prod.versions
            sandbox_versions = sandbox.versions

            # Later, you can retrieve connections by name
            prod_client = SalesforceClient.get_connection("production")
            sandbox_client = SalesforceClient.get_connection("sandbox")
