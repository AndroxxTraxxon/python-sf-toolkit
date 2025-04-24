Querying Records
==============

Salesforce Toolkit provides a powerful query builder for creating and executing SOQL queries.

Basic Queries
-----------

The simplest way to create a query is using the ``select()`` method on your SObject class:

.. code-block:: python

   from sf_toolkit.data import SObject
   from sf_toolkit.data.fields import IdField, TextField

   class Account(SObject):
       Id = IdField()
       Name = TextField()
       Industry = TextField()

   # Create a query for all fields
   query = Account.select()

   # Execute the query
   results = query.execute()

   # Process results
   for account in results.records:
       print(account.Name)

Filtering Records
--------------

You can filter records using the ``where()`` method with field conditions:

.. code-block:: python

   # Simple equality condition
   query = Account.select().where(Industry="Technology")

   # Comparison operators using field__operator syntax
   query = Account.select().where(
       AnnualRevenue__gt=1000000,    # Greater than
       Name__like="Test%"            # LIKE operator
   )

   # IN operator
   query = Account.select().where(Industry__in=["Technology", "Healthcare"])

Complex Conditions
---------------

For more complex conditions, use the logical operators ``AND`` and ``OR``:

.. code-block:: python

   from sf_toolkit.data.query_builder import AND, OR, EQ, GT

   # Complex boolean logic
   query = Account.select().where(
       OR(
           EQ("Industry", "Technology"),
           AND(
               GT("AnnualRevenue", 1000000),
               GT("NumberOfEmployees", 100)
           )
       )
   )

Raw WHERE Clauses
--------------

You can also use raw SOQL WHERE clauses for advanced filtering:

.. code-block:: python

   query = Account.select().where(
       "Name LIKE 'Test%' AND CreatedDate = LAST_N_DAYS:30"
   )

Grouping and Aggregates
--------------------

Support for GROUP BY and HAVING clauses:

.. code-block:: python

   # Basic GROUP BY
   query = Account.select().group_by("Industry")

   # GROUP BY with HAVING clause
   query = Account.select().group_by("Industry").having(
       COUNT__Id__gt=5
   )

   # Multiple HAVING conditions
   query = Account.select().group_by("Industry").having(
       COUNT__Id__gt=5
   ).and_having(
       SUM__AnnualRevenue__gt=1000000
   ).or_having(
       SUM__AnnualRevenue__gt=5000000
   )

Sorting Results
------------

Order results using the ``order_by()`` method:

.. code-block:: python

   from sf_toolkit.data.query_builder import Order

   # Using Order objects
   query = Account.select().order_by(Order("Name", "DESC"))

   # Using field=direction syntax
   query = Account.select().order_by(Name="DESC", CreatedDate="ASC")

Pagination
--------

Control result pagination using ``limit()`` and ``offset()``:

.. code-block:: python

   query = Account.select().limit(10).offset(20)

Handling Results
-------------

Query results are returned as a ``QueryResult`` object:

.. code-block:: python

   results = query.execute()

   # Check if all records were retrieved
   if not results.done:
       # Get next batch of records
       more_results = results.query_more()

   # Get total record count
   total = results.totalSize

   # Access records (returns SObjectList)
   records = results.records

Counting Records
-------------

Execute a COUNT() query to get the total number of matching records:

.. code-block:: python

   query = Account.select().where(Industry="Technology")
   count = query.count()
   print(f"Found {count} Technology accounts")

Tooling API Queries
----------------

Query Tooling API objects by setting the ``tooling=True`` flag on your SObject class:

.. code-block:: python

   class CustomObject(SObject, tooling=True):
       Id = IdField()
       Name = TextField()

   # Query will automatically use the Tooling API endpoint
   results = CustomObject.select().execute()

Date and DateTime Values
--------------------

Handle date and datetime values in queries:

.. code-block:: python

   from datetime import datetime, date

   # Query with datetime
   now = datetime.now().astimezone()
   query = Account.select().where(CreatedDate__gt=now)

   # Query with date
   today = date.today()
   query = Opportunity.select().where(CloseDate=today)