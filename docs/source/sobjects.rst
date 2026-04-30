Working with SObjects
=====================

``SObject`` is the base class for Salesforce object models. It provides a Pythonic interface for working with Salesforce records, mapping field types to native Python types and exposing module-level CRUD helpers in :mod:`sf_toolkit.io`.

Defining SObjects
-----------------

Create a class that inherits from ``SObject`` and define fields. The ``api_name`` keyword argument controls which Salesforce SObject this class maps to (when omitted, the class name is used):

.. code-block:: python

   from sf_toolkit import SObject
   from sf_toolkit.data.fields import IdField, TextField, NumberField, FieldFlag

   class Account(SObject, api_name="Account"):
       Id = IdField()
       Name = TextField()
       AnnualRevenue = NumberField()
       Industry = TextField()
       Rating = TextField()

Class-level options
^^^^^^^^^^^^^^^^^^^

``SObject`` subclasses accept several keyword arguments at class-definition time:

- ``api_name`` — Salesforce API name for this object (defaults to the class name).
- ``connection`` — Name of a registered :class:`~sf_toolkit.SalesforceClient` connection to use by default for this SObject. When omitted, the default connection is used.
- ``id_field`` — Field name to treat as the record's identifier (defaults to ``"Id"``). Useful for objects whose primary identifier isn't ``Id``.
- ``tooling`` — Set to ``True`` to use the Tooling API endpoints instead of the standard Data API.

.. code-block:: python

   class CustomToolingObject(
       SObject,
       api_name="CustomObject__c",
       connection="my_org",
       tooling=True,
   ):
       Id = IdField()
       Name = TextField()

Field Types
-----------

Salesforce Toolkit provides field types that map to Salesforce field types and convert values to/from native Python types:

* ``TextField`` — string, text, and (untyped) picklist fields
* ``IdField`` — Salesforce ID fields, with 15/18-character validation
* ``NumberField`` — floating-point numeric fields
* ``IntField`` — integer fields
* ``CheckboxField`` — boolean fields
* ``DateField`` — date fields (:class:`datetime.date`)
* ``DateTimeField`` — datetime fields (:class:`datetime.datetime`)
* ``TimeField`` — time fields (:class:`datetime.time`)
* ``PicklistField`` — picklist fields with allowed-value validation
* ``MultiPicklistField`` — multi-select picklist fields (semicolon-delimited)
* ``ReferenceField`` — lookup / master-detail relationship fields
* ``ListField`` — child-relationship fields (subqueries)
* ``BlobField`` — binary content fields; see :doc:`blobfield`
* ``RawField`` — passthrough field that performs no validation or conversion

Picklist option lists are passed using the ``options`` keyword:

.. code-block:: python

   from sf_toolkit.data.fields import PicklistField, MultiPicklistField

   class Account(SObject, api_name="Account"):
       Rating = PicklistField(options=["Hot", "Warm", "Cold"])
       Categories__c = MultiPicklistField(options=["A", "B", "C"])

Field Flags
-----------

Field flags are passed positionally to a field constructor and describe its behavior:

* ``FieldFlag.nillable`` — field can be null
* ``FieldFlag.unique`` — field must be unique
* ``FieldFlag.readonly`` — field cannot be assigned after initialization
* ``FieldFlag.case_sensitive`` — text comparisons are case-sensitive
* ``FieldFlag.updateable`` — field can be updated
* ``FieldFlag.createable`` — field can be set on creation
* ``FieldFlag.calculated`` — field is calculated by Salesforce (formula, etc.)
* ``FieldFlag.filterable`` — field can be used in WHERE clauses
* ``FieldFlag.sortable`` — field can be used in ORDER BY clauses
* ``FieldFlag.groupable`` — field can be used in GROUP BY clauses
* ``FieldFlag.permissionable`` — field-level security can be applied
* ``FieldFlag.restricted_picklist`` — picklist values are restricted
* ``FieldFlag.display_location_in_decimal`` — geolocation fields display in decimal
* ``FieldFlag.write_requires_master_read`` — master-detail field requires master read

.. code-block:: python

   from sf_toolkit.data.fields import DateTimeField, FieldFlag

   class Account(SObject, api_name="Account"):
       CreatedDate = DateTimeField(FieldFlag.readonly)

Default Field Values
--------------------

You can specify a default value for a field so that new SObject instances automatically receive a value when one is not provided in the constructor.

Passing a static default:

.. code-block:: python

   from sf_toolkit.data.fields import (
       TextField, CheckboxField, PicklistField, MultiPicklistField,
   )

   class Account(SObject, api_name="Account"):
       Name = TextField()
       Active__c = CheckboxField(default=True)
       Rating = PicklistField(options=["Hot", "Warm", "Cold"], default="Cold")
       Categories__c = MultiPicklistField(
           options=["A", "B", "C"], default=["A", "C"]
       )

   # Active__c, Rating, Categories__c are filled automatically
   account = Account(Name="Example")
   assert account.Active__c is True
   assert account.Rating == "Cold"
   assert set(account.Categories__c.values) == {"A", "C"}

Using a callable default (evaluated per instance):

