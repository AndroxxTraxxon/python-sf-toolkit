Authentication
==============

Salesforce Toolkit supports multiple authentication methods to connect to Salesforce. This guide will help you choose the right authentication method for your use case.

Quick Reference
--------------

Here's a quick reference table of available authentication methods:

+---------------------------+--------------------------------------------------+---------------------+
| Method                    | Use Case                                         | Security Level      |
+===========================+==================================================+=====================+
| CLI Authentication        | Local development with Salesforce CLI installed  | High                |
+---------------------------+--------------------------------------------------+---------------------+
| OAuth Username-Password   | Simple scripting with username/password          | Medium              |
+---------------------------+--------------------------------------------------+---------------------+
| OAuth JWT Bearer          | Server-to-server integration                     | High                |
+---------------------------+--------------------------------------------------+---------------------+
| OAuth Client Credentials  | Service integration with client credentials      | Low                 |
+---------------------------+--------------------------------------------------+---------------------+
| SOAP Security Token       | Legacy applications needing security token auth  | Medium              |
+---------------------------+--------------------------------------------------+---------------------+
| SOAP IP Filtering         | Orgs with IP restrictions enabled                | Medium              |
+---------------------------+--------------------------------------------------+---------------------+

Lazy Authentication (Auto-selection)
------------------------------------

For most use cases, you can use the ``lazy_login`` function which automatically selects the appropriate authentication method based on the provided parameters:

.. code-block:: python

   from sf_toolkit import SalesforceClient, lazy_login

   # CLI Authentication
   client = SalesforceClient(login=lazy_login(sf_cli_alias="my-org"))

   # OAuth JWT Bearer Flow
   with open("private_key.pem", "rb") as f:
       private_key_data = f.read()
   client = SalesforceClient(
       login=lazy_login(
           username="user@example.com",
           consumer_key="your_consumer_key",
           private_key=private_key_data
       )
   )

   # Username-Password Flow
   client = SalesforceClient(
       login=lazy_login(
           username="user@example.com",
           password="password",
           consumer_key="your_consumer_key",
           consumer_secret="your_consumer_secret"
       )
   )

CLI-based Authentication
-----------------------

If you're using the Salesforce CLI (sf or sfdx), this is the simplest method for local development:

.. code-block:: python

   from sf_toolkit import SalesforceClient, cli_login

   # Use default org from CLI
   client = SalesforceClient(login=cli_login())

   # Use a specific org by alias or username
   client = SalesforceClient(login=cli_login(alias_or_username="my-dev-org"))

   # Specify the path to the CLI executable
   client = SalesforceClient(login=cli_login(sf_exec_path="/custom/path/to/sf"))

This method:

- Uses the existing authentication from your Salesforce CLI
- Doesn't require storing credentials in your code
- Works with any authentication method supported by the CLI
- Automatically handles token refresh

OAuth 2.0 Authentication
-----------------------

Salesforce Toolkit supports several OAuth 2.0 flows for different use cases:

Username-Password Flow
^^^^^^^^^^^^^^^^^^^^^^

For simple scripting and personal applications:

.. code-block:: python

   from sf_toolkit import SalesforceClient, password_login

   client = SalesforceClient(
       login=password_login(
           username="user@example.com",
           password="password",
           consumer_key="your_consumer_key",
           consumer_secret="your_consumer_secret",
           domain="login"  # or your custom domain
       )
   )

.. warning::
   This method requires storing your password in your code or configuration.
   Consider using other methods for production applications.

JWT Bearer Flow
^^^^^^^^^^^^^^

For secure server-to-server integration:

.. code-block:: python

   import pathlib
   from sf_toolkit import SalesforceClient, public_key_auth_login

   # Load private key
   private_key_path = pathlib.Path("path/to/private_key.key")
   private_key = private_key_path.read_bytes()

   client = SalesforceClient(
       login=public_key_auth_login(
           username="user@example.com",
           consumer_key="your_connected_app_consumer_key",
           private_key=private_key,
           domain="login"  # or your custom domain
       )
   )

This method:

- Does not require storing user passwords
- Uses digital signatures to securely authenticate
- Is ideal for automated applications and server-to-server integrations
- Requires a connected app with a digital certificate

Client Credentials Flow
^^^^^^^^^^^^^^^^^^^^^

For service-to-service integration without a specific user context:

.. code-block:: python

   from sf_toolkit import SalesforceClient, client_credentials_flow_login

   client = SalesforceClient(
       login=client_credentials_flow_login(
           consumer_key="your_consumer_key",
           consumer_secret="your_consumer_secret",
           domain="login"  # or your custom domain
       )
   )

