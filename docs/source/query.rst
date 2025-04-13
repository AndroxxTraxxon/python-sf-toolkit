Querying Records
==============

Salesforce Toolkit provides a powerful query builder for creating SOQL queries.

SoqlSelect Query Builder
----------------------

The ``SoqlSelect`` class helps build and execute SOQL queries:

.. code-block:: python

   from sf_toolkit.data.query_builder import SoqlSelect
   from sf_toolkit import SObject
   
   class Account(SObject, api_name="Account"):
       Id = IdField()
       Name = TextField()
       Industry = TextField()
   
   # Create a query builder for Account
   query = SoqlSelect(Account)
   
   # Execute the query
   results = query.query()
   
   # Process results
   for account in results.records:
       print(account.Name)

Query Results
-----------

Query results are returned as a ``QueryResult`` object:

.. code-block:: python

   results = query.query()
   
   # Check if more records are available
   if not results.done:
       # Fetch more records
       more_results = results.query_more()
   
   # Get the total count
   total = results.totalSize
   
   # Access the records
   records = results.records

Filtering
--------

You can add WHERE clauses to your queries:

.. code-block:: python

   from sf_toolkit.data.query_builder import SoqlSelect, Comparison, BooleanOperation
   
   # Simple comparison
   query = SoqlSelect(Account)
   query.where = Comparison("Industry", "=", "Technology")
   
   # Complex conditions
   query.where = BooleanOperation(
       "AND",
       [
           Comparison("Industry", "=", "Technology"),
           Comparison("AnnualRevenue", ">", 1000000)
       ]
   )
   
   results = query.query()

Counting Records
--------------

You can execute a COUNT() query:

.. code-block:: python

   query = SoqlSelect(Account)
   query.where = Comparison("Industry", "=", "Technology")
   
   # Get the count of matching records
   count = query.count()
   print(f"Found {count} Technology accounts")

Ordering
-------

Add ORDER BY clauses:

.. code-block:: python

   from sf_toolkit.data.query_builder import Order
   
   query = SoqlSelect(Account)
   query.order = [
       Order("Name", "ASC"),
       Order("AnnualRevenue", "DESC")
   ]
   
   results = query.query()

Limiting and Offsetting
---------------------

Limit the number of records returned:

.. code-block:: python

   query = SoqlSelect(Account)
   query.limit = 10
   query.offset = 20  # Skip first 20 records
   
   results = query.query()