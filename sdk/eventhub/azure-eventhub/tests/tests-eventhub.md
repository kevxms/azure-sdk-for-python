# Azure Event Hubs Testing Guide

This document describes testing considerations specific to the `azure-eventhub` package. For the complete Azure SDK Python testing guide, see [doc/dev/tests.md](../../../../doc/dev/tests.md).

## Event Hubs-Specific Setup

The Event Hubs package uses namespace packages (`azure.eventhub.extensions`) that span multiple installed packages (checkpoint stores). This requires two modifications to the standard setup:

### 1. Install package and dependencies together

Instead of separate install commands, use a single command:

```bash
# Standard approach (may cause import conflicts):
# pip install -r dev_requirements.txt
# pip install -e .

# Event Hubs approach (recommended):
pip install -e . -r dev_requirements.txt
```

### 2. Use `python -m pytest` instead of `pytest`

Always invoke pytest as a module to ensure correct import resolution:

```bash
# Standard approach (may cause import errors):
# pytest tests

# Event Hubs approach (required):
python -m pytest tests
```

**Why?** Running `pytest` directly can cause the interpreter to find the wrong `azure.eventhub` module from site-packages instead of the editable install. Using `python -m pytest` ensures the import machinery is fully initialized before any imports occur.

## Quick Start

```bash
cd sdk/eventhub/azure-eventhub

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1  # Windows
# source .venv/bin/activate   # Linux/macOS

# Install package and dependencies
pip install -e . -r dev_requirements.txt

# Run tests
python -m pytest tests/livetest/synctests/test_consumer_client.py -k test_receive_partition
```

## Troubleshooting

### ImportError: cannot import name 'CheckpointStore' from 'azure.eventhub'

This indicates a namespace package conflict. Solutions:

1. Ensure you're using `python -m pytest` instead of `pytest`
2. Reinstall packages:
   ```bash
   pip uninstall azure-eventhub azure-eventhub-checkpointstoreblob azure-eventhub-checkpointstoreblob-aio -y
   pip install -e . -r dev_requirements.txt
   ```