.. code-block:: python

   from datetime import date, datetime
   from sf_toolkit.data.fields import DateField, DateTimeField, PicklistField

   class Task(SObject, api_name="Task"):
       DueDate__c = DateField(default=date.today)        # called for each new instance
       CreatedMarker__c = DateTimeField(default=datetime.utcnow)

       Priority__c = PicklistField(
           options=["High", "Normal", "Low"], default="Normal"
       )

   task = Task(Subject="Follow Up")
   # If you do not pass DueDate__c, it is set to today's date.

Notes:

* The default is only applied if the field is not supplied when constructing the instance.
* Callables (functions taking no arguments) are supported and invoked once per instance creation.
* Defaults must pass field validation (e.g., picklist values must be in the allowed set).

CRUD Operations
---------------

CRUD helpers are exposed as module-level functions in :mod:`sf_toolkit.io`. Each function takes the SObject instance (or class plus ID) and resolves the Salesforce client either from an explicit ``sf_client=`` argument, the SObject class's ``connection`` attribute, or the default connection.

Each operation has an ``async`` counterpart with the suffix ``_async``; see :doc:`async`.

Creating Records
^^^^^^^^^^^^^^^^

.. code-block:: python

   from sf_toolkit.io import save_insert

   account = Account(
       Name="Test Account",
       Industry="Technology",
       Rating="Hot",
   )

   # Insert into Salesforce; the new Id is set on the record
   save_insert(account)
   print(account.Id)

Reading Records
^^^^^^^^^^^^^^^

.. code-block:: python

   from sf_toolkit.io import fetch, fetch_list
   from sf_toolkit.data.sobject import SObjectList

   # Retrieve by ID
   account: Account = fetch(Account, "001xxxxxxxxxxxxxxx")

   # Fetch many records by ID using the composite API
   accounts: SObjectList[Account] = fetch_list(
       Account, "001xxxxxxxxxxxxxxx", "001yyyyyyyyyyyyyyy"
   )

To re-pull a record's current values from Salesforce, use :func:`~sf_toolkit.io.api.reload`:

.. code-block:: python

   from sf_toolkit.io.api import reload

   reload(account)

Updating Records
^^^^^^^^^^^^^^^^

.. code-block:: python

   from sf_toolkit.io import fetch, save_update

   account = fetch(Account, "001xxxxxxxxxxxxxxx")
   account.Name = "Updated Name"
   account.Rating = "Warm"

   # Update in Salesforce
   save_update(account)

   # Send only the modified fields
   save_update(account, only_changes=True)

Deleting Records
^^^^^^^^^^^^^^^^

.. code-block:: python

   from sf_toolkit.io import delete, fetch

   account = fetch(Account, "001xxxxxxxxxxxxxxx")
   delete(account)

Upsert with External ID
^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from sf_toolkit.io import save_upsert

   account = Account(
       ExternalId__c="EXT123",
       Name="New Account",
   )

   # Upsert based on external ID
   save_upsert(account, external_id_field="ExternalId__c")

Generic ``save``
^^^^^^^^^^^^^^^^

:func:`~sf_toolkit.io.save` automatically chooses between ``save_insert``, ``save_update``, and ``save_upsert`` based on the state of the record and the arguments passed:

.. code-block:: python

   from sf_toolkit.io import save

   # No Id set -> insert
   save(Account(Name="New"))

   # Id set -> update
   account.Name = "Updated"
   save(account)

   # external_id_field provided -> upsert
   save(account, external_id_field="ExternalId__c")

Working with SObjectList
------------------------

:class:`~sf_toolkit.data.sobject.SObjectList` is a typed list of SObject records that ships with bulk-friendly helpers. Pass it to one of the list helpers in :mod:`sf_toolkit.io` to operate on many records using Salesforce's composite API:

.. code-block:: python

   from sf_toolkit.data.sobject import SObjectList
   from sf_toolkit.io import (
       save_list,
       save_insert_list,
       save_update_list,
       save_upsert_list,
       delete_list,
   )

   accounts = SObjectList(
       Account(Name=f"Bulk Account {i}") for i in range(100)
   )

   # Generic save (insert/update/upsert per record)
   results = save_list(accounts)

   # Operation-specific helpers
   save_insert_list(accounts, batch_size=200)
   save_update_list(accounts, only_changes=True)
   save_upsert_list(accounts, external_id_field="ExternalId__c")
   delete_list(accounts)

For datasets that exceed the composite-API limits (typically 10k+ records), see :doc:`bulk_api`.

Dynamic SObject Creation
------------------------

You can also create SObject classes dynamically from Salesforce describe metadata using :func:`~sf_toolkit.io.sobject_from_description`:

.. code-block:: python

   from sf_toolkit.io import sobject_from_description

   # Generate an SObject class from describe metadata
   Contact = sobject_from_description("Contact")

   # Use the dynamically created class like any other SObject
   contact = Contact(FirstName="John", LastName="Doe")
   save_insert(contact)

You can narrow the generated class to a subset of fields with the ``include_fields`` or ``ignore_fields`` arguments, or pass a custom ``base_class`` to add behavior to the generated type.

Blob (File) Fields
------------------

For SObjects that hold file content (``ContentVersion``, ``Document``, ``Attachment``), define a :class:`~sf_toolkit.BlobField`. SF Toolkit handles the multipart upload automatically when you call ``save_insert`` / ``save_update`` / ``save``. See :doc:`blobfield` for details.
