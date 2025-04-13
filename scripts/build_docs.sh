#!/bin/bash
set -e

# Navigate to the project root
cd "$(dirname "$0")/.."

# Make sure dependencies are installed
python -m pip install -e .[docs]

# Clean previous build
rm -rf docs/build

# Build the documentation
sphinx-build -b html docs/source docs/build/html

echo "Documentation built successfully! Open docs/build/html/index.html to view."
