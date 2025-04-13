Authentication
=============

Authentication Methods
--------------------

Salesforce Toolkit supports different methods of authentication:

CLI-based Authentication
^^^^^^^^^^^^^^^^^^^^^^^

The simplest way to authenticate if you're already using the Salesforce CLI:

.. code-block:: python

   from sf_toolkit import SalesforceClient, cli_login
   
   # Default org from CLI
   client = SalesforceClient(login=cli_login())
   
   # Specific org by alias
   client = SalesforceClient(login=cli_login(alias_or_username="my-dev-org"))

Session Token
^^^^^^^^^^^^

If you already have a session token and instance URL:

.. code-block:: python

   from sf_toolkit import SalesforceClient, SalesforceToken
   from httpx import URL
   
   token = SalesforceToken(
       instance=URL("https://myinstance.my.salesforce.com"),
       token="00D..."
   )
   
   client = SalesforceClient(token=token)

Token Refresh Callback
--------------------

You can register a callback function to be executed when a token is refreshed:

.. code-block:: python

   def token_updated(token):
       # Save token to database or file
       print(f"Token updated: {token.instance}")
   
   client = SalesforceClient(
       login=cli_login(),
       token_refresh_callback=token_updated
   )

Authentication Classes
--------------------

These classes handle the authentication process:

* ``SalesforceAuth`` - HTTPX authentication class that handles token management
* ``SalesforceToken`` - Represents a Salesforce access token
* ``SalesforceLogin`` - A callable that performs authentication and returns a token