This method:

- Uses client credentials for authentication without a user context
- Requires a connected app configured for the client credentials flow
- Is useful for background service integrations

SOAP Authentication
------------------

Salesforce Toolkit supports various SOAP-based authentication methods for compatibility with different security configurations:

Security Token Authentication
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For orgs that require a security token with the password:

.. code-block:: python

   from sf_toolkit import SalesforceClient, security_token_login

   client = SalesforceClient(
       login=security_token_login(
           username="user@example.com",
           password="password",
           security_token="your_security_token",
           client_id="YourAppName",  # Optional identifier for your app
           domain="login",  # Or your custom domain
           api_version=63.0  # Salesforce API version
       )
   )

IP Filtering Authentication
^^^^^^^^^^^^^^^^^^^^^^^^^^

For orgs with IP filtering enabled that allow specific IPs to skip the security token:

.. code-block:: python

   from sf_toolkit import SalesforceClient, ip_filtering_non_service_login

   client = SalesforceClient(
       login=ip_filtering_non_service_login(
           username="user@example.com",
           password="password",
           client_id="YourAppName",  # Optional
           domain="login",  # Or your custom domain
           api_version=63.0  # Salesforce API version
       )
   )

Organization-Scoped Login
^^^^^^^^^^^^^^^^^^^^^^^^

For logging in to a specific organization within a multi-org setup:

.. code-block:: python

   from sf_toolkit import SalesforceClient, ip_filtering_org_login

   client = SalesforceClient(
       login=ip_filtering_org_login(
           username="user@example.com",
           password="password",
           organizationId="00Dxxxxxxxxxx",  # Your org ID
           client_id="YourAppName",  # Optional
           domain="login",  # Or your custom domain
           api_version=63.0  # Salesforce API version
       )
   )

Using Tokens Directly
-------------------

If you already have a Salesforce access token and instance URL:

.. code-block:: python

   from sf_toolkit import SalesforceClient, SalesforceToken
   from httpx import URL

   # Create a token directly
   token = SalesforceToken(
       instance=URL("https://myinstance.my.salesforce.com"),
       token="00D..."  # Your access token
   )

   # Use the token
   client = SalesforceClient(token=token)

Token Refresh and Callbacks
-------------------------

You can register a callback function to be executed when a token is refreshed:

.. code-block:: python

   def token_updated(token):
       # Save token to database or file
       print(f"Token updated for {token.instance}")
       with open("token.txt", "w") as f:
           f.write(f"{token.instance}|{token.token}")

   client = SalesforceClient(
       login=cli_login(),
       token_refresh_callback=token_updated
   )

Best Practices
------------

1. **Don't hardcode credentials**: Store secrets in environment variables or a secure credential store.

   .. code-block:: python

      import os

      client = SalesforceClient(
          login=password_login(
              username=os.environ["SF_USERNAME"],
              password=os.environ["SF_PASSWORD"],
              consumer_key=os.environ["SF_CONSUMER_KEY"],
              consumer_secret=os.environ["SF_CONSUMER_SECRET"]
          )
      )

2. **Use the strongest authentication method available**:
   - JWT Bearer for server applications
   - CLI login for development
   - Avoid storing passwords in code

3. **Implement token persistence** to avoid unnecessary authentications:

   .. code-block:: python

      import os
      import json
      from httpx import URL
      from sf_toolkit import SalesforceClient, SalesforceToken, cli_login

      # Try to load saved token
      token = None
      token_file = "saved_token.json"

      if os.path.exists(token_file):
          try:
              with open(token_file, "r") as f:
                  data = json.load(f)
                  token = SalesforceToken(
                      instance=URL(data["instance"]),
                      token=data["token"]
                  )
          except Exception as e:
              print(f"Error loading token: {e}")

      # Save token on refresh
      def save_token(token):
          with open(token_file, "w") as f:
              json.dump({
                  "instance": str(token.instance),
                  "token": token.token
              }, f)

      # Create client with token or login method
      client = SalesforceClient(
          login=None if token else cli_login(),
          token=token,
          token_refresh_callback=save_token
      )

4. **Handle token expiration gracefully**:
   Salesforce Toolkit automatically attempts to refresh tokens when they expire during a request.

Authentication Classes
--------------------

Under the hood, these authentication methods use these core classes:

* ``SalesforceAuth`` - HTTPX authentication class that handles token management and refresh
* ``SalesforceToken`` - Named tuple that represents a Salesforce access token with instance URL
* ``SalesforceLogin`` - A callable that performs the authentication flow and returns a token
* ``TokenRefreshCallback`` - A callable type for token refresh callbacks
