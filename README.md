# sf-toolkit: A Salesforce API Adapter for Python

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python: ^3.11](https://img.shields.io/badge/Python-^3.11-blue.svg)

`sf-toolkit` is a modern Python library designed to simplify interactions with Salesforce APIs. This toolkit provides a clean, Pythonic interface for working with Salesforce data and features.

## 🚧 Early Development Notice

This project is in its early stages. The API is subject to change, and not all features are fully implemented yet. Contributions and feedback are welcome!

## Features

- Seamless authentication with Salesforce using the SF/SFDX CLI
- Synchronous and asynchronous HTTP clients
- SOQL query building with type safety
- Proper handling of Salesforce data types and formatting

## Installation

```bash
pip install sf-toolkit
```

Or with Poetry:

```bash
poetry add sf-toolkit
```

## Quick Start

```python
from sf_toolkit.auth import cli_login
from sf_toolkit.session import Salesforce

# Use the built-in CLI authenticator
auth = cli_login()  # Uses the default org from SF CLI
# Or specify an org alias/username
# auth = cli_login("my-org-alias")

# Create a Salesforce session
sf = Salesforce(login=auth)

# Use as a context manager for automatic resource cleanup
with sf:
    # Coming soon: Query, create, update, and delete records
    pass

# Or use it asynchronously
async with sf:
    # Async operations
    pass
```

## SOQL Query Building (Preview)

The library includes a type-safe SOQL query builder (in development):

```python
from sf_toolkit.data.query_builder import SoqlSelect, Comparison, BooleanOperation

# This feature is under development
query = SoqlSelect(
    fields=["Id", "Name", "CreatedDate"],
    sobject="Account",
    where=Comparison("Name", "LIKE", "Acme%"),
    limit=10
)

# Will generate: SELECT Id, Name, CreatedDate FROM Account WHERE Name LIKE 'Acme%' LIMIT 10
```

## Requirements

- Python 3.11 or higher
- Salesforce CLI (sf or sfdx) installed for CLI-based authentication

## Dependencies

- httpx: Modern HTTP client with sync and async support
- jwt: JSON Web Token implementation
- lxml: XML processing library

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

Contributions are welcome! As this project is in its early stages, there's plenty of opportunity to help shape its future.
