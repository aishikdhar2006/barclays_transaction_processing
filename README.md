<!--
Copyright (c) BankingPlatform, Inc. and affiliates.

This source code is licensed under the BSD license found in the
LICENSE file in the root directory of this source tree.
-->

<p align="center">
  <h1 align="center">banking_tools</h1>
</p>

<p align="center">
<a href="https://pypi.org/project/banking_tools/"><img alt="PyPI" src="https://img.shields.io/pypi/v/banking_tools"></a>
<a href="https://github.com/aishikdhar2006/banking_tools/actions"><img alt="Actions Status" src="https://github.com/aishikdhar2006/banking_tools/actions/workflows/python-package.yml/badge.svg"></a>
<a href="https://github.com/aishikdhar2006/banking_tools/blob/main/LICENSE"><img alt="GitHub license" src="https://img.shields.io/github/license/aishikdhar2006/banking_tools"></a>
</p>

banking_tools is a command-line transaction processing platform that validates, processes, and settles banking transactions across multiple formats and compliance standards.

```sh
# Install banking_tools
pip install banking_tools

# Process and settle transactions in the directory
banking_tools process_and_settle MY_TRANSACTIONS_DIR

# List all commands
banking_tools --help
```

<!--ts-->

- [Supported Formats](#supported-formats)
  - [Transaction Formats](#transaction-formats)
  - [Batch Formats](#batch-formats)
- [Installation](#installation)
  - [Standalone Executable](#standalone-executable)
  - [Installing via pip](#installing-via-pip)
- [Usage](#usage)
  - [Process and Settle](#process-and-settle)
  - [Process](#process)
  - [Settle](#settle)
- [Advanced Usage](#advanced-usage)
  - [Batch Transaction Processing](#batch-transaction-processing)
    - [Data Converter Setup](#data-converter-setup)
    - [Batch Processing](#batch-processing)
  - [Compliance Validation with Audit Trails](#compliance-validation-with-audit-trails)
  - [Authenticate](#authenticate)
  - [Transaction Description](#transaction-description)
  - [Archive Transactions](#archive-transactions)
- [Development](#development)
  - [Setup](#setup)
  - [Running the code](#running-the-code)
  - [Tests](#tests)
  - [Code Quality](#code-quality)
  - [Release and Build](#release-and-build)

<!--te-->

# Supported Formats

banking_tools can process both individual transactions and batch files.

## Transaction Formats

banking_tools supports standard transaction record files (.txn, .csv), with the following fields minimally required:

- Account Number
- Transaction Amount
- Date/Time of Transaction

## Batch Formats

banking_tools supports batch transaction files (.batch, .dat) that contain any of the following structures:

- [SWIFT](https://www.swift.com/): International wire transfer messages
  - MT103 (Single Customer Credit Transfer)
  - MT202 (General Financial Institution Transfer)
- [ISO 20022](https://www.iso20022.org/): Modern XML-based financial messaging
  - pain.001 (Customer Credit Transfer Initiation)
  - pacs.008 (Financial Institution Credit Transfer)
- [ACH/NACHA](https://www.nacha.org/) batch files
  - Direct Deposits
  - Direct Payments

# Installation

## Standalone Executable

1. Download the latest executable for your platform from the [releases](https://github.com/aishikdhar2006/banking_tools/releases).
2. Move the executable to your system `$PATH`

## Installing via pip

To install or upgrade to the latest stable version:

```sh
pip install --upgrade banking_tools
```

If you can't wait for the latest features in development, install it from GitHub:

```sh
pip install --upgrade git+https://github.com/aishikdhar2006/banking_tools
```

# Usage

## Process and Settle

The `process_and_settle` command validates, processes, and settles transactions in a single step:

```sh
banking_tools process_and_settle MY_TRANSACTIONS_DIR
```

## Process

The `process` command validates and processes transactions without settling:

```sh
banking_tools process MY_TRANSACTIONS_DIR
```

## Settle

The `settle` command settles previously processed transactions:

```sh
banking_tools settle MY_TRANSACTIONS_DIR
```

# Advanced Usage

## Batch Transaction Processing

### Data Converter Setup

Install the data conversion utilities for batch processing:

```sh
# Install data converter dependencies
pip install banking_tools[batch]
```

### Batch Processing

Process batch transaction files:

```sh
# Process batch files with compliance validation
banking_tools batch_process MY_BATCH_DIR
```

## Compliance Validation with Audit Trails

Tag transactions with compliance data from audit trail files:

```sh
banking_tools process MY_TRANSACTIONS_DIR \
    --compliance_source "audit_trail" \
    --compliance_path MY_AUDIT_TRAIL.xml
```

## Authenticate

Authenticate with the banking settlement gateway:

```sh
banking_tools authenticate
```

## Transaction Description

The `process` command generates a transaction description file summarizing all validated transactions:

```sh
banking_tools process MY_TRANSACTIONS_DIR
```

## Archive Transactions

Archive processed transactions for long-term storage:

```sh
# Archive processed transactions
banking_tools archive MY_TRANSACTIONS_DIR MY_ARCHIVE_DIR

# Settle from archived files
banking_tools settle --file_types archive MY_ARCHIVE_DIR
```

# Development

## Setup

Clone the repository:

```sh
git clone git@github.com:aishikdhar2006/banking_tools.git
cd banking_tools
```

### Option 1: Using uv (Recommended)

Use [uv](https://docs.astral.sh/uv/) - a fast Python package manager.

Install the project in development mode with all dependencies:

```sh
# Install the project and development dependencies
uv sync --group dev

# Activate the virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### Option 2: Using pip with virtual environment

Set up a virtual environment (recommended):

```sh
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

Install the project in development mode:

```sh
# Install the project and all dependencies in editable mode
pip install -e .

# Install development dependencies
pip install --group dev
```

## Running the code

Run the code from the repository:

```sh
# If you have banking_tools installed in editable mode
banking_tools --version

# Alternatively
python -m banking_tools.commands --version
```

## Tests

Run tests:

```sh
# Test all cases
pytest -s -vv tests
# Or test a single case specifically
pytest -s -vv tests/unit/test_ledger_parser.py::test_build_and_parse
```

## Code Quality

Run code formatting and linting:

```sh
# Format code with ruff
ruff format banking_tools tests

# Lint code with ruff
ruff check banking_tools tests

# Sort imports with usort
usort format banking_tools tests

# Type checking with mypy
mypy banking_tools
```

## Release and Build

```sh
# Assume you are releasing v0.9.1a2 (alpha2)

# Tag your local branch
git tag -f v0.9.1a2

# Push the tagged commit first if it is not there yet
git push origin

# Push ALL local tags
git push origin --tags -f
```
