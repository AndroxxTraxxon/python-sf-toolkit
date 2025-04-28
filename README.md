# Salesforce Toolkit for Python

A modern, Pythonic interface to Salesforce APIs.

## Features

- Clean, intuitive API design
- Both synchronous and asynchronous client support
- Simple SObject modeling using Python classes
- Powerful query builder for SOQL queries
- Efficient batch operations
- Automatic session management and token refresh

## Installation

```bash
pip install sf-toolkit
```

## Quick Start

```python
from sf_toolkit import SalesforceClient, SObject, cli_login, query
from sf_toolkit.data.fields import IdField, TextField

# Define a Salesforce object model
class Account(SObject):
    Id = IdField()
    Name = TextField()
    Industry = TextField()
    Description = TextField()

# Connect to Salesforce using the CLI authentication
with SalesforceClient(login=cli_login()) as sf:
    # Create a new account
    account = Account(Name="Acme Corp", Industry="Technology")
    account.save()

    # Query accounts
    result = Account.query().execute()

    for acc in result:
        print(f"{acc.Name} ({acc.Industry}) {acc.Description}")
```
