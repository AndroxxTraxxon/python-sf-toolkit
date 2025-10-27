Working with SObjects
===================

SObject is the base class for Salesforce object models. It provides a Pythonic interface for working with Salesforce records.

Defining SObjects
---------------

Create a class that inherits from ``SObject`` and define fields:

.. code-block:: python

   from sf_toolkit import SObject
   from sf_toolkit.data.fields import IdField, TextField, NumberField, DateField, FieldFlag

   class Account(SObject, api_name="Account"):
       Id = IdField()
       Name = TextField()
       AnnualRevenue = NumberField()
       Industry = TextField()
       Rating = TextField()

Field Types
----------

Salesforce Toolkit provides various field types that map to Salesforce field types:

* ``TextField`` - For string, text, picklist fields
* ``IdField`` - For Salesforce ID fields
* ``NumberField`` - For numeric fields
* ``IntField`` - For integer fields
* ``CheckboxField`` - For boolean fields
* ``DateField`` - For date fields
* ``DateTimeField`` - For datetime fields
* ``TimeField`` - For time fields
* ``PicklistField`` - For picklist fields with validation
* ``MultiPicklistField`` - For multi-select picklist fields
* ``ReferenceField`` - For lookup/master-detail relationship fields

Field Flags
----------

Field flags can be used to set properties on fields:

* ``FieldFlag.nillable`` - Field can be null
* ``FieldFlag.unique`` - Field must be unique
* ``FieldFlag.readonly`` - Field cannot be modified
* ``FieldFlag.createable`` - Field can be set on creation
* ``FieldFlag.updateable`` - Field can be updated

CRUD Operations
-------------

Creating Records
^^^^^^^^^^^^^^

.. code-block:: python

   # Create new record
   account = Account(
       Name="Test Account",
       Industry="Technology",
       Rating="Hot"
   )

   # Insert into Salesforce
   save_insert(account)

Reading Records
^^^^^^^^^^^^^

.. code-block:: python

   # Retrieve by ID
   account: Account = fetch(Account, "001xxxxxxxxxxxxxxx")

   # Fetch multiple records
   accounts: SObjectList[Account] = fetch_list(Account, "001xxxxxxxxxxxxxxx", "001yyyyyyyyyyyyyyy")

Updating Records
^^^^^^^^^^^^^^

.. code-block:: python

   account = read(Account, "001xxxxxxxxxxxxxxx")
   account.Name = "Updated Name"
   account.Rating = "Warm"

   # Update in Salesforce
   account.save_update()

   # Only send modified fields
   account.save_update(only_changes=True)

Deleting Records
^^^^^^^^^^^^^^

.. code-block:: python

   account = read(Account, "001xxxxxxxxxxxxxxx")
   account.delete()

Upsert with External ID
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   account = Account(
       ExternalId__c="EXT123",
       Name="New Account"
   )

   # Upsert based on external ID
   account.save_upsert(external_id_field="ExternalId__c")

Dynamic SObject Creation
----------------------

You can also create SObject classes dynamically from Salesforce metadata:

.. code-block:: python

   # Generate SObject class from describe metadata
   Contact = SObject.from_description("Contact")

   # Use the dynamically created class
   contact = Contact(FirstName="John", LastName="Doe")
   contact.save()
