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
from sf_toolkit import SalesforceClient, SObject, cli_login
from sf_toolkit.data.fields import IdField, TextField

# Define a Salesforce object model
class Account(SObject, api_name="Account"):
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
    query = SoqlSelect(Account)
    results = query.query()

    for acc in results.records:
        print(f"{acc.Name} ({acc.Industry})")
```

## Documentation

For full documentation, visit [docs.example.com](https://docs.example.com).
### Building the documentation

You can build the documentation locally with:

```bash
# One-time build
python -m sphinx -b html docs/source docs/build/html

# Or with auto-reload during development
sphinx-autobuild docs/source docs/build/html
```

The documentation is automatically built from docstrings in the code, so make sure to write
comprehensive docstrings for all public classes and methods.

## License

MIT
