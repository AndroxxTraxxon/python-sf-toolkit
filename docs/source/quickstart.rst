Quickstart
=========

Basic Usage
----------

This guide will help you get started with Salesforce Toolkit quickly.

Authentication
-------------

First, import the necessary modules and authenticate:

.. code-block:: python

   from sf_toolkit import SalesforceClient, cli_login

   # Using SF CLI Authentication
   with SalesforceClient(login=cli_login()) as sf:
       # Now you can use the client
       print(sf.versions)

Working with SObjects
-------------------

Define a Salesforce object:

.. code-block:: python

   from sf_toolkit import SObject
   from sf_toolkit.data.fields import IdField, TextField, DateTimeField, FieldFlag

   class Contact(SObject, api_name="Contact"):
       Id = IdField()
       FirstName = TextField()
       LastName = TextField()
       Email = TextField()
       CreatedDate = DateTimeField(FieldFlag.readonly)

Querying Records
--------------

.. code-block:: python

   from sf_toolkit.data.query_builder import SoqlSelect

   # Query contacts
   query = SoqlSelect(Contact)
   results = query.query()

   # Process results
   for contact in results.records:
       print(f"{contact.FirstName} {contact.LastName}: {contact.Email}")

Creating Records
--------------

.. code-block:: python

   # Create a new contact
   new_contact = Contact(
       FirstName="John",
       LastName="Doe",
       Email="john.doe@example.com"
   )
   
   # Save to Salesforce
   new_contact.save()

Updating Records
--------------

.. code-block:: python

   # Update an existing contact
   contact = Contact.read("003xxxxxxxxxxxx")
   contact.LastName = "Smith"
   contact.save()

Next Steps
---------

For more advanced usage, see the :doc:`client` and :doc:`sobjects` sections.